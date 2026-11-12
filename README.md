# Cheese Max: a dark-mode yt-dlp app for Windows

A sleek desktop front end for [yt-dlp](https://github.com/yt-dlp/yt-dlp), packaged as a single `CheeseMax.exe`.

- Paste a link to see a preview (thumbnail, title, channel, length)
- Presets: Best (MP4), 1080p, 720p, MP3, M4A
- Optional subtitles and full-playlist downloads
- Download list with live progress, speed, time left, cancel, retry and "Show in Explorer"
- Dark title bar on Windows 10/11
- ffmpeg and deno are bundled inside the exe, so there's nothing else to install
- Remembers your folder and options (`%APPDATA%\Cheese Max\settings.json`)

## Build the .exe on Windows

1. Double-click **`build.bat`**.
   - If Python isn't installed, the script installs it with winget. Run `build.bat` again afterwards.
2. When it finishes, Explorer opens on **`dist\CheeseMax.exe`**. Copy that file anywhere you like.

The first build downloads about 150 MB (Python packages, ffmpeg, deno) and takes a few minutes.

## Or build it in the cloud (GitHub Actions)

Push this folder to a GitHub repository. The included workflow (`.github/workflows/build-windows.yml`)
builds the exe on a Windows runner. To get the file, open the **Actions** tab, click the latest run,
and download **CheeseMax-windows**.

## Notes

- The exe needs the Microsoft Edge WebView2 runtime. Windows 11 and up-to-date Windows 10 already have it.
- Sites change often. If downloads start failing, run `build.bat` again to pick up the latest yt-dlp.
- The exe unpacks itself on each launch, so it takes a few seconds to open.
- For a faster-starting folder build, change `--onefile` to `--onedir` in `build.bat`.
- To run from source instead: `pip install -r requirements.txt` then `python app.py`.
