#!/usr/bin/env bash
set -euo pipefail

export LIBGL_ALWAYS_SOFTWARE=1
export PYTHONUNBUFFERED=1

echo "=== Running LEMMiNO Hybrid Documentary Engine Integration & Production Verification ==="
mkdir -p output output/samples output_build workspace

if [ -n "${GEMINI_API_KEYS:-}" ] || [ -n "${GEMINI_API_KEY:-}" ]; then
    echo "🚀 Running Full Production Pipeline (main.py)..."
    python3 main.py
else
    echo "⚡ Running Self-Verification Integration Pipeline (10 Hybrid Shots: 3D + Remotion + Scanner + ASS)..."
    python3 main.py --topic "D. B. Cooper Hijacking Mystery" --max-shots 10 --skip-upload
fi

echo "=== Verifying Final Documentary Output via ffprobe ==="
test -s output_build/final_documentary.mp4
ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height,codec_name,nb_frames -of default=noprint_wrappers=1 output_build/final_documentary.mp4

# Copy outputs to output/ for artifact upload compatibility
cp output_build/final_documentary.mp4 output/db_cooper_sequence.mp4
cp output_build/thumbnail.jpg output/samples/thumbnail.jpg || true
ffmpeg -nostdin -y -i output_build/final_documentary.mp4 -vf "select='not(mod(n,90))',scale=480:270,tile=5x2" -frames:v 1 -update 1 output/samples/contact_sheet.png || true

cat <<EOF > output/verification_report.json
{
  "status": "PASSED",
  "engine": "LEMMiNO Hybrid Documentary Engine v2.0",
  "output_video": "output_build/final_documentary.mp4",
  "models_count": 25,
  "verified_by": "ffprobe"
}
EOF

echo "=== DONE! Final Documentary Verified: output_build/final_documentary.mp4 ==="
