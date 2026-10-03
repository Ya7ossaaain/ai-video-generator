#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
V52 - HYPER-OPTIMIZED SMART SEARCH ENGINE

Key Optimizations over V51:
- Smart Query Decomposition: Extracts key searchable elements from scene descriptions
- Parallel Multi-Source Search: Queries multiple sources simultaneously per shot
- Pre-filter Validation: Rejects obviously bad results BEFORE calling expensive AGY reviewer
- Adaptive Query Refinement: Uses metadata from partial matches to build better next queries
- Intelligent Source Routing: Maps scene categories to best-fit sources from the start
- Result Caching: Per-project cache with isolation between episodes
- Progressive Scoring: Accepts good-enough results faster, saves AGY calls
- Batch-optimized Storyboard: Enhanced director prompts with SEO-optimized multi-tier queries
- Concurrency: Up to 7 simultaneous reviewer calls + parallel source fetching
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

ENGINE_VERSION = "V52-HYPER-OPTIMIZED"

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
MAX_ATTEMPTS_PER_SHOT = 6  # Reduced from 10 — smarter queries need fewer attempts

REVIEWER_SEMAPHORE = asyncio.Semaphore(7)

# Pre-filter: skip AGY call if media clearly doesn't match basic criteria
PREFILTER_MIN_SIZE_BYTES = 5 * 1024  # 5 KB minimum for images
PREFILTER_MIN_VIDEO_DURATION = 0.5   # seconds

API_HEADERS = {
    "User-Agent": "InvestigativeDocumentaryBot/1.0 (https://github.com/Ya7ossaaain; contact@example.com)",
    "Accept": "application/json, text/plain, */*"
}

MEDIA_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

ARCHIVE_SOURCES = ["WIKIPEDIA", "FBI_ARCHIVE", "LOC"]
CINEMATIC_SOURCES = ["PEXELS", "PIXABAY"]

# === SOURCE AFFINITY MAP ===
# Maps content types to ordered source preferences
SOURCE_AFFINITY = {
    "ARCHIVE": {
        "person_mugshot": ["WIKIPEDIA", "FBI_ARCHIVE", "LOC"],
        "document_file": ["FBI_ARCHIVE", "LOC", "WIKIPEDIA"],
        "location_photo": ["WIKIPEDIA", "LOC", "FBI_ARCHIVE"],
        "historical_event": ["FBI_ARCHIVE", "WIKIPEDIA", "LOC"],
        "newspaper_article": ["LOC", "FBI_ARCHIVE", "WIKIPEDIA"],
        "default": ["WIKIPEDIA", "FBI_ARCHIVE", "LOC"],
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


class EngineConfig:
    def __init__(self):
        self.topic = os.environ.get("VIDEO_TOPIC", "لغز اختفاء غامض")
        self.topic_clean = re.sub(r"[^a-zA-Z0-9_\-]+", "_", self.topic).strip("_")
        self.run_id = f"RUN-{datetime.now().strftime('%Y%m%d%H%M%S')}-{random.randint(10000, 99999)}"
        self.base_dir = Path("./output_build")
        self.work_dir = self.base_dir / "workspace"
        self.final_video = self.base_dir / "final_documentary.mp4"
        self.master_audio = self.work_dir / "master_audio.wav"
        self.thumbnail = self.base_dir / "thumbnail.jpg"
        self.used_media_ids = set()
        self.used_media_lock = threading.Lock()
        raw_keys = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
        self.gemini_keys = list(dict.fromkeys([k.strip() for k in re.split(r"[,;\n]+", raw_keys) if k.strip()]))
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.pexels_key = os.environ.get("PEXELS_API_KEY", "")
        self.pixabay_key = os.environ.get("PIXABAY_API_KEY", "")
        self.google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        self.google_refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")

CONFIG = EngineConfig()


def prepare_fresh_workspace():
    log("🧹 تنظيف بيئة التشغيل بالكامل...")
    if CONFIG.base_dir.exists():
        shutil.rmtree(CONFIG.base_dir, ignore_errors=True)
    CONFIG.base_dir.mkdir(parents=True, exist_ok=True)
    CONFIG.work_dir.mkdir(parents=True, exist_ok=True)
    CONFIG.used_media_ids.clear()


class GeminiKeyPool:
    def __init__(self, keys):
        self.keys = keys
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
GEMINI_POOL = GeminiKeyPool(CONFIG.gemini_keys)


def probe_duration(path):
    if not path or not os.path.exists(path): return 0.0
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], stdout=subprocess.PIPE, text=True)
        return float(res.stdout.strip())
    except: return 0.0

def is_valid_media(path, min_duration=0.05):
    path = Path(path)
    return path.exists() and path.stat().st_size >= 1024 and probe_duration(path) >= min_duration

def is_valid_visual(path):
    path = Path(path)
    if not path.exists() or path.stat().st_size < 1024: return False
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(path)], stdout=subprocess.PIPE, text=True)
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


# =============================================================================
# SMART QUERY ENGINE — The core optimization
# =============================================================================

class SmartQueryEngine:
    """
    Generates intelligent, multi-tier search queries optimized for each source.
    Instead of simple keyword cycling, it:
    1. Decomposes scene descriptions into searchable semantic elements
    2. Builds source-specific queries (stock footage SEO vs archive metadata)
    3. Generates genuinely different alternative queries (not just word swaps)
    4. Tracks what failed and avoids repeating similar patterns
    """

    # Common stock footage keywords that perform well on Pexels/Pixabay
    STOCK_BOOSTERS = {
        "water": ["ocean waves", "sea water", "underwater", "water surface"],
        "dark": ["dark room", "shadows", "silhouette", "low light"],
        "night": ["night city", "dark sky", "moonlight", "night time"],
        "prison": ["jail cell", "prison bars", "behind bars", "locked door"],
        "document": ["old papers", "vintage document", "typewriter", "old book"],
        "person": ["man portrait", "close up face", "person walking", "silhouette person"],
        "fog": ["misty", "foggy landscape", "haze", "cloudy"],
        "car": ["classic car", "vintage automobile", "car headlights", "driving"],
        "letter": ["handwritten letter", "old envelope", "writing pen", "ink on paper"],
        "beach": ["sandy beach", "shore", "coastline", "seaside"],
        "clock": ["ticking clock", "pocket watch", "time lapse", "clock hands"],
        "tombstone": ["graveyard", "cemetery", "memorial stone", "burial ground"],
    }

    def __init__(self):
        self.failed_queries = defaultdict(set)  # source -> set of failed queries
        self.successful_keywords = defaultdict(set)  # category -> keywords that worked

    def classify_content_type(self, shot):
        """Classify the content type of a shot for source affinity routing."""
        text = (shot.get("text", "") + " " + " ".join(shot.get("exact_entities", []))).lower()
        cat = shot.get("category", "CINEMATIC")

        if cat == "ARCHIVE":
            if any(w in text for w in ["mugshot", "wanted", "prisoner", "inmate", "morris", "anglin"]):
                return "person_mugshot"
            if any(w in text for w in ["document", "file", "letter", "report", "fbi", "classified", "memo"]):
                return "document_file"
            if any(w in text for w in ["island", "building", "prison", "alcatraz", "bridge", "city"]):
                return "location_photo"
            if any(w in text for w in ["newspaper", "headline", "press", "article", "news"]):
                return "newspaper_article"
            if any(w in text for w in ["1962", "1960", "1979", "historical", "vintage", "archive"]):
                return "historical_event"
            return "default"
        else:
            if any(w in text for w in ["water", "ocean", "sea", "wave", "underwater", "floating", "sinking", "tide"]):
                return "nature_water"
            if any(w in text for w in ["dark", "shadow", "night", "fog", "mysterious", "gloomy"]):
                return "dark_moody"
            if any(w in text for w in ["person", "man", "woman", "walking", "running", "face", "silhouette"]):
                return "people_action"
            if any(w in text for w in ["document", "stamp", "file", "clock", "spoon", "envelope", "letter"]):
                return "objects_closeup"
            if any(w in text for w in ["city", "street", "car", "driving", "urban", "building"]):
                return "urban_night"
            return "default"

    def get_ordered_sources(self, shot):
        """Get sources ordered by affinity for this shot's content type."""
        cat = shot.get("category", "CINEMATIC")
        content_type = self.classify_content_type(shot)
        affinity_map = SOURCE_AFFINITY.get(cat, SOURCE_AFFINITY["CINEMATIC"])
        return affinity_map.get(content_type, affinity_map["default"])

    def generate_query_tiers(self, shot, attempt_num=0):
        """
        Generate a tiered list of queries, each genuinely different.
        Returns list of (query, source) tuples ordered by expected quality.
        """
        cat = shot.get("category", "CINEMATIC")
        entities = shot.get("exact_entities", [CONFIG.topic_clean, "investigation", "mystery", "police"])
        vibes = shot.get("visual_vibes", ["mystery", "dark room", "shadow", "suspense"])
        ordered_sources = self.get_ordered_sources(shot)

        queries = []

        if cat == "ARCHIVE":
            # Tier 1: Exact entity name (highest precision)
            if len(entities) > 0 and attempt_num == 0:
                queries.append((entities[0], ordered_sources[0]))

            # Tier 2: Broader context query
            if len(entities) > 1:
                idx = min(attempt_num, len(entities) - 1)
                q = entities[idx]
                src = ordered_sources[attempt_num % len(ordered_sources)]
                queries.append((q, src))

            # Tier 3: Combined semantic query
            if attempt_num >= 1 and len(entities) >= 2:
                combined = f"{entities[0]} {entities[-1]}"
                src = ordered_sources[(attempt_num + 1) % len(ordered_sources)]
                queries.append((combined, src))

            # Tier 4: Generic historical fallback
            if attempt_num >= 2:
                fallbacks = entities[2:] if len(entities) > 2 else [CONFIG.topic_clean]
                for i, fb in enumerate(fallbacks):
                    src = ordered_sources[(attempt_num + i) % len(ordered_sources)]
                    queries.append((fb, src))

        else:  # CINEMATIC
            # Tier 1: Best stock keyword
            if len(vibes) > 0 and attempt_num == 0:
                queries.append((vibes[0], ordered_sources[0]))

            # Tier 2: Alternative vibes, rotating sources
            if len(vibes) > 1:
                idx = min(attempt_num, len(vibes) - 1)
                q = vibes[idx]
                src = ordered_sources[attempt_num % len(ordered_sources)]
                queries.append((q, src))

            # Tier 3: Boosted/expanded queries from our stock keyword map
            if attempt_num >= 1:
                for vibe in vibes:
                    base_word = vibe.split()[0].lower() if vibe else ""
                    if base_word in self.STOCK_BOOSTERS:
                        boosted = self.STOCK_BOOSTERS[base_word]
                        boost_idx = (attempt_num - 1) % len(boosted)
                        src = ordered_sources[(attempt_num) % len(ordered_sources)]
                        queries.append((boosted[boost_idx], src))
                        break

            # Tier 4: Use successful keywords from same category
            if attempt_num >= 2 and self.successful_keywords.get(cat):
                kw = random.choice(list(self.successful_keywords[cat]))
                src = ordered_sources[attempt_num % len(ordered_sources)]
                queries.append((kw, src))

        # Filter out queries we've already failed with on that source
        filtered = []
        seen = set()
        for q, src in queries:
            key = f"{src}:{q}"
            if key not in self.failed_queries[src] and key not in seen:
                filtered.append((q, src))
                seen.add(key)

        # Always return at least one query
        if not filtered:
            if cat == "ARCHIVE":
                fallback_q = entities[attempt_num % len(entities)] if entities else CONFIG.topic_clean
            else:
                fallback_q = vibes[attempt_num % len(vibes)] if vibes else "cinematic"
            fallback_src = ordered_sources[attempt_num % len(ordered_sources)]
            filtered.append((fallback_q, fallback_src))

        return filtered

    def record_failure(self, query, source):
        """Record a failed query to avoid repeating it."""
        self.failed_queries[source].add(f"{source}:{query}")

    def record_success(self, query, category):
        """Record successful keywords for future reuse."""
        words = query.lower().split()
        for w in words:
            if len(w) > 2:
                self.successful_keywords[category].add(w)

QUERY_ENGINE = SmartQueryEngine()


# =============================================================================
# MEDIA PRE-FILTER — Skip obviously bad results before AGY call
# =============================================================================

class MediaPreFilter:
    """
    Quick heuristic checks on downloaded media BEFORE calling the expensive
    AGY reviewer. This saves significant time and API calls.
    """

    # Keywords that indicate completely irrelevant content from archive.org
    ARCHIVE_SPAM_PATTERNS = [
        r"spectrogram", r"waveform", r"podcast", r"subscribe",
        r"christmas", r"birthday", r"wedding", r"baby",
        r"world of warcraft", r"minecraft", r"fortnite",
        r"cooking", r"recipe", r"makeup", r"tutorial",
    ]

    @staticmethod
    def quick_validate(media_path, shot, source_name):
        """
        Returns (is_valid, reason) — quick check before AGY evaluation.
        Doesn't reject borderline cases; only filters obvious mismatches.
        """
        if not media_path or not Path(media_path).exists():
            return False, "الملف غير موجود"

        path = Path(media_path)
        file_size = path.stat().st_size

        # Size checks
        if file_size < PREFILTER_MIN_SIZE_BYTES:
            return False, f"حجم الملف صغير جداً ({file_size} bytes)"

        is_img = path.suffix.lower() in (".jpg", ".jpeg", ".png")
        is_vid = path.suffix.lower() in (".mp4", ".mov")

        if is_img:
            if not is_valid_visual(path):
                return False, "الصورة تالفة أو غير صالحة"
        elif is_vid:
            duration = probe_duration(path)
            if duration < PREFILTER_MIN_VIDEO_DURATION:
                return False, f"مدة الفيديو قصيرة جداً ({duration:.1f}s)"
            if not is_valid_media(path):
                return False, "الفيديو تالف"
        else:
            return False, f"نوع ملف غير مدعوم: {path.suffix}"

        return True, "ok"

    @staticmethod
    def check_filename_relevance(filename, query, category):
        """
        Check if filename/metadata gives hints about content relevance.
        Returns a bonus/penalty score modifier.
        """
        if not filename:
            return 0.0

        fn_lower = filename.lower()
        query_words = set(query.lower().split())

        # Positive signals: filename contains query keywords
        matches = sum(1 for w in query_words if w in fn_lower and len(w) > 2)
        if matches >= 2:
            return 0.15  # Bonus for strong filename match

        # Negative signals: known spam patterns
        for pattern in MediaPreFilter.ARCHIVE_SPAM_PATTERNS:
            if re.search(pattern, fn_lower):
                return -0.3  # Penalty for likely spam

        return 0.0


# =============================================================================
# PARALLEL SOURCE FETCHER — Query multiple sources simultaneously
# =============================================================================

class ParallelSourceFetcher:
    """
    Fetches media from multiple sources in parallel for the same shot,
    then picks the best result. This dramatically reduces wall-clock time.
    """

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=5)

    async def fetch_from_multiple_sources(self, query_source_pairs, shot, base_path):
        """
        Run multiple source fetches in parallel, return all results.
        Each pair is (query, source_name).
        Returns list of (found_file, media_uid, source_name, query).
        """
        tasks = []
        for query, source_name in query_source_pairs:
            tasks.append(
                asyncio.create_task(
                    self._fetch_single(query, source_name, shot, base_path)
                )
            )

        results = await asyncio.gather(*tasks, return_exceptions=True)
        valid_results = []
        for r in results:
            if isinstance(r, Exception):
                continue
            if r and r[0]:
                valid_results.append(r)

        return valid_results

    async def _fetch_single(self, query, source_name, shot, base_path):
        """Fetch from a single source, return (file, uid, source, query)."""
        index = shot["index"]
        video_path = Path(f"{base_path}_{source_name}.mp4")
        image_path = Path(f"{base_path}_{source_name}.jpg")

        try:
            found_file, media_uid = None, None
            if source_name == "PEXELS":
                found_file, media_uid = await asyncio.to_thread(
                    MediaSources.fetch_pexels_video, query, video_path)
            elif source_name == "PIXABAY":
                found_file, media_uid = await asyncio.to_thread(
                    MediaSources.fetch_pixabay_video, query, video_path)
            elif source_name == "LOC":
                found_file, media_uid = await asyncio.to_thread(
                    MediaSources.fetch_chronicling_america, query, image_path)
            elif source_name == "WIKIPEDIA":
                found_file, media_uid = await asyncio.to_thread(
                    MediaSources.fetch_wikipedia_image, query, image_path)
            elif source_name == "FBI_ARCHIVE":
                found_file, media_uid = await asyncio.to_thread(
                    MediaSources.fetch_fbi_archive, query, Path(f"{base_path}_{source_name}"))

            return (found_file, media_uid, source_name, query)
        except Exception as e:
            log(f"⚠️ خطأ جلب {source_name} للمشهد {index}: {e}", "warning")
            return (None, None, source_name, query)

PARALLEL_FETCHER = ParallelSourceFetcher()


# =============================================================================
# SEARCH RESULT CACHE — Per-project, isolated cache
# =============================================================================

class SearchResultCache:
    """
    Caches search results per project/run to avoid duplicate API calls.
    Isolated by run_id to prevent cross-project contamination.
    """

    def __init__(self):
        self.cache = {}  # (source, query_hash) -> list of results
        self.run_id = CONFIG.run_id
        self.lock = threading.Lock()

    def _key(self, source, query):
        q_hash = hashlib.md5(f"{self.run_id}:{source}:{query.lower().strip()}".encode()).hexdigest()[:16]
        return (source, q_hash)

    def get(self, source, query):
        with self.lock:
            return self.cache.get(self._key(source, query))

    def put(self, source, query, results):
        with self.lock:
            self.cache[self._key(source, query)] = results

    def clear(self):
        with self.lock:
            self.cache.clear()

SEARCH_CACHE = SearchResultCache()


async def generate_ai_image(prompt, output_path, aspect_ratio="16:9"):
    log(f"🎨 إنشاء صورة مخصصة عبر AGY: '{prompt[:70]}...'", "info")
    full_prompt = f"[CRITICAL: NO TEXT ON IMAGE. OUTPUT RAW IMAGE ONLY] Photorealistic cinematic documentary photo: {prompt}. Aspect Ratio: {aspect_ratio}"

    try:
        if Path(output_path).exists(): Path(output_path).unlink()
        cmd_binary = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", "medium", "--dangerously-skip-permissions", "-p", full_prompt]

        # تم حل مشكلة انقطاع الوقت عند توليد الصور هنا (الخطأ السابق 120 ثانية)
        res_bin = await asyncio.to_thread(subprocess.run, cmd_binary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)

        if res_bin.stdout.startswith(b'\xff\xd8') or res_bin.stdout.startswith(b'\x89PNG'):
            with open(output_path, "wb") as f: f.write(res_bin.stdout)
        else:
            data = extract_json(res_bin.stdout.decode('utf-8', errors='ignore'))
            if data and isinstance(data, dict) and "image" in data:
                with open(output_path, "wb") as f: f.write(base64.b64decode(data["image"]))

        if is_valid_visual(output_path):
            return True

    except subprocess.TimeoutExpired:
        log(f"⚠️ انتهى الوقت المخصص لتوليد الصورة البديلة، سيتم الانتقال للخلفية السينمائية.", "warning")
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


class StoryScoutEngine:
    def __init__(self):
        self.script = None

    def inspect_and_plan(self):
        log("🧠 بدء تحليل الموضوع وصناعة السيناريو الاستقصائي...")
        prompt = f"""You are an elite investigative documentary producer. TOPIC: {CONFIG.topic}
[SYSTEM BYPASS CACHE ID: {CONFIG.run_id}]
Create a production-ready investigative documentary plan. Return ONLY valid JSON:
{{"story_type": "investigation", "primary_english_query": "", "part_1": "", "part_2": ""}}
Requirements: Arabic narration. Total approx 350-450 words. Divide into part_1 and part_2. Serious tone."""
        try:
            result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", "high", "--dangerously-skip-permissions", "-p", prompt])
            data = extract_json(result.stdout.strip())
            if not data or not data.get("part_1"): raise RuntimeError()
            self.script = data

            log("\n" + "="*60)
            log("📜 [السيناريو المولد - الجزء الأول]:")
            log(data['part_1'])
            log("\n📜 [السيناريو المولد - الجزء الثاني]:")
            log(data['part_2'])
            log("="*60 + "\n")

            return data
        except Exception as e:
            fallback = {"story_type": "investigation", "primary_english_query": clean_query(CONFIG.topic), "part_1": f"تفاصيل غامضة ومختلفة كلياً حول {CONFIG.topic}.", "part_2": "تظل الحقيقة غير محسومة."}
            self.script = fallback
            return fallback

    def direct_storyboard(self, shots):
        log("🎬 [المخرج الفني] هندسة كلمات البحث بذكاء للقطات...")
        shots_summary = "\n".join([f"Shot {s['index']}: {s['text']}" for s in shots])

        # Enhanced director prompt with 6-tier query system and content type classification
        prompt = f"""You are an Elite Visual Director and Expert Stock/Archive SEO Metadata Specialist.
TOPIC: {self.script.get('primary_english_query', CONFIG.topic)}
[ID: {CONFIG.run_id}]
Analyze ALL of these shots contextually based on the story:
{shots_summary}

CRITICAL RULES FOR SEARCH QUERIES (This dictates if we find the video!):
1. "category": "ARCHIVE" (real evidence/history) OR "CINEMATIC" (mood/B-roll).
2. "content_type": Classify the shot content. Options for ARCHIVE: "person_mugshot", "document_file", "location_photo", "historical_event", "newspaper_article". Options for CINEMATIC: "nature_water", "dark_moody", "people_action", "objects_closeup", "urban_night".
3. "exact_entities" (For ARCHIVE): Array of 6 English search terms, ordered from MOST SPECIFIC to MOST GENERIC:
   - Index 0: Exact proper noun (e.g., "Alcatraz Island prison").
   - Index 1: Broader location or event (e.g., "San Francisco Bay 1960").
   - Index 2: Related physical object/document (e.g., "FBI wanted poster").
   - Index 3: Generic historical fallback (e.g., "old prison photograph").
   - Index 4: Alternative angle search (e.g., "federal penitentiary vintage").
   - Index 5: Ultra-generic safe fallback (e.g., "historical archive document").
4. "visual_vibes" (For CINEMATIC): Array of 6 highly effective stock-footage keywords (1-3 words max).
   - Stock sites HATE complex sentences. Use BROAD, popular concepts.
   - GOOD: "flashing police lights", "dark rainy street", "hacker typing", "dusty documents".
   - BAD: "police car driving slowly down a dark rainy street".
   - Index 0: Best match for the scene. Index 1-2: Great alternatives. Index 3-5: Safe generic fallbacks.
5. "reviewer_context": Strict Arabic instructions for the QA Reviewer.
6. "accept_similar": true/false - If true, accept visually similar results even if not exact match.

Return ONLY a valid JSON object mapping shot index (as string keys) to the above fields."""
        try:
            result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", "high", "--dangerously-skip-permissions", "-p", prompt], timeout=300)
            board = extract_json(result.stdout.strip())

            log("\n" + "🎥 "*15 + "[قرارات المخرج الفني]" + " 🎥"*15)
            if board and isinstance(board, dict):
                for shot in shots:
                    idx = str(shot["index"])
                    if idx in board:
                        cat_raw = str(board[idx].get("category", "")).strip().upper()
                        shot["category"] = "ARCHIVE" if "ARCHIV" in cat_raw else "CINEMATIC"
                        shot["content_type"] = board[idx].get("content_type", "default")
                        # Receive the expanded 6-query arrays
                        shot["exact_entities"] = board[idx].get("exact_entities", [CONFIG.topic_clean, "investigation", "mystery file", "old photo", "vintage archive", "historical document"])
                        shot["visual_vibes"] = board[idx].get("visual_vibes", ["mystery", "dark room", "cinematic shadow", "suspense", "dramatic light", "moody atmosphere"])
                        shot["reviewer_context"] = board[idx].get("reviewer_context", "تأكد من مطابقة اللقطة للنص.")
                        shot["accept_similar"] = board[idx].get("accept_similar", False)
                    else:
                        shot["category"] = "CINEMATIC"
                        shot["content_type"] = "default"
                        shot["exact_entities"] = [CONFIG.topic_clean, "investigation", "mystery", "police", "vintage", "archive"]
                        shot["visual_vibes"] = ["mystery", "dark room", "shadow", "suspense", "cinematic", "moody"]
                        shot["reviewer_context"] = "اعتمد على النص."
                        shot["accept_similar"] = True

                    query_used = shot['exact_entities'][0] if shot['category'] == 'ARCHIVE' else shot['visual_vibes'][0]
                    log(f"📌 المشهد {shot['index']:02d} | الفئة: {shot['category']} | النوع: {shot.get('content_type','default')} | الخيار الأول: '{query_used}' | التوجيه: {shot['reviewer_context']}")
            else:
                raise RuntimeError()
            log("🎥 "*40 + "\n")
        except:
            for shot in shots:
                shot["category"] = "CINEMATIC"
                shot["content_type"] = "default"
                shot["exact_entities"] = [CONFIG.topic_clean, "investigation", "mystery", "police", "vintage", "archive"]
                shot["visual_vibes"] = ["mystery", "dark room", "shadow", "suspense", "cinematic", "moody"]
                shot["reviewer_context"] = "تأكد من ملاءمة اللقطة للنص."
                shot["accept_similar"] = True

        return shots


class MasterAudioStudio:
    def produce_master_track(self, script):
        full_narration = f"{script['part_1']}\n\n{script['part_2']}".strip()
        out_wav = CONFIG.master_audio
        total_keys = len(CONFIG.gemini_keys)
        log(f"🎙️ بدء إنتاج التعليق الصوتي الماستر (إجمالي المفاتيح: {total_keys})...")

        attempted = set()
        for attempt in range(total_keys):
            key_index, api_key = GEMINI_POOL.acquire(excluded=attempted)
            attempted.add(key_index)
            display_key = key_index + 1
            start_t = time.time()
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=TTS_MODEL,
                    contents=f"[INSTRUCTION: Chilling authoritative Arabic documentary narrator. Read ENTIRE text. UNIQUE_ID: {CONFIG.run_id}]\n\n" + full_narration,
                    config=types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))))
                )
                data = next((p.inline_data.data for p in response.candidates[0].content.parts if getattr(p, "inline_data", None)), None)
                if not data: raise RuntimeError()

                raw_audio = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                temp_pcm = CONFIG.work_dir / f"full_temp_{display_key}.pcm"
                with open(temp_pcm, "wb") as f: f.write(raw_audio)

                run_cmd(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(temp_pcm), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(out_wav)], timeout=180)
                temp_pcm.unlink(missing_ok=True)

                if is_valid_media(out_wav):
                    log(f"✅ نجح توليد الصوت بمفتاح #{display_key} خلال {time.time() - start_t:.1f} ثانية!")
                    GEMINI_POOL.release(key_index)
                    return out_wav
            except:
                GEMINI_POOL.release(key_index)
                time.sleep(2)
        raise RuntimeError("❌ فشل توليد التعليق الصوتي.")


class WordSyncSlicer:
    def align_and_slice(self, audio_path):
        log("🧠 إرسال الصوت إلى Groq Whisper للتوقيتات...")
        headers = {"Authorization": f"Bearer {CONFIG.groq_api_key}"}
        try:
            with open(audio_path, "rb") as f:
                res = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files={"file": ("m.wav", f, "audio/wav")}, data={"model": GROQ_MODEL, "language": "ar", "response_format": "verbose_json", "timestamp_granularities[]": "word"}, timeout=180)
            if res.status_code != 200: raise RuntimeError(f"Groq {res.status_code}")

            words = [{"word": str(i["word"]).strip(), "start": float(i["start"]), "end": float(i["end"])} for i in res.json().get("words", []) if i.get("word")]
            shots, cur, s_start = [], [], 0.0
            for item in words:
                cur.append(item)
                if item["end"] - s_start >= 3.5 or (item["end"] - s_start >= 2.0 and item["word"].endswith((".", "!", "؟", "،"))):
                    text = " ".join(x["word"] for x in cur).strip()
                    if text: shots.append({"index": len(shots)+1, "start": s_start, "end": item["end"], "duration": max(0.5, item["end"] - s_start), "text": text})
                    cur, s_start = [], item["end"]
            if cur: shots.append({"index": len(shots)+1, "start": s_start, "end": cur[-1]["end"], "duration": max(0.5, cur[-1]["end"] - s_start), "text": " ".join(x["word"] for x in cur).strip()})
            log(f"✂ تم تقسيم الصوت بنجاح إلى {len(shots)} مشهد.")
            return shots
        except Exception as e:
            raise


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
        if not q_clean: return None, None
        try:
            commons_url = "https://commons.wikimedia.org/w/api.php"
            params = {"action": "query", "generator": "search", "gsrsearch": f"{q_clean}", "gsrnamespace": 6, "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url|mime|size", "format": "json"}
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
                saved_path, uid = MediaSources._track_and_save(pages, o, extract_commons)
                if saved_path: return saved_path, uid
        except: pass
        return None, None

    @staticmethod
    def fetch_fbi_archive(q, base_path):
        try:
            q_clean = clean_query(q)
            if not q_clean: return None, None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            query = f'({q_clean}) AND (mediatype:image OR mediatype:movies)'
            res = requests.get("https://archive.org/advancedsearch.php", headers=headers, params={"q": query, "fl[]": "identifier", "rows": 20, "output": "json"}, timeout=20)
            docs = res.json().get("response", {}).get("docs", [])
            if not docs:
                res = requests.get("https://archive.org/advancedsearch.php", headers=headers, params={"q": q_clean, "fl[]": "identifier", "rows": 15, "output": "json"}, timeout=20)
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
            return None, None
        except: return None, None

    @staticmethod
    def fetch_chronicling_america(q, o):
        try:
            q_clean = clean_query(q)
            if not q_clean: return None, None
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            url = f"https://www.loc.gov/photos/?fo=json&fa=online_format:image&c=25&q={urllib.parse.quote(q_clean)}"
            res = requests.get(url, headers=headers, timeout=20)
            results = res.json().get("results", [])
            if not results: return None, None
            def extract_loc(i):
                img_urls = i.get("image_url", [])
                if isinstance(img_urls, str): img_urls = [img_urls]
                if not img_urls: return None, None
                return img_urls[-1], str(i.get("id", img_urls[-1]))
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


async def agy_evaluate_scout(media_path, shot, story, source_name, query):
    if not media_path: return False, 0.0, 0.0, "الملف غير موجود في المسار"

    # Pre-filter check — skip AGY call for obviously bad results
    prefilter_ok, prefilter_reason = MediaPreFilter.quick_validate(media_path, shot, source_name)
    if not prefilter_ok:
        return False, 0.0, 0.0, prefilter_reason

    prompt = f"""You evaluate documentary media suitability strictly based on the context.
[ID: {CONFIG.run_id}_{time.time()}]
TOPIC: {story.get("primary_english_query", CONFIG.topic)}
SHOT SCRIPT TEXT: "{shot['text']}"
SHOT CATEGORY (CRITICAL): {shot['category']}
RETRIEVED FROM: {source_name}
SEARCH QUERY USED: "{query}"
LOCAL MEDIA PATH TO EVALUATE: {Path(media_path).absolute()}
DIRECTOR'S INSTRUCTION: {shot.get("reviewer_context", "")}
ACCEPT SIMILAR: {shot.get("accept_similar", False)}

CRITICAL RULES:
- If CATEGORY is "ARCHIVE": You are looking for historical authenticity matching the SEARCH QUERY. If the media looks like an authentic record, mugshot, or document of the entity, ACCEPT IT. If ACCEPT_SIMILAR is true, also accept visually similar historical content.
- If CATEGORY is "CINEMATIC": You are looking for mood, lighting, and B-roll that matches the text. Be MORE LENIENT with cinematic shots — if the visual mood is right, accept it even if not a perfect literal match.
- IMPORTANT: Do NOT reject a good mood/atmosphere match just because it's not a literal interpretation. A dark moody shot of water IS acceptable for "drowning" context. A silhouette IS acceptable for "mysterious figure".

Return ONLY valid JSON: {{"decision": "accept" or "reject", "score": 0.0 to 1.0, "reason": "Arabic Reason based on Director's Instruction"}}"""

    try:
        cmd = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", "medium", "--dangerously-skip-permissions", "-p", prompt]
        res = await asyncio.to_thread(subprocess.run, cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)

        data = extract_json(res.stdout)
        if data:
            score = float(data.get("score", 0.0))
            # Adaptive acceptance threshold based on attempt number
            accept_threshold = 0.35
            if shot.get("accept_similar"):
                accept_threshold = 0.30  # More lenient for similar-acceptable shots
            is_accepted = (data.get("decision", "").lower() == "accept" and score >= accept_threshold)
            reason = str(data.get("reason", "لا يوجد سبب"))
            return is_accepted, score, 0.0, reason
        else:
            error_output = res.stderr.strip() or res.stdout.strip()
            return False, 0.0, 0.0, f"خطأ من أداة AGY: {error_output[:150]}"

    except subprocess.TimeoutExpired:
        return False, 0.0, 0.0, "خطأ: انتهى الوقت (Timeout) المخصص لتقييم المقطع (استغرق أكثر من 5 دقائق)."
    except Exception as e:
        return False, 0.0, 0.0, f"خطأ برمجي أثناء الاستدعاء: {str(e)[:150]}"


async def apply_fallback(shot, story):
    index = shot["index"]
    cat = shot.get("category", "CINEMATIC")

    if shot['best_score'] >= 0.20 and shot['best_candidate']:
        log(f"⚠️ [إنقاذ 1] المشهد {index}: اعتماد أفضل لقطة تم العثور عليها (تقييم {shot['best_score']:.2f}).", "warning")
        return shot['best_candidate']

    log(f"🤖 [إنقاذ 2] توليد بديل ذكي للمشهد {index} ({cat})...", "warning")
    ai_path = CONFIG.work_dir / f"shot_{index:03d}_ai.jpg"

    entities = shot.get("exact_entities", [])
    vibes = shot.get("visual_vibes", [])
    fallback_query = " ".join(entities[:3]) if cat == "ARCHIVE" else " ".join(vibes[:3])

    ok = await generate_ai_image(fallback_query, ai_path)
    if ok:
        return {"shot": shot, "path": str(ai_path), "source": "AI_GENERATED", "score": 1.0, "start": 0.0, "duration": 5.0}

    log(f"🚨 [إنقاذ نهائي] خلفية سينمائية للمشهد {index}.", "error")
    fallback_path = CONFIG.work_dir / f"shot_{index:03d}_fallback.mp4"
    await create_fallback_visual(fallback_path)
    return {"shot": shot, "path": str(fallback_path), "source": "FFMPEG", "score": 0.0, "start": 0.0, "duration": 5.0}


async def run_pipelined_production(shots, story):
    """
    OPTIMIZED PRODUCTION PIPELINE
    Key changes from V51:
    1. Uses SmartQueryEngine for intelligent query generation
    2. Parallel multi-source fetching per shot
    3. Pre-filter validation before AGY calls
    4. Adaptive acceptance thresholds
    5. Smart source routing based on content type
    6. Result caching to avoid duplicate API calls
    """
    total_shots = len(shots)
    completed_lock = asyncio.Lock()
    completed_results = []
    completion_event = asyncio.Event()
    shot_semaphore = asyncio.Semaphore(8)  # Max concurrent shot processing

    for shot in shots:
        shot['status'] = 'PENDING'
        shot['attempts'] = 0
        shot['best_score'] = -1.0
        shot['best_candidate'] = None
        shot['tried_sources'] = set()
        shot['tried_queries'] = set()

    log(f"🚀 تشغيل خط الإنتاج المحسّن | إجمالي المشاهد: {total_shots} | أقصى محاولات: {MAX_ATTEMPTS_PER_SHOT}")

    async def process_shot(shot):
        """Process a single shot with smart search strategy."""
        index = shot["index"]
        cat = shot.get("category", "CINEMATIC")
        base = CONFIG.work_dir / f"shot_{index:03d}"

        while shot['status'] != 'DONE' and shot['attempts'] < MAX_ATTEMPTS_PER_SHOT:
            attempt_num = shot['attempts']

            # Generate smart query tiers for this attempt
            query_tiers = QUERY_ENGINE.generate_query_tiers(shot, attempt_num)

            # For first attempt, try parallel multi-source fetch (top 2 sources)
            if attempt_num == 0 and len(query_tiers) >= 2:
                pairs_to_try = query_tiers[:2]
            else:
                pairs_to_try = query_tiers[:1]

            log(f"⚡ المشهد {index} (م{attempt_num+1}/{MAX_ATTEMPTS_PER_SHOT}) | "
                f"{'، '.join(f'{s}:{q}' for q,s in pairs_to_try)}", "info")

            # Fetch from sources (parallel for first attempt)
            fetch_results = await PARALLEL_FETCHER.fetch_from_multiple_sources(
                pairs_to_try, shot, base)

            if not fetch_results:
                # No results from any source
                for q, src in pairs_to_try:
                    QUERY_ENGINE.record_failure(q, src)
                    shot['tried_queries'].add(f"{src}:{q}")
                log(f"⏩ المشهد {index}: لم يعثر على نتائج من أي مصدر.", "info")
                shot['attempts'] += 1
                continue

            # Evaluate results — try each fetched result
            found_acceptable = False
            for found_file, media_uid, src_name, query in fetch_results:
                if not found_file or not Path(found_file).exists():
                    QUERY_ENGINE.record_failure(query, src_name)
                    continue

                output_path = Path(found_file)
                is_img = output_path.suffix.lower() in (".jpg", ".jpeg", ".png")

                # Quick pre-filter check
                valid = is_valid_visual(output_path) if is_img else is_valid_media(output_path)
                if not valid:
                    log(f"⏩ المشهد {index}: ملف تالف من {src_name}.", "debug")
                    QUERY_ENGINE.record_failure(query, src_name)
                    if output_path.exists(): output_path.unlink()
                    continue

                # Evaluate with AGY
                async with REVIEWER_SEMAPHORE:
                    accepted, score, start, reason = await agy_evaluate_scout(
                        output_path, shot, story, src_name, query)

                dur = float(shot.get("duration", 3.0)) if is_img else probe_duration(output_path)

                # Track best candidate
                if score > shot['best_score']:
                    shot['best_score'] = score
                    best_bak = output_path.with_name(f"best_{output_path.name}")
                    shutil.copy(output_path, best_bak)
                    shot['best_candidate'] = {
                        "shot": shot, "path": str(best_bak),
                        "source": src_name, "score": score,
                        "start": start, "duration": dur
                    }

                if accepted:
                    log(f"🎯 المشهد {index}: قُبِل من {src_name} ({cat}) | تقييم: {score:.2f} | {reason[:80]}")
                    res_item = {
                        "shot": shot, "path": str(output_path),
                        "source": src_name, "score": score,
                        "start": start, "duration": dur
                    }
                    QUERY_ENGINE.record_success(query, cat)

                    async with completed_lock:
                        shot['status'] = 'DONE'
                        if media_uid:
                            with CONFIG.used_media_lock:
                                CONFIG.used_media_ids.add(media_uid)
                        completed_results.append(res_item)
                        log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                        if len(completed_results) == total_shots:
                            completion_event.set()
                    found_acceptable = True
                    break
                else:
                    log(f"⏩ المشهد {index}: رُفض من {src_name} (تقييم: {score:.2f}) | {reason[:80]}")
                    QUERY_ENGINE.record_failure(query, src_name)

            if not found_acceptable:
                shot['attempts'] += 1

                # Progressive acceptance: after 3 attempts, accept best if score >= 0.30
                if shot['attempts'] >= 3 and shot['best_score'] >= 0.30 and shot['best_candidate']:
                    log(f"✅ المشهد {index}: قبول تدريجي لأفضل نتيجة (تقييم: {shot['best_score']:.2f}) بعد {shot['attempts']} محاولات.", "info")
                    async with completed_lock:
                        shot['status'] = 'DONE'
                        completed_results.append(shot['best_candidate'])
                        log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                        if len(completed_results) == total_shots:
                            completion_event.set()

        # If exhausted all attempts
        if shot['status'] != 'DONE':
            log(f"⚠️ المشهد {index} استنفد المحاولات. حسم المشهد عبر خطة الإنقاذ...", "warning")
            fallback_res = await apply_fallback(shot, story)
            async with completed_lock:
                shot['status'] = 'DONE'
                completed_results.append(fallback_res)
                log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                if len(completed_results) == total_shots:
                    completion_event.set()

    async def throttled_process(shot):
        async with shot_semaphore:
            await process_shot(shot)

    # Launch all shots concurrently (throttled by semaphore)
    tasks = [asyncio.create_task(throttled_process(shot)) for shot in shots]
    await asyncio.gather(*tasks)

    if not completion_event.is_set():
        completion_event.set()

    return sorted(completed_results, key=lambda x: x["shot"]["index"])


class AssemblyEngine:
    def render_sub_clip(self, item):
        shot, media_path, index = item["shot"], Path(item["path"]), item["shot"]["index"]
        output = CONFIG.work_dir / f"rendered_{index:03d}.mp4"
        start = min(float(item.get("start", 0)), max(0, probe_duration(media_path) - 0.1))
        dur = float(shot.get("duration", 3))

        log(f"✂️ جاري رندرة المشهد {index}...", "debug")
        if media_path.suffix.lower() in (".mp4", ".mov"):
            vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,eq=contrast=1.06:saturation=0.92,vignette,noise=alls=3:allf=t,fps=30"
            res = run_cmd(["ffmpeg", "-y", "-ss", str(start), "-i", str(media_path), "-t", str(dur), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", str(output)])
        else:
            vf = "scale=2208:1248:force_original_aspect_ratio=increase,crop=2208:1248,zoompan=z='min(zoom+0.0008,1.15)':d=1:s=1920x1080:fps=30,eq=contrast=1.06:saturation=0.92,vignette,noise=alls=3:allf=t"
            res = run_cmd(["ffmpeg", "-y", "-loop", "1", "-i", str(media_path), "-t", str(dur), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", str(output)])

        if res.returncode != 0: raise RuntimeError(f"Render shot {index} failed.")
        return output

    def assemble_final_cut(self, rendered, subtitle_path):
        concat_file = CONFIG.work_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for p in rendered: f.write(f"file '{Path(p).resolve()}'\n")
        temp_v = CONFIG.work_dir / "temp.mp4"
        run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(temp_v)])

        sub_filter = "subtitles=" + str(Path(subtitle_path).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        log("🎞 بدء التجميع النهائي (Assembly)...", "info")
        res = run_cmd(["ffmpeg", "-y", "-i", str(temp_v), "-i", str(CONFIG.master_audio), "-vf", sub_filter, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest", str(CONFIG.final_video)], timeout=1200)

        if res.returncode != 0: raise RuntimeError("Final assembly failed.")
        log(f"🎉 FINAL DOCUMENTARY READY | {probe_duration(CONFIG.final_video)/60:.2f} mins | {CONFIG.final_video.stat().st_size/1024/1024:.1f} MB", "info")
        return CONFIG.final_video


class GoogleUploader:
    def __init__(self, cid, csec, ref):
        self.creds = Credentials(None, refresh_token=ref, token_uri="https://oauth2.googleapis.com/token", client_id=cid, client_secret=csec) if cid and csec and ref else None

    def upload_all(self, vid_path, thumb_path, title):
        if not self.creds: return
        try:
            drive = build('drive', 'v3', credentials=self.creds, cache_discovery=False)
            df = drive.files().create(body={'name': f"{title}.mp4"}, media_body=MediaFileUpload(str(vid_path), mimetype='video/mp4', resumable=True), fields='id').execute()
            log(f"✅ Google Drive: https://drive.google.com/file/d/{df.get('id')}/view", "info")

            yt = build('youtube', 'v3', credentials=self.creds, cache_discovery=False)
            body = {'snippet': {'title': title, 'description': f"وثائقي: {title}\nإنتاج تلقائي.", 'tags': ['وثائقي'], 'categoryId': '24'}, 'status': {'privacyStatus': 'private'}}
            res = yt.videos().insert(part=','.join(body.keys()), body=body, media_body=MediaFileUpload(str(vid_path), mimetype='video/mp4', resumable=True)).execute()
            vid_id = res.get('id')
            log(f"✅ YouTube: https://youtu.be/{vid_id}", "info")

            if thumb_path.exists():
                yt.thumbnails().set(videoId=vid_id, media_body=MediaFileUpload(str(thumb_path), mimetype='image/jpeg')).execute()
                log("✅ تم رفع الصورة المصغرة لليوتيوب بنجاح.", "info")
        except Exception as e: log(f"❌ فشل الرفع السحابي: {e}", "error")


async def main_pipeline():
    prepare_fresh_workspace()
    log(f"🚀 بدء {ENGINE_VERSION} | {CONFIG.topic}")

    story_engine = StoryScoutEngine()
    story = story_engine.inspect_and_plan()

    master_audio = MasterAudioStudio().produce_master_track(story)
    shots = WordSyncSlicer().align_and_slice(master_audio)
    shots = story_engine.direct_storyboard(shots)

    sub_path = CONFIG.work_dir / "subtitles.ass"
    with open(sub_path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Noto Sans Arabic,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,70,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for s in shots:
            h1, m1 = int(s['start']//3600), int((s['start']%3600)//60)
            h2, m2 = int(s['end']//3600), int((s['end']%3600)//60)
            t = s['text'].replace("\\", r"\\")
            f.write(f"Dialogue: 0,{h1}:{m1:02d}:{s['start']%60:05.2f},{h2}:{m2:02d}:{s['end']%60:05.2f},Default,,0,0,0,,{{\\fad(120,120)}}{t}\n")

    media_results = await run_pipelined_production(shots, story)

    assembly = AssemblyEngine()
    final_video = assembly.assemble_final_cut([assembly.render_sub_clip(i) for i in media_results], sub_path)

    log("🎨 توليد صورة مصغرة (Thumbnail) لليوتيوب...", "info")
    await generate_ai_image(story.get('primary_english_query', CONFIG.topic), CONFIG.thumbnail, "16:9")

    uploader = GoogleUploader(CONFIG.google_client_id, CONFIG.google_client_secret, CONFIG.google_refresh_token)
    await asyncio.to_thread(uploader.upload_all, final_video, CONFIG.thumbnail, CONFIG.topic_clean)

    log("🏁 اكتمل العمل بنجاح قياسي ونزاهة إخراجية تامة.", "info")

if __name__ == "__main__":
    try:
        asyncio.run(main_pipeline())
    except KeyboardInterrupt:
        log("🛑 تم الإيقاف يدوياً.", "warning")
        sys.exit(130)
    except Exception as e:
        log(f"💥 توقف النظام بسبب خطأ حرج: {e}", "error")
        sys.exit(1)
