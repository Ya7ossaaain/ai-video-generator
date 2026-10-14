#!/usr/bin/env bash
set -euo pipefail

echo "=== [1/3] Checking system resources (Disk & RAM) ==="
df -h .
free -h || true

echo "=== [2/3] Installing FFmpeg, Pillow, and Xvfb/headless libraries ==="
sudo apt-get update -y
sudo apt-get install -y ffmpeg python3-pil wget xz-utils libxi6 libxxf86vm1 libxfixes3 libxrender1 libgl1 libkbcommon0 libsm6 libice6

echo "=== [3/3] Ensuring Blender (4.0.2 LTS Portable or System Blender) ==="
BLENDER_DIR="$HOME/blender-4.0.2"
if ! command -v blender &> /dev/null; then
    if [ ! -f "$BLENDER_DIR/blender" ]; then
        echo "Downloading official Blender 4.0.2 LTS Linux x64..."
        wget -q "https://download.blender.org/release/Blender4.0/blender-4.0.2-linux-x64.tar.xz" -O /tmp/blender.tar.xz
        mkdir -p "$BLENDER_DIR"
        tar -xf /tmp/blender.tar.xz -C "$BLENDER_DIR" --strip-components=1
        rm -f /tmp/blender.tar.xz
    fi
    sudo ln -sf "$BLENDER_DIR/blender" /usr/local/bin/blender
fi

blender --version
ffmpeg -version | head -n 1
echo "=== Environment Setup Complete ==="