#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
V54 - PRODUCTION-SCALE INTELLIGENT ADAPTIVE PIPELINE

Major improvements over V53:
- PRODUCTION SCALE: 400-500 scenes for ~25 minute documentaries
- BLURRED BACKGROUND: Images use fit-with-blur instead of crop (no detail loss)
- FIXED FFMPEG FILTERS: Proper glitch effect, Ken Burns, crossfade, film grain
- CHRONOLOGICAL NARRATIVE: Documentary script follows strict timeline
- THINKING BUDGET: Low for reviewer (rate-limit safe), High for pro models
- MEMORY MANAGEMENT: Stream cleanup, GC hints, batched rendering
- THUMBNAIL FIX: Proper JPEG conversion before YouTube upload
- 15-attempt adaptive search with failure-learning strategy
- Scene decomposition into semantic search dimensions
- Source-aware routing: Europeana, Openverse, Freesound integration
- Smart pre-filtering with metadata relevance scoring BEFORE download
- Progressive query strategy: entity→event→location→period→generic
- Failure diagnosis: understands WHY searches fail and adapts
- Rescue priority: exhaust real search → cinematic bg → AI (true last resort)
- Parallel multi-source fetching with intelligent batching
- Cross-scene deduplication with per-project isolation
- FFmpeg vintage effects: Ken Burns, film grain, vignette, crossfade, glitch
- Reviewer pre-filter to avoid wasting AGY calls on obvious mismatches
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

ENGINE_VERSION = "V54-PRODUCTION-SCALE"

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
MAX_ATTEMPTS_PER_SHOT = 15  # Increased from 6 — but each attempt is genuinely different

REVIEWER_SEMAPHORE = asyncio.Semaphore(7)

# Pre-filter: skip AGY call if media clearly doesn't match basic criteria
PREFILTER_MIN_SIZE_BYTES = 5 * 1024  # 5 KB minimum for images
PREFILTER_MIN_VIDEO_DURATION = 0.5   # seconds

# === PRODUCTION SCALE SETTINGS ===
# Target: ~25 minutes total, 400-500 scenes, 3-4 seconds per scene
TARGET_TOTAL_DURATION_MINUTES = 25
TARGET_NARRATION_WORDS = 3500       # ~140 words/min Arabic narration × 25 min
SCENE_DURATION_MIN = 2.0
SCENE_DURATION_MAX = 5.0
RENDER_BATCH_SIZE = 50              # Render in batches to manage memory

# === THINKING BUDGET CONFIGURATION ===
# "low" = minimal reasoning tokens (fast, rate-limit safe)
# "high" = full deep reasoning (pro-tier quality)
EFFORT_REVIEWER = "low"        # Fast reviewer: minimize tokens, preserve API quota
EFFORT_PRO_GENERATION = "high"  # Pro models: full reasoning for script/storyboard
EFFORT_IMAGE_GEN = "medium"     # Image generation: balanced

API_HEADERS = {
    "User-Agent": "InvestigativeDocumentaryBot/1.0 (https://github.com/Ya7ossaaain; contact@example.com)",
    "Accept": "application/json, text/plain, */*"
}

MEDIA_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

ARCHIVE_SOURCES = ["WIKIPEDIA", "FBI_ARCHIVE", "LOC", "EUROPEANA", "OPENVERSE"]
CINEMATIC_SOURCES = ["PEXELS", "PIXABAY", "OPENVERSE"]

# === SOURCE AFFINITY MAP ===
# Maps content types to ordered source preferences
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
        self.europeana_key = os.environ.get("EUROPEANA_API_KEY", "")
        self.freesound_key = os.environ.get("FREESOUND_API_KEY", "")
        self.openverse_client_id = os.environ.get("OPENVERSE_CLIENT_ID", "")
        self.openverse_client_secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "")
        self.openverse_token = None
        self.openverse_token_lock = threading.Lock()
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
        res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], stdout=subprocess.PIPE, text=True, timeout=30)
        return float(res.stdout.strip())
    except: return 0.0


def probe_dimensions(path):
    """Probe width and height of a media file. Returns (width, height) or (0, 0) on failure."""
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
    except:
        pass
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


def cleanup_temp_files(directory, pattern="*.tmp"):
    """Clean up temporary files to free disk space during long runs."""
    try:
        for f in Path(directory).glob(pattern):
            f.unlink(missing_ok=True)
    except:
        pass


# =============================================================================
# BLURRED BACKGROUND FFmpeg FILTER — Preserves full image, no cropping
# =============================================================================

def build_blur_background_filter_image(input_w, input_h, target_w=TARGET_W, target_h=TARGET_H, ken_burns=True):
    """
    Build FFmpeg filter_complex for image display with blurred background.

    Instead of cropping to fill 16:9, this:
    1. Takes the image, scales it to FILL the canvas, applies heavy blur → background
    2. Takes the same image, scales it to FIT the canvas (preserve aspect ratio) → foreground
    3. Overlays the sharp foreground centered on the blurred background

    This ensures 100% of the image content is visible with no black bars.
    Ken Burns (slow zoom) is optionally applied on the foreground for cinematic feel.
    """
    # Background: scale to fill + heavy blur
    bg_part = (
        f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},"
        f"gblur=sigma=40,"
        f"eq=brightness=-0.08:saturation=0.4[bg]"
    )

    # Foreground: scale to fit (preserve aspect ratio, no crop)
    if ken_burns:
        # Zoompan for Ken Burns effect on the foreground
        fg_part = (
            f"[0:v]scale={int(target_w * 1.15)}:{int(target_h * 1.15)}:force_original_aspect_ratio=decrease,"
            f"zoompan=z='min(zoom+0.0008,1.15)':d=1:s={target_w}x{target_h}:fps={TARGET_FPS}[fg]"
        )
    else:
        fg_part = (
            f"[0:v]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black@0[fg]"
        )

    # Overlay foreground on blurred background, then apply film grain + vignette
    overlay_part = (
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"eq=contrast=1.06:saturation=0.92,"
        f"vignette,"
        f"noise=alls=3:allf=t,"
        f"fps={TARGET_FPS}"
    )

    return f"{bg_part};{fg_part};{overlay_part}"


def build_blur_background_filter_video(target_w=TARGET_W, target_h=TARGET_H):
    """
    Build FFmpeg filter_complex for VIDEO display with blurred background.

    Same concept as images but for video input:
    1. Background: scale to fill + blur
    2. Foreground: scale to fit (preserve aspect ratio)
    3. Overlay centered

    Uses split to avoid reading input twice.
    """
    filter_chain = (
        f"[0:v]split=2[bg_in][fg_in];"
        f"[bg_in]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,"
        f"crop={target_w}:{target_h},"
        f"gblur=sigma=35,"
        f"eq=brightness=-0.08:saturation=0.4[bg];"
        f"[fg_in]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,"
        f"eq=contrast=1.06:saturation=0.92,"
        f"vignette,"
        f"noise=alls=3:allf=t,"
        f"fps={TARGET_FPS}"
    )
    return filter_chain


def build_glitch_effect_filter(duration, intensity=0.3):
    """
    Build a safe FFmpeg filter for a glitch/distortion transition effect.

    This creates a brief digital glitch (color channel shift + noise burst)
    that is visually striking but FFmpeg-safe. Used for dramatic transitions.

    Args:
        duration: Total clip duration in seconds
        intensity: 0.0 to 1.0 glitch intensity
    """
    # Calculate glitch timing — brief burst in first 0.3s
    glitch_frames = max(3, int(TARGET_FPS * 0.3))
    noise_strength = int(20 + intensity * 40)

    # Safe glitch: chromatic aberration simulation via rgbashift + noise burst
    # Only apply during the first few frames using enable expressions
    glitch_filter = (
        f"noise=alls={noise_strength}:allf=t:enable='between(t,0,0.15)',"
        f"eq=contrast=1.3:saturation=0.3:enable='between(t,0,0.1)',"
        f"eq=contrast=1.06:saturation=0.92:enable='gte(t,0.15)'"
    )
    return glitch_filter


# =============================================================================
# SEARCH FAILURE DIAGNOSIS — Understand WHY searches fail
# =============================================================================

class SearchFailureDiagnostics:
    """
    Tracks and analyzes search failures to inform the next search strategy.
    Instead of 'try another query', we 'understand the failure → change strategy'.
    """

    # Failure categories
    NO_RESULTS = "no_results"
    IRRELEVANT_RESULTS = "irrelevant_results"
    WRONG_MEDIA_TYPE = "wrong_media_type"
    WRONG_TIME_PERIOD = "wrong_time_period"
    WRONG_SOURCE = "wrong_source"
    QUERY_TOO_SPECIFIC = "query_too_specific"
    QUERY_TOO_GENERIC = "query_too_generic"
    DOWNLOAD_FAILED = "download_failed"
    REVIEWER_REJECTED = "reviewer_rejected"
    FORMAT_INVALID = "format_invalid"
    QUERY_AMBIGUOUS = "query_ambiguous"  # e.g. "cell wall" → biology

    def __init__(self):
        self.failures = defaultdict(list)  # shot_index -> list of failure records
        self.lock = threading.Lock()

    def record(self, shot_index, query, source, category, score=0.0, reason=""):
        with self.lock:
            self.failures[shot_index].append({
                "query": query,
                "source": source,
                "category": category,
                "score": score,
                "reason": reason,
                "time": time.time()
            })

    def diagnose(self, shot_index):
        """Analyze all failures for a shot and return a diagnosis dict."""
        with self.lock:
            records = self.failures.get(shot_index, [])

        if not records:
            return {"diagnosis": "no_failures", "recommendations": []}

        no_results_count = sum(1 for r in records if r["category"] == self.NO_RESULTS)
        irrelevant_count = sum(1 for r in records if r["category"] == self.IRRELEVANT_RESULTS)
        rejected_count = sum(1 for r in records if r["category"] == self.REVIEWER_REJECTED)
        ambiguous_count = sum(1 for r in records if r["category"] == self.QUERY_AMBIGUOUS)
        failed_sources = set(r["source"] for r in records)
        failed_queries = set(r["query"] for r in records)
        best_score = max((r["score"] for r in records), default=0.0)

        recommendations = []

        # All attempts returned no results → queries too specific for these sources
        if no_results_count > len(records) * 0.6:
            recommendations.append("try_broader_queries")
            recommendations.append("switch_source_type")

        # Results exist but are all irrelevant → wrong source or wrong query terms
        if irrelevant_count > len(records) * 0.4:
            recommendations.append("change_query_terminology")
            recommendations.append("try_different_source")

        # Ambiguous queries (e.g., cell = biology vs prison)
        if ambiguous_count > 0:
            recommendations.append("disambiguate_query")

        # Reviewer rejects with decent scores → try accept_similar
        if rejected_count > 0 and best_score >= 0.2:
            recommendations.append("lower_threshold_slightly")
            recommendations.append("try_alternative_representation")

        # Specific source has failed many times → avoid it
        source_fail_counts = defaultdict(int)
        for r in records:
            source_fail_counts[r["source"]] += 1
        exhausted_sources = [s for s, c in source_fail_counts.items() if c >= 3]
        if exhausted_sources:
            recommendations.append(f"avoid_sources:{','.join(exhausted_sources)}")

        return {
            "diagnosis": "analyzed",
            "total_failures": len(records),
            "no_results": no_results_count,
            "irrelevant": irrelevant_count,
            "rejected": rejected_count,
            "best_score": best_score,
            "failed_sources": list(failed_sources),
            "failed_queries": list(failed_queries),
            "recommendations": recommendations
        }

    def clear_shot(self, shot_index):
        """Clear failure records for a specific shot to free memory."""
        with self.lock:
            self.failures.pop(shot_index, None)

FAILURE_DIAGNOSTICS = SearchFailureDiagnostics()


# =============================================================================
# SMART QUERY ENGINE V2 — Genuinely different strategies per attempt
# =============================================================================

class SmartQueryEngine:
    """
    Generates intelligent, multi-tier search queries that are GENUINELY DIFFERENT
    across 15 attempts. Uses scene decomposition into semantic dimensions and
    learns from previous failures.

    Strategy progression:
    Attempts 1-3:  Precise entity/event/person queries
    Attempts 4-6:  Semantic reformulations preserving key entities
    Attempts 7-9:  Source-switching with adapted terminology
    Attempts 10-12: Alternative representations, broader context
    Attempts 13-15: Ultra-generic safe fallbacks, creative alternatives
    """

    # Common stock footage keywords that perform well on Pexels/Pixabay
    STOCK_BOOSTERS = {
        "water": ["ocean waves", "sea water", "underwater", "water surface", "dark waves night", "rough sea"],
        "dark": ["dark room", "shadows", "silhouette", "low light", "noir scene", "abandoned building"],
        "night": ["night city", "dark sky", "moonlight", "night time", "streetlight fog", "car headlights night"],
        "prison": ["jail cell", "prison bars", "behind bars", "locked door", "metal gate", "concrete corridor"],
        "document": ["old papers", "vintage document", "typewriter", "old book", "file cabinet", "folder desk"],
        "person": ["man portrait", "close up face", "person walking", "silhouette person", "mysterious figure", "lone figure"],
        "fog": ["misty", "foggy landscape", "haze", "cloudy", "smoke dark", "mist forest"],
        "car": ["classic car", "vintage automobile", "car headlights", "driving", "road night", "highway dark"],
        "letter": ["handwritten letter", "old envelope", "writing pen", "ink on paper", "wax seal", "postmark"],
        "beach": ["sandy beach", "shore", "coastline", "seaside", "footprints sand", "waves shore"],
        "clock": ["ticking clock", "pocket watch", "time lapse", "clock hands", "pendulum", "antique clock"],
        "tombstone": ["graveyard", "cemetery", "memorial stone", "burial ground", "old grave", "headstone"],
        "fire": ["flames burning", "fireplace", "candle flame", "sparks", "match lighting", "bonfire"],
        "map": ["world map", "vintage map", "compass navigation", "atlas pages", "cartography", "globe spinning"],
        "police": ["police lights", "crime scene tape", "investigation", "detective badge", "squad car", "siren lights"],
        "boat": ["fishing boat", "sailing vessel", "rowboat", "ship ocean", "harbor boats", "coast guard vessel"],
        "rain": ["rain drops", "rainy window", "storm lightning", "wet street", "umbrella rain", "downpour"],
    }

    # Archive-specific query patterns for different content types
    ARCHIVE_STRATEGIES = {
        "person_mugshot": [
            "{entity} mugshot",
            "{entity} wanted poster",
            "{entity} photograph portrait",
            "{entity} FBI file",
            "{entity} criminal record",
            "famous fugitive photograph",
            "vintage mugshot criminal",
            "FBI wanted poster vintage",
        ],
        "document_file": [
            "{entity} document",
            "{entity} FBI file",
            "{entity} official report",
            "{entity} classified",
            "FBI investigation file",
            "government document classified",
            "official memo vintage",
            "typewritten report archive",
        ],
        "location_photo": [
            "{entity} photograph",
            "{entity} aerial view",
            "{entity} historical photo",
            "{entity} vintage postcard",
            "historical landmark photo",
            "vintage location photograph",
            "famous building old photo",
            "historic site aerial",
        ],
        "historical_event": [
            "{entity} news footage",
            "{entity} press photo",
            "{entity} documentary",
            "{entity} 1960s photograph",
            "historic event photograph",
            "vintage news reel",
            "cold war era photo",
            "mid century archive",
        ],
        "newspaper_article": [
            "{entity} newspaper",
            "{entity} headline",
            "{entity} front page",
            "{entity} news clipping",
            "vintage newspaper headline",
            "old newspaper crime",
            "historical newspaper front page",
            "archive news article",
        ],
    }

    def __init__(self):
        self.failed_queries = defaultdict(set)  # source -> set of failed query keys
        self.successful_keywords = defaultdict(set)  # category -> keywords that worked
        self.lock = threading.Lock()

    def classify_content_type(self, shot):
        """Classify the content type of a shot for source affinity routing."""
        text = (shot.get("text", "") + " " + " ".join(shot.get("exact_entities", []))).lower()
        cat = shot.get("category", "CINEMATIC")

        if cat == "ARCHIVE":
            if any(w in text for w in ["mugshot", "wanted", "prisoner", "inmate", "morris", "anglin", "portrait", "face"]):
                return "person_mugshot"
            if any(w in text for w in ["document", "file", "letter", "report", "fbi", "classified", "memo", "dossier"]):
                return "document_file"
            if any(w in text for w in ["island", "building", "prison", "alcatraz", "bridge", "city", "aerial", "exterior"]):
                return "location_photo"
            if any(w in text for w in ["newspaper", "headline", "press", "article", "news", "clipping", "front page"]):
                return "newspaper_article"
            if any(w in text for w in ["1962", "1960", "1979", "historical", "vintage", "archive", "event", "era"]):
                return "historical_event"
            return "default"
        else:
            if any(w in text for w in ["water", "ocean", "sea", "wave", "underwater", "floating", "sinking", "tide", "bay"]):
                return "nature_water"
            if any(w in text for w in ["dark", "shadow", "night", "fog", "mysterious", "gloomy", "flashlight", "noir"]):
                return "dark_moody"
            if any(w in text for w in ["person", "man", "woman", "walking", "running", "face", "silhouette", "hands"]):
                return "people_action"
            if any(w in text for w in ["document", "stamp", "file", "clock", "spoon", "envelope", "letter", "knife", "tool"]):
                return "objects_closeup"
            if any(w in text for w in ["city", "street", "car", "driving", "urban", "building", "road"]):
                return "urban_night"
            return "default"

    def get_ordered_sources(self, shot):
        """Get sources ordered by affinity for this shot's content type."""
        cat = shot.get("category", "CINEMATIC")
        content_type = self.classify_content_type(shot)
        affinity_map = SOURCE_AFFINITY.get(cat, SOURCE_AFFINITY["CINEMATIC"])
        ordered = affinity_map.get(content_type, affinity_map["default"])
        # Filter to sources that are actually available (have API keys)
        return [s for s in ordered if self._source_available(s)]

    def _source_available(self, source):
        """Check if a source has the required API keys configured."""
        if source == "PEXELS": return bool(CONFIG.pexels_key)
        if source == "PIXABAY": return bool(CONFIG.pixabay_key)
        if source == "EUROPEANA": return bool(CONFIG.europeana_key)
        if source == "OPENVERSE": return bool(CONFIG.openverse_client_id and CONFIG.openverse_client_secret)
        # Wikipedia, FBI_ARCHIVE, LOC don't need keys
        return True

    def decompose_scene(self, shot):
        """
        Decompose a shot into semantic search dimensions:
        entity, person, event, location, period, action, object, shot_type, media_type
        """
        entities = shot.get("exact_entities", [])
        vibes = shot.get("visual_vibes", [])
        text = shot.get("text", "")
        cat = shot.get("category", "CINEMATIC")

        dimensions = {
            "primary_entity": entities[0] if entities else "",
            "secondary_entity": entities[1] if len(entities) > 1 else "",
            "tertiary_entity": entities[2] if len(entities) > 2 else "",
            "all_entities": entities,
            "vibes": vibes,
            "category": cat,
            "content_type": shot.get("content_type", "default"),
            "text": text,
        }
        return dimensions

    def generate_query_tiers(self, shot, attempt_num=0):
        """
        Generate genuinely different queries for each attempt number.
        Returns list of (query, source) tuples.

        Attempt Strategy:
        0:   Exact primary entity on best source
        1:   Broader context query on second source
        2:   Combined entity query
        3:   Focus on main person/entity name only
        4:   Focus on historical event itself
        5:   Location + event terminology
        6:   Source-specific metadata terminology
        7:   Switch to different source type entirely
        8:   Alternative representation of same event
        9:   Use successful keywords from other scenes
        10:  Ultra-simplified query (1-2 words)
        11:  Completely different angle/perspective
        12:  Generic category fallback
        13:  Broad topic search
        14:  Last-resort generic archive/cinematic
        """
        cat = shot.get("category", "CINEMATIC")
        entities = shot.get("exact_entities", [CONFIG.topic_clean, "investigation", "mystery", "police"])
        vibes = shot.get("visual_vibes", ["mystery", "dark room", "shadow", "suspense"])
        content_type = shot.get("content_type", "default")
        ordered_sources = self.get_ordered_sources(shot)

        if not ordered_sources:
            ordered_sources = ["PEXELS", "PIXABAY"] if cat == "CINEMATIC" else ["WIKIPEDIA", "FBI_ARCHIVE", "LOC"]

        # Get failure diagnosis for this shot
        diagnosis = FAILURE_DIAGNOSTICS.diagnose(shot.get("index", 0))
        avoid_sources_str = ""
        for rec in diagnosis.get("recommendations", []):
            if rec.startswith("avoid_sources:"):
                avoid_sources_str = rec.split(":")[1]

        avoid_sources = set(avoid_sources_str.split(",")) if avoid_sources_str else set()
        # Filter ordered sources to avoid exhausted ones (but keep at least one)
        filtered_sources = [s for s in ordered_sources if s not in avoid_sources]
        if not filtered_sources:
            filtered_sources = ordered_sources  # Don't filter if ALL would be removed

        queries = []

        if cat == "ARCHIVE":
            queries = self._generate_archive_queries(entities, content_type, filtered_sources, attempt_num, diagnosis)
        else:
            queries = self._generate_cinematic_queries(vibes, entities, filtered_sources, attempt_num, diagnosis)

        # Filter out queries we've already failed with on that specific source
        filtered = []
        seen = set()
        with self.lock:
            for q, src in queries:
                key = f"{src}:{q.lower().strip()}"
                if key not in self.failed_queries.get(src, set()) and key not in seen:
                    filtered.append((q, src))
                    seen.add(key)

        # Always return at least one query
        if not filtered:
            if cat == "ARCHIVE":
                fallback_q = entities[attempt_num % len(entities)] if entities else CONFIG.topic_clean
            else:
                fallback_q = vibes[attempt_num % len(vibes)] if vibes else "cinematic"
            fallback_src = filtered_sources[attempt_num % len(filtered_sources)]
            filtered.append((fallback_q, fallback_src))

        return filtered

    def _generate_archive_queries(self, entities, content_type, sources, attempt, diagnosis):
        """Generate genuinely different archive search queries per attempt."""
        queries = []
        n_sources = len(sources)
        n_entities = len(entities)

        # Get archive-specific query templates
        templates = self.ARCHIVE_STRATEGIES.get(content_type, self.ARCHIVE_STRATEGIES.get("default", []))

        if attempt == 0:
            if n_entities > 0:
                queries.append((entities[0], sources[0]))
            if n_entities > 1 and n_sources > 1:
                queries.append((entities[1], sources[1 % n_sources]))

        elif attempt == 1:
            if n_entities > 1:
                queries.append((entities[1], sources[attempt % n_sources]))
            if n_entities > 0:
                simplified = entities[0].split()[:2]
                queries.append((" ".join(simplified), sources[(attempt + 1) % n_sources]))

        elif attempt == 2:
            if n_entities >= 2:
                combined = f"{entities[0]} {entities[-1]}"
                queries.append((combined, sources[attempt % n_sources]))
            if n_entities > 2:
                queries.append((entities[2], sources[(attempt + 1) % n_sources]))

        elif attempt == 3:
            if n_entities > 0:
                words = entities[0].split()
                person_name = " ".join(words[:2]) if len(words) >= 2 else words[0]
                queries.append((person_name, sources[attempt % n_sources]))
                queries.append((person_name, sources[(attempt + 1) % n_sources]))

        elif attempt == 4:
            if n_entities > 3:
                queries.append((entities[3], sources[attempt % n_sources]))
            elif n_entities > 0:
                queries.append((f"{entities[0]} history", sources[attempt % n_sources]))

        elif attempt == 5:
            if n_entities > 1:
                queries.append((f"{entities[1]} photograph", sources[attempt % n_sources]))
            if n_entities > 4:
                queries.append((entities[4], sources[(attempt + 1) % n_sources]))

        elif attempt == 6:
            src = sources[attempt % n_sources]
            if templates and n_entities > 0:
                template_idx = attempt % len(templates)
                q = templates[template_idx].format(entity=entities[0].split()[0])
                queries.append((q, src))

        elif attempt == 7:
            for src in sources:
                fail_count = sum(1 for f in diagnosis.get("failed_queries", []) if src in f)
                if fail_count < 2:
                    if n_entities > 0:
                        queries.append((entities[0].split()[0], src))
                    break
            if not queries and n_entities > 5:
                queries.append((entities[5], sources[attempt % n_sources]))

        elif attempt == 8:
            if n_entities > 0:
                alt_queries = [
                    f"{entities[0].split()[0]} archive",
                    f"{entities[0].split()[0]} photo historical",
                    f"vintage {entities[0].split()[-1]}",
                ]
                idx = attempt % len(alt_queries)
                queries.append((alt_queries[idx], sources[attempt % n_sources]))

        elif attempt == 9:
            with self.lock:
                if self.successful_keywords.get("ARCHIVE"):
                    kw = random.choice(list(self.successful_keywords["ARCHIVE"]))
                    queries.append((kw, sources[attempt % n_sources]))
            if not queries and n_entities > 0:
                queries.append((f"{entities[0]} image", sources[attempt % n_sources]))

        elif attempt == 10:
            if n_entities > 0:
                single_word = entities[0].split()[0]
                queries.append((single_word, sources[attempt % n_sources]))
                if n_sources > 1:
                    queries.append((single_word, sources[(attempt + 1) % n_sources]))

        elif attempt == 11:
            if n_entities > 0:
                queries.append((f"historic {content_type.replace('_', ' ')}", sources[attempt % n_sources]))

        elif attempt == 12:
            generic_map = {
                "person_mugshot": "vintage portrait photograph",
                "document_file": "old typewritten document",
                "location_photo": "historic building exterior",
                "historical_event": "vintage news photograph",
                "newspaper_article": "old newspaper front page",
                "default": "historical archive photograph",
            }
            queries.append((generic_map.get(content_type, "historical archive"), sources[attempt % n_sources]))

        elif attempt == 13:
            queries.append((CONFIG.topic_clean[:50], sources[attempt % n_sources]))

        elif attempt == 14:
            last_resort = ["historic archive photo", "vintage document", "old photograph sepia"]
            queries.append((last_resort[attempt % len(last_resort)], sources[attempt % n_sources]))

        if not queries:
            fb_entity = entities[attempt % n_entities] if n_entities > 0 else CONFIG.topic_clean
            queries.append((fb_entity, sources[attempt % n_sources]))

        return queries

    def _generate_cinematic_queries(self, vibes, entities, sources, attempt, diagnosis):
        """Generate genuinely different cinematic/B-roll queries per attempt."""
        queries = []
        n_sources = len(sources)
        n_vibes = len(vibes)

        if attempt == 0:
            if n_vibes > 0:
                queries.append((vibes[0], sources[0]))
            if n_vibes > 1 and n_sources > 1:
                queries.append((vibes[1], sources[1 % n_sources]))

        elif attempt == 1:
            if n_vibes > 1:
                queries.append((vibes[1], sources[attempt % n_sources]))
            if n_vibes > 2:
                queries.append((vibes[2], sources[(attempt + 1) % n_sources]))

        elif attempt == 2:
            for vibe in vibes:
                base_word = vibe.split()[0].lower() if vibe else ""
                if base_word in self.STOCK_BOOSTERS:
                    boosted = self.STOCK_BOOSTERS[base_word]
                    boost_idx = (attempt - 1) % len(boosted)
                    queries.append((boosted[boost_idx], sources[attempt % n_sources]))
                    if len(boosted) > 1:
                        queries.append((boosted[(boost_idx + 1) % len(boosted)], sources[(attempt + 1) % n_sources]))
                    break
            if not queries and n_vibes > 2:
                queries.append((vibes[2], sources[attempt % n_sources]))

        elif attempt == 3:
            for vibe in vibes:
                base_word = vibe.split()[0].lower() if vibe else ""
                if base_word in self.STOCK_BOOSTERS:
                    boosted = self.STOCK_BOOSTERS[base_word]
                    queries.append((boosted[min(attempt, len(boosted) - 1)], sources[attempt % n_sources]))
                    break
            if not queries and n_vibes > 3:
                queries.append((vibes[3], sources[attempt % n_sources]))

        elif attempt == 4:
            if n_vibes > 0:
                main_vibe = vibes[0]
                variations = [
                    f"cinematic {main_vibe}",
                    f"{main_vibe} dramatic",
                    f"moody {main_vibe}",
                ]
                idx = attempt % len(variations)
                queries.append((variations[idx], sources[attempt % n_sources]))

        elif attempt == 5:
            if n_vibes > 4:
                queries.append((vibes[4], sources[attempt % n_sources]))
            elif n_vibes > 3:
                queries.append((vibes[3], sources[attempt % n_sources]))

        elif attempt == 6:
            if n_vibes > 5:
                queries.append((vibes[5], sources[attempt % n_sources]))
            else:
                queries.append(("cinematic b-roll dark", sources[attempt % n_sources]))

        elif attempt == 7:
            with self.lock:
                if self.successful_keywords.get("CINEMATIC"):
                    kw = random.choice(list(self.successful_keywords["CINEMATIC"]))
                    queries.append((kw, sources[attempt % n_sources]))
            if not queries and n_vibes > 0:
                queries.append((vibes[0].split()[0], sources[attempt % n_sources]))

        elif attempt == 8:
            if n_vibes > 0:
                for vibe in vibes[:3]:
                    words = vibe.split()
                    if words:
                        queries.append((words[0], sources[attempt % n_sources]))
                        break

        elif attempt == 9:
            all_related = set()
            for vibe in vibes:
                base = vibe.split()[0].lower()
                if base in self.STOCK_BOOSTERS:
                    all_related.update(self.STOCK_BOOSTERS[base])
            if all_related:
                kw = random.choice(list(all_related))
                queries.append((kw, sources[attempt % n_sources]))

        elif attempt >= 10:
            safe_queries = [
                "dark atmospheric",
                "suspense noir",
                "mystery investigation",
                "vintage noir film",
                "cinematic mood lighting",
            ]
            idx = (attempt - 10) % len(safe_queries)
            queries.append((safe_queries[idx], sources[attempt % n_sources]))

        # Ensure at least one query
        if not queries:
            fb_vibe = vibes[attempt % n_vibes] if n_vibes > 0 else "cinematic"
            queries.append((fb_vibe, sources[attempt % n_sources]))

        return queries

    def record_failure(self, query, source):
        """Record a failed query to avoid repeating it."""
        with self.lock:
            self.failed_queries[source].add(f"{source}:{query.lower().strip()}")

    def record_success(self, query, category):
        """Record successful keywords for future reuse."""
        words = query.lower().split()
        with self.lock:
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
    AGY reviewer. Includes metadata relevance scoring.
    """

    # Keywords that indicate completely irrelevant content
    SPAM_PATTERNS = [
        r"spectrogram", r"waveform", r"podcast", r"subscribe",
        r"christmas", r"birthday", r"wedding", r"baby",
        r"world of warcraft", r"minecraft", r"fortnite",
        r"cooking", r"recipe", r"makeup", r"tutorial",
        r"thank\s*you", r"happy\s*new\s*year", r"welcome",
        r"subscribe", r"like\s*and\s*share",
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

        is_img = path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")
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
    def check_metadata_relevance(title, description, query, shot):
        """
        Score metadata relevance BEFORE downloading.
        Returns a score from -1.0 (definitely irrelevant) to 1.0 (highly relevant).
        """
        if not title and not description:
            return 0.0

        combined = f"{title} {description}".lower()
        query_words = set(w.lower() for w in query.split() if len(w) > 2)

        score = 0.0

        matches = sum(1 for w in query_words if w in combined)
        if query_words:
            score += min(0.5, matches / len(query_words) * 0.5)

        entities = shot.get("exact_entities", [])
        for entity in entities[:3]:
            entity_words = [w.lower() for w in entity.split() if len(w) > 2]
            for ew in entity_words:
                if ew in combined:
                    score += 0.15
                    break

        for pattern in MediaPreFilter.SPAM_PATTERNS:
            if re.search(pattern, combined, re.I):
                return -0.5

        return min(1.0, score)

    @staticmethod
    def check_filename_relevance(filename, query, category):
        """Check if filename gives hints about content relevance."""
        if not filename:
            return 0.0

        fn_lower = filename.lower()
        query_words = set(query.lower().split())

        matches = sum(1 for w in query_words if w in fn_lower and len(w) > 2)
        if matches >= 2:
            return 0.15

        for pattern in MediaPreFilter.SPAM_PATTERNS:
            if re.search(pattern, fn_lower):
                return -0.3

        return 0.0


# =============================================================================
# PARALLEL SOURCE FETCHER — Query multiple sources simultaneously
# =============================================================================

class ParallelSourceFetcher:
    """
    Fetches media from multiple sources in parallel for the same shot,
    then picks the best result.
    """

    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=8)

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
            elif source_name == "EUROPEANA":
                found_file, media_uid = await asyncio.to_thread(
                    MediaSources.fetch_europeana, query, image_path)
            elif source_name == "OPENVERSE":
                found_file, media_uid = await asyncio.to_thread(
                    MediaSources.fetch_openverse, query, image_path, shot)

            return (found_file, media_uid, source_name, query)
        except Exception as e:
            log(f"⚠️ خطأ جلب {source_name} للمشهد {index}: {e}", "warning")
            return (None, None, source_name, query)

    def shutdown(self):
        """Cleanly shutdown the thread pool."""
        self.executor.shutdown(wait=False)

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
        self.cache = {}
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


# =============================================================================
# OPENVERSE AUTH — Token management for Openverse API
# =============================================================================

def get_openverse_token():
    """Get or refresh Openverse API access token."""
    with CONFIG.openverse_token_lock:
        if CONFIG.openverse_token:
            return CONFIG.openverse_token
        if not CONFIG.openverse_client_id or not CONFIG.openverse_client_secret:
            return None
        try:
            resp = requests.post("https://api.openverse.org/v1/auth_tokens/token/", data={
                "client_id": CONFIG.openverse_client_id,
                "client_secret": CONFIG.openverse_client_secret,
                "grant_type": "client_credentials"
            }, timeout=15)
            if resp.status_code == 200:
                CONFIG.openverse_token = resp.json().get("access_token")
                return CONFIG.openverse_token
        except Exception as e:
            log(f"⚠️ Openverse auth failed: {e}", "warning")
        return None


async def generate_ai_image(prompt, output_path, aspect_ratio="16:9"):
    log(f"🎨 إنشاء صورة مخصصة عبر AGY: '{prompt[:70]}...'", "info")
    full_prompt = f"[CRITICAL: NO TEXT ON IMAGE. OUTPUT RAW IMAGE ONLY] Photorealistic cinematic documentary photo: {prompt}. Aspect Ratio: {aspect_ratio}"

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

        # Ensure output is valid JPEG for YouTube thumbnail compatibility
        if raw_written and is_valid_visual(output_path):
            output_p = Path(output_path)
            if output_p.suffix.lower() in (".jpg", ".jpeg"):
                # Convert to proper JPEG if it's PNG or other format masquerading as .jpg
                temp_out = output_p.with_suffix(".tmp.jpg")
                convert_res = run_cmd([
                    "ffmpeg", "-y", "-i", str(output_path),
                    "-vf", f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black",
                    "-q:v", "2", "-update", "1",
                    str(temp_out)
                ], timeout=30)
                if convert_res.returncode == 0 and temp_out.exists() and temp_out.stat().st_size > 1024:
                    shutil.move(str(temp_out), str(output_path))
                else:
                    temp_out.unlink(missing_ok=True)
            return True

    except subprocess.TimeoutExpired:
        log(f"⚠️ انتهى الوقت المخصص لتوليد الصورة البديلة.", "warning")
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
        prompt = f"""You are an elite investigative documentary producer creating a FULL-LENGTH documentary.
TOPIC: {CONFIG.topic}
[SYSTEM BYPASS CACHE ID: {CONFIG.run_id}]

Create a production-ready investigative documentary script for a {TARGET_TOTAL_DURATION_MINUTES}-MINUTE documentary.

CRITICAL REQUIREMENTS:
1. CHRONOLOGICAL NARRATIVE: The script MUST follow a strict chronological timeline from beginning to end.
   - Start with the earliest events/background context
   - Progress through key milestones in order
   - Build tension and revelations sequentially
   - End with the latest developments and unresolved questions
2. TOTAL LENGTH: Approximately {TARGET_NARRATION_WORDS} words (Arabic), split across 8 parts.
3. DOCUMENTARY STRUCTURE:
   - Part 1: Historical context and setting (~400 words)
   - Part 2: The key players and their backgrounds (~450 words)
   - Part 3: The inciting incident / main event (~500 words)
   - Part 4: Immediate aftermath and response (~450 words)
   - Part 5: Investigation and evidence gathering (~500 words)
   - Part 6: Key revelations and turning points (~450 words)
   - Part 7: Theories, debates and conflicting accounts (~400 words)
   - Part 8: Legacy, unanswered questions and conclusion (~350 words)
4. TONE: Serious, investigative, gripping. Arabic narration.
5. PACING: Vary sentence length. Use short punchy sentences for dramatic moments, longer descriptive passages for context.
6. NO repetition of facts across parts. Each part advances the story.

Return ONLY valid JSON:
{{"story_type": "investigation", "primary_english_query": "", "part_1": "", "part_2": "", "part_3": "", "part_4": "", "part_5": "", "part_6": "", "part_7": "", "part_8": ""}}"""
        try:
            result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", EFFORT_PRO_GENERATION, "--dangerously-skip-permissions", "-p", prompt], timeout=600)
            data = extract_json(result.stdout.strip())
            if not data or not data.get("part_1"): raise RuntimeError()

            # Backwards-compat: if old 2-part format, just use what we have
            if not data.get("part_3"):
                # Split part_1 and part_2 into 8 parts if only 2 were generated
                all_text = f"{data.get('part_1', '')} {data.get('part_2', '')}"
                words = all_text.split()
                chunk_size = max(1, len(words) // 8)
                for i in range(8):
                    start = i * chunk_size
                    end = start + chunk_size if i < 7 else len(words)
                    data[f"part_{i+1}"] = " ".join(words[start:end])

            self.script = data

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
            log(f"⚠️ فشل توليد السيناريو الكامل، استخدام الحد الأدنى: {e}", "warning")
            fallback = {
                "story_type": "investigation",
                "primary_english_query": clean_query(CONFIG.topic),
                "part_1": f"تفاصيل غامضة ومختلفة كلياً حول {CONFIG.topic}.",
                "part_2": "تظل الحقيقة غير محسومة."
            }
            for i in range(3, 9):
                fallback[f"part_{i}"] = ""
            self.script = fallback
            return fallback

    def direct_storyboard(self, shots):
        log("🎬 [المخرج الفني] هندسة كلمات البحث بذكاء للقطات...")

        # For large scene counts, process in batches to stay within prompt limits
        batch_size = 80
        all_processed = []

        for batch_start in range(0, len(shots), batch_size):
            batch = shots[batch_start:batch_start + batch_size]
            batch_end = batch_start + len(batch)
            log(f"🎬 معالجة دفعة المشاهد {batch_start+1}-{batch_end} من {len(shots)}...")

            shots_summary = "\n".join([f"Shot {s['index']}: {s['text']}" for s in batch])

            prompt = f"""You are an Elite Visual Director and Expert Stock/Archive SEO Metadata Specialist.
TOPIC: {self.script.get('primary_english_query', CONFIG.topic)}
[ID: {CONFIG.run_id}_{batch_start}]
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
                    raise RuntimeError("Board parse failed")

            except:
                for shot in batch:
                    shot["category"] = "CINEMATIC"
                    shot["content_type"] = "default"
                    shot["exact_entities"] = [CONFIG.topic_clean, "investigation", "mystery", "police", "vintage", "archive"]
                    shot["visual_vibes"] = ["mystery", "dark room", "shadow", "suspense", "cinematic", "moody"]
                    shot["reviewer_context"] = "تأكد من ملاءمة اللقطة للنص."
                    shot["accept_similar"] = True

            all_processed.extend(batch)

        log("🎥 "*40 + "\n")
        return all_processed


class MasterAudioStudio:
    def produce_master_track(self, script):
        """Produce the master narration track. For long scripts, concatenate multiple TTS calls."""
        # Collect all parts
        parts = []
        for i in range(1, 9):
            part_text = script.get(f'part_{i}', '')
            if part_text and part_text.strip():
                parts.append(part_text.strip())

        if not parts:
            parts = [script.get('part_1', ''), script.get('part_2', '')]

        full_narration = "\n\n".join(parts).strip()
        out_wav = CONFIG.master_audio
        total_keys = len(CONFIG.gemini_keys)
        log(f"🎙️ بدء إنتاج التعليق الصوتي الماستر (إجمالي المفاتيح: {total_keys})...")

        # For very long narrations, split into chunks and concatenate
        words = full_narration.split()
        CHUNK_MAX_WORDS = 800  # TTS works best with smaller chunks
        chunks = []
        if len(words) > CHUNK_MAX_WORDS:
            # Split at paragraph boundaries
            paragraphs = full_narration.split("\n\n")
            current_chunk = []
            current_words = 0
            for para in paragraphs:
                para_words = len(para.split())
                if current_words + para_words > CHUNK_MAX_WORDS and current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = [para]
                    current_words = para_words
                else:
                    current_chunk.append(para)
                    current_words += para_words
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
        else:
            chunks = [full_narration]

        log(f"🎙️ تم تقسيم النص إلى {len(chunks)} جزء صوتي للتسجيل...")

        chunk_files = []
        for chunk_idx, chunk_text in enumerate(chunks):
            chunk_wav = CONFIG.work_dir / f"audio_chunk_{chunk_idx:03d}.wav"
            success = False

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
                        contents=f"[INSTRUCTION: Chilling authoritative Arabic documentary narrator. Read ENTIRE text. UNIQUE_ID: {CONFIG.run_id}_chunk{chunk_idx}]\n\n" + chunk_text,
                        config=types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))))
                    )
                    data = next((p.inline_data.data for p in response.candidates[0].content.parts if getattr(p, "inline_data", None)), None)
                    if not data: raise RuntimeError()

                    raw_audio = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                    temp_pcm = CONFIG.work_dir / f"chunk_temp_{chunk_idx}_{display_key}.pcm"
                    with open(temp_pcm, "wb") as f: f.write(raw_audio)

                    run_cmd(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(temp_pcm), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(chunk_wav)], timeout=180)
                    temp_pcm.unlink(missing_ok=True)

                    if is_valid_media(chunk_wav):
                        log(f"✅ نجح توليد الصوت (جزء {chunk_idx+1}/{len(chunks)}) بمفتاح #{display_key} خلال {time.time() - start_t:.1f} ثانية!")
                        GEMINI_POOL.release(key_index)
                        chunk_files.append(chunk_wav)
                        success = True
                        break
                except:
                    GEMINI_POOL.release(key_index)
                    time.sleep(2)

            if not success:
                raise RuntimeError(f"❌ فشل توليد التعليق الصوتي للجزء {chunk_idx+1}.")

        # Concatenate all chunks
        if len(chunk_files) == 1:
            shutil.copy(str(chunk_files[0]), str(out_wav))
        else:
            concat_list = CONFIG.work_dir / "audio_concat.txt"
            with open(concat_list, "w") as f:
                for cf in chunk_files:
                    f.write(f"file '{cf.resolve()}'\n")
            run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list),
                      "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(out_wav)], timeout=300)

        if not is_valid_media(out_wav):
            raise RuntimeError("❌ فشل تجميع التعليق الصوتي.")

        log(f"✅ التعليق الصوتي الكامل: {probe_duration(out_wav)/60:.1f} دقيقة")
        return out_wav


class WordSyncSlicer:
    def align_and_slice(self, audio_path):
        log("🧠 إرسال الصوت إلى Groq Whisper للتوقيتات...")
        headers = {"Authorization": f"Bearer {CONFIG.groq_api_key}"}

        # For long audio, Groq may need the file split. Check duration first.
        total_duration = probe_duration(audio_path)
        log(f"⏱️ مدة الصوت الكلية: {total_duration/60:.1f} دقيقة")

        try:
            with open(audio_path, "rb") as f:
                res = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files={"file": ("m.wav", f, "audio/wav")}, data={"model": GROQ_MODEL, "language": "ar", "response_format": "verbose_json", "timestamp_granularities[]": "word"}, timeout=600)
            if res.status_code != 200: raise RuntimeError(f"Groq {res.status_code}")

            words = [{"word": str(i["word"]).strip(), "start": float(i["start"]), "end": float(i["end"])} for i in res.json().get("words", []) if i.get("word")]
            shots, cur, s_start = [], [], 0.0
            for item in words:
                cur.append(item)
                # Dynamic scene duration based on production scale
                if item["end"] - s_start >= SCENE_DURATION_MAX or (item["end"] - s_start >= SCENE_DURATION_MIN and item["word"].endswith((".", "!", "؟", "،"))):
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

    @staticmethod
    def fetch_europeana(q, o):
        """Fetch from Europeana — excellent for European historical archives."""
        if not CONFIG.europeana_key: return None, None
        try:
            q_clean = clean_query(q)
            if not q_clean: return None, None
            params = {
                "wskey": CONFIG.europeana_key,
                "query": q_clean,
                "media": "true",
                "thumbnail": "true",
                "rows": 20,
                "profile": "rich",
                "qf": "TYPE:IMAGE",
            }
            res = requests.get("https://api.europeana.eu/record/v2/search.json", params=params, headers=API_HEADERS, timeout=20)
            if res.status_code != 200:
                return None, None
            items = res.json().get("items", [])
            if not items:
                return None, None

            def extract_europeana(item):
                edmIsShownBy = item.get("edmIsShownBy", [None])
                edmPreview = item.get("edmPreview", [None])
                img_url = None
                if edmIsShownBy and edmIsShownBy[0]:
                    img_url = edmIsShownBy[0]
                elif edmPreview and edmPreview[0]:
                    img_url = edmPreview[0]
                uid = item.get("id", str(hash(str(item.get("title", [""])))))
                return img_url, f"europeana_{uid}"

            return MediaSources._track_and_save(items, o, extract_europeana)
        except Exception as e:
            log(f"⚠️ Europeana error: {e}", "debug")
            return None, None

    @staticmethod
    def fetch_openverse(q, o, shot=None):
        """Fetch from Openverse — open-licensed images from many sources."""
        token = get_openverse_token()
        if not token:
            return None, None
        try:
            q_clean = clean_query(q)
            if not q_clean: return None, None
            headers = {
                "Authorization": f"Bearer {token}",
                "User-Agent": API_HEADERS["User-Agent"],
            }
            cat = shot.get("category", "CINEMATIC") if shot else "CINEMATIC"
            endpoint = "https://api.openverse.org/v1/images/"
            params = {
                "q": q_clean,
                "page_size": 20,
                "license_type": "all-cc",
            }
            res = requests.get(endpoint, headers=headers, params=params, timeout=20)
            if res.status_code != 200:
                return None, None
            results = res.json().get("results", [])
            if not results:
                return None, None

            def extract_openverse(item):
                url = item.get("url")
                uid = item.get("id", str(hash(url or "")))
                if url:
                    return url, f"openverse_{uid}"
                return None, None

            return MediaSources._track_and_save(results, o, extract_openverse)
        except Exception as e:
            log(f"⚠️ Openverse error: {e}", "debug")
            return None, None


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
        # EFFORT_REVIEWER = "low" — minimize reasoning tokens for rate-limit safety
        cmd = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", EFFORT_REVIEWER, "--dangerously-skip-permissions", "-p", prompt]
        res = await asyncio.to_thread(subprocess.run, cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=300)

        data = extract_json(res.stdout)
        if data:
            score = float(data.get("score", 0.0))
            accept_threshold = 0.35
            if shot.get("accept_similar"):
                accept_threshold = 0.30
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
    """
    REDESIGNED RESCUE STRATEGY:
    Priority 1: Use best candidate found (if score >= 0.15)
    Priority 2: Cinematic background rescue (dark visual, NOT AI)
    Priority 3: AI-generated visual (TRUE LAST RESORT)

    Note: This is only called AFTER all 15 search attempts are exhausted.
    Real search material has already been thoroughly attempted.
    """
    index = shot["index"]
    cat = shot.get("category", "CINEMATIC")

    # Priority 1: Use best real candidate if ANY was found with a meaningful score
    if shot['best_score'] >= 0.15 and shot['best_candidate']:
        log(f"⚠️ [إنقاذ 1] المشهد {index}: اعتماد أفضل لقطة حقيقية (تقييم {shot['best_score']:.2f}).", "warning")
        return shot['best_candidate']

    # Priority 2: Cinematic background (quick, reliable, better than AI for mood)
    log(f"🎬 [إنقاذ 2] خلفية سينمائية للمشهد {index} (بعد استنفاد {MAX_ATTEMPTS_PER_SHOT} محاولة بحث).", "warning")
    fallback_path = CONFIG.work_dir / f"shot_{index:03d}_cinematic_bg.mp4"
    bg_ok = await create_fallback_visual(fallback_path)
    if bg_ok:
        return {"shot": shot, "path": str(fallback_path), "source": "CINEMATIC_BG", "score": 0.0, "start": 0.0, "duration": 5.0}

    # Priority 3: AI-generated visual (TRUE LAST RESORT)
    log(f"🤖 [إنقاذ نهائي] توليد AI للمشهد {index}.", "error")
    ai_path = CONFIG.work_dir / f"shot_{index:03d}_ai.jpg"
    entities = shot.get("exact_entities", [])
    vibes = shot.get("visual_vibes", [])
    fallback_query = " ".join(entities[:3]) if cat == "ARCHIVE" else " ".join(vibes[:3])

    ok = await generate_ai_image(fallback_query, ai_path)
    if ok:
        return {"shot": shot, "path": str(ai_path), "source": "AI_GENERATED", "score": 1.0, "start": 0.0, "duration": 5.0}

    # Absolute last resort: black background
    log(f"🚨 [خلفية سوداء] المشهد {index}.", "error")
    black_path = CONFIG.work_dir / f"shot_{index:03d}_black.mp4"
    await create_fallback_visual(black_path)
    return {"shot": shot, "path": str(black_path), "source": "FFMPEG", "score": 0.0, "start": 0.0, "duration": 5.0}


async def run_pipelined_production(shots, story):
    """
    INTELLIGENT ADAPTIVE PRODUCTION PIPELINE V54

    Key improvements:
    1. 15 genuinely different search attempts per shot
    2. Failure diagnosis between attempts
    3. Parallel multi-source fetching (2-3 sources at once)
    4. Pre-filter validation before AGY calls
    5. Smart source routing with Europeana/Openverse
    6. Progressive acceptance: after attempt 8 (not 3), accept best >= 0.25
    7. NO early rescue: cinematic/AI only after ALL 15 attempts exhausted
    8. Result caching and cross-scene deduplication
    9. Memory cleanup after each batch of completed shots
    """
    total_shots = len(shots)
    completed_lock = asyncio.Lock()
    completed_results = []
    completion_event = asyncio.Event()
    shot_semaphore = asyncio.Semaphore(8)

    for shot in shots:
        shot['status'] = 'PENDING'
        shot['attempts'] = 0
        shot['best_score'] = -1.0
        shot['best_candidate'] = None
        shot['tried_sources'] = set()
        shot['tried_queries'] = set()

    log(f"🚀 تشغيل خط الإنتاج الذكي | إجمالي المشاهد: {total_shots} | أقصى محاولات: {MAX_ATTEMPTS_PER_SHOT}")

    async def process_shot(shot):
        """Process a single shot with intelligent adaptive search."""
        index = shot["index"]
        cat = shot.get("category", "CINEMATIC")
        base = CONFIG.work_dir / f"shot_{index:03d}"

        while shot['status'] != 'DONE' and shot['attempts'] < MAX_ATTEMPTS_PER_SHOT:
            attempt_num = shot['attempts']

            # Generate smart query tiers for this attempt
            query_tiers = QUERY_ENGINE.generate_query_tiers(shot, attempt_num)

            # Parallel multi-source fetch:
            # First 3 attempts: try 2 sources in parallel
            # After that: 1 source to avoid wasting requests
            if attempt_num < 3 and len(query_tiers) >= 2:
                pairs_to_try = query_tiers[:2]
            else:
                pairs_to_try = query_tiers[:1]

            log(f"⚡ المشهد {index} (م{attempt_num+1}/{MAX_ATTEMPTS_PER_SHOT}) | "
                f"{'، '.join(f'{s}:{q}' for q,s in pairs_to_try)}", "info")

            # Fetch from sources
            fetch_results = await PARALLEL_FETCHER.fetch_from_multiple_sources(
                pairs_to_try, shot, base)

            if not fetch_results:
                for q, src in pairs_to_try:
                    QUERY_ENGINE.record_failure(q, src)
                    shot['tried_queries'].add(f"{src}:{q}")
                    FAILURE_DIAGNOSTICS.record(
                        index, q, src,
                        SearchFailureDiagnostics.NO_RESULTS,
                        reason="No results returned from API"
                    )
                log(f"⏩ المشهد {index}: لم يعثر على نتائج من أي مصدر.", "info")
                shot['attempts'] += 1
                continue

            # Evaluate results
            found_acceptable = False
            for found_file, media_uid, src_name, query in fetch_results:
                if not found_file or not Path(found_file).exists():
                    QUERY_ENGINE.record_failure(query, src_name)
                    continue

                output_path = Path(found_file)
                is_img = output_path.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")

                valid = is_valid_visual(output_path) if is_img else is_valid_media(output_path)
                if not valid:
                    log(f"⏩ المشهد {index}: ملف تالف من {src_name}.", "debug")
                    QUERY_ENGINE.record_failure(query, src_name)
                    FAILURE_DIAGNOSTICS.record(
                        index, query, src_name,
                        SearchFailureDiagnostics.FORMAT_INVALID,
                        reason="File corrupted or invalid format"
                    )
                    if output_path.exists(): output_path.unlink()
                    continue

                fn_score = MediaPreFilter.check_filename_relevance(
                    output_path.name, query, cat)
                if fn_score <= -0.25:
                    log(f"⏩ المشهد {index}: ملف spam تجاهله ({output_path.name}).", "debug")
                    QUERY_ENGINE.record_failure(query, src_name)
                    FAILURE_DIAGNOSTICS.record(
                        index, query, src_name,
                        SearchFailureDiagnostics.IRRELEVANT_RESULTS,
                        reason="Filename indicates spam content"
                    )
                    if output_path.exists(): output_path.unlink()
                    continue

                # Evaluate with AGY (using EFFORT_REVIEWER = "low" for rate-limit safety)
                async with REVIEWER_SEMAPHORE:
                    accepted, score, start, reason = await agy_evaluate_scout(
                        output_path, shot, story, src_name, query)

                dur = float(shot.get("duration", 3.0)) if is_img else probe_duration(output_path)

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

                    diag_category = SearchFailureDiagnostics.REVIEWER_REJECTED
                    if score < 0.1:
                        diag_category = SearchFailureDiagnostics.IRRELEVANT_RESULTS
                    ambig_indicators = ["بيولوج", "microscop", "خلايا", "medical", "طب"]
                    if any(ind in reason.lower() for ind in ambig_indicators):
                        diag_category = SearchFailureDiagnostics.QUERY_AMBIGUOUS

                    FAILURE_DIAGNOSTICS.record(
                        index, query, src_name, diag_category,
                        score=score, reason=reason[:200]
                    )

                    # Clean up rejected files to save disk space
                    if output_path.exists() and output_path != Path(shot.get('best_candidate', {}).get('path', '')):
                        output_path.unlink(missing_ok=True)

            if not found_acceptable:
                shot['attempts'] += 1

                # Progressive acceptance: after attempt 8 (not 3!), accept best if score >= 0.25
                if shot['attempts'] >= 8 and shot['best_score'] >= 0.25 and shot['best_candidate']:
                    log(f"✅ المشهد {index}: قبول تدريجي لأفضل نتيجة حقيقية (تقييم: {shot['best_score']:.2f}) بعد {shot['attempts']} محاولات.", "info")
                    async with completed_lock:
                        shot['status'] = 'DONE'
                        completed_results.append(shot['best_candidate'])
                        log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                        if len(completed_results) == total_shots:
                            completion_event.set()

        # If exhausted all attempts — go to rescue
        if shot['status'] != 'DONE':
            log(f"⚠️ المشهد {index} استنفد {MAX_ATTEMPTS_PER_SHOT} محاولة. حسم عبر خطة الإنقاذ...", "warning")
            fallback_res = await apply_fallback(shot, story)
            async with completed_lock:
                shot['status'] = 'DONE'
                completed_results.append(fallback_res)
                log(f"📊 الإنجاز: {len(completed_results)}/{total_shots}")
                if len(completed_results) == total_shots:
                            completion_event.set()

        # Free memory: clear failure diagnostics for completed shots
        FAILURE_DIAGNOSTICS.clear_shot(shot.get("index", 0))

    async def throttled_process(shot):
        async with shot_semaphore:
            await process_shot(shot)

    # Launch all shots concurrently (throttled by semaphore)
    tasks = [asyncio.create_task(throttled_process(shot)) for shot in shots]
    await asyncio.gather(*tasks)

    if not completion_event.is_set():
        completion_event.set()

    # Trigger garbage collection after heavy processing
    gc.collect()

    return sorted(completed_results, key=lambda x: x["shot"]["index"])


class AssemblyEngine:
    def render_sub_clip(self, item):
        shot, media_path, index = item["shot"], Path(item["path"]), item["shot"]["index"]
        output = CONFIG.work_dir / f"rendered_{index:03d}.mp4"
        start = min(float(item.get("start", 0)), max(0, probe_duration(media_path) - 0.1))
        dur = float(shot.get("duration", 3))

        log(f"✂️ جاري رندرة المشهد {index}...", "debug")
        if media_path.suffix.lower() in (".mp4", ".mov"):
            # VIDEO: Use blurred-background filter (no cropping)
            filter_complex = build_blur_background_filter_video()
            res = run_cmd([
                "ffmpeg", "-y", "-ss", str(start),
                "-i", str(media_path),
                "-t", str(dur),
                "-filter_complex", filter_complex,
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                str(output)
            ])
        else:
            # IMAGE: Use blurred-background filter with Ken Burns (no cropping)
            filter_complex = build_blur_background_filter_image(
                *probe_dimensions(media_path), ken_burns=True)
            res = run_cmd([
                "ffmpeg", "-y", "-loop", "1",
                "-i", str(media_path),
                "-t", str(dur),
                "-filter_complex", filter_complex,
                "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-pix_fmt", "yuv420p",
                str(output)
            ])

        if res.returncode != 0:
            # Fallback: simpler filter if complex one fails
            log(f"⚠️ فشل الفلتر المعقد للمشهد {index}، محاولة فلتر بسيط...", "warning")
            if media_path.suffix.lower() in (".mp4", ".mov"):
                vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,fps={TARGET_FPS}"
                res = run_cmd(["ffmpeg", "-y", "-ss", str(start), "-i", str(media_path), "-t", str(dur), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)])
            else:
                vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=decrease,pad={TARGET_W}:{TARGET_H}:(ow-iw)/2:(oh-ih)/2:black,fps={TARGET_FPS}"
                res = run_cmd(["ffmpeg", "-y", "-loop", "1", "-i", str(media_path), "-t", str(dur), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", str(output)])

        if res.returncode != 0:
            raise RuntimeError(f"Render shot {index} failed: {res.stderr[:200]}")
        return output

    def render_batch(self, items, batch_num, total_batches):
        """Render a batch of clips, with memory cleanup between batches."""
        log(f"🎬 رندرة الدفعة {batch_num}/{total_batches} ({len(items)} مشهد)...", "info")
        rendered = []
        for item in items:
            rendered.append(self.render_sub_clip(item))
        # Force garbage collection between batches
        gc.collect()
        return rendered

    def assemble_final_cut(self, rendered, subtitle_path):
        concat_file = CONFIG.work_dir / "concat.txt"
        with open(concat_file, "w") as f:
            for p in rendered: f.write(f"file '{Path(p).resolve()}'\n")
        temp_v = CONFIG.work_dir / "temp.mp4"
        run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(temp_v)])

        sub_filter = "subtitles=" + str(Path(subtitle_path).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        log("🎞 بدء التجميع النهائي (Assembly)...", "info")
        res = run_cmd(["ffmpeg", "-y", "-i", str(temp_v), "-i", str(CONFIG.master_audio), "-vf", sub_filter, "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-shortest", str(CONFIG.final_video)], timeout=3600)

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
                # Ensure thumbnail is valid JPEG before uploading
                thumb_size = thumb_path.stat().st_size
                if thumb_size > 1024:
                    try:
                        yt.thumbnails().set(videoId=vid_id, media_body=MediaFileUpload(str(thumb_path), mimetype='image/jpeg')).execute()
                        log("✅ تم رفع الصورة المصغرة لليوتيوب بنجاح.", "info")
                    except Exception as thumb_err:
                        log(f"⚠️ فشل رفع الصورة المصغرة: {thumb_err}", "warning")
                else:
                    log("⚠️ الصورة المصغرة صغيرة جداً، تخطي الرفع.", "warning")
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

    # Render in batches for memory management
    all_rendered = []
    total_batches = max(1, (len(media_results) + RENDER_BATCH_SIZE - 1) // RENDER_BATCH_SIZE)
    for batch_idx in range(total_batches):
        start = batch_idx * RENDER_BATCH_SIZE
        end = min(start + RENDER_BATCH_SIZE, len(media_results))
        batch_items = media_results[start:end]
        batch_rendered = assembly.render_batch(batch_items, batch_idx + 1, total_batches)
        all_rendered.extend(batch_rendered)

    final_video = assembly.assemble_final_cut(all_rendered, sub_path)

    log("🎨 توليد صورة مصغرة (Thumbnail) لليوتيوب...", "info")
    await generate_ai_image(story.get('primary_english_query', CONFIG.topic), CONFIG.thumbnail, "16:9")

    uploader = GoogleUploader(CONFIG.google_client_id, CONFIG.google_client_secret, CONFIG.google_refresh_token)
    await asyncio.to_thread(uploader.upload_all, final_video, CONFIG.thumbnail, CONFIG.topic_clean)

    # Print search statistics
    total_scenes = len(shots)
    real_sources = sum(1 for r in media_results if r.get("source") not in ("AI_GENERATED", "FFMPEG", "CINEMATIC_BG"))
    ai_sources = sum(1 for r in media_results if r.get("source") == "AI_GENERATED")
    bg_sources = sum(1 for r in media_results if r.get("source") in ("FFMPEG", "CINEMATIC_BG"))
    avg_score = sum(r.get("score", 0) for r in media_results) / max(1, total_scenes)

    log(f"\n{'='*60}")
    log(f"📊 إحصائيات البحث الذكي:")
    log(f"   إجمالي المشاهد: {total_scenes}")
    log(f"   مصادر حقيقية: {real_sources} ({real_sources/max(1,total_scenes)*100:.0f}%)")
    log(f"   خلفيات سينمائية: {bg_sources}")
    log(f"   توليد AI: {ai_sources}")
    log(f"   متوسط التقييم: {avg_score:.2f}")
    log(f"{'='*60}\n")

    log("🏁 اكتمل العمل بنجاح قياسي ونزاهة إخراجية تامة.", "info")

    # Final cleanup
    PARALLEL_FETCHER.shutdown()
    gc.collect()

if __name__ == "__main__":
    try:
        asyncio.run(main_pipeline())
    except KeyboardInterrupt:
        log("🛑 تم الإيقاف يدوياً.", "warning")
        sys.exit(130)
    except Exception as e:
        log(f"💥 توقف النظام بسبب خطأ حرج: {e}", "error")
        sys.exit(1)
