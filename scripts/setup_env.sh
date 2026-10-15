#!/usr/bin/env bash
set -euo pipefail

echo "=== [1/5] Freeing Runner Disk Space (~30GB) ==="
sudo rm -rf /usr/share/dotnet /usr/local/lib/android /opt/ghc /opt/hostedtoolcache/CodeQL || true
sudo apt-get clean || true
df -h || true

echo "=== [2/5] Installing Blender, FFmpeg, ImageMagick, Xvfb & Arabic Fonts ==="
sudo apt-get update -y
sudo apt-get install -y \
    ffmpeg \
    blender \
    imagemagick \
    xvfb \
    fonts-noto-core \
    fonts-noto-extra \
    fontconfig \
    python3-pip \
    python3-pil \
    python3-cairo \
    python3-numpy \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    libxi6 \
    libxxf86vm1 \
    libxfixes3 \
    libxrender1 \
    libgl1 \
    libgl1-mesa-dri \
    libglu1-mesa \
    libegl1 \
    libxkbcommon0 \
    libsm6 \
    libice6
fc-cache -f -v >/dev/null 2>&1 || true

echo "=== [3/5] Installing Python Dependencies ==="
pip3 install --upgrade pip || true
pip3 install -r requirements.txt || true

echo "=== [4/5] Building & Normalizing 25 3D GLB Assets in assets/models/ ==="
mkdir -p assets/models
if [ -f "intro.mp4" ] && [ ! -f "assets/intro.mp4" ]; then
    cp intro.mp4 assets/intro.mp4
fi
if [ -f "logo.png" ] && [ ! -f "assets/logo.png" ]; then
    cp logo.png assets/logo.png
fi
python3 build_models_library.py
export LIBGL_ALWAYS_SOFTWARE=1
xvfb-run -a blender -b -P blender_scripts/normalize_assets.py || python3 blender_scripts/normalize_assets.py

echo "=== [5/5] Installing Remotion & Verifying TypeScript ==="
if command -v npm >/dev/null 2>&1 && [ -d "remotion-documentary" ]; then
    cd remotion-documentary
    npm install --no-audit --no-fund || true
    npx tsc --noEmit || true
    cd ..
fi

blender --version | head -n 2 || true
ffmpeg -version | head -n 1 || true
convert --version | head -n 1 || true
echo "=== Environment Setup Complete ==="
