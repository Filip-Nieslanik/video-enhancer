#!/usr/bin/env bash
# Build the macOS .app and wrap it in a .dmg.
#
#   bash packaging/build_macos.sh
#
# Requirements: python3, pip, and create-dmg (brew install create-dmg).
# Run from the repository root.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Installing build dependencies"
python3 -m pip install --upgrade pyinstaller imageio-ffmpeg tkinterdnd2

echo "==> Fetching Real-ESRGAN (macOS build)"
# The Windows download script grabs the win binary; on macOS pull the
# matching macos release instead.
RESRGAN_DIR="realesrgan-ncnn"
if [ ! -x "$RESRGAN_DIR/realesrgan-ncnn-vulkan" ]; then
  mkdir -p "$RESRGAN_DIR"
  URL="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip"
  curl -L "$URL" -o /tmp/resrgan-macos.zip
  unzip -o /tmp/resrgan-macos.zip -d "$RESRGAN_DIR"
  chmod +x "$RESRGAN_DIR/realesrgan-ncnn-vulkan"
fi

echo "==> Running PyInstaller"
pyinstaller \
  --name "Video Enhancer" \
  --windowed \
  --noconfirm \
  --collect-all tkinterdnd2 \
  --collect-data imageio_ffmpeg \
  --add-data "realesrgan-ncnn:realesrgan-ncnn" \
  --osx-bundle-identifier "com.filipnieslanik.videoenhancer" \
  VideoEnhancer.pyw

echo "==> Building .dmg"
mkdir -p installer-output
create-dmg \
  --volname "Video Enhancer" \
  --window-size 540 360 \
  --icon-size 96 \
  --app-drop-link 380 170 \
  --icon "Video Enhancer.app" 150 170 \
  "installer-output/VideoEnhancer.dmg" \
  "dist/Video Enhancer.app" || \
  hdiutil create -volname "Video Enhancer" -srcfolder "dist/Video Enhancer.app" \
    -ov -format UDZO "installer-output/VideoEnhancer.dmg"

echo "==> Done: installer-output/VideoEnhancer.dmg"
echo "    Unsigned builds are blocked by Gatekeeper. See BUILD.md for signing"
echo "    and notarization, or right-click -> Open on first launch."
