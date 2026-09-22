#!/usr/bin/env bash
set -euo pipefail

# ── Configuration ──────────────────────────────────────────
APP_NAME="ytdlp-gui"
APP_DIR="${APP_NAME}.AppDir"
DESKTOP_FILE="${APP_NAME}.desktop"
MAIN_SCRIPT="main.py"
APP_ICON_SRC="/home/meowl/Downloads/yt-dlp.png"
HOME_DIR="$HOME"

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

# ── Clean previous build ──────────────────────────────────
echo "🧹 Cleaning previous build..."
rm -rf "${APP_DIR}" "${APP_NAME}-*.AppImage" "${DESKTOP_FILE}" dist build ytdlp-gui.spec 2>/dev/null || true

# ── Install pyinstaller if needed ─────────────────────────
echo "🔧 Checking pyinstaller..."
export PATH="$HOME/.local/bin:$PATH"
pyinstaller --version 2>&1

# ── Build standalone executable with PyInstaller ──────────
echo "🔨 Building standalone executable..."
pyinstaller \
  --onefile \
  --windowed \
  --name "${APP_NAME}" \
  --distpath dist \
  --workpath build \
  --specpath . \
  --hidden-import "sv_ttk" \
  --hidden-import "yt_dlp" \
  --paths "$HOME/.local/lib/python3.14/site-packages" \
  "${MAIN_SCRIPT}" 2>&1

# ── Create AppDir structure ───────────────────────────────
echo "📦 Setting up AppDir..."
mkdir -p "${APP_DIR}/usr/bin"
mkdir -p "${APP_DIR}/usr/share/applications"
mkdir -p "${APP_DIR}/usr/share/icons/hicolor/256x256/apps"

# Copy the standalone executable
cp "dist/${APP_NAME}" "${APP_DIR}/usr/bin/${APP_NAME}"
chmod +x "${APP_DIR}/usr/bin/${APP_NAME}"

# AppRun — pyinstaller --onefile is self-contained
cat > "${APP_DIR}/AppRun" <<EOF
#!/bin/sh
HERE="\$(dirname "\$(readlink -f "\$0")")"
exec "\${HERE}/usr/bin/${APP_NAME}" "\$@"
EOF
chmod +x "${APP_DIR}/AppRun"

# ── Desktop file (with absolute path so app drawer works) ──
echo "📝 Creating desktop entry..."
cat > "${DESKTOP_FILE}" <<EOF
[Desktop Entry]
Name=yt-dlp GUI
Comment=Download videos and audio with yt-dlp
Exec=${HOME_DIR}/.local/bin/ytdlp-gui
Icon=${APP_NAME}
Type=Application
Categories=Network;AudioVideo;
Terminal=false
Keywords=youtube;dl;download;yt-dlp;
EOF
cp "${DESKTOP_FILE}" "${APP_DIR}/usr/share/applications/"
cp "${DESKTOP_FILE}" "${APP_DIR}/"

# ── Copy icon ──────────────────────────────────────────────
echo "🎨 Copying icon from ${APP_ICON_SRC}..."
mkdir -p "${APP_DIR}/usr/share/icons/hicolor/256x256/apps"
cp "${APP_ICON_SRC}" "${APP_DIR}/usr/share/icons/hicolor/256x256/apps/${APP_NAME}.png"
cp "${APP_ICON_SRC}" "${APP_DIR}/${APP_NAME}.png"

# ── Build the AppImage ────────────────────────────────────
echo "📦 Building AppImage..."
/tmp/appimagetool \
  "${APP_DIR}" \
  "${APP_NAME}-x86_64.AppImage" 2>&1

# ── Find the AppImage ─────────────────────────────────────
APPIMAGE=$(ls -t "${APP_NAME}"-*.AppImage 2>/dev/null | head -1)

if [ -z "${APPIMAGE}" ]; then
    echo "❌ AppImage not found. Build may have failed."
    exit 1
fi

echo "✅ AppImage created: ${APPIMAGE}"

# ── Install to system ─────────────────────────────────────
echo "📥 Installing to system..."
mkdir -p ~/.local/bin ~/.local/share/applications
cp "${APPIMAGE}" ~/.local/bin/ytdlp-gui
chmod +x ~/.local/bin/ytdlp-gui
cp "${DESKTOP_FILE}" ~/.local/share/applications/ytdlp-gui.desktop
update-desktop-database ~/.local/share/applications/ 2>/dev/null || true

echo "✅ Installation complete!"
echo ""
echo "🎉 yt-dlp GUI is now available from the app drawer!"
echo "   Run it with: ytdlp-gui"
echo "   Or find it in your application menu under Network/Downloads."
echo ""
echo "   AppImage: $(pwd)/${APPIMAGE}"
echo "   To use directly, ensure ~/.local/bin is in your PATH."
