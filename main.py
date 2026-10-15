#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py
Main Orchestrator for the LEMMiNO Hybrid Documentary Engine.
"""

import os
import sys
import argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from engine.config import CONFIG
from engine.telemetry import log, probe_media_info
from engine.forensic_harvester import ForensicHarvester
from engine.script_writer import EvidenceScriptWriter
from engine.audio_studio import AudioStudio
from engine.visual_director import VisualDirector
from engine.blender_runner import BlenderRunner
from engine.compositor import HybridCompositor
from engine.cloud_uploader import CloudUploader


def parse_cli():
    parser = argparse.ArgumentParser(description="LEMMiNO Hybrid Documentary Engine Orchestrator")
    parser.add_argument("--topic", type=str, default="", help="Override VIDEO_TOPIC environment variable")
    parser.add_argument(
        "--max-shots",
        type=int,
        default=0,
        help="Optional cap on shots for fast CI/integration verification (0 = full episode)",
    )
    parser.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip Google Drive & YouTube upload during local verification runs",
    )
    return parser.parse_args()


def run_pipeline(args) -> Path:
    if args.topic:
        CONFIG.topic = args.topic

    log("=" * 72)
    log(f"🚀 انطلاق محرك الوثائقيات الهجين (LEMMiNO Hybrid Engine) | الموضوع: {CONFIG.topic}")
    log("=" * 72)

    CONFIG.ensure_directories(clean_workspace=True)

    # Stage 0: Normalize 3D Models & Build Catalog
    blender_runner = BlenderRunner()
    blender_runner.normalize_all_models()

    # Stage 1: Forensic Evidence Harvesting (Zero AI Quota)
    harvester = ForensicHarvester()
    evidence_manifest = harvester.harvest_all()

    # Stage 2: Evidence-Based Script Engineering (AGY Call #1)
    writer = EvidenceScriptWriter()
    script_data = writer.generate_script(evidence_manifest)

    # Stage 3: 10-Key TTS & Groq Whisper Word-Level Zero-Drift Sync
    audio_studio = AudioStudio()
    master_audio_path, shots = audio_studio.produce_and_sync(script_data)

    if args.max_shots and args.max_shots > 0:
        log(f"⚡ وضع الفحص السريع: تحديد عدد المشاهد بـ {args.max_shots} مشهد.")
        shots = shots[:args.max_shots]

    # Stage 4: Hybrid Visual Direction (AGY Calls #2 & #3)
    director = VisualDirector()
    directed_shots = director.direct_scenes(shots, evidence_manifest, script_data)

    # Stage 5: Hybrid Rendering (Blender 3D + Remotion + FFmpeg + ASS Subtitles)
    compositor = HybridCompositor()
    final_video = compositor.assemble_master_documentary(
        directed_shots=directed_shots,
        evidence_manifest=evidence_manifest,
        master_audio_path=master_audio_path,
    )

    info = probe_media_info(final_video)
    log(f"🔍 فحص ffprobe النهائي: {info}")
    if not info.get("valid"):
        raise RuntimeError(f"Final video failed ffprobe verification: {final_video}")

    # Stage 6: Cloud Upload (Google Drive & YouTube)
    if not args.skip_upload:
        uploader = CloudUploader()
        uploader.upload(
            video_path=final_video,
            thumbnail_path=CONFIG.thumbnail_path,
            script_data=script_data,
            shots=directed_shots,
        )

    log("🏁 اكتملت جميع مراحل محرك الوثائقيات الهجين بنجاح 100%.")
    return final_video


if __name__ == "__main__":
    cli_args = parse_cli()
    run_pipeline(cli_args)
