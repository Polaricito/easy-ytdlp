# yt-dlp GUI

A simple graphical user interface for [yt-dlp](https://github.com/yt-dlp/yt-dlp) built with Python, tkinter, and the [Sun Valley ttk theme](https://github.com/rdbende/Sun-Valley-ttk-theme).

## Features

- Paste any supported URL and download
- Choose quality: Best, 1080p, 720p, 480p, 360p, Audio only
- Choose output format: MP4, MKV, MP3, WAV, FLAC, Opus
- Select download directory
- Add extra yt-dlp options
- Download history saved between sessions
- Cancel in-progress downloads
- Real-time log output
- Beautiful Dark theme via [Sun Valley](https://github.com/rdbende/Sun-Valley-ttk-theme)

## Requirements

- Python 3.8+
- tkinter (usually included with Python)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [sv-ttk](https://pypi.org/project/sv-ttk/) (Sun Valley theme)

```bash
pip install sv-ttk yt-dlp
```

## Build AppImage (one-click)

```bash
curl -L https://raw.githubusercontent.com/meowl/ytdlp-gui/main/build_appimage.sh | bash
```

Or clone and run locally:

```bash
git clone https://github.com/meowl/ytdlp-gui.git
cd ytdlp-gui
bash build_appimage.sh
```

This will:
1. Download `pyinstaller` and build a standalone executable
2. Download `appimagetool` and package the app into an AppImage
3. Install to `~/.local/bin/ytdlp-gui` with a desktop entry for your app drawer

## Usage

```bash
python3 main.py
```

Or run the AppImage directly:

```bash
./ytdlp-gui-x86_64.AppImage
```

Or install it permanently:

```bash
chmod +x ytdlp-gui-x86_64.AppImage
sudo cp ytdlp-gui-x86_64.AppImage /usr/local/bin/ytdlp-gui
sudo cp ytdlp-gui.desktop /usr/share/applications/
```

Or without sudo, install to your user (includes custom icon):

```bash
mkdir -p ~/.local/bin ~/.local/share/applications ~/.local/share/icons/hicolor/256x256/apps
cp ytdlp-gui-x86_64.AppImage ~/.local/bin/ytdlp-gui
cp ytdlp-gui.desktop ~/.local/share/applications/
cp /home/meowl/Downloads/yt-dlp.png ~/.local/share/icons/hicolor/256x256/apps/ytdlp-gui.png
update-desktop-database ~/.local/share/applications/
```

The desktop entry uses the full path to `~/.local/bin/ytdlp-gui` so it works from the app drawer regardless of PATH settings.

## History

Download history is saved to `~/.ytdlp_gui_history.json`.

## Building from source

If you prefer to build manually:

```bash
pip install pyinstaller sv-ttk yt-dlp
pyinstaller --onefile --windowed --name ytdlp-gui --hidden-import sv_ttk --hidden-import yt_dlp main.py
```

Then download `appimagetool` and create the AppImage from the resulting `dist/ytdlp-gui` binary.


Download history is saved to `~/.ytdlp_gui_history.json`.

