# yt-dlp GUI

A simple graphical interface for [yt-dlp](https://github.com/yt-dlp/yt-dlp) built with Python, tkinter, and the [Sun Valley ttk theme](https://github.com/rdbende/Sun-Valley-ttk-theme). Works on Windows, Linux, and macOS, with first-class Windows support.

![icon](assets/icon.png)

## Features

- Paste any supported URL and download
- Choose quality: Best, Best video + audio, 1080p, 720p, 480p, 360p, Audio only
- Choose output format: MP4, MKV, MP3, WAV, FLAC, Opus
- Select the download folder (uses the real Windows *Downloads* folder by default)
- Open the download folder with one click
- Add extra yt-dlp options (cookies, playlists, metadata, subtitles, ...)
- Download history saved between sessions
- Cancel in-progress downloads (terminates the whole process tree on Windows)
- Real-time log and progress bar
- Dark theme via [Sun Valley](https://github.com/rdbende/Sun-Valley-ttk-theme)
- No console window flashes when running as a built `.exe`

## Windows: run from source

### 1. Install Python

Install [Python 3.8+](https://www.python.org/downloads/windows/) from python.org and enable **Add python.exe to PATH** during setup. tkinter is included with the python.org installer.

### 2. Install dependencies

```powershell
py -m pip install -r requirements.txt
```

### 3. Install ffmpeg (recommended)

ffmpeg is needed to merge separate video/audio streams (1080p, "Best video + audio", etc.) and to convert audio to MP3/WAV/FLAC/Opus.

```powershell
winget install Gyan.FFmpeg
```

Alternatively use `choco install ffmpeg`, download it from [gyan.dev](https://www.gyan.dev/ffmpeg/builds/), or place `ffmpeg.exe` in a `bin` folder next to `main.py` / `ytdlp-gui.exe`.

### 4. Run

```powershell
py main.py
```

You can also pass a URL directly:

```powershell
py main.py "https://www.youtube.com/watch?v=..."
```

## Build a Windows executable

Double-click `build_windows.bat` (or run the PowerShell script directly):

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

The build script:

1. Creates an isolated `.venv-build` environment
2. Installs the dependencies and PyInstaller
3. Downloads the latest `yt-dlp.exe`
4. Builds a windowed, single-file `dist\ytdlp-gui.exe` with the icon and theme bundled
5. Creates `dist\ytdlp-gui-windows-x64.zip` ready to share

To include ffmpeg in the package:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_windows.ps1 -WithFfmpeg
```

ffmpeg is placed in `dist\bin\` next to the executable. Other options:

| Switch | Effect |
| --- | --- |
| `-WithFfmpeg` | Download ffmpeg/ffprobe into `dist\bin\` |
| `-UpdateFfmpeg` | Re-download ffmpeg even if it already exists |
| `-NoZip` | Do not create the ZIP package |

Notes:

- `yt-dlp.exe` is embedded in the executable. To use a newer yt-dlp later, put `yt-dlp.exe` in a `bin` folder next to `ytdlp-gui.exe`; that copy takes priority.
- Windows SmartScreen may warn about an unsigned executable. Choose **More info → Run anyway**, or build it yourself.
- Antivirus software sometimes flags PyInstaller executables. Building locally avoids most of these false positives.

## How yt-dlp and ffmpeg are found

The app checks, in order:

1. `bin\yt-dlp.exe` / `bin\ffmpeg.exe` next to the app (or project folder)
2. `yt-dlp.exe` / `ffmpeg.exe` next to the app
3. The pip-installed `yt_dlp` module (when running from source)
4. `PATH`

This means a portable copy can ship its own binaries in `bin\`, and pip installs work out of the box.

## Usage tips

Extra options are passed directly to yt-dlp. Examples:

```text
--cookies-from-browser chrome
--yes-playlist --embed-thumbnail --embed-metadata
--download-sections "*00:01:00-00:05:00"
```

Quoted values with Windows paths are supported, for example:

```text
--cookies "C:\Users\Me\cookies.txt"
```

When downloading a playlist, progress reflects the current item.

## Files and settings

| Platform | History location |
| --- | --- |
| Windows | `%APPDATA%\ytdlp-gui\history.json` |
| Linux/macOS | `~/.config/ytdlp-gui/history.json` |

The old `~/.ytdlp_gui_history.json` file is imported automatically on first run.

## Linux AppImage

The original AppImage workflow is still available:

```bash
git clone https://github.com/meowl/ytdlp-gui.git
cd ytdlp-gui
bash build_appimage.sh
```

This builds a standalone executable with PyInstaller and packages it with `appimagetool`, then installs it to `~/.local/bin/ytdlp-gui` with a desktop entry.

## Manual build

Windows:

```powershell
# Download yt-dlp.exe into bin\ first:
# https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe
py -m pip install pyinstaller sv-ttk yt-dlp
py -m PyInstaller --onefile --windowed --name ytdlp-gui --icon assets\icon.ico `
  --add-data "assets;assets" --add-binary "bin\yt-dlp.exe;bin" `
  --collect-all sv_ttk main.py
```

Linux/macOS:

```bash
# Place a Linux/macOS yt-dlp binary in bin/yt-dlp first.
python3 -m pip install pyinstaller sv-ttk yt-dlp
python3 -m PyInstaller --onefile --windowed --name ytdlp-gui \
  --add-data "assets:assets" --add-binary "bin/yt-dlp:bin" \
  --collect-all sv_ttk main.py
```

Frozen builds run an external `yt-dlp` binary (bundled in `bin` above), so the
Python `yt_dlp` package is not required at runtime.

## Troubleshooting

- **"yt-dlp was not found"** – install it with `py -m pip install -U yt-dlp`, or place `yt-dlp.exe` in `bin\` next to the app.
- **Downloads fail at "Merging formats"** – install ffmpeg (see above).
- **Audio conversion fails** – ffmpeg is required for MP3/WAV/FLAC/Opus output.
- **The log shows `ERROR: ...`** – the full yt-dlp output is shown in the log pane; copy it when reporting an issue.
