#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
V28 - ANTI-DUPLICATION + CONTEXT-AWARE DIRECTOR + GOOGLE UPLOAD

- Global Memory Tracker prevents any media from being used twice.
- Random shuffle of API results ensures fresh visual selection.
- Director assigns sources AND writes specific "Reviewer Context".
- Reviewer AI evaluates media based on Shot Text + Overall Topic + Director's Instructions.
- Auto-uploads final render to Google Drive and YouTube via Refresh Token.
- Gemini keys rotate automatically.
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

from pathlib import Path
from datetime import datetime

import requests
from google import genai
from google.genai import types

# مكتبات الرفع إلى Google Drive و YouTube
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ENGINE_VERSION = "V28-ANTI-DUPLICATION-UPLOAD"

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

        # نظام تتبع الملفات المستخدمة لمنع التكرار
        self.used_media_ids = set()
        self.used_media_lock = threading.Lock()

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


def probe_duration(path):
    if not path or not os.path.exists(path):
        return 0.0
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
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
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0", str(path)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=20
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


def run_cmd(cmd, timeout=300):
    return subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)


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
    match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
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
TOPIC: {CONFIG.topic}
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
"""
        try:
            result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", "high", "--dangerously-skip-permissions", "-p", prompt], timeout=300)
            data = extract_json(result.stdout.strip())
            if not data or not data.get("part_1") or not data.get("part_2"):
                raise RuntimeError("AGY returned invalid JSON or empty parts.")
            self.script = data
            log("📝 تم توليد السيناريو بنجاح.")
            return data
        except Exception as e:
            log(f"⚠️ فشل AGY في إنشاء السيناريو: {e}", "warning")
            fallback = {
                "story_type": "investigation",
                "primary_english_query": clean_query(CONFIG.topic),
                "part_1": f"في هذه القصة الغامضة نقترب من تفاصيل {CONFIG.topic}. تبدأ الحكاية بتفاصيل تبدو عادية، لكن التناقضات تظهر سريعاً.",
                "part_2": "تظل بعض التفاصيل غير محسومة، ولهذا يجب فصل المعلومات الموثقة عن الروايات المتداولة."
            }
            self.script = fallback
            return fallback

    def direct_storyboard(self, shots):
        log("🎬 [المخرج العام] يضع الخطة ويوجه تعليمات صارمة للمراجع الفوري لكل مشهد...")

        shots_summary = "\n".join([f"Shot {s['index']}: {s['text']}" for s in shots])

        prompt = f"""
You are the Lead Visual Director of this investigative documentary.
TOPIC: {self.script.get('primary_english_query', CONFIG.topic)}

ALL SHOTS IN SEQUENTIAL ORDER:
{shots_summary}

YOUR TASK:
For EVERY shot from 1 to {len(shots)}, provide:
1. "sources": Top 3-5 sources and specific English search queries (1-4 words).
   CRITICAL: DO NOT USE 'PEXELS' FOR EVERY SHOT. You MUST drastically diversify. Use FBI_ARCHIVE for evidence, LOC for history, WIKIPEDIA for portraits, EUROPEANA for documents, PIXABAY for moody nature. Mix them heavily!
2. "reviewer_context": A strict instruction IN ARABIC to the Reviewer AI explaining EXACTLY what this shot should look like, the visual vibe, and what types of media to strictly REJECT.

Available Sources: PEXELS, PIXABAY, WIKIPEDIA, OPENVERSE, EUROPEANA, NASA, LOC, GIPHY, FBI_ARCHIVE.

Return ONLY a valid JSON object:
{{
  "1": {{
    "sources": [
      {{"source": "FBI_ARCHIVE", "search_query": "crime scene file"}},
      {{"source": "LOC", "search_query": "old newspaper"}}
    ],
    "reviewer_context": "هذا المشهد افتتاحي يجب أن يكون غامضاً ومظلماً. اقبل فقط اللقطات التي توحي بالسرية مثل ملفات قديمة. ارفض اللقطات المبهجة."
  }}
}}
"""
        try:
            result = run_cmd([
                "agy",
                "--model", AGY_SCRIPT_MODEL,
                "--effort", "high",
                "--dangerously-skip-permissions",
                "-p", prompt
            ], timeout=240)

            board = extract_json(result.stdout.strip())
            if isinstance(board, dict):
                matched = 0
                for shot in shots:
                    idx_str = str(shot["index"])
                    if idx_str in board and isinstance(board[idx_str], dict):
                        shot["director_plan"] = board[idx_str].get("sources", [])
                        shot["reviewer_context"] = board[idx_str].get("reviewer_context", "تأكد من أن المقطع يتوافق مع النص.")
                        matched += 1
                    else:
                        shot["director_plan"] = [{"source": "PIXABAY", "search_query": clean_query(shot["text"]) or "mystery"}, {"source": "WIKIPEDIA", "search_query": "archive"}]
                        shot["reviewer_context"] = "اعتمد على النص فقط في تقييمك، تأكد من وجود غموض ودراما."
                log(f"🎯 [المخرج العام] وزع الخطة والتعليمات بنجاح لـ {matched}/{len(shots)} مشهد.")
                return shots
        except Exception as e:
            log(f"⚠️ تعذر استكمال خطة المخرج الشاملة: {e}", "warning")

        for shot in shots:
            shot["director_plan"] = [{"source": "FBI_ARCHIVE", "search_query": "investigation"}, {"source": "PEXELS", "search_query": "mystery"}]
            shot["reviewer_context"] = "تأكد من ملاءمة اللقطة للنص وتجنب اللقطات المبهجة أو غير المتعلقة بالتحقيق."
        return shots


def is_rate_limit_error(error):
    text = str(error).lower()
    return any(item in text for item in ["429", "resource_exhausted", "rate limit", "quota", "too many requests"])


class MasterAudioStudio:
    def __init__(self):
        self.model = TTS_MODEL

    def _generate_full_narration(self, full_text, out_wav):
        out_wav = Path(out_wav)
        if out_wav.exists():
            try: out_wav.unlink()
            except: pass

        attempted = set()
        total_keys = len(CONFIG.gemini_keys)

        for attempt in range(total_keys):
            key_index, api_key = GEMINI_POOL.acquire(excluded=attempted)
            attempted.add(key_index)
            display_key = key_index + 1

            try:
                client = genai.Client(api_key=api_key)
                config = types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))
                    )
                )
                instruction = "[INSTRUCTION: Chilling authoritative Arabic documentary narrator. Read the ENTIRE narration exactly from beginning to end.]"
                response = client.models.generate_content(model=self.model, contents=instruction + "\n\n" + full_text, config=config)

                if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                    raise RuntimeError("Gemini returned empty content.")

                inline_data = next((part.inline_data for part in response.candidates[0].content.parts if getattr(part, "inline_data", None)), None)
                if not inline_data:
                    raise RuntimeError("No inline audio data returned.")

                raw_audio = base64.b64decode(inline_data.data) if isinstance(inline_data.data, str) else bytes(inline_data.data)
                
                if raw_audio[:4] == b"RIFF":
                    with open(out_wav, "wb") as f: f.write(raw_audio)
                else:
                    temp_pcm = CONFIG.work_dir / f"full_narration_key{display_key}.pcm"
                    with open(temp_pcm, "wb") as f: f.write(raw_audio)
                    run_cmd(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(temp_pcm), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(out_wav)], timeout=180)
                    try: temp_pcm.unlink()
                    except: pass

                if not is_valid_media(out_wav):
                    raise RuntimeError("Generated full narration WAV failed validation.")
                
                log(f"✅ التعليق الصوتي الماستر نجح باستخدام Gemini Key #{display_key}")
                return True

            except Exception as e:
                GEMINI_POOL.release(key_index)
                if attempt + 1 < total_keys:
                    time.sleep(0.7 if is_rate_limit_error(e) else 0.2)
                continue
            finally:
                GEMINI_POOL.release(key_index)

        raise RuntimeError("❌ انتهت جميع مفاتيح Gemini بدون نجاح في توليد التعليق الصوتي.")

    def produce_master_track(self, script):
        full_narration = f"{script['part_1']}\n\n{script['part_2']}".strip()
        if not full_narration: raise RuntimeError("النص الكامل فارغ.")
        log("🎙️ بدء إنتاج التعليق الصوتي الكامل دفعة واحدة...")
        if not self._generate_full_narration(full_narration, CONFIG.master_audio):
            raise RuntimeError("فشل إنتاج التعليق الصوتي.")
        return CONFIG.master_audio


class WordSyncSlicer:
    def __init__(self):
        self.url = "https://api.groq.com/openai/v1/audio/transcriptions"

    def align_and_slice(self, audio_path, full_script):
        if not CONFIG.groq_api_key: raise RuntimeError("GROQ_API_KEY غير موجود.")
        log("🧠 إرسال الصوت إلى Groq Whisper للتوقيتات الدقيقة...")
        headers = {"Authorization": f"Bearer {CONFIG.groq_api_key}"}
        with open(audio_path, "rb") as audio_file:
            files = {"file": ("master_audio.wav", audio_file, "audio/wav")}
            data = {"model": GROQ_MODEL, "language": "ar", "response_format": "verbose_json", "timestamp_granularities[]": "word"}
            response = requests.post(self.url, headers=headers, files=files, data=data, timeout=180)

        if response.status_code != 200: raise RuntimeError(f"Groq error {response.status_code}: {response.text[:2000]}")
        words = [{"word": str(i["word"]).strip(), "start": float(i["start"]), "end": float(i["end"])} for i in response.json().get("words", []) if i.get("word") and i.get("start") is not None]
        
        shots, current_words, shot_start, last_end = [], [], 0.0, 0.0
        punctuation = (".", "!", "?", "،", "؛", ":", "؟")

        for item in words:
            current_words.append(item)
            last_end = item["end"]
            elapsed = last_end - shot_start
            if elapsed >= 3.5 or (elapsed >= 2.0 and item["word"].endswith(punctuation)):
                text = " ".join(x["word"] for x in current_words).strip()
                if text: shots.append({"index": len(shots) + 1, "start": shot_start, "end": last_end, "duration": max(0.5, last_end - shot_start), "text": text})
                current_words, shot_start = [], last_end

        if current_words:
            text = " ".join(x["word"] for x in current_words).strip()
            if text: shots.append({"index": len(shots) + 1, "start": shot_start, "end": last_end, "duration": max(0.5, last_end - shot_start), "text": text})

        log(f"✂️ تم تقسيم التعليق الصوتي إلى {len(shots)} مشهد مستقل.")
        return shots


def ass_time(seconds):
    h, m = int(seconds // 3600), int((seconds % 3600) // 60)
    return f"{h}:{m:02d}:{seconds - h * 3600 - m * 60:05.2f}"


def write_subtitles_ass(shots, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\nScaledBorderAndShadow: yes\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Noto Sans Arabic,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,70,1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for shot in shots:
            text = shot["text"].replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
            f.write(f"Dialogue: 0,{ass_time(shot['start'])},{ass_time(shot['end'])},Default,,0,0,0,,{{\\fad(120,120)}}{text}\n")


class MediaSources:
    # 💡 قمنا بإضافة نظام التتبع العشوائي (Shuffle & Memory) لكل المصادر لضمان عدم تكرار أي مشهد
    @staticmethod
    def fetch_openverse_image(query, output, attempt=0):
        try:
            response = requests.get("https://api.openverse.org/v1/images/", params={"q": query, "page_size": 20}, timeout=30)
            results = response.json().get("results", [])
            random.shuffle(results)
            for item in results:
                uid = str(item.get("id") or item.get("url"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                url = item.get("thumbnail") or item.get("url")
                if url and requests.get(url, timeout=40).status_code == 200:
                    with open(output, "wb") as f: f.write(requests.get(url).content)
                    if is_valid_visual(output): return output
        except Exception: pass
        return None

    @staticmethod
    def fetch_europeana_image(query, output, attempt=0):
        if not CONFIG.europeana_key: return None
        try:
            response = requests.get("https://api.europeana.eu/record/v2/search.json", params={"wskey": CONFIG.europeana_key, "query": query, "rows": 20}, timeout=30)
            items = response.json().get("items", [])
            random.shuffle(items)
            for item in items:
                uid = str(item.get("id"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                previews = item.get("edmPreview", [])
                if previews and requests.get(previews[0], timeout=40).status_code == 200:
                    with open(output, "wb") as f: f.write(requests.get(previews[0]).content)
                    if is_valid_visual(output): return output
        except Exception: pass
        return None

    @staticmethod
    def fetch_nasa_media(query, output, attempt=0):
        try:
            response = requests.get("https://images-api.nasa.gov/search", params={"q": query, "media_type": "image"}, timeout=30)
            items = response.json().get("collection", {}).get("items", [])
            random.shuffle(items)
            for item in items:
                uid = str(item.get("data", [{}])[0].get("nasa_id") or item.get("href"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                links = item.get("links", [])
                if links and requests.get(links[0].get("href"), timeout=40).status_code == 200:
                    with open(output, "wb") as f: f.write(requests.get(links[0].get("href")).content)
                    if is_valid_visual(output): return output
        except Exception: pass
        return None

    @staticmethod
    def fetch_chronicling_america(query, output, attempt=0):
        try:
            response = requests.get(f"https://www.loc.gov/?fo=json&c=20&q={urllib.parse.quote(query)}", timeout=40)
            results = response.json().get("results", [])
            random.shuffle(results)
            for item in results:
                uid = str(item.get("id") or item.get("url"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                resources = item.get("resources", [])
                if not resources: continue
                image_url = resources[0].get("image_url")
                image_url = image_url[0] if isinstance(image_url, list) else image_url
                if image_url and requests.get(image_url, timeout=40).status_code == 200:
                    with open(output, "wb") as f: f.write(requests.get(image_url).content)
                    if is_valid_visual(output): return output
        except Exception: pass
        return None

    @staticmethod
    def fetch_pixabay_video(query, output, attempt=0):
        if not CONFIG.pixabay_key: return None
        try:
            response = requests.get("https://pixabay.com/api/videos/", params={"key": CONFIG.pixabay_key, "q": query, "per_page": 20}, timeout=30)
            hits = response.json().get("hits", [])
            random.shuffle(hits)
            for hit in hits:
                uid = str(hit.get("id"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                videos = hit.get("videos", {})
                item = videos.get("large") or videos.get("medium") or videos.get("small")
                if item and item.get("url"):
                    r = requests.get(item["url"], stream=True, timeout=60)
                    if r.status_code == 200:
                        with open(output, "wb") as f:
                            for chunk in r.iter_content(1024 * 256):
                                if chunk: f.write(chunk)
                        if is_valid_media(output, 0.5): return output
        except Exception: pass
        return None

    @staticmethod
    def fetch_pexels_video(query, output, attempt=0):
        if not CONFIG.pexels_key: return None
        try:
            response = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": CONFIG.pexels_key}, params={"query": query, "per_page": 20}, timeout=30)
            videos = response.json().get("videos", [])
            random.shuffle(videos)
            for video in videos:
                uid = str(video.get("id"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                files = sorted(video.get("video_files", []), key=lambda x: abs((x.get("width") or 0) - TARGET_W))
                if files:
                    r = requests.get(files[0].get("link"), stream=True, timeout=60)
                    if r.status_code == 200:
                        with open(output, "wb") as f:
                            for chunk in r.iter_content(1024 * 256):
                                if chunk: f.write(chunk)
                        if is_valid_media(output): return output
        except Exception: pass
        return None

    @staticmethod
    def fetch_giphy(query, output, attempt=0):
        if not CONFIG.giphy_key: return None
        try:
            response = requests.get("https://api.giphy.com/v1/gifs/search", params={"api_key": CONFIG.giphy_key, "q": query, "limit": 20, "rating": "pg-13"}, timeout=30)
            data = response.json().get("data", [])
            random.shuffle(data)
            for item in data:
                uid = str(item.get("id"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                mp4 = item.get("images", {}).get("original_mp4", {}).get("mp4")
                if mp4:
                    r = requests.get(mp4, stream=True, timeout=60)
                    if r.status_code == 200:
                        with open(output, "wb") as f:
                            for chunk in r.iter_content(1024 * 256):
                                if chunk: f.write(chunk)
                        if is_valid_media(output): return output
        except Exception: pass
        return None

    @staticmethod
    def fetch_wikipedia_image(query, output, attempt=0):
        try:
            response = requests.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "generator": "search", "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": 20, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 1600, "format": "json"}, timeout=30)
            pages = list(response.json().get("query", {}).get("pages", {}).values())
            random.shuffle(pages)
            for page in pages:
                uid = str(page.get("pageid"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                info = page.get("imageinfo", [])
                if info:
                    url = info[0].get("thumburl") or info[0].get("url")
                    if requests.get(url, timeout=40).status_code == 200:
                        with open(output, "wb") as f: f.write(requests.get(url).content)
                        if is_valid_visual(output): return output
        except Exception: pass
        return None

    @staticmethod
    def fetch_fbi_archive(query, output, attempt=0):
        try:
            response = requests.get("https://archive.org/advancedsearch.php", params={"q": f"title:({query})", "fl[]": ["identifier", "title"], "rows": 20, "output": "json"}, timeout=40)
            docs = response.json().get("response", {}).get("docs", [])
            random.shuffle(docs)
            for doc in docs:
                uid = str(doc.get("identifier"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                meta = requests.get(f"https://archive.org/metadata/{uid}", timeout=40)
                files = meta.json().get("files", [])
                candidates = [(int(item.get("size", 0) or 0), str(item.get("name", ""))) for item in files if str(item.get("name", "")).lower().endswith((".mp4", ".webm", ".mov")) and int(item.get("size", 0) or 0) <= MAX_MEDIA_SIZE_MB * 1024 * 1024]
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    url = f"https://archive.org/download/{uid}/{urllib.parse.quote(candidates[0][1])}"
                    r = requests.get(url, stream=True, timeout=90)
                    if r.status_code == 200:
                        with open(output, "wb") as f:
                            for chunk in r.iter_content(1024 * 256):
                                if chunk: f.write(chunk)
                        if is_valid_media(output): return output
        except Exception: pass
        return None


def create_fallback_visual(text, output):
    result = run_cmd([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x111111:s=1920x1080:r=30", "-t", "5",
        "-vf", "noise=alls=18:allf=t+u,vignette,eq=contrast=1.12:saturation=0.75",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p", str(output)
    ], timeout=60)
    return output if result.returncode == 0 and is_valid_media(output) else None


async def agy_evaluate_scout(media_path, shot, story):
    if not media_path:
        return False, 0.0, 0.0, "ملف الميديا غير موجود."
    
    topic = story.get("primary_english_query", CONFIG.topic)
    director_notes = shot.get("reviewer_context", "لا توجد تعليمات خاصة. تأكد من تطابق المشهد مع النص.")

    prompt = f"""
You are evaluating a media asset for an investigative documentary.

OVERALL DOCUMENTARY TOPIC: {topic}
CURRENT SHOT TEXT: {shot["text"]}

🔴 DIRECTOR'S STRICT INSTRUCTIONS FOR THIS SHOT 🔴:
{director_notes}

LOCAL MEDIA PATH TO EVALUATE: 
{media_path}

Based on the visual content of the media and the Director's instructions, return ONLY valid JSON:
{{
  "decision": "accept" or "reject",
  "score": 0.0,
  "best_start_second": 0.0,
  "reason": "Explain in Arabic WHY you accepted or rejected this specific media. You MUST refer to whether it obeyed the Director's instructions or not."
}}
score must be between 0 and 1.
"""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["agy", "--model", AGY_VISION_MODEL, "--effort", "high", "--dangerously-skip-permissions", "-p", prompt],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180
        )
        data = extract_json(result.stdout)
        if not data:
            return True, 0.5, 0.0, "تم القبول افتراضياً (فشل في استخراج رد التقييم)."
        
        decision = str(data.get("decision", "accept")).lower()
        score = float(data.get("score", 0.5))
        start = float(data.get("best_start_second", 0))
        reason = str(data.get("reason", "لا يوجد تعليل."))
        accepted = (decision not in ("reject", "rejected", "bad") and score >= 0.35)
        return accepted, score, start, reason
    except Exception:
        return True, 0.0, 0.0, "تم القبول افتراضياً بسبب خطأ في أداة التقييم."


async def scout_shot_worker(shot, semaphore, story):
    async with semaphore:
        index = shot["index"]
        base = CONFIG.work_dir / f"shot_{index:03d}"
        video_path = Path(str(base) + ".mp4")
        image_path = Path(str(base) + ".jpg")

        for p in (video_path, image_path):
            if p.exists():
                try: p.unlink()
                except: pass

        plan = shot.get("director_plan", [])
        
        FETCHERS = {
            "PEXELS": (MediaSources.fetch_pexels_video, video_path),
            "PIXABAY": (MediaSources.fetch_pixabay_video, video_path),
            "WIKIPEDIA": (MediaSources.fetch_wikipedia_image, image_path),
            "OPENVERSE": (MediaSources.fetch_openverse_image, image_path),
            "EUROPEANA": (MediaSources.fetch_europeana_image, image_path),
            "NASA": (MediaSources.fetch_nasa_media, image_path),
            "LOC": (MediaSources.fetch_chronicling_america, image_path),
            "GIPHY": (MediaSources.fetch_giphy, video_path),
            "FBI_ARCHIVE": (MediaSources.fetch_fbi_archive, video_path)
        }

        total_attempts = 0

        for directive in plan:
            source_name = directive.get("source", "PEXELS").upper()
            query = directive.get("search_query", "investigation")
            
            if source_name not in FETCHERS:
                continue
                
            fetcher, output_path = FETCHERS[source_name]

            for attempt in range(3):
                if total_attempts >= 15:
                    break
                total_attempts += 1

                try:
                    if output_path.exists(): output_path.unlink()

                    found = await asyncio.to_thread(fetcher, query, output_path, attempt)
                    if not found:
                        break 

                    valid = is_valid_visual(output_path) if output_path.suffix.lower() in (".jpg", ".png", ".jpeg", ".webp") else is_valid_media(output_path)
                    if not valid:
                        continue

                    accepted, score, start, reason = await agy_evaluate_scout(output_path, shot, story)

                    if accepted:
                        log(f"✅ [المراجع الفوري] قَبل المشهد {index} من {source_name} | {reason} (Score: {score:.2f})")
                        return {
                            "shot": shot, "path": str(output_path),
                            "source": source_name, "score": score,
                            "start": start, "duration": probe_duration(output_path)
                        }
                    else:
                        log(f"❌ [المراجع الفوري] رفض المشهد {index} (م{attempt+1} في {source_name}) | {reason}", "warning")

                except Exception as e:
                    log(f"{source_name} Shot {index} Error: {e}", "debug")

            if total_attempts >= 15:
                break

        fallback = CONFIG.work_dir / f"shot_{index:03d}_fallback.mp4"
        result = await asyncio.to_thread(create_fallback_visual, shot["text"], fallback)
        if result:
            log(f"🛟 Shot {index}: فشلت المحاولات ({total_attempts})، تم اعتماد Fallback visual", "warning")
            return {
                "shot": shot, "path": str(fallback), "source": "FALLBACK",
                "score": 0.0, "start": 0.0, "duration": probe_duration(fallback)
            }

        raise RuntimeError(f"Unable to obtain media for shot {index}")


async def scout_all_media(shots, story):
    log(f"🔍 بدء تنفيذ خطة المخرج واختبار الميديا لـ {len(shots)} مشهد عبر {CONCURRENT_WORKERS} مسارات متزامنة...")
    semaphore = asyncio.Semaphore(CONCURRENT_WORKERS)
    tasks = [scout_shot_worker(shot, semaphore, story) for shot in shots]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    successful = []
    for result in results:
        if isinstance(result, Exception):
            log(f"⚠️ Shot failed: {result}", "warning")
        else:
            successful.append(result)
    successful.sort(key=lambda x: x["shot"]["index"])
    if not successful: raise RuntimeError("لم يتم العثور على أي ميديا.")
    return successful


class AssemblyEngine:
    def render_sub_clip(self, item):
        shot, media_path, index = item["shot"], Path(item["path"]), item["shot"]["index"]
        output = CONFIG.work_dir / f"rendered_{index:03d}.mp4"
        if output.exists(): output.unlink()
        
        start = min(float(item.get("start", 0)), max(0, probe_duration(media_path) - 0.1))
        duration = float(shot.get("duration", 3))

        if media_path.suffix.lower() in (".mp4", ".webm", ".mov", ".mkv", ".avi"):
            vf = "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,eq=contrast=1.06:saturation=0.92,vignette,noise=alls=3:allf=t,fps=30"
            cmd = ["ffmpeg", "-y", "-ss", str(start), "-i", str(media_path), "-t", str(duration), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", str(output)]
        else:
            vf = "scale=2208:1248:force_original_aspect_ratio=increase,crop=2208:1248,zoompan=z='min(zoom+0.0008,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=30,eq=contrast=1.06:saturation=0.92,vignette,noise=alls=3:allf=t"
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(media_path), "-t", str(duration), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", str(output)]
            
        result = run_cmd(cmd, timeout=300)
        if result.returncode != 0 or not is_valid_media(output): raise RuntimeError(f"Render shot {index} failed.")
        return output

    def assemble_final_cut(self, rendered, subtitle_path):
        concat_file = CONFIG.work_dir / "video_concat.txt"
        with open(concat_file, "w", encoding="utf-8") as f:
            for path in rendered: f.write(f"file '{Path(path).resolve()}'\n")

        temp_video = CONFIG.work_dir / "temp_video_track.mp4"
        if run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(temp_video)]).returncode != 0:
            run_cmd(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c:v", "libx264", "-preset", "fast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", "30", str(temp_video)])

        subtitle_filter = "subtitles=" + str(Path(subtitle_path).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        log("🎞️ بدء Final FFmpeg Assembly...")
        
        result = run_cmd([
            "ffmpeg", "-y", "-i", str(temp_video), "-i", str(CONFIG.master_audio), "-vf", subtitle_filter,
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "1", "-shortest", "-movflags", "+faststart", str(CONFIG.final_video)
        ], timeout=1200)

        if result.returncode != 0 or not is_valid_media(CONFIG.final_video, 1):
            raise RuntimeError("Final assembly failed.")

        log(f"🎉 FINAL DOCUMENTARY READY | {probe_duration(CONFIG.final_video)/60:.2f} mins | {CONFIG.final_video.stat().st_size/1024/1024:.1f} MB")
        return CONFIG.final_video


class GoogleUploader:
    def __init__(self, client_id, client_secret, refresh_token):
        self.creds = None
        if client_id and client_secret and refresh_token:
            self.creds = Credentials(token=None, refresh_token=refresh_token, token_uri="https://oauth2.googleapis.com/token", client_id=client_id, client_secret=client_secret)

    def upload_to_drive(self, file_path, title):
        if not self.creds: return
        try:
            log(f"☁️ بدء الرفع إلى Google Drive: {title}")
            service = build('drive', 'v3', credentials=self.creds, cache_discovery=False)
            file = service.files().create(body={'name': f"{title}.mp4"}, media_body=MediaFileUpload(str(file_path), mimetype='video/mp4', resumable=True), fields='id').execute()
            log(f"✅ تم الرفع إلى Drive بنجاح! الرابط: https://drive.google.com/file/d/{file.get('id')}/view")
        except Exception as e: log(f"❌ فشل الرفع إلى Drive: {e}", "error")

    def upload_to_youtube(self, file_path, title, description):
        if not self.creds: return
        try:
            log(f"▶ بدء الرفع إلى YouTube: {title}")
            service = build('youtube', 'v3', credentials=self.creds, cache_discovery=False)
            body = {'snippet': {'title': title, 'description': description, 'tags': ['وثائقي', 'تحقيق', 'تلقائي', 'AI'], 'categoryId': '24'}, 'status': {'privacyStatus': 'private'}}
            response = service.videos().insert(part=','.join(body.keys()), body=body, media_body=MediaFileUpload(str(file_path), mimetype='video/mp4', resumable=True)).execute()
            log(f"✅ تم الرفع إلى YouTube بنجاح! الرابط: https://youtu.be/{response.get('id')}")
        except Exception as e: log(f"❌ فشل الرفع إلى YouTube: {e}", "error")


def cleanup_workspace():
    if CONFIG.work_dir.exists():
        try: shutil.rmtree(CONFIG.work_dir); log("🧹 تم حذف Workspace بالكامل.")
        except Exception as e: log(f"⚠️ تعذر تنظيف Workspace: {e}", "warning")


async def main_pipeline():
    started_total = time.time()
    prepare_fresh_workspace()
    
    log(f"🚀 Universal Investigative Engine {ENGINE_VERSION} | Topic: {CONFIG.topic}")

    # 1. صناعة النص الاستقصائي الشامل
    story_engine = StoryScoutEngine()
    story = story_engine.inspect_and_plan()

    # 2. توليد التعليق الصوتي الماستر دفعة واحدة
    master_audio = MasterAudioStudio().produce_master_track(story)

    # 3. تقطيع الجمل ومزامنتها عبر Groq Whisper
    shots = WordSyncSlicer().align_and_slice(master_audio, story["part_1"] + "\n" + story["part_2"])
    
    # 4. المخرج العام يضع خطة הـ Storyboard الشاملة والتعليمات
    shots = story_engine.direct_storyboard(shots)

    # 5. كتابة الترجمة
    subtitle_path = CONFIG.work_dir / "subtitles.ass"
    write_subtitles_ass(shots, subtitle_path)

    # 6. جلب وتقييم الميديا مع تمرير توجيهات المخرج للمراجع الفوري (الآن مع ذاكرة تمنع التكرار)
    media_results = await scout_all_media(shots, story)

    # 7. المونتاج والرندرة
    assembly = AssemblyEngine()
    rendered = [assembly.render_sub_clip(item) for item in media_results]
    final_video = assembly.assemble_final_cut(rendered, subtitle_path)

    # 8. الرفع إلى Drive و YouTube
    uploader = GoogleUploader(CONFIG.google_client_id, CONFIG.google_client_secret, CONFIG.google_refresh_token)
    if uploader.creds:
        log("🔄 جاري بدء عمليات الرفع إلى Google Services...")
        await asyncio.to_thread(uploader.upload_to_drive, final_video, CONFIG.topic_clean)
        await asyncio.to_thread(uploader.upload_to_youtube, final_video, CONFIG.topic_clean, f"وثائقي: {CONFIG.topic}\nتم الإنتاج آلياً بواسطة Documentary Engine.")

    cleanup_workspace()
    log(f"🏁 اكتملت العملية بالكامل في {(time.time() - started_total) / 60:.2f} دقيقة.")
    return final_video

if __name__ == "__main__":
    try: asyncio.run(main_pipeline())
    except KeyboardInterrupt: log("🛑 تم الإيقاف.", "warning"); cleanup_workspace(); sys.exit(130)
    except Exception as e: log(f"💥 PIPELINE FAILED: {e}", "error"); cleanup_workspace(); sys.exit(1)
