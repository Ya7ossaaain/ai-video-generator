#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
====================================================================================================
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
HYBRID V23 - Antigravity Vision Scout / Real Media Only
====================================================================================================

الهيكل:

- السيناريو:
    Google Antigravity - Gemini 3.1 Pro High

- المراجع البصري الفوري لكل مرشح:
    Google Antigravity - Gemini 3.6 Flash High

- المراجع النهائي للفيديو الحقيقي:
    Google Antigravity - Gemini 3.1 Pro High

- Groq:
    Whisper word timestamps فقط.

- الصوت:
    Google AI Studio Gemini TTS
    Model: gemini-3.8-flash-tts
    Voice: Charon

- دوران مفاتيح TTS:
    3 جولات.

- تبريد TTS بعد النجاح:
    30 ثانية.
    ممنوع تغييره.

- الوسائط:
    PEXELS
    PIXABAY
    MAPBOX
    WIKIPEDIA

- لا يوجد:
    fallback graphic
    placeholder
    CLASSIFIED EVIDENCE
    قبول تلقائي

- كل لقطة حقيقية تمر عبر Gemini 3.6 Flash High.

- فيديوهات:
    3 إطارات:
    20%
    50%
    80%

- البحث:
    PEXELS 3 محاولات
    PIXABAY 3 محاولات
    ثم تكرار الدورة.

- النسخ النهائية:
    كل نسخة يتم الاحتفاظ بها.
    كل نسخة يتم رفعها إلى:
        Google Drive
        YouTube

- حتى النسخ REJECTED يتم الاحتفاظ بها ورفعها.

- أسماء النسخ:
    Documentary_V01_REJECTED.mp4
    Documentary_V02_REJECTED.mp4
    Documentary_V03_ACCEPTED.mp4

- مراجعات منفصلة:
    final_review_V01.json
    final_review_V02.json
    final_review_V03.json

- إذا تم رفض النسخة:
    1. رفع النسخة أولاً.
    2. محاولة إصلاح pipeline.
    3. تنظيف Cache الرندر.
    4. إعادة تشغيل العملية.

- الحد الأقصى:
    3 جولات مراجعة/إصلاح إجمالاً.

- لا يتم حذف الإصدارات السابقة.

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
import hashlib
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
# 1. إعدادات النظام والمراقبة والذاكرة
# ==================================================================================================

class ProTelemetryFormatter(logging.Formatter):

    COLORS = {
        "INFO": "\x1b[38;5;39m",
        "WARNING": "\x1b[38;5;214m",
        "ERROR": "\x1b[38;5;196m",
        "CRITICAL": "\x1b[48;5;196;38;5;231m\x1b[1m"
    }

    RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:

        color = self.COLORS.get(
            record.levelname,
            self.RESET
        )

        return logging.Formatter(
            f"{color}%(asctime)s | [%(levelname)s] | %(message)s{self.RESET}",
            datefmt="%H:%M:%S"
        ).format(record)


def setup_logger() -> logging.Logger:

    logger = logging.getLogger("HybridMaster")
    logger.setLevel(logging.INFO)

    if not logger.handlers:

        ch = logging.StreamHandler(sys.stdout)

        ch.setFormatter(
            ProTelemetryFormatter()
        )

        logger.addHandler(ch)

        fh = logging.FileHandler(
            "production_logs.txt",
            encoding="utf-8"
        )

        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s | [%(levelname)s] | %(message)s"
            )
        )

        logger.addHandler(fh)

    return logger


log = setup_logger()

MEMORY_FILE = Path("director_memory.md")

CURRENT_PIPELINE = Path(
    __file__
).resolve()

MASTER_START_TS = float(
    os.environ.get(
        "MASTER_START_TS",
        str(time.time())
    )
)

FINAL_REVIEW_ROUND = int(
    os.environ.get(
        "FINAL_REVIEW_ROUND",
        "0"
    )
)


# ==================================================================================================
# 2. الذاكرة
# ==================================================================================================

def read_memory() -> str:

    if MEMORY_FILE.exists():

        return MEMORY_FILE.read_text(
            encoding="utf-8"
        )

    return (
        "هذه أول جلسة لك. ركز على إنتاج سيناريو "
        "وثائقي طويل مع مشاهد حقيقية مرتبطة بالسرد."
    )


def append_memory(
    session_summary: str
):

    now = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    entry = (
        f"\n\n### تقرير الجلسة [{now}]\n"
        f"{session_summary}"
    )

    with open(
        MEMORY_FILE,
        "a",
        encoding="utf-8"
    ) as f:

        f.write(entry)


# ==================================================================================================
# 3. المسارات
# ==================================================================================================

@dataclass
class PipelinePaths:

    base: Path = field(
        default_factory=lambda:
        Path("./output_build")
    )

    cache: Path = field(
        default_factory=lambda:
        Path("./output_build/cache")
    )

    manifest: Path = field(
        default_factory=lambda:
        Path("./output_build/master_manifest.json")
    )

    final_review: Path = field(
        default_factory=lambda:
        Path("./output_build/final_review.json")
    )

    def initialize(self):

        for p in [
            self.base,
            self.cache
        ]:

            p.mkdir(
                parents=True,
                exist_ok=True
            )


class HybridConfig:

    topic = os.environ.get(
        "VIDEO_TOPIC",
        "لغز اختفاء طائرة دي بي كوبر"
    )

    paths = PipelinePaths()

    gemini_keys = [
        k.strip()
        for k in os.environ.get(
            "GEMINI_API_KEY",
            ""
        ).split(",")
        if k.strip()
    ]

    pexels = os.environ.get(
        "PEXELS_API_KEY",
        ""
    )

    pixabay = os.environ.get(
        "PIXABAY_API_KEY",
        ""
    )

    mapbox = os.environ.get(
        "MAPBOX_API_KEY",
        ""
    )

    groq = os.environ.get(
        "GROQ_API_KEY",
        ""
    )

    freesound = os.environ.get(
        "FREESOUND_API_KEY",
        ""
    )

    # ----------------------------------------------------------------------------------------------
    # Google OAuth
    # ----------------------------------------------------------------------------------------------

    google_client_id = os.environ.get(
        "GOOGLE_CLIENT_ID",
        ""
    )

    google_client_secret = os.environ.get(
        "GOOGLE_CLIENT_SECRET",
        ""
    )

    drive_token = os.environ.get(
        "DRIVE_REFRESH_TOKEN",
        ""
    )

    yt_refresh = os.environ.get(
        "YOUTUBE_REFRESH_TOKEN",
        ""
    )

    # ----------------------------------------------------------------------------------------------
    # YouTube
    # ----------------------------------------------------------------------------------------------

    youtube_privacy = os.environ.get(
        "YOUTUBE_PRIVACY_STATUS",
        "private"
    ).lower().strip()

    if youtube_privacy not in {
        "private",
        "unlisted",
        "public"
    }:

        youtube_privacy = "private"


CONFIG = HybridConfig()

CONFIG.paths.initialize()

if not CONFIG.gemini_keys:

    sys.exit(
        "🛑 حرج: مفاتيح GEMINI_API_KEY مفقودة!"
    )


# ==================================================================================================
# 4. أدوات مساعدة
# ==================================================================================================

def safe_unlink(
    path: Path
):

    try:

        if path.exists():
            path.unlink()

    except Exception as e:

        log.warning(
            f"⚠️ تعذر حذف {path}: {e}"
        )


def valid_file(
    path: Path,
    minimum_size: int = 50000
) -> bool:

    try:

        return (
            path.exists()
            and path.is_file()
            and path.stat().st_size >= minimum_size
        )

    except Exception:

        return False


def sha256_text(
    text: str
) -> str:

    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def elapsed_seconds() -> float:

    return time.time() - MASTER_START_TS


def runtime_expired() -> bool:

    return elapsed_seconds() >= (
        3 * 3600 + 45 * 60
    )


def safe_topic_slug(
    topic: str
) -> str:

    """
    يحافظ على الحروف العربية ويمنع الأحرف
    غير المناسبة لأسماء الملفات.
    """

    slug = re.sub(
        r"[^\w\u0600-\u06FF\-]+",
        "_",
        topic,
        flags=re.UNICODE
    )

    slug = re.sub(
        r"_+",
        "_",
        slug
    ).strip("_")

    if not slug:

        slug = "Documentary"

    return slug[:90]


def version_filename(
    round_number: int,
    status: str
) -> str:

    slug = safe_topic_slug(
        CONFIG.topic
    )

    return (
        f"{slug}_V{round_number:02d}_{status}.mp4"
    )


# ==================================================================================================
# 5. العقل الهجين
# ==================================================================================================

class Hybrid_Director:

    # ----------------------------------------------------------------------------------------------
    # السيناريو
    # ----------------------------------------------------------------------------------------------

    def plan_documentary(
        self
    ) -> List[Dict]:

        if CONFIG.paths.manifest.exists():

            try:

                existing = json.loads(
                    CONFIG.paths.manifest.read_text(
                        encoding="utf-8"
                    )
                )

                if isinstance(
                    existing,
                    list
                ) and existing:

                    log.info(
                        f"♻️ استخدام السيناريو الموجود: "
                        f"{len(existing)} مشهداً."
                    )

                    return existing

            except Exception:

                log.warning(
                    "⚠️ manifest موجود لكنه غير صالح. سيتم إعادة توليده."
                )

        log.info(
            "🧠 كتابة السيناريو عبر Antigravity Gemini 3.1 Pro High..."
        )

        prompt = f"""
أنت كبير المخرجين والباحثين في إنتاج وثائقيات التحقيق.

موضوع الوثائقي:
"{CONFIG.topic}"

ابنِ سيناريو وثائقي من 40 إلى 50 مشهداً.

الهدف:
إنتاج وثائقي طويل يتجاوز 18 دقيقة.

القواعد:

1. النص في كل مشهد من 60 إلى 80 كلمة.
2. العربية فصحى مشكولة بدقة.
3. الأدوات المسموحة:
   PEXELS
   PIXABAY
   MAPBOX
   WIKIPEDIA

4. foley_type يجب أن يكون باللغة الإنجليزية.
5. search_query يجب أن يكون وصفاً بصرياً واضحاً وقابلاً للبحث.
6. كل مشهد يجب أن يخدم المعلومة الموجودة في السرد.
7. لا تستخدم لقطات عشوائية.
8. لا تطلب لقطات لا يمكن العثور عليها واقعياً.
9. اجعل البحث عن الأشخاص والأماكن والأحداث محدداً قدر الإمكان.
10. لا تعتمد على جمال اللقطة وحده.
11. يجب أن تكون اللقطة قابلة للتطابق بصرياً مع السرد.

[الذاكرة]
{read_memory()}

أخرج JSON Array فقط:

[
  {{
    "scene_num": 1,
    "media_type": "PEXELS",
    "search_query": "dark rainy street at night cinematic",
    "foley_type": "rain",
    "narration": "..."
  }}
]
"""

        for attempt in range(3):

            try:

                cmd = [
                    "agy",
                    "--model",
                    "gemini-3.1-pro-high",
                    "-p",
                    prompt
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                    timeout=900
                )

                output = result.stdout.strip()

                match = re.search(
                    r"\[.*\]",
                    output,
                    re.DOTALL
                )

                if not match:

                    log.warning(
                        "⚠️ Antigravity لم يرجع JSON صالحاً."
                    )

                    time.sleep(5)

                    continue

                data = json.loads(
                    match.group(0)
                )

                if not isinstance(
                    data,
                    list
                ) or not data:

                    raise ValueError(
                        "السيناريو فارغ."
                    )

                CONFIG.paths.manifest.write_text(
                    json.dumps(
                        data,
                        ensure_ascii=False,
                        indent=2
                    ),
                    encoding="utf-8"
                )

                log.info(
                    f"✅ تم إنشاء السيناريو: {len(data)} مشهداً."
                )

                return data

            except subprocess.TimeoutExpired:

                log.warning(
                    f"⚠️ انتهى وقت Antigravity "
                    f"(المحاولة {attempt + 1}/3)"
                )

            except Exception as e:

                log.warning(
                    f"⚠️ خطأ أثناء توليد السيناريو: {e}"
                )

                time.sleep(5)

        sys.exit(
            "🛑 فشل Antigravity في كتابة السيناريو."
        )

    # ----------------------------------------------------------------------------------------------
    # المراجع البصري الفوري
    # ----------------------------------------------------------------------------------------------

    def evaluate_scene_with_scout(
        self,
        media_path: Path,
        narration: str
    ) -> Dict:

        log.info(
            "👁️ Gemini 3.6 Flash High يفحص المرشح..."
        )

        eval_img_path = (
            CONFIG.paths.cache
            / f"{media_path.stem}_vision_review.jpg"
        )

        try:

            if media_path.suffix.lower() == ".mp4":

                probe_cmd = [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(media_path)
                ]

                try:

                    duration_output = (
                        subprocess.check_output(
                            probe_cmd,
                            stderr=subprocess.DEVNULL
                        )
                        .decode()
                        .strip()
                    )

                    video_duration = float(
                        duration_output
                    )

                except Exception:

                    video_duration = 5.0

                frame_paths = []

                positions = [
                    0.20,
                    0.50,
                    0.80
                ]

                for idx, pos in enumerate(
                    positions
                ):

                    frame_path = (
                        CONFIG.paths.cache
                        / f"{media_path.stem}_frame_{idx}.jpg"
                    )

                    seek_time = max(
                        0.2,
                        video_duration * pos
                    )

                    frame_cmd = [
                        "ffmpeg",
                        "-y",
                        "-ss",
                        str(seek_time),
                        "-i",
                        str(media_path),
                        "-frames:v",
                        "1",
                        "-q:v",
                        "2",
                        str(frame_path)
                    ]

                    subprocess.run(
                        frame_cmd,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=60
                    )

                    if frame_path.exists():

                        frame_paths.append(
                            frame_path
                        )

                if not frame_paths:

                    return {
                        "valid": False,
                        "montage": "NORMAL",
                        "reason": "تعذر استخراج إطارات من الفيديو."
                    }

                opened = []

                for fp in frame_paths:

                    try:

                        opened.append(
                            Image.open(fp).convert("RGB")
                        )

                    except Exception:

                        pass

                if not opened:

                    return {
                        "valid": False,
                        "montage": "NORMAL",
                        "reason": "تعذر قراءة إطارات الفيديو."
                    }

                thumb_w = 640
                thumb_h = 360

                sheet = Image.new(
                    "RGB",
                    (
                        thumb_w * len(opened),
                        thumb_h
                    ),
                    "black"
                )

                for idx, img in enumerate(
                    opened
                ):

                    img.thumbnail(
                        (
                            thumb_w,
                            thumb_h
                        )
                    )

                    x = idx * thumb_w

                    sheet.paste(
                        img,
                        (
                            x,
                            0
                        )
                    )

                sheet.save(
                    eval_img_path,
                    "JPEG",
                    quality=94
                )

                for fp in frame_paths:

                    safe_unlink(fp)

            else:

                if media_path.exists():

                    img = Image.open(
                        media_path
                    ).convert("RGB")

                    img.save(
                        eval_img_path,
                        "JPEG",
                        quality=94
                    )

        except Exception as e:

            log.warning(
                f"⚠️ فشل تجهيز الوسيط للمراجعة: {e}"
            )

            return {
                "valid": False,
                "montage": "NORMAL",
                "reason": str(e)
            }

        if not eval_img_path.exists():

            log.error(
                "❌ لم يتم إنشاء مادة المراجعة."
            )

            return {
                "valid": False,
                "montage": "NORMAL",
                "reason": "review image missing"
            }

        image_path = str(
            eval_img_path.resolve()
        )

        prompt = f"""
أنت مراجع بصري صارم لوثائقي تحقيق جنائي.

يجب عليك فتح الصورة الموجودة هنا فعلياً:

{image_path}

إذا كانت الصورة عبارة عن Contact Sheet، فهي تحتوي على عدة إطارات من نفس الفيديو:
البداية تقريباً، المنتصف، والنهاية.

النص السردي:

"{narration}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
المطلوب
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

افحص الصورة فعلياً.

لا تعتمد على اسم الملف.
لا تعتمد على search query.
لا تفترض أن اللقطة صحيحة فقط لأنها جميلة.
لا تحاول مجاملة خط الإنتاج.

اسأل:

1. ماذا يظهر فعلياً؟
2. هل ما يظهر مرتبط مباشرة بالسرد؟
3. هل اللقطة يمكن وضعها في هذا الموضع من الوثائقي؟
4. هل يوجد عنصر واضح غير متعلق؟
5. هل المكان/الشخص/السيارة/الطائرة/الحدث، إن وجد، يتوافق مع السرد؟
6. هل الفيديو يحتوي على تغيرات تجعل اللقطة غير مناسبة؟
7. هل الجودة مقبولة؟
8. هل هناك تشوه أو لقطة سيئة؟
9. هل المشهد يعطي انطباعاً مضللاً؟
10. هل اللقطة حقيقية وليست بطاقة أو placeholder؟

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قاعدة القبول
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ACCEPT فقط إذا كان هناك تطابق بصري واضح ومفيد مع السرد.

REJECT إذا:

- الصورة عشوائية.
- الصورة لا علاقة لها بالسرد.
- اللقطة جميلة لكن معناها خاطئ.
- تحتوي على عناصر مضللة.
- الجودة سيئة جداً.
- لا يمكن تبرير وجودها في المشهد.

كن صارماً.

الأولوية:

التطابق مع السرد
ثم الملاءمة الوثائقية
ثم الجودة السينمائية.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
المونتاج
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ZOOM_IN
PAN_RIGHT
BW
NORMAL

اختر واحداً فقط.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
الإخراج
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

أخرج JSON فقط:

{{
  "decision": "ACCEPT",
  "montage": "NORMAL",
  "reason": "سبب مختصر"
}}

decision يجب أن يكون:
ACCEPT
أو
REJECT
"""

        try:

            cmd = [
                "agy",
                "--model",
                "gemini-3.6-flash-high",
                "--dangerously-skip-permissions",
                "-p",
                prompt
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=180
            )

            output = result.stdout.strip()

            log.info(
                f"🔎 رد Gemini 3.6:\n{output[:700]}"
            )

            match = re.search(
                r"\{.*\}",
                output,
                re.DOTALL
            )

            if not match:

                return {
                    "valid": False,
                    "montage": "NORMAL",
                    "reason": "لم يرجع JSON صالحاً."
                }

            data = json.loads(
                match.group(0)
            )

            decision = str(
                data.get(
                    "decision",
                    "REJECT"
                )
            ).upper().strip()

            montage = str(
                data.get(
                    "montage",
                    "NORMAL"
                )
            ).upper().strip()

            if montage not in {
                "ZOOM_IN",
                "PAN_RIGHT",
                "BW",
                "NORMAL"
            }:

                montage = "NORMAL"

            reason = str(
                data.get(
                    "reason",
                    ""
                )
            )

            if decision == "ACCEPT":

                log.info(
                    "✅ Gemini 3.6: ACCEPT"
                )

                log.info(
                    f"🎬 Montage: {montage}"
                )

                return {
                    "valid": True,
                    "montage": montage,
                    "reason": reason
                }

            log.warning(
                "❌ Gemini 3.6: REJECT"
            )

            log.warning(
                f"السبب: {reason}"
            )

            return {
                "valid": False,
                "montage": montage,
                "reason": reason
            }

        except subprocess.TimeoutExpired:

            log.warning(
                "⚠️ انتهى وقت Gemini 3.6."
            )

            return {
                "valid": False,
                "montage": "NORMAL",
                "reason": "vision timeout"
            }

        except Exception as e:

            log.warning(
                f"⚠️ خطأ Vision: {e}"
            )

            return {
                "valid": False,
                "montage": "NORMAL",
                "reason": str(e)
            }

        finally:

            safe_unlink(
                eval_img_path
            )

    # ----------------------------------------------------------------------------------------------
    # المراجعة النهائية للفيديو الحقيقي
    # ----------------------------------------------------------------------------------------------

    def final_video_review(
        self,
        video_path: Path
    ) -> Dict:

        log.info(
            "🎞️ بدء المراجعة النهائية للفيديو الكامل..."
        )

        if not valid_file(
            video_path,
            50000
        ):

            return {
                "decision": "REJECT",
                "reason": "الملف النهائي غير صالح أو فارغ.",
                "issues": [],
                "fixes": []
            }

        video_abs = str(
            video_path.resolve()
        )

        prompt = f"""
أنت المخرج النهائي والمراجع التقني لوثائقي تحقيق.

الفيديو النهائي الحقيقي موجود هنا:

{video_abs}

يجب عليك فحص الفيديو الفعلي باستخدام أدواتك البصرية.

لا تعتمد فقط على:
- manifest
- أسماء الملفات
- production logs
- وصف المشاهد

بل افحص الناتج المرئي الحقيقي.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
راجع الفيديو من منظور شامل
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

تحقق من:

1. هل اللقطات مرتبطة فعلاً بالسرد؟
2. هل توجد لقطات عشوائية؟
3. هل توجد لقطات مكررة بلا سبب؟
4. هل توجد لقطات سيئة الجودة؟
5. هل توجد إطارات سوداء؟
6. هل هناك قصات غير منطقية؟
7. هل مدة المشاهد مناسبة؟
8. هل الانتقالات سليمة؟
9. هل الصوت متزامن؟
10. هل توجد فجوات صوتية؟
11. هل مستوى الصوت مناسب؟
12. هل الترجمة تظهر في الوقت الصحيح؟
13. هل الترجمة مقصوصة؟
14. هل توجد أخطاء في النص؟
15. هل توجد بطاقة placeholder؟
16. هل توجد صورة أو لقطة لا علاقة لها بالسرد؟
17. هل يوجد خلل سببه pipeline وليس المادة نفسها؟
18. هل ترتيب الأحداث منطقي؟
19. هل هناك مشاكل في الرندر؟
20. هل جودة الفيديو النهائية مناسبة؟

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
مهم جداً
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

إذا وجدت مشكلة، حاول تحديد السبب الجذري في pipeline.

مثلاً:

- اختيار وسيط خاطئ
- مراجعة بصرية ضعيفة
- query غير مناسبة
- استخدام ملف خام كمخرج
- مشكلة في cache
- مشكلة في الترجمة
- مشكلة في الرندر
- مشكلة في مدة المشهد
- مشكلة في concat

لا تخف من REJECT.

لا تعتبر الفيديو مثالياً لمجرد أنه يعمل تقنياً.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
الإخراج
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

JSON فقط:

{{
  "decision": "ACCEPT",
  "reason": "ملخص",
  "issues": [
    {{
      "time": "00:00-00:20",
      "type": "VISUAL",
      "problem": "المشكلة",
      "cause": "السبب الجذري المحتمل",
      "fix": "الإصلاح المقترح"
    }}
  ],
  "fixes": [
    "إصلاح 1",
    "إصلاح 2"
  ]
}}

decision:
ACCEPT
أو
REJECT
"""

        try:

            cmd = [
                "agy",
                "--model",
                "gemini-3.1-pro-high",
                "--dangerously-skip-permissions",
                "--print-timeout",
                "20m",
                "-p",
                prompt
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=1200
            )

            output = result.stdout.strip()

            log.info(
                f"🧠 المراجعة النهائية:\n{output[:1500]}"
            )

            match = re.search(
                r"\{.*\}",
                output,
                re.DOTALL
            )

            if not match:

                return {
                    "decision": "REJECT",
                    "reason": "المراجع النهائي لم يرجع JSON.",
                    "issues": [],
                    "fixes": []
                }

            review = json.loads(
                match.group(0)
            )

            decision = str(
                review.get(
                    "decision",
                    "REJECT"
                )
            ).upper().strip()

            review["decision"] = (
                "ACCEPT"
                if decision == "ACCEPT"
                else "REJECT"
            )

            return review

        except Exception as e:

            log.error(
                f"❌ فشل المراجع النهائي: {e}"
            )

            return {
                "decision": "REJECT",
                "reason": str(e),
                "issues": [],
                "fixes": []
            }

    # ----------------------------------------------------------------------------------------------
    # إصلاح pipeline
    # ----------------------------------------------------------------------------------------------

    def apply_final_repairs(
        self,
        review: Dict
    ) -> bool:

        log.warning(
            "🛠️ Gemini 3.1 Pro سيحاول إصلاح السبب الجذري..."
        )

        review_text = json.dumps(
            review,
            ensure_ascii=False,
            indent=2
        )

        prompt = f"""
أنت مهندس البرمجيات والمخرج التقني المسؤول عن إصلاح خط إنتاج وثائقي.

ملف الـpipeline الحالي هو:

{CURRENT_PIPELINE}

المراجعة النهائية للفيديو:

{review_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
المهمة
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

افتح ملف الـpipeline الحالي وافحص الكود فعلياً.

حدد السبب الجذري للمشاكل المذكورة.

ثم عدّل الكود نفسه لإصلاح المشاكل.

لا تكتف بإخفاء المشكلة.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قيود إلزامية
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. ممنوع إضافة fallback graphic.
2. ممنوع إضافة placeholder.
3. ممنوع إضافة CLASSIFIED EVIDENCE.
4. ممنوع قبول لقطة لمجرد عدم وجود بديل.
5. Gemini 3.6 Flash High يجب أن يبقى المراجع البصري للمشهد.
6. يجب أن يتم رفض اللقطات غير المناسبة فعلياً.
7. يجب أن يستمر البحث عن وسائط حقيقية.
8. لا تحذف فحص Gemini 3.6.
9. لا تستخدم Groq Vision.
10. Groq يبقى فقط لـ Whisper.
11. لا تغيّر نموذج TTS.
12. لا تغيّر دوران مفاتيح TTS.
13. لا تغيّر فترة التبريد 30 ثانية.
14. يجب أن تبقى حرفياً:
    time.sleep(30)
    بعد نجاح توليد الصوت.
15. لا تحذف المراجعة النهائية للفيديو.
16. لا تكسر Google Drive.
17. لا تكسر YouTube upload.
18. لا تكسر FFmpeg.
19. لا تحذف Cache إلا إذا كان ضرورياً.
20. لا تغيّر مفاتيح البيئة.
21. لا تستبدل النظام الحقيقي ببيانات وهمية.
22. يجب الاحتفاظ بكل النسخ النهائية السابقة.
23. لا تضف أي منطق يحذف النسخ الموجودة في output_build.
24. يجب أن تبقى عملية رفع النسخة قبل الإصلاح عند REJECT.
25. يجب الحفاظ على versioning للنسخ.

إذا كان هناك خطأ في اختيار الوسائط:
اجعل النظام يجلب مرشحاً آخر ثم يفحصه.

إذا كان هناك خطأ في الرندر:
أصلح الرندر.

إذا كان هناك خطأ في cache:
أصلحه.

إذا كان هناك خطأ في الترجمة:
أصلحه.

إذا كانت المشكلة بسبب search_query:
يمكن تعديل منطق البحث أو manifest عند الحاجة.

قبل تعديل الملف:
أنشئ نسخة احتياطية:

{CURRENT_PIPELINE}.bak

بعد التعديل:
شغّل:

python3 -m py_compile "{CURRENT_PIPELINE}"

إذا فشل syntax:
أصلح الخطأ.

لا تكتب تقريراً طويلاً.

أصلح الملفات مباشرة.
"""

        try:

            # --------------------------------------------------------------------------------------
            # Backup إضافي من Python قبل أن يتدخل Antigravity.
            # --------------------------------------------------------------------------------------

            backup_path = CURRENT_PIPELINE.with_suffix(
                CURRENT_PIPELINE.suffix + ".bak"
            )

            try:

                backup_path.write_bytes(
                    CURRENT_PIPELINE.read_bytes()
                )

                log.info(
                    f"🛡️ تم إنشاء backup: {backup_path}"
                )

            except Exception as backup_error:

                log.warning(
                    f"⚠️ تعذر إنشاء backup: {backup_error}"
                )

            cmd = [
                "agy",
                "--model",
                "gemini-3.1-pro-high",
                "--dangerously-skip-permissions",
                "--print-timeout",
                "20m",
                "-p",
                prompt
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1200
            )

            log.info(
                f"🔧 نتيجة مهندس الإصلاح:\n"
                f"{result.stdout[-2000:]}"
            )

            if result.returncode != 0:

                log.error(
                    f"❌ فشل Antigravity في الإصلاح: "
                    f"{result.stderr[-1000:]}"
                )

                return False

            try:

                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "py_compile",
                        str(CURRENT_PIPELINE)
                    ],
                    check=True,
                    timeout=60
                )

                log.info(
                    "✅ فحص Python syntax ناجح."
                )

            except Exception as e:

                log.error(
                    f"❌ الكود المعدل غير صالح Python: {e}"
                )

                return False

            return True

        except Exception as e:

            log.error(
                f"❌ خطأ أثناء الإصلاح الذاتي: {e}"
            )

            return False

    # ----------------------------------------------------------------------------------------------
    # TTS
    # ----------------------------------------------------------------------------------------------

    def generate_voice(
        self,
        text: str,
        out_wav: Path
    ):

        prompt = (
            "[INSTRUCTION: Documentary narrator. "
            "Deep, chilling voice. Read normally.]\n\n"
            f"{text}"
        )

        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            )
        )

        for round_num in range(3):

            for i, key in enumerate(
                CONFIG.gemini_keys
            ):

                try:

                    temp_client = genai.Client(
                        api_key=key
                    )

                    res = temp_client.models.generate_content(
                        model="gemini-3.8-flash-tts",
                        contents=prompt,
                        config=cfg
                    )

                    raw = (
                        res
                        .candidates[0]
                        .content
                        .parts[0]
                        .inline_data
                        .data
                    )

                    out_wav.write_bytes(
                        base64.b64decode(raw)
                        if isinstance(raw, str)
                        else raw
                    )

                    log.info(
                        "⏳ تم توليد الصوت بنجاح. "
                        "بدء التبريد (30 ثانية)..."
                    )

                    # ==========================================================================
                    # لا نلمس فترة التبريد.
                    # ==========================================================================

                    time.sleep(30)

                    return True

                except Exception as e:

                    log.warning(
                        f"⚠️ فشل المفتاح ({i + 1}) "
                        f"لتوليد الصوت. التبديل للتالي..."
                    )

                    log.warning(
                        f"تفاصيل: {e}"
                    )

                    time.sleep(2)

            time.sleep(10)

        log.error(
            "❌ استنفدت جميع المفاتيح لتوليد الصوت!"
        )

        return False


# ==================================================================================================
# 6. محرك الوسائط
# ==================================================================================================

class MediaFetcher:

    def __init__(self):

        self.h = {
            "User-Agent": "HybridPipeline/23.0"
        }

    # ----------------------------------------------------------------------------------------------
    # Pexels / Pixabay
    # ----------------------------------------------------------------------------------------------

    def fetch_video(
        self,
        source: str,
        query: str,
        out: Path,
        index: int = 0
    ) -> bool:

        safe_unlink(out)

        try:

            if source == "PEXELS":

                if not CONFIG.pexels:
                    return False

                r = requests.get(
                    "https://api.pexels.com/videos/search",
                    params={
                        "query": query,
                        "orientation": "landscape",
                        "per_page": min(
                            80,
                            max(
                                10,
                                index + 5
                            )
                        )
                    },
                    headers={
                        "Authorization":
                        CONFIG.pexels
                    },
                    timeout=20
                )

                if r.status_code != 200:

                    log.warning(
                        f"PEXELS HTTP {r.status_code}"
                    )

                    return False

                data = r.json()

                videos = data.get(
                    "videos",
                    []
                )

                if len(videos) <= index:
                    return False

                video = videos[index]

                files = sorted(
                    video.get(
                        "video_files",
                        []
                    ),
                    key=lambda x:
                    x.get(
                        "width",
                        0
                    ),
                    reverse=True
                )

                if not files:
                    return False

                video_url = files[0].get(
                    "link"
                )

                if not video_url:
                    return False

                response = requests.get(
                    video_url,
                    timeout=90
                )

                if response.status_code != 200:
                    return False

                if len(response.content) < 50000:
                    return False

                out.write_bytes(
                    response.content
                )

                return valid_file(
                    out,
                    50000
                )

            if source == "PIXABAY":

                if not CONFIG.pixabay:
                    return False

                r = requests.get(
                    "https://pixabay.com/api/videos/",
                    params={
                        "key": CONFIG.pixabay,
                        "q": query,
                        "per_page": min(
                            200,
                            max(
                                20,
                                index + 10
                            )
                        )
                    },
                    timeout=20
                )

                if r.status_code != 200:

                    log.warning(
                        f"PIXABAY HTTP {r.status_code}"
                    )

                    return False

                data = r.json()

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

                candidates = [
                    videos.get("large"),
                    videos.get("medium"),
                    videos.get("small")
                ]

                video_url = None

                for candidate in candidates:

                    if (
                        isinstance(
                            candidate,
                            dict
                        )
                        and candidate.get("url")
                    ):

                        video_url = candidate["url"]

                        break

                if not video_url:
                    return False

                response = requests.get(
                    video_url,
                    timeout=90
                )

                if response.status_code != 200:
                    return False

                if len(response.content) < 50000:
                    return False

                out.write_bytes(
                    response.content
                )

                return valid_file(
                    out,
                    50000
                )

        except Exception as e:

            log.warning(
                f"⚠️ فشل جلب {source}: {e}"
            )

        safe_unlink(out)

        return False

    # ----------------------------------------------------------------------------------------------
    # الصور
    # ----------------------------------------------------------------------------------------------

    def fetch_image(
        self,
        source: str,
        query: str,
        out: Path,
        index: int = 0
    ) -> bool:

        safe_unlink(out)

        try:

            if source == "MAPBOX":

                if not CONFIG.mapbox:
                    return False

                response = requests.get(
                    f"https://api.mapbox.com/styles/v1/"
                    f"mapbox/dark-v11/static/"
                    f"{query},14,0,0/1920x1080",
                    params={
                        "access_token":
                        CONFIG.mapbox
                    },
                    timeout=30
                )

                if (
                    response.status_code == 200
                    and response.content
                ):

                    out.write_bytes(
                        response.content
                    )

                    return valid_file(
                        out,
                        5000
                    )

                return False

            if source == "WIKIPEDIA":

                r = requests.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "generator": "search",
                        "gsrsearch": query,
                        "gsrlimit": min(
                            50,
                            max(
                                10,
                                index + 5
                            )
                        ),
                        "prop": "pageimages",
                        "pithumbsize": 1920,
                        "format": "json"
                    },
                    headers=self.h,
                    timeout=20
                )

                if r.status_code != 200:
                    return False

                pages = list(
                    r.json()
                    .get(
                        "query",
                        {}
                    )
                    .get(
                        "pages",
                        {}
                    )
                    .values()
                )

                pages = [
                    p for p in pages
                    if p.get(
                        "thumbnail",
                        {}
                    ).get(
                        "source"
                    )
                ]

                if len(pages) <= index:
                    return False

                thumb = pages[index][
                    "thumbnail"
                ]["source"]

                response = requests.get(
                    thumb,
                    headers=self.h,
                    timeout=30
                )

                if response.status_code != 200:
                    return False

                if len(response.content) < 5000:
                    return False

                out.write_bytes(
                    response.content
                )

                return valid_file(
                    out,
                    5000
                )

        except Exception as e:

            log.warning(
                f"⚠️ فشل جلب الصورة {source}: {e}"
            )

        safe_unlink(out)

        return False

    # ----------------------------------------------------------------------------------------------
    # Freesound
    # ----------------------------------------------------------------------------------------------

    def get_freesound_foley(
        self,
        query: str,
        out: Path
    ) -> bool:

        if (
            not CONFIG.freesound
            or not query
            or query.lower() == "none"
        ):

            return False

        try:

            r = requests.get(
                "https://freesound.org/apiv2/search/text/",
                params={
                    "query": query,
                    "token": CONFIG.freesound,
                    "fields": "previews",
                    "page_size": 5
                },
                timeout=20
            )

            if r.status_code != 200:
                return False

            results = r.json().get(
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

            response = requests.get(
                preview,
                timeout=30
            )

            if response.status_code != 200:
                return False

            out.write_bytes(
                response.content
            )

            return valid_file(
                out,
                1000
            )

        except Exception as e:

            log.warning(
                f"⚠️ خطأ Freesound: {e}"
            )

            return False


# ==================================================================================================
# 7. البحث عن لقطة حقيقية مقبولة
# ==================================================================================================

def find_accepted_media(
    director: Hybrid_Director,
    fetcher: MediaFetcher,
    source_type: str,
    query: str,
    narration: str,
    video_path: Path,
    image_path: Path
) -> Dict:

    if source_type in {
        "PEXELS",
        "PIXABAY"
    }:

        MAX_CYCLES = 4

        for cycle in range(
            MAX_CYCLES
        ):

            source_order = [
                "PEXELS",
                "PIXABAY"
            ]

            for source in source_order:

                if runtime_expired():

                    log.warning(
                        "⏳ حد الزمن اقترب أثناء البحث عن الوسائط."
                    )

                    return {
                        "accepted": False
                    }

                if (
                    source == "PEXELS"
                    and not CONFIG.pexels
                ):

                    log.warning(
                        "⚠️ PEXELS API غير موجود."
                    )

                    continue

                if (
                    source == "PIXABAY"
                    and not CONFIG.pixabay
                ):

                    log.warning(
                        "⚠️ PIXABAY API غير موجود."
                    )

                    continue

                log.info(
                    f"🔄 المصدر الحالي: {source} | "
                    f"الدورة {cycle + 1}/{MAX_CYCLES}"
                )

                for local_attempt in range(3):

                    global_index = (
                        cycle * 3
                        + local_attempt
                    )

                    log.info(
                        f"🔎 {source} | "
                        f"محاولة {local_attempt + 1}/3 "
                        f"| المرشح #{global_index + 1}"
                    )

                    safe_unlink(
                        video_path
                    )

                    fetched = fetcher.fetch_video(
                        source,
                        query,
                        video_path,
                        global_index
                    )

                    if not fetched:

                        log.warning(
                            f"⚠️ {source} لم يعثر على "
                            f"مرشح رقم {global_index + 1}."
                        )

                        continue

                    evaluation = (
                        director.evaluate_scene_with_scout(
                            video_path,
                            narration
                        )
                    )

                    if evaluation.get(
                        "valid",
                        False
                    ):

                        log.info(
                            f"🏆 ACCEPT — {source} "
                            f"المرشح #{global_index + 1}"
                        )

                        return {
                            "accepted": True,
                            "source": source,
                            "path": video_path,
                            "is_video": True,
                            "montage": evaluation.get(
                                "montage",
                                "NORMAL"
                            ),
                            "reason": evaluation.get(
                                "reason",
                                ""
                            ),
                            "candidate": global_index
                        }

                    log.warning(
                        f"❌ REJECT — {source} "
                        f"المرشح #{global_index + 1}"
                    )

                    safe_unlink(
                        video_path
                    )

        log.error(
            "🚫 لم يتم العثور على لقطة فيديو حقيقية مقبولة."
        )

        return {
            "accepted": False
        }

    source = source_type

    if source not in {
        "MAPBOX",
        "WIKIPEDIA"
    }:

        source = "WIKIPEDIA"

    MAX_IMAGE_ATTEMPTS = 12

    for index in range(
        MAX_IMAGE_ATTEMPTS
    ):

        if runtime_expired():

            return {
                "accepted": False
            }

        log.info(
            f"🔎 {source} | "
            f"محاولة الصورة {index + 1}/{MAX_IMAGE_ATTEMPTS}"
        )

        safe_unlink(
            image_path
        )

        fetched = fetcher.fetch_image(
            source,
            query,
            image_path,
            index
        )

        if not fetched:

            log.warning(
                f"⚠️ لم يتم جلب صورة رقم {index + 1}."
            )

            continue

        evaluation = (
            director.evaluate_scene_with_scout(
                image_path,
                narration
            )
        )

        if evaluation.get(
            "valid",
            False
        ):

            log.info(
                f"🏆 ACCEPT — {source} "
                f"الصورة #{index + 1}"
            )

            return {
                "accepted": True,
                "source": source,
                "path": image_path,
                "is_video": False,
                "montage": evaluation.get(
                    "montage",
                    "NORMAL"
                ),
                "reason": evaluation.get(
                    "reason",
                    ""
                ),
                "candidate": index
            }

        log.warning(
            f"❌ REJECT — {source} "
            f"الصورة #{index + 1}"
        )

        safe_unlink(
            image_path
        )

    log.error(
        f"🚫 لم يتم العثور على صورة حقيقية "
        f"مقبولة من {source}."
    )

    return {
        "accepted": False
    }


# ==================================================================================================
# 8. Groq Whisper فقط
# ==================================================================================================

def groq_transcribe(
    audio_path: Path
) -> List[Dict]:

    if not CONFIG.groq:
        return []

    try:

        with open(
            audio_path,
            "rb"
        ) as f:

            res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={
                    "Authorization":
                    f"Bearer {CONFIG.groq}"
                },
                files={
                    "file": (
                        audio_path.name,
                        f,
                        "audio/mpeg"
                    )
                },
                data={
                    "model": "whisper-large-v3",
                    "response_format": "verbose_json",
                    "timestamp_granularities[]": "word"
                },
                timeout=60
            )

        if res.status_code != 200:

            log.warning(
                f"⚠️ Groq Whisper HTTP {res.status_code}"
            )

            return []

        return res.json().get(
            "words",
            []
        )

    except Exception as e:

        log.warning(
            f"⚠️ خطأ Groq Whisper: {e}"
        )

        return []


# ==================================================================================================
# 9. الترجمة
# ==================================================================================================

def generate_ass(
    words: List[Dict],
    fallback: str,
    dur: float,
    out: Path,
    badge: str
):

    def ft(s):

        return (
            f"{int(s // 3600)}:"
            f"{int((s % 3600) // 60):02d}:"
            f"{s % 60:05.2f}"
        )

    evs = []

    if words:

        ch = []
        st = 0.0

        for i, w in enumerate(
            words
        ):

            if not ch:

                st = float(
                    w.get(
                        "start",
                        0
                    )
                )

            ch.append(
                w.get(
                    "word",
                    ""
                )
            )

            if (
                len(ch) == 5
                or i == len(words) - 1
            ):

                end_time = float(
                    w.get(
                        "end",
                        st + 1
                    )
                )

                evs.append(
                    "Dialogue: 1,"
                    f"{ft(st)},"
                    f"{ft(end_time)},"
                    "Sub,,0,0,0,,"
                    +
                    get_display(
                        reshape(
                            " ".join(ch)
                        )
                    )
                )

                ch = []

    else:

        wl = fallback.split()

        groups = max(
            1,
            (len(wl) + 4) // 5
        )

        cd = dur / groups

        for i in range(
            0,
            len(wl),
            5
        ):

            start = (
                i // 5
            ) * cd

            end = min(
                dur,
                start + cd
            )

            evs.append(
                "Dialogue: 1,"
                f"{ft(start)},"
                f"{ft(end)},"
                "Sub,,0,0,0,,"
                +
                get_display(
                    reshape(
                        " ".join(
                            wl[i:i + 5]
                        )
                    )
                )

    bdg = get_display(
        reshape(
            badge
        )
    )

    ass = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        "PlayResX: 1920\n"
        "PlayResY: 1080\n"
        "[V4+ Styles]\n"
        "Style: Sub,Noto Sans Arabic,110,"
        "&H00FFFFFF,&H000000FF,"
        "&H00000000,&H90000000,"
        "-1,100,100,0,1,4,4,2,80,80,100\n"
        "Style: Bdg,Noto Sans Arabic,35,"
        "&H00FFFFFF,&H000000FF,"
        "&H00101010,&H90000000,"
        "-1,100,100,0,1,2,2,7,60,60,50\n"
        "[Events]\n"
        f"Dialogue: 0,0:00:00.00,{ft(dur)},"
        f"Bdg,,0,0,0,,{bdg}\n"
        +
        "\n".join(evs)
    )

    out.write_text(
        ass,
        encoding="utf-8"
    )


# ==================================================================================================
# 10. معالجة الصوت
# ==================================================================================================

def process_audio(
    voice: Path,
    foley: Path,
    has_foley: bool,
    out: Path
) -> float:

    safe_unlink(
        out
    )

    if has_foley:

        fc = (
            "[0:a]"
            "silenceremove="
            "stop_periods=-1:"
            "stop_duration=0.8:"
            "stop_threshold=-45dB,"
            "loudnorm=I=-16[v];"
            "[1:a]volume=0.04[bg];"
            "[v][bg]amix="
            "inputs=2:"
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
            "-c:a",
            "aac",
            str(out)
        ]

    else:

        fc = (
            "[0:a]"
            "silenceremove="
            "stop_periods=-1:"
            "stop_duration=0.8:"
            "stop_threshold=-45dB,"
            "loudnorm=I=-16[aout]"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(voice),
            "-filter_complex",
            fc,
            "-map",
            "[aout]",
            "-ar",
            "48000",
            "-c:a",
            "aac",
            str(out)
        ]

    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=180,
        check=True
    )

    duration = float(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(out)
            ]
        )
        .decode()
        .strip()
    )

    return duration


# ==================================================================================================
# 11. رندر المشهد
# ==================================================================================================

def render_scene(
    media: Path,
    is_vid: bool,
    ass: Path,
    aud: Path,
    out: Path,
    dur: float,
    montage_hint: str
):

    safe_unlink(
        out
    )

    fps = 24

    color_fx = (
        ",hue=s=0"
        if "BW" in montage_hint
        else
        ",eq=contrast=1.12:saturation=0.85"
    )

    if is_vid:

        fc = (
            "[0:v]"
            "scale=1920:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1920:1080"
            f"{color_fx},"
            "vignette=PI/3.6,"
            f"subtitles='{ass}',"
            f"fps={fps}"
            "[v]"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-stream_loop",
            "-1",
            "-i",
            str(media),
            "-i",
            str(aud),
            "-filter_complex",
            fc,
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out)
        ]

    else:

        if "PAN_RIGHT" in montage_hint:

            motion = (
                "z=1.1:"
                "x='min(iw-iw/zoom,x+1)':"
                "y='ih/2-(ih/zoom/2)'"
            )

        elif "NORMAL" in montage_hint:

            motion = (
                "z=1:"
                "x='iw/2-(iw/zoom/2)':"
                "y='ih/2-(ih/zoom/2)'"
            )

        else:

            motion = (
                "z='min(1.15,1.05+0.0003*on)':"
                "x='iw/2-(iw/zoom/2)':"
                "y='ih/2-(ih/zoom/2)'"
            )

        fc = (
            "[0:v]"
            "scale=1920:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            f"zoompan={motion}:"
            f"d={int(max(1, dur) * fps)}:"
            "s=1920x1080:"
            "fps=24"
            f"{color_fx},"
            "vignette=PI/3.6,"
            f"subtitles='{ass}'"
            "[v]"
        )

        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(media),
            "-i",
            str(aud),
            "-filter_complex",
            fc,
            "-map",
            "[v]",
            "-map",
            "1:a",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(out)
        ]

    try:

        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=300,
            check=True
        )

    except Exception as e:

        log.error(
            f"❌ فشل رندر المشهد: {e}"
        )


# ==================================================================================================
# 12. Google OAuth
# ==================================================================================================

def create_google_credentials(
    refresh_token: str
):

    if not (
        CONFIG.google_client_id
        and CONFIG.google_client_secret
        and refresh_token
    ):

        return None

    try:

        return Credentials(
            None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CONFIG.google_client_id,
            client_secret=CONFIG.google_client_secret
        )

    except Exception as e:

        log.error(
            f"❌ تعذر إنشاء Google Credentials: {e}"
        )

        return None


# ==================================================================================================
# 13. Google Drive
# ==================================================================================================

def upload_drive(
    vid: Path
) -> Dict:

    if not CONFIG.drive_token:

        log.info(
            "ℹ️ DRIVE_REFRESH_TOKEN غير موجود، تم تخطي Drive."
        )

        return {
            "uploaded": False,
            "id": None,
            "error": "DRIVE_REFRESH_TOKEN missing"
        }

    if not (
        CONFIG.google_client_id
        and CONFIG.google_client_secret
    ):

        log.warning(
            "⚠️ GOOGLE_CLIENT_ID/SECRET غير موجودين، تم تخطي Drive."
        )

        return {
            "uploaded": False,
            "id": None,
            "error": "Google OAuth credentials missing"
        }

    log.info(
        f"☁️ رفع {vid.name} إلى Google Drive..."
    )

    try:

        credentials = create_google_credentials(
            CONFIG.drive_token
        )

        if not credentials:

            return {
                "uploaded": False,
                "id": None,
                "error": "credentials creation failed"
            }

        dr = build(
            "drive",
            "v3",
            credentials=credentials
        )

        res = dr.files().list(
            q=(
                "name='Broadcast_Vault' "
                "and mimeType='application/vnd.google-apps.folder' "
                "and trashed=false"
            ),
            fields="files(id,name)",
            pageSize=10
        ).execute()

        if res.get("files"):

            fid = res["files"][0]["id"]

        else:

            fid = dr.files().create(
                body={
                    "name": "Broadcast_Vault",
                    "mimeType":
                    "application/vnd.google-apps.folder"
                },
                fields="id"
            ).execute()["id"]

        metadata = {
            "name": vid.name,
            "parents": [fid]
        }

        media = MediaFileUpload(
            str(vid),
            mimetype="video/mp4",
            resumable=True,
            chunksize=5 * 1024 * 1024
        )

        req = dr.files().create(
            body=metadata,
            media_body=media,
            fields="id,name,webViewLink"
        )

        response = None

        while response is None:

            status, response = req.next_chunk()

            if status:

                log.info(
                    f"☁️ Drive: {int(status.progress() * 100)}%"
                )

        file_id = response.get(
            "id"
        )

        log.info(
            f"✅ تم رفع النسخة إلى Drive: {file_id}"
        )

        return {
            "uploaded": True,
            "id": file_id,
            "link": response.get("webViewLink")
        }

    except Exception as e:

        log.error(
            f"❌ فشل Drive: {e}"
        )

        return {
            "uploaded": False,
            "id": None,
            "error": str(e)
        }


# ==================================================================================================
# 14. YouTube
# ==================================================================================================

def upload_youtube(
    vid: Path,
    round_number: int,
    status: str,
    review: Dict
) -> Dict:

    if not CONFIG.yt_refresh:

        log.info(
            "ℹ️ YOUTUBE_REFRESH_TOKEN غير موجود، تم تخطي YouTube."
        )

        return {
            "uploaded": False,
            "id": None,
            "error": "YOUTUBE_REFRESH_TOKEN missing"
        }

    if not (
        CONFIG.google_client_id
        and CONFIG.google_client_secret
    ):

        log.warning(
            "⚠️ GOOGLE_CLIENT_ID/SECRET غير موجودين، تم تخطي YouTube."
        )

        return {
            "uploaded": False,
            "id": None,
            "error": "Google OAuth credentials missing"
        }

    log.info(
        f"▶️ رفع {vid.name} إلى YouTube..."
    )

    try:

        credentials = create_google_credentials(
            CONFIG.yt_refresh
        )

        if not credentials:

            return {
                "uploaded": False,
                "id": None,
                "error": "credentials creation failed"
            }

        youtube = build(
            "youtube",
            "v3",
            credentials=credentials
        )

        topic_title = re.sub(
            r"\s+",
            " ",
            CONFIG.topic
        ).strip()

        title = (
            f"{topic_title} | "
            f"V{round_number:02d} | "
            f"{status}"
        )

        # YouTube title max = 100 characters.
        title = title[:100]

        reason = str(
            review.get(
                "reason",
                ""
            )
        )

        description = (
            f"وثائقي تحقيقي آلي.\n\n"
            f"الموضوع: {CONFIG.topic}\n"
            f"الإصدار: V{round_number:02d}\n"
            f"الحالة: {status}\n\n"
            f"نتيجة المراجعة النهائية:\n"
            f"{reason}\n\n"
            f"هذه النسخة محفوظة كإصدار مستقل للمقارنة "
            f"مع الإصدارات السابقة واللاحقة."
        )

        body = {
            "snippet": {
                "title": title,
                "description": description,
                "categoryId": "22"
            },
            "status": {
                "privacyStatus": CONFIG.youtube_privacy,
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(
            str(vid),
            mimetype="video/mp4",
            resumable=True,
            chunksize=8 * 1024 * 1024
        )

        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None

        while response is None:

            upload_status, response = request.next_chunk()

            if upload_status:

                log.info(
                    f"▶️ YouTube: "
                    f"{int(upload_status.progress() * 100)}%"
                )

        video_id = response.get(
            "id"
        )

        log.info(
            f"✅ تم رفع النسخة إلى YouTube: {video_id}"
        )

        return {
            "uploaded": True,
            "id": video_id,
            "url": (
                f"https://www.youtube.com/watch?v={video_id}"
                if video_id
                else None
            ),
            "privacy": CONFIG.youtube_privacy
        }

    except Exception as e:

        log.error(
            f"❌ فشل YouTube: {e}"
        )

        return {
            "uploaded": False,
            "id": None,
            "error": str(e)
        }


# ==================================================================================================
# 15. حفظ مراجعة النسخة
# ==================================================================================================

def save_version_review(
    review: Dict,
    round_number: int,
    version_path: Path,
    drive_result: Dict,
    youtube_result: Dict
) -> Path:

    enriched = dict(
        review
    )

    enriched["version"] = (
        round_number
    )

    enriched["version_file"] = (
        version_path.name
    )

    enriched["drive"] = drive_result

    enriched["youtube"] = youtube_result

    review_path = (
        CONFIG.paths.base
        / f"final_review_V{round_number:02d}.json"
    )

    review_path.write_text(
        json.dumps(
            enriched,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # Latest review أيضاً.
    CONFIG.paths.final_review.write_text(
        json.dumps(
            enriched,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    return review_path


# ==================================================================================================
# 16. سجل جميع الإصدارات
# ==================================================================================================

def update_versions_manifest(
    round_number: int,
    status: str,
    version_path: Path,
    drive_result: Dict,
    youtube_result: Dict
):

    versions_file = (
        CONFIG.paths.base
        / "versions_manifest.json"
    )

    try:

        if versions_file.exists():

            data = json.loads(
                versions_file.read_text(
                    encoding="utf-8"
                )
            )

        else:

            data = {
                "topic": CONFIG.topic,
                "created_at": datetime.now().isoformat(),
                "versions": []
            }

        data.setdefault(
            "versions",
            []
        )

        # لا نضيف نفس رقم النسخة مرتين.
        data["versions"] = [
            v for v in data["versions"]
            if v.get("version") != round_number
        ]

        data["versions"].append(
            {
                "version": round_number,
                "status": status,
                "file": version_path.name,
                "drive": drive_result,
                "youtube": youtube_result,
                "timestamp": datetime.now().isoformat()
            }
        )

        data["versions"].sort(
            key=lambda x:
            x.get("version", 0)
        )

        versions_file.write_text(
            json.dumps(
                data,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

    except Exception as e:

        log.warning(
            f"⚠️ تعذر تحديث versions_manifest.json: {e}"
        )


# ==================================================================================================
# 17. تنظيف Cache بعد إصلاح pipeline
# ==================================================================================================

def clear_render_cache_for_rebuild():

    log.info(
        "♻️ تنظيف ملفات رندر المشاهد لإعادة الإنتاج..."
    )

    # ----------------------------------------------------------------------------------------------
    # نحذف فقط Cache المشاهد.
    # لا نلمس output_build/*.mp4
    # وبالتالي لا يتم حذف أي إصدار نهائي سابق.
    # ----------------------------------------------------------------------------------------------

    for path in CONFIG.paths.cache.glob(
        "s_*.mp4"
    ):

        safe_unlink(
            path
        )

    for path in CONFIG.paths.cache.glob(
        "s_*_source.mp4"
    ):

        safe_unlink(
            path
        )

    for path in CONFIG.paths.cache.glob(
        "s_*_source.jpg"
    ):

        safe_unlink(
            path
        )

    for path in CONFIG.paths.cache.glob(
        "s_*_accepted.json"
    ):

        safe_unlink(
            path
        )

    for path in CONFIG.paths.cache.glob(
        "s_*_vision_review.jpg"
    ):

        safe_unlink(
            path
        )

    for path in CONFIG.paths.cache.glob(
        "s_*_frame_*.jpg"
    ):

        safe_unlink(
            path
        )

    log.info(
        "✅ تم تنظيف Cache الرندر فقط. الإصدارات السابقة محفوظة."
    )


# ==================================================================================================
# 18. إعادة التشغيل
# ==================================================================================================

def restart_pipeline(
    review_round: int
):

    log.warning(
        "🔄 إعادة تشغيل الـpipeline بالكود الجديد..."
    )

    env = os.environ.copy()

    env["MASTER_START_TS"] = str(
        MASTER_START_TS
    )

    env["FINAL_REVIEW_ROUND"] = str(
        review_round
    )

    os.execvpe(
        sys.executable,
        [
            sys.executable,
            str(CURRENT_PIPELINE)
        ],
        env
    )


# ==================================================================================================
# 19. الدمج النهائي
# ==================================================================================================

def concat_clips(
    clips: List[Path],
    round_number: int
) -> Path:

    txt_list = (
        CONFIG.paths.base
        / f"list_{round_number}.txt"
    )

    lines = []

    for clip in clips:

        if valid_file(
            clip,
            50000
        ):

            lines.append(
                f"file '{clip.resolve().as_posix()}'"
            )

    txt_list.write_text(
        "\n".join(lines),
        encoding="utf-8"
    )

    final_vid = (
        CONFIG.paths.base
        / f"MasterDoc_review_{round_number}.mp4"
    )

    safe_unlink(
        final_vid
    )

    if not lines:

        return final_vid

    try:

        subprocess.run(
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
                str(final_vid)
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=900,
            check=True
        )

    except Exception as e:

        log.error(
            f"❌ فشل دمج الفيديو: {e}"
        )

    return final_vid


# ==================================================================================================
# 20. أرشفة نسخة الفيديو بعد المراجعة
# ==================================================================================================

def archive_reviewed_video(
    source_video: Path,
    round_number: int,
    status: str
) -> Path:

    filename = version_filename(
        round_number,
        status
    )

    destination = (
        CONFIG.paths.base
        / filename
    )

    # لا نحذف نسخة قديمة بنفس الاسم.
    # في الحالة الطبيعية لن يحدث ذلك، لكن إذا حدث نضيف timestamp.
    if destination.exists():

        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )

        destination = (
            CONFIG.paths.base
            / (
                f"{safe_topic_slug(CONFIG.topic)}_"
                f"V{round_number:02d}_"
                f"{status}_"
                f"{timestamp}.mp4"
            )
        )

    source_video.replace(
        destination
    )

    return destination


# ==================================================================================================
# 21. رفع نسخة كاملة
# ==================================================================================================

def publish_version(
    final_vid: Path,
    round_number: int,
    status: str,
    review: Dict
) -> Path:

    log.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    log.info(
        f"📦 حفظ النسخة V{round_number:02d} "
        f"بحالة {status}"
    )

    version_path = archive_reviewed_video(
        final_vid,
        round_number,
        status
    )

    log.info(
        f"💾 النسخة المحلية: {version_path}"
    )

    # ----------------------------------------------------------------------------------------------
    # Drive
    # ----------------------------------------------------------------------------------------------

    drive_result = upload_drive(
        version_path
    )

    # ----------------------------------------------------------------------------------------------
    # YouTube
    # ----------------------------------------------------------------------------------------------

    youtube_result = upload_youtube(
        version_path,
        round_number,
        status,
        review
    )

    # ----------------------------------------------------------------------------------------------
    # حفظ سجل المراجعة
    # ----------------------------------------------------------------------------------------------

    review_path = save_version_review(
        review,
        round_number,
        version_path,
        drive_result,
        youtube_result
    )

    # ----------------------------------------------------------------------------------------------
    # تحديث سجل جميع النسخ
    # ----------------------------------------------------------------------------------------------

    update_versions_manifest(
        round_number,
        status,
        version_path,
        drive_result,
        youtube_result
    )

    log.info(
        f"📋 تم حفظ مراجعة النسخة: {review_path.name}"
    )

    if drive_result.get(
        "uploaded"
    ):

        log.info(
            "☁️ Drive: SUCCESS"
        )

    else:

        log.warning(
            "☁️ Drive: FAILED/SKIPPED"
        )

    if youtube_result.get(
        "uploaded"
    ):

        log.info(
            "▶️ YouTube: SUCCESS"
        )

    else:

        log.warning(
            "▶️ YouTube: FAILED/SKIPPED"
        )

    log.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    return version_path


# ==================================================================================================
# 22. وحدة التحكم المركزية
# ==================================================================================================

def main():

    log.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    log.info(
        "▶ UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE V23"
    )

    log.info(
        "👁️ Real Media Only / Antigravity Vision Scout"
    )

    log.info(
        f"🎯 القضية: {CONFIG.topic}"
    )

    log.info(
        f"🔄 جولة المراجعة الحالية: {FINAL_REVIEW_ROUND}"
    )

    log.info(
        f"▶️ YouTube privacy: {CONFIG.youtube_privacy}"
    )

    log.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    director = Hybrid_Director()
    fetcher = MediaFetcher()

    script = director.plan_documentary()

    clips = []

    # ==============================================================================================
    # إنتاج جميع المشاهد
    # ==============================================================================================

    for i, s in enumerate(
        script
    ):

        if runtime_expired():

            log.warning(
                "⏳ تم بلوغ حد الجلسة."
            )

            break

        typ = str(
            s.get(
                "media_type",
                "WIKIPEDIA"
            )
        ).upper()

        q = str(
            s.get(
                "search_query",
                ""
            )
        )

        foley = str(
            s.get(
                "foley_type",
                "none"
            )
        )

        txt = str(
            s.get(
                "narration",
                ""
            )
        )

        narration_hash = sha256_text(
            txt
        )

        c_mp4 = (
            CONFIG.paths.cache
            / f"s_{i:03d}.mp4"
        )

        c_source_mp4 = (
            CONFIG.paths.cache
            / f"s_{i:03d}_source.mp4"
        )

        c_source_jpg = (
            CONFIG.paths.cache
            / f"s_{i:03d}_source.jpg"
        )

        c_wav = (
            CONFIG.paths.cache
            / f"s_{i:03d}.wav"
        )

        c_foley = (
            CONFIG.paths.cache
            / f"s_{i:03d}_foley.mp3"
        )

        c_mp3 = (
            CONFIG.paths.cache
            / f"s_{i:03d}.mp3"
        )

        c_ass = (
            CONFIG.paths.cache
            / f"s_{i:03d}.ass"
        )

        accepted_marker = (
            CONFIG.paths.cache
            / f"s_{i:03d}_accepted.json"
        )

        voice_marker = (
            CONFIG.paths.cache
            / f"s_{i:03d}_voice.json"
        )

        # ==========================================================================================
        # Cache للمشهد المقبول
        # ==========================================================================================

        if (
            valid_file(
                c_mp4,
                50000
            )
            and accepted_marker.exists()
        ):

            try:

                marker = json.loads(
                    accepted_marker.read_text(
                        encoding="utf-8"
                    )
                )

                marker_hash = marker.get(
                    "narration_hash"
                )

                if (
                    marker.get(
                        "accepted",
                        False
                    )
                    and marker_hash == narration_hash
                ):

                    clips.append(
                        c_mp4
                    )

                    log.info(
                        f"♻️ المشهد {i + 1} موجود ومقبول "
                        f"بنفس narration hash — تخطي."
                    )

                    continue

                log.warning(
                    f"⚠️ Cache المشهد {i + 1} قديم أو narration تغيّر."
                )

            except Exception:

                log.warning(
                    f"⚠️ Marker المشهد {i + 1} غير صالح."
                )

        if c_mp4.exists():

            log.warning(
                f"⚠️ المشهد {i + 1} موجود بدون Cache صالح — سيتم إنتاجه من جديد."
            )

            safe_unlink(
                c_mp4
            )

        log.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        log.info(
            f"🎬 المشهد {i + 1}/{len(script)}"
        )

        log.info(
            f"🔍 Query: {q}"
        )

        log.info(
            f"📝 المصدر المطلوب في السيناريو: {typ}"
        )

        # ==========================================================================================
        # الصوت مع Cache مرتبط بالنص
        # ==========================================================================================

        voice_cache_valid = False

        if (
            valid_file(
                c_wav,
                1000
            )
            and voice_marker.exists()
        ):

            try:

                vm = json.loads(
                    voice_marker.read_text(
                        encoding="utf-8"
                    )
                )

                voice_cache_valid = (
                    vm.get(
                        "narration_hash"
                    ) == narration_hash
                    and vm.get(
                        "model"
                    ) == "gemini-3.8-flash-tts"
                    and vm.get(
                        "voice"
                    ) == "Charon"
                )

            except Exception:

                voice_cache_valid = False

        if not voice_cache_valid:

            if c_wav.exists():

                log.info(
                    "♻️ حذف TTS Cache لأن narration تغيّر."
                )

                safe_unlink(
                    c_wav
                )

            log.info(
                "🎙️ توليد الصوت..."
            )

            generated = director.generate_voice(
                txt,
                c_wav
            )

            if generated and valid_file(
                c_wav,
                1000
            ):

                voice_marker.write_text(
                    json.dumps(
                        {
                            "narration_hash": narration_hash,
                            "model": "gemini-3.8-flash-tts",
                            "voice": "Charon",
                            "created_at": datetime.now().isoformat()
                        },
                        ensure_ascii=False,
                        indent=2
                    ),
                    encoding="utf-8"
                )

        if not valid_file(
            c_wav,
            1000
        ):

            log.error(
                f"❌ لم يتم إنتاج الصوت للمشهد {i + 1}."
            )

            continue

        # ==========================================================================================
        # Foley
        # ==========================================================================================

        has_foley = False

        if not valid_file(
            c_foley,
            1000
        ):

            has_foley = (
                fetcher.get_freesound_foley(
                    foley,
                    c_foley
                )
            )

        else:

            has_foley = True

        # ==========================================================================================
        # معالجة الصوت
        # ==========================================================================================

        try:

            dur = process_audio(
                c_wav,
                c_foley,
                has_foley,
                c_mp3
            )

        except Exception as e:

            log.error(
                f"❌ فشل معالجة الصوت: {e}"
            )

            continue

        # ==========================================================================================
        # Whisper
        # ==========================================================================================

        words = groq_transcribe(
            c_mp3
        )

        # ==========================================================================================
        # البحث الحقيقي عن الوسيط
        # ==========================================================================================

        accepted_media = find_accepted_media(
            director=director,
            fetcher=fetcher,
            source_type=typ,
            query=q,
            narration=txt,
            video_path=c_source_mp4,
            image_path=c_source_jpg
        )

        # ==========================================================================================
        # لا يوجد fallback إطلاقاً
        # ==========================================================================================

        if not accepted_media.get(
            "accepted",
            False
        ):

            log.error(
                "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            log.error(
                f"🚫 فشل المشهد {i + 1}: "
                "لم نجد لقطة حقيقية مناسبة."
            )

            log.error(
                "🚫 لن يتم إدخال بطاقة احتياطية."
            )

            log.error(
                "🚫 لن يتم إدخال صورة وهمية."
            )

            log.error(
                "🚫 لن يتم إدخال placeholder."
            )

            log.error(
                "➡️ سيتم تجاوز المشهد بدلاً من تخريب الفيلم."
            )

            safe_unlink(
                c_source_mp4
            )

            safe_unlink(
                c_source_jpg
            )

            continue

        # ==========================================================================================
        # لدينا لقطة حقيقية مقبولة
        # ==========================================================================================

        c_media = accepted_media[
            "path"
        ]

        is_vid = accepted_media[
            "is_video"
        ]

        accepted_source = accepted_media[
            "source"
        ]

        montage_style = accepted_media.get(
            "montage",
            "NORMAL"
        )

        candidate = accepted_media.get(
            "candidate",
            0
        )

        log.info(
            "🏆 تم العثور على لقطة حقيقية مناسبة."
        )

        log.info(
            f"📦 المصدر: {accepted_source}"
        )

        log.info(
            f"🎯 رقم المرشح: {candidate + 1}"
        )

        log.info(
            f"🎬 المونتاج: {montage_style}"
        )

        # ==========================================================================================
        # الترجمة
        # ==========================================================================================

        badges = {
            "PEXELS": "لقطات سينمائية",
            "PIXABAY": "أرشيف عام",
            "MAPBOX": "إحداثيات جغرافية",
            "WIKIPEDIA": "سجلات أرشيفية"
        }

        generate_ass(
            words,
            txt,
            dur,
            c_ass,
            f"● {badges.get(accepted_source, 'أرشيف')} | {q}"
        )

        # ==========================================================================================
        # الرندر
        # ==========================================================================================

        render_scene(
            media=c_media,
            is_vid=is_vid,
            ass=c_ass,
            aud=c_mp3,
            out=c_mp4,
            dur=dur,
            montage_hint=montage_style
        )

        # ==========================================================================================
        # التحقق من الناتج
        # ==========================================================================================

        if not valid_file(
            c_mp4,
            50000
        ):

            log.error(
                f"❌ فشل رندر المشهد {i + 1}."
            )

            safe_unlink(
                c_mp4
            )

            continue

        # ==========================================================================================
        # Marker
        # ==========================================================================================

        marker = {
            "accepted": True,
            "scene": i + 1,
            "source": accepted_source,
            "candidate": candidate,
            "montage": montage_style,
            "query": q,
            "narration_hash": narration_hash,
            "accepted_at": datetime.now().isoformat()
        }

        accepted_marker.write_text(
            json.dumps(
                marker,
                ensure_ascii=False,
                indent=2
            ),
            encoding="utf-8"
        )

        clips.append(
            c_mp4
        )

        log.info(
            f"✅ تم رندر المشهد {i + 1} وقبوله."
        )

    # ==============================================================================================
    # لا توجد مشاهد
    # ==============================================================================================

    if not clips:

        log.error(
            "🛑 لم يتم إنتاج أي مشهد صالح."
        )

        append_memory(
            "فشل الإنتاج لأن النظام لم يجد وسائط حقيقية مناسبة."
        )

        return

    # ==============================================================================================
    # الدمج
    # ==============================================================================================

    review_round = (
        FINAL_REVIEW_ROUND + 1
    )

    final_vid = concat_clips(
        clips,
        review_round
    )

    if not valid_file(
        final_vid,
        50000
    ):

        log.error(
            "❌ لم يتم إنشاء MP4 نهائي صالح."
        )

        return

    log.info(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    log.info(
        f"🎞️ تم إنتاج MP4 النهائي لجولة {review_round}."
    )

    # ==============================================================================================
    # المراجعة النهائية
    # ==============================================================================================

    review = director.final_video_review(
        final_vid
    )

    decision = review.get(
        "decision",
        "REJECT"
    )

    if decision == "ACCEPT":

        log.info(
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        log.info(
            "🏆 GEMINI 3.1 PRO: ACCEPT"
        )

        log.info(
            "🎬 النسخة النهائية اجتازت المراجعة."
        )

        # ------------------------------------------------------------------------------------------
        # مهم:
        # الرفع يحدث قبل إنهاء الجلسة.
        # ------------------------------------------------------------------------------------------

        version_path = publish_version(
            final_vid,
            review_round,
            "ACCEPTED",
            review
        )

        append_memory(
            f"تم إنتاج النسخة V{review_round:02d} "
            f"واجتازت مراجعة Gemini 3.1 Pro. "
            f"الملف: {version_path.name}"
        )

        log.info(
            "✔ اكتملت الجلسة بنجاح."
        )

        log.info(
            f"⏱ الوقت الإجمالي: "
            f"{time.time() - MASTER_START_TS:.1f} ثانية"
        )

        return

    # ==============================================================================================
    # REJECT
    # ==============================================================================================

    log.warning(
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    log.warning(
        "❌ GEMINI 3.1 PRO: REJECT"
    )

    log.warning(
        f"السبب: {review.get('reason', '')}"
    )

    issues = review.get(
        "issues",
        []
    )

    log.warning(
        f"عدد المشاكل المكتشفة: {len(issues)}"
    )

    # ==============================================================================================
    # مهم جداً:
    #
    # نرفع النسخة المرفوضة أولاً.
    # لا ننتظر الإصلاح.
    # لا نحذفها.
    # ==============================================================================================

    version_path = publish_version(
        final_vid,
        review_round,
        "REJECTED",
        review
    )

    log.warning(
        f"📦 تم الاحتفاظ بالنسخة المرفوضة: {version_path.name}"
    )

    # ==============================================================================================
    # الحد الأقصى
    # ==============================================================================================

    MAX_FINAL_REPAIRS = 3

    if review_round >= MAX_FINAL_REPAIRS:

        log.error(
            "🛑 تم الوصول إلى الحد الأقصى لجولات "
            "المراجعة والإصلاح."
        )

        log.error(
            "📦 النسخة REJECTED محفوظة محلياً وفي Drive/YouTube."
        )

        append_memory(
            f"انتهت جلسات الإصلاح عند الجولة "
            f"{review_round} دون ACCEPT. "
            f"تم الاحتفاظ بالنسخة {version_path.name}."
        )

        return

    # ==============================================================================================
    # إصلاح الكود
    # ==============================================================================================

    repaired = director.apply_final_repairs(
        review
    )

    if not repaired:

        log.error(
            "❌ لم ينجح الإصلاح الذاتي."
        )

        log.error(
            "📦 النسخة REJECTED السابقة محفوظة."
        )

        append_memory(
            f"تم رفض النسخة V{review_round:02d}، "
            "ثم فشل الإصلاح الذاتي. النسخة محفوظة."
        )

        return

    # ==============================================================================================
    # إعادة الإنتاج
    # ==============================================================================================

    clear_render_cache_for_rebuild()

    append_memory(
        f"Gemini 3.1 Pro رفض النسخة V{review_round:02d} "
        f"وتم تعديل pipeline لإعادة الإنتاج. "
        f"النسخة السابقة محفوظة للمقارنة."
    )

    restart_pipeline(
        review_round
    )


# ==================================================================================================
# 23. التشغيل
# ==================================================================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        log.warning(
            "⛔ تم إيقاف الإنتاج يدوياً."
        )

    except Exception as e:

        log.critical(
            f"💥 خطأ غير متوقع: {e}",
            exc_info=True
        )

        append_memory(
            f"حدث خطأ غير متوقع: {e}"
        )
