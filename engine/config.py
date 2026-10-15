# -*- coding: utf-8 -*-
"""
engine/config.py
System configuration, directory paths, and environment variable bindings.
"""

import os
import re
import random
import shutil
import threading
from pathlib import Path
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent.parent

TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
TARGET_AR = 24000

AGY_MODEL = "gemini-3.8-flash"
TTS_MODEL = "gemini-3.8-flash-tts"
TTS_VOICE = "Charon"
GROQ_MODEL = "whisper-large-v3"

MAX_AGY_CALLS_PER_EPISODE = 4

WIKIMEDIA_USER_AGENT = (
    "LEMMiNOHybridDocumentaryEngine/2.0 "
    "(https://github.com/Ya7ossaaain/ai-video-generator; contact@documentary-engine.org) "
    "python-requests/2.32"
)


class EngineConfig:
    def __init__(self):
        self.topic = os.environ.get("VIDEO_TOPIC", "D. B. Cooper Hijacking Mystery")
        self.topic_clean = re.sub(r"[^a-zA-Z0-9_\u0600-\u06FF\-]+", "_", self.topic).strip("_") or "Documentary"
        self.run_id = f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(1000, 9999)}"

        raw_keys = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
        self.gemini_keys = list(dict.fromkeys([k.strip() for k in re.split(r"[,;\n]+", raw_keys) if k.strip()]))
        self.gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.youtube_api_key = os.environ.get("YOUTUBE_API_KEY", "")
        self.pexels_api_key = os.environ.get("PEXELS_API_KEY", "")
        self.pixabay_api_key = os.environ.get("PIXABAY_API_KEY", "")
        self.giphy_api_key = os.environ.get("GIPHY_API_KEY", "")
        self.europeana_api_key = os.environ.get("EUROPEANA_API_KEY", "")
        self.freesound_api_key = os.environ.get("FREESOUND_API_KEY", "")
        self.openverse_client_id = os.environ.get("OPENVERSE_CLIENT_ID", "")
        self.openverse_client_secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "")

        self.google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        self.google_refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
        self.drive_folder_id = os.environ.get("DRIVE_FOLDER_ID", "1wn4z3A-t8Dnnq1kkiJopvUsCBQpkWxQW")

        self.repo_root = REPO_ROOT
        self.assets_dir = self.repo_root / "assets"
        self.models_dir = self.assets_dir / "models"
        self.models_catalog_path = self.models_dir / "models_catalog.json"
        self.blender_scripts_dir = self.repo_root / "blender_scripts"
        self.remotion_dir = self.repo_root / "remotion-documentary"

        self.intro_path = self.assets_dir / "intro.mp4"
        self.logo_path = self.assets_dir / "logo.png"

        self.workspace_dir = self.repo_root / "workspace"
        self.evidence_vault_dir = self.workspace_dir / "evidence_vault"
        self.evidence_manifest_path = self.workspace_dir / "evidence_manifest.json"
        self.script_manifest_path = self.workspace_dir / "script_manifest.json"
        self.audio_dir = self.workspace_dir / "audio_chapters"
        self.master_audio_path = self.workspace_dir / "master_audio.wav"
        self.shots_timeline_path = self.workspace_dir / "shots_timeline.json"
        self.visual_plan_path = self.workspace_dir / "visual_plan.json"
        self.rendered_shots_dir = self.workspace_dir / "rendered_shots"
        self.subtitles_ass_path = self.workspace_dir / "subtitles.ass"

        self.output_dir = self.repo_root / "output_build"
        self.final_video_path = self.output_dir / "final_documentary.mp4"
        self.thumbnail_path = self.output_dir / "thumbnail.jpg"

        self.lock = threading.Lock()

    def ensure_directories(self, clean_workspace: bool = False):
        if clean_workspace and self.workspace_dir.exists():
            shutil.rmtree(self.workspace_dir, ignore_errors=True)
        for d in [
            self.assets_dir,
            self.models_dir,
            self.workspace_dir,
            self.evidence_vault_dir,
            self.audio_dir,
            self.rendered_shots_dir,
            self.output_dir,
        ]:
            d.mkdir(parents=True, exist_ok=True)

        root_intro = self.repo_root / "intro.mp4"
        if root_intro.exists() and not self.intro_path.exists():
            try:
                shutil.copy2(root_intro, self.intro_path)
            except Exception:
                pass

        root_logo = self.repo_root / "logo.png"
        if root_logo.exists() and not self.logo_path.exists():
            try:
                shutil.copy2(root_logo, self.logo_path)
            except Exception:
                pass


CONFIG = EngineConfig()
