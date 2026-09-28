#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================================================
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE (HYBRID V21 - Antigravity Vision Scout)

- السيناريو والنقد النهائي: Google Antigravity - Gemini 3.1 Pro High.
- المراجع البصري الفوري: Google Antigravity - Gemini 3.6 Flash High.
- لا يستخدم Groq في تقييم الصور/المشاهد.
- الصوت: Google AI Studio (Charon) + دوران المفاتيح 3 جولات + تبريد 30 ثانية.
- Groq يبقى فقط لـ Whisper لتحديد توقيت الكلمات للترجمة.
- المراجع البصري يرى الصورة الفعلية بنفسه، وليس وصفاً من نموذج آخر.
- إذا كانت اللقطة مرفوضة يتم الانتقال إلى مصدر/نتيجة أخرى.
- الذاكرة وحلقة الكمال: تسجيل الأخطاء، معالجة ذاتية، بحد 3.75 ساعات.
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
from pathlib import Path
from typing import List, Dict
from dataclasses import dataclass, field
from datetime import datetime

import requests
from PIL import Image, ImageDraw
import arabic_reshaper
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
        'INFO': "\x1b[38;5;39m",
        'WARNING': "\x1b[38;5;214m",
        'ERROR': "\x1b[38;5;196m",
        'CRITICAL': "\x1b[48;5;196;38;5;231m\x1b[1m"
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

        fh = logging.FileHandler("production_logs.txt", encoding="utf-8")
        fh.setFormatter(
            logging.Formatter(
                "%(asctime)s | [%(levelname)s] | %(message)s"
            )
        )
        logger.addHandler(fh)

    return logger


log = setup_logger()

MEMORY_FILE = Path("director_memory.md")


def read_memory() -> str:
    if MEMORY_FILE.exists():
        return MEMORY_FILE.read_text(encoding="utf-8")

    return (
        "هذه أول جلسة لك. ركز على إنتاج سيناريو من 40-50 مشهداً "
        "بكلمات طويلة للوصول إلى 20 دقيقة."
    )


def append_memory(session_summary: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n\n### تقرير الجلسة [{now}]\n{session_summary}"

    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(entry)


# ==================================================================================================
# 2. الإعدادات والمسارات
# ==================================================================================================

@dataclass
class PipelinePaths:
    base: Path = field(
        default_factory=lambda: Path("./output_build")
    )

    cache: Path = field(
        default_factory=lambda: Path("./output_build/cache")
    )

    manifest: Path = field(
        default_factory=lambda: Path("./output_build/master_manifest.json")
    )

    def initialize(self):
        for p in [self.base, self.cache]:
            p.mkdir(parents=True, exist_ok=True)


class HybridConfig:

    topic = os.environ.get(
        "VIDEO_TOPIC",
        "لغز اختفاء طائرة دي بي كوبر"
    )

    paths = PipelinePaths()

    gemini_keys = [
        k.strip()
        for k in os.environ.get(
            "GEMINI_API_KEY", ""
        ).split(",")
        if k.strip()
    ]

    pexels = os.environ.get(
        "PEXELS_API_KEY", ""
    )

    pixabay = os.environ.get(
        "PIXABAY_API_KEY", ""
    )

    mapbox = os.environ.get(
        "MAPBOX_API_KEY", ""
    )

    # Groq الآن يستخدم فقط لـ Whisper transcription.
    groq = os.environ.get(
        "GROQ_API_KEY", ""
    )

    freesound = os.environ.get(
        "FREESOUND_API_KEY", ""
    )

    yt_id = os.environ.get(
        "GOOGLE_CLIENT_ID", ""
    )

    yt_secret = os.environ.get(
        "GOOGLE_CLIENT_SECRET", ""
    )

    drive_token = os.environ.get(
        "DRIVE_REFRESH_TOKEN", ""
    )

    yt_refresh = os.environ.get(
        "YOUTUBE_REFRESH_TOKEN", ""
    )


CONFIG = HybridConfig()

CONFIG.paths.initialize()

if not CONFIG.gemini_keys:
    sys.exit(
        "🛑 حرج: مفاتيح GEMINI_API_KEY مفقودة!"
    )


# ==================================================================================================
# 3. العقل الهجين والمراجع البصري عبر Antigravity
# ==================================================================================================

class Hybrid_Director:

    # ----------------------------------------------------------------------------------------------
    # السيناريو
    # ----------------------------------------------------------------------------------------------

    def plan_documentary(self) -> List[Dict]:

        if CONFIG.paths.manifest.exists():
            return json.loads(
                CONFIG.paths.manifest.read_text(
                    encoding="utf-8"
                )
            )

        log.info(
            f"كتابة السيناريو الضخم عبر Antigravity (Pro) | القضية: {CONFIG.topic}"
        )

        prompt = f"""
أنت كبير المخرجين والباحثين في إنتاج وثائقيات التحقيق الجنائي.

موضوعنا:
"{CONFIG.topic}"

قم ببناء سيناريو ضخم جداً من 40 إلى 50 مشهداً.

الهدف:
ضمان مدة تتجاوز 18 دقيقة.

القيود:

1. النص في كل مشهد من 60 إلى 80 كلمة.
2. العربية فصحى مشكولة بدقة.
3. الأدوات:
   PEXELS
   PIXABAY
   MAPBOX
   WIKIPEDIA
4. المؤثر الصوتي foley_type يجب أن يكون باللغة الإنجليزية.
5. search_query يجب أن يكون وصفاً بصرياً دقيقاً وقابلاً للبحث.
6. كل مشهد يجب أن يخدم المعلومات الموجودة في السرد.
7. لا تستخدم لقطات عشوائية لا علاقة لها بالمعلومة.
8. اجعل المشاهد قابلة للتنفيذ بمصادر أرشيفية حقيقية.

[الذاكرة التراكمية]
{read_memory()}

أخرج JSON Array فقط:

[
  {{
    "scene_num": 1,
    "media_type": "PEXELS",
    "search_query": "dark street at night rain cinematic",
    "foley_type": "rain",
    "narration": "فِي لَيْلَةٍ عَاصِفَةٍ..."
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
                    r'\[.*\]',
                    output,
                    re.DOTALL
                )

                if not match:

                    log.warning(
                        "⚠️ Antigravity لم يرجع JSON صالحاً."
                    )

                    log.warning(
                        f"محتوى الرد:\n{output[:500]}..."
                    )

                    time.sleep(5)
                    continue

                clean = match.group(0)

                data = json.loads(clean)

                CONFIG.paths.manifest.write_text(
                    json.dumps(
                        data,
                        ensure_ascii=False,
                        indent=2
                    ),
                    encoding="utf-8"
                )

                return data

            except subprocess.TimeoutExpired:

                log.warning(
                    f"⚠️ انتهى وقت Antigravity "
                    f"(المحاولة {attempt + 1})"
                )

            except Exception as e:

                log.warning(
                    f"⚠️ خطأ أثناء توليد السيناريو: {e}"
                )

                time.sleep(5)

        sys.exit(
            "🛑 فشل Antigravity نهائياً في كتابة السيناريو."
        )

    # ----------------------------------------------------------------------------------------------
    # النقد النهائي
    # ----------------------------------------------------------------------------------------------

    def critique_and_improve(self) -> bool:

        log.info(
            "🧠 بدء جلسة التقييم الذاتي الشاملة..."
        )

        manifest_text = CONFIG.paths.manifest.read_text(
            encoding="utf-8"
        )

        logs_text = ""

        if Path("production_logs.txt").exists():

            logs = Path(
                "production_logs.txt"
            ).read_text(
                encoding="utf-8"
            ).split("\n")

            logs_text = "\n".join(
                [
                    line
                    for line in logs
                    if (
                        "WARNING" in line
                        or "ERROR" in line
                        or "CRITICAL" in line
                    )
                ][-50:]
            )

        if not logs_text.strip():

            log.info(
                "✅ الفيلم مثالي بناءً على السجلات."
            )

            append_memory(
                "تم إنتاج الفيديو بسلاسة بدون أخطاء تقنية."
            )

            return True

        prompt = f"""
أنت المخرج والمراجع النهائي.

حاولنا إنتاج السيناريو التالي:

{manifest_text}

الأخطاء المسجلة:

{logs_text}

حلل الأخطاء.

إذا كانت الأخطاء طفيفة ولا تستدعي تعديلاً:
أخرج فقط:

PERFECT

أما إذا كانت هناك أخطاء تستحق الإصلاح:
أصلح السيناريو وأخرج JSON Array كاملاً بنفس البنية الأصلية.

لا تضف أي نص خارج JSON أو PERFECT.
"""

        try:

            cmd = [
                "agy",
                "--model",
                "gemini-3.1-pro-high",
                "--dangerously-skip-permissions",
                "-p",
                prompt
            ]

            output = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=600
            ).stdout.strip()

            if "PERFECT" in output:

                append_memory(
                    "ظهرت تحذيرات لكن تم تجاوزها لاعتماد المقطع."
                )

                return True

            match = re.search(
                r'\[.*\]',
                output,
                re.DOTALL
            )

            if match:

                CONFIG.paths.manifest.write_text(
                    json.dumps(
                        json.loads(match.group(0)),
                        ensure_ascii=False,
                        indent=2
                    ),
                    encoding="utf-8"
                )

                log.info(
                    "🔄 تم تحديث السيناريو بناءً على النقد!"
                )

                append_memory(
                    "تم إصلاح أخطاء بصرية/برمجية "
                    "وتحديث السيناريو بنجاح."
                )

                Path(
                    "production_logs.txt"
                ).write_text(
                    "",
                    encoding="utf-8"
                )

                return False

            return True

        except Exception as e:

            log.warning(
                f"⚠️ فشل التقييم، سيتم الاعتماد "
                f"على النسخة الحالية: {e}"
            )

            return True

    # ----------------------------------------------------------------------------------------------
    # توليد الصوت
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

                    # لا نلمس فترة التبريد.
                    time.sleep(30)

                    return

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

    # ----------------------------------------------------------------------------------------------
    # المراجع البصري الجديد
    # ----------------------------------------------------------------------------------------------

    def evaluate_scene_with_scout(
        self,
        media_path: Path,
        narration: str
    ) -> Dict:
        """
        المراجع البصري الحقيقي.

        لا يستخدم Groq Vision.

        يتم تجهيز صورة تمثل المشهد ثم إرسال مسارها
        إلى Antigravity ليقوم Gemini 3.6 Flash High
        بقراءة الصورة فعلياً واتخاذ القرار.
        """

        log.info(
            "👁️ الكشاف البصري: Gemini 3.6 Flash High عبر Antigravity..."
        )

        eval_img_path = (
            CONFIG.paths.cache
            / f"{media_path.stem}_vision_review.jpg"
        )

        try:

            # --------------------------------------------------------------------------------------
            # إذا كان المصدر فيديو:
            # استخراج إطار من منتصف الفيديو تقريباً بدلاً من أول إطار.
            # --------------------------------------------------------------------------------------

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

                    duration_output = subprocess.check_output(
                        probe_cmd,
                        stderr=subprocess.DEVNULL
                    ).decode().strip()

                    video_duration = float(
                        duration_output
                    )

                except Exception:

                    video_duration = 3.0

                # نأخذ لقطة من منتصف الفيديو تقريباً.
                seek_time = max(
                    0.5,
                    video_duration * 0.45
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
                    str(eval_img_path)
                ]

                subprocess.run(
                    frame_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=60
                )

            else:

                # ----------------------------------------------------------------------------------
                # الصور: نستخدم الصورة نفسها لكن نضع نسخة داخل cache
                # لضمان أن Antigravity يملك وصولاً مباشراً إليها.
                # ----------------------------------------------------------------------------------

                if media_path.exists():

                    try:
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
                            f"⚠️ تعذر تجهيز صورة المراجعة: {e}"
                        )

        except Exception as e:

            log.warning(
                f"⚠️ فشل تجهيز الصورة للمراجع: {e}"
            )

        if not eval_img_path.exists():

            log.error(
                "❌ لم يتم إنشاء صورة المراجعة."
            )

            return {
                "valid": False,
                "montage": "NORMAL"
            }

        # ------------------------------------------------------------------------------------------
        # المسار المطلق للصورة.
        # Antigravity سيقرأ الصورة من workspace باستخدام أدواته البصرية.
        # ------------------------------------------------------------------------------------------

        image_path = str(
            eval_img_path.resolve()
        )

        log.info(
            "🧠 Gemini 3.6 Flash High يفحص الصورة فعلياً..."
        )

        prompt = f"""
أنت الآن تعمل كمراجع بصري سينمائي صارم داخل خط إنتاج وثائقيات تحقيق جنائية.

مهمتك ليست تخمين الصورة من اسم الملف.

يجب عليك فتح وقراءة الصورة الموجودة هنا باستخدام أدواتك البصرية:

{image_path}

هذه الصورة هي لقطة فعلية من المشهد الذي سنضعه في الفيلم.

النص السردي للمشهد:

"{narration}"

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
مهمة الفحص
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

افحص الصورة فعلياً ثم قيّم:

1. ما الذي يظهر في الصورة؟
2. هل العناصر المرئية مرتبطة فعلاً بالنص السردي؟
3. هل يمكن للمشاهد أن يفهم لماذا وُضعت هذه اللقطة هنا؟
4. هل الصورة مناسبة لوثائقي تحقيق جنائي؟
5. هل يوجد شيء واضح يناقض السرد؟
6. هل اللقطة ذات جودة بصرية مقبولة؟
7. هل يوجد تشوه أو لقطة رديئة أو عنصر عشوائي؟
8. هل الجو العام مناسب للمشهد؟
9. إذا كانت الصورة تحتوي على شخص أو مكان أو جسم محدد، هل يتوافق مع السياق؟
10. لا تعتمد على اسم الملف أو search_query للحكم؛ احكم على ما تراه بالصورة.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
قواعد القبول
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ACCEPT:
إذا كانت الصورة مناسبة بشكل واضح للسرد ويمكن استخدامها في الوثائقي.

REJECT:
إذا كانت الصورة بعيدة عن معنى السرد، عشوائية، مضللة، رديئة جداً، أو لا تخدم المشهد.

كن صارماً.

لا تقبل الصورة فقط لأنها "سينمائية".
التطابق مع المعنى أهم من جمال الصورة.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
اختيار المونتاج
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

إذا كانت الصورة:

- لقطة ثابتة تحتاج حركة درامية:
  ZOOM_IN

- تحتوي على مساحة مناسبة لحركة أفقية:
  PAN_RIGHT

- ذات طابع أرشيفي/قديم/تحقيقي ويخدمها الأبيض والأسود:
  BW

- مناسبة بدون تأثير:
  NORMAL

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
الإخراج
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

أخرج JSON فقط، بدون Markdown وبدون شرح خارجي:

{{
  "decision": "ACCEPT",
  "montage": "ZOOM_IN",
  "reason": "سبب مختصر جداً"
}}

decision يجب أن يكون فقط:
ACCEPT
أو
REJECT

montage يجب أن يكون فقط:
ZOOM_IN
PAN_RIGHT
BW
NORMAL
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
                f"🔎 رد Gemini البصري:\n{output[:700]}"
            )

            match = re.search(
                r'\{.*\}',
                output,
                re.DOTALL
            )

            if not match:

                log.warning(
                    "⚠️ المراجع لم يرجع JSON صالحاً."
                )

                return {
                    "valid": False,
                    "montage": "NORMAL"
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

            allowed_montages = {
                "ZOOM_IN",
                "PAN_RIGHT",
                "BW",
                "NORMAL"
            }

            if montage not in allowed_montages:
                montage = "NORMAL"

            if decision == "ACCEPT":

                log.info(
                    "✅ Gemini 3.6 Flash High اعتمد اللقطة."
                )

                log.info(
                    f"🎬 أسلوب المونتاج: {montage}"
                )

                return {
                    "valid": True,
                    "montage": montage,
                    "reason": data.get(
                        "reason",
                        ""
                    )
                }

            log.warning(
                "❌ Gemini 3.6 Flash High رفض اللقطة."
            )

            log.warning(
                f"السبب: {data.get('reason', 'غير محدد')}"
            )

            return {
                "valid": False,
                "montage": montage,
                "reason": data.get(
                    "reason",
                    ""
                )
            }

        except subprocess.TimeoutExpired:

            log.warning(
                "⚠️ انتهى وقت المراجع البصري."
            )

            return {
                "valid": False,
                "montage": "NORMAL"
            }

        except Exception as e:

            log.warning(
                f"⚠️ خطأ في Gemini Vision عبر Antigravity: {e}"
            )

            return {
                "valid": False,
                "montage": "NORMAL"
            }

        finally:

            # حذف صورة المراجعة المؤقتة.
            try:

                if eval_img_path.exists():
                    eval_img_path.unlink()

            except Exception:
                pass


# ==================================================================================================
# 4. محرك استدعاء الوسائط ومعالجة الصوت والمونتاج
# ==================================================================================================

class MediaFetcher:

    def __init__(self):
        self.h = {
            "User-Agent": "HybridPipeline/21.0"
        }

    def fetch_video(
        self,
        source: str,
        query: str,
        out: Path,
        index: int = 0
    ) -> bool:

        try:

            if source == "PEXELS" and CONFIG.pexels:

                r = requests.get(
                    "https://api.pexels.com/videos/search",
                    params={
                        "query": query,
                        "orientation": "landscape"
                    },
                    headers={
                        "Authorization": CONFIG.pexels
                    },
                    timeout=15
                ).json()

                if (
                    r.get("videos")
                    and len(r["videos"]) > index
                ):

                    video_files = sorted(
                        r["videos"][index]["video_files"],
                        key=lambda x: x.get(
                            "width",
                            0
                        ),
                        reverse=True
                    )

                    if video_files:

                        video_url = video_files[0]["link"]

                        response = requests.get(
                            video_url,
                            timeout=60
                        )

                        if response.status_code == 200:

                            out.write_bytes(
                                response.content
                            )

                            return True

            elif source == "PIXABAY" and CONFIG.pixabay:

                r = requests.get(
                    "https://pixabay.com/api/videos/",
                    params={
                        "key": CONFIG.pixabay,
                        "q": query
                    },
                    timeout=15
                ).json()

                if (
                    int(r.get("totalHits", 0)) > index
                ):

                    video_url = (
                        r["hits"][index]
                        ["videos"]
                        ["large"]
                        ["url"]
                    )

                    response = requests.get(
                        video_url,
                        timeout=60
                    )

                    if response.status_code == 200:

                        out.write_bytes(
                            response.content
                        )

                        return True

        except Exception:
            pass

        return False

    def fetch_image(
        self,
        source: str,
        query: str,
        out: Path
    ) -> bool:

        try:

            if source == "MAPBOX" and CONFIG.mapbox:

                res = requests.get(
                    f"https://api.mapbox.com/styles/v1/"
                    f"mapbox/dark-v11/static/"
                    f"{query},14,0,0/1920x1080",
                    params={
                        "access_token": CONFIG.mapbox
                    },
                    timeout=20
                )

                if (
                    res.status_code == 200
                    and b"{" not in res.content[:10]
                ):

                    out.write_bytes(
                        res.content
                    )

                    return True

            elif source == "WIKIPEDIA":

                r = requests.get(
                    "https://en.wikipedia.org/w/api.php",
                    params={
                        "action": "query",
                        "generator": "search",
                        "gsrsearch": query,
                        "prop": "pageimages",
                        "pithumbsize": 1920,
                        "format": "json"
                    },
                    headers=self.h,
                    timeout=15
                ).json()

                pages = list(
                    r.get(
                        "query",
                        {}
                    ).get(
                        "pages",
                        {}
                    ).values()
                )

                if pages:

                    thumb = (
                        pages[0]
                        .get("thumbnail", {})
                        .get("source")
                    )

                    if thumb:

                        response = requests.get(
                            thumb,
                            headers=self.h,
                            timeout=20
                        )

                        if response.status_code == 200:

                            out.write_bytes(
                                response.content
                            )

                            return True

        except Exception:
            pass

        return False

    def get_freesound_foley(
        self,
        query: str,
        out: Path
    ) -> bool:

        if (
            not CONFIG.freesound
            or query.lower() == "none"
        ):
            return False

        try:

            r = requests.get(
                "https://freesound.org/apiv2/search/text/",
                params={
                    "query": query,
                    "token": CONFIG.freesound,
                    "fields": "previews"
                },
                timeout=15
            ).json()

            if r.get("results"):

                preview = (
                    r["results"][0]
                    ["previews"]
                    ["preview-hq-mp3"]
                )

                response = requests.get(
                    preview,
                    timeout=30
                )

                if response.status_code == 200:

                    out.write_bytes(
                        response.content
                    )

                    return True

        except Exception:
            pass

        return False

    def fallback_graphic(
        self,
        query: str,
        out: Path
    ):

        canvas = Image.new(
            "RGB",
            (1920, 1080),
            (20, 22, 25)
        )

        d = ImageDraw.Draw(canvas)

        d.text(
            (960, 540),
            f"CLASSIFIED EVIDENCE\n{query[:30]}",
            fill=(180, 50, 50),
            anchor="mm"
        )

        canvas.save(
            out,
            "JPEG"
        )


# ==================================================================================================
# 5. Groq Whisper فقط
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
# 6. إنشاء الترجمة
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

        for i, w in enumerate(words):

            if not ch:
                st = w["start"]

            ch.append(w["word"])

            if (
                len(ch) == 5
                or i == len(words) - 1
            ):

                evs.append(
                    "Dialogue: 1,"
                    f"{ft(st)},"
                    f"{ft(w['end'])},"
                    "Sub,,0,0,0,,"
                    +
                    get_display(
                        arabic_reshaper.reshape(
                            " ".join(ch)
                        )
                    )
                )

                ch = []

    else:

        wl = fallback.split()

        cd = dur / max(
            1,
            len(wl) // 5
        )

        for i in range(
            0,
            len(wl),
            5
        ):

            evs.append(
                "Dialogue: 1,"
                f"{ft(i // 5 * cd)},"
                f"{ft((i // 5 + 1) * cd)},"
                "Sub,,0,0,0,,"
                +
                get_display(
                    arabic_reshaper.reshape(
                        " ".join(
                            wl[i:i + 5]
                        )
                    )
                )
            )

    bdg = get_display(
        arabic_reshaper.reshape(
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
# 7. معالجة الصوت
# ==================================================================================================

def process_audio(
    voice: Path,
    foley: Path,
    has_foley: bool,
    out: Path
) -> float:

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
            str(out)
        ]

    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    return float(
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
        ).decode().strip()
    )


# ==================================================================================================
# 8. رندرة المشهد
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
            "-c:a",
            "aac",
            "-shortest",
            str(out)
        ]

    else:

        if "PAN_RIGHT" in montage_hint:

            motion = (
                "z=1.1:"
                "x='x+1':"
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
            f"d={int(dur * fps)}:"
            "s=1920x1080"
            f"{color_fx},"
            "vignette=PI/3.6,"
            f"subtitles='{ass}',"
            f"fps={fps}"
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
            timeout=300
        )

    except Exception:

        log.error(
            "⚠️ FFmpeg تخطى الوقت."
        )


# ==================================================================================================
# 9. رفع Google Drive
# ==================================================================================================

def upload_drive(
    vid: Path
):

    if not (
        CONFIG.yt_id
        and CONFIG.drive_token
    ):
        return

    log.info(
        "الرفع إلى Google Drive..."
    )

    try:

        dr = build(
            "drive",
            "v3",
            credentials=Credentials(
                None,
                refresh_token=CONFIG.drive_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CONFIG.yt_id,
                client_secret=CONFIG.yt_secret
            )
        )

        res = dr.files().list(
            q=(
                "name='Broadcast_Vault' "
                "and mimeType='application/vnd.google-apps.folder'"
            ),
            fields="files(id)"
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

        req = dr.files().create(
            body={
                "name": vid.name,
                "parents": [fid]
            },
            media_body=MediaFileUpload(
                str(vid),
                mimetype="video/mp4",
                resumable=True,
                chunksize=5 * 1024 * 1024
            )
        )

        while req.next_chunk()[1] is None:
            pass

        log.info(
            "✅ تم الرفع إلى Drive بنجاح!"
        )

    except Exception as e:

        log.error(
            f"فشل Drive: {e}"
        )


# ==================================================================================================
# 10. وحدة التحكم المركزية
# ==================================================================================================

def main():

    start_time = datetime.now()

    max_seconds = (
        3 * 3600
        + 45 * 60
    )

    log.info(
        f"▶ بدء محرك الإنتاج V21 "
        f"(Antigravity Vision Scout) | "
        f"القضية: {CONFIG.topic}"
    )

    director = Hybrid_Director()

    fetcher = MediaFetcher()

    while True:

        if (
            datetime.now()
            - start_time
        ).total_seconds() > max_seconds:

            log.warning(
                "⏳ اقتربنا من الحد الأقصى "
                "(3.75 ساعات). "
                "سيتم إنهاء الحلقة ورفع أفضل نسخة."
            )

            append_memory(
                "توقفنا للحفاظ على السيرفر "
                "ورفعنا أفضل نسخة تم رندرتها."
            )

            break

        script = director.plan_documentary()

        clips = []

        for i, s in enumerate(script):

            typ = s.get(
                "media_type",
                "WIKIPEDIA"
            )

            q = s.get(
                "search_query",
                ""
            )

            foley = s.get(
                "foley_type",
                "none"
            )

            txt = s.get(
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

            c_ass = pfx.with_suffix(
                ".ass"
            )

            # --------------------------------------------------------------------------------------
            # إذا كان المشهد النهائي موجوداً بالفعل، لا نعيد العمل.
            # --------------------------------------------------------------------------------------

            if (
                c_mp4.exists()
                and c_mp4.stat().st_size > 50000
            ):

                clips.append(c_mp4)

                log.info(
                    f"♻️ المشهد {i + 1} موجود في Cache — تخطي."
                )

                continue

            log.info(
                f"🎬 المشهد {i + 1} | "
                f"الأداة: {typ} | "
                f"المؤثر: {foley}"
            )

            # --------------------------------------------------------------------------------------
            # الصوت
            # --------------------------------------------------------------------------------------

            if not c_wav.exists():

                director.generate_voice(
                    txt,
                    c_wav
                )

            has_foley = (
                fetcher.get_freesound_foley(
                    foley,
                    c_foley
                )
            )

            if c_wav.exists():

                dur = process_audio(
                    c_wav,
                    c_foley,
                    has_foley,
                    c_mp3
                )

                # Groq هنا فقط للـ Whisper.
                words = groq_transcribe(
                    c_mp3
                )

            else:

                log.warning(
                    "⚠️ تعذر إنتاج الصوت، "
                    "سيتم تجاوز المشهد."
                )

                continue

            # --------------------------------------------------------------------------------------
            # الوسائط + المراجع البصري
            # --------------------------------------------------------------------------------------

            c_media = (
                pfx.with_suffix(".mp4")
                if typ in ["PEXELS", "PIXABAY"]
                else
                pfx.with_suffix(".jpg")
            )

            is_vid = False

            montage_style = "NORMAL"

            accepted = False

            # نحاول حتى 3 نتائج مختلفة.
            for attempt in range(3):

                log.info(
                    f"🔎 محاولة الوسيط {attempt + 1}/3 "
                    f"للمشهد {i + 1}"
                )

                # ----------------------------------------------------------------------
                # فيديو
                # ----------------------------------------------------------------------

                if typ in [
                    "PEXELS",
                    "PIXABAY"
                ]:

                    is_vid = fetcher.fetch_video(
                        typ,
                        q,
                        c_media,
                        attempt
                    )

                # ----------------------------------------------------------------------
                # صورة
                # ----------------------------------------------------------------------

                else:

                    is_vid = not fetcher.fetch_image(
                        typ,
                        q,
                        c_media
                    )

                if not c_media.exists():

                    log.warning(
                        "⚠️ لم يتم العثور على الوسيط."
                    )

                    continue

                # ----------------------------------------------------------------------
                # هنا نقطة المراجعة المهمة:
                #
                # Gemini 3.6 Flash High
                # عبر Google Antigravity
                #
                # يرى الصورة فعلياً.
                # ----------------------------------------------------------------------

                eval_result = (
                    director.evaluate_scene_with_scout(
                        c_media,
                        txt
                    )
                )

                if eval_result["valid"]:

                    accepted = True

                    montage_style = eval_result.get(
                        "montage",
                        "NORMAL"
                    )

                    log.info(
                        f"🏆 المشهد {i + 1} اجتاز "
                        f"المراجع البصري."
                    )

                    break

                else:

                    log.warning(
                        f"🗑️ تم رفض نتيجة الوسيط "
                        f"للمشهد {i + 1}."
                    )

                    try:

                        if c_media.exists():
                            c_media.unlink()

                    except Exception:
                        pass

            # --------------------------------------------------------------------------------------
            # إذا فشلت جميع المحاولات
            # --------------------------------------------------------------------------------------

            if (
                not accepted
                or not c_media.exists()
            ):

                log.warning(
                    f"⚠️ لم يتم العثور على لقطة مقبولة "
                    f"للمشهد {i + 1}. "
                    f"سيتم استخدام بطاقة احتياطية."
                )

                fallback_path = (
                    pfx.with_suffix(".jpg")
                )

                fetcher.fallback_graphic(
                    q,
                    fallback_path
                )

                c_media = fallback_path

                is_vid = False

                montage_style = "ZOOM_IN"

            # --------------------------------------------------------------------------------------
            # الترجمة
            # --------------------------------------------------------------------------------------

            badges = {
                "PEXELS": "لقطات سينمائية",
                "PIXABAY": "أرشيف عام",
                "MAPBOX": "إحداثيات جغرافية تكتيكية",
                "WIKIPEDIA": "سجلات التحقيق الرسمية"
            }

            generate_ass(
                words,
                txt,
                dur,
                c_ass,
                f"● {badges.get(typ, 'ملف سري')} | {q}"
            )

            # --------------------------------------------------------------------------------------
            # الرندر
            # --------------------------------------------------------------------------------------

            render_scene(
                c_media,
                is_vid,
                c_ass,
                c_mp3,
                c_mp4,
                dur,
                montage_style
            )

            if c_mp4.exists():

                clips.append(
                    c_mp4
                )

                log.info(
                    f"✅ تم رندر المشهد {i + 1}."
                )

        # ------------------------------------------------------------------------------------------
        # التقييم النهائي
        # ------------------------------------------------------------------------------------------

        if director.critique_and_improve():

            log.info(
                "🎬 المخرج النهائي اعتمد النسخة. "
                "جاري التصدير..."
            )

            break

        else:

            log.info(
                "🛠️ جاري إعادة هندسة المشاهد المعيبة..."
            )

    # =================================================================================================
    # التصدير النهائي
    # =================================================================================================

    if clips:

        txt_list = (
            CONFIG.paths.base
            / "list.txt"
        )

        txt_list.write_text(
            "\n".join(
                f"file '{c.resolve().as_posix()}'"
                for c in clips
            ),
            encoding="utf-8"
        )

        final_vid = (
            CONFIG.paths.base
            / f"MasterDoc_{int(time.time())}.mp4"
        )

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
            stderr=subprocess.DEVNULL
        )

        upload_drive(
            final_vid
        )

    log.info(
        f"✔ اكتملت الجلسة! "
        f"الوقت الإجمالي: "
        f"{datetime.now() - start_time}"
    )


# ==================================================================================================
# 11. التشغيل
# ==================================================================================================

if __name__ == "__main__":
    main()
