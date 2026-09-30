#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
HYBRID V22.33 - Montage Renderer Fixed
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
        return logging.Formatter(fmt, datefmt="%H:%M:%S").format(record)


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


def load_ag_media(file_path):
    ext = file_path.suffix.lower()
    path_str = str(file_path.resolve())

    if ext in [".mp4", ".mov", ".webm", ".avi"]:
        if hasattr(ag, "Video"):
            return ag.Video.from_file(path_str)

        if hasattr(ag, "media") and hasattr(
            ag.media,
            "Video"
        ):
            return ag.media.Video.from_file(path_str)

        if hasattr(ag, "from_file"):
            return ag.from_file(path_str)

    else:
        if hasattr(ag, "Image"):
            return ag.Image.from_file(path_str)

        if hasattr(ag, "media") and hasattr(
            ag.media,
            "Image"
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
    # doesn't route to AI Studio
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
                        "📋 تم العثور على master_manifest.json صالح."
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
                        f"⚠️ Agy Error الجولة {round_num + 1}: "
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
                        "⚠ لم يتم العثور على JSON Array صالح من Agy."
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
                        indent=2
                    ),
                    encoding="utf-8",
                )

                log.info(
                    f"✅ تم إنشاء السيناريو: {len(data)} مشهداً."
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

    async def _async_evaluate_scout(
        self,
        media_path,
        narration,
        source
    ):
        # 🔴 تم تعديل البرومبت هنا ليكون المراجع أذكى ويقبل اللقطات التعبيرية
        prompt = f'''أنت المراجع البصري الفوري (مخرج وثائقي محترف) لفيلم تحقيقي بعنوان:
"{CONFIG.topic}"

نوع المصدر:
{source}

التعليق الصوتي للمشهد:
"{narration}"

شاهد الوسيط المرفق بعناية:
{media_path}

قواعد التقييم كمخرج سينمائي:
1. لا تبحث عن التطابق الحرفي الممل فقط. اقبل (ACCEPT) اللقطات التعبيرية، الرمزية، أو الأجواء العامة (B-Roll) إذا كانت تخدم النص (مثلاً: نص عن تحقيق مالي يقبل مشهد للأوراق، آلة حاسبة، أو شارع مظلم).
2. أعطِ درجة (score) من 0.0 إلى 1.0 تعكس مدى جودة اللقطة لخدمة جو الفيلم.
3. اختر ACCEPT إذا كانت اللقطة مناسبة للجو العام للوثائقي، واختر REJECT إذا كانت اللقطة مشتتة أو سيئة أو لا علاقة لها إطلاقاً.
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

            import asyncio

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Agy failed: {stderr.decode('utf-8')}"
                )

            result_text = (
                stdout
                .decode("utf-8")
                .strip()
            )

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
            f"👁 Antigravity Vision Scout يفحص الوسيط من {source}..."
        )

        try:
            result_text = str(
                asyncio.run(
                    self._async_evaluate_scout(
                        media_path,
                        narration,
                        source
                    )
                )
            ).strip()

            if (
                not result_text
                or "<google.antigravity" in result_text
                or "<bound method" in result_text
            ):
                log.warning(
                    "⚠️ رد المراجع عبارة عن كائن برمجي فارغ، تم رفض المشهد للانتقال للتالي."
                )

                return {
                    "accepted": False,
                    "montage": "ZOOM_IN",
                    "new_query": "investigation evidence",
                    "score": 0.0,
                    "reason": "Empty or Object Response"
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
                    f"⚠️ تعذر استخراج JSON من الرد: {result_text[:200]}"
                )

                return {
                    "accepted": False,
                    "montage": "ZOOM_IN",
                    "new_query": "archival evidence",
                    "score": 0.0,
                    "reason": "Parse Error"
                }

            score = float(
                data.get(
                    "score",
                    0.0
                )
            )

            decision = str(
                data.get(
                    "decision",
                    ""
                )
            ).upper()

            # 🔴 تم تخفيض شرط القبول إلى 60% لإعطاء مرونة للقطات التعبيرية
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
                "reason": "Exception"
            }

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

            import asyncio

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                raise RuntimeError(
                    f"Agy failed: {stderr.decode('utf-8')}"
                )

            result_text = (
                stdout
                .decode("utf-8")
                .strip()
            )

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
            )
            .read_text(
                encoding="utf-8",
                errors="ignore"
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
                        logs
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
                    "المراجع النهائي شاهد الفيلم وقدم إصلاحاً برمجياً."
                )

                Path(__file__).write_text(
                    new_code,
                    encoding="utf-8"
                )

                log.warning(
                    "🔄 تم استبدال pipeline.py. إعادة التشغيل..."
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

    def generate_voice(
        self,
        text,
        out_wav
    ):
        if not CONFIG.gemini_keys:
            log.error(
                "❌ لا توجد GEMINI_API_KEY لاستخدامها في الصوت."
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
                f"🎙 توليد الصوت الجولة {round_num + 1}/3..."
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
                        and out_wav.stat().st_size > 1000
                    ):
                        log.info(
                            "⏳ تم توليد الصوت بنجاح. تبريد 30 ثانية..."
                        )

                        time.sleep(30)
                        return

                except Exception as e:
                    log.warning(
                        f"⚠️ فشل المفتاح {i + 1}: {str(e)[:200]}"
                    )

                    time.sleep(2)

            time.sleep(10)

        log.error(
            "❌ استنفدت جميع محاولات توليد الصوت."
        )


class MediaFetcher:

    def __init__(self):
        self.h = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,"
                "application/xml;q=0.9,image/avif,image/webp,"
                "image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://" + "en.wikipedia.org/"
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
            safe_query[:100]
            .strip()
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
                        "Authorization": CONFIG.pexels,
                        "User-Agent": self.h["User-Agent"],
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
                    key=lambda x: x.get(
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
                    and out.stat().st_size > 50000
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
                    and out.stat().st_size > 50000
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
                    p for p in pages
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
                    and out.stat().st_size > 10000
                )

            if source == "ARCHIVE":
                api_url = (
                    f"https://{'archive'}.org/advancedsearch.php"
                )

                r = self._get(
                    api_url,
                    params={
                        "q": (
                            f"{safe_query} "
                            "AND mediatype:image"
                        ),
                        "fl[]": "identifier",
                        "output": "json",
                        "rows": 10,
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

                identifier = docs[index].get(
                    "identifier"
                )

                if not identifier:
                    return False

                image_url = (
                    f"https://{'archive'}.org/services/img/"
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
                    and out.stat().st_size > 10000
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
                        "token": CONFIG.freesound,
                        "fields": "previews",
                        "page_size": 5,
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
                    and out.stat().st_size > 1000
                )

        except requests.RequestException as e:
            err_msg = str(e)

            if "429" in err_msg:
                log.warning(
                    f"⏳ {source} يطلب التمهل (Error 429). سننتظر قليلاً..."
                )
                time.sleep(3)

            elif "403" in err_msg:
                log.warning(
                    f"🛡️ {source} يرفض الوصول (Error 403). تم التخطي بأمان."
                )

            else:
                log.warning(
                    f"🌐 خطأ شبكة في {source}: {err_msg[:150]}"
                )

        except Exception as e:
            log.warning(
                f"⚠️ خطأ {source}: {str(e)[:150]}"
            )

        return False


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
            "[v][bg]amix=inputs=2:duration=first:"
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

    subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        dur = float(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-show_entries",
                    "format=duration",
                    "-of",
                    "default=noprint_wrappers=1:nokey=1",
                    str(out),
                ]
            )
            .decode()
            .strip()
        )

        if dur < 0.5:
            raise ValueError(
                "Audio duration is too short"
            )

        return dur

    except Exception:
        return 3.0


# ============================================================
# MONTAGE FIX V22.33
# ============================================================

RENDER_VERSION = "V22.33_MONTAGE_FIX"


def ffprobe_duration(path):
    """
    الحصول على المدة الحقيقية للملف.
    يستخدم فقط للتحقق من أن الرندر لم يتحول إلى
    مدة الفيديو الخام.
    """

    try:
        value = subprocess.check_output(
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
            stderr=subprocess.DEVNULL,
            timeout=30,
        )

        return float(
            value.decode().strip()
        )

    except Exception:
        return 0.0


def render_stamp_path(output_path):
    return output_path.with_suffix(
        ".render.json"
    )


def validate_rendered_scene(
    output_path,
    expected_duration,
    tolerance=0.60
):
    if not output_path.exists():
        return False, 0.0

    if output_path.stat().st_size < 50000:
        return False, 0.0

    actual_duration = ffprobe_duration(
        output_path
    )

    if actual_duration <= 0:
        return False, actual_duration

    if abs(
        actual_duration - expected_duration
    ) > tolerance:
        log.error(
            f"❌ مدة المشهد غير صحيحة | "
            f"المطلوب: {expected_duration:.2f}s | "
            f"الناتج: {actual_duration:.2f}s"
        )

        return False, actual_duration

    return True, actual_duration


def render_scene(
    media,
    is_vid,
    aud,
    out,
    dur,
    montage
):
    """
    الرندر الجديد:
    - المصدر الخام منفصل تماماً عن ملف الإخراج.
    - المدة مقيدة بمدة الصوت.
    - 25 FPS ثابت.
    - يمنع بقاء فيديو المصدر الخام لعدة دقائق.
    """

    fx = (
        ",hue=s=0"
        if "BW" in str(montage).upper()
        else ",eq=contrast=1.12:saturation=0.85"
    )

    montage_upper = str(
        montage or "NORMAL"
    ).upper()

    if is_vid:

        # تأثير الحركة حسب قرار الـ Scout
        if "ZOOM_OUT" in montage_upper:
            zoom_expr = (
                "max(1.0,"
                "1.10-on*0.00010)"
            )

        elif "ZOOM_IN" in montage_upper:
            zoom_expr = (
                "min(1.10,"
                "1.0+on*0.00010)"
            )

        else:
            zoom_expr = "1.03"

        filter_complex = (
            "[0:v]"
            "scale=1920:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            f"zoompan="
            f"z='{zoom_expr}':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            "d=1:"
            "s=1920x1080:"
            "fps=25"
            f"{fx}[v]"
        )

        cmd = [
            "ffmpeg",
            "-y",

            # إذا كان الفيديو أقصر من الصوت يسمح له بالتكرار،
            # لكن لا يسمح للخروج بتجاوز مدة الصوت.
            "-stream_loop",
            "-1",

            "-i",
            str(media),

            "-i",
            str(aud),

            "-filter_complex",
            filter_complex,

            "-map",
            "[v]",

            "-map",
            "1:a",

            # الحارس الأساسي ضد تمدد الفيديو
            "-t",
            f"{dur:.3f}",

            "-r",
            "25",

            "-fps_mode",
            "cfr",

            "-pix_fmt",
            "yuv420p",

            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-crf",
            "20",

            "-c:a",
            "aac",

            "-ar",
            "48000",

            "-b:a",
            "192k",

            "-movflags",
            "+faststart",

            str(out),
        ]

    else:

        # الصور: حركة Zoom بسيطة ومستمرة.
        # لا نستخدم مدة frames القديمة لأنها كانت تسبب
        # سلوكاً غير مضبوط للـ zoompan.
        if "ZOOM_OUT" in montage_upper:
            zoom_expr = (
                "max(1.0,"
                "1.10-on*0.00010)"
            )

        elif "ZOOM_IN" in montage_upper:
            zoom_expr = (
                "min(1.10,"
                "1.0+on*0.00010)"
            )

        else:
            zoom_expr = "1.03"

        filter_complex = (
            "[0:v]"
            "scale=1920:1080:"
            "force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            f"zoompan="
            f"z='{zoom_expr}':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            "d=1:"
            "s=1920x1080:"
            "fps=25"
            f"{fx}[v]"
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
            filter_complex,

            "-map",
            "[v]",

            "-map",
            "1:a",

            # الحارس الأساسي للصور أيضاً
            "-t",
            f"{dur:.3f}",

            "-r",
            "25",

            "-fps_mode",
            "cfr",

            "-pix_fmt",
            "yuv420p",

            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-crf",
            "20",

            "-c:a",
            "aac",

            "-ar",
            "48000",

            "-b:a",
            "192k",

            "-movflags",
            "+faststart",

            str(out),
        ]

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
                "❌ FFmpeg فشل في رندر المشهد:"
            )

            error_tail = (
                result.stderr[-1500:]
                if result.stderr
                else "No FFmpeg error output"
            )

            log.error(
                error_tail
            )

            return False

        valid, actual = validate_rendered_scene(
            out,
            dur
        )

        if not valid:
            try:
                if out.exists():
                    out.unlink()
            except Exception:
                pass

            return False

        stamp = render_stamp_path(
            out
        )

        stamp.write_text(
            json.dumps(
                {
                    "render_version": RENDER_VERSION,
                    "expected_duration": round(
                        dur,
                        3
                    ),
                    "actual_duration": round(
                        actual,
                        3
                    ),
                    "montage": str(
                        montage
                    ),
                    "created_at": datetime.now().isoformat(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return True

    except subprocess.TimeoutExpired:
        log.error(
            "❌ انتهت مهلة FFmpeg البالغة 300 ثانية."
        )

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass

        return False

    except Exception as e:
        log.error(
            f"❌ خطأ في render_scene: {e}"
        )

        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass

        return False


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
                        "name": "Broadcast_Vault",
                        "mimeType": (
                            "application/vnd.google-apps.folder"
                        ),
                    },
                    fields="id",
                )
                .execute()["id"]
            )

        req = dr.files().create(
            body={
                "name": vid.name,
                "parents": [fid]
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
                    f"نسخة المخرج | {CONFIG.topic} - {int(time.time())}"
                ),
                "description": (
                    "تم الإنتاج عبر "
                    "UNIVERSAL INVESTIGATIVE "
                    "DOCUMENTARY ENGINE V22.32"
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


def main():
    start_time = datetime.now()

    log.info(
        f"▶ بدء المحرك V22.33 | القضية: {CONFIG.topic}"
    )

    director = Hybrid_Director()
    fetcher = MediaFetcher()

    try:
        script = director.plan_documentary()

    except Exception as e:
        log.error(
            str(e)
        )
        sys.exit(1)

    clips = []
    clip_durations = []

    for i, scene in enumerate(script):

        elapsed = (
            datetime.now() - start_time
        ).total_seconds()

        if elapsed > 13500:
            log.warning(
                "⏳ تم تجاوز الحد الزمني الكلي 13,500 ثانية. "
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

        # --------------------------------------------------
        # أهم إصلاح:
        # c_mp4 = خرج المونتاج فقط
        # c_media = المصدر الخام فقط
        # --------------------------------------------------

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

        render_stamp = render_stamp_path(
            c_mp4
        )

        log.info(
            f"\n🎥 جاري العمل على المشهد "
            f"{i + 1}/{len(script)}..."
        )

        if not c_wav.exists():
            director.generate_voice(
                txt,
                c_wav
            )

        if not c_wav.exists():
            log.error(
                f"❌ لم يتم إنشاء صوت للمشهد {i + 1}."
            )
            continue

        has_foley = False

        if (
            foley
            and str(foley).lower() != "none"
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

        # --------------------------------------------------
        # فحص كاش الرندر بعد معرفة مدة الصوت
        # --------------------------------------------------

        cache_valid = False

        if (
            c_mp4.exists()
            and c_mp4.stat().st_size > 50000
            and render_stamp.exists()
        ):
            try:
                stamp_data = json.loads(
                    render_stamp.read_text(
                        encoding="utf-8"
                    )
                )

                stamp_version = stamp_data.get(
                    "render_version"
                )

                cached_duration = ffprobe_duration(
                    c_mp4
                )

                if (
                    stamp_version == RENDER_VERSION
                    and cached_duration > 0
                    and abs(
                        cached_duration - dur
                    ) <= 0.60
                ):
                    cache_valid = True

                    log.info(
                        f"⏭ المشهد {i + 1} موجود في كاش V22.33 صالح "
                        f"({cached_duration:.2f}s)."
                    )

                    clips.append(
                        c_mp4
                    )

                    clip_durations.append(
                        cached_duration
                    )

            except Exception:
                cache_valid = False

        if cache_valid:
            continue

        # --------------------------------------------------
        # تنظيف كاش V22.32 القديم
        # حتى لا يتم اعتبار الفيديو الخام القديم
        # مشهداً مرندراً.
        # --------------------------------------------------

        if c_mp4.exists():
            log.info(
                f"🧹 إزالة خرج رندر قديم/غير موثوق للمشهد {i + 1}."
            )

            try:
                c_mp4.unlink()
            except Exception:
                pass

        if render_stamp.exists():
            try:
                render_stamp.unlink()
            except Exception:
                pass

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

        # 🔴 متغيرات تتبع أفضل لقطة لتجنب ترك المشهد فارغاً
        best_score = -1.0
        best_media_ext = ".jpg"
        best_montage = "NORMAL"

        while (
            not scene_approved
            and attempt_counter < MAX_ATTEMPTS
        ):
            elapsed = (
                datetime.now() - start_time
            ).total_seconds()

            if elapsed > 13500:
                log.warning(
                    f"⏳ انتهى الوقت الكلي أثناء البحث "
                    f"عن المشهد {i + 1}."
                )
                break

            current_source = sources_pool[
                attempt_counter
                % len(sources_pool)
            ]

            index_in_source = (
                attempt_counter % 3
            )

            # --------------------------------------------------
            # الإصلاح المهم:
            # فيديو المصدر الخام أصبح _source.mp4
            # وليس s_000.mp4
            # --------------------------------------------------

            if current_source in [
                "PEXELS",
                "PIXABAY"
            ]:
                c_media = pfx.with_name(
                    pfx.name + "_source.mp4"
                )

            else:
                c_media = pfx.with_name(
                    pfx.name + "_source.jpg"
                )

            safe_q = enforce_english_query(
                current_q
            )

            log.info(
                f"🔎 محاولة البحث #{attempt_counter + 1} | "
                f"{current_source} | "
                f"نتيجة {index_in_source + 1}/3 | "
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
                    f"👁 تم العثور على وسيط من {current_source}. "
                    "إرساله إلى Antigravity..."
                )

                eval_res = (
                    director.evaluate_scene_with_scout(
                        c_media,
                        txt,
                        current_source,
                    )
                )

                current_score = eval_res.get(
                    "score",
                    0.0
                )

                # 🔴 حفظ أفضل لقطة
                if (
                    current_score > best_score
                    and c_media.exists()
                    and c_media.stat().st_size > 1000
                ):
                    best_score = current_score

                    best_montage = eval_res.get(
                        "montage",
                        "NORMAL"
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
                        f"💾 تم حفظ هذه اللقطة كأفضل بديل حتى الآن "
                        f"(Score: {best_score})."
                    )

                if eval_res.get(
                    "accepted",
                    False
                ):
                    scene_approved = True

                    montage_style = eval_res.get(
                        "montage",
                        "NORMAL"
                    )

                    log.info(
                        f"✅ ACCEPTED | المشهد {i + 1} "
                        f"اعتمد بعد {attempt_counter + 1} محاولة."
                    )

                    break

                new_q = enforce_english_query(
                    eval_res.get(
                        "new_query",
                        ""
                    )
                )

                if (
                    new_q
                    and new_q != "mystery evidence"
                    and new_q.lower()
                    != safe_q.lower()
                ):
                    current_q = enforce_english_query(
                        new_q,
                        90
                    )

                else:
                    variant = query_variants[
                        attempt_counter
                        % len(query_variants)
                    ]

                    current_q = enforce_english_query(
                        f"{base_q} {variant}",
                        90,
                    )

                log.warning(
                    "🔄 REJECTED | Antigravity رفض الوسيط."
                )

                log.info(
                    f"🔎 Query الجديدة: '{current_q}'"
                )

                try:
                    c_media.unlink()
                except Exception:
                    pass

            else:
                log.warning(
                    f"⚠️ {current_source} لم يعطِ نتيجة صالحة "
                    f"لـ '{safe_q}'."
                )

            time.sleep(3)

            attempt_counter += 1

            if (
                attempt_counter
                % len(sources_pool)
                == 0
            ):
                variant = query_variants[
                    (
                        attempt_counter
                        // len(sources_pool)
                    )
                    % len(query_variants)
                ]

                current_q = enforce_english_query(
                    f"{base_q} {variant}",
                    90,
                )

                log.info(
                    "♻️ لم يتم اعتماد أي لقطة في الدورة الكاملة. "
                    f"تغيير استراتيجية البحث إلى: '{current_q}'"
                )

        # 🔴 نظام الإنقاذ الذكي إذا فشلت جميع المحاولات
        if not scene_approved:
            log.error(
                f"❌ استنفذت جميع المحاولات الـ {MAX_ATTEMPTS} للمشهد {i + 1}."
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
                and backup_path.stat().st_size > 1000
            ):
                log.warning(
                    f"⚠️ إجبار استخدام أفضل لقطة بديلة تم العثور عليها "
                    f"(Score: {best_score}) كإجراء إنقاذي."
                )

                # تحديد مسار المصدر الصحيح
                if best_media_ext.lower() == ".mp4":
                    c_media = pfx.with_name(
                        pfx.name
                        + "_source.mp4"
                    )
                else:
                    c_media = pfx.with_name(
                        pfx.name
                        + "_source.jpg"
                    )

                shutil.move(
                    backup_path,
                    c_media
                )

                scene_approved = True
                montage_style = best_montage

            else:
                append_memory(
                    f"Scene {i + 1} completely failed after {MAX_ATTEMPTS} attempts. "
                    f"Original query: {original_q}"
                )

                continue

        # تنظيف أي ملفات نسخ احتياطي متبقية
        try:
            for backup_file in pfx.parent.glob(
                pfx.name
                + "_best_backup*"
            ):
                backup_file.unlink()

        except Exception:
            pass

        # --------------------------------------------------
        # الرندر
        # --------------------------------------------------

        try:
            is_video_source = (
                c_media.suffix.lower()
                == ".mp4"
            )

            log.info(
                f"🎬 Montage Renderer: {RENDER_VERSION} | "
                f"1920x1080 | 25 FPS | "
                f"Target Duration: {dur:.2f}s"
            )

            rendered = render_scene(
                c_media,
                is_video_source,
                c_mp3,
                c_mp4,
                dur,
                montage_style,
            )

            if rendered:
                actual_duration = ffprobe_duration(
                    c_mp4
                )

                clips.append(
                    c_mp4
                )

                clip_durations.append(
                    actual_duration
                )

                log.info(
                    f"🎬 تم بناء المشهد {i + 1} | "
                    f"المدة: {actual_duration:.2f}s"
                )

            else:
                log.error(
                    f"❌ فشل بناء ملف المشهد {i + 1}."
                )

        except Exception as e:
            log.error(
                f"⚠️ خطأ FFmpeg في المشهد {i + 1}: {e}"
            )

    final_vid = (
        CONFIG.paths.base
        / f"MasterDoc_{int(time.time())}.mp4"
    )

    if clips:
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

        expected_total = sum(
            clip_durations
        )

        log.info(
            f"🎞️ دمج {len(clips)} مشهداً..."
        )

        log.info(
            f"⏱️ مجموع مدد المشاهد المرندرة: "
            f"{expected_total / 60:.2f} دقيقة"
        )

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
                str(final_vid),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600,
        )

        if (
            concat_result.returncode != 0
            or not final_vid.exists()
        ):
            log.error(
                "❌ فشل الدمج الأول بـ stream copy."
            )

            # إعادة الدمج بطريقة أكثر صرامة
            # إذا اختلفت خصائص أحد المقاطع.
            fallback_vid = (
                CONFIG.paths.base
                / f"MasterDoc_{int(time.time())}_reencoded.mp4"
            )

            fallback_result = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-i",
                    str(txt_list),
                    "-c:v",
                    "libx264",
                    "-preset",
                    "veryfast",
                    "-crf",
                    "20",
                    "-pix_fmt",
                    "yuv420p",
                    "-c:a",
                    "aac",
                    "-ar",
                    "48000",
                    "-b:a",
                    "192k",
                    "-movflags",
                    "+faststart",
                    str(fallback_vid),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
                timeout=900,
            )

            if (
                fallback_result.returncode == 0
                and fallback_vid.exists()
            ):
                final_vid = fallback_vid

            else:
                log.error(
                    "❌ فشل الدمج النهائي حتى بعد إعادة الترميز."
                )

        # --------------------------------------------------
        # التحقق النهائي من المدة
        # --------------------------------------------------

        if final_vid.exists():
            final_duration = ffprobe_duration(
                final_vid
            )

            log.info(
                f"🎬 مدة الفيلم النهائي: "
                f"{final_duration / 60:.2f} دقيقة"
            )

            duration_difference = abs(
                final_duration
                - expected_total
            )

            if duration_difference > 2.0:
                log.error(
                    f"❌ تحذير حرج: مدة الفيلم النهائي تختلف عن "
                    f"مجموع المشاهد بمقدار "
                    f"{duration_difference:.2f} ثانية."
                )

            else:
                log.info(
                    "✅ تحقق المدة النهائية ناجح."
                )

            log.info(
                "🎬 تم تصدير الفيلم النهائي."
            )

            upload_drive(
                final_vid
            )

            upload_youtube(
                final_vid
            )

    else:
        log.error(
            "❌ لا توجد مشاهد جاهزة للدمج."
        )

    if final_vid.exists():
        director.self_critique_and_recode(
            final_vid
        )


if __name__ == "__main__":
    main()
