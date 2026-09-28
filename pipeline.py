#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE - HYBRID V23 FIXED

- Script/reviewer/repair: Antigravity Gemini 3.1 Pro High
- Per-candidate visual reviewer: Antigravity Gemini 3.6 Flash High
- TTS: Gemini 3.8 Flash TTS / Charon
- Groq: Whisper word timestamps ONLY
- Real media: Pexels / Pixabay / Mapbox / Wikipedia
- No fallback graphics, placeholders, or fake evidence
- Pexels 3 candidates + Pixabay 3 candidates, repeated for 4 cycles
- Every final version is preserved and uploaded to Drive + YouTube when configured,
  including REJECTED versions
- TTS success cooldown is EXACTLY 30 seconds
"""

import os
import sys
import json
import time
import re
import logging
import subprocess
import base64
import hashlib
import shutil
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field
from datetime import datetime

import requests
from PIL import Image
from arabic_reshaper import reshape
from bidi.algorithm import get_display
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ==================================================================================================
# 1. Logging / runtime
# ==================================================================================================

class ProTelemetryFormatter(logging.Formatter):
    COLORS = {
        "INFO": "\x1b[38;5;39m",
        "WARNING": "\x1b[38;5;214m",
        "ERROR": "\x1b[38;5;196m",
        "CRITICAL": "\x1b[48;5;196;38;5;231m\x1b[1m",
    }
    RESET = "\x1b[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        return logging.Formatter(
            f"{color}%(asctime)s | [%(levelname)s] | %(message)s{self.RESET}",
            datefmt="%H:%M:%S",
        ).format(record)


def setup_logger():
    logger = logging.getLogger("HybridMaster")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(ProTelemetryFormatter())
        logger.addHandler(ch)
        fh = logging.FileHandler("production_logs.txt", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s | [%(levelname)s] | %(message)s"))
        logger.addHandler(fh)
    return logger


log = setup_logger()
MEMORY_FILE = Path("director_memory.md")
CURRENT_PIPELINE = Path(__file__).resolve()
MASTER_START_TS = float(os.environ.get("MASTER_START_TS", str(time.time())))
FINAL_REVIEW_ROUND = int(os.environ.get("FINAL_REVIEW_ROUND", "0"))
MAX_FINAL_REPAIRS = 3


# ==================================================================================================
# 2. Memory / config
# ==================================================================================================

def read_memory():
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text(encoding="utf-8")
    return "هذه أول جلسة. ركز على إنتاج وثائقي تحقيقي طويل مع مشاهد حقيقية مرتبطة بالسرد."


def append_memory(summary):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n\n### تقرير الجلسة [{now}]\n{summary}")


@dataclass
class PipelinePaths:
    base: Path = field(default_factory=lambda: Path("./output_build"))
    cache: Path = field(default_factory=lambda: Path("./output_build/cache"))
    manifest: Path = field(default_factory=lambda: Path("./output_build/master_manifest.json"))
    final_review: Path = field(default_factory=lambda: Path("./output_build/final_review.json"))

    def initialize(self):
        self.base.mkdir(parents=True, exist_ok=True)
        self.cache.mkdir(parents=True, exist_ok=True)


class HybridConfig:
    topic = os.environ.get("VIDEO_TOPIC", "لغز اختفاء طائرة دي بي كوبر")
    paths = PipelinePaths()
    gemini_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
    pexels = os.environ.get("PEXELS_API_KEY", "")
    pixabay = os.environ.get("PIXABAY_API_KEY", "")
    mapbox = os.environ.get("MAPBOX_API_KEY", "")
    groq = os.environ.get("GROQ_API_KEY", "")
    freesound = os.environ.get("FREESOUND_API_KEY", "")
    google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    drive_token = os.environ.get("DRIVE_REFRESH_TOKEN", "")
    yt_refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    youtube_privacy = os.environ.get("YOUTUBE_PRIVACY_STATUS", "private").lower().strip()
    if youtube_privacy not in {"private", "unlisted", "public"}:
        youtube_privacy = "private"


CONFIG = HybridConfig()
CONFIG.paths.initialize()
if not CONFIG.gemini_keys:
    sys.exit("🛑 حرج: مفاتيح GEMINI_API_KEY مفقودة!")


# ==================================================================================================
# 3. Helpers
# ==================================================================================================

def safe_unlink(path: Path):
    try:
        if path.exists():
            path.unlink()
    except Exception as e:
        log.warning(f"⚠️ تعذر حذف {path}: {e}")


def valid_file(path: Path, minimum_size=50000):
    try:
        return path.exists() and path.is_file() and path.stat().st_size >= minimum_size
    except Exception:
        return False


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def elapsed_seconds():
    return time.time() - MASTER_START_TS


def runtime_expired():
    return elapsed_seconds() >= 3 * 3600 + 45 * 60


def safe_topic_slug(topic):
    slug = re.sub(r"[^\w\u0600-\u06FF\-]+", "_", topic, flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return (slug or "Documentary")[:90]


def version_filename(round_number, status):
    return f"{safe_topic_slug(CONFIG.topic)}_V{round_number:02d}_{status}.mp4"


def parse_json_object(text):
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ==================================================================================================
# 4. Hybrid Director
# ==================================================================================================

class Hybrid_Director:

    def plan_documentary(self):
        if CONFIG.paths.manifest.exists():
            try:
                existing = json.loads(CONFIG.paths.manifest.read_text(encoding="utf-8"))
                if isinstance(existing, list) and existing:
                    log.info(f"♻️ استخدام السيناريو الموجود: {len(existing)} مشهداً.")
                    return existing
            except Exception:
                log.warning("⚠️ manifest موجود لكنه غير صالح. سيتم إعادة توليده.")

        prompt = f"""
أنت كبير المخرجين والباحثين في إنتاج وثائقيات التحقيق.
موضوع الوثائقي: {CONFIG.topic}

أنشئ 40 إلى 50 مشهداً. الهدف وثائقي طويل.
كل مشهد يحتوي 60-80 كلمة عربية فصحى، مع search_query بصري واقعي.
media_type يجب أن يكون واحداً من PEXELS أو PIXABAY أو MAPBOX أو WIKIPEDIA.
كل مشهد يجب أن يخدم معلومة السرد مباشرة.
لا تستخدم صوراً عشوائية أو أوصافاً يستحيل العثور عليها واقعياً.
foley_type باللغة الإنجليزية.

الذاكرة:
{read_memory()}

أخرج JSON Array فقط:
[
  {{
    "scene_num": 1,
    "media_type": "PEXELS",
    "search_query": "specific real visual search query",
    "foley_type": "rain",
    "narration": "..."
  }}
]
"""

        for attempt in range(3):
            try:
                result = subprocess.run(
                    ["agy", "--model", "gemini-3.1-pro-high", "-p", prompt],
                    capture_output=True, text=True, check=True, timeout=900,
                )
                match = re.search(r"\[.*\]", result.stdout.strip(), re.DOTALL)
                if not match:
                    raise ValueError("Antigravity لم يرجع JSON Array.")
                data = json.loads(match.group(0))
                if not isinstance(data, list) or not data:
                    raise ValueError("السيناريو فارغ.")
                write_json(CONFIG.paths.manifest, data)
                log.info(f"✅ تم إنشاء السيناريو: {len(data)} مشهداً.")
                return data
            except Exception as e:
                log.warning(f"⚠️ خطأ توليد السيناريو ({attempt + 1}/3): {e}")
                time.sleep(5)
        raise SystemExit("🛑 فشل Antigravity في كتابة السيناريو.")

    def evaluate_scene_with_scout(self, media_path: Path, narration: str):
        log.info("👁️ Gemini 3.6 Flash High يفحص المرشح...")
        eval_img = CONFIG.paths.cache / f"{media_path.stem}_vision_review.jpg"
        frame_paths = []
        try:
            if media_path.suffix.lower() == ".mp4":
                try:
                    duration = float(subprocess.check_output([
                        "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(media_path)
                    ], stderr=subprocess.DEVNULL).decode().strip())
                except Exception:
                    duration = 5.0
                for idx, pos in enumerate((0.20, 0.50, 0.80)):
                    fp = CONFIG.paths.cache / f"{media_path.stem}_frame_{idx}.jpg"
                    subprocess.run([
                        "ffmpeg", "-y", "-ss", str(max(0.2, duration * pos)), "-i", str(media_path),
                        "-frames:v", "1", "-q:v", "2", str(fp)
                    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
                    if fp.exists():
                        frame_paths.append(fp)
                imgs = []
                for fp in frame_paths:
                    try:
                        imgs.append(Image.open(fp).convert("RGB"))
                    except Exception:
                        pass
                if not imgs:
                    return {"valid": False, "montage": "NORMAL", "reason": "تعذر استخراج الإطارات."}
                w, h = 640, 360
                sheet = Image.new("RGB", (w * len(imgs), h), "black")
                for idx, img in enumerate(imgs):
                    img.thumbnail((w, h))
                    sheet.paste(img, (idx * w, 0))
                sheet.save(eval_img, "JPEG", quality=94)
            else:
                Image.open(media_path).convert("RGB").save(eval_img, "JPEG", quality=94)
        except Exception as e:
            return {"valid": False, "montage": "NORMAL", "reason": str(e)}
        finally:
            for fp in frame_paths:
                safe_unlink(fp)

        if not eval_img.exists():
            return {"valid": False, "montage": "NORMAL", "reason": "review image missing"}

        prompt = f"""
أنت مراجع بصري صارم لوثائقي تحقيق جنائي.
افتح الصورة فعلياً هنا:
{eval_img.resolve()}

السرد:
{narration}

إذا كانت Contact Sheet فهي ثلاثة إطارات تقريباً من 20% و50% و80% من الفيديو.
لا تعتمد على اسم الملف أو search query. افحص ما يظهر فعلياً.
ACCEPT فقط إذا كان هناك تطابق بصري واضح ومفيد مع السرد.
REJECT إذا كانت اللقطة عشوائية، جميلة لكن معناها خاطئ، مضللة، رديئة، أو غير قابلة للتبرير.
الأولوية: التطابق مع السرد، ثم الملاءمة الوثائقية، ثم الجودة.

اختر montage واحداً: ZOOM_IN أو PAN_RIGHT أو BW أو NORMAL.
أخرج JSON فقط:
{{"decision":"ACCEPT","montage":"NORMAL","reason":"..."}}
"""
        try:
            result = subprocess.run([
                "agy", "--model", "gemini-3.6-flash-high", "--dangerously-skip-permissions", "-p", prompt
            ], capture_output=True, text=True, check=True, timeout=180)
            data = parse_json_object(result.stdout)
            if not data:
                return {"valid": False, "montage": "NORMAL", "reason": "JSON غير صالح."}
            decision = str(data.get("decision", "REJECT")).upper().strip()
            montage = str(data.get("montage", "NORMAL")).upper().strip()
            if montage not in {"ZOOM_IN", "PAN_RIGHT", "BW", "NORMAL"}:
                montage = "NORMAL"
            if decision == "ACCEPT":
                return {"valid": True, "montage": montage, "reason": str(data.get("reason", ""))}
            return {"valid": False, "montage": montage, "reason": str(data.get("reason", ""))}
        except Exception as e:
            return {"valid": False, "montage": "NORMAL", "reason": str(e)}
        finally:
            safe_unlink(eval_img)

    def final_video_review(self, video_path: Path):
        log.info("🎞️ بدء المراجعة النهائية للفيديو الكامل...")
        if not valid_file(video_path):
            return {"decision": "REJECT", "reason": "الملف النهائي غير صالح أو فارغ.", "issues": [], "fixes": []}
        prompt = f"""
أنت المخرج النهائي والمراجع التقني لوثائقي تحقيق.
الفيديو الحقيقي موجود هنا:
{video_path.resolve()}

افحص الفيديو الفعلي، وليس manifest أو logs فقط.
تحقق من: تطابق اللقطات مع السرد، اللقطات العشوائية والمكررة، الجودة، الإطارات السوداء، القصات،
الانتقالات، مدة المشاهد، تزامن الصوت، الفجوات ومستوى الصوت، الترجمة وتوقيتها وقصها، placeholder،
المواد غير المرتبطة، أخطاء الرندر، ترتيب الأحداث، وأسباب pipeline الجذرية.

أخرج JSON فقط:
{{
  "decision":"ACCEPT",
  "reason":"...",
  "issues":[{{"time":"00:00-00:20","type":"VISUAL|AUDIO|SUBTITLE|EDITING|CONTENT|PIPELINE","problem":"...","cause":"...","fix":"..."}}],
  "fixes":["..."]
}}
"""
        try:
            result = subprocess.run([
                "agy", "--model", "gemini-3.1-pro-high", "--dangerously-skip-permissions",
                "--print-timeout", "20m", "-p", prompt
            ], capture_output=True, text=True, check=True, timeout=1200)
            review = parse_json_object(result.stdout)
            if not review:
                return {"decision": "REJECT", "reason": "المراجع النهائي لم يرجع JSON.", "issues": [], "fixes": []}
            review["decision"] = "ACCEPT" if str(review.get("decision", "REJECT")).upper() == "ACCEPT" else "REJECT"
            review.setdefault("issues", [])
            review.setdefault("fixes", [])
            return review
        except Exception as e:
            return {"decision": "REJECT", "reason": str(e), "issues": [], "fixes": []}

    def apply_final_repairs(self, review: Dict):
        log.warning("🛠️ Gemini 3.1 Pro سيحاول إصلاح السبب الجذري...")
        backup = CURRENT_PIPELINE.with_suffix(CURRENT_PIPELINE.suffix + ".bak")
        try:
            shutil.copy2(CURRENT_PIPELINE, backup)
        except Exception as e:
            log.warning(f"⚠️ تعذر إنشاء backup: {e}")

        prompt = f"""
أنت مهندس البرمجيات والمخرج التقني المسؤول عن إصلاح خط إنتاج وثائقي.
افتح الملف فعلياً: {CURRENT_PIPELINE}

المراجعة النهائية:
{json.dumps(review, ensure_ascii=False, indent=2)}

أصلح السبب الجذري داخل الملف نفسه، ثم شغّل:
python3 -m py_compile "{CURRENT_PIPELINE}"

قيود إلزامية:
- لا fallback graphic ولا placeholder ولا CLASSIFIED EVIDENCE.
- كل مرشح حقيقي يمر عبر Gemini 3.6 Flash High.
- Groq فقط لـ Whisper word timestamps.
- لا تغيّر نموذج TTS ولا Charon ولا دوران مفاتيح TTS.
- لا تغيّر إطلاقاً فترة التبريد بعد نجاح TTS: time.sleep(30).
- لا تحذف المراجعة النهائية للفيديو.
- لا تكسر Drive أو YouTube أو FFmpeg.
- لا تحذف النسخ النهائية السابقة من output_build.
- النسخة REJECTED يجب أن تُرفع قبل الإصلاح.
- حافظ على versioning.
- Pexels/Pixabay: 3 مرشحين لكل مصدر بالتناوب، مع استمرار الدورات.

أصلح الملفات مباشرة ولا تكتفِ بتقرير.
"""
        try:
            result = subprocess.run([
                "agy", "--model", "gemini-3.1-pro-high", "--dangerously-skip-permissions",
                "--print-timeout", "20m", "-p", prompt
            ], capture_output=True, text=True, timeout=1200)
            if result.returncode != 0:
                log.error(f"❌ فشل الإصلاح: {result.stderr[-1500:]}")
                return False
            subprocess.run([sys.executable, "-m", "py_compile", str(CURRENT_PIPELINE)], check=True, timeout=60)
            log.info("✅ فحص Python syntax ناجح بعد الإصلاح.")
            return True
        except Exception as e:
            log.error(f"❌ الكود المعدل غير صالح أو فشل الإصلاح: {e}")
            return False

    def generate_voice(self, text: str, out_wav: Path):
        prompt = "[INSTRUCTION: Documentary narrator. Deep, chilling voice. Read normally.]\n\n" + text
        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
                )
            ),
        )
        for round_num in range(3):
            for i, key in enumerate(CONFIG.gemini_keys):
                try:
                    temp_client = genai.Client(api_key=key)
                    res = temp_client.models.generate_content(
                        model="gemini-3.8-flash-tts", contents=prompt, config=cfg
                    )
                    raw = res.candidates[0].content.parts[0].inline_data.data
                    out_wav.write_bytes(base64.b64decode(raw) if isinstance(raw, str) else raw)
                    log.info("⏳ تم توليد الصوت بنجاح. بدء التبريد (30 ثانية)...")
                    # لا نلمس فترة التبريد.
                    time.sleep(30)
                    return True
                except Exception as e:
                    log.warning(f"⚠️ فشل المفتاح ({i + 1}) لتوليد الصوت: {e}")
                    time.sleep(2)
            time.sleep(10)
        log.error("❌ استنفدت جميع المفاتيح لتوليد الصوت!")
        return False


# ==================================================================================================
# 5. Media fetcher
# ==================================================================================================

class MediaFetcher:
    def __init__(self):
        self.h = {"User-Agent": "HybridPipeline/23.0"}

    def fetch_video(self, source, query, out, index=0):
        safe_unlink(out)
        try:
            if source == "PEXELS":
                if not CONFIG.pexels:
                    return False
                r = requests.get(
                    "https://api.pexels.com/videos/search",
                    params={"query": query, "orientation": "landscape", "per_page": min(80, max(10, index + 5))},
                    headers={"Authorization": CONFIG.pexels}, timeout=20,
                )
                if r.status_code != 200:
                    return False
                videos = r.json().get("videos", [])
                if len(videos) <= index:
                    return False
                files = sorted(videos[index].get("video_files", []), key=lambda x: x.get("width", 0), reverse=True)
                if not files or not files[0].get("link"):
                    return False
                response = requests.get(files[0]["link"], timeout=90)
                if response.status_code != 200 or len(response.content) < 50000:
                    return False
                out.write_bytes(response.content)
                return valid_file(out)

            if source == "PIXABAY":
                if not CONFIG.pixabay:
                    return False
                r = requests.get(
                    "https://pixabay.com/api/videos/",
                    params={"key": CONFIG.pixabay, "q": query, "per_page": min(200, max(20, index + 10))},
                    timeout=20,
                )
                if r.status_code != 200:
                    return False
                hits = r.json().get("hits", [])
                if len(hits) <= index:
                    return False
                vids = hits[index].get("videos", {})
                url = next((v.get("url") for v in (vids.get("large"), vids.get("medium"), vids.get("small")) if isinstance(v, dict) and v.get("url")), None)
                if not url:
                    return False
                response = requests.get(url, timeout=90)
                if response.status_code != 200 or len(response.content) < 50000:
                    return False
                out.write_bytes(response.content)
                return valid_file(out)
        except Exception as e:
            log.warning(f"⚠️ فشل جلب {source}: {e}")
        safe_unlink(out)
        return False

    def fetch_image(self, source, query, out, index=0):
        safe_unlink(out)
        try:
            if source == "MAPBOX":
                if not CONFIG.mapbox:
                    return False
                response = requests.get(
                    f"https://api.mapbox.com/styles/v1/mapbox/dark-v11/static/{query},14,0,0/1920x1080",
                    params={"access_token": CONFIG.mapbox}, timeout=30,
                )
                if response.status_code == 200 and response.content:
                    out.write_bytes(response.content)
                    return valid_file(out, 5000)
                return False

            if source == "WIKIPEDIA":
                r = requests.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={"action": "query", "generator": "search", "gsrsearch": query,
                            "gsrlimit": min(50, max(10, index + 5)), "prop": "pageimages",
                            "pithumbsize": 1920, "format": "json"},
                    headers=self.h, timeout=20,
                )
                if r.status_code != 200:
                    return False
                pages = list(r.json().get("query", {}).get("pages", {}).values())
                pages = [p for p in pages if p.get("thumbnail", {}).get("source")]
                if len(pages) <= index:
                    return False
                response = requests.get(pages[index]["thumbnail"]["source"], headers=self.h, timeout=30)
                if response.status_code != 200 or len(response.content) < 5000:
                    return False
                out.write_bytes(response.content)
                return valid_file(out, 5000)
        except Exception as e:
            log.warning(f"⚠️ فشل جلب الصورة {source}: {e}")
        safe_unlink(out)
        return False

    def get_freesound_foley(self, query, out):
        if not CONFIG.freesound or not query or query.lower() == "none":
            return False
        try:
            r = requests.get(
                "https://freesound.org/apiv2/search/text/",
                params={"query": query, "token": CONFIG.freesound, "fields": "previews", "page_size": 5},
                timeout=20,
            )
            if r.status_code != 200:
                return False
            results = r.json().get("results", [])
            if not results:
                return False
            url = results[0].get("previews", {}).get("preview-hq-mp3")
            if not url:
                return False
            response = requests.get(url, timeout=30)
            if response.status_code != 200:
                return False
            out.write_bytes(response.content)
            return valid_file(out, 1000)
        except Exception as e:
            log.warning(f"⚠️ خطأ Freesound: {e}")
            return False


# ==================================================================================================
# 6. Find accepted real media
# ==================================================================================================

def find_accepted_media(director, fetcher, source_type, query, narration, video_path, image_path):
    if source_type in {"PEXELS", "PIXABAY"}:
        MAX_CYCLES = 4
        for cycle in range(MAX_CYCLES):
            for source in ("PEXELS", "PIXABAY"):
                if runtime_expired():
                    return {"accepted": False}
                if source == "PEXELS" and not CONFIG.pexels:
                    continue
                if source == "PIXABAY" and not CONFIG.pixabay:
                    continue
                for local_attempt in range(3):
                    global_index = cycle * 3 + local_attempt
                    safe_unlink(video_path)
                    if not fetcher.fetch_video(source, query, video_path, global_index):
                        continue
                    evaluation = director.evaluate_scene_with_scout(video_path, narration)
                    if evaluation.get("valid"):
                        return {
                            "accepted": True, "source": source, "path": video_path,
                            "is_video": True, "montage": evaluation.get("montage", "NORMAL"),
                            "reason": evaluation.get("reason", ""), "candidate": global_index,
                        }
                    safe_unlink(video_path)
        return {"accepted": False}

    source = source_type if source_type in {"MAPBOX", "WIKIPEDIA"} else "WIKIPEDIA"
    for index in range(12):
        if runtime_expired():
            return {"accepted": False}
        safe_unlink(image_path)
        if not fetcher.fetch_image(source, query, image_path, index):
            continue
        evaluation = director.evaluate_scene_with_scout(image_path, narration)
        if evaluation.get("valid"):
            return {
                "accepted": True, "source": source, "path": image_path,
                "is_video": False, "montage": evaluation.get("montage", "NORMAL"),
                "reason": evaluation.get("reason", ""), "candidate": index,
            }
        safe_unlink(image_path)
    return {"accepted": False}


# ==================================================================================================
# 7. Whisper / subtitles
# ==================================================================================================

def groq_transcribe(audio_path):
    if not CONFIG.groq:
        return []
    try:
        with open(audio_path, "rb") as f:
            res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {CONFIG.groq}"},
                files={"file": (audio_path.name, f, "audio/mpeg")},
                data={"model": "whisper-large-v3", "response_format": "verbose_json", "timestamp_granularities[]": "word"},
                timeout=60,
            )
        if res.status_code != 200:
            return []
        return res.json().get("words", [])
    except Exception as e:
        log.warning(f"⚠️ خطأ Groq Whisper: {e}")
        return []


def generate_ass(words, fallback, dur, out, badge):
    def ft(s):
        return f"{int(s // 3600)}:{int((s % 3600) // 60):02d}:{s % 60:05.2f}"

    evs = []
    if words:
        ch = []
        st = 0.0
        for i, w in enumerate(words):
            if not ch:
                st = float(w.get("start", 0))
            ch.append(w.get("word", ""))
            if len(ch) == 5 or i == len(words) - 1:
                end_time = float(w.get("end", st + 1))
                evs.append(
                    "Dialogue: 1,"
                    f"{ft(st)},"
                    f"{ft(end_time)},"
                    "Sub,,0,0,0,,"
                    + get_display(reshape(" ".join(ch)))
                )
                ch = []
    else:
        wl = fallback.split()
        groups = max(1, (len(wl) + 4) // 5)
        cd = dur / groups
        for i in range(0, len(wl), 5):
            start = (i // 5) * cd
            end = min(dur, start + cd)
            # IMPORTANT: closes evs.append correctly.
            evs.append(
                "Dialogue: 1,"
                f"{ft(start)},"
                f"{ft(end)},"
                "Sub,,0,0,0,,"
                + get_display(reshape(" ".join(wl[i:i + 5])))
            )

    bdg = get_display(reshape(badge))
    ass = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "[V4+ Styles]\n"
        "Style: Sub,Noto Sans Arabic,110,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,100,100,0,1,4,4,2,80,80,100\n"
        "Style: Bdg,Noto Sans Arabic,35,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,-1,100,100,0,1,2,2,7,60,60,50\n"
        "[Events]\n"
        f"Dialogue: 0,0:00:00.00,{ft(dur)},Bdg,,0,0,0,,{bdg}\n"
        + "\n".join(evs)
    )
    out.write_text(ass, encoding="utf-8")


# ==================================================================================================
# 8. Audio / render
# ==================================================================================================

def process_audio(voice, foley, has_foley, out):
    safe_unlink(out)
    if has_foley:
        fc = (
            "[0:a]silenceremove=stop_periods=-1:stop_duration=0.8:stop_threshold=-45dB,loudnorm=I=-16[v];"
            "[1:a]volume=0.04[bg];[v][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        )
        cmd = ["ffmpeg", "-y", "-i", str(voice), "-stream_loop", "-1", "-i", str(foley),
               "-filter_complex", fc, "-map", "[aout]", "-ar", "48000", "-c:a", "aac", str(out)]
    else:
        fc = "[0:a]silenceremove=stop_periods=-1:stop_duration=0.8:stop_threshold=-45dB,loudnorm=I=-16[aout]"
        cmd = ["ffmpeg", "-y", "-i", str(voice), "-filter_complex", fc, "-map", "[aout]", "-ar", "48000", "-c:a", "aac", str(out)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=180, check=True)
    return float(subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(out)
    ]).decode().strip())


def render_scene(media, is_vid, ass, aud, out, dur, montage_hint):
    safe_unlink(out)
    color_fx = ",hue=s=0" if "BW" in montage_hint else ",eq=contrast=1.12:saturation=0.85"
    if is_vid:
        fc = (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080"
            f"{color_fx},vignette=PI/3.6,subtitles='{ass}',fps=24[v]"
        )
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(media), "-i", str(aud),
               "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-c:v", "libx264",
               "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)]
    else:
        if montage_hint == "PAN_RIGHT":
            motion = "z=1.1:x='min(iw-iw/zoom,x+1)':y='ih/2-(ih/zoom/2)'"
        elif montage_hint == "NORMAL":
            motion = "z=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        else:
            motion = "z='min(1.15,1.05+0.0003*on)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        fc = (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,"
            f"zoompan={motion}:d={int(max(1,dur)*24)}:s=1920x1080:fps=24"
            f"{color_fx},vignette=PI/3.6,subtitles='{ass}'[v]"
        )
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(media), "-i", str(aud),
               "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-c:v", "libx264",
               "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)]
    try:
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300, check=True)
    except Exception as e:
        log.error(f"❌ فشل رندر المشهد: {e}")


# ==================================================================================================
# 9. Google OAuth / uploads
# ==================================================================================================

def create_google_credentials(refresh_token):
    if not (CONFIG.google_client_id and CONFIG.google_client_secret and refresh_token):
        return None
    try:
        return Credentials(
            None, refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CONFIG.google_client_id, client_secret=CONFIG.google_client_secret,
        )
    except Exception as e:
        log.error(f"❌ تعذر إنشاء Google Credentials: {e}")
        return None


def upload_drive(vid):
    if not CONFIG.drive_token:
        return {"uploaded": False, "id": None, "error": "DRIVE_REFRESH_TOKEN missing"}
    if not (CONFIG.google_client_id and CONFIG.google_client_secret):
        return {"uploaded": False, "id": None, "error": "Google OAuth credentials missing"}
    try:
        credentials = create_google_credentials(CONFIG.drive_token)
        if not credentials:
            return {"uploaded": False, "id": None, "error": "credentials creation failed"}
        dr = build("drive", "v3", credentials=credentials)
        res = dr.files().list(
            q="name='Broadcast_Vault' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id,name)", pageSize=10,
        ).execute()
        if res.get("files"):
            fid = res["files"][0]["id"]
        else:
            fid = dr.files().create(
                body={"name": "Broadcast_Vault", "mimeType": "application/vnd.google-apps.folder"},
                fields="id",
            ).execute()["id"]
        media = MediaFileUpload(str(vid), mimetype="video/mp4", resumable=True, chunksize=5 * 1024 * 1024)
        req = dr.files().create(body={"name": vid.name, "parents": [fid]}, media_body=media, fields="id,name,webViewLink")
        response = None
        while response is None:
            status, response = req.next_chunk()
            if status:
                log.info(f"☁️ Drive: {int(status.progress()*100)}%")
        return {"uploaded": True, "id": response.get("id"), "link": response.get("webViewLink")}
    except Exception as e:
        log.error(f"❌ فشل Drive: {e}")
        return {"uploaded": False, "id": None, "error": str(e)}


def upload_youtube(vid, round_number, status, review):
    if not CONFIG.yt_refresh:
        return {"uploaded": False, "id": None, "error": "YOUTUBE_REFRESH_TOKEN missing"}
    if not (CONFIG.google_client_id and CONFIG.google_client_secret):
        return {"uploaded": False, "id": None, "error": "Google OAuth credentials missing"}
    try:
        credentials = create_google_credentials(CONFIG.yt_refresh)
        if not credentials:
            return {"uploaded": False, "id": None, "error": "credentials creation failed"}
        youtube = build("youtube", "v3", credentials=credentials)
        title = re.sub(r"\s+", " ", CONFIG.topic).strip() + f" | V{round_number:02d} | {status}"
        title = title[:100]
        reason = str(review.get("reason", ""))
        description = (
            f"وثائقي تحقيقي آلي.\n\nالموضوع: {CONFIG.topic}\n"
            f"الإصدار: V{round_number:02d}\nالحالة: {status}\n\n"
            f"نتيجة المراجعة النهائية:\n{reason}\n\n"
            "هذه النسخة محفوظة كإصدار مستقل للمقارنة."
        )
        body = {
            "snippet": {"title": title, "description": description, "categoryId": "22"},
            "status": {"privacyStatus": CONFIG.youtube_privacy, "selfDeclaredMadeForKids": False},
        }
        media = MediaFileUpload(str(vid), mimetype="video/mp4", resumable=True, chunksize=8 * 1024 * 1024)
        request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
        response = None
        while response is None:
            upload_status, response = request.next_chunk()
            if upload_status:
                log.info(f"▶️ YouTube: {int(upload_status.progress()*100)}%")
        video_id = response.get("id")
        return {
            "uploaded": True, "id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else None,
            "privacy": CONFIG.youtube_privacy,
        }
    except Exception as e:
        log.error(f"❌ فشل YouTube: {e}")
        return {"uploaded": False, "id": None, "error": str(e)}


def save_version_review(review, round_number, version_path, drive_result, youtube_result):
    enriched = dict(review)
    enriched.update({
        "version": round_number,
        "version_file": version_path.name,
        "drive": drive_result,
        "youtube": youtube_result,
    })
    review_path = CONFIG.paths.base / f"final_review_V{round_number:02d}.json"
    write_json(review_path, enriched)
    write_json(CONFIG.paths.final_review, enriched)
    return review_path


def update_versions_manifest(round_number, status, version_path, drive_result, youtube_result):
    path = CONFIG.paths.base / "versions_manifest.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "topic": CONFIG.topic, "created_at": datetime.now().isoformat(), "versions": []
        }
        data.setdefault("versions", [])
        data["versions"] = [v for v in data["versions"] if v.get("version") != round_number]
        data["versions"].append({
            "version": round_number, "status": status, "file": version_path.name,
            "drive": drive_result, "youtube": youtube_result, "timestamp": datetime.now().isoformat(),
        })
        data["versions"].sort(key=lambda x: x.get("version", 0))
        write_json(path, data)
    except Exception as e:
        log.warning(f"⚠️ تعذر تحديث versions_manifest.json: {e}")


def archive_reviewed_video(source_video, round_number, status):
    destination = CONFIG.paths.base / version_filename(round_number, status)
    if destination.exists():
        destination = CONFIG.paths.base / (
            f"{safe_topic_slug(CONFIG.topic)}_V{round_number:02d}_{status}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        )
    source_video.replace(destination)
    return destination


def publish_version(final_vid, round_number, status, review):
    version_path = archive_reviewed_video(final_vid, round_number, status)
    log.info(f"💾 النسخة المحلية: {version_path}")
    drive_result = upload_drive(version_path)
    youtube_result = upload_youtube(version_path, round_number, status, review)
    review_path = save_version_review(review, round_number, version_path, drive_result, youtube_result)
    update_versions_manifest(round_number, status, version_path, drive_result, youtube_result)
    log.info(f"📋 تم حفظ مراجعة النسخة: {review_path.name}")
    return version_path


# ==================================================================================================
# 10. Cache cleanup / restart / concat
# ==================================================================================================

def clear_render_cache_for_rebuild():
    log.info("♻️ تنظيف ملفات رندر المشاهد فقط...")
    patterns = ["s_*.mp4", "s_*_source.mp4", "s_*_source.jpg", "s_*_accepted.json", "s_*_vision_review.jpg", "s_*_frame_*.jpg"]
    for pattern in patterns:
        for path in CONFIG.paths.cache.glob(pattern):
            safe_unlink(path)
    # TTS/audio cache is intentionally preserved; narration hashes decide whether it is reusable.
    log.info("✅ تم تنظيف Cache الرندر فقط. الإصدارات السابقة والصوت محفوظة.")


def restart_pipeline(review_round):
    env = os.environ.copy()
    env["MASTER_START_TS"] = str(MASTER_START_TS)
    env["FINAL_REVIEW_ROUND"] = str(review_round)
    os.execvpe(sys.executable, [sys.executable, str(CURRENT_PIPELINE)], env)


def concat_clips(clips, round_number):
    txt_list = CONFIG.paths.base / f"list_{round_number}.txt"
    lines = []
    for clip in clips:
        if valid_file(clip):
            p = clip.resolve().as_posix().replace("'", "'\\''")
            lines.append(f"file '{p}'")
    txt_list.write_text("\n".join(lines), encoding="utf-8")
    final_vid = CONFIG.paths.base / f"MasterDoc_review_{round_number}.mp4"
    safe_unlink(final_vid)
    if not lines:
        return final_vid
    try:
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt_list),
            "-c", "copy", str(final_vid)
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900, check=True)
    except Exception as e:
        log.error(f"❌ فشل دمج الفيديو: {e}")
    return final_vid


# ==================================================================================================
# 11. Main
# ==================================================================================================

def main():
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    log.info("▶ UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE V23 FIXED")
    log.info(f"🎯 القضية: {CONFIG.topic}")
    log.info(f"🔄 جولة المراجعة الحالية: {FINAL_REVIEW_ROUND}")
    log.info(f"▶️ YouTube privacy: {CONFIG.youtube_privacy}")
    log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    director = Hybrid_Director()
    fetcher = MediaFetcher()
    script = director.plan_documentary()
    clips = []

    for i, s in enumerate(script):
        if runtime_expired():
            log.warning("⏳ تم بلوغ حد الجلسة.")
            break

        typ = str(s.get("media_type", "WIKIPEDIA")).upper()
        q = str(s.get("search_query", ""))
        foley = str(s.get("foley_type", "none"))
        txt = str(s.get("narration", ""))
        narration_hash = sha256_text(txt)

        c_mp4 = CONFIG.paths.cache / f"s_{i:03d}.mp4"
        c_source_mp4 = CONFIG.paths.cache / f"s_{i:03d}_source.mp4"
        c_source_jpg = CONFIG.paths.cache / f"s_{i:03d}_source.jpg"
        c_wav = CONFIG.paths.cache / f"s_{i:03d}.wav"
        c_foley = CONFIG.paths.cache / f"s_{i:03d}_foley.mp3"
        c_mp3 = CONFIG.paths.cache / f"s_{i:03d}.mp3"
        c_ass = CONFIG.paths.cache / f"s_{i:03d}.ass"
        accepted_marker = CONFIG.paths.cache / f"s_{i:03d}_accepted.json"
        voice_marker = CONFIG.paths.cache / f"s_{i:03d}_voice.json"

        if valid_file(c_mp4) and accepted_marker.exists():
            try:
                marker = json.loads(accepted_marker.read_text(encoding="utf-8"))
                if marker.get("accepted") and marker.get("narration_hash") == narration_hash:
                    clips.append(c_mp4)
                    log.info(f"♻️ المشهد {i+1} موجود بنفس narration hash — تخطي.")
                    continue
            except Exception:
                pass
        safe_unlink(c_mp4)

        log.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log.info(f"🎬 المشهد {i+1}/{len(script)} | Query: {q}")

        voice_cache_valid = False
        if valid_file(c_wav, 1000) and voice_marker.exists():
            try:
                vm = json.loads(voice_marker.read_text(encoding="utf-8"))
                voice_cache_valid = (
                    vm.get("narration_hash") == narration_hash
                    and vm.get("model") == "gemini-3.8-flash-tts"
                    and vm.get("voice") == "Charon"
                )
            except Exception:
                pass

        if not voice_cache_valid:
            safe_unlink(c_wav)
            if not director.generate_voice(txt, c_wav):
                log.error(f"❌ لم يتم إنتاج الصوت للمشهد {i+1}.")
                continue
            if valid_file(c_wav, 1000):
                write_json(voice_marker, {
                    "narration_hash": narration_hash,
                    "model": "gemini-3.8-flash-tts",
                    "voice": "Charon",
                    "created_at": datetime.now().isoformat(),
                })

        if not valid_file(c_wav, 1000):
            continue

        has_foley = valid_file(c_foley, 1000)
        if not has_foley:
            has_foley = fetcher.get_freesound_foley(foley, c_foley)

        try:
            dur = process_audio(c_wav, c_foley, has_foley, c_mp3)
        except Exception as e:
            log.error(f"❌ فشل معالجة الصوت: {e}")
            continue

        words = groq_transcribe(c_mp3)

        accepted_media = find_accepted_media(
            director, fetcher, typ, q, txt, c_source_mp4, c_source_jpg
        )

        if not accepted_media.get("accepted"):
            log.error(f"🚫 تجاوز المشهد {i+1}: لا توجد وسائط حقيقية مناسبة.")
            safe_unlink(c_source_mp4)
            safe_unlink(c_source_jpg)
            continue

        c_media = accepted_media["path"]
        is_vid = accepted_media["is_video"]
        accepted_source = accepted_media["source"]
        montage_style = accepted_media.get("montage", "NORMAL")
        candidate = accepted_media.get("candidate", 0)

        badges = {
            "PEXELS": "لقطات سينمائية",
            "PIXABAY": "أرشيف عام",
            "MAPBOX": "إحداثيات جغرافية",
            "WIKIPEDIA": "سجلات أرشيفية",
        }
        generate_ass(words, txt, dur, c_ass, f"● {badges.get(accepted_source, 'أرشيف')} | {q}")

        render_scene(c_media, is_vid, c_ass, c_mp3, c_mp4, dur, montage_style)
        if not valid_file(c_mp4):
            safe_unlink(c_mp4)
            continue

        write_json(accepted_marker, {
            "accepted": True,
            "scene": i + 1,
            "source": accepted_source,
            "candidate": candidate,
            "montage": montage_style,
            "query": q,
            "narration_hash": narration_hash,
            "accepted_at": datetime.now().isoformat(),
        })
        clips.append(c_mp4)
        log.info(f"✅ تم رندر المشهد {i+1} وقبوله.")

    if not clips:
        append_memory("فشل الإنتاج لأن النظام لم يجد وسائط حقيقية مناسبة.")
        return

    review_round = FINAL_REVIEW_ROUND + 1
    final_vid = concat_clips(clips, review_round)
    if not valid_file(final_vid):
        log.error("❌ لم يتم إنشاء MP4 نهائي صالح.")
        return

    review = director.final_video_review(final_vid)
    decision = review.get("decision", "REJECT")

    if decision == "ACCEPT":
        version_path = publish_version(final_vid, review_round, "ACCEPTED", review)
        append_memory(f"تم إنتاج النسخة V{review_round:02d} واجتازت المراجعة. الملف: {version_path.name}")
        log.info("🏆 اكتملت الجلسة بنجاح.")
        return

    # REJECTED versions are uploaded BEFORE repair and are NEVER deleted.
    version_path = publish_version(final_vid, review_round, "REJECTED", review)
    log.warning(f"📦 تم الاحتفاظ بالنسخة المرفوضة: {version_path.name}")

    if review_round >= MAX_FINAL_REPAIRS:
        append_memory(f"انتهت جلسات الإصلاح عند الجولة {review_round}. النسخة محفوظة: {version_path.name}")
        return

    repaired = director.apply_final_repairs(review)
    if not repaired:
        append_memory(f"تم رفض V{review_round:02d} وفشل الإصلاح الذاتي. النسخة محفوظة.")
        return

    clear_render_cache_for_rebuild()
    append_memory(f"تم رفض V{review_round:02d} وتعديل pipeline. النسخة السابقة محفوظة للمقارنة.")
    restart_pipeline(review_round)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.warning("⛔ تم إيقاف الإنتاج يدوياً.")
    except Exception as e:
        log.critical(f"💥 خطأ غير متوقع: {e}", exc_info=True)
        append_memory(f"حدث خطأ غير متوقع: {e}")
