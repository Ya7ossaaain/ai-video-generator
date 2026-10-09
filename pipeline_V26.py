#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
V60 - GENIUS ARCHIVE & COMPACT SOURCING MASTER
(ZERO-RATELIMIT DDG, YT-DLP DENO ENGINE, RESILIENT YARN & SURGICAL QUERIES)
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

ENGINE_VERSION = "V60-GENIUS-ARCHIVE-MASTER"

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

REVIEWER_SEMAPHORE = asyncio.Semaphore(7)

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

API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
}

MEDIA_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

ARCHIVE_SOURCES = ["WIKIPEDIA", "DUCKDUCKGO", "FBI_ARCHIVE", "YOUTUBE", "YARN", "OPENVERSE", "LOC", "EUROPEANA"]
CINEMATIC_SOURCES = ["PEXELS", "PIXABAY"]

SOURCE_AFFINITY = {
    "ARCHIVE": {
        "person_mugshot": ["WIKIPEDIA", "DUCKDUCKGO", "FBI_ARCHIVE", "OPENVERSE", "LOC"],
        "document_file": ["FBI_ARCHIVE", "WIKIPEDIA", "DUCKDUCKGO", "LOC", "EUROPEANA"],
        "historic_interview": ["YOUTUBE", "FBI_ARCHIVE", "WIKIPEDIA"],
        "movie_clip": ["YARN", "YOUTUBE"],
        "location_photo": ["WIKIPEDIA", "DUCKDUCKGO", "OPENVERSE", "LOC"],
        "historical_event": ["WIKIPEDIA", "FBI_ARCHIVE", "DUCKDUCKGO", "YOUTUBE"],
        "newspaper_article": ["LOC", "WIKIPEDIA", "DUCKDUCKGO", "EUROPEANA"],
        "default": ["WIKIPEDIA", "DUCKDUCKGO", "FBI_ARCHIVE", "OPENVERSE", "LOC"],
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
        self.topic = os.environ.get("VIDEO_TOPIC", "لغز القاتل زودياك").strip()
        self.topic_clean = re.sub(r'[\\/*?:"<>|]', "", self.topic).strip() or "documentary"
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
        self.youtube_api_key = os.environ.get("YOUTUBE_API_KEY", "")
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
            if path_obj.exists() and path_obj.stat().st_size > 1024:
                return path_obj
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
    w, h = probe_dimensions(path)
    return w > 0 and h > 0

def clean_query(text):
    """Surgical 2-3 word distillation to guarantee high hit-rates on archive APIs."""
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
# BULLETPROOF FFMPEG FILTERS
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
        if source == "EUROPEANA": return bool(CONFIG.europeana_key)
        if source == "OPENVERSE": return bool(CONFIG.openverse_client_id and CONFIG.openverse_client_secret)
        return True

    def generate_query_tiers(self, shot, attempt_num=0):
        cat = shot.get("category", "ARCHIVE")
        entities = [clean_query(e) for e in shot.get("exact_entities", []) if clean_query(e)]
        vibes = [clean_query(v) for v in shot.get("visual_vibes", []) if clean_query(v)]
        content_type = shot.get("content_type", "default")
        filtered_sources = self.get_ordered_sources(shot)

        topic_words = clean_query(CONFIG.topic).split()[:2]
        topic_short = " ".join(topic_words)
        if not entities: entities = [topic_short, f"{topic_short} police"]
        if not vibes: vibes = ["police lights night", "dark street lamp"]

        queries = []
        n_sources = len(filtered_sources)
        src = filtered_sources[attempt_num % n_sources]

        if cat == "ARCHIVE":
            anchor = entities[attempt_num % len(entities)]
            short_anchor = " ".join(anchor.split()[:2])

            if content_type == "movie_clip":
                dialogue_quotes = ["I have a bomb", "twenty dollar bills", "parachute", "hijack"]
                queries.append((dialogue_quotes[attempt_num % len(dialogue_quotes)], "YARN"))
                queries.append((short_anchor, "YOUTUBE"))
            elif content_type == "historic_interview":
                queries.append((f"{short_anchor} interview", "YOUTUBE"))
                queries.append((short_anchor, "FBI_ARCHIVE"))
            else:
                if attempt_num == 0:
                    queries.append((short_anchor, src))
                elif attempt_num <= 4:
                    tags = ["photo", "file", "diagram", "press"]
                    tag = tags[(attempt_num - 1) % len(tags)]
                    queries.append((f"{short_anchor} {tag}", src))
                elif attempt_num <= 9:
                    queries.append((f"{short_anchor}", "WIKIPEDIA"))
                    queries.append((f"{short_anchor}", "DUCKDUCKGO"))
                else:
                    queries.append((short_anchor, "OPENVERSE"))
                    queries.append(("police investigation night", "PEXELS"))
        else:
            if attempt_num < len(vibes):
                queries.append((vibes[attempt_num], src))
            else:
                ageless_fallbacks = [
                    "police flashing lights reflection wet night",
                    "fountain pen writing paper macro",
                    "ticking clock hands macro shadows"
                ]
                queries.append((ageless_fallbacks[attempt_num % len(ageless_fallbacks)], src))

        valid_pairs = []
        seen = set()
        with self.lock:
            for q, s in queries:
                q_clean = clean_query(q)
                if not q_clean or len(q_clean) < 3: continue
                key = f"{s}:{q_clean.lower()}"
                if key not in self.failed_queries.get(s, set()) and key not in seen:
                    valid_pairs.append((q_clean, s))
                    seen.add(key)

        if not valid_pairs:
            fallback_q = clean_query(entities[0] if cat == "ARCHIVE" else vibes[0]) or topic_short
            valid_pairs.append((fallback_q, filtered_sources[attempt_num % n_sources]))

        return valid_pairs

    def record_failure(self, query, source):
        with self.lock:
            self.failed_queries[source].add(f"{source}:{query.lower().strip()}")

QUERY_ENGINE = SmartQueryEngine()


class MediaPreFilter:
    SPAM_PATTERNS = [
        r"spectrogram", r"waveform", r"podcast", r"subscribe",
        r"christmas", r"wedding", r"baby", r"gameplay", r"minecraft",
        r"cooking", r"recipe", r"makeup", r"tutorial"
    ]

    @staticmethod
    def quick_validate(media_path, shot):
        if not media_path or not Path(media_path).exists():
            return False, "الملف غير موجود"
        path = Path(media_path)
        file_size = path.stat().st_size
        if file_size < PREFILTER_MIN_SIZE_BYTES:
            return False, f"حجم الملف صغير جداً ({file_size} bytes)"

        w, h = probe_dimensions(path)
        if w > 0 and h > 0:
            if w < h or (w / h) < 1.15:
                return False, f"مقطع رأسي غير متوافق مع الشاشة العريضة 16:9 ({w}x{h})"

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
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_wikipedia_image, query, image_path)
            elif source_name == "DUCKDUCKGO":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_duckduckgo_resilient, query, image_path)
            elif source_name == "FBI_ARCHIVE":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_fbi_archive, query, Path(f"{base_path}_{source_name}"))
            elif source_name == "YOUTUBE":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_youtube_clip, query, video_path, shot)
            elif source_name == "YARN":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_yarn_clip, query, video_path)
            elif source_name == "PEXELS":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_pexels_video, query, video_path)
            elif source_name == "PIXABAY":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_pixabay_video, query, video_path)
            elif source_name == "LOC":
                found_file, media_uid = await asyncio.to_thread(MediaSources.fetch_chronicling_america, query, image_path)
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


# =============================================================================
# ZERO-BLOCK RESILIENT MEDIA SOURCES
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
    def fetch_duckduckgo_resilient(q, output_path):
        """Bypasses Cloudflare 202 Ratelimit using real browser header session and Wikimedia fallback."""
        q_clean = clean_query(q)
        if not q_clean: return None, None
        try:
            # First attempt: Direct DuckDuckGo JSON with Chrome headers
            session = requests.Session()
            session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                "Referer": "https://duckduckgo.com/",
                "Accept": "*/*"
            })
            res_vqd = session.get(f"https://duckduckgo.com/?q={urllib.parse.quote(q_clean)}&t=h_", timeout=8)
            vqd_match = re.search(r'vqd=([\d\-]+)', res_vqd.text) or re.search(r'vqd="([\d\-]+)"', res_vqd.text)
            if vqd_match:
                vqd = vqd_match.group(1)
                img_url = f"https://duckduckgo.com/i.js?l=us-en&o=json&q={urllib.parse.quote(q_clean)}&vqd={vqd}&f=,,,&p=1"
                img_res = session.get(img_url, timeout=10)
                if img_res.status_code == 200:
                    results = img_res.json().get("results", [])
                    if results:
                        return MediaSources._track_and_save(results, output_path, lambda x: (x.get("image"), f"ddg_{hash(x.get('image'))}"))
        except Exception:
            pass

        # Intelligent Fallback: Instant Wikipedia article image pull (Zero Ratelimit)
        try:
            wiki_res = requests.get(
                f"https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={urllib.parse.quote(q_clean)}&gsrlimit=5&prop=pageimages&pithumbsize=1080&format=json",
                headers=API_HEADERS, timeout=8
            )
            if wiki_res.status_code == 200:
                pages = list(wiki_res.json().get("query", {}).get("pages", {}).values())
                return MediaSources._track_and_save(pages, output_path, lambda p: (p.get("thumbnail", {}).get("source"), f"wiki_{p.get('pageid')}"))
        except Exception:
            pass
        return None, None

    @staticmethod
    def fetch_youtube_clip(q, output_path, shot):
        """Bypass bot-detection using Android/web client and Node/Deno challenge solving."""
        q_clean = clean_query(q)
        if not q_clean: return None, None
        try:
            dur = max(3.0, float(shot.get("duration", 3.0)))
            target_query = f"{q_clean} interview"
            
            cmd_search = [
                "yt-dlp",
                "--extractor-args", "youtube:player_client=android,web",
                "--no-check-certificates",
                f"ytsearch1:{target_query}",
                "--get-id",
                "--no-playlist", "--quiet"
            ]
            res = subprocess.run(cmd_search, stdout=subprocess.PIPE, text=True, timeout=20)
            lines = res.stdout.strip().split("\n")
            if not lines or not lines[0]: return None, None
            video_id = lines[0].strip()

            with CONFIG.used_media_lock:
                if f"yt_{video_id}" in CONFIG.used_media_ids: return None, None

            video_url = f"https://www.youtube.com/watch?v={video_id}"
            sec_spec = f"*00:20-00:{int(20+dur):02d}"
            
            cmd_dl = [
                "yt-dlp",
                "--extractor-args", "youtube:player_client=android,web",
                "--no-check-certificates",
                "--download-sections", sec_spec,
                "-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best",
                "-o", str(output_path),
                "--force-keyframes-at-cuts",
                "--no-playlist", "--quiet",
                video_url
            ]
            dl_res = subprocess.run(cmd_dl, timeout=40)
            if dl_res.returncode == 0 and Path(output_path).exists() and Path(output_path).stat().st_size > 10240:
                return str(output_path), f"yt_{video_id}"
        except Exception:
            pass
        return None, None

    @staticmethod
    def fetch_yarn_clip(q, output_path):
        """Short spoken dialogue quote matching for yarn.co."""
        q_clean = clean_query(q)
        if not q_clean: return None, None
        try:
            quote = " ".join(q_clean.split()[:2])
            url = f"https://yarn.co/yarn-find?text={urllib.parse.quote(quote)}"
            res = requests.get(url, headers=API_HEADERS, timeout=10)
            if res.status_code == 200:
                clip_ids = re.findall(r'/yarn-clip/([a-zA-Z0-9\-]+)', res.text)
                if clip_ids:
                    random.shuffle(clip_ids)
                    for cid in clip_ids[:2]:
                        with CONFIG.used_media_lock:
                            if f"yarn_{cid}" in CONFIG.used_media_ids: continue
                        video_url = f"https://y.yarn.co/{cid}.mp4"
                        r = requests.get(video_url, headers=MEDIA_DOWNLOAD_HEADERS, timeout=15)
                        if r.status_code == 200 and len(r.content) > 10240:
                            with open(output_path, "wb") as f:
                                f.write(r.content)
                            return str(output_path), f"yarn_{cid}"
        except Exception:
            pass
        return None, None

    @staticmethod
    def fetch_wikipedia_image(q, o):
        q_clean = clean_query(q)
        if not q_clean: return None, None
        try:
            commons_url = "https://commons.wikimedia.org/w/api.php"
            params = {"action": "query", "generator": "search", "gsrsearch": f"{q_clean}", "gsrnamespace": 6, "gsrlimit": 15, "prop": "imageinfo", "iiprop": "url|mime|size", "format": "json"}
            res = requests.get(commons_url, headers=API_HEADERS, params=params, timeout=15)
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
            if not q_clean: return None, None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            query = f'({q_clean}) AND (mediatype:image OR mediatype:movies)'
            res = requests.get("https://archive.org/advancedsearch.php", headers=headers, params={"q": query, "fl[]": "identifier", "rows": 15, "output": "json"}, timeout=18)
            docs = res.json().get("response", {}).get("docs", [])
            random.shuffle(docs)
            for doc in docs:
                uid = str(doc.get("identifier"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                try:
                    meta = requests.get(f"https://archive.org/metadata/{uid}", headers=headers, timeout=15).json()
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
            res = requests.get("https://api.pexels.com/videos/search", headers=headers, params={"query": q, "per_page": 8}, timeout=15).json().get("videos", [])
            return MediaSources._track_and_save(res, o, lambda i: (sorted(i.get("video_files", []), key=lambda x: abs((x.get("width") or 0)-TARGET_W))[0].get("link") if i.get("video_files") else None, str(i.get("id"))))
        except: return None, None

    @staticmethod
    def fetch_pixabay_video(q, o):
        if not CONFIG.pixabay_key: return None, None
        try:
            res = requests.get("https://pixabay.com/api/videos/", headers=MEDIA_DOWNLOAD_HEADERS, params={"key": CONFIG.pixabay_key, "q": q, "per_page": 8}, timeout=15).json().get("hits", [])
            return MediaSources._track_and_save(res, o, lambda i: ((i.get("videos", {}).get("large") or i.get("videos", {}).get("medium", {})).get("url"), str(i.get("id"))))
        except: return None, None

    @staticmethod
    def fetch_chronicling_america(q, o):
        try:
            q_clean = clean_query(q)
            if not q_clean: return None, None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            url = f"https://www.loc.gov/photos/?fo=json&fa=online_format:image&c=15&q={urllib.parse.quote(q_clean)}"
            res = requests.get(url, headers=headers, timeout=15)
            results = res.json().get("results", [])
            def extract_loc(i):
                img_urls = i.get("image_url", [])
                if isinstance(img_urls, str): img_urls = [img_urls]
                return (img_urls[-1], str(i.get("id", img_urls[-1]))) if img_urls else (None, None)
            return MediaSources._track_and_save(results, o, extract_loc)
        except: return None, None

    @staticmethod
    def fetch_europeana(q, o):
        if not CONFIG.europeana_key: return None, None
        try:
            q_clean = clean_query(q)
            if not q_clean: return None, None
            params = {"wskey": CONFIG.europeana_key, "query": q_clean, "media": "true", "thumbnail": "true", "rows": 15, "profile": "rich", "qf": "TYPE:IMAGE"}
            res = requests.get("https://api.europeana.eu/record/v2/search.json", params=params, headers=API_HEADERS, timeout=15)
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
            if not q_clean: return None, None
            headers = {"Authorization": f"Bearer {token}", "User-Agent": API_HEADERS["User-Agent"]}
            res = requests.get("https://api.openverse.org/v1/images/", headers=headers, params={"q": q_clean, "page_size": 15, "license_type": "all-cc"}, timeout=15)
            if res.status_code == 200:
                results = res.json().get("results", [])
                return MediaSources._track_and_save(results, o, lambda item: (item.get("url"), f"openverse_{item.get('id')}"))
        except: pass
        return None, None


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
        except Exception:
            pass
        return None


def create_fallback_image(output_path):
    out_p = Path(output_path)
    res = run_cmd([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "color=c=0x0a0c10:s=1280x720",
        "-vf", "noise=alls=15:allf=t+u,vignette=PI/4",
        "-frames:v", "1", "-pix_fmt", "yuvj420p", "-q:v", "2",
        str(out_p)
    ])
    return is_valid_visual(out_p)


async def generate_ai_image(prompt, output_path, aspect_ratio="16:9"):
    log(f"🎨 إنشاء صورة مصغرة عبر AGY: '{prompt[:70]}...'", "info")
    full_prompt = f"[CRITICAL: NO TEXT ON IMAGE. OUTPUT RAW IMAGE ONLY] Photorealistic cinematic documentary archive photo: {prompt}. Aspect Ratio: {aspect_ratio}"
    try:
        out_p = Path(output_path)
        if out_p.exists(): out_p.unlink()

        cmd_binary = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", EFFORT_IMAGE_GEN, "--dangerously-skip-permissions", "-p", full_prompt]
        res_bin = await asyncio.to_thread(subprocess.run, cmd_binary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
        
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


def generate_chapter_transition_card(chapter_num, chapter_title, out_video_path, sfx_path=None, duration=2.2):
    log(f"🎬 توليد الفاصل السينمائي للفصل {chapter_num}: '{chapter_title}'...", "info")
    safe_title = chapter_title.replace("'", "").replace(":", "-").strip()
    font_file = find_system_arabic_font()
    
    draw_title = f"fontfile='{font_file}':" if font_file else ""
    vf_text = (
        f"color=c=0x060709:s=1920x1080:d={duration}:r={TARGET_FPS},"
        f"noise=alls=10:allf=t+u,vignette=PI/4,"
        f"drawtext={draw_title}text='محور التحقيق 0{chapter_num}':"
        f"x=(w-text_w)/2:y=(h-text_h)/2-55:fontsize=32:fontcolor=0x999999:alpha='if(lt(t,0.3),t/0.3,if(gt(t,{duration}-0.3),({duration}-t)/0.3,1))',"
        f"drawtext={draw_title}text='{safe_title}':"
        f"x=(w-text_w)/2:y=(h-text_h)/2+25:fontsize=56:fontcolor=white:shadowcolor=black@0.8:shadowx=3:shadowy=3:alpha='if(lt(t,0.3),t/0.3,if(gt(t,{duration}-0.3),({duration}-t)/0.3,1))'"
    )
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
1. HUMAN DEPTH & EMOTIONAL WEIGHT:
   - Highlight the human tragedy: victims' lives, family grief, and ethical stakes.
   - Balance forensic precision with deeply moving storytelling.
2. DYNAMIC PERIOD ANALYSIS:
   - Identify "target_era" (e.g. "Late 1960s (1968-1969)" or "Modern 2024").
   - List "forbidden_anachronisms": Things that must never appear if historical (e.g. smartphones, laptops, euro bills, modern cars for a 1960s topic; or leave empty if modern).
   - List "featured_adaptations": Specific famous movies/series made about this topic.
3. PART 1 MUST BE THE HOOK (45 to 65 seconds, ~110 to 140 Arabic words):
   - Fast, gripping paradox highlighting innocence disrupted by terror.
4. PARTS 2 THROUGH 8 (CHRONOLOGICAL CHAPTERS):
   - Part 2: Background, innocent lives, and historical context (~450 words)
   - Part 3: Crime scene & physical forensic evidence (~500 words)
   - Part 4: Mysterious letters & psychological press terror (~450 words)
   - Part 5: Breakthrough turning points & human testimonies (~450 words)
   - Part 6: Suspects & intense interrogations (~450 words)
   - Part 7: Conflicting theories & investigative debates (~400 words)
   - Part 8: Open cold case legacy, unhealed wounds, and conclusion (~350 words)
5. NARRATION RULE: Continuous Arabic narration without naming chapter numbers.

Return ONLY valid JSON:
{{
  "story_type": "investigation",
  "primary_english_query": "",
  "target_era": "",
  "forbidden_anachronisms": [],
  "featured_adaptations": [],
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

            log("\n" + "="*60)
            log(f"🕰️ الحقبة المستنتجة للقضية: {data.get('target_era', 'غير محددة')}")
            log(f"🎬 الأعمال السينمائية المرتبطة بالقضية: {', '.join(data.get('featured_adaptations', []))}")
            log(f"🚫 المحظورات الزمنية الصارمة: {', '.join(data.get('forbidden_anachronisms', []))}")
            for i in range(1, 9):
                part_key = f"part_{i}"
                if data.get(part_key):
                    log(f"📜 [السيناريو المولد - الجزء {i}]:")
                    log(data[part_key])
                    log("")
            log("="*60 + "\n")
            return data
        except Exception as e:
            log(f"⚠️ خطأ توليد السيناريو، تفعيل خطة الطوارئ: {e}", "warning")
            fallback = {
                "story_type": "investigation",
                "primary_english_query": clean_query(CONFIG.topic),
                "target_era": "Historical Investigation",
                "forbidden_anachronisms": ["smartphones", "laptops", "modern euro currency"],
                "featured_adaptations": ["Zodiac (2007)"],
                "hashtag": f"#{CONFIG.topic_clean[:25]}",
                "chapters": [
                    {"id": 1, "title": "المقدمة واللغز", "key": "part_1", "is_hook": True},
                    {"id": 2, "title": "خفايا التحقيق", "key": "part_2"}
                ],
                "part_1": f"تفاصيل غامضة وإنسانية عميقة حول {CONFIG.topic}.",
                "part_2": "تظل الحقيقة والعدالة غائبة حتى اليوم."
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
                        if str(item.get(k, "")).strip() == str(idx_int):
                            return item
            if 0 <= idx_int - 1 < len(board) and isinstance(board[idx_int - 1], dict):
                return board[idx_int - 1]

        if isinstance(board, dict):
            for wrapper in ["shots", "scenes", "storyboard", "data", "results", "board"]:
                if wrapper in board and isinstance(board[wrapper], (dict, list)):
                    found = StoryScoutEngine._find_shot_data(board[wrapper], idx_int)
                    if found: return found

            idx_str = str(idx_int)
            candidate_keys = [
                idx_str,
                f"shot_{idx_str}",
                f"shot_{idx_int:02d}",
                f"Shot {idx_str}",
                f"Shot_{idx_str}",
                f"shot {idx_str}",
                f"scene_{idx_str}",
                f"Scene {idx_str}",
                f"[{idx_str}]"
            ]
            for ck in candidate_keys:
                if ck in board and isinstance(board[ck], dict):
                    return board[ck]
                for actual_k, val in board.items():
                    if actual_k.lower().strip() == ck.lower().strip() and isinstance(val, dict):
                        return val

            for actual_k, val in board.items():
                if isinstance(val, dict):
                    if re.search(r'\b' + idx_str + r'\b', actual_k):
                        return val
        return None

    def direct_storyboard(self, shots):
        log("🎬 [المخرج الفني] هندسة كلمات البحث (إلزام نسبة 90% للأرشيف والمصادر التاريخية)...")
        batch_size = 70
        all_processed = []

        target_era = self.script.get("target_era", "")
        forbidden = ", ".join(self.script.get("forbidden_anachronisms", []))
        adaptations = ", ".join(self.script.get("featured_adaptations", []))

        for batch_start in range(0, len(shots), batch_size):
            batch = shots[batch_start:batch_start + batch_size]
            batch_end = batch_start + len(batch)
            log(f"🎬 معالجة دفعة المشاهد {batch_start+1}-{batch_end} من {len(shots)}...")

            shots_summary = "\n".join([f"[{s['index']}]: {s['text']}" for s in batch])
            prompt = f"""You are an Elite Visual Director and Expert Archival Video Researcher.
TOPIC: {self.script.get('primary_english_query', CONFIG.topic)}
TARGET ERA: {target_era}
FEATURED MOVIE ADAPTATIONS: {adaptations}
FORBIDDEN MODERN ITEMS: {forbidden}
[ID: {CONFIG.run_id}_{batch_start}]

Analyze ALL of these shots contextually based on the story:
{shots_summary}

STRICT ARCHIVE DISTRIBUTION RULE (CRITICAL):
- 85% to 90% of scenes MUST BE CATEGORIZED AS "ARCHIVE".
  Use content_type: "document_file", "historic_interview", "movie_clip", "person_mugshot", "location_photo", "newspaper_article".
- ONLY 10% to 15% maximum may be "CINEMATIC" (pure atmospheric B-roll like rain, fog, flashing police lights).

CRITICAL KEYWORD RULES (SURGICAL 2-3 WORDS):
1. KEEP ALL ENTITIES SHORT (2-3 words max): Never make long sentence queries! (e.g. 'D.B. Cooper bomb', NOT 'FBI bomb diagram D.B. Cooper case investigation file').
2. If "content_type" is "movie_clip": USE ONLY 2-word spoken dialogue quotes for Yarn (e.g. 'bomb briefcase', 'twenty dollars').
3. "exact_entities": 5 concise English search terms (2-3 words max each).
4. "visual_vibes": 5 concise physical period-neutral phrases (e.g. 'police lights night', 'revolver cylinder spinning').
5. "reviewer_context": Strict Arabic instructions ensuring authenticity.

MANDATORY JSON FORMAT:
Map string integer index directly to object:
{{
  "{batch[0]['index']}": {{
    "category": "ARCHIVE",
    "content_type": "document_file",
    "exact_entities": ["...", "..."],
    "visual_vibes": ["...", "..."],
    "reviewer_context": "تأكد من مطابقة الوثيقة للتحقيق",
    "accept_similar": true
  }}
}}"""
            try:
                result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", EFFORT_PRO_GENERATION, "--dangerously-skip-permissions", "-p", prompt], timeout=600)
                board = extract_json(result.stdout.strip())

                if batch_start == 0:
                    log("\n" + "🎥 "*15 + "[قرارات المخرج الفني - سيادة الأرشيف]" + " 🎥"*15)

                for shot in batch:
                    idx_int = shot["index"]
                    shot_data = self._find_shot_data(board, idx_int)

                    if shot_data and isinstance(shot_data, dict):
                        cat_raw = str(shot_data.get("category", "")).strip().upper()
                        shot["category"] = "CINEMATIC" if ("CINEMAT" in cat_raw and "ARCHIV" not in cat_raw) else "ARCHIVE"
                        shot["content_type"] = shot_data.get("content_type", "document_file" if shot["category"] == "ARCHIVE" else "dark_moody")
                        shot["exact_entities"] = [clean_query(e) for e in shot_data.get("exact_entities", []) if clean_query(e)] or [clean_query(CONFIG.topic), "police file"]
                        shot["visual_vibes"] = [clean_query(v) for v in shot_data.get("visual_vibes", []) if clean_query(v)] or ["police lights night", "dark street lamp"]
                        shot["reviewer_context"] = shot_data.get("reviewer_context", "تأكد من أصلية الوثيقة ومطابقتها للحقبة التاريخية.")
                        shot["accept_similar"] = shot_data.get("accept_similar", True)
                    else:
                        shot["category"] = "ARCHIVE"
                        shot["content_type"] = "document_file"
                        shot["exact_entities"] = [clean_query(CONFIG.topic), "police archive"]
                        shot["visual_vibes"] = ["police car night", "dark hallway shadows"]
                        shot["reviewer_context"] = "تأكد من ملاءمة اللقطة للنص الجنائي والحقبة التاريخية."
                        shot["accept_similar"] = True

                    q_disp = shot['exact_entities'][0] if shot['category'] == 'ARCHIVE' else shot['visual_vibes'][0]
                    log(f"📌 المشهد {shot['index']:02d} | الفئة: {shot['category']} ({shot['content_type']}) | البحث الأول: '{q_disp}'")

            except Exception as e:
                log(f"⚠️ خطأ في معالجة الدفعة: {e}", "warning")
                for shot in batch:
                    shot["category"] = "ARCHIVE"
                    shot["content_type"] = "document_file"
                    shot["exact_entities"] = [clean_query(CONFIG.topic), "police archive"]
                    shot["visual_vibes"] = ["police car night", "dark hallway shadows"]
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

        log(f"🎙️ بدء إنتاج التعليق الصوتي الماستر (معالجة نبرة إنسانية دافئة ومؤثرة)...")
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
                    voice_instruction = (
                        "[INSTRUCTION: Solemn, emotionally resonant, and gripping Arabic investigative documentary narrator. "
                        "Blend suspenseful authority with genuine empathy for the victims and the human tragedy. "
                        "Vary vocal cadence naturally: reflect warmth and grief in reflective moments, and build tension during revelations. "
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

        log(f"🎙️ Groq Whisper: مزامنة التوقيتات وتطهير النصوص من الشوائب ومربعات التوفو...")

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
                    raw_text = " ".join(x["word"] for x in cur).strip()
                    clean_text = re.sub(r"[\|]{2,}", " ", raw_text).strip()
                    clean_text = unicodedata.normalize('NFKC', clean_text)
                    clean_text = re.sub(r'[\u200B-\u200F\uFEFF\u00A0]', ' ', clean_text)
                    clean_text = re.sub(r"\s+", " ", clean_text).strip()

                    if clean_text:
                        raw_dur = max(0.5, item["end"] - s_start)
                        exact_frames = max(15, int(round(raw_dur * TARGET_FPS)))
                        quantized_dur = exact_frames / TARGET_FPS

                        shots.append({
                            "index": len(shots) + 1,
                            "start": s_start,
                            "end": s_start + quantized_dur,
                            "duration": quantized_dur,
                            "frames": exact_frames,
                            "text": clean_text,
                            "is_hook": is_hook,
                            "chapter_num": p_idx + 1
                        })
                    cur, s_start = [], item["end"]

            if cur:
                raw_text = " ".join(x["word"] for x in cur).strip()
                clean_text = re.sub(r"[\|]{2,}", " ", raw_text).strip()
                clean_text = unicodedata.normalize('NFKC', clean_text)
                clean_text = re.sub(r'[\u200B-\u200F\uFEFF\u00A0]', ' ', clean_text)
                clean_text = re.sub(r"\s+", " ", clean_text).strip()

                if clean_text:
                    raw_dur = max(0.5, cur[-1]["end"] - s_start)
                    exact_frames = max(15, int(round(raw_dur * TARGET_FPS)))
                    quantized_dur = exact_frames / TARGET_FPS
                    shots.append({
                        "index": len(shots) + 1,
                        "start": s_start,
                        "end": s_start + quantized_dur,
                        "duration": quantized_dur,
                        "frames": exact_frames,
                        "text": clean_text,
                        "is_hook": is_hook,
                        "chapter_num": p_idx + 1
                    })

            timeline_offset += dur

        log(f"✂️ تم تقسيم الصوت بدقة إلى {len(shots)} مشهد بدون أي شوائب نصية.")
        return shots, chapter_timeline


async def agy_evaluate_scout(media_path, shot, story, source_name, query):
    if not media_path: return False, 0.0, 0.0, "الملف غير موجود في المسار"
    prefilter_ok, prefilter_reason = MediaPreFilter.quick_validate(media_path, shot)
    if not prefilter_ok: return False, 0.0, 0.0, prefilter_reason

    target_era = story.get("target_era", "Historical")
    forbidden = ", ".join(story.get("forbidden_anachronisms", []))

    prompt = f"""You evaluate documentary media suitability strictly based on the context and temporal era.
TOPIC: {story.get("primary_english_query", CONFIG.topic)}
TARGET ERA: {target_era}
FORBIDDEN ANACHRONISMS: {forbidden}

SHOT SCRIPT TEXT: "{shot['text']}"
SHOT CATEGORY: {shot['category']}
RETRIEVED FROM: {source_name}
SEARCH QUERY: "{query}"
LOCAL PATH: {Path(media_path).absolute()}
DIRECTOR NOTE: {shot.get("reviewer_context", "")}
ACCEPT SIMILAR: {shot.get("accept_similar", True)}

CRITICAL EVALUATION RULES:
1. TEMPORAL ACCURACY: If the story era is historical, and forbidden modern anachronisms appear (e.g. smartphones, modern cars, laptops, euros), REJECT IMMEDIATELY with score 0.0.
2. If CATEGORY is "ARCHIVE": Accept genuine historical evidence, authentic interview clips, case movies, newspaper clippings, or vintage photos.
3. If CATEGORY is "CINEMATIC": Do NOT demand literal text match. Accept mood, noir atmosphere, rain, fog, vintage closeups, flashing lights, or shadows. Be flexible on mood, ruthless on modern anachronisms.

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
    cat = shot.get("category", "ARCHIVE")
    dur = float(shot.get("duration", 3.0))
    
    if shot.get('best_candidate') and shot['best_score'] >= 0.15:
        cand_path = Path(shot['best_candidate']['path'])
        if cand_path.exists():
            log(f"⚠️ [إنقاذ 1] المشهد {index}: اعتماد أفضل لقطة حقيقية (تقييم {shot['best_score']:.2f}).", "warning")
            return shot['best_candidate']

    log(f"🎬 [إنقاذ 2] توليد خلفية سينمائية للمشهد {index}.", "warning")
    fallback_path = CONFIG.work_dir / f"selected_shot_{index:03d}_fallback.mp4"
    if await create_fallback_visual(fallback_path, duration=dur):
        return {"shot": shot, "path": str(fallback_path), "source": "CINEMATIC_BG", "score": 0.0, "start": 0.0, "duration": dur}

    log(f"🤖 [إنقاذ نهائي] توليد صورة AI للمشهد {index}.", "error")
    ai_path = CONFIG.work_dir / f"selected_shot_{index:03d}_ai.jpg"
    query = " ".join(shot.get("exact_entities", [])[:3]) if cat == "ARCHIVE" else " ".join(shot.get("visual_vibes", [])[:3])
    if await generate_ai_image(query, ai_path):
        return {"shot": shot, "path": str(ai_path), "source": "AI_GENERATED", "score": 1.0, "start": 0.0, "duration": dur}

    black_path = CONFIG.work_dir / f"selected_shot_{index:03d}_black.mp4"
    await create_fallback_visual(black_path, duration=dur)
    return {"shot": shot, "path": str(black_path), "source": "FFMPEG", "score": 0.0, "start": 0.0, "duration": dur}


# =============================================================================
# PRODUCTION PIPELINE
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

    log(f"🚀 تشغيل خط الإنتاج الذكي (سيادة الأرشيف 90%) | إجمالي المشاهد: {total_shots} | أقصى محاولات: {MAX_ATTEMPTS_PER_SHOT}")

    async def process_shot(shot):
        index = shot["index"]
        cat = shot.get("category", "ARCHIVE")
        base = CONFIG.work_dir / f"raw_shot_{index:03d}"

        while shot['status'] != 'DONE' and shot['attempts'] < MAX_ATTEMPTS_PER_SHOT:
            attempt_num = shot['attempts']
            query_tiers = QUERY_ENGINE.generate_query_tiers(shot, attempt_num)
            pairs_to_try = query_tiers[:2] if (attempt_num < 2 and len(query_tiers) >= 2) else query_tiers[:1]

            log(f"⚡ ({attempt_num+1}/{MAX_ATTEMPTS_PER_SHOT}م) المشهد {index} | "
                f"{'، '.join(f'{s}:{q}' for q,s in pairs_to_try)}", "info")

            fetch_results = await PARALLEL_FETCHER.fetch_from_multiple_sources(pairs_to_try, shot, base)
            if not fetch_results:
                for q, src in pairs_to_try:
                    QUERY_ENGINE.record_failure(q, src)
                log(f"⏩ المشهد {index}: لم يعثر على نتائج من أي مصدر.", "info")
                shot['attempts'] += 1
                continue

            found_acceptable = False
            for found_file, media_uid, src_name, query in fetch_results:
                if not found_file or not Path(found_file).exists():
                    QUERY_ENGINE.record_failure(query, src_name)
                    continue

                output_path = Path(found_file)
                pre_ok, pre_reason = MediaPreFilter.quick_validate(output_path, shot)
                if not pre_ok:
                    log(f"⏩ المشهد {index}: استبعاد {output_path.name} ({pre_reason}).", "debug")
                    QUERY_ENGINE.record_failure(query, src_name)
                    output_path.unlink(missing_ok=True)
                    continue

                async with REVIEWER_SEMAPHORE:
                    accepted, score, start, reason = await agy_evaluate_scout(output_path, shot, story, src_name, query)

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
                    log(f"🎯 المشهد {index}: قُبِل من {src_name} ({cat}) | تقييم: {score:.2f} | {reason[:80]}")
                    selected_path = CONFIG.work_dir / f"selected_shot_{index:03d}{output_path.suffix}"
                    if selected_path.exists(): selected_path.unlink(missing_ok=True)
                    shutil.move(str(output_path), str(selected_path))

                    res_item = {
                        "shot": shot, "path": str(selected_path), "source": src_name,
                        "score": score, "start": start, "duration": dur
                    }
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

                if shot['status'] != 'DONE' and shot['attempts'] >= 8 and shot['best_score'] >= 0.25 and shot['best_candidate']:
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

    async def throttled_process(shot):
        async with shot_semaphore:
            await process_shot(shot)

    tasks = [asyncio.create_task(throttled_process(shot)) for shot in shots]
    await asyncio.gather(*tasks)
    if not completion_event.is_set(): completion_event.set()
    gc.collect()

    final_dict = {}
    for r in completed_results:
        final_dict[r["shot"]["index"]] = r
    return [final_dict[s["index"]] for s in shots if s["index"] in final_dict]


# =============================================================================
# ZERO-DRIFT ASSEMBLY ENGINE
# =============================================================================

class AssemblyEngine:
    def render_sub_clip(self, item):
        shot, index = item["shot"], item["shot"]["index"]
        media_path = Path(item["path"])
        output = CONFIG.work_dir / f"rendered_{index:03d}.mp4"
        exact_frames = int(shot.get("frames", round(shot.get("duration", 3.0) * TARGET_FPS)))

        if not media_path.exists() or media_path.stat().st_size < 1024:
            log(f"⚠️ تنبيه: الملف للمشهد {index} غير متوفر، جاري توليد بديل فوري...", "warning")
            asyncio.run(create_fallback_visual(output, duration=exact_frames/TARGET_FPS))
            return output

        start = min(float(item.get("start", 0)), max(0, probe_duration(media_path) - 0.1))
        log(f"✂️ جاري رندرة المشهد {index} ({exact_frames} إطار ثابت)...", "debug")

        if media_path.suffix.lower() in (".mp4", ".mov"):
            filter_complex = build_blur_background_filter_video()
            res = run_cmd([
                "ffmpeg", "-y", "-ss", str(start), "-i", str(media_path),
                "-filter_complex", filter_complex,
                "-frames:v", str(exact_frames),
                "-fps_mode", "cfr", "-r", str(TARGET_FPS),
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", str(output)
            ])
        else:
            filter_complex = build_blur_background_filter_image(ken_burns=True)
            res = run_cmd([
                "ffmpeg", "-y", "-loop", "1", "-i", str(media_path),
                "-filter_complex", filter_complex,
                "-frames:v", str(exact_frames),
                "-fps_mode", "cfr", "-r", str(TARGET_FPS),
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p", str(output)
            ])

        if res.returncode != 0:
            vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,fps={TARGET_FPS}"
            if media_path.suffix.lower() in (".mp4", ".mov"):
                res = run_cmd(["ffmpeg", "-y", "-ss", str(start), "-i", str(media_path), "-vf", vf, "-frames:v", str(exact_frames), "-fps_mode", "cfr", "-r", str(TARGET_FPS), "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)])
            else:
                res = run_cmd(["ffmpeg", "-y", "-loop", "1", "-i", str(media_path), "-vf", vf, "-frames:v", str(exact_frames), "-fps_mode", "cfr", "-r", str(TARGET_FPS), "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)])

        if res.returncode != 0:
            asyncio.run(create_fallback_visual(output, duration=exact_frames/TARGET_FPS))

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

    def assemble_final_cut(self, rendered_items, shots, chapter_timeline, hashtag):
        log("🎞️ تجهيز المونتاج النهائي ومحاذاة التايم لاين بالمللي ثانية...", "info")

        normalized_intro = None
        intro_dur = 0.0
        if CONFIG.intro_path and Path(CONFIG.intro_path).exists() and Path(CONFIG.intro_path).stat().st_size > 1024:
            intro_dur = probe_duration(CONFIG.intro_path)
            if intro_dur > 1.0:
                normalized_intro = CONFIG.work_dir / "normalized_intro.mp4"
                log(f"🎬 تطبيع الإنترو ({intro_dur:.1f} ثانية) بمواصفات البث...", "info")
                run_cmd([
                    "ffmpeg", "-y", "-i", str(CONFIG.intro_path),
                    "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease:force_divisible_by=2,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,fps={TARGET_FPS}",
                    "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-ar", "48000", "-ac", "2", str(normalized_intro)
                ])

        final_video_sequence = []
        final_audio_segments = []
        youtube_chapters = []
        current_time = 0.0
        chapter_offsets = {}

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

            if ch_num >= 2:
                trans_card = CONFIG.work_dir / f"trans_card_ch_{ch_num:02d}.mp4"
                created_card = generate_chapter_transition_card(ch_num, ch_title, trans_card, CONFIG.chapter_sfx_path, duration=2.2)
                if created_card:
                    final_video_sequence.append(str(trans_card))
                    card_audio = CONFIG.work_dir / f"card_audio_ch_{ch_num:02d}.wav"
                    run_cmd(["ffmpeg", "-y", "-i", str(trans_card), "-vn", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(card_audio)])
                    final_audio_segments.append(str(card_audio))
                    current_time += 2.2

            chapter_offsets[ch_num] = current_time - ch_info["start_time"]

            items = chapter_shots.get(ch_num, [])
            for it in items:
                v_path = CONFIG.work_dir / f"rendered_{it['shot']['index']:03d}.mp4"
                if v_path.exists():
                    final_video_sequence.append(str(v_path))
                    current_time += it['shot']['duration']

            ch_narration = CONFIG.work_dir / f"chapter_{ch_num:02d}.wav"
            if ch_narration.exists():
                norm_audio = CONFIG.work_dir / f"norm_audio_{ch_num:02d}.wav"
                run_cmd(["ffmpeg", "-y", "-i", str(ch_narration), "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(norm_audio)])
                final_audio_segments.append(str(norm_audio))

        sub_path = CONFIG.work_dir / "subtitles_sync.ass"
        with open(sub_path, "w", encoding="utf-8") as f:
            f.write(
                "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n"
                "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
                "Style: Default,Noto Sans Arabic,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,2.5,1.5,2,80,80,68,1\n"
                "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            )
            for s in shots:
                ch = s.get("chapter_num", 1)
                offset = chapter_offsets.get(ch, 0.0)
                s_start = s["start"] + offset
                s_end = s["end"] + offset
                h1, m1 = int(s_start // 3600), int((s_start % 3600) // 60)
                h2, m2 = int(s_end // 3600), int((s_end % 3600) // 60)
                t_clean = s['text'].replace("\\", r"\\")
                f.write(f"Dialogue: 0,{h1}:{m1:02d}:{s_start%60:05.2f},{h2}:{m2:02d}:{s_end%60:05.2f},Default,,0,0,0,,{{\\fad(100,100)}}{t_clean}\n")

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
        sub_filter = "subtitles=" + str(Path(sub_path).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")

        title_file = CONFIG.work_dir / "title_tag.txt"
        safe_display_title = f"{CONFIG.topic[:35]} | #{CONFIG.topic_clean[:20]}"
        with open(title_file, "w", encoding="utf-8") as tf:
            tf.write(safe_display_title)

        font_file = find_system_arabic_font()
        has_logo = CONFIG.logo_path and Path(CONFIG.logo_path).exists() and Path(CONFIG.logo_path).stat().st_size > 1024

        filter_complex_parts = [f"[0:v]{sub_filter}[v_sub]"]
        current_v = "[v_sub]"

        if has_logo:
            filter_complex_parts.append(f"[2:v]scale=180:-1[logo_scaled]")
            filter_complex_parts.append(f"{current_v}[logo_scaled]overlay=W-w-50:50:enable='{intro_mask}':format=auto[v_logo]")
            current_v = "[v_logo]"

        if font_file:
            safe_title_path = str(title_file.resolve()).replace("\\", "/").replace(":", "\\:")
            filter_complex_parts.append(
                f"{current_v}drawtext=fontfile='{font_file}':textfile='{safe_title_path}':"
                f"x=50:y=50:fontsize=32:fontcolor=white@0.85:shadowcolor=black@0.7:shadowx=2:shadowy=2:"
                f"enable='{intro_mask}'[v_final]"
            )
        else:
            filter_complex_parts.append(f"{current_v}null[v_final]")

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

        desc_text = f"وثائقي استقصائي شامل: {CONFIG.topic}\n\nفصول الوثائقي:\n" + "\n".join(youtube_chapters) + f"\n\n#{CONFIG.topic_clean[:25]}"
        with open(CONFIG.description_file, "w", encoding="utf-8") as f:
            f.write(desc_text)

        log(f"🎉 تم إنتاج الوثائقي التلفزيوني بنجاح تام! | المدة: {probe_duration(CONFIG.final_video)/60:.2f} دقيقة | الحجم: {CONFIG.final_video.stat().st_size/1024/1024:.1f} MB", "info")
        return CONFIG.final_video, desc_text


class GoogleUploader:
    def __init__(self, cid, csec, ref, drive_folder_id):
        self.drive_folder_id = drive_folder_id
        self.creds = Credentials(None, refresh_token=ref, token_uri="https://oauth2.googleapis.com/token", client_id=cid, client_secret=csec) if cid and csec and ref else None

    def upload_all(self, vid_path, thumb_path, title, description=""):
        if not self.creds: return
        final_display_title = title or CONFIG.topic or "وثائقي استقصائي"
        try:
            drive = build('drive', 'v3', credentials=self.creds, cache_discovery=False)
            body = {'name': f"{final_display_title}.mp4"}
            if self.drive_folder_id:
                body['parents'] = [self.drive_folder_id]

            df = drive.files().create(
                body=body,
                media_body=MediaFileUpload(str(vid_path), mimetype='video/mp4', resumable=True),
                fields='id, webViewLink'
            ).execute()
            log(f"✅ Google Drive: تم الرفع بنجاح! الرابط: https://drive.google.com/file/d/{df.get('id')}/view", "info")

            yt = build('youtube', 'v3', credentials=self.creds, cache_discovery=False)
            yt_body = {
                'snippet': {
                    'title': final_display_title[:95],
                    'description': description or f"وثائقي: {final_display_title}\nإنتاج تلفزيوني استقصائي تلقائي.",
                    'tags': ['وثائقي', 'جريمة', 'غموض', 'تحقيق', 'تاريخ'],
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
            log(f"✅ YouTube: تم الرفع بالعنوان العربي الكامل والفصول التلقائية! https://youtu.be/{vid_id}", "info")

            if thumb_path.exists() and thumb_path.stat().st_size > 1024:
                try:
                    yt.thumbnails().set(videoId=vid_id, media_body=MediaFileUpload(str(thumb_path), mimetype='image/jpeg')).execute()
                    log("✅ تم رفع الصورة المصغرة لليوتيوب بنجاح تام.", "info")
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
    final_video, desc_text = assembly.assemble_final_cut(rendered_shot_items, shots, chapter_timeline, hashtag)

    log("🎨 توليد الصورة المصغرة (Thumbnail) الاحترافية بصيغة JPEG صالحة...", "info")
    await generate_ai_image(story.get('primary_english_query', CONFIG.topic), CONFIG.thumbnail, "16:9")

    uploader = GoogleUploader(CONFIG.google_client_id, CONFIG.google_client_secret, CONFIG.google_refresh_token, CONFIG.drive_folder_id)
    await asyncio.to_thread(uploader.upload_all, final_video, CONFIG.thumbnail, CONFIG.topic, desc_text)

    log(f"\n{'='*60}\n🏁 اكتمل إنتاج الوثائقي التلفزيوني بنجاح واحترافية متكاملة.\n{'='*60}\n", "info")
    PARALLEL_FETCHER.shutdown()
    gc.collect()


if __name__ == "__main__":
    try:
        asyncio.run(main_pipeline())
    except KeyboardInterrupt:
        log("🛑 تم الإيقاف يدوياً.", "warning")
        sys.exit(0)
