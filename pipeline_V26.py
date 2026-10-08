#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
V56 - BROADCAST CINEMATIC MASTER EDITION
(RESTORED HIGH-PRECISION SEARCH & ZERO-CRASH STABLE LIFECYCLE)

Key Enhancements & Fixes:
- CRITICAL FIX: Elimination of the double-append and premature file deletion bug in shot evaluation.
- CRITICAL FIX: Safe file preservation with fallback safeguard in AssemblyEngine to prevent any render crashes.
- RESTORED PRECISION SEARCH: Strict physical-noun search engineering from V26 (eliminating useless abstract keywords).
- FULL VERBATIM TELEMETRY: Complete script text printing for all 8 chapters + live Reviewer telemetry.
- STABLE BROADCAST FILTERS: Ken Burns with background blur, split graph safety, and force_divisible_by=2.
- INTEGRATED INTRO & TRANSITIONS: 8-second channel intro + episodic chapter title cards with sub-bass hits.
- BRANDING: Dynamic logo + hashtag overlay, automatically hidden during channel intro.
- DIRECT DRIVE DESTINATION: Targeted upload to the 02_Generated_Videos folder.
"""

import os
import sys
import json
import time
import re
import logging
import subprocess
import base64
import asyncio
import urllib.parse
import shutil
import threading
import random
import hashlib
import gc

from pathlib import Path
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

import requests
from google import genai
from google.genai import types

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ENGINE_VERSION = "V56-BROADCAST-CINEMATIC-MASTER"

TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
TARGET_AR = 48000

TTS_MODEL = "gemini-3.8-flash-tts"
TTS_VOICE = "Charon"

AGY_SCRIPT_MODEL = "gemini-3.1-pro"
AGY_REVIEWER_MODEL = "gemini-3.6-flash"
GROQ_MODEL = "whisper-large-v3"

MAX_MEDIA_SIZE_MB = 120
MAX_ATTEMPTS_PER_SHOT = 12

REVIEWER_SEMAPHORE = asyncio.Semaphore(7)

PREFILTER_MIN_SIZE_BYTES = 5 * 1024
PREFILTER_MIN_VIDEO_DURATION = 0.5

TARGET_TOTAL_DURATION_MINUTES = 25
TARGET_NARRATION_WORDS = 3500
SCENE_DURATION_MIN = 2.2
SCENE_DURATION_MAX = 5.0
SCENE_DURATION_MIN_HOOK = 1.3
SCENE_DURATION_MAX_HOOK = 2.0
RENDER_BATCH_SIZE = 40

EFFORT_REVIEWER = "low"
EFFORT_PRO_GENERATION = "high"
EFFORT_IMAGE_GEN = "medium"

API_HEADERS = {
    "User-Agent": "InvestigativeDocumentaryBot/2.0 (https://github.com/Ya7ossaaain; contact@example.com)",
    "Accept": "application/json, text/plain, */*"
}

MEDIA_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

SOURCE_AFFINITY = {
    "ARCHIVE": {
        "person_mugshot": ["WIKIPEDIA", "FBI_ARCHIVE", "OPENVERSE", "LOC", "EUROPEANA"],
        "document_file": ["FBI_ARCHIVE", "LOC", "WIKIPEDIA", "EUROPEANA", "OPENVERSE"],
        "location_photo": ["WIKIPEDIA", "OPENVERSE", "LOC", "EUROPEANA", "FBI_ARCHIVE"],
        "historical_event": ["FBI_ARCHIVE", "WIKIPEDIA", "LOC", "EUROPEANA", "OPENVERSE"],
        "newspaper_article": ["LOC", "EUROPEANA", "FBI_ARCHIVE", "WIKIPEDIA", "OPENVERSE"],
        "default": ["WIKIPEDIA", "FBI_ARCHIVE", "LOC", "EUROPEANA", "OPENVERSE"],
    },
    "CINEMATIC": {
        "nature_water": ["PEXELS", "PIXABAY", "OPENVERSE"],
        "dark_moody": ["PEXELS", "PIXABAY", "OPENVERSE"],
        "people_action": ["PEXELS", "PIXABAY", "OPENVERSE"],
        "objects_closeup": ["PIXABAY", "PEXELS", "OPENVERSE"],
        "urban_night": ["PEXELS", "PIXABAY", "OPENVERSE"],
        "default": ["PEXELS", "PIXABAY", "OPENVERSE"],
    }
}


class ProTelemetryFormatter(logging.Formatter):
    def format(self, record):
        now = datetime.now().strftime("%H:%M:%S")
        icons = {"INFO": "INFO", "WARNING": "WARN", "ERROR": "ERROR", "DEBUG": "DEBUG"}
        return f"{now} | [{icons.get(record.levelname, record.levelname)}] | {record.getMessage()}"

def setup_logger():
    logger = logging.getLogger("DOCUMENTARY_ENGINE")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ProTelemetryFormatter())
    logger.addHandler(handler)
    return logger

LOGGER = setup_logger()

def log(msg, level="info"):
    if level == "warning": LOGGER.warning(msg)
    elif level == "error": LOGGER.error(msg)
    elif level == "debug": LOGGER.debug(msg)
    else: LOGGER.info(msg)
    sys.stdout.flush()


class EngineConfig:
    def __init__(self):
        self.topic = os.environ.get("VIDEO_TOPIC", "لغز القاتل زودياك")
        self.topic_clean = re.sub(r"[^a-zA-Z0-9_\-]+", "_", self.topic).strip("_")
        self.run_id = f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(10000, 99999)}"
        self.base_dir = Path("./output_build")
        self.work_dir = self.base_dir / "workspace"
        self.final_video = self.base_dir / "final_documentary.mp4"
        self.master_audio = self.work_dir / "master_audio.wav"
        self.thumbnail = self.base_dir / "thumbnail.jpg"
        self.description_file = self.base_dir / "description.txt"

        self.intro_path = self._locate_asset(["intro.mp4", "assets/intro.mp4"])
        self.logo_path = self._locate_asset(["logo.png", "assets/logo.png"])
        self.chapter_sfx_path = self._locate_asset(["chapter_hit.wav", "assets/chapter_hit.wav"])
        self.drive_folder_id = os.environ.get("DRIVE_FOLDER_ID", "1wn4z3A-t8Dnnq1kkiJopvUsCBQpkWxQW")

        self.used_media_ids = set()
        self.used_media_lock = threading.Lock()
        raw_keys = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
        self.gemini_keys = list(dict.fromkeys([k.strip() for k in re.split(r"[,;\n]+", raw_keys) if k.strip()]))
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.pexels_key = os.environ.get("PEXELS_API_KEY", "")
        self.pixabay_key = os.environ.get("PIXABAY_API_KEY", "")
        self.europeana_key = os.environ.get("EUROPEANA_API_KEY", "")
        self.freesound_key = os.environ.get("FREESOUND_API_KEY", "")
        self.openverse_client_id = os.environ.get("OPENVERSE_CLIENT_ID", "")
        self.openverse_client_secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "")
        self.openverse_token = None
        self.openverse_token_lock = threading.Lock()
        self.google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        self.google_refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")

    def _locate_asset(self, candidate_paths):
        for p in candidate_paths:
            path_obj = Path(p)
            if path_obj.exists(): return path_obj
        return Path(candidate_paths[0])

CONFIG = EngineConfig()


def prepare_fresh_workspace():
    log("🧹 تنظيف وتجهيز بيئة التشغيل بالكامل...")
    if CONFIG.base_dir.exists():
        shutil.rmtree(CONFIG.base_dir, ignore_errors=True)
    CONFIG.base_dir.mkdir(parents=True, exist_ok=True)
    CONFIG.work_dir.mkdir(parents=True, exist_ok=True)
    CONFIG.used_media_ids.clear()


class GeminiKeyPool:
    def __init__(self):
        self.keys = CONFIG.gemini_keys
        self.lock = threading.Lock()
        self.active = set()
        self.cursor = 0

    def acquire(self, excluded=None):
        excluded = excluded or set()
        while True:
            with self.lock:
                for offset in range(len(self.keys)):
                    idx = (self.cursor + offset) % len(self.keys)
                    if idx in self.active or idx in excluded: continue
                    self.active.add(idx)
                    self.cursor = (idx + 1) % len(self.keys)
                    return idx, self.keys[idx]
            time.sleep(0.1)

    def release(self, index):
        with self.lock: self.active.discard(index)

if not CONFIG.gemini_keys:
    raise RuntimeError("🚨 لم يتم العثور على مفاتيح Gemini.")
GEMINI_POOL = GeminiKeyPool()


def probe_duration(path):
    if not path or not os.path.exists(path): return 0.0
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], stdout=subprocess.PIPE, text=True, timeout=30)
        return float(res.stdout.strip())
    except: return 0.0


def probe_dimensions(path):
    if not path or not os.path.exists(path): return 0, 0
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height",
             "-of", "csv=s=x:p=0", str(path)],
            stdout=subprocess.PIPE, text=True, timeout=30
        )
        parts = res.stdout.strip().split("x")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except: pass
    return 0, 0


def is_valid_media(path, min_duration=0.05):
    path = Path(path)
    return path.exists() and path.stat().st_size >= 1024 and probe_duration(path) >= min_duration

def is_valid_visual(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size < 1024: return False
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(path)], stdout=subprocess.PIPE, text=True, timeout=30)
        return "x" in res.stdout.strip()
    except: return False

def clean_query(text):
    return re.sub(r"\s+", " ", re.sub(r"[^\x00-\x7F]+", " ", text or "")).strip()[:180]

def run_cmd(cmd, timeout=300):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)

def extract_json(text):
    if not text: return None
    text = re.sub(r"```json\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"```\s*$", "", text)
    try: return json.loads(text)
    except: pass
    match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
    if match:
        try: return json.loads(match.group(0))
        except: pass
    return None

def cleanup_shot_unused_files(index, keep_path=None):
    """Safely cleans up candidate downloads for a shot without touching protected items."""
    try:
        keep_resolved = Path(keep_path).resolve() if keep_path else None
        for p in CONFIG.work_dir.glob(f"*shot_{index:03d}*"):
            if keep_resolved and p.resolve() == keep_resolved:
                continue
            if p.name.startswith("selected_") or p.name.startswith("rendered_"):
                continue
            p.unlink(missing_ok=True)
    except Exception:
        pass


# =============================================================================
# BULLETPROOF FFMPEG FILTERS (Ken Burns + Blur Background + Divisible by 2)
# =============================================================================

def build_blur_background_filter_image(target_w=TARGET_W, target_h=TARGET_H, ken_burns=True):
    bg_part = (
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase:force_divisible_by=2,"
        f"crop={target_w}:{target_h},"
        f"gblur=sigma=40,"
        f"eq=brightness=-0.08:saturation=0.4[bg]"
    )
    if ken_burns:
        fg_part = (
            f"[0:v]scale={int(target_w * 1.12)}:{int(target_h * 1.12)}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"zoompan=z='min(zoom+0.0008,1.15)':d=1:s={target_w}x{target_h}:fps={TARGET_FPS}[fg]"
        )
    else:
        fg_part = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:black@0[fg]"
        )

    overlay_part = (
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"eq=contrast=1.06:saturation=0.92,"
        f"vignette,"
        f"noise=alls=3:allf=t,"
        f"fps={TARGET_FPS}"
    )
    return f"{bg_part};{fg_part};{overlay_part}"


def build_blur_background_filter_video(target_w=TARGET_W, target_h=TARGET_H):
    return (
        f"[0:v]split=2[bg_in][fg_in];"
        f"[bg_in]scale={target_w}:{target_h}:force_original_aspect_ratio=increase:force_divisible_by=2,"
        f"crop={target_w}:{target_h},"
        f"gblur=sigma=35,"
        f"eq=brightness=-0.08:saturation=0.4[bg];"
        f"[fg_in]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease:force_divisible_by=2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"eq=contrast=1.06:saturation=0.92,"
        f"vignette,"
        f"noise=alls=3:allf=t,"
        f"fps={TARGET_FPS}"
    )


class SearchFailureDiagnostics:
    NO_RESULTS = "no_results"
    IRRELEVANT_RESULTS = "irrelevant_results"
    REVIEWER_REJECTED = "reviewer_rejected"
    FORMAT_INVALID = "format_invalid"

    def __init__(self):
        self.failures = defaultdict(list)
        self.lock = threading.Lock()

    def record(self, shot_index, query, source, category, score=0.0, reason=""):
        with self.lock:
            self.failures[shot_index].append({
                "query": query, "source": source, "category": category,
                "score": score, "reason": reason, "time": time.time()
            })

    def diagnose(self, shot_index):
        with self.lock:
            records = self.failures.get(shot_index, [])
        if not records:
            return {"recommendations": []}

        failed_sources = set(r["source"] for r in records)
        source_fail_counts = defaultdict(int)
        for r in records:
            source_fail_counts[r["source"]] += 1
        exhausted_sources = [s for s, c in source_fail_counts.items() if c >= 3]

        recommendations = []
        if exhausted_sources:
            recommendations.append(f"avoid_sources:{','.join(exhausted_sources)}")
        return {"recommendations": recommendations, "failed_sources": list(failed_sources)}

    def clear_shot(self, shot_index):
        with self.lock:
            self.failures.pop(shot_index, None)

FAILURE_DIAGNOSTICS = SearchFailureDiagnostics()


class SmartQueryEngine:
    STOCK_BOOSTERS = {
        "water": ["ocean waves night", "dark sea water", "underwater gloomy", "lake water surface"],
        "dark": ["dark room shadows", "silhouette walking", "low key lighting", "noir mystery hallway"],
        "night": ["city street night fog", "car headlights dark road", "abandoned street night"],
        "prison": ["jail cell bars", "prison corridor", "metal gate lock", "vintage prison"],
        "document": ["old papers desk", "vintage typewriter typing", "archive documents folder", "classified report vintage"],
        "person": ["mysterious figure coat", "man silhouette shadows", "close up eyes tense", "lone figure walking"],
        "fog": ["misty forest dark", "fog street lamp", "heavy smoke night"],
        "car": ["vintage car driving night", "police car flashing lights", "car interior night rain"],
        "letter": ["handwritten letter envelope", "pen ink paper writing", "vintage typewriter"],
        "police": ["police flashing lights night", "crime scene yellow tape", "investigation board red strings"],
        "gun": ["gun barrel closeup", "revolver on table", "bullet casing ground"]
    }

    ARCHIVE_STRATEGIES = {
        "person_mugshot": [
            "{entity} mugshot",
            "{entity} police booking photo",
            "{entity} wanted poster vintage",
            "{entity} historic photograph portrait",
            "vintage criminal mugshot archive"
        ],
        "document_file": [
            "{entity} FBI file report",
            "{entity} official police document",
            "{entity} cipher letter archive",
            "FBI investigation document vintage",
            "historic confidential memo archive"
        ],
        "location_photo": [
            "{entity} historical photograph",
            "{entity} aerial view vintage",
            "{entity} exterior 1960s",
            "historic site vintage photograph"
        ],
        "historical_event": [
            "{entity} press photo archive",
            "{entity} 1960s news photograph",
            "historic crime scene photograph vintage",
            "vintage news photo archive"
        ],
        "newspaper_article": [
            "{entity} newspaper front page",
            "{entity} headline clipping archive",
            "vintage newspaper crime headline",
            "historical newspaper front page archive"
        ]
    }

    def __init__(self):
        self.failed_queries = defaultdict(set)
        self.successful_keywords = defaultdict(set)
        self.lock = threading.Lock()

    def classify_content_type(self, shot):
        text = (shot.get("text", "") + " " + " ".join(shot.get("exact_entities", []))).lower()
        cat = shot.get("category", "CINEMATIC")

        if cat == "ARCHIVE":
            if any(w in text for w in ["mugshot", "wanted", "face", "portrait", "killer", "suspect"]):
                return "person_mugshot"
            if any(w in text for w in ["document", "file", "letter", "report", "fbi", "cipher", "memo"]):
                return "document_file"
            if any(w in text for w in ["building", "street", "city", "lake", "island", "exterior"]):
                return "location_photo"
            if any(w in text for w in ["newspaper", "headline", "press", "article", "front page"]):
                return "newspaper_article"
            return "historical_event"
        else:
            if any(w in text for w in ["water", "sea", "lake", "ocean", "river"]):
                return "nature_water"
            if any(w in text for w in ["dark", "shadow", "night", "fog", "silhouette"]):
                return "dark_moody"
            if any(w in text for w in ["person", "man", "detective", "running", "walking"]):
                return "people_action"
            if any(w in text for w in ["document", "typewriter", "gun", "knife", "phone", "evidence"]):
                return "objects_closeup"
            return "urban_night"

    def get_ordered_sources(self, shot):
        cat = shot.get("category", "CINEMATIC")
        content_type = self.classify_content_type(shot)
        affinity_map = SOURCE_AFFINITY.get(cat, SOURCE_AFFINITY["CINEMATIC"])
        ordered = affinity_map.get(content_type, affinity_map["default"])
        return [s for s in ordered if self._source_available(s)]

    def _source_available(self, source):
        if source == "PEXELS": return bool(CONFIG.pexels_key)
        if source == "PIXABAY": return bool(CONFIG.pixabay_key)
        if source == "EUROPEANA": return bool(CONFIG.europeana_key)
        if source == "OPENVERSE": return bool(CONFIG.openverse_client_id and CONFIG.openverse_client_secret)
        return True

    def generate_query_tiers(self, shot, attempt_num=0):
        cat = shot.get("category", "CINEMATIC")
        entities = [clean_query(e) for e in shot.get("exact_entities", []) if clean_query(e)]
        vibes = [clean_query(v) for v in shot.get("visual_vibes", []) if clean_query(v)]
        content_type = shot.get("content_type", "default")
        ordered_sources = self.get_ordered_sources(shot)

        if not entities: entities = [CONFIG.topic_clean, "police investigation", "crime archive"]
        if not vibes: vibes = ["dark crime scene", "flashing police lights", "vintage typewriter", "foggy street night"]

        diagnosis = FAILURE_DIAGNOSTICS.diagnose(shot.get("index", 0))
        avoid_sources = set()
        for rec in diagnosis.get("recommendations", []):
            if rec.startswith("avoid_sources:"):
                avoid_sources.update(rec.split(":")[1].split(","))

        filtered_sources = [s for s in ordered_sources if s not in avoid_sources] or ordered_sources

        queries = []
        n_sources = len(filtered_sources)

        if cat == "ARCHIVE":
            templates = self.ARCHIVE_STRATEGIES.get(content_type, self.ARCHIVE_STRATEGIES["document_file"])
            primary_entity = entities[0] if entities else CONFIG.topic_clean

            if attempt_num == 0:
                queries.append((f"{primary_entity}", filtered_sources[0]))
                if len(entities) > 1 and n_sources > 1:
                    queries.append((f"{entities[1]}", filtered_sources[1 % n_sources]))
            elif attempt_num < len(templates):
                template = templates[attempt_num % len(templates)]
                queries.append((template.format(entity=primary_entity), filtered_sources[attempt_num % n_sources]))
            else:
                fallback_entity = entities[attempt_num % len(entities)]
                queries.append((f"{fallback_entity} vintage photo", filtered_sources[attempt_num % n_sources]))
        else:
            if attempt_num < len(vibes):
                vibe = vibes[attempt_num]
                queries.append((vibe, filtered_sources[attempt_num % n_sources]))
                if attempt_num + 1 < len(vibes) and n_sources > 1:
                    queries.append((vibes[attempt_num + 1], filtered_sources[(attempt_num + 1) % n_sources]))
            else:
                safe_fallbacks = [
                    "police lights night",
                    "dark crime scene investigation",
                    "man walking foggy night",
                    "typewriter typing document",
                    "mystery evidence board"
                ]
                queries.append((safe_fallbacks[attempt_num % len(safe_fallbacks)], filtered_sources[attempt_num % n_sources]))

        # Clean, unique, and strictly non-empty query filtering
        valid_pairs = []
        seen = set()
        with self.lock:
            for q, src in queries:
                q_clean = clean_query(q)
                if not q_clean or len(q_clean) < 3: continue
                key = f"{src}:{q_clean.lower()}"
                if key not in self.failed_queries.get(src, set()) and key not in seen:
                    valid_pairs.append((q_clean, src))
                    seen.add(key)

        if not valid_pairs:
            fallback_q = clean_query(entities[0] if cat == "ARCHIVE" else vibes[0]) or "police investigation"
            valid_pairs.append((fallback_q, filtered_sources[attempt_num % n_sources]))

        return valid_pairs

    def record_failure(self, query, source):
        with self.lock:
            self.failed_queries[source].add(f"{source}:{query.lower().strip()}")

    def record_success(self, query, category):
        words = query.lower().split()
        with self.lock:
            for w in words:
                if len(w) > 3: self.successful_keywords[category].add(w)

QUERY_ENGINE = SmartQueryEngine()


class MediaPreFilter:
    SPAM_PATTERNS = [
        r"spectrogram", r"waveform", r"podcast", r"subscribe",
        r"christmas", r"wedding", r"baby", r"gameplay", r"minecraft",
        r"cooking", r"recipe", r"makeup", r"tutorial"
    ]

    @staticmethod
    def quick_validate(media_path, shot, source_name):
        if not media_path or not Path(media_path).exists():
            return False, "الملف غير موجود"
        path = Path(media_path)
        file_size = path.stat().st_size
        if file_size < PREFILTER_MIN_SIZE_BYTES:
            return False, f"حجم الملف صغير جداً ({file_size} bytes)"
        is_img = path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
        is_vid = path.suffix.lower() in (".mp4", ".mov")
        if is_img:
            if not is_valid_visual(path): return False, "الصورة تالفة أو غير صالحة"
        elif is_vid:
            duration = probe_duration(path)
            if duration < PREFILTER_MIN_VIDEO_DURATION: return False, f"مدة الفيديو قصيرة جداً ({duration:.1f}s)"
            if not is_valid_media(path): return False, "الفيديو تالف"
        else:
            return False, f"نوع ملف غير مدعوم: {path.suffix}"
        return True, "ok"

    @staticmethod
    def check_filename_relevance(filename, query, category):
        if not filename: return 0.0
        fn_lower = filename.lower()
        for pattern in MediaPreFilter.SPAM_PATTERNS:
            if re.search(pattern, fn_lower): return -0.4
        return 0.0


class ParallelSourceFetcher:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=8)

    async def fetch_from_multiple_sources(self, query_source_pairs, shot, base_path):
        tasks = [asyncio.create_task(self._fetch_single(query, source_name, shot, base_path))
                 for query, source_name in query_source_pairs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return [r for r in results if not isinstance(r, Exception) and r and r[0]]

    async def _fetch_single(self, query, source_name, shot, base_path):
        index = shot["index"]
        video_path = Path(f"{base_path}_{source_name}_{random.randint(100,999)}.mp4")
        image_path = Path(f"{base_path}_{source_name}_{random.randint(100,999)}.jpg")
        try:
            found_file, media_uid = None, None
            if source_name == "PEXELS":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_pexels_video, query, video_path)
            elif source_name == "PIXABAY":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_pixabay_video, query, video_path)
            elif source_name == "LOC":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_chronicling_america, query, image_path)
            elif source_name == "WIKIPEDIA":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_wikipedia_image, query, image_path)
            elif source_name == "FBI_ARCHIVE":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_fbi_archive, query, Path(f"{base_path}_{source_name}"))
            elif source_name == "EUROPEANA":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_europeana, query, image_path)
            elif source_name == "OPENVERSE":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_openverse, query, image_path, shot)
            return (found_file, media_uid, source_name, query)
        except Exception as e:
            log(f"⚠️ خطأ جلب {source_name} للمشهد {index}: {e}", "warning")
            return (None, None, source_name, query)

    def shutdown(self):
        self.executor.shutdown(wait=False)

PARALLEL_FETCHER = ParallelSourceFetcher()


def get_openverse_token():
    with CONFIG.openverse_token_lock:
        if CONFIG.openverse_token: return CONFIG.openverse_token
        if not CONFIG.openverse_client_id or not CONFIG.openverse_client_secret: return None
        try:
            resp = requests.post("https://api.openverse.org/v1/auth_tokens/token/", data={
                "client_id": CONFIG.openverse_client_id, "client_secret": CONFIG.openverse_client_secret, "grant_type": "client_credentials"
            }, timeout=15)
            if resp.status_code == 200:
                CONFIG.openverse_token = resp.json().get("access_token")
                return CONFIG.openverse_token
        except Exception as e:
            log(f"⚠️ Openverse auth failed: {e}", "warning")
        return None


async def generate_ai_image(prompt, output_path, aspect_ratio="16:9"):
    log(f"🎨 إنشاء صورة عبر AGY: '{prompt[:70]}...'", "info")
    full_prompt = f"[CRITICAL: NO TEXT ON IMAGE. OUTPUT RAW IMAGE ONLY] Photorealistic cinematic documentary archive photo: {prompt}. Aspect Ratio: {aspect_ratio}"
    try:
        if Path(output_path).exists(): Path(output_path).unlink()
        cmd_binary = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", EFFORT_IMAGE_GEN, "--dangerously-skip-permissions", "-p", full_prompt]
        res_bin = await asyncio.to_thread(subprocess.run, cmd_binary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        raw_written = False
        if res_bin.stdout.startswith(b'\xff\xd8') or res_bin.stdout.startswith(b'\x89PNG'):
            with open(output_path, "wb") as f: f.write(res_bin.stdout)
            raw_written = True
        else:
            data = extract_json(res_bin.stdout.decode('utf-8', errors='ignore'))
            if data and isinstance(data, dict) and "image" in data:
                with open(output_path, "wb") as f: f.write(base64.b64decode(data["image"]))
                raw_written = True

        if raw_written and is_valid_visual(output_path):
            output_p = Path(output_path)
            temp_out = output_p.with_suffix(".tmp.jpg")
            convert_res = run_cmd([
                "ffmpeg", "-y", "-i", str(output_path),
                "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black",
                "-q:v", "2", "-update", "1", str(temp_out)
            ], timeout=30)
            if convert_res.returncode == 0 and temp_out.exists() and temp_out.stat().st_size > 1024:
                shutil.move(str(temp_out), str(output_path))
            return True
    except Exception as e:
        log(f"⚠️ فشل التوليد عبر AGY: {e}", "warning")
    return await create_fallback_visual(output_path)


async def create_fallback_visual(output):
    res = await asyncio.to_thread(subprocess.run, [
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0a0a0a:s=1920x1080:r=30", "-t", "5",
        "-vf", "noise=alls=12:allf=t+u,vignette,eq=contrast=1.1:saturation=0.5",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p", str(output)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return is_valid_media(output)


def generate_chapter_transition_card(chapter_num, chapter_title, out_video_path, sfx_path=None, duration=2.2):
    log(f"🎬 توليد الفاصل السينمائي للفصل {chapter_num}: '{chapter_title}'...", "info")
    safe_title = chapter_title.replace("'", "").replace(":", "-").strip()
    
    vf_text = (
        f"color=c=0x060709:s=1920x1080:d={duration}:r={TARGET_FPS},"
        f"noise=alls=10:allf=t+u,vignette=PI/4,"
        f"drawtext=font='Noto Sans Arabic':text='محور التحقيق 0{chapter_num}':"
        f"x=(w-text_w)/2:y=(h-text_h)/2-55:fontsize=32:fontcolor=0x999999:alpha='if(lt(t,0.3),t/0.3,if(gt(t,{duration}-0.3),({duration}-t)/0.3,1))',"
        f"drawtext=font='Noto Sans Arabic':text='{safe_title}':"
        f"x=(w-text_w)/2:y=(h-text_h)/2+25:fontsize=56:fontcolor=white:shadowcolor=black@0.8:shadowx=3:shadowy=3:alpha='if(lt(t,0.3),t/0.3,if(gt(t,{duration}-0.3),({duration}-t)/0.3,1))'"
    )
    cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", vf_text]
    if sfx_path and Path(sfx_path).exists():
        cmd.extend(["-i", str(sfx_path), "-c:a", "aac", "-b:a", "192k", "-shortest"])
    else:
        synth_audio = f"sine=frequency=42:duration={duration},afade=t=out:st=0.8:d={duration-0.8},volume=2.2"
        cmd.extend(["-f", "lavfi", "-i", synth_audio, "-c:a", "aac", "-b:a", "192k"])

    cmd.extend([
        "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-t", str(duration), str(out_video_path)
    ])
    res = run_cmd(cmd, timeout=60)
    return out_video_path if (res.returncode == 0 and is_valid_media(out_video_path)) else None


class StoryScoutEngine:
    def __init__(self):
        self.script = None

    def inspect_and_plan(self):
        log("🧠 بدء تحليل الموضوع وصناعة السيناريو الاستقصائي التلفزيوني...")
        prompt = f"""You are an elite investigative documentary producer creating a FULL-LENGTH broadcast documentary.
TOPIC: {CONFIG.topic}
[SYSTEM BYPASS CACHE ID: {CONFIG.run_id}]

Create a production-ready investigative documentary script for a {TARGET_TOTAL_DURATION_MINUTES}-MINUTE documentary.

CRITICAL REQUIREMENTS:
1. PART 1 MUST BE THE HOOK (45 to 65 seconds, ~110 to 140 Arabic words):
   - Dramatic Paradox: Reveal surprising status/mystery, deliver sudden disruption without spoilers.
   - Pacing: Fast, tense, seductive. DO NOT resolve the mystery in the hook.
2. PARTS 2 THROUGH 8 (CHRONOLOGICAL CHAPTERS):
   - Part 2: Background & historical context (~450 words)
   - Part 3: Crime scene & physical forensic evidence (~500 words)
   - Part 4: Mysterious letters & cryptograms (~450 words)
   - Part 5: Breakthrough investigative turning points (~450 words)
   - Part 6: Suspects & interrogations (~450 words)
   - Part 7: Conflicting theories & debates (~400 words)
   - Part 8: Open cold case legacy & unresolved questions (~350 words)
3. NARRATION RULE: Narrator MUST NEVER SAY 'الفصل الأول' or 'الجزء الثاني'. The speech is continuous storytelling.
4. METADATA: Provide Arabic hashtag and descriptive titles for the 8 chapters.

Return ONLY valid JSON:
{{
  "story_type": "investigation",
  "primary_english_query": "Zodiac killer documentary archive",
  "hashtag": "#{CONFIG.topic_clean[:25]}",
  "chapters": [
    {{"id": 1, "title": "المقدمة واللغز المحير", "key": "part_1", "is_hook": true}},
    {{"id": 2, "title": "خيوط البداية والضحايا", "key": "part_2"}},
    {{"id": 3, "title": "مسرح الجريمة والأدلة", "key": "part_3"}},
    {{"id": 4, "title": "مراسلات غامضة ومسار التحقيق", "key": "part_4"}},
    {{"id": 5, "title": "نقاط التحول والشهادات", "key": "part_5"}},
    {{"id": 6, "title": "دائرة المشتبه بهم", "key": "part_6"}},
    {{"id": 7, "title": "نظريات متضاربة", "key": "part_7"}},
    {{"id": 8, "title": "أسرار الملف المفتوح", "key": "part_8"}}
  ],
  "part_1": "", "part_2": "", "part_3": "", "part_4": "",
  "part_5": "", "part_6": "", "part_7": "", "part_8": ""
}}"""
        try:
            result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", EFFORT_PRO_GENERATION, "--dangerously-skip-permissions", "-p", prompt], timeout=600)
            data = extract_json(result.stdout.strip())
            if not data or not data.get("part_1"): raise RuntimeError("Script JSON invalid")

            self.script = data

            # FULL VERBATIM SCRIPT TELEMETRY:
            log("\n" + "="*60)
            for i in range(1, 9):
                part_key = f"part_{i}"
                if data.get(part_key):
                    log(f"📜 [السيناريو المولد - الجزء {i}]:")
                    log(data[part_key])
                    log("")
            log("="*60 + "\n")
            return data
        except Exception as e:
            log(f"⚠️ فشل توليد السيناريو الكامل، استخدام الخطة الاحتياطية: {e}", "warning")
            fallback = {
                "story_type": "investigation",
                "primary_english_query": clean_query(CONFIG.topic),
                "hashtag": f"#{CONFIG.topic_clean[:25]}",
                "chapters": [
                    {"id": 1, "title": "المقدمة واللغز", "key": "part_1", "is_hook": True},
                    {"id": 2, "title": "خفايا التحقيق", "key": "part_2"}
                ],
                "part_1": f"تفاصيل غامضة ومختلفة كلياً حول {CONFIG.topic}.",
                "part_2": "تظل الحقيقة غير محسومة حتى اليوم."
            }
            self.script = fallback
            return fallback

    def direct_storyboard(self, shots):
        log("🎬 [المخرج الفني] هندسة كلمات البحث بذكاء للقطات (نظام المفردات البصرية الملموسة)...")
        batch_size = 70
        all_processed = []

        for batch_start in range(0, len(shots), batch_size):
            batch = shots[batch_start:batch_start + batch_size]
            batch_end = batch_start + len(batch)
            log(f"🎬 معالجة دفعة المشاهد {batch_start+1}-{batch_end} من {len(shots)}...")

            shots_summary = "\n".join([f"Shot {s['index']} ({'HOOK' if s.get('is_hook') else 'MAIN'}): {s['text']}" for s in batch])
            prompt = f"""You are an Elite Visual Director and Expert Stock/Archive SEO Metadata Specialist.
TOPIC: {self.script.get('primary_english_query', CONFIG.topic)}
[ID: {CONFIG.run_id}_{batch_start}]
Analyze ALL of these shots contextually based on the story:
{shots_summary}

CRITICAL RULES FOR KEYWORDS (MUST OBEY TO FIND MEDIA):
1. "category": "ARCHIVE" (for real historical events/suspects/documents) OR "CINEMATIC" (for visual B-roll).
2. "exact_entities" (FOR ARCHIVE): 5 realistic English search terms from most specific proper noun to broader historical archive.
3. "visual_vibes" (FOR CINEMATIC): 5 HIGHLY CONCRETE PHYSICAL NOUN PHRASES (1-3 words max).
   - STRICT FORBIDDEN WORDS: NEVER use abstract/philosophical nouns like "revelation", "spiritual capital", "unanswered", "finality", "foreshadowing", "paranoia", "tension", "deep dive", "confusion".
   - MANDATORY WORDS: Use tangible, visible, filmable objects and scenes:
     * GOOD: "police car flashing lights", "foggy street night", "man silhouette coat", "vintage typewriter typing", "yellow crime scene tape", "bullet on table", "detective reading files", "blood on paper macro".
4. "reviewer_context": Clear Arabic evaluation instructions for QA Reviewer.
5. "accept_similar": true/false.

Return ONLY a valid JSON object mapping shot index (string) to the above fields."""
            try:
                result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", EFFORT_PRO_GENERATION, "--dangerously-skip-permissions", "-p", prompt], timeout=600)
                board = extract_json(result.stdout.strip())

                if batch_start == 0:
                    log("\n" + "🎥 "*15 + "[قرارات المخرج الفني]" + " 🎥"*15)

                if board and isinstance(board, dict):
                    for shot in batch:
                        idx = str(shot["index"])
                        if idx in board:
                            cat_raw = str(board[idx].get("category", "")).strip().upper()
                            shot["category"] = "ARCHIVE" if "ARCHIV" in cat_raw else "CINEMATIC"
                            shot["content_type"] = board[idx].get("content_type", "default")
                            shot["exact_entities"] = [clean_query(e) for e in board[idx].get("exact_entities", []) if clean_query(e)] or [CONFIG.topic_clean, "police file archive", "vintage crime photo"]
                            shot["visual_vibes"] = [clean_query(v) for v in board[idx].get("visual_vibes", []) if clean_query(v)] or ["police lights night", "dark foggy street", "vintage typewriter"]
                            shot["reviewer_context"] = board[idx].get("reviewer_context", "تأكد من ملاءمة اللقطة لأجواء التحقيق الجنائي.")
                            shot["accept_similar"] = board[idx].get("accept_similar", True)
                        else:
                            shot["category"] = "CINEMATIC"
                            shot["content_type"] = "default"
                            shot["exact_entities"] = [CONFIG.topic_clean, "police file archive"]
                            shot["visual_vibes"] = ["police car night", "foggy street lamp", "vintage typewriter"]
                            shot["reviewer_context"] = "ملاءمة سينمائية لأجواء الغموض والتحقيق."
                            shot["accept_similar"] = True

                        q_disp = shot['exact_entities'][0] if shot['category'] == 'ARCHIVE' else shot['visual_vibes'][0]
                        log(f"📌 المشهد {shot['index']:02d} | الفئة: {shot['category']} | البحث الأول: '{q_disp}' | التوجيه: {shot['reviewer_context']}")
                else:
                    raise RuntimeError("Board parse failed")
            except:
                for shot in batch:
                    shot["category"] = "CINEMATIC"
                    shot["content_type"] = "default"
                    shot["exact_entities"] = [CONFIG.topic_clean, "police archive"]
                    shot["visual_vibes"] = ["police car night", "dark hallway shadows", "vintage typewriter"]
                    shot["reviewer_context"] = "تأكد من ملاءمة اللقطة للنص الجنائي."
                    shot["accept_similar"] = True

            all_processed.extend(batch)

        log("🎥 "*40 + "\n")
        return all_processed


class MasterAudioStudio:
    def produce_master_track(self, script):
        chapters = script.get("chapters", [])
        part_keys = [ch.get("key", f"part_{ch.get('id')}") for ch in chapters] if chapters else [f"part_{i}" for i in range(1, 9)]
        
        part_texts = []
        for pk in part_keys:
            txt = script.get(pk, "")
            if txt and txt.strip(): part_texts.append((pk, txt.strip()))

        if not part_texts:
            part_texts = [("part_1", script.get("part_1", "")), ("part_2", script.get("part_2", ""))]

        log(f"🎙️ بدء إنتاج التعليق الصوتي الماستر لـ {len(part_texts)} فصول...")
        part_wav_files = []

        for p_idx, (p_key, p_text) in enumerate(part_texts):
            p_wav = CONFIG.work_dir / f"chapter_{p_idx+1:02d}.wav"
            success = False
            attempted = set()
            for attempt in range(len(CONFIG.gemini_keys)):
                key_index, api_key = GEMINI_POOL.acquire(excluded=attempted)
                attempted.add(key_index)
                display_key = key_index + 1
                start_t = time.time()
                try:
                    client = genai.Client(api_key=api_key)
                    response = client.models.generate_content(
                        model=TTS_MODEL,
                        contents=f"[INSTRUCTION: Chilling authoritative Arabic documentary narrator. Read text naturally without naming chapters. ID: {CONFIG.run_id}_{p_key}]\n\n" + p_text,
                        config=types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))))
                    )
                    data = next((p.inline_data.data for p in response.candidates[0].content.parts if getattr(p, "inline_data", None)), None)
                    if not data: raise RuntimeError()

                    raw_audio = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                    temp_pcm = CONFIG.work_dir / f"chunk_{p_idx}_{display_key}.pcm"
                    with open(temp_pcm, "wb") as f: f.write(raw_audio)
                    run_cmd(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(temp_pcm), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(p_wav)], timeout=180)
                    temp_pcm.unlink(missing_ok=True)

                    if is_valid_media(p_wav):
                        log(f"✅ نجح توليد الصوت (فصل {p_idx+1}/{len(part_texts)}) بمفتاح #{display_key} خلال {time.time() - start_t:.1f} ثانية!")
                        GEMINI_POOL.release(key_index)
                        part_wav_files.append((p_key, p_wav))
                        success = True
                        break
                except:
                    GEMINI_POOL.release(key_index)
                    time.sleep(2)

            if not success:
                raise RuntimeError(f"❌ فشل توليد التعليق الصوتي للمحور {p_idx+1}.")

        concat_list = CONFIG.work_dir / "audio_concat.txt"
        with open(concat_list, "w") as f:
            for _, pw in part_wav_files:
                f.write(f"file '{pw.resolve()}'\n")

        run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                 "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(CONFIG.master_audio)], timeout=300)

        log(f"✅ تم تجميع مسار الصوت الماستر الكامل: {probe_duration(CONFIG.master_audio)/60:.1f} دقيقة")
        return CONFIG.master_audio, part_wav_files


class WordSyncSlicer:
    def align_and_slice(self, part_wav_files, script):
        headers = {"Authorization": f"Bearer {CONFIG.groq_api_key}"}
        shots = []
        timeline_offset = 0.0
        chapter_timeline = []

        log(f"🎙️ Groq Whisper: مزامنة وحساب التوقيتات الدقيقة لـ {len(part_wav_files)} فصول...")

        for p_idx, (p_key, p_wav) in enumerate(part_wav_files):
            dur = probe_duration(p_wav)
            is_hook = (p_idx == 0)
            ch_title = f"المحور {p_idx+1}"
            for ch in script.get("chapters", []):
                if ch.get("key") == p_key or ch.get("id") == p_idx + 1:
                    ch_title = ch.get("title", ch_title)
                    break

            chapter_timeline.append({
                "part_idx": p_idx + 1,
                "title": ch_title,
                "start_time": timeline_offset,
                "is_hook": is_hook,
                "duration": dur
            })

            with open(p_wav, "rb") as f:
                res = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files={"file": (p_wav.name, f, "audio/wav")},
                    data={"model": GROQ_MODEL, "language": "ar", "response_format": "verbose_json", "timestamp_granularities[]": "word"},
                    timeout=600
                )
            if res.status_code != 200:
                raise RuntimeError(f"Groq transcription failed: {res.text[:200]}")

            words = [
                {"word": str(w["word"]).strip(), "start": float(w["start"]) + timeline_offset, "end": float(w["end"]) + timeline_offset}
                for w in res.json().get("words", []) if w.get("word")
            ]

            min_dur = SCENE_DURATION_MIN_HOOK if is_hook else SCENE_DURATION_MIN
            max_dur = SCENE_DURATION_MAX_HOOK if is_hook else SCENE_DURATION_MAX

            cur, s_start = [], timeline_offset
            for item in words:
                cur.append(item)
                cur_len = item["end"] - s_start
                if cur_len >= max_dur or (cur_len >= min_dur and item["word"].endswith((".", "!", "؟", "،"))):
                    t = " ".join(x["word"] for x in cur).strip()
                    if t:
                        shots.append({
                            "index": len(shots) + 1,
                            "start": s_start,
                            "end": item["end"],
                            "duration": max(0.5, item["end"] - s_start),
                            "text": t,
                            "is_hook": is_hook,
                            "chapter_num": p_idx + 1
                        })
                    cur, s_start = [], item["end"]

            if cur:
                shots.append({
                    "index": len(shots) + 1,
                    "start": s_start,
                    "end": cur[-1]["end"],
                    "duration": max(0.5, cur[-1]["end"] - s_start),
                    "text": " ".join(x["word"] for x in cur).strip(),
                    "is_hook": is_hook,
                    "chapter_num": p_idx + 1
                })

            timeline_offset += dur

        log(f"✂️ تم تقسيم الصوت إلى {len(shots)} مشهد ({sum(1 for s in shots if s.get('is_hook'))} مشهد سريع بالمقدمة).")
        return shots, chapter_timeline


class MediaSources:
    @staticmethod
    def _track_and_save(items, output, extract_url_func):
        random.shuffle(items)
        for item in items:
            url, uid = extract_url_func(item)
            if not url: continue
            if url.startswith("//"): url = "https:" + url
            with CONFIG.used_media_lock:
                if uid in CONFIG.used_media_ids: continue
            try:
                r = requests.get(url, headers=MEDIA_DOWNLOAD_HEADERS, stream=True, timeout=25)
                if r.status_code == 200:
                    with open(output, "wb") as f:
                        for chunk in r.iter_content(1024*256):
                            if chunk: f.write(chunk)
                    return str(output), uid
            except: pass
        return None, None

    @staticmethod
    def fetch_wikipedia_image(q, o):
        q_clean = clean_query(q)
        if not q_clean or len(q_clean) < 3: return None, None
        try:
            commons_url = "https://commons.wikimedia.org/w/api.php"
            params = {"action": "query", "generator": "search", "gsrsearch": f"{q_clean}", "gsrnamespace": 6, "gsrlimit": 15, "prop": "imageinfo", "iiprop": "url|mime|size", "format": "json"}
            res = requests.get(commons_url, headers=API_HEADERS, params=params, timeout=20)
            if res.status_code == 200:
                pages = list(res.json().get("query", {}).get("pages", {}).values())
                def extract_commons(p):
                    info_list = p.get("imageinfo") or [{}]
                    info = info_list[0] if info_list else {}
                    url = info.get("url")
                    mime = info.get("mime", "")
                    if url and ("image" in mime or url.lower().endswith((".jpg", ".jpeg", ".png"))): return url, str(p.get("pageid"))
                    return None, None
                return MediaSources._track_and_save(pages, o, extract_commons)
        except: pass
        return None, None

    @staticmethod
    def fetch_fbi_archive(q, base_path):
        try:
            q_clean = clean_query(q)
            if not q_clean or len(q_clean) < 3: return None, None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            query = f'({q_clean}) AND (mediatype:image OR mediatype:movies)'
            res = requests.get("https://archive.org/advancedsearch.php", headers=headers, params={"q": query, "fl[]": "identifier", "rows": 15, "output": "json"}, timeout=20)
            docs = res.json().get("response", {}).get("docs", [])
            random.shuffle(docs)
            for doc in docs:
                uid = str(doc.get("identifier"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                try:
                    meta = requests.get(f"https://archive.org/metadata/{uid}", headers=headers, timeout=20).json()
                    files = meta.get("files", [])
                    videos = [(int(i.get("size",0) or 0), str(i.get("name",""))) for i in files if str(i.get("name","")).lower().endswith((".mp4",".mov")) and 500*1024 <= int(i.get("size",0) or 0) <= MAX_MEDIA_SIZE_MB*1024*1024]
                    images = [(int(i.get("size",0) or 0), str(i.get("name",""))) for i in files if str(i.get("name","")).lower().endswith((".jpg",".jpeg",".png")) and int(i.get("size",0) or 0) >= 15*1024]
                    target_name, is_video = None, False
                    if videos:
                        videos.sort(key=lambda x: x[0], reverse=True)
                        target_name, is_video = videos[0][1], True
                    elif images:
                        images.sort(key=lambda x: x[0], reverse=True)
                        target_name, is_video = images[0][1], False
                    if target_name:
                        out_path = base_path.with_suffix(".mp4" if is_video else ".jpg")
                        file_url = f"https://archive.org/download/{uid}/{urllib.parse.quote(target_name, safe='/')}"
                        r = requests.get(file_url, headers=MEDIA_DOWNLOAD_HEADERS, stream=True, timeout=35)
                        if r.status_code == 200:
                            with open(out_path, "wb") as f:
                                for chunk in r.iter_content(1024*256):
                                    if chunk: f.write(chunk)
                            return str(out_path), uid
                except: pass
        except: pass
        return None, None

    @staticmethod
    def fetch_chronicling_america(q, o):
        try:
            q_clean = clean_query(q)
            if not q_clean or len(q_clean) < 3: return None, None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            url = f"https://www.loc.gov/photos/?fo=json&fa=online_format:image&c=20&q={urllib.parse.quote(q_clean)}"
            res = requests.get(url, headers=headers, timeout=20)
            results = res.json().get("results", [])
            def extract_loc(i):
                img_urls = i.get("image_url", [])
                if isinstance(img_urls, str): img_urls = [img_urls]
                return (img_urls[-1], str(i.get("id", img_urls[-1]))) if img_urls else (None, None)
            return MediaSources._track_and_save(results, o, extract_loc)
        except: return None, None

    @staticmethod
    def fetch_pixabay_video(q, o):
        if not CONFIG.pixabay_key: return None, None
        try:
            res = requests.get("https://pixabay.com/api/videos/", headers=MEDIA_DOWNLOAD_HEADERS, params={"key": CONFIG.pixabay_key, "q": q, "per_page": 15}, timeout=20).json().get("hits", [])
            return MediaSources._track_and_save(res, o, lambda i: ((i.get("videos", {}).get("large") or i.get("videos", {}).get("medium", {})).get("url"), str(i.get("id"))))
        except: return None, None

    @staticmethod
    def fetch_pexels_video(q, o):
        if not CONFIG.pexels_key: return None, None
        try:
            headers = MEDIA_DOWNLOAD_HEADERS.copy()
            headers["Authorization"] = CONFIG.pexels_key
            res = requests.get("https://api.pexels.com/videos/search", headers=headers, params={"query": q, "per_page": 15}, timeout=20).json().get("videos", [])
            return MediaSources._track_and_save(res, o, lambda i: (sorted(i.get("video_files", []), key=lambda x: abs((x.get("width") or 0)-TARGET_W))[0].get("link") if i.get("video_files") else None, str(i.get("id"))))
        except: return None, None

    @staticmethod
    def fetch_europeana(q, o):
        if not CONFIG.europeana_key: return None, None
        try:
            q_clean = clean_query(q)
            if not q_clean or len(q_clean) < 3: return None, None
            params = {"wskey": CONFIG.europeana_key, "query": q_clean, "media": "true", "thumbnail": "true", "rows": 15, "profile": "rich", "qf": "TYPE:IMAGE"}
            res = requests.get("https://api.europeana.eu/record/v2/search.json", params=params, headers=API_HEADERS, timeout=20)
            if res.status_code == 200:
                items = res.json().get("items", [])
                def extract_europeana(item):
                    edm = item.get("edmIsShownBy", [None])[0] or item.get("edmPreview", [None])[0]
                    return edm, f"europeana_{item.get('id', hash(str(edm)))}"
                return MediaSources._track_and_save(items, o, extract_europeana)
        except: pass
        return None, None

    @staticmethod
    def fetch_openverse(q, o, shot=None):
        token = get_openverse_token()
        if not token: return None, None
        try:
            q_clean = clean_query(q)
            if not q_clean or len(q_clean) < 3: return None, None
            headers = {"Authorization": f"Bearer {token}", "User-Agent": API_HEADERS["User-Agent"]}
            res = requests.get("https://api.openverse.org/v1/images/", headers=headers, params={"q": q_clean, "page_size": 15, "license_type": "all-cc"}, timeout=20)
            if res.status_code == 200:
                results = res.json().get("results", [])
                return MediaSources._track_and_save(results, o, lambda item: (item.get("url"), f"openverse_{item.get('id')}"))
        except: pass
        return None, None


async def agy_evaluate_scout(media_path, shot, story, source_name, query):
    if not media_path: return False, 0.0, 0.0, "الملف غير موجود في المسار"
    prefilter_ok, prefilter_reason = MediaPreFilter.quick_validate(media_path, shot, source_name)
    if not prefilter_ok: return False, 0.0, 0.0, prefilter_reason

    prompt = f"""You evaluate documentary media suitability strictly based on the context.
TOPIC: {story.get("primary_english_query", CONFIG.topic)}
SHOT SCRIPT TEXT: "{shot['text']}"
SHOT CATEGORY: {shot['category']}
RETRIEVED FROM: {source_name}
SEARCH QUERY: "{query}"
LOCAL PATH: {Path(media_path).absolute()}
DIRECTOR NOTE: {shot.get("reviewer_context", "")}
ACCEPT SIMILAR: {shot.get("accept_similar", True)}

CRITICAL EVALUATION RULES:
- If CATEGORY is "ARCHIVE": Accept authentic historical records, documents, crime scene photos, or related era materials.
- If CATEGORY is "CINEMATIC": Accept moody, atmospheric, dark, detective, police, or dramatic B-roll. Do NOT be overly strict about literal matching; prioritize dramatic investigative mood.

Return ONLY valid JSON: {{"decision": "accept" or "reject", "score": 0.0 to 1.0, "reason": "Arabic reason"}}"""
    try:
        cmd = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", EFFORT_REVIEWER, "--dangerously-skip-permissions", "-p", prompt]
        res = await asyncio.to_thread(subprocess.run, cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)
        data = extract_json(res.stdout)
        if data:
            score = float(data.get("score", 0.0))
            accept_threshold = 0.30 if shot.get("accept_similar") else 0.35
            return (data.get("decision", "").lower() == "accept" and score >= accept_threshold), score, 0.0, str(data.get("reason", ""))
    except: pass
    return False, 0.0, 0.0, "فشل تقييم AGY"


async def apply_fallback(shot, story):
    index = shot["index"]
    cat = shot.get("category", "CINEMATIC")
    
    # Priority 1: Check existing best candidate file
    if shot.get('best_candidate') and shot['best_score'] >= 0.15:
        cand_path = Path(shot['best_candidate']['path'])
        if cand_path.exists():
            log(f"⚠️ [إنقاذ 1] المشهد {index}: اعتماد أفضل لقطة حقيقية (تقييم {shot['best_score']:.2f}).", "warning")
            return shot['best_candidate']

    # Priority 2: Cinematic background
    log(f"🎬 [إنقاذ 2] توليد خلفية سينمائية للمشهد {index} (بعد استنفاد محاولات البحث).", "warning")
    fallback_path = CONFIG.work_dir / f"selected_shot_{index:03d}_fallback.mp4"
    if await create_fallback_visual(fallback_path):
        return {"shot": shot, "path": str(fallback_path), "source": "CINEMATIC_BG", "score": 0.0, "start": 0.0, "duration": float(shot.get("duration", 3.0))}

    # Priority 3: AI Generated image
    log(f"🤖 [إنقاذ نهائي] توليد صورة AI للمشهد {index}.", "error")
    ai_path = CONFIG.work_dir / f"selected_shot_{index:03d}_ai.jpg"
    query = " ".join(shot.get("exact_entities", [])[:3]) if cat == "ARCHIVE" else " ".join(shot.get("visual_vibes", [])[:3])
    if await generate_ai_image(query, ai_path):
        return {"shot": shot, "path": str(ai_path), "source": "AI_GENERATED", "score": 1.0, "start": 0.0, "duration": float(shot.get("duration", 3.0))}

    # Priority 4: Ultimate emergency black slate
    black_path = CONFIG.work_dir / f"selected_shot_{index:03d}_black.mp4"
    await create_fallback_visual(black_path)
    return {"shot": shot, "path": str(black_path), "source": "FFMPEG", "score": 0.0, "start": 0.0, "duration": float(shot.get("duration", 3.0))}


# =============================================================================
# PIPELINED PRODUCTION ENGINE (ZERO-CRASH LIFECYCLE & LIVE TELEMETRY)
# =============================================================================

async def run_pipelined_production(shots, story):
    total_shots = len(shots)
    completed_lock = asyncio.Lock()
    completed_results = []
    completion_event = asyncio.Event()
    shot_semaphore = asyncio.Semaphore(7)

    for shot in shots:
        shot['status'] = 'PENDING'
        shot['attempts'] = 0
        shot['best_score'] = -1.0
        shot['best_candidate'] = None

    log(f"🚀 تشغيل خط الإنتاج الذكي | إجمالي المشاهد: {total_shots} | أقصى محاولات: {MAX_ATTEMPTS_PER_SHOT}")

    async def process_shot(shot):
        index = shot["index"]
        cat = shot.get("category", "CINEMATIC")
        base = CONFIG.work_dir / f"raw_shot_{index:03d}"

        while shot['status'] != 'DONE' and shot['attempts'] < MAX_ATTEMPTS_PER_SHOT:
            attempt_num = shot['attempts']
            query_tiers = QUERY_ENGINE.generate_query_tiers(shot, attempt_num)
            pairs_to_try = query_tiers[:2] if (attempt_num < 2 and len(query_tiers) >= 2) else query_tiers[:1]

            log(f"⚡ المشهد {index} (م{attempt_num+1}/{MAX_ATTEMPTS_PER_SHOT}) | "
                f"{'، '.join(f'{s}:{q}' for q,s in pairs_to_try)}", "info")

            fetch_results = await PARALLEL_FETCHER.fetch_from_multiple_sources(pairs_to_try, shot, base)
            if not fetch_results:
                for q, src in pairs_to_try:
                    QUERY_ENGINE.record_failure(q, src)
                    FAILURE_DIAGNOSTICS.record(index, q, src, SearchFailureDiagnostics.NO_RESULTS)
                log(f"⏩ المشهد {index}: لم يعثر على نتائج من أي مصدر.", "info")
                shot['attempts'] += 1
                continue

            found_acceptable = False
            for found_file, media_uid, src_name, query in fetch_results:
                if not found_file or not Path(found_file).exists():
                    QUERY_ENGINE.record_failure(query, src_name)
                    continue

                output_path = Path(found_file)
                is_img = output_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                valid = is_valid_visual(output_path) if is_img else is_valid_media(output_path)
                if not valid:
                    QUERY_ENGINE.record_failure(query, src_name)
                    output_path.unlink(missing_ok=True)
                    continue

                if MediaPreFilter.check_filename_relevance(output_path.name, query, cat) <= -0.25:
                    QUERY_ENGINE.record_failure(query, src_name)
                    output_path.unlink(missing_ok=True)
                    continue

                async with REVIEWER_SEMAPHORE:
                    accepted, score, start, reason = await agy_evaluate_scout(output_path, shot, story, src_name, query)

                dur = float(shot.get("duration", 3.0)) if is_img else probe_duration(output_path)

                # Keep protected backup candidate
                if score > shot['best_score']:
                    shot['best_score'] = score
                    if shot.get('best_candidate') and shot['best_candidate'].get('path'):
                        old_p = Path(shot['best_candidate']['path'])
                        if old_p.exists() and old_p.resolve() != output_path.resolve():
                            old_p.unlink(missing_ok=True)
                    
                    cand_bak = CONFIG.work_dir / f"protected_cand_{index:03d}{output_path.suffix}"
                    shutil.copy(output_path, cand_bak)
                    shot['best_candidate'] = {
                        "shot": shot, "path": str(cand_bak), "source": src_name,
                        "score": score, "start": start, "duration": dur
                    }

                if accepted:
                    log(f"🎯 المشهد {index}: قُبِل من {src_name} ({cat}) | تقييم: {score:.2f} | {reason[:80]}")
                    selected_path = CONFIG.work_dir / f"selected_shot_{index:03d}{output_path.suffix}"
                    if selected_path.exists(): selected_path.unlink(missing_ok=True)
                    shutil.move(str(output_path), str(selected_path))

                    res_item = {
                        "shot": shot, "path": str(selected_path), "source": src_name,
                        "score": score, "start": start, "duration": dur
                    }
                    QUERY_ENGINE.record_success(query, cat)
                    cleanup_shot_unused_files(index, keep_path=selected_path)

                    async with completed_lock:
                        if shot['status'] != 'DONE':
                            shot['status'] = 'DONE'
                            if media_uid:
                                with CONFIG.used_media_lock: CONFIG.used_media_ids.add(media_uid)
                            completed_results.append(res_item)
                            log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                            if len(completed_results) == total_shots: completion_event.set()

                    found_acceptable = True
                    break
                else:
                    log(f"⏩ المشهد {index}: رُفض من {src_name} (تقييم: {score:.2f}) | {reason[:80]}")
                    QUERY_ENGINE.record_failure(query, src_name)
                    if output_path.exists() and output_path != Path(shot.get('best_candidate', {}).get('path', '')):
                        output_path.unlink(missing_ok=True)

            if not found_acceptable:
                shot['attempts'] += 1

                # Progressive acceptance: ONLY if NOT already DONE
                if shot['status'] != 'DONE' and shot['attempts'] >= 7 and shot['best_score'] >= 0.25 and shot['best_candidate']:
                    best_used = shot['best_candidate']
                    cand_file = Path(best_used['path'])
                    if cand_file.exists():
                        selected_path = CONFIG.work_dir / f"selected_shot_{index:03d}{cand_file.suffix}"
                        shutil.move(str(cand_file), str(selected_path))
                        best_used['path'] = str(selected_path)

                        log(f"✅ المشهد {index}: قبول تدريجي لأفضل نتيجة حقيقية (تقييم: {shot['best_score']:.2f}) بعد {shot['attempts']} محاولات.", "info")
                        cleanup_shot_unused_files(index, keep_path=selected_path)

                        async with completed_lock:
                            if shot['status'] != 'DONE':
                                shot['status'] = 'DONE'
                                completed_results.append(best_used)
                                log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                                if len(completed_results) == total_shots: completion_event.set()
                        break

        # Final Fallback: ONLY if NOT already DONE
        if shot['status'] != 'DONE':
            log(f"⚠️ المشهد {index} استنفد {MAX_ATTEMPTS_PER_SHOT} محاولات. حسم عبر خطة الإنقاذ...", "warning")
            fallback_res = await apply_fallback(shot, story)
            cleanup_shot_unused_files(index, keep_path=fallback_res.get('path'))
            async with completed_lock:
                if shot['status'] != 'DONE':
                    shot['status'] = 'DONE'
                    completed_results.append(fallback_res)
                    log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                    if len(completed_results) == total_shots: completion_event.set()

        FAILURE_DIAGNOSTICS.clear_shot(shot.get("index", 0))

    async def throttled_process(shot):
        async with shot_semaphore:
            await process_shot(shot)

    tasks = [asyncio.create_task(throttled_process(shot)) for shot in shots]
    await asyncio.gather(*tasks)
    if not completion_event.is_set(): completion_event.set()
    gc.collect()

    # Deduplicate results by shot index to ensure strictly 1 render per shot
    final_dict = {}
    for r in completed_results:
        final_dict[r["shot"]["index"]] = r
    return [final_dict[s["index"]] for s in shots if s["index"] in final_dict]


# =============================================================================
# ASSEMBLY ENGINE (ZERO-CRASH RENDERING PIPELINE)
# =============================================================================

class AssemblyEngine:
    def render_sub_clip(self, item):
        shot, index = item["shot"], item["shot"]["index"]
        media_path = Path(item["path"])
        output = CONFIG.work_dir / f"rendered_{index:03d}.mp4"
        dur = float(shot.get("duration", 3))

        # SAFEGUARD: If media file went missing, dynamically generate a replacement
        if not media_path.exists() or media_path.stat().st_size < 1024:
            log(f"⚠️ تنبيه: الملف المخصص للمشهد {index} غير موجود، جاري إنشاء بديل فوري...", "warning")
            asyncio.run(create_fallback_visual(output))
            return output

        start = min(float(item.get("start", 0)), max(0, probe_duration(media_path) - 0.1))
        log(f"✂️ جاري رندرة المشهد {index}...", "debug")

        if media_path.suffix.lower() in (".mp4", ".mov"):
            filter_complex = build_blur_background_filter_video()
            res = run_cmd([
                "ffmpeg", "-y", "-ss", str(start), "-i", str(media_path), "-t", str(dur),
                "-filter_complex", filter_complex, "-an", "-c:v", "libx264", "-preset", "fast",
                "-crf", "20", "-pix_fmt", "yuv420p", str(output)
            ])
        else:
            filter_complex = build_blur_background_filter_image(ken_burns=True)
            res = run_cmd([
                "ffmpeg", "-y", "-loop", "1", "-i", str(media_path), "-t", str(dur),
                "-filter_complex", filter_complex, "-an", "-c:v", "libx264", "-preset", "fast",
                "-crf", "20", "-pix_fmt", "yuv420p", str(output)
            ])

        # Bulletproof fallback with force_divisible_by=2 to avoid odd-pixel crashes
        if res.returncode != 0:
            log(f"⚠️ فشل الفلتر المعقد للمشهد {index}، محاولة الفلتر الآمن...", "warning")
            vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,fps={TARGET_FPS}"
            if media_path.suffix.lower() in (".mp4", ".mov"):
                res = run_cmd(["ffmpeg", "-y", "-ss", str(start), "-i", str(media_path), "-t", str(dur), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)])
            else:
                res = run_cmd(["ffmpeg", "-y", "-loop", "1", "-i", str(media_path), "-t", str(dur), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)])

        # Ultimate fallback if safe filter also fails
        if res.returncode != 0:
            log(f"🚨 خطأ رندرة غير متوقع للمشهد {index}، توليد لقطة طوارئ...", "error")
            asyncio.run(create_fallback_visual(output))

        # Cleanup source file immediately to save runner disk space
        if media_path.exists() and media_path.resolve() != output.resolve():
            try:
                if CONFIG.work_dir.resolve() in media_path.resolve().parents:
                    media_path.unlink(missing_ok=True)
            except: pass
        return output

    def render_batch(self, items, batch_num, total_batches):
        log(f"🎬 رندرة الدفعة {batch_num}/{total_batches} ({len(items)} مشهد)...", "info")
        rendered = [self.render_sub_clip(item) for item in items]
        gc.collect()
        return rendered

    def assemble_final_cut(self, rendered_items, subtitle_path, intro_path, chapter_timeline, hashtag):
        log("🎞️ تجهيز المونتاج النهائي التلفزيوني (دمج الإنترو، الفواصل السينمائية، الشعار، والهاشتاق)...", "info")

        normalized_intro = None
        intro_dur = 0.0
        if intro_path and Path(intro_path).exists():
            intro_dur = probe_duration(intro_path)
            if intro_dur > 0:
                normalized_intro = CONFIG.work_dir / "normalized_intro.mp4"
                log(f"🎬 تطبيع الإنترو ({intro_dur:.1f} ثانية) ليتطابق مع مواصفات البث...", "info")
                run_cmd([
                    "ffmpeg", "-y", "-i", str(intro_path),
                    "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,fps={TARGET_FPS}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2", str(normalized_intro)
                ])

        final_video_sequence = []
        final_audio_segments = []
        youtube_chapters = []
        current_time = 0.0

        chapter_shots = defaultdict(list)
        for item in rendered_items:
            ch_num = item["shot"].get("chapter_num", 1)
            chapter_shots[ch_num].append(item)

        intro_inserted = False
        intro_start_time = 0.0
        intro_end_time = 0.0

        for ch_info in chapter_timeline:
            ch_num = ch_info["part_idx"]
            ch_title = ch_info["title"]
            is_hook = ch_info["is_hook"]

            time_str = f"{int(current_time//60):02d}:{int(current_time%60):02d}"
            youtube_chapters.append(f"{time_str} {ch_title}")

            # Insert channel intro directly after chapter 1 (the hook)
            if not is_hook and not intro_inserted and normalized_intro and normalized_intro.exists():
                intro_start_time = current_time
                final_video_sequence.append(str(normalized_intro))
                intro_audio = CONFIG.work_dir / "intro_audio.wav"
                run_cmd(["ffmpeg", "-y", "-i", str(normalized_intro), "-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(intro_audio)])
                final_audio_segments.append(str(intro_audio))
                current_time += intro_dur
                intro_end_time = current_time
                intro_inserted = True
                log(f"🎬 أُدرج الإنترو من {intro_start_time:.1f}s إلى {intro_end_time:.1f}s.", "info")

            # Insert episodic title transition card between chapters
            if ch_num >= 2:
                trans_card = CONFIG.work_dir / f"trans_card_ch_{ch_num:02d}.mp4"
                created_card = generate_chapter_transition_card(ch_num, ch_title, trans_card, CONFIG.chapter_sfx_path, duration=2.2)
                if created_card:
                    final_video_sequence.append(str(trans_card))
                    card_audio = CONFIG.work_dir / f"card_audio_ch_{ch_num:02d}.wav"
                    run_cmd(["ffmpeg", "-y", "-i", str(trans_card), "-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(card_audio)])
                    final_audio_segments.append(str(card_audio))
                    current_time += 2.2

            # Append rendered video clips of this chapter
            items = chapter_shots.get(ch_num, [])
            for it in items:
                v_path = CONFIG.work_dir / f"rendered_{it['shot']['index']:03d}.mp4"
                if v_path.exists():
                    final_video_sequence.append(str(v_path))
                    current_time += it['shot']['duration']

            # Append normalized narration audio of this chapter
            ch_narration = CONFIG.work_dir / f"chapter_{ch_num:02d}.wav"
            if ch_narration.exists():
                norm_audio = CONFIG.work_dir / f"norm_audio_{ch_num:02d}.wav"
                run_cmd(["ffmpeg", "-y", "-i", str(ch_narration), "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(norm_audio)])
                final_audio_segments.append(str(norm_audio))

        v_concat_txt = CONFIG.work_dir / "final_v_concat.txt"
        with open(v_concat_txt, "w") as f:
            for vp in final_video_sequence:
                f.write(f"file '{Path(vp).resolve()}'\n")

        a_concat_txt = CONFIG.work_dir / "final_a_concat.txt"
        with open(a_concat_txt, "w") as f:
            for ap in final_audio_segments:
                f.write(f"file '{Path(ap).resolve()}'\n")

        merged_audio = CONFIG.work_dir / "master_soundtrack.wav"
        run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(a_concat_txt), "-c:a", "pcm_s16le", str(merged_audio)])

        intro_mask = f"not(between(t,{intro_start_time:.2f},{intro_end_time:.2f}))" if intro_end_time > 0 else "1"
        safe_hash = hashtag.replace("'", "").strip()
        sub_filter = "subtitles=" + str(Path(subtitle_path).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

        filter_complex_parts = [f"[0:v]{sub_filter}[v_sub]"]
        has_logo = CONFIG.logo_path and CONFIG.logo_path.exists()
        current_v = "[v_sub]"

        if has_logo:
            filter_complex_parts.append(f"[2:v]scale=180:-1[logo_scaled]")
            filter_complex_parts.append(f"{current_v}[logo_scaled]overlay=W-w-50:50:enable='{intro_mask}':format=auto[v_logo]")
            current_v = "[v_logo]"

        filter_complex_parts.append(
            f"{current_v}drawtext=font='Noto Sans Arabic':text='{safe_hash}':"
            f"x=50:y=55:fontsize=36:fontcolor=white@0.85:shadowcolor=black@0.7:shadowx=2:shadowy=2:"
            f"enable='{intro_mask}'[v_final]"
        )

        full_vf = ";".join(filter_complex_parts)

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(v_concat_txt),
            "-i", str(merged_audio)
        ]
        if has_logo: cmd.extend(["-i", str(CONFIG.logo_path)])

        cmd.extend([
            "-filter_complex", full_vf,
            "-map", "[v_final]", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k",
            "-shortest", str(CONFIG.final_video)
        ])

        res = run_cmd(cmd, timeout=3600)
        if res.returncode != 0:
            log(f"⚠️ الانتقال إلى التجميع المباشر السريع: {res.stderr[-250:]}", "warning")
            run_cmd([
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(v_concat_txt),
                "-i", str(merged_audio), "-vf", sub_filter,
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k", "-shortest", str(CONFIG.final_video)
            ], timeout=3600)

        if not is_valid_media(CONFIG.final_video):
            raise RuntimeError("Final assembly failed.")

        desc_text = f"وثائقي استقصائي شامل: {CONFIG.topic}\n\nفصول الوثائقي:\n" + "\n".join(youtube_chapters) + f"\n\n{safe_hash}"
        with open(CONFIG.description_file, "w", encoding="utf-8") as f:
            f.write(desc_text)

        log(f"🎉 تم إنتاج الوثائقي التلفزيوني بنجاح! | المدة: {probe_duration(CONFIG.final_video)/60:.2f} دقيقة | الحجم: {CONFIG.final_video.stat().st_size/1024/1024:.1f} MB", "info")
        return CONFIG.final_video, desc_text


class GoogleUploader:
    def __init__(self, cid, csec, ref, drive_folder_id):
        self.drive_folder_id = drive_folder_id
        self.creds = Credentials(None, refresh_token=ref, token_uri="https://oauth2.googleapis.com/token", client_id=cid, client_secret=csec) if cid and csec and ref else None

    def upload_all(self, vid_path, thumb_path, title, description=""):
        if not self.creds: return
        try:
            drive = build('drive', 'v3', credentials=self.creds, cache_discovery=False)
            body = {'name': f"{title}.mp4"}
            if self.drive_folder_id:
                body['parents'] = [self.drive_folder_id]

            df = drive.files().create(
                body=body,
                media_body=MediaFileUpload(str(vid_path), mimetype='video/mp4', resumable=True),
                fields='id, webViewLink'
            ).execute()
            log(f"✅ Google Drive: تم الرفع بنجاح إلى المجلد المحدد! الرابط: https://drive.google.com/file/d/{df.get('id')}/view", "info")

            yt = build('youtube', 'v3', credentials=self.creds, cache_discovery=False)
            yt_body = {
                'snippet': {
                    'title': title,
                    'description': description or f"وثائقي: {title}\nإنتاج تلقائي.",
                    'tags': ['وثائقي', 'جريمة', 'غموض', 'تحقيق'],
                    'categoryId': '24'
                },
                'status': {'privacyStatus': 'private'}
            }
            res = yt.videos().insert(
                part=','.join(yt_body.keys()),
                body=yt_body,
                media_body=MediaFileUpload(str(vid_path), mimetype='video/mp4', resumable=True)
            ).execute()
            vid_id = res.get('id')
            log(f"✅ YouTube: تم الرفع مع الفصول التلقائية! https://youtu.be/{vid_id}", "info")

            if thumb_path.exists() and thumb_path.stat().st_size > 1024:
                try:
                    yt.thumbnails().set(videoId=vid_id, media_body=MediaFileUpload(str(thumb_path), mimetype='image/jpeg')).execute()
                    log("✅ تم رفع الصورة المصغرة لليوتيوب بنجاح.", "info")
                except Exception as thumb_err:
                    log(f"⚠️ فشل رفع الصورة المصغرة: {thumb_err}", "warning")
        except Exception as e:
            log(f"❌ فشل الرفع السحابي: {e}", "error")


async def main_pipeline():
    prepare_fresh_workspace()
    log(f"🚀 بدء تشغيل المحرك التلفزيوني {ENGINE_VERSION} | القضية: {CONFIG.topic}")

    story_engine = StoryScoutEngine()
    story = story_engine.inspect_and_plan()

    audio_studio = MasterAudioStudio()
    master_audio, part_wav_files = audio_studio.produce_master_track(story)

    shots, chapter_timeline = WordSyncSlicer().align_and_slice(part_wav_files, story)
    shots = story_engine.direct_storyboard(shots)

    sub_path = CONFIG.work_dir / "subtitles.ass"
    with open(sub_path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Noto Sans Arabic,54,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,65,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for s in shots:
            h1, m1 = int(s['start']//3600), int((s['start']%3600)//60)
            h2, m2 = int(s['end']//3600), int((s['end']%3600)//60)
            t = s['text'].replace("\\", r"\\")
            f.write(f"Dialogue: 0,{h1}:{m1:02d}:{s['start']%60:05.2f},{h2}:{m2:02d}:{s['end']%60:05.2f},Default,,0,0,0,,{{\\fad(120,120)}}{t}\n")

    assembly = AssemblyEngine()
    all_rendered = []
    media_results = []

    total_batches = max(1, (len(shots) + RENDER_BATCH_SIZE - 1) // RENDER_BATCH_SIZE)
    for batch_idx in range(total_batches):
        start = batch_idx * RENDER_BATCH_SIZE
        end = min(start + RENDER_BATCH_SIZE, len(shots))

        batch_shots = shots[start:end]
        batch_items = await run_pipelined_production(batch_shots, story)
        media_results.extend(batch_items)

        batch_rendered = assembly.render_batch(batch_items, batch_idx + 1, total_batches)
        all_rendered.extend(batch_rendered)

        for item in batch_items:
            try:
                raw_path = item.get("path")
                if raw_path and os.path.exists(raw_path):
                    os.remove(raw_path)
            except Exception: pass

    rendered_shot_items = []
    for item, r_path in zip(media_results, all_rendered):
        rendered_shot_items.append({"shot": item["shot"], "path": r_path})

    hashtag = story.get("hashtag", f"#{CONFIG.topic_clean[:25]}")
    final_video, desc_text = assembly.assemble_final_cut(rendered_shot_items, sub_path, CONFIG.intro_path, chapter_timeline, hashtag)

    log("🎨 توليد الصورة المصغرة (Thumbnail) الاحترافية...", "info")
    await generate_ai_image(story.get('primary_english_query', CONFIG.topic), CONFIG.thumbnail, "16:9")

    uploader = GoogleUploader(CONFIG.google_client_id, CONFIG.google_client_secret, CONFIG.google_refresh_token, CONFIG.drive_folder_id)
    await asyncio.to_thread(uploader.upload_all, final_video, CONFIG.thumbnail, CONFIG.topic_clean, desc_text)

    log(f"\n{'='*60}\n🏁 اكتمل إنتاج الوثائقي التلفزيوني بنجاح واحترافية متكاملة وبلا أي أخطاء.\n{'='*60}\n", "info")
    PARALLEL_FETCHER.shutdown()
    gc.collect()


if __name__ == "__main__":
    try:
        asyncio.run(main_pipeline())
    except KeyboardInterrupt:
        log("🛑 تم الإيقاف يدوياً.", "warning")
        sys.exit(0)
