#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
====================================================================================================
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
HYBRID V22.33 - Strict Scene Duration + Render Cache Invalidation + Montage Validation
====================================================================================================

V22.33 إصلاحات المونتاج:

1. كل مشهد يُجبر على مدة الصوت الفعلية.
2. الصور لا تستخدم zoompan بطريقة تجعل عدد الإطارات يتضخم مع الإدخال المتكرر.
3. الفيديوهات تُقص/تُمدد بصرياً فقط حتى مدة المشهد.
4. إضافة FPS ثابت 25 للمشاهد.
5. إضافة ffprobe للتحقق من مدة كل MP4 بعد الرندر.
6. إذا كانت مدة المشهد الناتجة مختلفة بشكل غير مقبول عن مدة الصوت، تتم إعادة المحاولة.
7. الكاش القديم V22.32 لا يُستخدم تلقائياً.
8. كل مشهد ناجح يحصل على Render Stamp خاص بـ V22.33.
9. قبل الدمج النهائي يتم فحص جميع المشاهد.
10. يتم حساب مجموع مدد المشاهد قبل الدمج وبعده.
11. إذا ظهرت مدة نهائية غير منطقية، لا يتم رفع الفيلم إلى Drive/YouTube.
12. تم الإبقاء على نظام TTS وAntigravity وMedia Scout كما هو.
====================================================================================================
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
from pathlib import Path
from typing import List, Dict
from datetime import datetime

import requests
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

import google.antigravity as ag
from google.antigravity import Agent, LocalAgentConfig


# ================================================================================================
# VERSION / RENDER CONSTANTS
# ================================================================================================

ENGINE_VERSION = "V22.33"
RENDER_VERSION = "V22.33"

TARGET_WIDTH = 1920
TARGET_HEIGHT = 1080
TARGET_FPS = 25

# السماح بفارق بسيط بسبب دقة حاوية MP4.
SCENE_DURATION_TOLERANCE = 0.35

# إذا خرج المشهد أطول من الصوت بهذا الحد، يعتبر غير صالح.
MAX_SCENE_OVERRUN = 0.75

# حد أدنى لحجم ملف الفيديو.
MIN_VIDEO_SIZE = 50000


# ================================================================================================
# LOGGER
# ================================================================================================

class ProTelemetryFormatter(logging.Formatter):
    COLORS = {
        "INFO": "\x1b[38;5;39m",
        "WARNING": "\x1b[38;5;214m",
        "ERROR": "\x1b[38;5;196m",
    }
    RESET = "\x1b[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        fmt = f"{color}%(asctime)s | [%(levelname)s] | %(message)s{self.RESET}"
        return logging.Formatter(
            fmt,
            datefmt="%H:%M:%S"
        ).format(record)


def setup_logger():
    logger = logging.getLogger("HybridMaster")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(ProTelemetryFormatter())
        logger.addHandler(ch)

        fh = logging.FileHandler(
            "production_logs.txt",
            encoding="utf-8"
        )
        logger.addHandler(fh)

    logger.propagate = False
    return logger


log = setup_logger()

MEMORY_FILE = Path("director_memory.md")


def append_memory(summary):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(
        MEMORY_FILE,
        "a",
        encoding="utf-8"
    ) as f:
        f.write(
            f"\n\n### [{now}]\n{summary}"
        )


# ================================================================================================
# GENERAL HELPERS
# ================================================================================================

def load_ag_media(file_path):
    ext = file_path.suffix.lower()
    path_str = str(file_path.resolve())

    if ext in [".mp4", ".mov", ".webm", ".avi"]:
        if hasattr(ag, "Video"):
            return ag.Video.from_file(path_str)

        if (
            hasattr(ag, "media")
            and hasattr(ag.media, "Video")
        ):
            return ag.media.Video.from_file(path_str)

        if hasattr(ag, "from_file"):
            return ag.from_file(path_str)

    else:
        if hasattr(ag, "Image"):
            return ag.Image.from_file(path_str)

        if (
            hasattr(ag, "media")
            and hasattr(ag.media, "Image")
        ):
            return ag.media.Image.from_file(path_str)

        if hasattr(ag, "from_file"):
            return ag.from_file(path_str)

    raise RuntimeError(
        "لم يتم العثور على فئة الوسائط في حزمة google.antigravity"
    )


def enforce_english_query(query, max_chars=90):
    query = str(query or "")

    safe_q = re.sub(
        r"[\u0600-\u06FF]",
        "",
        query
    )

    safe_q = re.sub(
        r"[^A-Za-z0-9,._' -]",
        " ",
        safe_q
    )

    safe_q = re.sub(
        r"\s+",
        " ",
        safe_q
    ).strip()

    words = []
    seen = set()

    for word in safe_q.split():
        key = word.lower()

        if key not in seen:
            seen.add(key)
            words.append(word)

    safe_q = " ".join(words)

    if not safe_q or len(safe_q) < 2:
        safe_q = "mystery evidence"

    if len(safe_q) > max_chars:
        safe_q = (
            safe_q[:max_chars]
            .rsplit(" ", 1)[0]
            .strip()
        )

    return safe_q


def safe_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


# ================================================================================================
# FFPROBE HELPERS
# ================================================================================================

def probe_duration(path):
    """
    الحصول على مدة ملف صوت/فيديو بدقة من ffprobe.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return None

        value = result.stdout.strip()

        if not value:
            return None

        duration = float(value)

        if duration <= 0:
            return None

        return duration

    except Exception as e:
        log.warning(
            f"⚠️ ffprobe فشل في قراءة مدة {path}: "
            f"{str(e)[:150]}"
        )
        return None


def probe_stream_info(path):
    """
    التحقق من وجود Video + Audio في الملف.
    """
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type",
                "-of",
                "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            return False, False

        streams = {
            x.strip().lower()
            for x in result.stdout.splitlines()
            if x.strip()
        }

        return (
            "video" in streams,
            "audio" in streams,
        )

    except Exception:
        return False, False


def validate_scene_video(path, expected_duration):
    """
    فحص MP4 بعد الرندر.

    يعيد:
        valid, actual_duration, reason
    """

    if not path.exists():
        return False, 0.0, "الملف غير موجود"

    if path.stat().st_size < MIN_VIDEO_SIZE:
        return False, 0.0, "حجم الفيديو صغير جداً"

    actual = probe_duration(path)

    if actual is None:
        return False, 0.0, "تعذر قراءة مدة الفيديو"

    has_video, has_audio = probe_stream_info(path)

    if not has_video:
        return False, actual, "لا يوجد Video stream"

    if not has_audio:
        return False, actual, "لا يوجد Audio stream"

    expected = max(
        0.5,
        float(expected_duration)
    )

    difference = actual - expected

    log.info(
        f"📏 فحص مدة المشهد | "
        f"المتوقعة: {expected:.2f}s | "
        f"الفعلية: {actual:.2f}s | "
        f"الفرق: {difference:+.2f}s"
    )

    # السماح بفارق صغير فقط.
    if abs(difference) > SCENE_DURATION_TOLERANCE:
        if difference > MAX_SCENE_OVERRUN:
            return (
                False,
                actual,
                f"المشهد أطول من المطلوب بشكل واضح (+{difference:.2f}s)"
            )

        return (
            False,
            actual,
            f"مدة المشهد لا تطابق الصوت (+/-{difference:.2f}s)"
        )

    return True, actual, "OK"


def get_render_stamp_path(mp4_path):
    return Path(
        str(mp4_path) + ".render.json"
    )


def read_render_stamp(mp4_path):
    stamp = get_render_stamp_path(mp4_path)

    if not stamp.exists():
        return None

    try:
        return json.loads(
            stamp.read_text(
                encoding="utf-8"
            )
        )
    except Exception:
        return None


def write_render_stamp(mp4_path, duration):
    stamp = get_render_stamp_path(mp4_path)

    payload = {
        "render_version": RENDER_VERSION,
        "engine_version": ENGINE_VERSION,
        "duration": round(float(duration), 4),
        "created_at": datetime.now().isoformat(),
    }

    try:
        stamp.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception as e:
        log.warning(
            f"⚠️ تعذر كتابة Render Stamp: {e}"
        )


def invalidate_old_render_cache(mp4_path):
    """
    حذف MP4 القديم إذا لم يكن مولداً بواسطة V22.33.
    """
    if not mp4_path.exists():
        return False

    stamp = read_render_stamp(mp4_path)

    if not stamp:
        log.warning(
            f"♻️ الكاش القديم بلا Render Stamp: "
            f"{mp4_path.name} — سيتم إعادة بنائه."
        )

        try:
            mp4_path.unlink()
        except Exception:
            pass

        try:
            get_render_stamp_path(mp4_path).unlink()
        except Exception:
            pass

        return True

    if stamp.get("render_version") != RENDER_VERSION:
        log.warning(
            f"♻️ كاش {mp4_path.name} مولد بإصدار "
            f"{stamp.get('render_version')} — "
            f"سيتم إعادة بنائه بـ {RENDER_VERSION}."
        )

        try:
            mp4_path.unlink()
        except Exception:
            pass

        try:
            get_render_stamp_path(mp4_path).unlink()
        except Exception:
            pass

        return True

    return False


# ================================================================================================
# CONFIG
# ================================================================================================

class HybridConfig:
    topic = os.environ.get(
        "VIDEO_TOPIC",
        "لغز الجريمة الغامضة"
    )

    paths = type(
        "Paths",
        (),
        {
            "base": Path("./output_build"),
            "cache": Path("./output_build/cache"),
            "manifest": Path(
                "./output_build/master_manifest.json"
            ),
        },
    )()

    gemini_keys = [
        k.strip()
        for k in os.environ.get(
            "GEMINI_API_KEY",
            ""
        ).split(",")
        if k.strip()
    ]

    # Remove it from environment so google-antigravity SDK
    # doesn't route to AI Studio.
    os.environ.pop(
        "GEMINI_API_KEY",
        None
    )

    pexels = os.environ.get(
        "PEXELS_API_KEY",
        ""
    )

    pixabay = os.environ.get(
        "PIXABAY_API_KEY",
        ""
    )

    freesound = os.environ.get(
        "FREESOUND_API_KEY",
        ""
    )

    yt_id = os.environ.get(
        "GOOGLE_CLIENT_ID",
        ""
    )

    yt_secret = os.environ.get(
        "GOOGLE_CLIENT_SECRET",
        ""
    )

    drive_token = os.environ.get(
        "DRIVE_REFRESH_TOKEN",
        ""
    )

    yt_refresh = os.environ.get(
        "YOUTUBE_REFRESH_TOKEN",
        "")


CONFIG = HybridConfig()

CONFIG.paths.base.mkdir(
    parents=True,
    exist_ok=True
)

CONFIG.paths.cache.mkdir(
    parents=True,
    exist_ok=True
)


# ================================================================================================
# DIRECTOR
# ================================================================================================

class Hybrid_Director:

    def plan_documentary(self) -> List[Dict]:

        if CONFIG.paths.manifest.exists():
            try:
                data = json.loads(
                    CONFIG.paths.manifest.read_text(
                        encoding="utf-8"
                    )
                )

                if isinstance(data, list) and data:
                    log.info(
                        "📋 تم العثور على "
                        "master_manifest.json صالح."
                    )
                    return data

            except Exception as e:
                log.warning(
                    f"⚠️ تعذر قراءة الـ manifest القديم: {e}"
                )

        log.info(
            f"🧠 كتابة السيناريو عبر Antigravity CLI | "
            f"gemini-3.1-pro | القضية: {CONFIG.topic}"
        )

        prompt = f"""
أنت كبير المخرجين ومخطط أفلام وثائقية تحقيقية.

القضية:
"{CONFIG.topic}"

أنشئ سيناريو وثائقي متكامل من 40 إلى 50 مشهداً.
كل مشهد يحتوي على تعليق صوتي عربي واضح من 60 إلى 80 كلمة تقريباً.

لكل مشهد أخرج:
- scene_num
- media_type
- search_query
- foley_type
- narration

القيم المسموحة لـ media_type:
PEXELS
PIXABAY
WIKIPEDIA
ARCHIVE

قواعد صارمة:
1. search_query باللغة الإنجليزية فقط.
2. لا تضع حروفاً عربية داخل search_query.
3. اجعل كلمات البحث مرتبطة مباشرة بمحتوى المشهد.
4. narration باللغة العربية.
5. أخرج JSON Array فقط.
6. لا تضف Markdown أو ``` أو أي نص قبل أو بعد JSON.

مثال:
[
  {{
    "scene_num": 1,
    "media_type": "PEXELS",
    "search_query": "dark empty street at night",
    "foley_type": "rain",
    "narration": "في ليلة..."
  }}
]
""".strip()

        for round_num in range(3):
            try:
                cmd = [
                    "agy",
                    "--model",
                    "gemini-3.1-pro",
                    "--effort",
                    "high",
                    "--dangerously-skip-permissions",
                    "-p",
                    prompt,
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=360,
                )

                if result.returncode != 0:
                    log.warning(
                        f"⚠️ Agy Error الجولة "
                        f"{round_num + 1}: "
                        f"{result.stderr.strip()[:1000]}"
                    )
                    time.sleep(5)
                    continue

                match = re.search(
                    r"\s*\{.*\}\s*",
                    result.stdout.strip(),
                    re.DOTALL,
                )

                if not match:
                    log.warning(
                        "⚠ لم يتم العثور على "
                        "JSON Array صالح من Agy."
                    )
                    time.sleep(5)
                    continue

                data = json.loads(
                    match.group(0)
                )

                if not isinstance(data, list) or not data:
                    log.warning(
                        "⚠ السيناريو فارغ."
                    )
                    time.sleep(5)
                    continue

                CONFIG.paths.manifest.write_text(
                    json.dumps(
                        data,
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

                log.info(
                    f"✅ تم إنشاء السيناريو: "
                    f"{len(data)} مشهداً."
                )

                return data

            except subprocess.TimeoutExpired:
                log.warning(
                    "⏳ انتهت مهلة توليد السيناريو 360 ثانية."
                )

            except Exception as e:
                log.warning(
                    f"⚠️ خطأ السيناريو: {e}"
                )

            time.sleep(5)

        raise RuntimeError(
            "🛑 فشل إنشاء السيناريو بعد 3 جولات."
        )

    # ============================================================================================
    # VISION SCOUT
    # ============================================================================================

    async def _async_evaluate_scout(
        self,
        media_path,
        narration,
        source
    ):

        prompt = f'''أنت المراجع البصري الفوري (مخرج وثائقي محترف) لفيلم تحقيقي بعنوان:
"{CONFIG.topic}"

نوع المصدر:
{source}

التعليق الصوتي للمشهد:
"{narration}"

شاهد الوسيط المرفق بعناية:
{media_path}

قواعد التقييم كمخرج سينمائي:
1. لا تبحث عن التطابق الحرفي الممل فقط. اقبل (ACCEPT) اللقطات التعبيرية، الرمزية، أو الأجواء العامة (B-Roll) إذا كانت تخدم النص.
2. أعطِ درجة (score) من 0.0 إلى 1.0 تعكس مدى جودة اللقطة لخدمة جو الفيلم.
3. اختر ACCEPT إذا كانت اللقطة مناسبة للجو العام للوثائقي، واختر REJECT إذا كانت مشتتة أو سيئة أو لا علاقة لها إطلاقاً.
4. اشرح سبب القرار باختصار كأنك مخرج.
5. عند الرفض اقترح new_query باللغة الإنجليزية لتوجيه البحث لزاوية تصوير أوسع أو مختلفة تماماً.
6. أخرج JSON فقط بلا Markdown، وتأكد أن يبدأ بـ {{ وينتهي بـ }}.

البنية:
{{
  "decision": "ACCEPT",
  "score": 0.85,
  "reason": "سبب القرار بالعربية",
  "montage": "ZOOM_IN",
  "new_query": "English replacement query"
}}
'''

        try:
            cmd = [
                "agy",
                "--model",
                "gemini-3.8-flash",
                "--effort",
                "high",
                "--dangerously-skip-permissions",
                "-p",
                prompt,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Agy failed: "
                    f"{stderr.decode('utf-8')}"
                )

            result_text = stdout.decode(
                "utf-8"
            ).strip()

            return result_text

        except Exception as e:
            log.error(
                f"⚠️ انهيار المراجع الفوري: {e}"
            )
            return ""

    def evaluate_scene_with_scout(
        self,
        media_path,
        narration,
        source
    ):

        log.info(
            f"👁 Antigravity Vision Scout يفحص "
            f"الوسيط من {source}..."
        )

        try:
            result_text = str(
                asyncio.run(
                    self._async_evaluate_scout(
                        media_path,
                        narration,
                        source,
                    )
                )
            ).strip()

            if (
                not result_text
                or "<google.antigravity" in result_text
                or "<bound method" in result_text
            ):
                log.warning(
                    "⚠️ رد المراجع عبارة عن كائن "
                    "برمجي فارغ، تم رفض المشهد "
                    "للانتقال للتالي."
                )

                return {
                    "accepted": False,
                    "montage": "ZOOM_IN",
                    "new_query": "investigation evidence",
                    "score": 0.0,
                    "reason": "Empty or Object Response",
                }

            log.info(
                f"🗣️ نتيجة المراجع:\n{result_text}"
            )

            data = None

            match = re.search(
                r"\{[\s\S]*\}",
                result_text
            )

            if match:
                try:
                    data = json.loads(
                        match.group(0)
                    )
                except Exception:
                    pass

            if data is None:
                log.warning(
                    "⚠️ تعذر استخراج JSON من الرد: "
                    f"{result_text[:200]}"
                )

                return {
                    "accepted": False,
                    "montage": "ZOOM_IN",
                    "new_query": "archival evidence",
                    "score": 0.0,
                    "reason": "Parse Error",
                }

            score = float(
                data.get("score", 0.0)
            )

            decision = str(
                data.get(
                    "decision",
                    ""
                )
            ).upper()

            return {
                "accepted": (
                    decision == "ACCEPT"
                    and score >= 0.60
                ),
                "montage": data.get(
                    "montage",
                    "NORMAL"
                ),
                "new_query": data.get(
                    "new_query",
                    ""
                ),
                "score": score,
                "reason": data.get(
                    "reason",
                    ""
                ),
            }

        except Exception as e:
            log.error(
                f"⚠️ انهيار المراجع الفوري: {e}"
            )

            return {
                "accepted": False,
                "montage": "ZOOM_IN",
                "new_query": "",
                "score": 0.0,
                "reason": "Exception",
            }

    # ============================================================================================
    # FINAL CRITIQUE
    # ============================================================================================

    async def _async_critique(
        self,
        final_video,
        logs
    ):

        prompt = f'''أنت المراجع النهائي للفيلم الوثائقي.

سجلات النظام:
{logs}

شاهد الفيلم النهائي المرفق:
{final_video}

افحص:
1. تزامن الصوت والصورة.
2. الشاشات السوداء أو التالفة.
3. أخطاء المونتاج الواضحة.
4. المشاكل البرمجية الظاهرة.
5. خصوصاً: هل توجد لقطة واحدة ثابتة أو مكررة لفترة طويلة بشكل غير سينمائي؟

إذا كان هناك خلل برمجي حقيقي يحتاج إلى تعديل:
أخرج كود pipeline.py كاملاً داخل كتلة python.

إذا كان الفيلم سليماً:
أجب بكلمة PERFECT فقط.
'''

        try:
            cmd = [
                "agy",
                "--model",
                "gemini-3.1-pro",
                "--effort",
                "high",
                "--dangerously-skip-permissions",
                "-p",
                prompt,
            ]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Agy failed: "
                    f"{stderr.decode('utf-8')}"
                )

            result_text = stdout.decode(
                "utf-8"
            ).strip()

            return result_text

        except Exception as e:
            log.error(
                f"⚠️ فشل المراجع النهائي: {e}"
            )
            return ""

    def self_critique_and_recode(
        self,
        final_video
    ):

        log.info(
            "🧠 المراجع النهائي يشاهد الفيلم الكامل..."
        )

        logs = (
            Path(
                "production_logs.txt"
            ).read_text(
                encoding="utf-8",
                errors="ignore",
            )[-5000:]
            if Path(
                "production_logs.txt"
            ).exists()
            else "No logs"
        )

        try:
            result_text = str(
                asyncio.run(
                    self._async_critique(
                        final_video,
                        logs,
                    )
                )
            )

            log.info(
                f"🗣️ المراجع النهائي:\n{result_text}"
            )

            if "PERFECT" in result_text.upper():
                log.info(
                    "✅ المراجع النهائي اعتمد الفيلم."
                )
                return True

            code_match = re.search(
                r"```python\s*(.*?)```",
                result_text,
                re.DOTALL,
            )

            if code_match:
                new_code = (
                    code_match.group(1)
                    .strip()
                )

                append_memory(
                    "المراجع النهائي شاهد الفيلم "
                    "وقدم إصلاحاً برمجياً."
                )

                Path(__file__).write_text(
                    new_code,
                    encoding="utf-8",
                )

                log.warning(
                    "🔄 تم استبدال pipeline.py. "
                    "إعادة التشغيل..."
                )

                os.execv(
                    sys.executable,
                    [sys.executable] + sys.argv,
                )

            return True

        except Exception as e:
            log.error(
                f"⚠️ فشل التعديل الذاتي: {e}"
            )
            return True

    # ============================================================================================
    # TTS
    # ============================================================================================

    def generate_voice(
        self,
        text,
        out_wav
    ):

        if not CONFIG.gemini_keys:
            log.error(
                "❌ لا توجد GEMINI_API_KEY "
                "لاستخدامها في الصوت."
            )
            return

        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

        for round_num in range(3):

            log.info(
                f"🎙 توليد الصوت الجولة "
                f"{round_num + 1}/3..."
            )

            for i, key in enumerate(
                CONFIG.gemini_keys
            ):

                try:
                    client = genai.Client(
                        api_key=key
                    )

                    res = client.models.generate_content(
                        model="gemini-3.8-flash-tts",
                        contents=(
                            "[INSTRUCTION: Deep chilling narrator]\n"
                            + text
                        ),
                        config=cfg,
                    )

                    audio_data = (
                        res.candidates[0]
                        .content.parts[0]
                        .inline_data
                        .data
                    )

                    if isinstance(
                        audio_data,
                        str
                    ):
                        out_wav.write_bytes(
                            base64.b64decode(
                                audio_data
                            )
                        )
                    else:
                        out_wav.write_bytes(
                            audio_data
                        )

                    if (
                        out_wav.exists()
                        and out_wav.stat().st_size
                        > 1000
                    ):
                        log.info(
                            "⏳ تم توليد الصوت بنجاح. "
                            "تبريد 30 ثانية..."
                        )

                        time.sleep(30)
                        return

                except Exception as e:
                    log.warning(
                        f"⚠️ فشل المفتاح {i + 1}: "
                        f"{str(e)[:200]}"
                    )
                    time.sleep(2)

            time.sleep(10)

        log.error(
            "❌ استنفدت جميع محاولات توليد الصوت."
        )


# ================================================================================================
# MEDIA FETCHER
# ================================================================================================

class MediaFetcher:

    def __init__(self):
        self.h = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "(KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,"
                "image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://" + "en.wikipedia.org/",
        }

    def _get(
        self,
        url,
        **kwargs
    ):

        kwargs.setdefault(
            "timeout",
            30
        )

        kwargs.setdefault(
            "headers",
            self.h
        )

        response = requests.get(
            url,
            **kwargs
        )

        response.raise_for_status()

        return response

    def fetch_media(
        self,
        source,
        query,
        out,
        index
    ):

        safe_query = enforce_english_query(
            query
        )

        pixabay_query = (
            safe_query[:100].strip()
        )

        try:

            if source == "PEXELS":

                if not CONFIG.pexels:
                    return False

                api_url = (
                    f"https://api.{'pexels'}.com/videos/search"
                )

                r = self._get(
                    api_url,
                    params={
                        "query": safe_query,
                        "orientation": "landscape",
                        "per_page": 10,
                    },
                    headers={
                        "Authorization":
                            CONFIG.pexels,
                        "User-Agent":
                            self.h["User-Agent"],
                    },
                )

                try:
                    data = r.json()
                except Exception:
                    return False

                videos = data.get(
                    "videos",
                    []
                )

                if len(videos) <= index:
                    return False

                files = videos[index].get(
                    "video_files",
                    []
                )

                if not files:
                    return False

                files = sorted(
                    files,
                    key=lambda x:
                        x.get(
                            "width",
                            0
                        ),
                    reverse=True,
                )

                video_url = files[0].get(
                    "link"
                )

                if not video_url:
                    return False

                media = self._get(
                    video_url,
                    headers=self.h,
                    timeout=60,
                )

                out.write_bytes(
                    media.content
                )

                return (
                    out.exists()
                    and out.stat().st_size
                    > 50000
                )

            if source == "PIXABAY":

                if not CONFIG.pixabay:
                    return False

                api_url = (
                    f"https://{'pixabay'}.com/api/videos/"
                )

                r = self._get(
                    api_url,
                    params={
                        "key": CONFIG.pixabay,
                        "q": pixabay_query,
                        "per_page": 10,
                    },
                    headers=self.h,
                )

                try:
                    data = r.json()
                except Exception:
                    return False

                hits = data.get(
                    "hits",
                    []
                )

                if len(hits) <= index:
                    return False

                videos = hits[index].get(
                    "videos",
                    {}
                )

                info = (
                    videos.get("large")
                    or videos.get("medium")
                    or videos.get("small")
                )

                if (
                    not info
                    or not info.get("url")
                ):
                    return False

                media = self._get(
                    info["url"],
                    headers=self.h,
                    timeout=60,
                )

                out.write_bytes(
                    media.content
                )

                return (
                    out.exists()
                    and out.stat().st_size
                    > 50000
                )

            if source == "WIKIPEDIA":

                api_url = (
                    f"https://en.{'wikipedia'}.org/w/api.php"
                )

                r = self._get(
                    api_url,
                    params={
                        "action": "query",
                        "generator": "search",
                        "gsrsearch": safe_query,
                        "gsrnamespace": 0,
                        "gsrlimit": 10,
                        "prop": "pageimages",
                        "piprop": "thumbnail",
                        "pithumbsize": 1920,
                        "format": "json",
                    },
                    headers=self.h,
                )

                try:
                    data = r.json()
                except Exception:
                    return False

                pages = list(
                    data
                    .get("query", {})
                    .get("pages", {})
                    .values()
                )

                pages = [
                    p
                    for p in pages
                    if p.get(
                        "thumbnail",
                        {}
                    ).get("source")
                ]

                if not pages:
                    return False

                image_url = pages[
                    index % len(pages)
                ][
                    "thumbnail"
                ][
                    "source"
                ]

                media = self._get(
                    image_url,
                    headers=self.h,
                    timeout=60,
                )

                out.write_bytes(
                    media.content
                )

                return (
                    out.exists()
                    and out.stat().st_size
                    > 10000
                )

            if source == "ARCHIVE":

                api_url = (
                    f"https://{'archive'}.org/advancedsearch.php"
                )

                r = self._get(
                    api_url,
                    params={
                        "q":
                            f"{safe_query} AND mediatype:image",
                        "fl[]":
                            "identifier",
                        "output":
                            "json",
                        "rows":
                            10,
                    },
                    headers=self.h,
                )

                try:
                    data = r.json()
                except Exception:
                    return False

                docs = (
                    data
                    .get("response", {})
                    .get("docs", [])
                )

                if len(docs) <= index:
                    return False

                identifier = docs[
                    index
                ].get(
                    "identifier"
                )

                if not identifier:
                    return False

                image_url = (
                    "https://"
                    f"{'archive'}.org/services/img/"
                    + urllib.parse.quote(
                        identifier
                    )
                )

                media = self._get(
                    image_url,
                    headers=self.h,
                    timeout=60,
                )

                out.write_bytes(
                    media.content
                )

                return (
                    out.exists()
                    and out.stat().st_size
                    > 10000
                )

            if source == "FREESOUND":

                if not CONFIG.freesound:
                    return False

                api_url = (
                    f"https://{'freesound'}.org/apiv2/search/text/"
                )

                r = self._get(
                    api_url,
                    params={
                        "query": safe_query,
                        "token":
                            CONFIG.freesound,
                        "fields":
                            "previews",
                        "page_size":
                            5,
                    },
                    headers=self.h,
                )

                try:
                    data = r.json()
                except Exception:
                    return False

                results = data.get(
                    "results",
                    []
                )

                if not results:
                    return False

                preview = (
                    results[0]
                    .get("previews", {})
                    .get("preview-hq-mp3")
                )

                if not preview:
                    return False

                media = self._get(
                    preview,
                    headers=self.h,
                    timeout=60,
                )

                out.write_bytes(
                    media.content
                )

                return (
                    out.exists()
                    and out.stat().st_size
                    > 1000
                )

        except requests.RequestException as e:

            err_msg = str(e)

            if "429" in err_msg:
                log.warning(
                    f"⏳ {source} يطلب التمهل "
                    "(Error 429). سننتظر قليلاً..."
                )
                time.sleep(3)

            elif "403" in err_msg:
                log.warning(
                    f"🛡️ {source} يرفض الوصول "
                    "(Error 403). تم التخطي بأمان."
                )

            else:
                log.warning(
                    f"🌐 خطأ شبكة في {source}: "
                    f"{err_msg[:150]}"
                )

        except Exception as e:
            log.warning(
                f"⚠️ خطأ {source}: "
                f"{str(e)[:150]}"
            )

        return False


# ================================================================================================
# SOURCE POOL
# ================================================================================================

def get_source_pool(media_type):

    media_type = str(
        media_type or "WIKIPEDIA"
    ).upper()

    if media_type in [
        "PEXELS",
        "PIXABAY"
    ]:
        return [
            "PEXELS",
            "PEXELS",
            "PEXELS",
            "PIXABAY",
            "PIXABAY",
            "PIXABAY",
        ]

    return [
        "WIKIPEDIA",
        "WIKIPEDIA",
        "WIKIPEDIA",
        "ARCHIVE",
        "ARCHIVE",
        "ARCHIVE",
    ]


# ================================================================================================
# AUDIO PROCESSING
# ================================================================================================

def process_audio(
    voice,
    foley,
    has_foley,
    out
):

    if has_foley:

        fc = (
            "[0:a]loudnorm=I=-16[v];"
            "[1:a]volume=0.04[bg];"
            "[v][bg]amix=inputs=2:"
            "duration=first:"
            "dropout_transition=0[aout]"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(voice),
            "-stream_loop",
            "-1",
            "-i",
            str(foley),
            "-filter_complex",
            fc,
            "-map",
            "[aout]",
            "-ar",
            "48000",
            str(out),
        ]

    else:

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(voice),
            "-filter_complex",
            "[0:a]loudnorm=I=-16[aout]",
            "-map",
            "[aout]",
            "-ar",
            "48000",
            str(out),
        ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if result.returncode != 0:
        log.error(
            f"❌ فشل FFmpeg في معالجة الصوت: "
            f"{out.name}"
        )
        return 3.0

    duration = probe_duration(out)

    if duration is None or duration < 0.5:
        log.error(
            f"❌ تعذر الحصول على مدة الصوت: "
            f"{out.name}"
        )
        return 3.0

    log.info(
        f"🎙 مدة الصوت النهائية: "
        f"{duration:.2f} ثانية"
    )

    return duration


# ================================================================================================
# MONTAGE / SCENE RENDERER V22.33
# ================================================================================================

def render_scene(
    media,
    is_vid,
    aud,
    out,
    dur,
    montage
):
    """
    V22.33:

    - مدة الخرج = dur بشكل صريح.
    - FPS ثابت.
    - لا يوجد zoompan d=frames على input loop.
    - الصور تتحرك ببطء مع الزمن.
    - الفيديو يكرر فقط عند الحاجة، ثم يتوقف إجبارياً.
    """

    dur = max(
        0.5,
        float(dur)
    )

    fx = (
        ",hue=s=0"
        if "BW" in str(
            montage
        ).upper()
        else ",eq=contrast=1.12:saturation=0.85"
    )

    temp_out = Path(
        str(out) + ".rendering.mp4"
    )

    try:
        if temp_out.exists():
            temp_out.unlink()
    except Exception:
        pass

    if is_vid:

        # ----------------------------------------------------------------------------
        # VIDEO SOURCE
        # ----------------------------------------------------------------------------

        video_filter = (
            "[0:v]"
            "scale=1920:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            "fps=25"
            f"{fx}"
            "[v]"
        )

        cmd = [
            "ffmpeg",
            "-y",

            # تكرار الفيديو المصدر عند الحاجة فقط.
            "-stream_loop",
            "-1",

            "-i",
            str(media),

            "-i",
            str(aud),

            "-filter_complex",
            video_filter,

            "-map",
            "[v]",

            "-map",
            "1:a",

            # المدة الإجبارية الدقيقة للمشهد.
            "-t",
            f"{dur:.3f}",

            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-crf",
            "20",

            "-pix_fmt",
            "yuv420p",

            "-r",
            str(TARGET_FPS),

            "-c:a",
            "aac",

            "-b:a",
            "192k",

            "-ar",
            "48000",

            "-shortest",

            "-avoid_negative_ts",
            "make_zero",

            "-movflags",
            "+faststart",

            str(temp_out),
        ]

    else:

        # ----------------------------------------------------------------------------
        # IMAGE SOURCE
        # ----------------------------------------------------------------------------
        #
        # الإصلاح المهم:
        # لا نستخدم zoompan=d={frames}.
        #
        # بدلاً من ذلك:
        # - الصورة loop
        # - zoompan ينتج إطاراً واحداً لكل input frame
        # - zoom يتحرك ببطء
        # - -t يفرض مدة المشهد
        #

        image_filter = (
            "[0:v]"
            "scale=1920:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            "zoompan="
            "z='min(zoom+0.00035,1.12)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            "d=1:"
            "s=1920x1080:"
            "fps=25"
            f"{fx}"
            "[v]"
        )

        cmd = [
            "ffmpeg",
            "-y",

            # الصورة لا نهائية المصدر؛
            # -t سيحدد مدة الناتج.
            "-loop",
            "1",

            "-i",
            str(media),

            "-i",
            str(aud),

            "-filter_complex",
            image_filter,

            "-map",
            "[v]",

            "-map",
            "1:a",

            # مدة المشهد الإجبارية.
            "-t",
            f"{dur:.3f}",

            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-crf",
            "20",

            "-pix_fmt",
            "yuv420p",

            "-r",
            str(TARGET_FPS),

            "-c:a",
            "aac",

            "-b:a",
            "192k",

            "-ar",
            "48000",

            "-shortest",

            "-avoid_negative_ts",
            "make_zero",

            "-movflags",
            "+faststart",

            str(temp_out),
        ]

    log.info(
        f"🎞️ Rendering {out.name} | "
        f"المدة المستهدفة: {dur:.2f}s | "
        f"FPS: {TARGET_FPS}"
    )

    try:

        result = subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:

            log.error(
                f"❌ FFmpeg فشل في رندر "
                f"{out.name}"
            )

            if result.stderr:
                log.error(
                    result.stderr[-2000:]
                )

            return False

        if not temp_out.exists():
            log.error(
                "❌ FFmpeg انتهى بدون إنشاء ملف."
            )
            return False

        # ----------------------------------------------------------------------------
        # VALIDATE OUTPUT
        # ----------------------------------------------------------------------------

        valid, actual, reason = (
            validate_scene_video(
                temp_out,
                dur,
            )
        )

        if not valid:

            log.warning(
                f"⚠️ نتيجة الرندر غير صالحة: "
                f"{reason}"
            )

            try:
                temp_out.unlink()
            except Exception:
                pass

            return False

        # ----------------------------------------------------------------------------
        # MOVE ONLY AFTER SUCCESSFUL VALIDATION
        # ----------------------------------------------------------------------------

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass

        temp_out.replace(out)

        write_render_stamp(
            out,
            actual
        )

        log.info(
            f"✅ Render ناجح: {out.name} | "
            f"{actual:.2f}s"
        )

        return True

    except subprocess.TimeoutExpired:

        log.error(
            f"⏳ انتهت مهلة FFmpeg "
            f"للمشهد {out.name}."
        )

        try:
            temp_out.unlink()
        except Exception:
            pass

        return False

    except Exception as e:

        log.error(
            f"⚠️ خطأ render_scene: "
            f"{str(e)[:500]}"
        )

        try:
            temp_out.unlink()
        except Exception:
            pass

        return False


# ================================================================================================
# CACHE VALIDATION
# ================================================================================================

def get_cached_scene(
    c_mp4,
    expected_duration
):
    """
    لا يقبل الكاش إلا إذا:
    1. لديه Render Stamp.
    2. الـstamp من V22.33.
    3. الفيديو سليم.
    4. مدته تطابق مدة الصوت.
    """

    if not c_mp4.exists():
        return False

    stamp = read_render_stamp(
        c_mp4
    )

    if not stamp:
        log.warning(
            f"♻️ {c_mp4.name}: "
            "لا يوجد Render Stamp. "
            "سيعاد الرندر."
        )

        try:
            c_mp4.unlink()
        except Exception:
            pass

        try:
            get_render_stamp_path(
                c_mp4
            ).unlink()
        except Exception:
            pass

        return False

    if stamp.get(
        "render_version"
    ) != RENDER_VERSION:

        log.warning(
            f"♻️ {c_mp4.name}: "
            "الكاش من إصدار قديم. "
            "سيعاد الرندر."
        )

        try:
            c_mp4.unlink()
        except Exception:
            pass

        try:
            get_render_stamp_path(
                c_mp4
            ).unlink()
        except Exception:
            pass

        return False

    valid, actual, reason = (
        validate_scene_video(
            c_mp4,
            expected_duration,
        )
    )

    if not valid:

        log.warning(
            f"♻️ {c_mp4.name}: "
            f"الكاش غير صالح: {reason}"
        )

        try:
            c_mp4.unlink()
        except Exception:
            pass

        try:
            get_render_stamp_path(
                c_mp4
            ).unlink()
        except Exception:
            pass

        return False

    log.info(
        f"⏭ استخدام كاش V22.33 صالح: "
        f"{c_mp4.name} | {actual:.2f}s"
    )

    return True


# ================================================================================================
# FINAL VIDEO VALIDATION
# ================================================================================================

def validate_final_video(
    final_vid,
    expected_total
):

    if not final_vid.exists():
        return False

    actual = probe_duration(
        final_vid
    )

    if actual is None:
        log.error(
            "❌ تعذر قراءة مدة الفيلم النهائي."
        )
        return False

    difference = (
        actual - expected_total
    )

    log.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    log.info(
        f"🎬 مدة الفيلم المتوقعة: "
        f"{expected_total:.2f} ثانية "
        f"({expected_total / 60:.2f} دقيقة)"
    )

    log.info(
        f"🎬 مدة الفيلم الفعلية: "
        f"{actual:.2f} ثانية "
        f"({actual / 60:.2f} دقيقة)"
    )

    log.info(
        f"🎬 فرق المدة: "
        f"{difference:+.2f} ثانية"
    )

    log.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    # التسامح هنا أكبر قليلاً من المشهد
    # بسبب اختلافات بسيطة في حاوية MP4.
    allowed = max(
        1.0,
        len(str(expected_total)) * 0.01
    )

    if abs(difference) > allowed:

        log.error(
            "🛑 مدة الفيلم النهائي لا تطابق "
            "مجموع مدد المشاهد."
        )

        return False

    return True


# ================================================================================================
# GOOGLE DRIVE
# ================================================================================================

def upload_drive(vid):

    if not (
        CONFIG.yt_id
        and CONFIG.drive_token
    ):
        return

    log.info(
        "☁️ الرفع إلى Google Drive..."
    )

    try:

        token_url = (
            "https://oauth2.googleapis.com/token"
        )

        credentials = Credentials(
            None,
            refresh_token=CONFIG.drive_token,
            token_uri=token_url,
            client_id=CONFIG.yt_id,
            client_secret=CONFIG.yt_secret,
        )

        dr = build(
            "drive",
            "v3",
            credentials=credentials,
        )

        res = dr.files().list(
            q=(
                "name='Broadcast_Vault' and "
                "mimeType='application/vnd.google-apps.folder'"
            ),
            fields="files(id)",
        ).execute()

        files = res.get(
            "files",
            []
        )

        if files:
            fid = files[0]["id"]

        else:
            fid = (
                dr.files()
                .create(
                    body={
                        "name":
                            "Broadcast_Vault",
                        "mimeType":
                            "application/vnd.google-apps.folder",
                    },
                    fields="id",
                )
                .execute()["id"]
            )

        req = dr.files().create(
            body={
                "name": vid.name,
                "parents": [fid],
            },
            media_body=MediaFileUpload(
                str(vid),
                mimetype="video/mp4",
                resumable=True,
                chunksize=5 * 1024 * 1024,
            ),
        )

        while True:

            status, _ = req.next_chunk()

            if status is None:
                break

        log.info(
            "✅ تم حفظ نسخة في Google Drive."
        )

    except Exception as e:
        log.error(
            f"⚠️ فشل Google Drive: {e}"
        )


# ================================================================================================
# YOUTUBE
# ================================================================================================

def upload_youtube(vid):

    if not (
        CONFIG.yt_id
        and CONFIG.yt_refresh
    ):
        return

    log.info(
        "▶ الرفع إلى YouTube كفيديو خاص..."
    )

    try:

        token_url = (
            "https://oauth2.googleapis.com/token"
        )

        credentials = Credentials(
            None,
            refresh_token=CONFIG.yt_refresh,
            token_uri=token_url,
            client_id=CONFIG.yt_id,
            client_secret=CONFIG.yt_secret,
        )

        yt = build(
            "youtube",
            "v3",
            credentials=credentials,
        )

        body = {
            "snippet": {
                "title": (
                    f"نسخة المخرج | "
                    f"{CONFIG.topic} - "
                    f"{int(time.time())}"
                ),
                "description": (
                    "تم الإنتاج عبر "
                    "UNIVERSAL INVESTIGATIVE "
                    "DOCUMENTARY ENGINE "
                    f"{ENGINE_VERSION}"
                ),
                "categoryId": "24",
            },
            "status": {
                "privacyStatus": "private"
            },
        }

        req = yt.videos().insert(
            part="snippet,status",
            body=body,
            media_body=MediaFileUpload(
                str(vid),
                chunksize=-1,
                resumable=True,
                mimetype="video/mp4",
            ),
        )

        while True:

            status, _ = req.next_chunk()

            if status is None:
                break

        log.info(
            "✅ تم الرفع إلى YouTube."
        )

    except Exception as e:
        log.error(
            f"⚠️ فشل YouTube: {e}"
        )


# ================================================================================================
# MAIN
# ================================================================================================

def main():

    start_time = datetime.now()

    log.info(
        f"▶ بدء المحرك {ENGINE_VERSION} | "
        f"القضية: {CONFIG.topic}"
    )

    log.info(
        f"🎬 Montage Renderer: {RENDER_VERSION} | "
        f"{TARGET_WIDTH}x{TARGET_HEIGHT} | "
        f"{TARGET_FPS} FPS"
    )

    director = Hybrid_Director()
    fetcher = MediaFetcher()

    # ============================================================================================
    # PLAN
    # ============================================================================================

    try:

        script = director.plan_documentary()

    except Exception as e:

        log.error(
            str(e)
        )

        sys.exit(1)

    clips = []

    # ============================================================================================
    # SCENES
    # ============================================================================================

    for i, scene in enumerate(script):

        elapsed = (
            datetime.now()
            - start_time
        ).total_seconds()

        if elapsed > 13500:

            log.warning(
                "⏳ تم تجاوز الحد الزمني "
                "الكلي 13,500 ثانية. "
                "سيتم حفظ ما تم إنجازه."
            )

            break

        typ = scene.get(
            "media_type",
            "WIKIPEDIA"
        )

        original_q = scene.get(
            "search_query",
            ""
        )

        foley = scene.get(
            "foley_type",
            "none"
        )

        txt = scene.get(
            "narration",
            ""
        )

        pfx = (
            CONFIG.paths.cache
            / f"s_{i:03d}"
        )

        c_mp4 = pfx.with_suffix(
            ".mp4"
        )

        c_wav = pfx.with_suffix(
            ".wav"
        )

        c_foley = Path(
            f"{pfx}_foley.mp3"
        )

        c_mp3 = pfx.with_suffix(
            ".mp3"
        )

        # ========================================================================================
        # AUDIO FIRST
        # ========================================================================================

        if not c_wav.exists():

            director.generate_voice(
                txt,
                c_wav
            )

        if not c_wav.exists():

            log.error(
                f"❌ لم يتم إنشاء صوت "
                f"للمشهد {i + 1}."
            )

            continue

        has_foley = False

        if (
            foley
            and str(foley).lower()
            != "none"
        ):

            has_foley = fetcher.fetch_media(
                "FREESOUND",
                enforce_english_query(
                    foley
                ),
                c_foley,
                0,
            )

        dur = process_audio(
            c_wav,
            c_foley,
            has_foley,
            c_mp3,
        )

        if dur <= 0:

            log.error(
                f"❌ مدة الصوت غير صالحة "
                f"للمشهد {i + 1}."
            )

            continue

        # ========================================================================================
        # CACHE CHECK — IMPORTANT
        # ========================================================================================

        if get_cached_scene(
            c_mp4,
            dur
        ):

            clips.append(
                c_mp4
            )

            continue

        # ========================================================================================
        # MEDIA SEARCH
        # ========================================================================================

        log.info(
            f"\n🎥 جاري العمل على المشهد "
            f"{i + 1}/{len(script)}..."
        )

        scene_approved = False
        montage_style = "NORMAL"

        current_q = enforce_english_query(
            original_q
        )

        sources_pool = get_source_pool(
            typ
        )

        attempt_counter = 0
        MAX_ATTEMPTS = 15

        query_variants = [
            "documentary evidence",
            "archival photograph",
            "investigation scene",
            "crime investigation",
            "police investigation",
            "historical evidence",
            "news archive",
            "forensic evidence",
            "mysterious location",
            "case evidence",
        ]

        base_q = enforce_english_query(
            original_q
        )

        # أفضل لقطة
        best_score = -1.0
        best_media_ext = ".jpg"
        best_montage = "NORMAL"

        while (
            not scene_approved
            and attempt_counter
            < MAX_ATTEMPTS
        ):

            elapsed = (
                datetime.now()
                - start_time
            ).total_seconds()

            if elapsed > 13500:

                log.warning(
                    f"⏳ انتهى الوقت الكلي "
                    f"أثناء البحث عن "
                    f"المشهد {i + 1}."
                )

                break

            current_source = (
                sources_pool[
                    attempt_counter
                    % len(sources_pool)
                ]
            )

            index_in_source = (
                attempt_counter % 3
            )

            if current_source in [
                "PEXELS",
                "PIXABAY",
            ]:
                c_media = (
                    pfx.with_suffix(
                        ".mp4"
                    )
                )

            else:
                c_media = (
                    pfx.with_suffix(
                        ".jpg"
                    )
                )

            safe_q = enforce_english_query(
                current_q
            )

            log.info(
                f"🔎 محاولة البحث #"
                f"{attempt_counter + 1} | "
                f"{current_source} | "
                f"نتيجة "
                f"{index_in_source + 1}/3 | "
                f"Query: '{safe_q}'"
            )

            try:

                if c_media.exists():
                    c_media.unlink()

            except Exception:
                pass

            found = fetcher.fetch_media(
                current_source,
                safe_q,
                c_media,
                index_in_source,
            )

            if (
                found
                and c_media.exists()
            ):

                log.info(
                    f"👁 تم العثور على وسيط "
                    f"من {current_source}. "
                    "إرساله إلى Antigravity..."
                )

                eval_res = (
                    director.evaluate_scene_with_scout(
                        c_media,
                        txt,
                        current_source,
                    )
                )

                current_score = safe_float(
                    eval_res.get(
                        "score",
                        0.0
                    )
                )

                # ----------------------------------------------------------------------------
                # BEST SHOT BACKUP
                # ----------------------------------------------------------------------------

                if (
                    current_score > best_score
                    and c_media.exists()
                    and c_media.stat().st_size
                    > 1000
                ):

                    best_score = (
                        current_score
                    )

                    best_montage = (
                        eval_res.get(
                            "montage",
                            "NORMAL"
                        )
                    )

                    best_media_ext = (
                        c_media.suffix
                    )

                    backup_path = (
                        pfx.with_name(
                            pfx.name
                            + "_best_backup"
                            + best_media_ext
                        )
                    )

                    shutil.copy2(
                        c_media,
                        backup_path
                    )

                    log.info(
                        "💾 تم حفظ هذه اللقطة "
                        "كأفضل بديل حتى الآن "
                        f"(Score: {best_score})."
                    )

                if eval_res.get(
                    "accepted",
                    False
                ):

                    scene_approved = True

                    montage_style = (
                        eval_res.get(
                            "montage",
                            "NORMAL"
                        )
                    )

                    log.info(
                        f"✅ ACCEPTED | "
                        f"المشهد {i + 1} "
                        f"اعتمد بعد "
                        f"{attempt_counter + 1} "
                        "محاولة."
                    )

                    break

                new_q = (
                    enforce_english_query(
                        eval_res.get(
                            "new_query",
                            ""
                        )
                    )
                )

                if (
                    new_q
                    and new_q
                    != "mystery evidence"
                    and new_q.lower()
                    != safe_q.lower()
                ):

                    current_q = (
                        enforce_english_query(
                            new_q,
                            90
                        )
                    )

                else:

                    variant = (
                        query_variants[
                            attempt_counter
                            % len(query_variants)
                        ]
                    )

                    current_q = (
                        enforce_english_query(
                            f"{base_q} {variant}",
                            90,
                        )
                    )

                log.warning(
                    "🔄 REJECTED | "
                    "Antigravity رفض الوسيط."
                )

                log.info(
                    f"🔎 Query الجديدة: "
                    f"'{current_q}'"
                )

                try:
                    c_media.unlink()
                except Exception:
                    pass

            else:

                log.warning(
                    f"⚠️ {current_source} "
                    "لم يعطِ نتيجة صالحة "
                    f"لـ '{safe_q}'."
                )

            time.sleep(3)

            attempt_counter += 1

            if (
                attempt_counter
                % len(sources_pool)
                == 0
            ):

                variant = (
                    query_variants[
                        (
                            attempt_counter
                            // len(sources_pool)
                        )
                        % len(query_variants)
                    ]
                )

                current_q = (
                    enforce_english_query(
                        f"{base_q} {variant}",
                        90,
                    )
                )

                log.info(
                    "♻️ لم يتم اعتماد أي "
                    "لقطة في الدورة الكاملة. "
                    "تغيير استراتيجية البحث إلى: "
                    f"'{current_q}'"
                )

        # ========================================================================================
        # EMERGENCY BEST SHOT
        # ========================================================================================

        if not scene_approved:

            log.error(
                f"❌ استنفذت جميع المحاولات "
                f"الـ {MAX_ATTEMPTS} "
                f"للمشهد {i + 1}."
            )

            backup_path = (
                pfx.with_name(
                    pfx.name
                    + "_best_backup"
                    + best_media_ext
                )
            )

            if (
                best_score > -1.0
                and backup_path.exists()
                and backup_path.stat().st_size
                > 1000
            ):

                log.warning(
                    "⚠️ إجبار استخدام أفضل "
                    "لقطة بديلة تم العثور "
                    f"عليها (Score: {best_score}) "
                    "كإجراء إنقاذي."
                )

                c_media = (
                    pfx.with_suffix(
                        best_media_ext
                    )
                )

                shutil.move(
                    backup_path,
                    c_media
                )

                scene_approved = True
                montage_style = (
                    best_montage
                )

            else:

                append_memory(
                    f"Scene {i + 1} "
                    f"completely failed after "
                    f"{MAX_ATTEMPTS} attempts. "
                    f"Original query: "
                    f"{original_q}"
                )

                continue

        # ========================================================================================
        # CLEAN BACKUPS
        # ========================================================================================

        try:

            for backup_file in (
                pfx.parent.glob(
                    pfx.name
                    + "_best_backup*"
                )
            ):
                backup_file.unlink()

        except Exception:
            pass

        # ========================================================================================
        # RENDER
        # ========================================================================================

        render_success = False

        # محاولة أولى
        render_success = render_scene(
            c_media,
            c_media.suffix.lower()
            == ".mp4",
            c_mp3,
            c_mp4,
            dur,
            montage_style,
        )

        # محاولة ثانية إذا فشل التحقق
        if not render_success:

            log.warning(
                f"🔁 إعادة رندر المشهد "
                f"{i + 1} بعد فشل التحقق."
            )

            try:
                if c_mp4.exists():
                    c_mp4.unlink()
            except Exception:
                pass

            try:
                get_render_stamp_path(
                    c_mp4
                ).unlink()
            except Exception:
                pass

            render_success = render_scene(
                c_media,
                c_media.suffix.lower()
                == ".mp4",
                c_mp3,
                c_mp4,
                dur,
                "NORMAL",
            )

        # ========================================================================================
        # FINAL SCENE ACCEPTANCE
        # ========================================================================================

        if render_success:

            valid, actual, reason = (
                validate_scene_video(
                    c_mp4,
                    dur
                )
            )

            if valid:

                clips.append(
                    c_mp4
                )

                log.info(
                    f"🎬 تم بناء المشهد "
                    f"{i + 1} بنجاح | "
                    f"{actual:.2f}s"
                )

            else:

                log.error(
                    f"❌ المشهد {i + 1} "
                    f"فشل التحقق النهائي: "
                    f"{reason}"
                )

                try:
                    c_mp4.unlink()
                except Exception:
                    pass

                try:
                    get_render_stamp_path(
                        c_mp4
                    ).unlink()
                except Exception:
                    pass

        else:

            log.error(
                f"❌ فشل بناء ملف المشهد "
                f"{i + 1}."
            )

    # ============================================================================================
    # FINAL ASSEMBLY
    # ============================================================================================

    final_vid = (
        CONFIG.paths.base
        / f"MasterDoc_{int(time.time())}.mp4"
    )

    if clips:

        log.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        log.info(
            "🔍 بدء التحقق من جميع المشاهد "
            "قبل الدمج النهائي..."
        )

        valid_clips = []
        expected_total = 0.0

        for idx, clip in enumerate(
            clips,
            start=1
        ):

            duration = probe_duration(
                clip
            )

            if duration is None:

                log.error(
                    f"❌ المشهد {idx} "
                    "ليس له مدة قابلة للقراءة."
                )

                continue

            has_video, has_audio = (
                probe_stream_info(
                    clip
                )
            )

            if not has_video or not has_audio:

                log.error(
                    f"❌ المشهد {idx} "
                    "يفتقد Video أو Audio."
                )

                continue

            valid_clips.append(
                clip
            )

            expected_total += duration

            log.info(
                f"   المشهد {idx:02d}: "
                f"{duration:.2f}s"
            )

        clips = valid_clips

        log.info(
            f"📊 مجموع مدد المشاهد: "
            f"{expected_total:.2f}s "
            f"= {expected_total / 60:.2f} دقيقة"
        )

        if not clips:

            log.error(
                "❌ لا توجد مشاهد سليمة بعد التحقق."
            )

            sys.exit(1)

        # ========================================================================================
        # CONCAT LIST
        # ========================================================================================

        txt_list = (
            CONFIG.paths.base
            / "video_list.txt"
        )

        txt_list.write_text(
            "\n".join(
                f"file '{c.resolve().as_posix()}'"
                for c in clips
            ),
            encoding="utf-8",
        )

        log.info(
            f"🎞️ دمج {len(clips)} مشهداً..."
        )

        # ----------------------------------------------------------------------------------------
        # IMPORTANT:
        # نستخدم concat demuxer مع ملفات تم توحيد
        # خصائصها في render_scene.
        #
        # لا نستخدم -shortest هنا لأن المطلوب هو
        # دمج جميع المشاهد، وليس قطعها.
        # ----------------------------------------------------------------------------------------

        concat_result = subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(txt_list),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(final_vid),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=900,
        )

        if concat_result.returncode != 0:

            log.error(
                "❌ فشل دمج الفيديوهات."
            )

            if concat_result.stderr:
                log.error(
                    concat_result.stderr[-3000:]
                )

            sys.exit(1)

        # ========================================================================================
        # FINAL VALIDATION
        # ========================================================================================

        if final_vid.exists():

            final_valid = (
                validate_final_video(
                    final_vid,
                    expected_total,
                )
            )

            if not final_valid:

                log.error(
                    "🛑 تم إيقاف العملية: "
                    "الفيلم النهائي لا يطابق "
                    "مجموع مدد المشاهد."
                )

                log.error(
                    "🚫 لن يتم رفع الفيديو "
                    "إلى Google Drive أو YouTube."
                )

                sys.exit(1)

            log.info(
                "🎬 تم تصدير الفيلم النهائي "
                "واجتاز فحص المدة."
            )

            upload_drive(
                final_vid
            )

            upload_youtube(
                final_vid
            )

        else:

            log.error(
                "❌ لم يتم إنشاء الفيلم النهائي."
            )

    else:

        log.error(
            "❌ لا توجد مشاهد جاهزة للدمج."
        )

        sys.exit(1)

    # ============================================================================================
    # FINAL AI CRITIQUE
    # ============================================================================================

    if final_vid.exists():

        director.self_critique_and_recode(
            final_vid
        )


# ================================================================================================
# ENTRY POINT
# ================================================================================================

if __name__ == "__main__":
    main()
