#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
V26 - FRESH WORKSPACE + 10-KEY GEMINI TTS ROTATION + GOOGLE DRIVE & YOUTUBE UPLOAD

- NO CACHE
- NO REUSE OF PREVIOUS FILES
- output_build is deleted completely at startup
- FULL narration TTS is generated in ONE request
- Gemini keys rotate automatically
- Every key switch is printed in the logs
- Auto-uploads final render to Google Drive and YouTube via Refresh Token
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

from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import requests
from google import genai
from google.genai import types

# مكتبات الرفع إلى Google Drive و YouTube
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


ENGINE_VERSION = "V26-FRESH-NO-CACHE-FULL-TTS-10KEY-UPLOAD"

TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
TARGET_AR = 48000

CONCURRENT_WORKERS = 5
TTS_WORKERS = 2

TTS_MODEL = "gemini-3.8-flash-tts"
TTS_VOICE = "Charon"

AGY_SCRIPT_MODEL = "gemini-3.1-pro"
AGY_VISION_MODEL = "gemini-3.8-flash"
GROQ_MODEL = "whisper-large-v3"

MAX_MEDIA_SIZE_MB = 120


class ProTelemetryFormatter(logging.Formatter):
    def format(self, record):
        now = datetime.now().strftime("%H:%M:%S")
        icons = {"INFO": "INFO", "WARNING": "WARN", "ERROR": "ERROR", "DEBUG": "DEBUG"}
        return f"{now} | [{icons.get(record.levelname, record.levelname)}] | {record.getMessage()}"


def setup_logger():
    logger = logging.getLogger("DOCUMENTARY_ENGINE")
    logger.setLevel(logging.INFO)
    if logger.handlers:
        logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ProTelemetryFormatter())
    logger.addHandler(handler)
    return logger


LOGGER = setup_logger()


def log(msg, level="info"):
    if level == "warning":
        LOGGER.warning(msg)
    elif level == "error":
        LOGGER.error(msg)
    elif level == "debug":
        LOGGER.debug(msg)
    else:
        LOGGER.info(msg)


class EngineConfig:
    def __init__(self):
        self.topic = os.environ.get("VIDEO_TOPIC", "لغز اختفاء غامض")
        self.topic_clean = re.sub(r"[^a-zA-Z0-9_\-]+", "_", self.topic).strip("_")
        self.topic_key = self.topic_clean[:80] or "documentary"

        self.base_dir = Path("./output_build")
        self.work_dir = self.base_dir / "workspace"
        self.final_video = self.base_dir / "final_documentary.mp4"
        self.master_audio = self.work_dir / "master_audio.wav"

        raw_keys = (
            os.environ.get("GEMINI_API_KEYS")
            or os.environ.get("GEMINI_API_KEY")
            or ""
        )

        self.gemini_keys = list(dict.fromkeys([
            k.strip()
            for k in re.split(r"[,;\n]+", raw_keys)
            if k.strip()
        ]))

        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.pexels_key = os.environ.get("PEXELS_API_KEY", "")
        self.pixabay_key = os.environ.get("PIXABAY_API_KEY", "")
        self.giphy_key = os.environ.get("GIPHY_API_KEY", "")
        self.openverse_client_id = os.environ.get("OPENVERSE_CLIENT_ID", "")
        self.openverse_client_secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "")
        self.europeana_key = os.environ.get("EUROPEANA_API_KEY", "")
        self.openverse_token = os.environ.get("OPENVERSE_TOKEN", "")

        # إعدادات جوجل للرفع
        self.google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        self.google_refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")


CONFIG = EngineConfig()


def prepare_fresh_workspace():
    log("🧹 تنظيف بيئة التشغيل بالكامل...")

    if CONFIG.base_dir.exists():
        try:
            shutil.rmtree(CONFIG.base_dir)
            log("🗑️ تم حذف output_build بالكامل — لا توجد ملفات سابقة.")
        except Exception as e:
            log(f"تعذر حذف output_build: {e}", "error")
            raise

    CONFIG.base_dir.mkdir(parents=True, exist_ok=True)
    CONFIG.work_dir.mkdir(parents=True, exist_ok=True)

    log("🆕 تم إنشاء Workspace جديد من الصفر.")
    log("🚫 لا يوجد Cache ولا إعادة استخدام لأي ملف سابق.")


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
                    if idx in self.active or idx in excluded:
                        continue

                    self.active.add(idx)
                    self.cursor = (idx + 1) % len(self.keys)
                    return idx, self.keys[idx]

            time.sleep(0.05)

    def release(self, index):
        with self.lock:
            self.active.discard(index)


if not CONFIG.gemini_keys:
    log("لم يتم العثور على GEMINI_API_KEY أو GEMINI_API_KEYS.", "error")
    raise RuntimeError("No Gemini API keys configured.")

GEMINI_POOL = GeminiKeyPool(CONFIG.gemini_keys)

log(f"🔑 تم تحميل {len(CONFIG.gemini_keys)} مفتاح Gemini.")

if len(CONFIG.gemini_keys) < 10:
    log(f"⚠️ تم العثور على {len(CONFIG.gemini_keys)} مفاتيح فقط، وليس 10.", "warning")
else:
    log("🔑 تم تجهيز المفاتيح العشرة للتدوير.")


def probe_duration(path):
    if not path or not os.path.exists(path):
        return 0.0

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def is_valid_media(path, min_duration=0.05):
    if not path:
        return False

    path = Path(path)
    if not path.exists() or path.stat().st_size < 1024:
        return False

    return probe_duration(path) >= min_duration


def is_valid_visual(path):
    if not path:
        return False

    path = Path(path)
    if not path.exists() or path.stat().st_size < 1024:
        return False

    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                str(path)
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20
        )

        dimensions = result.stdout.strip()
        if "x" not in dimensions:
            return False

        w, h = dimensions.split("x")
        return int(w) > 100 and int(h) > 100
    except Exception:
        return False


def clean_query(text):
    if not text:
        return ""

    text = re.sub(r"[^\x00-\x7F]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:180]


def safe_filename(text):
    return re.sub(r"[^a-zA-Z0-9_\-]+", "_", text)[:100]


def run_cmd(cmd, timeout=300):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout
    )


def extract_json(text):
    if not text:
        return None

    text = text.strip()
    text = re.sub(r"```json\s*", "", text, flags=re.I)
    text = re.sub(r"```\s*$", "", text)

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


class StoryScoutEngine:
    def __init__(self):
        self.script = None

    def inspect_and_plan(self):
        log("🧠 بدء تحليل الموضوع وصناعة السيناريو عبر AGY...")

        prompt = f"""
You are an elite investigative documentary producer.

TOPIC:
{CONFIG.topic}

Create a production-ready investigative documentary plan.

Return ONLY valid JSON.

Required structure:

{{
  "story_type": "investigation",
  "major_movie": false,
  "movie_title": "",
  "primary_english_query": "",
  "part_1": "",
  "part_2": ""
}}

Requirements:
1. Arabic narration.
2. Total narration approximately 350-450 Arabic words.
3. Divide naturally into part_1 and part_2.
4. Do NOT summarize.
5. Do NOT shorten.
6. Serious investigative documentary tone.
7. Factual where facts are known.
8. Clearly distinguish uncertain claims.
9. Avoid fabricated sources.
10. Make the narration suitable for cinematic documentary voice-over.
"""

        try:
            result = subprocess.run(
                [
                    "agy",
                    "--model", AGY_SCRIPT_MODEL,
                    "--effort", "high",
                    "--dangerously-skip-permissions",
                    "-p", prompt
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=300
            )

            data = extract_json(result.stdout.strip())
            if not data:
                raise RuntimeError("AGY returned invalid JSON.")

            part1 = str(data.get("part_1", "")).strip()
            part2 = str(data.get("part_2", "")).strip()

            if not part1 or not part2:
                raise RuntimeError("AGY returned empty narration parts.")

            self.script = data

            total_words = len(part1.split()) + len(part2.split())
            log(f"📝 تم توليد السيناريو: {total_words} كلمة.")
            log("━━━━━━━━━━ النص الكامل ━━━━━━━━━━")
            log(part1 + "\n\n" + part2)
            log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            return data

        except Exception as e:
            log(f"⚠️ فشل AGY في إنشاء السيناريو: {e}", "warning")

            fallback = {
                "story_type": "investigation",
                "major_movie": False,
                "movie_title": "",
                "primary_english_query": clean_query(CONFIG.topic),
                "part_1": (
                    f"في هذه القصة الغامضة نقترب من تفاصيل {CONFIG.topic}. "
                    f"تبدأ الحكاية بتفاصيل تبدو عادية، لكن مجموعة من الأحداث "
                    f"والوثائق والشهادات تفتح أسئلة أكثر مما تقدم إجابات. "
                    f"ومع إعادة ترتيب الوقائع زمنياً تظهر تناقضات يصعب تجاهلها. "
                    f"ما الذي حدث فعلاً، ومن كان يعرف ما يجري في ذلك الوقت؟"
                ),
                "part_2": (
                    "تظل بعض التفاصيل غير محسومة، ولهذا يجب فصل المعلومات "
                    "الموثقة عن الروايات المتداولة. عند مقارنة الشهادات "
                    "والوثائق والتوقيتات تظهر صورة أكثر تعقيداً للقضية. "
                    "وفي النهاية لا تقدم هذه القصة إجابة سهلة، بل تتركنا "
                    "أمام مجموعة من الحقائق والأسئلة التي ما زالت تنتظر تفسيراً."
                )
            }

            self.script = fallback
            return fallback


def is_rate_limit_error(error):
    text = str(error).lower()

    indicators = [
        "429",
        "resource_exhausted",
        "rate limit",
        "rate_limit",
        "quota",
        "too many requests",
        "exhausted"
    ]

    return any(item in text for item in indicators)


class MasterAudioStudio:
    def __init__(self):
        self.model = TTS_MODEL

    def _generate_full_narration(self, full_text, out_wav):
        out_wav = Path(out_wav)

        if out_wav.exists():
            try:
                out_wav.unlink()
            except Exception:
                pass

        attempted = set()
        total_keys = len(CONFIG.gemini_keys)

        for attempt in range(total_keys):
            key_index, api_key = GEMINI_POOL.acquire(excluded=attempted)
            attempted.add(key_index)
            display_key = key_index + 1

            try:
                log(
                    f"🔑 Gemini Key #{display_key} → "
                    f"بدء TTS للنص الكامل "
                    f"(محاولة {attempt + 1}/{total_keys})"
                )

                started = time.time()

                client = genai.Client(api_key=api_key)

                config = types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=TTS_VOICE
                            )
                        )
                    )
                )

                instruction = (
                    "[INSTRUCTION: "
                    "Chilling authoritative Arabic documentary narrator. "
                    "Read the ENTIRE narration exactly from beginning to end. "
                    "Do not summarize. "
                    "Do not omit any words. "
                    "Do not split the narration into separate sections. "
                    "Do not add explanations or commentary. "
                    "Preserve the exact Arabic wording and punctuation. "
                    "Maintain one continuous cinematic narration.]"
                )

                response = client.models.generate_content(
                    model=self.model,
                    contents=instruction + "\n\n" + full_text,
                    config=config
                )

                if not response.candidates:
                    raise RuntimeError("Gemini returned no candidates.")

                candidate = response.candidates[0]

                if not candidate.content or not candidate.content.parts:
                    raise RuntimeError("Gemini returned empty content.")

                inline_data = None

                for part in candidate.content.parts:
                    if getattr(part, "inline_data", None):
                        inline_data = part.inline_data
                        break

                if not inline_data:
                    raise RuntimeError("No inline audio data returned.")

                data = inline_data.data

                if isinstance(data, str):
                    raw_audio = base64.b64decode(data)
                else:
                    raw_audio = bytes(data)

                if not raw_audio:
                    raise RuntimeError("Empty audio payload.")

                if raw_audio[:4] == b"RIFF":
                    with open(out_wav, "wb") as f:
                        f.write(raw_audio)
                else:
                    temp_pcm = (
                        CONFIG.work_dir
                        / f"full_narration_key{display_key}.pcm"
                    )

                    with open(temp_pcm, "wb") as f:
                        f.write(raw_audio)

                    ffmpeg_result = run_cmd(
                        [
                            "ffmpeg", "-y",
                            "-f", "s16le",
                            "-ar", "24000",
                            "-ac", "1",
                            "-i", str(temp_pcm),
                            "-c:a", "pcm_s16le",
                            "-ar", "24000",
                            "-ac", "1",
                            str(out_wav)
                        ],
                        timeout=180
                    )

                    try:
                        temp_pcm.unlink()
                    except Exception:
                        pass

                    if ffmpeg_result.returncode != 0:
                        raise RuntimeError(ffmpeg_result.stderr[-2000:])

                duration = probe_duration(out_wav)

                if not is_valid_media(out_wav):
                    raise RuntimeError(
                        "Generated full narration WAV failed validation."
                    )

                elapsed = time.time() - started

                log(
                    f"✅ النص الكامل نجح باستخدام Gemini Key "
                    f"#{display_key}"
                )
                log(
                    f"🎙️ Full Narration: {duration:.2f}s audio | "
                    f"{elapsed:.1f}s generation time"
                )

                return True

            except Exception as e:
                error_text = str(e)

                if is_rate_limit_error(e):
                    log(
                        f"⚠️ Gemini Key #{display_key} تعرض لـ "
                        f"Rate Limit / Quota.",
                        "warning"
                    )
                else:
                    log(
                        f"❌ Gemini Key #{display_key} فشل في TTS الكامل: "
                        f"{error_text[:500]}",
                        "warning"
                    )

                GEMINI_POOL.release(key_index)

                if attempt + 1 < total_keys:
                    next_candidates = [
                        i for i in range(total_keys)
                        if i not in attempted
                    ]

                    if next_candidates:
                        next_display = next_candidates[0] + 1
                        log(
                            f"🔄 تبديل المفتاح: "
                            f"#{display_key} → #{next_display}"
                        )

                    time.sleep(
                        0.7 if is_rate_limit_error(e) else 0.2
                    )

                continue

            finally:
                GEMINI_POOL.release(key_index)

        raise RuntimeError(
            "❌ انتهت جميع مفاتيح Gemini بدون نجاح "
            "في توليد التعليق الصوتي الكامل."
        )

    def produce_master_track(self, script):
        part1 = str(script["part_1"]).strip()
        part2 = str(script["part_2"]).strip()

        full_narration = f"{part1}\n\n{part2}".strip()

        if not full_narration:
            raise RuntimeError("النص الكامل للتعليق الصوتي فارغ.")

        if CONFIG.master_audio.exists():
            try:
                CONFIG.master_audio.unlink()
            except Exception:
                pass

        log("🎙️ بدء إنتاج التعليق الصوتي الكامل.")
        log("🚫 لا يوجد تقسيم إلى Part 1 / Part 2.")
        log("⚡ سيتم إرسال النص الكامل إلى Gemini TTS في طلب واحد.")

        total_words = len(full_narration.split())
        log(f"📝 إجمالي النص المرسل إلى TTS: {total_words} كلمة.")

        started = time.time()

        ok = self._generate_full_narration(
            full_narration,
            CONFIG.master_audio
        )

        elapsed = time.time() - started

        if not ok:
            raise RuntimeError("فشل إنتاج التعليق الصوتي الكامل.")

        duration = probe_duration(CONFIG.master_audio)

        if not is_valid_media(CONFIG.master_audio):
            raise RuntimeError("Master audio validation failed.")

        log(
            f"🎙️ اكتمل TTS الكامل في {elapsed:.1f} ثانية."
        )
        log(
            f"🎚️ Master Audio: {duration:.2f} ثانية."
        )

        return CONFIG.master_audio


class WordSyncSlicer:
    def __init__(self):
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"

    def align_and_slice(self, audio_path, full_script):
        if not CONFIG.groq_api_key:
            raise RuntimeError("GROQ_API_KEY غير موجود.")

        log("🧠 إرسال الصوت إلى Groq Whisper للتوقيتات...")

        headers = {
            "Authorization": f"Bearer {CONFIG.groq_api_key}"
        }

        with open(audio_path, "rb") as audio_file:
            files = {
                "file": (
                    "master_audio.wav",
                    audio_file,
                    "audio/wav"
                )
            }

            data = {
                "model": GROQ_MODEL,
                "language": "ar",
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word"
            }

            response = requests.post(
                self.url,
                headers=headers,
                files=files,
                data=data,
                timeout=180
            )

        if response.status_code != 200:
            raise RuntimeError(
                f"Groq error {response.status_code}: {response.text[:2000]}"
            )

        payload = response.json()
        words = []

        for item in payload.get("words", []):
            word = str(item.get("word", "")).strip()
            start = item.get("start")
            end = item.get("end")

            if word and start is not None and end is not None:
                words.append({
                    "word": word,
                    "start": float(start),
                    "end": float(end)
                })

        if not words:
            raise RuntimeError("Groq returned no word timestamps.")

        log(f"📝 تم الحصول على {len(words)} توقيت كلمة.")

        shots = []
        current_words = []
        shot_start = 0.0
        last_end = 0.0
        punctuation = (".", "!", "?", "،", "؛", ":", "؟")

        for item in words:
            current_words.append(item)
            last_end = item["end"]

            elapsed = last_end - shot_start
            should_cut = False

            if elapsed >= 3.5:
                should_cut = True
            elif elapsed >= 2.0 and item["word"].endswith(punctuation):
                should_cut = True

            if should_cut:
                text = " ".join(
                    x["word"] for x in current_words
                ).strip()

                if text:
                    shots.append({
                        "index": len(shots) + 1,
                        "start": shot_start,
                        "end": last_end,
                        "duration": max(0.5, last_end - shot_start),
                        "text": text
                    })

                current_words = []
                shot_start = last_end

        if current_words:
            text = " ".join(
                x["word"] for x in current_words
            ).strip()

            if text:
                shots.append({
                    "index": len(shots) + 1,
                    "start": shot_start,
                    "end": last_end,
                    "duration": max(0.5, last_end - shot_start),
                    "text": text
                })

        log(f"✂️ تم تقسيم التعليق الصوتي إلى {len(shots)} لقطة.")
        return shots


def ass_time(seconds):
    seconds = max(0, float(seconds))

    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60

    return f"{h}:{m:02d}:{s:05.2f}"


def escape_ass(text):
    text = text.replace("\\", r"\\")
    text = text.replace("{", r"\{")
    text = text.replace("}", r"\}")
    return text


def write_subtitles_ass(shots, output_path):
    log("📝 إنشاء Broadcast ASS subtitles...")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\n")
        f.write("ScriptType: v4.00+\n")
        f.write("PlayResX: 1920\n")
        f.write("PlayResY: 1080\n")
        f.write("ScaledBorderAndShadow: yes\n\n")

        f.write("[V4+ Styles]\n")
        f.write(
            "Format: Name, Fontname, Fontsize, PrimaryColour, "
            "SecondaryColour, OutlineColour, BackColour, Bold, "
            "Italic, Underline, StrikeOut, ScaleX, ScaleY, "
            "Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )

        f.write(
            "Style: Default,Noto Sans Arabic,58,"
            "&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,"
            "-1,0,0,0,100,100,0,0,1,3,1,2,80,80,70,1\n\n"
        )

        f.write("[Events]\n")
        f.write(
            "Format: Layer, Start, End, Style, Name, "
            "MarginL, MarginR, MarginV, Effect, Text\n"
        )

        for shot in shots:
            start = ass_time(shot["start"])
            end = ass_time(shot["end"])
            text = escape_ass(shot["text"])

            f.write(
                f"Dialogue: 0,{start},{end},Default,,"
                f"0,0,0,,{{\\fad(120,120)}}{text}\n"
            )

    log(f"✅ ASS subtitles: {output_path}")


class MediaSources:

    @staticmethod
    def fetch_openverse_image(query, output):
        try:
            response = requests.get(
                "https://api.openverse.org/v1/images/",
                params={"q": query, "page_size": 5},
                timeout=30
            )

            if response.status_code != 200:
                return None

            for item in response.json().get("results", []):
                url = item.get("thumbnail") or item.get("url")
                if not url:
                    continue

                r = requests.get(url, timeout=40)
                if r.status_code != 200:
                    continue

                with open(output, "wb") as f:
                    f.write(r.content)

                if is_valid_visual(output):
                    return output

        except Exception as e:
            log(f"Openverse: {e}", "debug")

        return None

    @staticmethod
    def fetch_europeana_image(query, output):
        if not CONFIG.europeana_key:
            return None

        try:
            response = requests.get(
                "https://api.europeana.eu/record/v2/search.json",
                params={
                    "wskey": CONFIG.europeana_key,
                    "query": query,
                    "rows": 5,
                    "profile": "rich"
                },
                timeout=30
            )

            if response.status_code != 200:
                return None

            for item in response.json().get("items", []):
                previews = item.get("edmPreview", [])
                if not previews:
                    continue

                r = requests.get(previews[0], timeout=40)
                if r.status_code != 200:
                    continue

                with open(output, "wb") as f:
                    f.write(r.content)

                if is_valid_visual(output):
                    return output

        except Exception as e:
            log(f"Europeana: {e}", "debug")

        return None

    @staticmethod
    def fetch_nasa_media(query, output):
        try:
            response = requests.get(
                "https://images-api.nasa.gov/search",
                params={"q": query, "media_type": "image"},
                timeout=30
            )

            if response.status_code != 200:
                return None

            items = response.json().get("collection", {}).get("items", [])

            for item in items:
                links = item.get("links", [])
                if not links:
                    continue

                href = links[0].get("href")
                if not href:
                    continue

                r = requests.get(href, timeout=40)
                if r.status_code != 200:
                    continue

                with open(output, "wb") as f:
                    f.write(r.content)

                if is_valid_visual(output):
                    return output

        except Exception as e:
            log(f"NASA: {e}", "debug")

        return None

    @staticmethod
    def fetch_chronicling_america(query, output):
        try:
            url = (
                "https://www.loc.gov/"
                "?fo=json&c=100&q="
                + urllib.parse.quote(query)
            )

            response = requests.get(url, timeout=40)

            if response.status_code != 200:
                return None

            for item in response.json().get("results", []):
                for resource in item.get("resources", []):
                    image_url = resource.get("image_url")

                    if isinstance(image_url, list):
                        image_url = image_url[0] if image_url else None

                    if not image_url:
                        continue

                    r = requests.get(image_url, timeout=40)
                    if r.status_code != 200:
                        continue

                    with open(output, "wb") as f:
                        f.write(r.content)

                    if is_valid_visual(output):
                        return output

        except Exception as e:
            log(f"LOC: {e}", "debug")

        return None

    @staticmethod
    def fetch_pixabay_video(query, output):
        if not CONFIG.pixabay_key:
            return None

        try:
            response = requests.get(
                "https://pixabay.com/api/videos/",
                params={
                    "key": CONFIG.pixabay_key,
                    "q": query,
                    "per_page": 10,
                    "safesearch": "true"
                },
                timeout=30
            )

            if response.status_code != 200:
                return None

            for hit in response.json().get("hits", []):
                videos = hit.get("videos", {})

                for name in ("large", "medium", "small"):
                    item = videos.get(name)
                    if not item or not item.get("url"):
                        continue

                    r = requests.get(
                        item["url"],
                        stream=True,
                        timeout=60
                    )

                    if r.status_code != 200:
                        continue

                    with open(output, "wb") as f:
                        for chunk in r.iter_content(1024 * 256):
                            if chunk:
                                f.write(chunk)

                    if is_valid_media(output, 0.5):
                        return output

        except Exception as e:
            log(f"Pixabay: {e}", "debug")

        return None

    @staticmethod
    def fetch_pexels_video(query, output):
        if not CONFIG.pexels_key:
            return None

        try:
            response = requests.get(
                "https://api.pexels.com/videos/search",
                headers={"Authorization": CONFIG.pexels_key},
                params={"query": query, "per_page": 8},
                timeout=30
            )

            if response.status_code != 200:
                return None

            for video in response.json().get("videos", []):
                files = video.get("video_files", [])

                files = sorted(
                    files,
                    key=lambda x: abs((x.get("width") or 0) - TARGET_W)
                )

                for item in files:
                    url = item.get("link")
                    if not url:
                        continue

                    r = requests.get(
                        url,
                        stream=True,
                        timeout=60
                    )

                    if r.status_code != 200:
                        continue

                    with open(output, "wb") as f:
                        for chunk in r.iter_content(1024 * 256):
                            if chunk:
                                f.write(chunk)

                    if is_valid_media(output):
                        return output

        except Exception as e:
            log(f"Pexels: {e}", "debug")

        return None

    @staticmethod
    def fetch_giphy(query, output):
        if not CONFIG.giphy_key:
            return None

        try:
            response = requests.get(
                "https://api.giphy.com/v1/gifs/search",
                params={
                    "api_key": CONFIG.giphy_key,
                    "q": query,
                    "limit": 8,
                    "rating": "pg-13"
                },
                timeout=30
            )

            if response.status_code != 200:
                return None

            for item in response.json().get("data", []):
                mp4 = (
                    item.get("images", {})
                    .get("original_mp4", {})
                    .get("mp4")
                )

                if not mp4:
                    continue

                r = requests.get(
                    mp4,
                    stream=True,
                    timeout=60
                )

                if r.status_code != 200:
                    continue

                with open(output, "wb") as f:
                    for chunk in r.iter_content(1024 * 256):
                        if chunk:
                            f.write(chunk)

                if is_valid_media(output):
                    return output

        except Exception as e:
            log(f"Giphy: {e}", "debug")

        return None

    @staticmethod
    def fetch_wikipedia_image(query, output):
        try:
            response = requests.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrnamespace": 6,
                    "gsrlimit": 5,
                    "prop": "imageinfo",
                    "iiprop": "url",
                    "iiurlwidth": 1600,
                    "format": "json"
                },
                timeout=30
            )

            if response.status_code != 200:
                return None

            pages = response.json().get("query", {}).get("pages", {})

            for page in pages.values():
                info = page.get("imageinfo", [])
                if not info:
                    continue

                url = info[0].get("thumburl") or info[0].get("url")
                if not url:
                    continue

                r = requests.get(url, timeout=40)
                if r.status_code != 200:
                    continue

                with open(output, "wb") as f:
                    f.write(r.content)

                if is_valid_visual(output):
                    return output

        except Exception as e:
            log(f"Wikipedia: {e}", "debug")

        return None

    @staticmethod
    def fetch_fbi_archive(query, output):
        try:
            response = requests.get(
                "https://archive.org/advancedsearch.php",
                params={
                    "q": f"title:({query})",
                    "fl[]": ["identifier", "title"],
                    "rows": 10,
                    "output": "json"
                },
                timeout=40
            )

            if response.status_code != 200:
                return None

            docs = response.json().get("response", {}).get("docs", [])

            for doc in docs:
                identifier = doc.get("identifier")
                if not identifier:
                    continue

                metadata_url = f"https://archive.org/metadata/{identifier}"

                meta = requests.get(metadata_url, timeout=40)
                if meta.status_code != 200:
                    continue

                files = meta.json().get("files", [])
                candidates = []

                for item in files:
                    name = str(item.get("name", ""))

                    if not name.lower().endswith((".mp4", ".webm", ".mov")):
                        continue

                    size = int(item.get("size", 0) or 0)

                    if size > MAX_MEDIA_SIZE_MB * 1024 * 1024:
                        continue

                    candidates.append((size, name))

                candidates.sort(key=lambda x: x[0])

                for _, filename in candidates[:3]:
                    url = (
                        f"https://archive.org/download/"
                        f"{identifier}/"
                        f"{urllib.parse.quote(filename)}"
                    )

                    r = requests.get(
                        url,
                        stream=True,
                        timeout=90
                    )

                    if r.status_code != 200:
                        continue

                    with open(output, "wb") as f:
                        for chunk in r.iter_content(1024 * 256):
                            if chunk:
                                f.write(chunk)

                    if is_valid_media(output):
                        return output

        except Exception as e:
            log(f"Archive/FBI: {e}", "debug")

        return None


def create_fallback_visual(text, output):
    log(f"🖼️ إنشاء Fallback visual لـ: {text[:60]}")

    result = run_cmd(
        [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "color=c=0x111111:s=1920x1080:r=30",
            "-t", "5",
            "-vf",
            "noise=alls=18:allf=t+u,vignette,eq=contrast=1.12:saturation=0.75",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "24",
            "-pix_fmt", "yuv420p",
            str(output)
        ],
        timeout=60
    )

    if result.returncode == 0 and is_valid_media(output):
        return output

    return None


async def agy_evaluate_scout(media_path, shot):
    if not media_path:
        return False, 0.0, 0.0

    prompt = f"""
You are evaluating a media asset for an investigative documentary.

SHOT TEXT:
{shot["text"]}

LOCAL MEDIA PATH:
{media_path}

IMPORTANT:
Do NOT claim that you visually inspected the media unless the
CLI actually provided visual access to it.

Return ONLY JSON:

{{
  "decision": "accept",
  "score": 0.0,
  "best_start_second": 0.0
}}

score must be between 0 and 1.

If visual inspection is unavailable, use a conservative
decision based only on available metadata/context.
"""

    try:
        result = await asyncio.to_thread(
            subprocess.run,
            [
                "agy",
                "--model", AGY_VISION_MODEL,
                "--effort", "high",
                "--dangerously-skip-permissions",
                "-p", prompt
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=180
        )

        data = extract_json(result.stdout)

        if not data:
            return True, 0.5, 0.0

        decision = str(data.get("decision", "accept")).lower()
        score = float(data.get("score", 0.5))
        start = float(data.get("best_start_second", 0))

        accepted = (
            decision not in ("reject", "rejected", "bad")
            and score >= 0.35
        )

        return accepted, score, start

    except Exception as e:
        log(f"AGY Vision: {e}", "debug")
        return True, 0.0, 0.0


async def scout_shot_worker(shot, semaphore, story):
    async with semaphore:
        index = shot["index"]

        base = CONFIG.work_dir / f"shot_{index:03d}"
        video_path = Path(str(base) + ".mp4")
        image_path = Path(str(base) + ".jpg")

        for p in (video_path, image_path):
            if p.exists():
                try:
                    p.unlink()
                except Exception:
                    pass

        primary_query = story.get("primary_english_query", "")
        query = clean_query(shot["text"] + " " + primary_query)

        log(f"🔎 Shot {index}: {query[:120]}")

        source_candidates = []

        if CONFIG.pexels_key:
            source_candidates.append(
                ("PEXELS", MediaSources.fetch_pexels_video, video_path)
            )

        if CONFIG.pixabay_key:
            source_candidates.append(
                ("PIXABAY", MediaSources.fetch_pixabay_video, video_path)
            )

        source_candidates.append(
            ("WIKIPEDIA", MediaSources.fetch_wikipedia_image, image_path)
        )

        source_candidates.append(
            ("OPENVERSE", MediaSources.fetch_openverse_image, image_path)
        )

        if CONFIG.europeana_key:
            source_candidates.append(
                ("EUROPEANA", MediaSources.fetch_europeana_image, image_path)
            )

        source_candidates.append(
            ("NASA", MediaSources.fetch_nasa_media, image_path)
        )

        source_candidates.append(
            ("LOC", MediaSources.fetch_chronicling_america, image_path)
        )

        if CONFIG.giphy_key:
            source_candidates.append(
                ("GIPHY", MediaSources.fetch_giphy, video_path)
            )

        story_type = str(story.get("story_type", "")).lower()

        if (
            "invest" in story_type
            or "crime" in story_type
            or "mystery" in story_type
        ):
            source_candidates.append(
                ("FBI_ARCHIVE", MediaSources.fetch_fbi_archive, video_path)
            )

        for source_name, fetcher, output in source_candidates:
            try:
                if output.exists():
                    output.unlink()

                found = await asyncio.to_thread(
                    fetcher,
                    query,
                    output
                )

                if not found:
                    continue

                if output.suffix.lower() in (
                    ".jpg", ".jpeg", ".png", ".webp"
                ):
                    valid = is_valid_visual(output)
                else:
                    valid = is_valid_media(output)

                if not valid:
                    continue

                accepted, score, start = await agy_evaluate_scout(
                    output,
                    shot
                )

                if accepted:
                    duration = probe_duration(output)

                    log(
                        f"✅ Shot {index}: {source_name} "
                        f"| score={score:.2f} "
                        f"| start={start:.2f}s"
                    )

                    return {
                        "shot": shot,
                        "path": str(output),
                        "source": source_name,
                        "score": score,
                        "start": start,
                        "duration": duration
                    }

                log(
                    f"↩️ Shot {index}: {source_name} "
                    f"رفضه AGY (score={score:.2f})",
                    "debug"
                )

            except Exception as e:
                log(f"{source_name} Shot {index}: {e}", "debug")

        fallback = CONFIG.work_dir / f"shot_{index:03d}_fallback.mp4"

        result = await asyncio.to_thread(
            create_fallback_visual,
            shot["text"],
            fallback
        )

        if result:
            log(f"🛟 Shot {index}: Fallback visual")

            return {
                "shot": shot,
                "path": str(fallback),
                "source": "FALLBACK",
                "score": 0.0,
                "start": 0.0,
                "duration": probe_duration(fallback)
            }

        raise RuntimeError(f"Unable to obtain media for shot {index}")


async def scout_all_media(shots, story):
    log(
        f"🔍 بدء Media Scouting لـ {len(shots)} لقطة "
        f"بـ {CONCURRENT_WORKERS} عمال..."
    )

    semaphore = asyncio.Semaphore(CONCURRENT_WORKERS)

    tasks = [
        scout_shot_worker(shot, semaphore, story)
        for shot in shots
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    successful = []

    for result in results:
        if isinstance(result, Exception):
            log(f"⚠️ Shot failed: {result}", "warning")
        else:
            successful.append(result)

    successful.sort(key=lambda x: x["shot"]["index"])

    log(
        f"📦 Media Scouting مكتمل: "
        f"{len(successful)}/{len(shots)}"
    )

    if not successful:
        raise RuntimeError("لم يتم العثور على أي Media.")

    return successful


class AssemblyEngine:

    def render_sub_clip(self, item):
        shot = item["shot"]
        media_path = Path(item["path"])
        index = shot["index"]

        output = CONFIG.work_dir / f"rendered_{index:03d}.mp4"

        if output.exists():
            output.unlink()

        start = float(item.get("start", 0))
        duration = float(shot.get("duration", 3))

        media_duration = probe_duration(media_path)

        if media_duration > 0:
            start = min(start, max(0, media_duration - 0.1))

        is_video = media_path.suffix.lower() in (
            ".mp4", ".webm", ".mov", ".mkv", ".avi"
        )

        if is_video:
            vf = (
                "scale=1920:1080:"
                "force_original_aspect_ratio=increase,"
                "crop=1920:1080,"
                "eq=contrast=1.06:saturation=0.92,"
                "vignette,noise=alls=3:allf=t,fps=30"
            )

            cmd = [
                "ffmpeg", "-y",
                "-ss", str(start),
                "-i", str(media_path),
                "-t", str(duration),
                "-vf", vf,
                "-an",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                str(output)
            ]

        else:
            vf = (
                "scale=2208:1248:"
                "force_original_aspect_ratio=increase,"
                "crop=2208:1248,"
                "zoompan="
                "z='min(zoom+0.0008,1.15)':"
                "x='iw/2-(iw/zoom/2)':"
                "y='ih/2-(ih/zoom/2)':"
                "d=1:s=1920x1080:fps=30,"
                "eq=contrast=1.06:saturation=0.92,"
                "vignette,noise=alls=3:allf=t"
            )

            cmd = [
                "ffmpeg", "-y",
                "-loop", "1",
                "-i", str(media_path),
                "-t", str(duration),
                "-vf", vf,
                "-an",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                str(output)
            ]

        result = run_cmd(cmd, timeout=300)

        if result.returncode != 0:
            raise RuntimeError(
                f"Render shot {index} failed:\n"
                + result.stderr[-2000:]
            )

        if not is_valid_media(output):
            raise RuntimeError(f"Rendered shot {index} is invalid.")

        log(f"🎬 Rendered Shot {index}")
        return output

    def assemble_final_cut(self, rendered, subtitle_path):
        if not rendered:
            raise RuntimeError("No rendered clips.")

        concat_file = CONFIG.work_dir / "video_concat.txt"

        with open(concat_file, "w", encoding="utf-8") as f:
            for path in rendered:
                f.write(f"file '{Path(path).resolve()}'\n")

        temp_video = CONFIG.work_dir / "temp_video_track.mp4"

        if temp_video.exists():
            temp_video.unlink()

        result = run_cmd(
            [
                "ffmpeg", "-y",
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_file),
                "-c", "copy",
                str(temp_video)
            ],
            timeout=300
        )

        if result.returncode != 0:
            log(
                "⚠️ concat copy فشل، سيتم إعادة الترميز.",
                "warning"
            )

            result = run_cmd(
                [
                    "ffmpeg", "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", str(concat_file),
                    "-c:v", "libx264",
                    "-preset", "fast",
                    "-crf", "20",
                    "-pix_fmt", "yuv420p",
                    "-r", "30",
                    str(temp_video)
                ],
                timeout=600
            )

        if result.returncode != 0:
            raise RuntimeError(
                "Video concat failed:\n" + result.stderr[-3000:]
            )

        subtitle_abs = str(Path(subtitle_path).resolve())

        subtitle_filter = (
            "subtitles="
            + subtitle_abs
            .replace("\\", "\\\\")
            .replace(":", "\\:")
            .replace("'", "\\'")
        )

        log("🎞️ بدء Final FFmpeg Assembly...")

        if CONFIG.final_video.exists():
            CONFIG.final_video.unlink()

        result = run_cmd(
            [
                "ffmpeg", "-y",
                "-i", str(temp_video),
                "-i", str(CONFIG.master_audio),
                "-vf", subtitle_filter,
                "-map", "0:v:0",
                "-map", "1:a:0",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-r", "30",
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "48000",
                "-ac", "1",
                "-shortest",
                "-movflags", "+faststart",
                str(CONFIG.final_video)
            ],
            timeout=1200
        )

        if result.returncode != 0:
            raise RuntimeError(
                "Final FFmpeg assembly failed:\n"
                + result.stderr[-5000:]
            )

        if not is_valid_media(CONFIG.final_video, 1):
            raise RuntimeError("Final video failed validation.")

        final_duration = probe_duration(CONFIG.final_video)

        size_mb = (
            CONFIG.final_video.stat().st_size
            / 1024
            / 1024
        )

        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        log("🎉 FINAL DOCUMENTARY READY")
        log(f"⏱️ Duration: {final_duration / 60:.2f} minutes")
        log(f"💾 Size: {size_mb:.1f} MB")
        log(f"📁 {CONFIG.final_video}")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return CONFIG.final_video


class GoogleUploader:
    """كلاس لرفع الفيديو تلقائياً إلى Google Drive و YouTube"""
    def __init__(self, client_id, client_secret, refresh_token):
        self.creds = None
        if client_id and client_secret and refresh_token:
            self.creds = Credentials(
                token=None,
                refresh_token=refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=client_id,
                client_secret=client_secret
            )

    def upload_to_drive(self, file_path, title):
        if not self.creds:
            log("⚠️️ بيانات اعتماد Google مفقودة، سيتم تخطي الرفع إلى Drive.", "warning")
            return
        try:
            log(f"☁️ بدء الرفع إلى Google Drive: {title}")
            service = build('drive', 'v3', credentials=self.creds, cache_discovery=False)
            file_metadata = {'name': f"{title}.mp4"}
            media = MediaFileUpload(str(file_path), mimetype='video/mp4', resumable=True)
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            log(f"✅ تم الرفع إلى Drive بنجاح! الرابط: https://drive.google.com/file/d/{file.get('id')}/view")
        except Exception as e:
            log(f"❌ فشل الرفع إلى Drive: {e}", "error")

    def upload_to_youtube(self, file_path, title, description):
        if not self.creds:
            log("⚠️ بيانات اعتماد Google مفقودة، سيتم تخطي الرفع إلى YouTube.", "warning")
            return
        try:
            log(f"▶️ بدء الرفع إلى YouTube: {title}")
            service = build('youtube', 'v3', credentials=self.creds, cache_discovery=False)
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'tags': ['وثائقي', 'تحقيق', 'تلقائي', 'AI'],
                    'categoryId': '24' 
                },
                'status': {
                    'privacyStatus': 'private' # يتم الرفع كفيديو خاص (Private) للتحكم فيه لاحقاً
                }
            }
            media = MediaFileUpload(str(file_path), mimetype='video/mp4', resumable=True)
            request = service.videos().insert(
                part=','.join(body.keys()),
                body=body,
                media_body=media
            )
            response = request.execute()
            log(f"✅ تم الرفع إلى YouTube بنجاح! الرابط: https://youtu.be/{response.get('id')}")
        except Exception as e:
            log(f"❌ فشل الرفع إلى YouTube: {e}", "error")


def cleanup_workspace():
    if not CONFIG.work_dir.exists():
        return

    try:
        shutil.rmtree(CONFIG.work_dir)
        log("🧹 تم حذف Workspace بالكامل.")
        log("🚫 لا توجد ملفات Cache أو ملفات وسيطة متبقية.")
    except Exception as e:
        log(f"⚠️ تعذر تنظيف Workspace: {e}", "warning")


async def main_pipeline():
    started_total = time.time()

    prepare_fresh_workspace()

    log(
        f"🚀 Universal Investigative Documentary Engine "
        f"{ENGINE_VERSION}"
    )
    log(f"🎯 Topic: {CONFIG.topic}")

    story_engine = StoryScoutEngine()
    story = story_engine.inspect_and_plan()

    audio_engine = MasterAudioStudio()
    master_audio = audio_engine.produce_master_track(story)

    slicer = WordSyncSlicer()

    shots = slicer.align_and_slice(
        master_audio,
        story["part_1"] + "\n" + story["part_2"]
    )

    subtitle_path = CONFIG.work_dir / "subtitles.ass"
    write_subtitles_ass(shots, subtitle_path)

    media_results = await scout_all_media(shots, story)

    assembly = AssemblyEngine()
    rendered = []

    log(f"🎬 بدء Render لـ {len(media_results)} لقطة...")

    for item in media_results:
        rendered_clip = assembly.render_sub_clip(item)
        rendered.append(rendered_clip)

    final_video = assembly.assemble_final_cut(
        rendered,
        subtitle_path
    )

    # ==========================================
    # إضافة عملية الرفع إلى جوجل درايف ويوتيوب هنا
    # ==========================================
    uploader = GoogleUploader(CONFIG.google_client_id, CONFIG.google_client_secret, CONFIG.google_refresh_token)
    
    if uploader.creds:
        log("🔄 جاري بدء عمليات الرفع إلى Google Services...")
        
        # الرفع إلى جوجل درايف
        await asyncio.to_thread(uploader.upload_to_drive, final_video, CONFIG.topic_clean)
        
        # الرفع إلى يوتيوب
        yt_description = f"وثائقي: {CONFIG.topic}\nتم الإنتاج آلياً بواسطة Universal Documentary Engine."
        await asyncio.to_thread(uploader.upload_to_youtube, final_video, CONFIG.topic_clean, yt_description)

    cleanup_workspace()

    elapsed_total = time.time() - started_total

    log(
        f"🏁 اكتملت العملية بالكامل في "
        f"{elapsed_total / 60:.2f} دقيقة."
    )
    log(f"📌 الفيديو النهائي: {final_video}")

    return final_video


if __name__ == "__main__":
    try:
        asyncio.run(main_pipeline())

    except KeyboardInterrupt:
        log("🛑 تم إيقاف العملية بواسطة المستخدم.", "warning")
        cleanup_workspace()
        sys.exit(130)

    except Exception as e:
        log(f"💥 PIPELINE FAILED: {e}", "error")
        cleanup_workspace()
        sys.exit(1)
