#!/usr/bin/env bash
set -euo pipefail

PROFILE="${1:-preview}"
FRAME_STEP="${2:-2}"

echo "=== Step 1: Rendering Sample Keyframes & Verifying Scene Quality (Profile: $PROFILE) ==="
blender -b -noaudio --python main_scene.py -- --profile "$PROFILE" --mode samples

echo "=== Step 2: Running Visual & Pixel Verification on Sample Keyframes ==="
python3 verify_output.py

echo "=== Step 3: Rendering Full Sequence (Resumable, Step=$FRAME_STEP) ==="
blender -b -noaudio --python main_scene.py -- --profile "$PROFILE" --mode samples_and_video --frame-step "$FRAME_STEP"

echo "=== Step 4: Assembling Final MP4 & Generating Verification Report ==="
python3 verify_output.py

echo "=== DONE! Final Video: output/db_cooper_sequence.mp4 ==="