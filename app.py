#!/usr/bin/env python3
"""Glide — a sleek, dark-mode desktop GUI for yt-dlp.

Run:  python3 app.py
Needs: pip install -r requirements.txt   (and ffmpeg on PATH, or bundled in bin/ by build.bat)
"""
import json
import os
import platform
import subprocess
import sys
import threading
import uuid
from pathlib import Path

import webview
import yt_dlp

APP_NAME = "Glide"
IS_WIN = sys.platform == "win32"
FROZEN = getattr(sys, "frozen", False)
# Bundled resources live in _MEIPASS when packaged by PyInstaller.
HERE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))

if IS_WIN:
    SETTINGS_FILE = Path(os.environ.get("APPDATA", Path.home())) / APP_NAME / "settings.json"
else:
    SETTINGS_FILE = Path.home() / ".glide-ytdlp.json"

# Put bundled tools (ffmpeg.exe, ffprobe.exe, deno.exe) on PATH so yt-dlp finds them.
_BIN = HERE / "bin"
if _BIN.is_dir():
    os.environ["PATH"] = str(_BIN) + os.pathsep + os.environ.get("PATH", "")


class _QuietLogger:
    """Windowed .exe builds have no console (sys.stdout is None), so never let yt-dlp print."""
    def debug(self, msg): pass
    def info(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): pass

PRESETS = {
    "best":  {"format": "bestvideo*+bestaudio/best", "merge_output_format": "mp4"},
    "1080":  {"format": "bv*[height<=1080]+ba/b[height<=1080]/b", "merge_output_format": "mp4"},
    "720":   {"format": "bv*[height<=720]+ba/b[height<=720]/b", "merge_output_format": "mp4"},
    "mp3":   {"format": "bestaudio/best",
              "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]},
    "m4a":   {"format": "bestaudio[ext=m4a]/bestaudio/best",
              "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "m4a"}]},
}


class Cancelled(Exception):
    pass


class Api:
    def __init__(self):
        self.window = None
        self._cancel = {}
        self.settings = {"folder": str(Path.home() / "Downloads"), "preset": "best", "subs": False, "playlist": False, "cookies": ""}
        try:
            self.settings.update(json.loads(SETTINGS_FILE.read_text()))
        except Exception:
            pass

    # ---------- helpers ----------
    def _emit(self, event, payload):
        if self.window:
            self.window.evaluate_js(f"window.onBackend({json.dumps(event)}, {json.dumps(payload)})")

    def _add_cookies(self, opts):
        browser = self.settings.get("cookies")
        if browser:
            opts["cookiesfrombrowser"] = (browser,)

    def _save(self):
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(self.settings))
        except Exception:
            pass

    # ---------- exposed to JS ----------
    def get_settings(self):
        return {**self.settings, "version": yt_dlp.version.__version__, "platform": sys.platform}

    def set_setting(self, key, value):
        self.settings[key] = value
        self._save()
        return True

    def choose_folder(self):
        res = self.window.create_file_dialog(webview.FOLDER_DIALOG, directory=self.settings["folder"])
        if res:
            folder = res[0] if isinstance(res, (list, tuple)) else res
            self.set_setting("folder", folder)
            return folder
        return None

    def fetch_info(self, url):
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "logger": _QuietLogger(),
                "extract_flat": "in_playlist", "noplaylist": not self.settings.get("playlist")}
        self._add_cookies(opts)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as e:
            return {"error": _clean_err(e)}
        entries = info.get("entries")
        thumb = info.get("thumbnail")
        if not thumb and info.get("thumbnails"):
            thumb = info["thumbnails"][-1].get("url")
        return {
            "title": info.get("title") or url,
            "uploader": info.get("uploader") or info.get("channel") or info.get("extractor_key") or "",
            "duration": info.get("duration"),
            "thumbnail": thumb,
            "site": info.get("extractor_key", ""),
            "count": len(list(entries)) if entries is not None else None,
        }

    def download(self, url, preset, meta=None):
        job_id = uuid.uuid4().hex[:8]
        self._cancel[job_id] = False
        threading.Thread(target=self._run, args=(job_id, url, preset), daemon=True).start()
        return job_id

    def cancel(self, job_id):
        self._cancel[job_id] = True
        return True

    def reveal(self, path):
        if not path:
            return
        system = platform.system()
        if system == "Darwin":
            subprocess.run(["open", "-R", path])
        elif system == "Windows":
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        else:
            subprocess.run(["xdg-open", os.path.dirname(path) or path])

    def open_folder(self):
        folder = self.settings["folder"]
        if IS_WIN:
            os.startfile(folder)
        else:
            subprocess.run([{"Darwin": "open"}.get(platform.system(), "xdg-open"), folder])

    # ---------- worker ----------
    def _run(self, job_id, url, preset):
        def hook(d):
            if self._cancel.get(job_id):
                raise Cancelled()
            if d["status"] == "downloading":
                total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
                done = d.get("downloaded_bytes") or 0
                self._emit("progress", {
                    "id": job_id,
                    "percent": (done / total * 100) if total else None,
                    "downloaded": done, "total": total,
                    "speed": d.get("speed"), "eta": d.get("eta"),
                    "playlist_index": (d.get("info_dict") or {}).get("playlist_index"),
                })
            elif d["status"] == "finished":
                self._emit("stage", {"id": job_id, "stage": "Processing…"})

        def pp_hook(d):
            if self._cancel.get(job_id):
                raise Cancelled()
            if d["status"] == "started":
                name = d.get("postprocessor", "")
                label = {"Merger": "Merging streams…", "ExtractAudio": "Converting audio…"}.get(name, "Processing…")
                self._emit("stage", {"id": job_id, "stage": label})

        opts = {
            "quiet": True, "no_warnings": True, "noprogress": True, "logger": _QuietLogger(),
            "outtmpl": os.path.join(self.settings["folder"], "%(title).180B [%(id)s].%(ext)s"),
            "progress_hooks": [hook], "postprocessor_hooks": [pp_hook],
            "noplaylist": not self.settings.get("playlist"),
            "windowsfilenames": platform.system() == "Windows",
            **PRESETS.get(preset, PRESETS["best"]),
        }
        if self.settings.get("subs"):
            opts.update({"writesubtitles": True, "subtitleslangs": ["en.*", "en"], "embedsubtitles": True})
            if preset in ("mp3", "m4a"):
                opts.pop("embedsubtitles")
            else:
                opts.setdefault("postprocessors", []).append({"key": "FFmpegEmbedSubtitle"})

        self._add_cookies(opts)
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            path = None
            items = info.get("entries") or [info]
            for it in items:
                for rd in (it or {}).get("requested_downloads") or []:
                    path = rd.get("filepath") or path
            self._emit("done", {"id": job_id, "path": path})
        except Cancelled:
            self._emit("cancelled", {"id": job_id})
        except Exception as e:
            if self._cancel.get(job_id):
                self._emit("cancelled", {"id": job_id})
            else:
                self._emit("error", {"id": job_id, "message": _clean_err(e)})
        finally:
            self._cancel.pop(job_id, None)


def _clean_err(e):
    msg = str(e)
    for prefix in ("ERROR: ", "\x1b[0;31mERROR:\x1b[0m "):
        msg = msg.replace(prefix, "")
    msg = msg.split("; please report this issue")[0]
    if "confirm you" in msg and "not a bot" in msg:
        return "YouTube wants you signed in. Set \"Login\" to the browser you use YouTube in, then retry."
    if "could not copy" in msg.lower() and "cookie" in msg.lower():
        return "Couldn't read that browser's login while it's open. Close the browser and retry, or pick Firefox."
    if "decrypt" in msg.lower() and "cookie" in msg.lower():
        return "This browser locks its cookies on Windows. Try Firefox for the Login option."
    return msg.strip()[:300]


def _dark_titlebar(window):
    """Give the Windows 10/11 title bar a dark look that matches the app."""
    try:
        import ctypes
        hwnd = window.native.Handle.ToInt32()
        dwm = ctypes.windll.dwmapi
        on = ctypes.c_int(1)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (new / old builds)
            if dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(on), ctypes.sizeof(on)) == 0:
                break
        color = ctypes.c_int(0x00161414)  # COLORREF 0x00BBGGRR -> #141416 (Windows 11 only)
        dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(color), ctypes.sizeof(color))
    except Exception:
        pass


def selftest(out_file, folder, urls):
    """Headless check used by CI: download each URL as 720p video and as MP3, write a JSON report."""
    events, results = [], []

    class FakeWindow:
        def evaluate_js(self, js):
            events.append(js)

    api = Api()
    api.window = FakeWindow()
    api.settings.update({"folder": folder, "subs": False, "playlist": False})
    for url in urls:
        for preset in ("720", "mp3"):
            events.clear()
            api._run("t", url, preset)
            last = events[-1] if events else ""
            ok = '"done"' in last
            path = None
            if ok:
                path = json.loads(last[last.index(", ") + 2:-1]).get("path")
            results.append({"url": url, "preset": preset, "ok": ok and bool(path) and os.path.exists(path),
                            "path": path, "size": os.path.getsize(path) if path and os.path.exists(path) else 0,
                            "progress_events": sum('"progress"' in e for e in events), "last_event": last[:400]})
    import shutil
    tools = {}
    for tool in ("ffmpeg", "ffprobe", "deno"):
        exe = shutil.which(tool)
        try:
            out = subprocess.run([exe, "-version" if tool != "deno" else "--version"], capture_output=True,
                                 text=True, timeout=30).stdout.splitlines()[0] if exe else None
        except Exception as e:
            out = f"failed: {e}"
        tools[tool] = {"path": exe, "version": out}
    report = {"yt_dlp": yt_dlp.version.__version__, "tools": tools, "results": results}
    Path(out_file).write_text(json.dumps(report, indent=2))
    sys.exit(0 if any(r["ok"] for r in results) else 1)


def main():
    if len(sys.argv) > 3 and sys.argv[1] == "--selftest":
        return selftest(sys.argv[2], sys.argv[3], sys.argv[4:])
    api = Api()
    kwargs = dict(width=880, height=680, min_size=(640, 520), background_color="#141416", js_api=api)
    if sys.platform == "darwin":
        kwargs["vibrancy"] = True
    window = webview.create_window(APP_NAME, str(HERE / "ui.html"), **kwargs)
    api.window = window
    if IS_WIN:
        window.events.shown += lambda: _dark_titlebar(window)
    webview.start(debug=os.environ.get("GLIDE_DEBUG") == "1", private_mode=False)


if __name__ == "__main__":
    main()
