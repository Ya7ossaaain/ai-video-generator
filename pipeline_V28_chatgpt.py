#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
V28.1 - MEDIA-FIRST + REMOTION (FIXED)

FIXES vs V28.0:
  [FIX-1] Real Media-First: VerifiedMediaPool is consumed BEFORE network fetch
  [FIX-2] Removed dead safe_async_run
  [FIX-3] Remotion calls are fully async via asyncio.to_thread
  [FIX-4] _locate_asset returns None safely (no phantom paths)
  [FIX-5] REVIEWER_SEMAPHORE created inside main_pipeline (loop-safe)
  [FIX-6] MediaPoolBuilder retries failed angles once
  [FIX-7] Remotion 4.x CLI compatible (--codec h264)
  [FIX-8] Pool items claimed atomically (no double-use)
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
import gc
import unicodedata

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

ENGINE_VERSION = "V28.1-MEDIA-FIRST-REMOTION-FIXED"

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
MAX_ATTEMPTS_PER_SHOT = 15
REVIEWER_MAX_RETRIES = 2          # => 3 total attempts
POOL_ATTEMPTS_PER_SHOT = 3        # how many pool items to try before network

PREFILTER_MIN_SIZE_BYTES = 5 * 1024
PREFILTER_MIN_VIDEO_DURATION = 0.5

TARGET_TOTAL_DURATION_MINUTES = 25
TARGET_NARRATION_WORDS = 3500
SCENE_DURATION_MIN = 2.0
SCENE_DURATION_MAX = 5.0
SCENE_DURATION_MIN_HOOK = 1.3
SCENE_DURATION_MAX_HOOK = 2.0
RENDER_BATCH_SIZE = 40

EFFORT_REVIEWER = "low"
EFFORT_PRO_GENERATION = "high"
EFFORT_IMAGE_GEN = "medium"

BRAND_COLORS = {
    "primary": "#C47A1A",
    "secondary": "#FFFFFF",
    "dark": "#0A0C10",
    "accent": "#D4891A",
}

WIKI_HEADERS = {
    "User-Agent": "InvestigativeDocEngine/7.1 (https://github.com/Ya7ossaaain; bot@archive-doc.org) python-requests/2.31",
    "Accept": "application/json"
}

MEDIA_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

ARCHIVE_SOURCES = ["WIKIPEDIA", "FBI_ARCHIVE", "OPENVERSE", "LOC"]
CINEMATIC_SOURCES = ["PEXELS", "PIXABAY"]

SOURCE_AFFINITY = {
    "ARCHIVE": {
        "person_mugshot": ["WIKIPEDIA", "OPENVERSE", "FBI_ARCHIVE", "LOC"],
        "document_file": ["WIKIPEDIA", "FBI_ARCHIVE", "LOC", "OPENVERSE"],
        "historic_interview": ["FBI_ARCHIVE", "WIKIPEDIA", "OPENVERSE"],
        "location_photo": ["WIKIPEDIA", "OPENVERSE", "LOC", "FBI_ARCHIVE"],
        "historical_event": ["WIKIPEDIA", "FBI_ARCHIVE", "OPENVERSE", "LOC"],
        "newspaper_article": ["LOC", "WIKIPEDIA", "FBI_ARCHIVE", "OPENVERSE"],
        "default": ["WIKIPEDIA", "FBI_ARCHIVE", "OPENVERSE", "LOC"],
    },
    "CINEMATIC": {
        "nature_water": ["PEXELS", "PIXABAY"],
        "dark_moody": ["PEXELS", "PIXABAY"],
        "people_action": ["PEXELS", "PIXABAY"],
        "objects_closeup": ["PIXABAY", "PEXELS"],
        "urban_night": ["PEXELS", "PIXABAY"],
        "default": ["PEXELS", "PIXABAY"],
    }
}


# =============================================================================
# LOGGER
# =============================================================================

class ProTelemetryFormatter(logging.Formatter):
    def format(self, record):
        now = datetime.now().strftime("%H:%M:%S")
        return f"{now} | [{record.levelname}] | {record.getMessage()}"

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


# =============================================================================
# CONFIG
# =============================================================================

class EngineConfig:
    def __init__(self):
        self.topic = os.environ.get("VIDEO_TOPIC", "لغز اختفاء طائرة دي بي كوبر").strip()
        self.topic_clean = re.sub(r'[\\/*?:"<>|]', "", self.topic).strip() or "documentary"
        self.run_id = f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(10000, 99999)}"
        self.base_dir = Path("./output_build")
        self.work_dir = self.base_dir / "workspace"
        self.final_video = self.base_dir / "final_documentary.mp4"
        self.master_audio = self.work_dir / "master_audio.wav"
        self.thumbnail = self.base_dir / "thumbnail.jpg"
        self.description_file = self.base_dir / "description.txt"

        # [FIX-4] _locate_asset now returns Optional[Path]
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
        self.openverse_client_id = os.environ.get("OPENVERSE_CLIENT_ID", "")
        self.openverse_client_secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "")
        self.openverse_token = None
        self.openverse_token_lock = threading.Lock()
        self.google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        self.google_refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")

        self.remotion_project_dir = Path("./remotion-documentary")

    @staticmethod
    def _locate_asset(candidate_paths):
        """Return first existing asset or None (no phantom paths)."""
        for p in candidate_paths:
            path_obj = Path(p)
            if path_obj.exists() and path_obj.stat().st_size > 1024:
                return path_obj
        return None

CONFIG = EngineConfig()


def prepare_fresh_workspace():
    log("🧹 تنظيف وتجهيز بيئة التشغيل بالكامل...")
    if CONFIG.base_dir.exists():
        shutil.rmtree(CONFIG.base_dir, ignore_errors=True)
    CONFIG.base_dir.mkdir(parents=True, exist_ok=True)
    CONFIG.work_dir.mkdir(parents=True, exist_ok=True)
    CONFIG.used_media_ids.clear()


# =============================================================================
# KEY POOL
# =============================================================================

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


# =============================================================================
# HELPERS
# =============================================================================

def probe_duration(path):
    if not path or not os.path.exists(path): return 0.0
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                             stdout=subprocess.PIPE, text=True, timeout=30)
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
        if len(parts) == 2: return int(parts[0]), int(parts[1])
    except: pass
    return 0, 0


def is_valid_media(path, min_duration=0.05):
    path = Path(path)
    return path.exists() and path.stat().st_size >= 1024 and probe_duration(path) >= min_duration

def is_valid_visual(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size < 1024: return False
    w, h = probe_dimensions(path)
    return w > 0 and h > 0

def clean_query(text):
    clean = re.sub(r"\s+", " ", re.sub(r"[^\x00-\x7F]+", " ", text or "")).strip()
    words = clean.split()
    fluff = {"investigation", "classified", "memorandum", "official", "diagram", "report", "case", "file"}
    distilled = [w for w in words if w.lower() not in fluff]
    if not distilled: distilled = words
    return " ".join(distilled[:3])[:60]

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

def find_system_arabic_font():
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/noto-cjk/NotoSansArabic-Regular.ttf"
    ]
    for c in candidates:
        if Path(c).exists(): return c
    return None

def cleanup_shot_unused_files(index, keep_path=None):
    try:
        keep_resolved = Path(keep_path).resolve() if keep_path else None
        for p in CONFIG.work_dir.glob(f"*shot_{index:03d}*"):
            if keep_resolved and p.resolve() == keep_resolved: continue
            if p.name.startswith("selected_") or p.name.startswith("rendered_"): continue
            p.unlink(missing_ok=True)
    except Exception: pass


# =============================================================================
# FFMPEG FILTERS
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
        f"vignette,noise=alls=3:allf=t,fps={TARGET_FPS}"
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
        f"vignette,noise=alls=3:allf=t,fps={TARGET_FPS}"
    )


# =============================================================================
# SMART QUERY ENGINE
# =============================================================================

class SmartQueryEngine:
    def __init__(self):
        self.failed_queries = defaultdict(set)
        self.lock = threading.Lock()

    def get_ordered_sources(self, shot):
        cat = shot.get("category", "ARCHIVE")
        content_type = shot.get("content_type", "default")
        if cat == "ARCHIVE":
            ordered = SOURCE_AFFINITY["ARCHIVE"].get(content_type, ARCHIVE_SOURCES)
        else:
            ordered = SOURCE_AFFINITY["CINEMATIC"].get(content_type, CINEMATIC_SOURCES)
        return [s for s in ordered if self._source_available(s)]

    def _source_available(self, source):
        if source == "PEXELS": return bool(CONFIG.pexels_key)
        if source == "PIXABAY": return bool(CONFIG.pixabay_key)
        if source == "OPENVERSE": return bool(CONFIG.openverse_client_id and CONFIG.openverse_client_secret)
        return True

    def generate_query_tiers(self, shot, attempt_num=0):
        cat = shot.get("category", "ARCHIVE")
        entities = [clean_query(e) for e in shot.get("exact_entities", []) if clean_query(e)]
        vibes = [clean_query(v) for v in shot.get("visual_vibes", []) if clean_query(v)]
        filtered_sources = self.get_ordered_sources(shot)

        topic_words = clean_query(shot.get("topic_anchor", CONFIG.topic)).split()[:2]
        topic_anchor = " ".join(topic_words) if topic_words else "investigation"

        queries = []
        n_sources = len(filtered_sources)
        src = filtered_sources[attempt_num % n_sources]

        if cat == "ARCHIVE":
            sub_entity = entities[attempt_num % len(entities)] if entities else "evidence"
            sub_clean = " ".join(sub_entity.split()[:2])
            anchored_query = sub_clean if topic_anchor.lower() in sub_clean.lower() else f"{topic_anchor} {sub_clean}"

            if attempt_num == 0:
                queries.append((topic_anchor, "WIKIPEDIA"))
                queries.append((anchored_query, src))
            elif attempt_num <= 4:
                queries.append((anchored_query, src))
                queries.append((topic_anchor, "WIKIPEDIA"))
            elif attempt_num <= 8:
                queries.append((anchored_query, "FBI_ARCHIVE"))
                queries.append((topic_anchor, "WIKIPEDIA"))
            elif attempt_num <= 11:
                queries.append((f'"{topic_anchor}"', "LOC"))
                queries.append((anchored_query, "OPENVERSE"))
            else:
                queries.append((topic_anchor, "WIKIPEDIA"))
                queries.append(("police investigation night", "PEXELS"))
        else:
            if attempt_num < len(vibes):
                queries.append((vibes[attempt_num], src))
            else:
                ageless_fallbacks = [
                    "police flashing lights reflection wet night",
                    "fountain pen writing paper macro",
                    "ticking clock hands macro shadows",
                    "dark foggy street lamp night"
                ]
                queries.append((ageless_fallbacks[attempt_num % len(ageless_fallbacks)], src))

        valid_pairs, seen = [], set()
        with self.lock:
            for q, s in queries:
                q_clean = clean_query(q)
                if not q_clean or len(q_clean) < 3: continue
                key = f"{s}:{q_clean.lower()}"
                if key not in self.failed_queries.get(s, set()) and key not in seen:
                    valid_pairs.append((q_clean, s))
                    seen.add(key)

        if not valid_pairs:
            valid_pairs.append((topic_anchor, filtered_sources[attempt_num % n_sources]))
        return valid_pairs

    def record_failure(self, query, source):
        with self.lock:
            self.failed_queries[source].add(f"{source}:{query.lower().strip()}")

QUERY_ENGINE = SmartQueryEngine()


# =============================================================================
# MEDIA PRE-FILTER
# =============================================================================

class MediaPreFilter:
    @staticmethod
    def quick_validate(media_path, shot):
        if not media_path or not Path(media_path).exists():
            return False, "الملف غير موجود"
        path = Path(media_path)
        file_size = path.stat().st_size
        if file_size < PREFILTER_MIN_SIZE_BYTES:
            return False, f"حجم الملف صغير جداً ({file_size} bytes)"

        is_img = path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
        is_vid = path.suffix.lower() in (".mp4", ".mov")

        w, h = probe_dimensions(path)
        if is_vid and w > 0 and h > 0:
            if w < h or (w / h) < 1.15:
                return False, f"فيديو رأسي غير متوافق مع الشاشة العريضة 16:9 ({w}x{h})"

        if is_img:
            if not is_valid_visual(path): return False, "الصورة تالفة أو غير صالحة"
        elif is_vid:
            duration = probe_duration(path)
            if duration < PREFILTER_MIN_VIDEO_DURATION: return False, f"مدة الفيديو قصيرة جداً ({duration:.1f}s)"
            if not is_valid_media(path): return False, "الفيديو تالف"
        else:
            return False, f"نوع ملف غير مدعوم: {path.suffix}"
        return True, "ok"


# =============================================================================
# [FIX-1] VERIFIED MEDIA POOL (REAL MEDIA-FIRST)
# =============================================================================

class VerifiedMediaPool:
    """Thread-safe pool of pre-verified media, consumed BEFORE network fetch.

    [FIX-1] This is what makes V28.1 truly Media-First. Each shot first tries
    to claim a matching item from the pool. Only if the pool is exhausted (or
    no suitable match) does the shot fall back to network fetching.
    """

    def __init__(self):
        self.items = []
        self.claimed_paths = set()
        self.lock = threading.Lock()
        self.stats = {"total": 0, "claimed": 0, "missed": 0}

    def load(self, media_list):
        with self.lock:
            self.items = list(media_list)
            self.claimed_paths = set()
            self.stats = {"total": len(self.items), "claimed": 0, "missed": 0}
            log(f"📦 [VerifiedMediaPool] تم تحميل {len(self.items)} وسيطة مؤكدة في المجمع.")

    def try_claim_for_shot(self, shot):
        """Return the best-matching unclaimed pool item for this shot, or None.
        Matching priority:
            1. category + content_type exact match
            2. category match only
            3. any unclaimed
        """
        shot_cat = shot.get("category", "ARCHIVE")
        shot_ct = shot.get("content_type", "default")

        with self.lock:
            def eligible(m):
                return m["path"] not in self.claimed_paths

            # Priority 1: exact cat + ct
            cands = [m for m in self.items if eligible(m)
                     and m["category"] == shot_cat and m["content_type"] == shot_ct]
            # Priority 2: same cat
            if not cands:
                cands = [m for m in self.items if eligible(m) and m["category"] == shot_cat]
            # Priority 3: any
            if not cands:
                cands = [m for m in self.items if eligible(m)]

            if not cands:
                self.stats["missed"] += 1
                return None

            # Prefer higher score, then older (to keep pool fresh)
            cands.sort(key=lambda m: (-m.get("score", 0), m.get("angle_id", 0)))
            chosen = cands[0]
            self.claimed_paths.add(chosen["path"])
            self.stats["claimed"] += 1
            return dict(chosen)

    def summary(self):
        with self.lock:
            return dict(self.stats)

VERIFIED_MEDIA_POOL = VerifiedMediaPool()


# =============================================================================
# PARALLEL SOURCE FETCHER
# =============================================================================

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
            if source_name == "WIKIPEDIA":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_wikipedia_anchored, query, image_path)
            elif source_name == "FBI_ARCHIVE":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_fbi_archive, query, Path(f"{base_path}_{source_name}"))
            elif source_name == "PEXELS":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_pexels_video, query, video_path)
            elif source_name == "PIXABAY":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_pixabay_video, query, video_path)
            elif source_name == "LOC":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_chronicling_america, query, image_path)
            elif source_name == "OPENVERSE":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_openverse, query, image_path, shot)
            return (found_file, media_uid, source_name, query)
        except Exception as e:
            log(f"⚠️ خطأ جلب {source_name} للمشهد {index}: {e}", "warning")
            return (None, None, source_name, query)

    def shutdown(self):
        self.executor.shutdown(wait=False)

PARALLEL_FETCHER = ParallelSourceFetcher()


# =============================================================================
# MEDIA SOURCES
# =============================================================================

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
                r = requests.get(url, headers=MEDIA_DOWNLOAD_HEADERS, stream=True, timeout=20)
                if r.status_code == 200:
                    with open(output, "wb") as f:
                        for chunk in r.iter_content(1024*256):
                            if chunk: f.write(chunk)
                    return str(output), uid
            except: pass
        return None, None

    @staticmethod
    def fetch_wikipedia_anchored(q, output_path):
        q_clean = clean_query(q)
        if not q_clean or len(q_clean) < 3: return None, None

        try:
            wiki_api = "https://en.wikipedia.org/w/api.php"
            params = {"action": "query", "generator": "search", "gsrsearch": q_clean,
                      "gsrlimit": 8, "prop": "pageimages", "pithumbsize": 1080, "format": "json"}
            res = requests.get(wiki_api, headers=WIKI_HEADERS, params=params, timeout=12)
            if res.status_code == 200:
                pages = list(res.json().get("query", {}).get("pages", {}).values())
                def extract_page_thumb(p):
                    t = p.get("thumbnail", {}).get("source")
                    return (t, f"wiki_page_{p.get('pageid')}") if t else (None, None)
                saved, uid = MediaSources._track_and_save(pages, output_path, extract_page_thumb)
                if saved: return saved, uid
        except Exception: pass

        try:
            commons_url = "https://commons.wikimedia.org/w/api.php"
            params = {"action": "query", "generator": "search", "gsrsearch": q_clean,
                      "gsrlimit": 15, "prop": "imageinfo", "iiprop": "url|mime|size", "format": "json"}
            res = requests.get(commons_url, headers=WIKI_HEADERS, params=params, timeout=12)
            if res.status_code == 200:
                pages = list(res.json().get("query", {}).get("pages", {}).values())
                def extract_commons(p):
                    info_list = p.get("imageinfo") or [{}]
                    url = info_list[0].get("url")
                    mime = info_list[0].get("mime", "")
                    if url and ("image" in mime or url.lower().endswith((".jpg", ".jpeg", ".png"))):
                        return url, f"commons_{p.get('pageid')}"
                    return None, None
                saved, uid = MediaSources._track_and_save(pages, output_path, extract_commons)
                if saved: return saved, uid
        except Exception: pass
        return None, None

    @staticmethod
    def fetch_fbi_archive(q, base_path):
        try:
            q_clean = clean_query(q)
            if not q_clean or len(q_clean) < 3: return None, None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            query = f'({q_clean}) AND (mediatype:image OR mediatype:movies)'
            res = requests.get("https://archive.org/advancedsearch.php", headers=headers,
                               params={"q": query, "fl[]": "identifier", "rows": 15, "output": "json"}, timeout=18)
            docs = res.json().get("response", {}).get("docs", [])
            random.shuffle(docs)
            for doc in docs:
                uid = str(doc.get("identifier"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                try:
                    meta = requests.get(f"https://archive.org/metadata/{uid}", headers=headers, timeout=15).json()
                    files = meta.get("files", [])
                    videos = [(int(i.get("size",0) or 0), str(i.get("name",""))) for i in files
                              if str(i.get("name","")).lower().endswith((".mp4",".mov"))
                              and 500*1024 <= int(i.get("size",0) or 0) <= MAX_MEDIA_SIZE_MB*1024*1024]
                    images = [(int(i.get("size",0) or 0), str(i.get("name",""))) for i in files
                              if str(i.get("name","")).lower().endswith((".jpg",".jpeg",".png"))
                              and int(i.get("size",0) or 0) >= 15*1024]
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
                        r = requests.get(file_url, headers=MEDIA_DOWNLOAD_HEADERS, stream=True, timeout=25)
                        if r.status_code == 200:
                            with open(out_path, "wb") as f:
                                for chunk in r.iter_content(1024*256):
                                    if chunk: f.write(chunk)
                            return str(out_path), uid
                except: pass
        except: pass
        return None, None

    @staticmethod
    def fetch_pexels_video(q, o):
        if not CONFIG.pexels_key: return None, None
        try:
            headers = MEDIA_DOWNLOAD_HEADERS.copy()
            headers["Authorization"] = CONFIG.pexels_key
            res = requests.get("https://api.pexels.com/videos/search", headers=headers,
                               params={"query": q, "per_page": 8}, timeout=15).json().get("videos", [])
            return MediaSources._track_and_save(res, o, lambda i: (
                sorted(i.get("video_files", []), key=lambda x: abs((x.get("width") or 0)-TARGET_W))[0].get("link")
                if i.get("video_files") else None, str(i.get("id"))))
        except: return None, None

    @staticmethod
    def fetch_pixabay_video(q, o):
        if not CONFIG.pixabay_key: return None, None
        try:
            res = requests.get("https://pixabay.com/api/videos/", headers=MEDIA_DOWNLOAD_HEADERS,
                               params={"key": CONFIG.pixabay_key, "q": q, "per_page": 8}, timeout=15).json().get("hits", [])
            return MediaSources._track_and_save(res, o, lambda i: (
                (i.get("videos", {}).get("large") or i.get("videos", {}).get("medium", {})).get("url"),
                str(i.get("id"))))
        except: return None, None

    @staticmethod
    def fetch_chronicling_america(q, o):
        try:
            q_clean = clean_query(q)
            if not q_clean: return None, None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            url = f'https://www.loc.gov/photos/?fo=json&fa=online_format:image&c=15&q="{urllib.parse.quote(q_clean)}"'
            res = requests.get(url, headers=headers, timeout=15)
            results = res.json().get("results", [])
            def extract_loc(i):
                img_urls = i.get("image_url", [])
                if isinstance(img_urls, str): img_urls = [img_urls]
                return (img_urls[-1], str(i.get("id", img_urls[-1]))) if img_urls else (None, None)
            return MediaSources._track_and_save(results, o, extract_loc)
        except: return None, None

    @staticmethod
    def fetch_openverse(q, o, shot=None):
        token = get_openverse_token()
        if not token: return None, None
        try:
            q_clean = clean_query(q)
            if not q_clean or len(q_clean) < 3: return None, None
            headers = {"Authorization": f"Bearer {token}", "User-Agent": "InvestigativeDocEngine/7.1"}
            res = requests.get("https://api.openverse.org/v1/images/", headers=headers,
                               params={"q": q_clean, "page_size": 15, "license_type": "all-cc"}, timeout=15)
            if res.status_code == 200:
                results = res.json().get("results", [])
                return MediaSources._track_and_save(results, o,
                    lambda item: (item.get("url"), f"openverse_{item.get('id')}"))
        except: pass
        return None, None


def get_openverse_token():
    with CONFIG.openverse_token_lock:
        if CONFIG.openverse_token: return CONFIG.openverse_token
        if not CONFIG.openverse_client_id or not CONFIG.openverse_client_secret: return None
        try:
            resp = requests.post("https://api.openverse.org/v1/auth_tokens/token/", data={
                "client_id": CONFIG.openverse_client_id,
                "client_secret": CONFIG.openverse_client_secret,
                "grant_type": "client_credentials"
            }, timeout=15)
            if resp.status_code == 200:
                CONFIG.openverse_token = resp.json().get("access_token")
                return CONFIG.openverse_token
        except Exception: pass
        return None


# =============================================================================
# FALLBACK GENERATORS
# =============================================================================

def create_fallback_image(output_path):
    out_p = Path(output_path)
    res = run_cmd([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0a0c10:s=1280x720",
        "-vf", "noise=alls=15:allf=t+u,vignette=PI/4",
        "-frames:v", "1", "-pix_fmt", "yuvj420p", "-q:v", "2", str(out_p)
    ])
    return is_valid_visual(out_p)


async def generate_ai_image(prompt, output_path, aspect_ratio="16:9"):
    log(f"🎨 إنشاء صورة مصغرة عبر AGY: '{prompt[:70]}...'", "info")
    full_prompt = f"[CRITICAL: NO TEXT ON IMAGE. OUTPUT RAW IMAGE ONLY] Photorealistic cinematic documentary archive photo: {prompt}. Aspect Ratio: {aspect_ratio}"
    try:
        out_p = Path(output_path)
        if out_p.exists(): out_p.unlink()

        cmd_binary = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", EFFORT_IMAGE_GEN,
                      "--dangerously-skip-permissions", "-p", full_prompt]
        res_bin = await asyncio.to_thread(subprocess.run, cmd_binary,
                                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)

        raw_written = False
        if res_bin.stdout.startswith(b'\xff\xd8') or res_bin.stdout.startswith(b'\x89PNG'):
            with open(out_p, "wb") as f: f.write(res_bin.stdout)
            raw_written = True
        else:
            data = extract_json(res_bin.stdout.decode('utf-8', errors='ignore'))
            if data and isinstance(data, dict) and "image" in data:
                with open(out_p, "wb") as f: f.write(base64.b64decode(data["image"]))
                raw_written = True

        if raw_written and is_valid_visual(out_p):
            temp_out = out_p.with_suffix(".tmp.jpg")
            convert_res = run_cmd([
                "ffmpeg", "-y", "-i", str(out_p),
                "-vf", "scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:black",
                "-frames:v", "1", "-pix_fmt", "yuvj420p", "-q:v", "2", str(temp_out)
            ], timeout=30)
            if convert_res.returncode == 0 and temp_out.exists() and temp_out.stat().st_size > 1024:
                shutil.move(str(temp_out), str(out_p))
                return True
    except Exception as e:
        log(f"⚠️ فشل التوليد عبر AGY: {e}", "warning")
    return create_fallback_image(output_path)


async def create_fallback_visual(output, duration=3.0):
    res = await asyncio.to_thread(subprocess.run, [
        "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0a0a0a:s={TARGET_W}x{TARGET_H}:r={TARGET_FPS}",
        "-vf", "noise=alls=12:allf=t+u,vignette,eq=contrast=1.1:saturation=0.5",
        "-frames:v", str(int(duration * TARGET_FPS)),
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-pix_fmt", "yuv420p", str(output)
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return is_valid_media(output)


# =============================================================================
# [FIX-3] REMOTION BRIDGE (FULLY ASYNC)
# =============================================================================

class RemotionBridge:
    """Async bridge to Remotion renderer. [FIX-3] All subprocess calls use
    asyncio.to_thread so the event loop is not blocked during rendering."""

    def __init__(self):
        self.remotion_available = self._check_remotion()
        self._probe_logged = False

    def _check_remotion(self):
        if not CONFIG.remotion_project_dir.exists():
            log("⚠️ مجلد Remotion غير موجود، سيتم استخدام FFmpeg كبديل.", "warning")
            return False
        try:
            res = subprocess.run(["node", "--version"], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, timeout=10)
            if res.returncode != 0:
                log("⚠️ Node.js غير متوفر، سيتم استخدام FFmpeg كبديل.", "warning")
                return False
            node_modules = CONFIG.remotion_project_dir / "node_modules"
            if not node_modules.exists():
                log("⚠️ حزم npm غير مثبتة (node_modules مفقود)، سيتم استخدام FFmpeg كبديل.", "warning")
                return False
            entry = CONFIG.remotion_project_dir / "src" / "index.ts"
            if not entry.exists():
                entry = CONFIG.remotion_project_dir / "src" / "index.tsx"
                if not entry.exists():
                    log("⚠️ src/index.ts(x) مفقود في مشروع Remotion.", "warning")
                    return False
            log("✅ Remotion متوفر وجاهز للاستخدام.")
            return True
        except Exception as e:
            log(f"⚠️ فحص Remotion فشل: {e}", "warning")
            return False

    async def generate_chapter_transition(self, chapter_num, chapter_title, out_video_path, duration=2.2):
        if self.remotion_available:
            result = await self._render_remotion_scene(
                scene_type="chapter_transition",
                chapter_num=chapter_num, title=chapter_title,
                arabic_text="", duration=duration, output_path=out_video_path
            )
            if result: return result
        return self._ffmpeg_chapter_card(chapter_num, chapter_title, out_video_path, duration)

    async def generate_map_overlay(self, arabic_text, out_video_path, duration=3.0):
        if not self.remotion_available: return None
        return await self._render_remotion_scene(
            scene_type="map_overlay", chapter_num=0, title="",
            arabic_text=arabic_text, duration=duration, output_path=out_video_path
        )

    async def generate_timeline_card(self, title, arabic_text, out_video_path, duration=3.0):
        if not self.remotion_available: return None
        return await self._render_remotion_scene(
            scene_type="timeline_card", chapter_num=0, title=title,
            arabic_text=arabic_text, duration=duration, output_path=out_video_path
        )

    async def _render_remotion_scene(self, scene_type, chapter_num, title, arabic_text, duration, output_path):
        fps = TARGET_FPS
        duration_in_frames = int(round(duration * fps))

        payload = {
            "scenes": [{
                "type": scene_type,
                "chapterNum": chapter_num,
                "title": title,
                "arabicText": arabic_text,
                "durationInFrames": duration_in_frames,
            }],
            "brandColors": BRAND_COLORS,
        }

        payload_path = CONFIG.work_dir / f"remotion_payload_{scene_type}_{chapter_num}_{random.randint(1000,9999)}.json"
        with open(payload_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        output_path = Path(output_path)
        log(f"🎬 Remotion: رندرة {scene_type} (الفصل {chapter_num})...", "info")

        entry = "src/index.ts"
        if not (CONFIG.remotion_project_dir / entry).exists():
            entry = "src/index.tsx"

        try:
            # [FIX-7] Remotion 4.x CLI compatible
            cmd = [
                "npx", "remotion", "render",
                entry,
                "DocumentaryComposition",
                str(output_path.resolve()),
                f"--props={payload_path.resolve()}",
                "--codec", "h264",
            ]
            res = await asyncio.to_thread(
                subprocess.run, cmd,
                cwd=str(CONFIG.remotion_project_dir.resolve()),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300
            )
            if res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 1024:
                log(f"✅ Remotion: نجح رندرة {scene_type}", "info")
                payload_path.unlink(missing_ok=True)
                return str(output_path)
            else:
                log(f"⚠️ Remotion فشل ({res.returncode}): {res.stderr[:200]}", "warning")
        except Exception as e:
            log(f"⚠️ خطأ Remotion: {e}", "warning")

        payload_path.unlink(missing_ok=True)
        return None

    def _ffmpeg_chapter_card(self, chapter_num, chapter_title, out_video_path, duration=2.2):
        log(f"🎬 FFmpeg بديل: توليد الفاصل للفصل {chapter_num}: '{chapter_title}'...", "info")
        safe_title = chapter_title.replace("'", "").replace(":", "-").strip()
        font_file = find_system_arabic_font()

        draw_title = f"fontfile='{font_file}':" if font_file else ""
        primary_hex = BRAND_COLORS["primary"].lstrip("#")
        dark_hex = BRAND_COLORS["dark"].lstrip("#")
        vf_text = (
            f"color=c=0x{dark_hex}:s=1920x1080:d={duration}:r={TARGET_FPS},"
            f"noise=alls=10:allf=t+u,vignette=PI/4,"
            f"drawtext={draw_title}text='محور التحقيق 0{chapter_num}':"
            f"x=(w-text_w)/2:y=(h-text_h)/2-55:fontsize=32:fontcolor=0x{primary_hex}:alpha='if(lt(t,0.3),t/0.3,if(gt(t,{duration}-0.3),({duration}-t)/0.3,1))',"
            f"drawtext={draw_title}text='{safe_title}':"
            f"x=(w-text_w)/2:y=(h-text_h)/2+25:fontsize=56:fontcolor=white:shadowcolor=black@0.8:shadowx=3:shadowy=3:alpha='if(lt(t,0.3),t/0.3,if(gt(t,{duration}-0.3),({duration}-t)/0.3,1))'"
        )
        sfx_path = CONFIG.chapter_sfx_path
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", vf_text]
        if sfx_path and Path(sfx_path).exists() and Path(sfx_path).stat().st_size > 1024:
            cmd.extend(["-i", str(sfx_path), "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k", "-shortest"])
        else:
            synth_audio = f"sine=frequency=42:duration={duration},afade=t=out:st=0.8:d={duration-0.8},volume=2.2"
            cmd.extend(["-f", "lavfi", "-i", synth_audio, "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "192k"])

        total_frames = int(round(duration * TARGET_FPS))
        cmd.extend([
            "-frames:v", str(total_frames),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            str(out_video_path)
        ])
        res = run_cmd(cmd, timeout=60)
        return str(out_video_path) if (res.returncode == 0 and is_valid_media(out_video_path)) else None

REMOTION_BRIDGE = RemotionBridge()


# =============================================================================
# PREFLIGHT ANALYZER
# =============================================================================

class PreFlightAnalyzer:
    def analyze_topic(self, topic):
        log("🔍 [PreFlight] تحليل أولي للموضوع وتوليد استعلامات البحث والزوايا البصرية...")
        prompt = f"""You are an elite investigative research director. 
TOPIC: {topic}
[BYPASS CACHE: {CONFIG.run_id}]

Analyze this topic and produce a comprehensive research plan for a documentary.
You must identify all key visual elements we need to find BEFORE writing any script.

Return ONLY valid JSON:
{{
  "primary_english_query": "2-3 word English search anchor",
  "target_era": "e.g. 1970s Pacific Northwest",
  "primary_historical_anchor": "1-2 word core entity",
  "forbidden_anachronisms": ["smartphones", "laptops", "modern cars"],
  "visual_research_angles": [
    {{"angle_id": 1, "description": "Key suspects and persons of interest", "search_queries": ["query1", "query2", "query3"], "category": "ARCHIVE", "content_type": "person_mugshot", "priority": "HIGH"}},
    {{"angle_id": 2, "description": "Crime scene and physical evidence", "search_queries": ["query1", "query2"], "category": "ARCHIVE", "content_type": "document_file", "priority": "HIGH"}},
    {{"angle_id": 3, "description": "Atmospheric B-roll footage", "search_queries": ["dark street night", "police car lights"], "category": "CINEMATIC", "content_type": "dark_moody", "priority": "MEDIUM"}}
  ],
  "estimated_chapters": [
    {{"id": 1, "title": "المقدمة واللغز المحير", "key": "part_1", "is_hook": true}},
    {{"id": 2, "title": "خيوط البداية والضحايا", "key": "part_2"}},
    {{"id": 3, "title": "مسرح الجريمة والأدلة", "key": "part_3"}},
    {{"id": 4, "title": "مراسلات غامضة ومسار التحقيق", "key": "part_4"}},
    {{"id": 5, "title": "نقاط التحول والشهادات", "key": "part_5"}},
    {{"id": 6, "title": "دائرة المشتبه بهم", "key": "part_6"}},
    {{"id": 7, "title": "نظريات متضاربة", "key": "part_7"}},
    {{"id": 8, "title": "أسرار الملف المفتوح", "key": "part_8"}}
  ]
}}"""
        try:
            result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", EFFORT_PRO_GENERATION,
                              "--dangerously-skip-permissions", "-p", prompt], timeout=600)
            data = extract_json(result.stdout.strip())
            if data and data.get("visual_research_angles"):
                log(f"✅ [PreFlight] تم تحديد {len(data['visual_research_angles'])} زاوية بحث بصرية")
                log(f"🕰️ الحقبة المستنتجة: {data.get('target_era', 'غير محددة')}")
                return data
        except Exception as e:
            log(f"⚠️ خطأ PreFlight: {e}", "warning")

        anchor = clean_query(topic)
        return {
            "primary_english_query": anchor,
            "target_era": "Historical Investigation",
            "primary_historical_anchor": anchor,
            "forbidden_anachronisms": ["smartphones", "laptops", "modern euro currency"],
            "visual_research_angles": [
                {"angle_id": 1, "description": "Main subject", "search_queries": [anchor, f"{anchor} photo"], "category": "ARCHIVE", "content_type": "person_mugshot", "priority": "HIGH"},
                {"angle_id": 2, "description": "Documents", "search_queries": [f"{anchor} document", f"{anchor} FBI"], "category": "ARCHIVE", "content_type": "document_file", "priority": "HIGH"},
                {"angle_id": 3, "description": "Atmosphere", "search_queries": ["dark street night", "police car lights"], "category": "CINEMATIC", "content_type": "dark_moody", "priority": "MEDIUM"},
            ],
            "estimated_chapters": [
                {"id": 1, "title": "المقدمة واللغز", "key": "part_1", "is_hook": True},
                {"id": 2, "title": "خفايا التحقيق", "key": "part_2"},
            ]
        }


# =============================================================================
# [FIX-6] MEDIA POOL BUILDER (with retry on failed angles)
# =============================================================================

class MediaPoolBuilder:
    def __init__(self):
        self.verified_media = []
        self.lock = threading.Lock()

    async def build_media_pool(self, preflight_data):
        log("📸 [MediaPool] بدء بناء مجمع الوسائط (الوسائط أولاً، السيناريو ثانياً)...")
        angles = preflight_data.get("visual_research_angles", [])
        anchor = preflight_data.get("primary_historical_anchor", clean_query(CONFIG.topic))

        pool_dir = CONFIG.work_dir / "media_pool"
        pool_dir.mkdir(parents=True, exist_ok=True)

        # First pass
        failed_angles = []
        tasks = []
        for angle in angles:
            tasks.append(self._fetch_angle_media(angle, anchor, pool_dir, preflight_data, failed_angles))
        await asyncio.gather(*tasks)

        # [FIX-6] Retry failed angles once with more attempts
        if failed_angles:
            log(f"🔁 [MediaPool] إعادة محاولة {len(failed_angles)} زاوية فاشلة بمحاولات إضافية...", "warning")
            retry_tasks = []
            for angle in failed_angles:
                angle["_retry"] = True
                retry_tasks.append(self._fetch_angle_media(angle, anchor, pool_dir, preflight_data, []))
            await asyncio.gather(*retry_tasks)

        log(f"✅ [MediaPool] تم جمع {len(self.verified_media)} وسيطة مؤكدة")
        return self.verified_media

    async def _fetch_angle_media(self, angle, anchor, pool_dir, preflight_data, failed_tracker):
        angle_id = angle.get("angle_id", 0)
        category = angle.get("category", "ARCHIVE")
        content_type = angle.get("content_type", "default")
        queries = angle.get("search_queries", [anchor])
        priority = angle.get("priority", "MEDIUM")
        is_retry = angle.get("_retry", False)

        target_count = 5 if priority == "HIGH" else 3
        max_attempts = 20 if is_retry else 15
        found_count = 0

        pseudo_shot = {
            "index": angle_id,
            "category": category,
            "content_type": content_type,
            "exact_entities": [clean_query(q) for q in queries],
            "visual_vibes": queries if category == "CINEMATIC" else ["dark atmosphere"],
            "topic_anchor": anchor,
            "accept_similar": True,
            "text": angle.get("description", ""),
        }

        for attempt in range(max_attempts):
            if found_count >= target_count: break
            query_tiers = QUERY_ENGINE.generate_query_tiers(pseudo_shot, attempt)
            base = pool_dir / f"angle_{angle_id:02d}_att_{attempt:02d}"
            if is_retry:
                base = pool_dir / f"angle_{angle_id:02d}_retry_{attempt:02d}"

            results = await PARALLEL_FETCHER.fetch_from_multiple_sources(query_tiers[:2], pseudo_shot, base)
            for found_file, media_uid, src_name, query in results:
                if not found_file or not Path(found_file).exists():
                    QUERY_ENGINE.record_failure(query, src_name)
                    continue
                pre_ok, pre_reason = MediaPreFilter.quick_validate(Path(found_file), pseudo_shot)
                if not pre_ok:
                    Path(found_file).unlink(missing_ok=True)
                    QUERY_ENGINE.record_failure(query, src_name)
                    continue

                # Global reviewer semaphore is passed in via closure — see main_pipeline
                accepted, score, _, reason = await agy_evaluate_scout_bounded(
                    found_file, pseudo_shot, preflight_data, src_name, query, REVIEWER_SEMAPHORE_REF[0]
                )
                if accepted or score >= 0.25:
                    is_img = Path(found_file).suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                    entry = {
                        "angle_id": angle_id,
                        "path": str(found_file),
                        "source": src_name,
                        "query": query,
                        "category": category,
                        "content_type": content_type,
                        "score": score,
                        "description": angle.get("description", ""),
                        "is_image": is_img,
                        "media_uid": media_uid,
                    }
                    with self.lock:
                        self.verified_media.append(entry)
                        if media_uid:
                            with CONFIG.used_media_lock:
                                CONFIG.used_media_ids.add(media_uid)
                    found_count += 1
                    log(f"📸 [MediaPool] زاوية {angle_id}: وسيطة #{found_count}/{target_count} من {src_name} (تقييم: {score:.2f})")
                else:
                    Path(found_file).unlink(missing_ok=True)
                    QUERY_ENGINE.record_failure(query, src_name)

        if found_count == 0 and not is_retry:
            with self.lock:
                failed_tracker.append(angle)
            log(f"⚠️ [MediaPool] زاوية {angle_id}: لم يتم العثور على وسائط — ستُعاد المحاولة.", "warning")
        elif found_count == 0 and is_retry:
            log(f"❌ [MediaPool] زاوية {angle_id}: فشلت نهائياً بعد إعادة المحاولة.", "error")


# [FIX-5] Global reference holder for the reviewer semaphore (set in main_pipeline)
REVIEWER_SEMAPHORE_REF = [None]


# =============================================================================
# AGY REVIEWER (BOUNDED)
# =============================================================================

async def agy_evaluate_scout_bounded(media_path, shot, story, source_name, query, semaphore):
    if not media_path: return False, 0.0, 0.0, "الملف غير موجود"
    prefilter_ok, prefilter_reason = MediaPreFilter.quick_validate(media_path, shot)
    if not prefilter_ok: return False, 0.0, 0.0, prefilter_reason

    target_era = story.get("target_era", "Historical")
    forbidden = ", ".join(story.get("forbidden_anachronisms", []))

    prompt = f"""You evaluate documentary media suitability strictly based on the context and temporal era.
TOPIC: {story.get("primary_english_query", CONFIG.topic)}
TARGET ERA: {target_era}
FORBIDDEN ANACHRONISMS: {forbidden}

SHOT SCRIPT TEXT: "{shot.get('text', '')}"
SHOT CATEGORY: {shot.get('category', 'ARCHIVE')}
RETRIEVED FROM: {source_name}
SEARCH QUERY: "{query}"
LOCAL PATH: {Path(media_path).absolute()}
DIRECTOR NOTE: {shot.get("reviewer_context", "")}
ACCEPT SIMILAR: {shot.get("accept_similar", True)}

CRITICAL EVALUATION RULES:
1. TEMPORAL ACCURACY: historical era + modern anachronisms → REJECT score 0.0.
2. ARCHIVE: accept genuine historical evidence, case documents, sketches, newspaper clippings.
3. CINEMATIC: accept mood, noir, rain, fog, shadows — ruthless on modern anachronisms.

Return ONLY valid JSON: {{"decision": "accept" or "reject", "score": 0.0 to 1.0, "reason": "Arabic reason"}}"""

    async with semaphore:
        for retry in range(REVIEWER_MAX_RETRIES + 1):
            try:
                cmd = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", EFFORT_REVIEWER,
                       "--dangerously-skip-permissions", "-p", prompt]
                res = await asyncio.to_thread(subprocess.run, cmd,
                                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                              text=True, timeout=300)
                data = extract_json(res.stdout)
                if data:
                    score = float(data.get("score", 0.0))
                    threshold = 0.30 if shot.get("accept_similar") else 0.35
                    return (data.get("decision", "").lower() == "accept" and score >= threshold), score, 0.0, str(data.get("reason", ""))
            except Exception as e:
                if retry < REVIEWER_MAX_RETRIES:
                    log(f"⚠️ AGY إعادة محاولة ({retry+1}/{REVIEWER_MAX_RETRIES}): {e}", "warning")
                    await asyncio.sleep(1)
                else:
                    log(f"❌ AGY فشل نهائي بعد {REVIEWER_MAX_RETRIES} محاولات. رفض حتمي.", "error")
        return False, 0.0, 0.0, "فشل تقييم AGY - رفض حتمي"


async def agy_evaluate_scout(media_path, shot, story, source_name, query, semaphore):
    return await agy_evaluate_scout_bounded(media_path, shot, story, source_name, query, semaphore)


# =============================================================================
# STORY SCOUT ENGINE
# =============================================================================

class StoryScoutEngine:
    def __init__(self):
        self.script = None

    def write_script_from_media_context(self, preflight_data, verified_media_list):
        log("🧠 [Media-First] كتابة السيناريو بناءً على الأدلة البصرية المتاحة فعلياً...")

        media_summary_lines = []
        for i, m in enumerate(verified_media_list[:80], 1):
            media_summary_lines.append(
                f"  [{i}] Source: {m['source']} | Category: {m['category']} | "
                f"Type: {m['content_type']} | Score: {m['score']:.2f} | "
                f"Description: {m['description']} | Query: {m['query']}"
            )
        media_context = "\n".join(media_summary_lines) if media_summary_lines else "  (No pre-fetched media)"

        anchor = preflight_data.get("primary_historical_anchor", clean_query(CONFIG.topic))
        era = preflight_data.get("target_era", "Historical")

        prompt = f"""You are an elite investigative documentary producer creating a FULL-LENGTH broadcast documentary.
TOPIC: {CONFIG.topic}
[SYSTEM BYPASS CACHE ID: {CONFIG.run_id}]

VERIFIED MEDIA INVENTORY ({len(verified_media_list)} assets pre-fetched and verified):
{media_context}

PRIMARY ANCHOR: {anchor}
TARGET ERA: {era}

Create a production-ready investigative documentary script for a {TARGET_TOTAL_DURATION_MINUTES}-MINUTE documentary.

CRITICAL REQUIREMENTS:
1. HUMAN DEPTH: victims' lives, family grief, ethical stakes.
2. DYNAMIC PERIOD ANALYSIS: identify target_era, forbidden_anachronisms, primary_historical_anchor.
3. PART 1 = HOOK (45-65s, ~110-140 Arabic words).
4. PARTS 2-8 chronological (~450 words each).
5. NARRATION: continuous Arabic without naming chapter numbers.
6. MEDIA ALIGNMENT: reference the verified media where relevant.

Return ONLY valid JSON:
{{
  "story_type": "investigation",
  "primary_english_query": "",
  "target_era": "",
  "primary_historical_anchor": "",
  "forbidden_anachronisms": [],
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
            result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", EFFORT_PRO_GENERATION,
                              "--dangerously-skip-permissions", "-p", prompt], timeout=600)
            data = extract_json(result.stdout.strip())
            if not data or not data.get("part_1"): raise RuntimeError("Script JSON invalid")
            self.script = data
            log(f"✅ السيناريو جاهز | الحقبة: {data.get('target_era', '?')} | المرساة: {data.get('primary_historical_anchor', '?')}")
            return data
        except Exception as e:
            log(f"⚠️ فشل توليد السيناريو، خطة الطوارئ: {e}", "warning")
            fallback = {
                "story_type": "investigation",
                "primary_english_query": clean_query(CONFIG.topic),
                "target_era": preflight_data.get("target_era", "Historical Investigation"),
                "primary_historical_anchor": preflight_data.get("primary_historical_anchor", clean_query(CONFIG.topic)),
                "forbidden_anachronisms": preflight_data.get("forbidden_anachronisms", ["smartphones", "laptops"]),
                "hashtag": f"#{CONFIG.topic_clean[:25]}",
                "chapters": [
                    {"id": 1, "title": "المقدمة واللغز", "key": "part_1", "is_hook": True},
                    {"id": 2, "title": "خفايا التحقيق", "key": "part_2"}
                ],
                "part_1": f"تفاصيل غامضة حول {CONFIG.topic}.",
                "part_2": "تظل الحقيقة غائبة حتى اليوم."
            }
            self.script = fallback
            return fallback

    @staticmethod
    def _find_shot_data(board, idx_int):
        if not board: return None
        if isinstance(board, list):
            for item in board:
                if isinstance(item, dict):
                    for k in ["index", "shot", "id", "shot_id", "shot_index"]:
                        if str(item.get(k, "")).strip() == str(idx_int): return item
            if 0 <= idx_int - 1 < len(board) and isinstance(board[idx_int - 1], dict):
                return board[idx_int - 1]
        if isinstance(board, dict):
            for wrapper in ["shots", "scenes", "storyboard", "data", "results", "board"]:
                if wrapper in board and isinstance(board[wrapper], (dict, list)):
                    found = StoryScoutEngine._find_shot_data(board[wrapper], idx_int)
                    if found: return found
            idx_str = str(idx_int)
            for ck in [idx_str, f"shot_{idx_str}", f"shot_{idx_int:02d}", f"Shot {idx_str}",
                       f"Shot_{idx_str}", f"shot {idx_str}", f"scene_{idx_str}", f"Scene {idx_str}", f"[{idx_str}]"]:
                if ck in board and isinstance(board[ck], dict): return board[ck]
                for actual_k, val in board.items():
                    if actual_k.lower().strip() == ck.lower().strip() and isinstance(val, dict): return val
            for actual_k, val in board.items():
                if isinstance(val, dict) and re.search(r'\b' + idx_str + r'\b', actual_k): return val
        return None

    def direct_storyboard(self, shots):
        log("🎬 [المخرج الفني] هندسة كلمات البحث...")
        batch_size = 70
        all_processed = []
        target_era = self.script.get("target_era", "")
        anchor = self.script.get("primary_historical_anchor", clean_query(CONFIG.topic))
        forbidden = ", ".join(self.script.get("forbidden_anachronisms", []))

        for batch_start in range(0, len(shots), batch_size):
            batch = shots[batch_start:batch_start + batch_size]
            shots_summary = "\n".join([f"[{s['index']}]: {s['text']}" for s in batch])
            prompt = f"""You are an Elite Visual Director.
TOPIC: {self.script.get('primary_english_query', CONFIG.topic)}
ANCHOR: {anchor}
ERA: {target_era}
FORBIDDEN: {forbidden}
[ID: {CONFIG.run_id}_{batch_start}]

Shots:
{shots_summary}

RULES:
- 85-90% ARCHIVE, 10-15% CINEMATIC.
- Entities 2-3 words, always anchored to '{anchor}'.
- MANDATORY JSON FORMAT:
{{
  "{batch[0]['index']}": {{
    "category": "ARCHIVE",
    "content_type": "document_file",
    "exact_entities": ["{anchor} photo", "{anchor} FBI"],
    "visual_vibes": ["police lights night"],
    "reviewer_context": "تأكد من مطابقة الوثيقة",
    "accept_similar": true
  }}
}}"""
            try:
                result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", EFFORT_PRO_GENERATION,
                                  "--dangerously-skip-permissions", "-p", prompt], timeout=600)
                board = extract_json(result.stdout.strip())

                for shot in batch:
                    idx_int = shot["index"]
                    shot_data = self._find_shot_data(board, idx_int)
                    shot["topic_anchor"] = anchor
                    if shot_data and isinstance(shot_data, dict):
                        cat_raw = str(shot_data.get("category", "")).strip().upper()
                        shot["category"] = "CINEMATIC" if ("CINEMAT" in cat_raw and "ARCHIV" not in cat_raw) else "ARCHIVE"
                        shot["content_type"] = shot_data.get("content_type", "document_file" if shot["category"] == "ARCHIVE" else "dark_moody")
                        shot["exact_entities"] = [clean_query(e) for e in shot_data.get("exact_entities", []) if clean_query(e)] or [anchor, f"{anchor} FBI"]
                        shot["visual_vibes"] = [clean_query(v) for v in shot_data.get("visual_vibes", []) if clean_query(v)] or ["police lights night"]
                        shot["reviewer_context"] = shot_data.get("reviewer_context", "تأكد من الأصالة.")
                        shot["accept_similar"] = shot_data.get("accept_similar", True)
                    else:
                        shot["category"] = "ARCHIVE"
                        shot["content_type"] = "document_file"
                        shot["exact_entities"] = [anchor, f"{anchor} archive"]
                        shot["visual_vibes"] = ["police car night"]
                        shot["reviewer_context"] = "تأكد من الملاءمة."
                        shot["accept_similar"] = True
            except Exception as e:
                log(f"⚠️ خطأ الدفعة: {e}", "warning")
                for shot in batch:
                    shot["topic_anchor"] = anchor
                    shot["category"] = "ARCHIVE"
                    shot["content_type"] = "document_file"
                    shot["exact_entities"] = [anchor, f"{anchor} archive"]
                    shot["visual_vibes"] = ["police car night"]
                    shot["reviewer_context"] = "تأكد."
                    shot["accept_similar"] = True
            all_processed.extend(batch)
        return all_processed


# =============================================================================
# AUDIO STUDIO
# =============================================================================

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

        log(f"🎙️ إنتاج التعليق الصوتي...")
        part_wav_files = []

        for p_idx, (p_key, p_text) in enumerate(part_texts):
            p_wav = CONFIG.work_dir / f"chapter_{p_idx+1:02d}.wav"
            success = False
            attempted = set()
            for attempt in range(len(CONFIG.gemini_keys)):
                key_index, api_key = GEMINI_POOL.acquire(excluded=attempted)
                attempted.add(key_index)
                try:
                    client = genai.Client(api_key=api_key)
                    voice_instruction = (
                        "[INSTRUCTION: Solemn, emotionally resonant Arabic investigative documentary narrator. "
                        f"Read naturally without naming chapter titles. ID: {CONFIG.run_id}_{p_key}]\n\n"
                    )
                    response = client.models.generate_content(
                        model=TTS_MODEL,
                        contents=voice_instruction + p_text,
                        config=types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=types.SpeechConfig(
                                voice_config=types.VoiceConfig(
                                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE)
                                )
                            )
                        )
                    )
                    data = next((p.inline_data.data for p in response.candidates[0].content.parts if getattr(p, "inline_data", None)), None)
                    if not data: raise RuntimeError()
                    raw_audio = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                    temp_pcm = CONFIG.work_dir / f"chunk_{p_idx}_{key_index}.pcm"
                    with open(temp_pcm, "wb") as f: f.write(raw_audio)
                    run_cmd(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(temp_pcm),
                             "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(p_wav)], timeout=180)
                    temp_pcm.unlink(missing_ok=True)
                    if is_valid_media(p_wav):
                        log(f"✅ صوت الفصل {p_idx+1}/{len(part_texts)} بمفتاح #{key_index+1}")
                        GEMINI_POOL.release(key_index)
                        part_wav_files.append((p_key, p_wav))
                        success = True
                        break
                except:
                    GEMINI_POOL.release(key_index)
                    time.sleep(2)
            if not success:
                raise RuntimeError(f"❌ فشل صوت المحور {p_idx+1}.")

        concat_list = CONFIG.work_dir / "audio_concat.txt"
        with open(concat_list, "w") as f:
            for _, pw in part_wav_files:
                f.write(f"file '{pw.resolve()}'\n")
        run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                 "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(CONFIG.master_audio)], timeout=300)
        log(f"✅ مسار الصوت الماستر: {probe_duration(CONFIG.master_audio)/60:.1f} دقيقة")
        return CONFIG.master_audio, part_wav_files


# =============================================================================
# WORD SYNC SLICER
# =============================================================================

class WordSyncSlicer:
    def align_and_slice(self, part_wav_files, script):
        headers = {"Authorization": f"Bearer {CONFIG.groq_api_key}"}
        shots = []
        timeline_offset = 0.0
        chapter_timeline = []

        for p_idx, (p_key, p_wav) in enumerate(part_wav_files):
            dur = probe_duration(p_wav)
            is_hook = (p_idx == 0)
            ch_title = f"المحور {p_idx+1}"
            for ch in script.get("chapters", []):
                if ch.get("key") == p_key or ch.get("id") == p_idx + 1:
                    ch_title = ch.get("title", ch_title)
                    break

            chapter_timeline.append({
                "part_idx": p_idx + 1, "title": ch_title,
                "start_time": timeline_offset, "is_hook": is_hook, "duration": dur
            })

            with open(p_wav, "rb") as f:
                res = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers=headers,
                    files={"file": (p_wav.name, f, "audio/wav")},
                    data={"model": GROQ_MODEL, "language": "ar", "response_format": "verbose_json",
                          "timestamp_granularities[]": "word"},
                    timeout=600
                )
            if res.status_code != 200:
                raise RuntimeError(f"Groq failed: {res.text[:200]}")

            words = [{"word": str(w["word"]).strip(), "start": float(w["start"]) + timeline_offset,
                      "end": float(w["end"]) + timeline_offset}
                     for w in res.json().get("words", []) if w.get("word")]

            min_dur = SCENE_DURATION_MIN_HOOK if is_hook else SCENE_DURATION_MIN
            max_dur = SCENE_DURATION_MAX_HOOK if is_hook else SCENE_DURATION_MAX

            cur, s_start = [], timeline_offset
            for item in words:
                cur.append(item)
                cur_len = item["end"] - s_start
                if cur_len >= max_dur or (cur_len >= min_dur and item["word"].endswith((".", "!", "؟", "،"))):
                    self._emit_shot(shots, cur, s_start, item["end"], is_hook, p_idx + 1)
                    cur, s_start = [], item["end"]
            if cur:
                self._emit_shot(shots, cur, s_start, cur[-1]["end"], is_hook, p_idx + 1)

            timeline_offset += dur

        log(f"✂️ تم تقسيم الصوت إلى {len(shots)} مشهد.")
        return shots, chapter_timeline

    @staticmethod
    def _emit_shot(shots, cur, s_start, s_end, is_hook, chapter_num):
        raw_text = " ".join(x["word"] for x in cur).strip()
        clean_text = re.sub(r"[\|]{2,}", " ", raw_text).strip()
        clean_text = unicodedata.normalize('NFKC', clean_text)
        clean_text = re.sub(r'[\u200B-\u200F\uFEFF\u00A0]', ' ', clean_text)
        clean_text = re.sub(r"\s+", " ", clean_text).strip()
        if not clean_text: return
        raw_dur = max(0.5, s_end - s_start)
        exact_frames = max(15, int(round(raw_dur * TARGET_FPS)))
        quantized_dur = exact_frames / TARGET_FPS
        shots.append({
            "index": len(shots) + 1,
            "start": s_start, "end": s_start + quantized_dur,
            "duration": quantized_dur, "frames": exact_frames,
            "text": clean_text, "is_hook": is_hook, "chapter_num": chapter_num
        })


# =============================================================================
# FALLBACK
# =============================================================================

async def apply_fallback(shot, story):
    index = shot["index"]
    dur = float(shot.get("duration", 3.0))

    if shot.get('best_candidate') and shot['best_score'] >= 0.15:
        cand_path = Path(shot['best_candidate']['path'])
        if cand_path.exists():
            log(f"⚠️ [إنقاذ 1] المشهد {index}: أفضل نتيجة (تقييم {shot['best_score']:.2f}).", "warning")
            return shot['best_candidate']

    log(f"🎬 [إنقاذ 2] خلفية سينمائية للمشهد {index}.", "warning")
    fb = CONFIG.work_dir / f"selected_shot_{index:03d}_fallback.mp4"
    if await create_fallback_visual(fb, duration=dur):
        return {"shot": shot, "path": str(fb), "source": "CINEMATIC_BG", "score": 0.0, "start": 0.0, "duration": dur}

    log(f"🤖 [إنقاذ نهائي] AI للمشهد {index}.", "error")
    ai = CONFIG.work_dir / f"selected_shot_{index:03d}_ai.jpg"
    anchor = shot.get("topic_anchor", clean_query(CONFIG.topic))
    if await generate_ai_image(f"{anchor} crime archive photograph vintage", ai):
        return {"shot": shot, "path": str(ai), "source": "AI_GENERATED", "score": 1.0, "start": 0.0, "duration": dur}

    black = CONFIG.work_dir / f"selected_shot_{index:03d}_black.mp4"
    await create_fallback_visual(black, duration=dur)
    return {"shot": shot, "path": str(black), "source": "FFMPEG", "score": 0.0, "start": 0.0, "duration": dur}


# =============================================================================
# [FIX-1] PRODUCTION PIPELINE — REAL MEDIA-FIRST
# =============================================================================

async def run_pipelined_production(shots, story, reviewer_semaphore):
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
        shot['pool_tried'] = 0

    log(f"🚀 خط الإنتاج (Media-First) | المشاهد: {total_shots} | pool items: {VERIFIED_MEDIA_POOL.summary()['total']}")

    async def _try_pool_first(shot):
        """[FIX-1] Try to claim from pool. Returns result item or None."""
        if shot['pool_tried'] >= POOL_ATTEMPTS_PER_SHOT:
            return None

        pool_item = VERIFIED_MEDIA_POOL.try_claim_for_shot(shot)
        if not pool_item:
            return None

        src_path = Path(pool_item["path"])
        if not src_path.exists():
            return None

        pre_ok, pre_reason = MediaPreFilter.quick_validate(src_path, shot)
        if not pre_ok:
            log(f"⏩ مشهد {shot['index']}: pool item رُفض ({pre_reason})", "debug")
            return None

        # Reviewer pass (bounded)
        accepted, score, _, reason = await agy_evaluate_scout(
            src_path, shot, story, pool_item["source"], pool_item["query"], reviewer_semaphore
        )

        if accepted or score >= 0.25:
            # Copy into work dir under standard naming
            dst = CONFIG.work_dir / f"selected_shot_{shot['index']:03d}{src_path.suffix}"
            shutil.copy(src_path, dst)
            log(f"✅ مشهد {shot['index']}: من المجمع ({pool_item['source']}) تقييم {score:.2f} — {reason[:60]}")
            is_img = src_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
            dur = float(shot.get("duration", 3.0)) if is_img else probe_duration(dst)
            return {
                "shot": shot, "path": str(dst), "source": f"POOL_{pool_item['source']}",
                "score": score, "start": 0.0, "duration": dur, "from_pool": True
            }
        return None

    async def process_shot(shot):
        index = shot["index"]
        base = CONFIG.work_dir / f"raw_shot_{index:03d}"

        while shot['status'] != 'DONE' and shot['attempts'] < MAX_ATTEMPTS_PER_SHOT:
            # ── [FIX-1] Try pool first ──
            while shot['pool_tried'] < POOL_ATTEMPTS_PER_SHOT:
                pool_res = await _try_pool_first(shot)
                shot['pool_tried'] += 1
                if pool_res:
                    async with completed_lock:
                        if shot['status'] != 'DONE':
                            shot['status'] = 'DONE'
                            completed_results.append(pool_res)
                            log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                            if len(completed_results) == total_shots: completion_event.set()
                    return

            # ── Network fetch ──
            attempt_num = shot['attempts']
            query_tiers = QUERY_ENGINE.generate_query_tiers(shot, attempt_num)
            pairs = query_tiers[:2] if (attempt_num < 2 and len(query_tiers) >= 2) else query_tiers[:1]

            log(f"⚡ ({attempt_num+1}/{MAX_ATTEMPTS_PER_SHOT}) مشهد {index} | "
                f"{'، '.join(f'{s}:{q}' for q,s in pairs)}")

            fetch_results = await PARALLEL_FETCHER.fetch_from_multiple_sources(pairs, shot, base)
            if not fetch_results:
                for q, src in pairs: QUERY_ENGINE.record_failure(q, src)
                shot['attempts'] += 1
                continue

            found_acceptable = False
            for found_file, media_uid, src_name, query in fetch_results:
                if not found_file or not Path(found_file).exists():
                    QUERY_ENGINE.record_failure(query, src_name); continue
                output_path = Path(found_file)
                pre_ok, pre_reason = MediaPreFilter.quick_validate(output_path, shot)
                if not pre_ok:
                    QUERY_ENGINE.record_failure(query, src_name)
                    output_path.unlink(missing_ok=True); continue

                accepted, score, start, reason = await agy_evaluate_scout(
                    output_path, shot, story, src_name, query, reviewer_semaphore
                )
                is_img = output_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
                dur = float(shot.get("duration", 3.0)) if is_img else probe_duration(output_path)

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
                    log(f"🎯 مشهد {index}: من {src_name} ({score:.2f}) — {reason[:60]}")
                    selected = CONFIG.work_dir / f"selected_shot_{index:03d}{output_path.suffix}"
                    if selected.exists(): selected.unlink(missing_ok=True)
                    shutil.move(str(output_path), str(selected))
                    res_item = {"shot": shot, "path": str(selected), "source": src_name,
                                "score": score, "start": start, "duration": dur}
                    cleanup_shot_unused_files(index, keep_path=selected)
                    async with completed_lock:
                        if shot['status'] != 'DONE':
                            shot['status'] = 'DONE'
                            if media_uid:
                                with CONFIG.used_media_lock: CONFIG.used_media_ids.add(media_uid)
                            completed_results.append(res_item)
                            log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                            if len(completed_results) == total_shots: completion_event.set()
                    found_acceptable = True; break
                else:
                    QUERY_ENGINE.record_failure(query, src_name)
                    if output_path.exists() and output_path != Path(shot.get('best_candidate', {}).get('path', '')):
                        output_path.unlink(missing_ok=True)

            if not found_acceptable:
                shot['attempts'] += 1
                if shot['status'] != 'DONE' and shot['attempts'] >= 8 and shot['best_score'] >= 0.25 and shot['best_candidate']:
                    best = shot['best_candidate']
                    cf = Path(best['path'])
                    if cf.exists():
                        selected = CONFIG.work_dir / f"selected_shot_{index:03d}{cf.suffix}"
                        shutil.move(str(cf), str(selected))
                        best['path'] = str(selected)
                        log(f"✅ مشهد {index}: قبول تدريجي ({shot['best_score']:.2f})")
                        cleanup_shot_unused_files(index, keep_path=selected)
                        async with completed_lock:
                            if shot['status'] != 'DONE':
                                shot['status'] = 'DONE'
                                completed_results.append(best)
                                log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                                if len(completed_results) == total_shots: completion_event.set()
                        break

        if shot['status'] != 'DONE':
            log(f"⚠️ مشهد {index}: خطة الإنقاذ...", "warning")
            fb = await apply_fallback(shot, story)
            cleanup_shot_unused_files(index, keep_path=fb.get('path'))
            async with completed_lock:
                if shot['status'] != 'DONE':
                    shot['status'] = 'DONE'
                    completed_results.append(fb)
                    log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                    if len(completed_results) == total_shots: completion_event.set()

    async def throttled(shot):
        async with shot_semaphore:
            await process_shot(shot)

    await asyncio.gather(*[asyncio.create_task(throttled(s)) for s in shots])
    if not completion_event.is_set(): completion_event.set()
    gc.collect()

    final_dict = {r["shot"]["index"]: r for r in completed_results}
    log(f"📦 ملخص المجمع النهائي: {VERIFIED_MEDIA_POOL.summary()}")
    return [final_dict[s["index"]] for s in shots if s["index"] in final_dict]


# =============================================================================
# ASSEMBLY ENGINE
# =============================================================================

class AssemblyEngine:
    async def render_sub_clip(self, item):
        shot, index = item["shot"], item["shot"]["index"]
        media_path = Path(item["path"])
        output = CONFIG.work_dir / f"rendered_{index:03d}.mp4"
        exact_frames = int(shot.get("frames", round(shot.get("duration", 3.0) * TARGET_FPS)))

        if not media_path.exists() or media_path.stat().st_size < 1024:
            log(f"⚠️ ملف مشهد {index} مفقود، بديل فوري...", "warning")
            await create_fallback_visual(output, duration=exact_frames/TARGET_FPS)
            return output

        start = min(float(item.get("start", 0)), max(0, probe_duration(media_path) - 0.1))

        if media_path.suffix.lower() in (".mp4", ".mov"):
            fc = build_blur_background_filter_video()
            res = await asyncio.to_thread(run_cmd, [
                "ffmpeg", "-y", "-ss", str(start), "-i", str(media_path),
                "-filter_complex", fc,
                "-frames:v", str(exact_frames), "-fps_mode", "cfr", "-r", str(TARGET_FPS),
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", str(output)
            ])
        else:
            fc = build_blur_background_filter_image(ken_burns=True)
            res = await asyncio.to_thread(run_cmd, [
                "ffmpeg", "-y", "-loop", "1", "-i", str(media_path),
                "-filter_complex", fc,
                "-frames:v", str(exact_frames), "-fps_mode", "cfr", "-r", str(TARGET_FPS),
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", str(output)
            ])

        if res.returncode != 0:
            vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,fps={TARGET_FPS}"
            if media_path.suffix.lower() in (".mp4", ".mov"):
                res = await asyncio.to_thread(run_cmd, ["ffmpeg", "-y", "-ss", str(start), "-i", str(media_path), "-vf", vf,
                        "-frames:v", str(exact_frames), "-fps_mode", "cfr", "-r", str(TARGET_FPS), "-an",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)])
            else:
                res = await asyncio.to_thread(run_cmd, ["ffmpeg", "-y", "-loop", "1", "-i", str(media_path), "-vf", vf,
                        "-frames:v", str(exact_frames), "-fps_mode", "cfr", "-r", str(TARGET_FPS), "-an",
                        "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)])

        if res.returncode != 0:
            await create_fallback_visual(output, duration=exact_frames/TARGET_FPS)
        return output

    async def render_batch(self, items, batch_num, total_batches):
        log(f"🎬 رندرة الدفعة {batch_num}/{total_batches} ({len(items)} مشهد)...")
        rendered = []
        for item in items:
            rendered.append(await self.render_sub_clip(item))
        gc.collect()
        return rendered

    async def assemble_final_cut(self, rendered_items, shots, chapter_timeline, hashtag):
        log("🎞️ التجميع النهائي...")

        normalized_intro = None
        intro_dur = 0.0
        if CONFIG.intro_path and CONFIG.intro_path.exists() and CONFIG.intro_path.stat().st_size > 1024:
            intro_dur = probe_duration(CONFIG.intro_path)
            if intro_dur > 1.0:
                normalized_intro = CONFIG.work_dir / "normalized_intro.mp4"
                await asyncio.to_thread(run_cmd, [
                    "ffmpeg", "-y", "-i", str(CONFIG.intro_path),
                    "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,fps={TARGET_FPS}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2", str(normalized_intro)
                ])

        final_video_sequence, final_audio_segments, youtube_chapters = [], [], []
        current_time = 0.0
        chapter_offsets = {}

        chapter_shots = defaultdict(list)
        for item in rendered_items:
            chapter_shots[item["shot"].get("chapter_num", 1)].append(item)

        intro_inserted = False
        intro_start_time = intro_end_time = 0.0

        for ch_info in chapter_timeline:
            ch_num, ch_title, is_hook = ch_info["part_idx"], ch_info["title"], ch_info["is_hook"]
            youtube_chapters.append(f"{int(current_time//60):02d}:{int(current_time%60):02d} {ch_title}")

            if not is_hook and not intro_inserted and normalized_intro and normalized_intro.exists():
                intro_start_time = current_time
                final_video_sequence.append(str(normalized_intro))
                intro_audio = CONFIG.work_dir / "intro_audio.wav"
                await asyncio.to_thread(run_cmd, ["ffmpeg", "-y", "-i", str(normalized_intro), "-vn",
                        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(intro_audio)])
                final_audio_segments.append(str(intro_audio))
                current_time += intro_dur
                intro_end_time = current_time
                intro_inserted = True

            if ch_num >= 2:
                trans_card = CONFIG.work_dir / f"trans_card_ch_{ch_num:02d}.mp4"
                created = await REMOTION_BRIDGE.generate_chapter_transition(ch_num, ch_title, trans_card, duration=2.2)
                if created:
                    final_video_sequence.append(str(trans_card))
                    card_audio = CONFIG.work_dir / f"card_audio_ch_{ch_num:02d}.wav"
                    await asyncio.to_thread(run_cmd, ["ffmpeg", "-y", "-i", str(trans_card), "-vn",
                            "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(card_audio)])
                    final_audio_segments.append(str(card_audio))
                    current_time += 2.2

            chapter_offsets[ch_num] = current_time - ch_info["start_time"]

            for it in chapter_shots.get(ch_num, []):
                v_path = CONFIG.work_dir / f"rendered_{it['shot']['index']:03d}.mp4"
                if v_path.exists():
                    final_video_sequence.append(str(v_path))
                    current_time += it['shot']['duration']

            ch_narration = CONFIG.work_dir / f"chapter_{ch_num:02d}.wav"
            if ch_narration.exists():
                norm_audio = CONFIG.work_dir / f"norm_audio_{ch_num:02d}.wav"
                await asyncio.to_thread(run_cmd, ["ffmpeg", "-y", "-i", str(ch_narration),
                        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(norm_audio)])
                final_audio_segments.append(str(norm_audio))

        primary_bgr = self._hex_to_ass_color(BRAND_COLORS["primary"])
        dark_bgr = self._hex_to_ass_color(BRAND_COLORS["dark"])

        sub_path = CONFIG.work_dir / "subtitles_sync.ass"
        with open(sub_path, "w", encoding="utf-8") as f:
            f.write(
                "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n"
                "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
                f"Style: Default,Noto Sans Arabic,58,&H00FFFFFF,&H00FFFFFF,&H00{primary_bgr},&H90{dark_bgr},-1,0,0,0,100,100,0,0,1,2.5,1.5,2,80,80,68,1\n"
                "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            )
            for s in shots:
                offset = chapter_offsets.get(s.get("chapter_num", 1), 0.0)
                s_start = s["start"] + offset
                s_end = s["end"] + offset
                h1, m1 = int(s_start // 3600), int((s_start % 3600) // 60)
                h2, m2 = int(s_end // 3600), int((s_end % 3600) // 60)
                t_clean = s['text'].replace("\\", r"\\")
                f.write(f"Dialogue: 0,{h1}:{m1:02d}:{s_start%60:05.2f},{h2}:{m2:02d}:{s_end%60:05.2f},Default,,0,0,0,,{{\\fad(100,100)}}{t_clean}\n")

        v_concat_txt = CONFIG.work_dir / "final_v_concat.txt"
        with open(v_concat_txt, "w") as f:
            for vp in final_video_sequence: f.write(f"file '{Path(vp).resolve()}'\n")

        a_concat_txt = CONFIG.work_dir / "final_a_concat.txt"
        with open(a_concat_txt, "w") as f:
            for ap in final_audio_segments: f.write(f"file '{Path(ap).resolve()}'\n")

        merged_audio = CONFIG.work_dir / "master_soundtrack.wav"
        await asyncio.to_thread(run_cmd, ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(a_concat_txt), "-c:a", "pcm_s16le", str(merged_audio)])

        intro_mask = f"not(between(t,{intro_start_time:.2f},{intro_end_time:.2f}))" if intro_end_time > 0 else "1"
        sub_filter = "subtitles=" + str(Path(sub_path).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

        title_file = CONFIG.work_dir / "title_tag.txt"
        safe_display_title = f"{CONFIG.topic[:35]} | #{CONFIG.topic_clean[:20]}"
        with open(title_file, "w", encoding="utf-8") as tf:
            tf.write(safe_display_title)

        font_file = find_system_arabic_font()
        has_logo = CONFIG.logo_path and CONFIG.logo_path.exists() and CONFIG.logo_path.stat().st_size > 1024

        parts = [f"[0:v]{sub_filter}[v_sub]"]
        current_v = "[v_sub]"
        if has_logo:
            parts.append(f"[2:v]scale=180:-1[logo_scaled]")
            parts.append(f"{current_v}[logo_scaled]overlay=W-w-50:50:enable='{intro_mask}':format=auto[v_logo]")
            current_v = "[v_logo]"
        if font_file:
            safe_title_path = str(title_file.resolve()).replace("\\", "/").replace(":", "\\:")
            parts.append(
                f"{current_v}drawtext=fontfile='{font_file}':textfile='{safe_title_path}':"
                f"x=50:y=50:fontsize=32:fontcolor=white@0.85:shadowcolor=black@0.7:shadowx=2:shadowy=2:"
                f"enable='{intro_mask}'[v_final]"
            )
        else:
            parts.append(f"{current_v}null[v_final]")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(v_concat_txt),
               "-i", str(merged_audio)]
        if has_logo: cmd.extend(["-i", str(CONFIG.logo_path)])
        cmd.extend([
            "-filter_complex", ";".join(parts),
            "-map", "[v_final]", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18",
            "-c:a", "aac", "-b:a", "192k", "-shortest", str(CONFIG.final_video)
        ])

        res = await asyncio.to_thread(run_cmd, cmd, 3600)
        if res.returncode != 0:
            log(f"⚠️ تجميع احتياطي: {res.stderr[-250:]}", "warning")
            await asyncio.to_thread(run_cmd, [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(v_concat_txt),
                "-i", str(merged_audio), "-vf", sub_filter,
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k", "-shortest", str(CONFIG.final_video)
            ], 3600)

        if not is_valid_media(CONFIG.final_video):
            raise RuntimeError("Final assembly failed.")

        desc_text = f"وثائقي استقصائي شامل: {CONFIG.topic}\n\nفصول الوثائقي:\n" + "\n".join(youtube_chapters) + f"\n\n#{CONFIG.topic_clean[:25]}"
        with open(CONFIG.description_file, "w", encoding="utf-8") as f:
            f.write(desc_text)
        log(f"🎉 تم الإنتاج! المدة: {probe_duration(CONFIG.final_video)/60:.2f} دقيقة | الحجم: {CONFIG.final_video.stat().st_size/1024/1024:.1f} MB")
        return CONFIG.final_video, desc_text

    @staticmethod
    def _hex_to_ass_color(hex_color):
        hex_color = hex_color.lstrip("#")
        r, g, b = hex_color[0:2], hex_color[2:4], hex_color[4:6]
        return f"{b}{g}{r}"


# =============================================================================
# QC
# =============================================================================

def run_final_qc(video_path):
    log("🔍 [QC] فحص الجودة النهائي...")
    try:
        res_black = subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-vf", "blackdetect=d=1.0:pix_th=0.10", "-an", "-f", "null", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1200)
        blacks = re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)\s+black_duration:([\d.]+)", res_black.stderr)
        for s, e, d in blacks:
            if float(d) > 1.0: log(f"⚠️ [QC] أسود: {float(s):.1f}s-{float(e):.1f}s ({float(d):.1f}s)", "warning")

        res_silence = subprocess.run(
            ["ffmpeg", "-i", str(video_path), "-af", "silencedetect=n=-50dB:d=2.0", "-vn", "-f", "null", "-"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1200)
        silences = re.findall(r"silence_start:\s*([\d.]+).*?silence_end:\s*([\d.]+).*?silence_duration:\s*([\d.]+)", res_silence.stderr, re.DOTALL)
        for s, e, d in silences:
            if float(d) > 2.0: log(f"⚠️ [QC] صمت: {float(s):.1f}s-{float(e):.1f}s ({float(d):.1f}s)", "warning")
        log("✅ [QC] انتهى الفحص.")
    except Exception as e:
        log(f"⚠️ [QC] فشل: {e}", "warning")


# =============================================================================
# UPLOADER
# =============================================================================

class GoogleUploader:
    def __init__(self, cid, csec, ref, drive_folder_id):
        self.drive_folder_id = drive_folder_id
        self.creds = Credentials(None, refresh_token=ref, token_uri="https://oauth2.googleapis.com/token",
                                 client_id=cid, client_secret=csec) if cid and csec and ref else None

    def upload_all(self, vid_path, thumb_path, title, description=""):
        if not self.creds: return
        final_display_title = title or CONFIG.topic or "وثائقي استقصائي"
        try:
            drive = build('drive', 'v3', credentials=self.creds, cache_discovery=False)
            body = {'name': f"{final_display_title}.mp4"}
            if self.drive_folder_id: body['parents'] = [self.drive_folder_id]
            df = drive.files().create(body=body,
                media_body=MediaFileUpload(str(vid_path), mimetype='video/mp4', resumable=True),
                fields='id, webViewLink').execute()
            log(f"✅ Drive: https://drive.google.com/file/d/{df.get('id')}/view")

            yt = build('youtube', 'v3', credentials=self.creds, cache_discovery=False)
            yt_body = {'snippet': {'title': final_display_title[:95],
                'description': description or f"وثائقي: {final_display_title}",
                'tags': ['وثائقي', 'جريمة', 'غموض', 'تحقيق'], 'categoryId': '24'},
                'status': {'privacyStatus': 'private'}}
            res = yt.videos().insert(part=','.join(yt_body.keys()), body=yt_body,
                media_body=MediaFileUpload(str(vid_path), mimetype='video/mp4', resumable=True)).execute()
            vid_id = res.get('id')
            log(f"✅ YouTube: https://youtu.be/{vid_id}")

            if thumb_path.exists() and thumb_path.stat().st_size > 1024:
                try:
                    yt.thumbnails().set(videoId=vid_id,
                        media_body=MediaFileUpload(str(thumb_path), mimetype='image/jpeg')).execute()
                    log("✅ Thumbnail مرفوع.")
                except Exception as te: log(f"⚠️ Thumbnail: {te}", "warning")
        except Exception as e:
            log(f"❌ رفع فاشل: {e}", "error")


# =============================================================================
# [FIX-5] MAIN PIPELINE (semaphore created inside async context)
# =============================================================================

async def main_pipeline():
    prepare_fresh_workspace()
    log(f"🚀 {ENGINE_VERSION} | القضية: {CONFIG.topic}")

    # [FIX-5] Semaphore created inside the running event loop
    reviewer_semaphore = asyncio.Semaphore(7)
    REVIEWER_SEMAPHORE_REF[0] = reviewer_semaphore

    # STAGE 1: PreFlight
    preflight_data = PreFlightAnalyzer().analyze_topic(CONFIG.topic)

    # STAGE 2: Media Pool (BEFORE script)
    media_pool_builder = MediaPoolBuilder()
    verified_media = await media_pool_builder.build_media_pool(preflight_data)

    # [FIX-1] Load pool into global
    VERIFIED_MEDIA_POOL.load(verified_media)

    # Save verified media context
    media_context_path = CONFIG.work_dir / "verified_media_context.json"
    with open(media_context_path, "w", encoding="utf-8") as f:
        json.dump([{k: m[k] for k in ("angle_id", "path", "source", "query", "category",
                                       "content_type", "score", "description", "is_image")}
                   for m in verified_media], f, ensure_ascii=False, indent=2)

    # STAGE 3: Script (AFTER media)
    story = StoryScoutEngine().write_script_from_media_context(preflight_data, verified_media)

    # STAGE 4: Audio
    master_audio, part_wav_files = MasterAudioStudio().produce_master_track(story)

    # STAGE 5: Word Sync
    shots, chapter_timeline = WordSyncSlicer().align_and_slice(part_wav_files, story)

    # STAGE 6: Storyboard
    shots = StoryScoutEngine().direct_storyboard(shots) if False else StoryScoutEngine_direct(story, shots)

    # STAGE 7: Production + Render
    assembly = AssemblyEngine()
    all_rendered, media_results = [], []
    total_batches = max(1, (len(shots) + RENDER_BATCH_SIZE - 1) // RENDER_BATCH_SIZE)

    for batch_idx in range(total_batches):
        start = batch_idx * RENDER_BATCH_SIZE
        end = min(start + RENDER_BATCH_SIZE, len(shots))
        batch_shots = shots[start:end]
        batch_items = await run_pipelined_production(batch_shots, story, reviewer_semaphore)
        media_results.extend(batch_items)
        batch_rendered = await assembly.render_batch(batch_items, batch_idx + 1, total_batches)
        all_rendered.extend(batch_rendered)
        for item in batch_items:
            try:
                rp = item.get("path")
                if rp and os.path.exists(rp): os.remove(rp)
            except Exception: pass

    rendered_shot_items = [{"shot": item["shot"], "path": r_path}
                           for item, r_path in zip(media_results, all_rendered)]

    # STAGE 8: Final Assembly
    hashtag = story.get("hashtag", f"#{CONFIG.topic_clean[:25]}")
    final_video, desc_text = await assembly.assemble_final_cut(rendered_shot_items, shots, chapter_timeline, hashtag)

    # STAGE 9: QC
    run_final_qc(CONFIG.final_video)

    # STAGE 10: Thumbnail + Upload
    await generate_ai_image(story.get('primary_english_query', CONFIG.topic), CONFIG.thumbnail, "16:9")
    uploader = GoogleUploader(CONFIG.google_client_id, CONFIG.google_client_secret,
                              CONFIG.google_refresh_token, CONFIG.drive_folder_id)
    await asyncio.to_thread(uploader.upload_all, final_video, CONFIG.thumbnail, CONFIG.topic, desc_text)

    log(f"\n{'='*60}\n🏁 اكتمل الإنتاج بنجاح.\n{'='*60}\n")
    PARALLEL_FETCHER.shutdown()
    gc.collect()


def StoryScoutEngine_direct(story, shots):
    """Helper to run direct_storyboard on a fresh StoryScoutEngine that has `script` set."""
    engine = StoryScoutEngine()
    engine.script = story
    return engine.direct_storyboard(shots)


if __name__ == "__main__":
    try:
        asyncio.run(main_pipeline())
    except KeyboardInterrupt:
        log("🛑 تم الإيقاف يدوياً.", "warning")
        sys.exit(0)