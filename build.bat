@echo off
setlocal
cd /d "%~dp0"
title Building Glide.exe
echo.
echo   ==  Building Glide.exe  ==
echo.

rem ---- 1. Find Python -------------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY ( where python >nul 2>nul && set "PY=python" )
if not defined PY (
  echo Python was not found. Installing it with winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python installed. Close this window and double-click build.bat again.
  goto :end
)

rem ---- 2. Virtual env + dependencies --------------------------------------
if not exist .venv (
  echo [1/4] Creating virtual environment...
  %PY% -m venv .venv || goto :fail
)
echo [2/4] Installing dependencies (yt-dlp, pywebview, pyinstaller)...
".venv\Scripts\python.exe" -m pip install -q --upgrade pip
".venv\Scripts\python.exe" -m pip install -q --upgrade -r requirements.txt pyinstaller || goto :fail

rem ---- 3. Download ffmpeg + deno to bundle inside the exe -----------------
if not exist build\bin mkdir build\bin
if not exist build\bin\ffmpeg.exe (
  echo [3/4] Downloading ffmpeg...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl-shared.zip' -OutFile 'build\ffmpeg.zip'; Expand-Archive -Force 'build\ffmpeg.zip' 'build\ffmpeg'; Copy-Item 'build\ffmpeg\*\bin\*' 'build\bin\' -Force" || goto :fail
)
if not exist build\bin\deno.exe (
  echo       Downloading deno (JavaScript runtime yt-dlp needs for YouTube^)...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest 'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip' -OutFile 'build\deno.zip'; Expand-Archive -Force 'build\deno.zip' 'build\bin'" || goto :fail
)

rem ---- 4. Package -----------------------------------------------------------
echo [4/4] Packaging with PyInstaller (this takes a minute)...
".venv\Scripts\python.exe" -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name Glide --icon glide.ico ^
  --add-data "ui.html;." --add-data "build\bin\*;bin" ^
  --collect-all webview --collect-all yt_dlp_ejs ^
  app.py || goto :fail

echo.
echo   Done!  Your app is at:  %cd%\dist\Glide.exe
echo.
if not defined CI explorer /select,"%cd%\dist\Glide.exe"
goto :end

:fail
echo.
echo   Build failed - see the messages above.
if defined CI exit /b 1

:end
if not defined CI pause
