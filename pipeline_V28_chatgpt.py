#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pipeline_V28_chatgpt.py
Bridge entrypoint for GitHub Actions workflow (`v24-2-7scene-test.yml`).
Ensures Blender, ImageMagick, and 25 normalized 3D GLB models are ready on the runner,
then delegates execution to the modular LEMMiNO Hybrid Documentary Engine (`main.py`).
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def ensure_ci_system_tools():
    if shutil.which("blender") is None or shutil.which("convert") is None:
        print("🔧 Installing Blender, Xvfb, and ImageMagick on CI runner...")
        subprocess.run(["sudo", "apt-get", "update", "-y"], check=False)
        subprocess.run([
            "sudo", "apt-get", "install", "-y",
            "blender", "xvfb", "libgl1-mesa-dri", "libglu1-mesa",
            "imagemagick", "python3-cairo", "python3-pil", "python3-numpy"
        ], check=False)


if __name__ == "__main__":
    ensure_ci_system_tools()
    from build_models_library import build_all_25_models
    build_all_25_models(REPO_ROOT / "assets" / "models")
    from main import parse_cli, run_pipeline
    run_pipeline(parse_cli())
