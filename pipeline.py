#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
====================================================================================================
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
HYBRID V22.14 - API FIXED / DEBUGGED / EXTENDED TIMEOUT
====================================================================================================

الإصلاحات في هذه النسخة:

1. إصلاح جميع روابط API التي كانت تحتوي على Markdown بالخطأ:
   [https://...](https://...)

2. إصلاح:
   - Pexels
   - Pixabay
   - Wikipedia
   - Internet Archive
   - Freesound
   - Google OAuth

3. إضافة timeout لجميع طلبات HTTP.

4. إضافة raise_for_status() لكشف أخطاء:
   401 / 403 / 404 / 429 / 500 وغيرها.

5. عدم ابتلاع أخطاء MediaFetcher بصمت.

6. تسجيل حالة API والـHTTP status في production_logs.txt.

7. إصلاح التعامل مع query باستخدام params بدل تركيب URL يدويًا قدر الإمكان.

8. منع حلقة البحث عن المشهد من الدوران إلى الأبد.

9. الاحتفاظ بتبريد توليد الصوت 30 ثانية كما هو.

10. الاحتفاظ بـ Antigravity SDK للمراجعة البصرية.

11. الاحتفاظ بـ agy CLI لتوليد السيناريو.

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
from pathlib import Path
from typing import List, Dict
from datetime import datetime

import requests
from PIL import Image as PILImage, ImageDraw
import arabic_reshaper
from bidi.algorithm import get_display

# الصوت فقط - Gemini API
from google import genai
from google.genai import types

# Google Drive / YouTube
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Antigravity
import google.antigravity as ag
from google.antigravity import Agent, LocalAgentConfig


# ==================================================================================================
# 1. إعدادات النظام وتوثيق السجلات
# ==================================================================================================

class ProTelemetryFormatter(logging.Formatter):

    COLORS = {
        'INFO': "\x1b[38;5;39m",
        'WARNING': "\x1b[38;5;214m",
        'ERROR': "\x1b[38;5;196m"
    }

    RESET = "\x1b[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)

        return logging.Formatter(
            f"{color}%(asctime)s | [%(levelname)s] | %(message)s{self.RESET}",
            datefmt="%H:%M:%S"
        ).format(record)


def setup_logger() -> logging.Logger:

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

    return logger


log = setup_logger()

MEMORY_FILE = Path("director_memory.md")


def append_memory(summary: str):

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(
            f"\n\n### [{now}]\n{summary}"
        )


# ==================================================================================================
# 2. مستكشف وسائط Antigravity
# ==================================================================================================

def load_ag_media(file_path: Path):

    ext = file_path.suffix.lower()

    path_str = str(file_path.resolve())

    # الفيديو
    if ext in [".mp4", ".mov", ".webm", ".avi"]:

        if hasattr(ag, "Video"):
            return getattr(ag, "Video").from_file(path_str)

        if hasattr(ag, "media") and hasattr(ag.media, "Video"):
            return getattr(ag.media, "Video").from_file(path_str)

        if hasattr(ag, "from_file"):
            return getattr(ag, "from_file")(path_str)

    # الصور
    else:

        if hasattr(ag, "Image"):
            return getattr(ag, "Image").from_file(path_str)

        if hasattr(ag, "media") and hasattr(ag.media, "Image"):
            return getattr(ag.media, "Image").from_file(path_str)

        if hasattr(ag, "from_file"):
            return getattr(ag, "from_file")(path_str)

    raise RuntimeError(
        "لم يتم العثور على فئة الوسائط المناسبة داخل google.antigravity"
    )


# ==================================================================================================
# 3. فلتر البحث الإنجليزي
# ==================================================================================================

def enforce_english_query(query: str) -> str:

    if not query:
        return "mystery evidence"

    safe_q = re.sub(
        r'[\u0600-\u06FF]',
        '',
        str(query)
    ).strip()

    safe_q = re.sub(
        r'\s+',
        ' ',
        safe_q
    )

    if not safe_q or len(safe_q) < 2:
        safe_q = "mystery evidence"

    return safe_q


# ==================================================================================================
# 4. المسارات والمفاتيح
# ==================================================================================================

class HybridConfig:

    topic = os.environ.get(
        "VIDEO_TOPIC",
        "لغز الجريمة الغامضة"
    )

    paths = type(
        'Paths',
        (),
        {
            'base': Path("./output_build"),
            'cache': Path("./output_build/cache"),
            'manifest': Path("./output_build/master_manifest.json")
        }
    )()

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
        ""
    )


CONFIG = HybridConfig()

CONFIG.paths.base.mkdir(
    parents=True,
    exist_ok=True
)

CONFIG.paths.cache.mkdir(
    parents=True,
    exist_ok=True
)


# ==================================================================================================
# 5. العقل المدبر
# ==================================================================================================

class Hybrid_Director:

    # ----------------------------------------------------------------------------------------------
    # توليد السيناريو
    # ----------------------------------------------------------------------------------------------

    def plan_documentary(self) -> List[Dict]:

        if CONFIG.paths.manifest.exists():

            try:

                existing = json.loads(
                    CONFIG.paths.manifest.read_text(
                        encoding="utf-8"
                    )
                )

                if isinstance(existing, list) and existing:

                    log.info(
                        f"📋 تم العثور على سيناريو محفوظ يحتوي على {len(existing)} مشهد."
                    )

                    return existing

            except Exception as e:

                log.warning(
                    f"⚠️ تعذر قراءة manifest القديم: {e}"
                )

        log.info(
            f"🧠 كتابة السيناريو عبر agy / gemini-3.1-pro | القضية: {CONFIG.topic}"
        )

        prompt = f"""
أنت كبير المخرجين ومهندس أفلام وثائقية تحقيقية.

القضية:
"{CONFIG.topic}"

قم ببناء سيناريو وثائقي ضخم من 40 إلى 50 مشهداً.

لكل مشهد:

- scene_num
- media_type
- search_query
- foley_type
- narration

شروط صارمة:

1. narration باللغة العربية الفصحى.
2. search_query باللغة الإنجليزية حصراً.
3. search_query يجب أن يصف شيئاً يمكن العثور عليه فعلياً في:
   PEXELS
   PIXABAY
   WIKIPEDIA
   INTERNET ARCHIVE

4. لا تستخدم كلمات عربية داخل search_query.

5. لا تستخدم Markdown.

6. أخرج JSON Array فقط.

الشكل:

[
  {{
    "scene_num": 1,
    "media_type": "PEXELS",
    "search_query": "dark empty street at night",
    "foley_type": "rain",
    "narration": "في ليلة..."
  }}
]
"""

        for attempt in range(3):

            try:

                log.info(
                    f"🧠 محاولة توليد السيناريو {attempt + 1}/3..."
                )

                cmd = [
                    "agy",
                    "--model",
                    "gemini-3.1-pro",
                    "--effort",
                    "high",
                    "--dangerously-skip-permissions",
                    "-p",
                    prompt
                ]

                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=360
                )

                if result.returncode != 0:

                    log.warning(
                        f"⚠️ Agy Error:\n{result.stderr.strip()}"
                    )

                    time.sleep(5)

                    continue

                stdout = result.stdout.strip()

                match = re.search(
                    r'\[.*\]',
                    stdout,
                    re.DOTALL
                )

                if not match:

                    log.warning(
                        "⚠️ لم يتم العثور على JSON Array في خرج agy."
                    )

                    continue

                data = json.loads(
                    match.group(0)
                )

                if not isinstance(data, list) or not data:

                    log.warning(
                        "⚠️ السيناريو الناتج فارغ."
                    )

                    continue

                # تنظيف search_query
                for scene in data:

                    scene["search_query"] = enforce_english_query(
                        scene.get(
                            "search_query",
                            ""
                        )
                    )

                    scene["foley_type"] = enforce_english_query(
                        scene.get(
                            "foley_type",
                            "none"
                        )
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
                    f"✅ تم حفظ سيناريو يحتوي على {len(data)} مشهد."
                )

                return data

            except Exception as e:

                log.warning(
                    f"⚠️ خطأ السيناريو: {type(e).__name__}: {e}"
                )

                time.sleep(5)

        sys.exit(
            "🛑 فشل كتابة السيناريو بعد جميع المحاولات."
        )


    # ----------------------------------------------------------------------------------------------
    # Antigravity - المراجع البصري
    # ----------------------------------------------------------------------------------------------

    async def _async_evaluate_scout(
        self,
        media_path: Path,
        narration: str,
        source: str
    ) -> str:

        config = LocalAgentConfig(
            model="gemini-3.6-flash",
            effort="high"
        )

        agent = Agent(
            config=config
        )

        prompt = f"""
أنت مراجع بصري فوري لمشروع وثائقي تحقيقي.

عنوان المشروع:
"{CONFIG.topic}"

نوع المصدر:
{source}

التعليق الصوتي:
"{narration}"

شاهد الوسيط المرفق بعناية.

قرر هل الوسيط مناسب مباشرة للتعليق الصوتي أم لا.

القواعد:

1. ACCEPT فقط إذا كان المحتوى المرئي مرتبطاً بشكل مباشر وواضح.
2. إذا كان التطابق غير مؤكد اختر REJECT.
3. اشرح السبب بالعربية.
4. إذا رفضت، اقترح search query جديدة باللغة الإنجليزية فقط.
5. لا تخترع معلومات غير ظاهرة في الوسيط.

أخرج JSON فقط:

{{
  "decision": "ACCEPT",
  "score": 0.95,
  "reason": "سبب القرار",
  "montage": "ZOOM_IN",
  "new_query": "English replacement query"
}}

القيم الممكنة لـ montage:

ZOOM_IN
NORMAL
BW
"""

        media_input = load_ag_media(
            media_path
        )

        return await agent.chat(
            [
                prompt,
                media_input
            ]
        )


    def evaluate_scene_with_scout(
        self,
        media_path: Path,
        narration: str,
        source: str
    ) -> Dict:

        log.info(
            f"👁️ Antigravity يفحص الوسيط من {source}..."
        )

        try:

            result_text = asyncio.run(
                self._async_evaluate_scout(
                    media_path,
                    narration,
                    source
                )
            )

            log.info(
                f"🗣️ نتيجة المراجع:\n{result_text}"
            )

            match = re.search(
                r'\{.*\}',
                result_text,
                re.DOTALL
            )

            if not match:

                log.warning(
                    "⚠️ المراجع لم يرجع JSON صالحاً."
                )

                return {
                    "accepted": False,
                    "montage": "ZOOM_IN",
                    "new_query": ""
                }

            data = json.loads(
                match.group(0)
            )

            score = float(
                data.get(
                    "score",
                    0.0
                )
            )

            accepted = (
                data.get("decision") == "ACCEPT"
                and score >= 0.70
            )

            return {
                "accepted": accepted,
                "montage": data.get(
                    "montage",
                    "NORMAL"
                ),
                "new_query": data.get(
                    "new_query",
                    ""
                )
            }

        except Exception as e:

            log.error(
                f"⚠️ انهيار المراجع الفوري: "
                f"{type(e).__name__}: {e}"
            )

            return {
                "accepted": False,
                "montage": "ZOOM_IN",
                "new_query": ""
            }


    # ----------------------------------------------------------------------------------------------
    # المراجعة النهائية
    # ----------------------------------------------------------------------------------------------

    async def _async_critique(
        self,
        final_video: Path,
        logs: str
    ) -> str:

        config = LocalAgentConfig(
            model="gemini-3.1-pro",
            effort="high"
        )

        agent = Agent(
            config=config
        )

        prompt = f"""
أنت المراجع النهائي والمؤسس التقني للفيلم.

إليك آخر سجلات النظام:

{logs}

شاهد الفيلم الوثائقي النهائي المرفق.

تحقق من:

1. تزامن الصوت والصورة.
2. وجود شاشات سوداء أو معطوبة.
3. وجود أخطاء واضحة في FFmpeg.
4. وجود مشاهد ناقصة.
5. وجود مشاكل تقنية واضحة.

إذا كان هناك خلل برمجي يحتاج إلى إصلاح جذري:

اكتب كود pipeline.py جديداً كاملاً داخل:

```python
...
