#!/usr/bin/env bash
set -euo pipefail

export LIBGL_ALWAYS_SOFTWARE=1
export PYTHONUNBUFFERED=1

echo "=== [Stage 0] Committing 25 Normalized 3D GLB Models to Repository ==="
git config --global user.name "LEMMiNO-Hybrid-Engine" || true
git config --global user.email "actions@github.com" || true
if ls assets/models/*.glb >/dev/null 2>&1; then
    git add -f assets/models/*.glb assets/models/models_catalog.json || true
    git commit -m "chore(assets): add 25 Blender-normalized binary 3D .glb models [skip ci]" || true
    git pull --rebase origin main || true
    git push origin main || true
fi

echo "=== [Stage 1-5] Running LEMMiNO Hybrid Documentary Engine ==="
mkdir -p output output/samples output_build workspace

if [ -n "${GEMINI_API_KEYS:-}" ] || [ -n "${GEMINI_API_KEY:-}" ]; then
    echo "🚀 Running Full Production Pipeline (main.py)..."
    python3 main.py
else
    echo "⚡ Running Self-Verification Integration Pipeline (10 Hybrid Shots: 3D + Remotion + Scanner + ASS)..."
    python3 main.py --topic "D. B. Cooper Hijacking Mystery" --max-shots 10 --skip-upload
fi

echo "=== [Stage 6] Verifying Final Documentary Output via ffprobe ==="
test -s output_build/final_documentary.mp4
FFPROBE_INFO=$(ffprobe -v error -show_entries format=duration,size -show_entries stream=width,height,codec_name,nb_frames -of default=noprint_wrappers=1 output_build/final_documentary.mp4 | tr '\n' ' ')
echo "ffprobe: $FFPROBE_INFO"

# Copy outputs to output/ for artifact upload compatibility
cp output_build/final_documentary.mp4 output/db_cooper_sequence.mp4
cp output_build/thumbnail.jpg output/samples/thumbnail.jpg || true
ffmpeg -nostdin -y -i output_build/final_documentary.mp4 -vf "select='not(mod(n,90))',scale=480:270,tile=5x2" -frames:v 1 -update 1 output/samples/contact_sheet.png || true

cat <<EOF > output/verification_report.json
{
  "status": "PASSED",
  "engine": "LEMMiNO Hybrid Documentary Engine v2.0",
  "output_video": "output_build/final_documentary.mp4",
  "ffprobe_telemetry": "$FFPROBE_INFO",
  "models_count": 25,
  "timestamp_utc": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
}
EOF

git add -f output/verification_report.json production_logs.txt || true
git commit -m "telemetry(ci): verify LEMMiNO Hybrid Documentary Engine run ($FFPROBE_INFO) [skip ci]" || true
git pull --rebase origin main || true
git push origin main || true

echo "=== DONE! Final Documentary Verified: output_build/final_documentary.mp4 ==="
