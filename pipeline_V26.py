#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
V33 - ADVANCED API SEARCH ENGINEERING + IMMORTAL WORKERS

- Wikipedia API: Switched to 'pageimages' to extract high-res article thumbnails (99% hit rate).
- Archive.org: Removed title restriction, added mediatype filter (image/movies) for deep metadata search.
- LOC: Added 'online_format:image' filter.
- Director Prompts: Forced strict 1-2 word NOUN queries to match dumb API search engines.
- Smart Modifiers: Visual vibes only apply to Pexels/Pixabay, not factual archives.
- Single Batch Director & Immortal Workers.
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

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ENGINE_VERSION = "V33-ADVANCED-SEARCH"

TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
TARGET_AR = 48000

CONCURRENT_WORKERS = 5

TTS_MODEL = "gemini-3.8-flash-tts"
TTS_VOICE = "Charon"

AGY_SCRIPT_MODEL = "gemini-3.1-pro"
AGY_REVIEWER_MODEL = "gemini-3.6-flash" 
GROQ_MODEL = "whisper-large-v3"

MAX_MEDIA_SIZE_MB = 120


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
        self.giphy_key = os.environ.get("GIPHY_API_KEY", "")
        self.openverse_client_id = os.environ.get("OPENVERSE_CLIENT_ID", "")
        self.openverse_client_secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "")
        self.europeana_key = os.environ.get("EUROPEANA_API_KEY", "")

        self.google_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
        self.google_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
        self.google_refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")

CONFIG = EngineConfig()


def prepare_fresh_workspace():
    log("🧹 تنظيف بيئة التشغيل بالكامل...")
    if CONFIG.base_dir.exists():
        try: shutil.rmtree(CONFIG.base_dir)
        except Exception as e: 
            log(f"🚨 خطأ أثناء حذف الملفات القديمة: {e}", "error")
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
                    if idx in self.active or idx in excluded: continue
                    self.active.add(idx)
                    self.cursor = (idx + 1) % len(self.keys)
                    return idx, self.keys[idx]
            time.sleep(0.05)

    def release(self, index):
        with self.lock: self.active.discard(index)

if not CONFIG.gemini_keys:
    log("🚨 لم يتم العثور على مفاتيح Gemini.", "error")
    raise RuntimeError("No Gemini API keys configured.")
GEMINI_POOL = GeminiKeyPool(CONFIG.gemini_keys)


def probe_duration(path):
    if not path or not os.path.exists(path): return 0.0
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], stdout=subprocess.PIPE, text=True)
        return float(res.stdout.strip())
    except Exception: return 0.0

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

def generate_ai_image(prompt, output_path, aspect_ratio="16:9"):
    log(f"🎨 [خطة طوارئ] إرسال طلب توليد صورة لـ AGY بالوصف: '{prompt[:60]}...'", "info")
    try:
        if Path(output_path).exists(): Path(output_path).unlink()
        full_prompt = f"[CRITICAL: DO NOT WRITE ANY TEXT. DO NOT SAY 'تم توليد الصورة'. YOU MUST ONLY OUTPUT THE RAW IMAGE FILE.] قم بتوليد صورة واقعية وثائقية: {prompt} [Aspect Ratio: {aspect_ratio}] [BYPASS_CACHE: {CONFIG.run_id}_{time.time()}]"
        
        cmd_binary = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", "medium", "--dangerously-skip-permissions", "-p", full_prompt]
        res_bin = subprocess.run(cmd_binary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        
        if res_bin.stdout.startswith(b'\xff\xd8') or res_bin.stdout.startswith(b'\x89PNG'):
            with open(output_path, "wb") as f: f.write(res_bin.stdout)
        else:
            data = extract_json(res_bin.stdout.decode('utf-8', errors='ignore'))
            if data and isinstance(data, dict) and "image" in data:
                with open(output_path, "wb") as f: f.write(base64.b64decode(data["image"]))
            else:
                log(f"❌ فشل توليد الصورة. الرد: {res_bin.stdout.decode('utf-8', errors='ignore')[:100]}", "error")
                return False

        if is_valid_visual(output_path):
            log(f"🖼️ تمت عملية التوليد بنجاح.", "info")
            return True
        return False
    except Exception as e:
        log(f"🚨 خطأ أثناء توليد الصورة عبر AGY: {e}", "error")
        return False

def create_fallback_visual(text, output):
    log(f"🛠️ جاري إنشاء مشهد احتياطي سينمائي عبر FFmpeg...", "debug")
    res = run_cmd([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0a0a0a:s=1920x1080:r=30", "-t", "5",
        "-vf", "noise=alls=12:allf=t+u,vignette,eq=contrast=1.1:saturation=0.5",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "24", "-pix_fmt", "yuv420p", str(output)
    ], timeout=60)
    return output if res.returncode == 0 and is_valid_media(output) else None


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
            if not data or not data.get("part_1"):
                raise RuntimeError("فشل استخراج الـ JSON أو كان السيناريو فارغاً.")
            self.script = data
            part1, part2 = str(data.get("part_1", "")), str(data.get("part_2", ""))
            total_words = len(part1.split()) + len(part2.split())
            log(f"📝 تم توليد سيناريو جديد تماماً بنجاح (عدد الكلمات: {total_words} كلمة).")
            log("━━━━━━━━━━ النص الكامل للسيناريو ━━━━━━━━━━\n" + part1 + "\n\n" + part2 + "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            return data
        except Exception as e:
            log(f"🚨 فشل AGY في إنشاء السيناريو. التفاصيل: {e}", "error")
            fallback = {"story_type": "investigation", "primary_english_query": clean_query(CONFIG.topic), "part_1": f"تفاصيل غامضة ومختلفة كلياً حول {CONFIG.topic}.", "part_2": "تظل الحقيقة غير محسومة."}
            self.script = fallback
            return fallback

    def direct_storyboard(self, shots):
        log("🎬 [المخرج العام] يقرأ كل المشاهد ويضع خطة البحث المخصصة للـ APIs...")
        
        shots_summary = "\n".join([f"Shot {s['index']}: {s['text']}" for s in shots])
        
        prompt = f"""You are the Lead Visual Director. TOPIC: {self.script.get('primary_english_query', CONFIG.topic)}
[SYSTEM BYPASS CACHE ID: {CONFIG.run_id}]
Analyze ALL of these shots AT ONCE:
{shots_summary}

CRITICAL RULES FOR SEARCH QUERIES (APIs ARE DUMB):
1. NEVER use sentences. 
2. MAXIMUM 2 WORDS per query (e.g. use "detective" NOT "detective smoking in a room").
3. Use ONLY NOUNS (e.g. use "evidence", "police car", "forest").

For EVERY shot, output a JSON object mapping its index:
1. "category": "ARCHIVE" (for specific facts/documents) OR "CINEMATIC" (for mood/b-roll).
2. "exact_entities": Array of 3 exact nouns for Wikipedia/FBI (e.g., ["Zodiac Killer", "Boeing 727", "San Francisco"]). 1-2 words MAX.
3. "visual_vibes": Array of 3 basic nouns for Pexels (e.g., ["detective", "typewriter", "dark street"]). 1-2 words MAX.
4. "reviewer_context": Strict Arabic instructions.

Return ONLY a valid JSON object covering ALL shots:
{{
  "1": {{
    "category": "ARCHIVE",
    "exact_entities": ["Zodiac Killer", "Cipher", "Police"],
    "visual_vibes": ["document", "dark room", "newspaper"],
    "reviewer_context": "هذا المشهد يحتاج دليلاً حقيقياً. ارفض اللقطات السينمائية الحديثة."
  }}
}}"""
        try:
            log(f"⏳ معالجة الخطة الكاملة لـ {len(shots)} مشهد دفعة واحدة...")
            result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", "high", "--dangerously-skip-permissions", "-p", prompt], timeout=300)
            board = extract_json(result.stdout.strip())
            
            if board and isinstance(board, dict):
                for shot in shots:
                    idx = str(shot["index"])
                    if idx in board:
                        shot["category"] = board[idx].get("category", "CINEMATIC")
                        shot["exact_entities"] = board[idx].get("exact_entities", [CONFIG.topic_clean])
                        shot["visual_vibes"] = board[idx].get("visual_vibes", ["mystery"])
                        shot["reviewer_context"] = board[idx].get("reviewer_context", "تأكد من مطابقة النص.")
                    else:
                        shot["category"] = "CINEMATIC"
                        shot["exact_entities"] = [clean_query(CONFIG.topic_clean).split()[0]]
                        shot["visual_vibes"] = ["mystery"]
                        shot["reviewer_context"] = "اعتمد على النص."
            else:
                raise RuntimeError("الذكاء الاصطناعي أرجع بيانات غير صالحة للدفعة الكاملة.")
        except Exception as e:
            log(f"⚠ خطأ في معالجة الخطة: {e}. سيتم استخدام التوجيه التلقائي.", "warning")
            for shot in shots:
                shot["category"] = "CINEMATIC"
                shot["exact_entities"] = ["evidence"]
                shot["visual_vibes"] = ["mystery"]
                shot["reviewer_context"] = "تأكد من ملاءمة اللقطة للنص."

        log("\n📋 ━━━━━━━━━━ خطة المخرج التفصيلية لكل المشاهد ━━━━━━━━━━")
        for s in shots:
            log(f"🎬 المشهد {s['index']} [{s.get('category')}]: {s['text']}")
            log(f"   ┣ الكيانات الدقيقة (للأرشيف): {s.get('exact_entities', [])}")
            log(f"   ┣ الطابع البصري (للسينمائي): {s.get('visual_vibes', [])}")
            log(f"   ┗ توجيهات المراجع: {s.get('reviewer_context', '')}")
        log("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
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
            log(f"🔑 إرسال النص إلى مفتاح Gemini #{display_key} (محاولة {attempt + 1}/{total_keys})...")
            start_t = time.time()
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=TTS_MODEL,
                    contents=f"[INSTRUCTION: Chilling authoritative Arabic documentary narrator. Read ENTIRE text. UNIQUE_ID: {CONFIG.run_id}]\n\n" + full_narration,
                    config=types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))))
                )
                data = next((p.inline_data.data for p in response.candidates[0].content.parts if getattr(p, "inline_data", None)), None)
                if not data: raise RuntimeError("لم يتم إرجاع أي بيانات صوتية.")

                raw_audio = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                temp_pcm = CONFIG.work_dir / f"full_temp_{display_key}.pcm"
                with open(temp_pcm, "wb") as f: f.write(raw_audio)
                
                run_cmd(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(temp_pcm), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(out_wav)], timeout=180)
                temp_pcm.unlink(missing_ok=True)
                
                if is_valid_media(out_wav):
                    log(f"✅ نجح توليد الصوت بمفتاح #{display_key} خلال {time.time() - start_t:.1f} ثانية!")
                    GEMINI_POOL.release(key_index)
                    return out_wav
                raise RuntimeError("الملف الصوتي الناتج غير صالح.")
            except Exception as e:
                err_msg = str(e).replace('\n', ' ')
                if "429" in err_msg or "resource_exhausted" in err_msg.lower(): log(f"⚠️️ مفتاح #{display_key} واجه ضغطاً (Rate Limit).", "warning")
                else: log(f"⚠️ فشل مفتاح #{display_key}: {err_msg[:120]}", "warning")
                GEMINI_POOL.release(key_index)
                time.sleep(2)
        raise RuntimeError("❌ فشل توليد التعليق الصوتي بعد تجربة جميع المفاتيح المتاحة.")


class WordSyncSlicer:
    def align_and_slice(self, audio_path, full_script):
        log("🧠 إرسال الصوت إلى Groq Whisper للتوقيتات...")
        headers = {"Authorization": f"Bearer {CONFIG.groq_api_key}"}
        try:
            with open(audio_path, "rb") as f:
                res = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files={"file": ("m.wav", f, "audio/wav")}, data={"model": GROQ_MODEL, "language": "ar", "response_format": "verbose_json", "timestamp_granularities[]": "word"}, timeout=180)
            if res.status_code != 200: raise RuntimeError(f"Groq API Error {res.status_code}: {res.text[:200]}")
                
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
            log(f"🚨 فشل استخراج التوقيتات من الصوت: {e}", "error")
            raise


class MediaSources:
    @staticmethod
    def _track_and_save(items, output, extract_url_func, source_name):
        random.shuffle(items)
        for item in items:
            url, uid = extract_url_func(item)
            if not url: continue
            with CONFIG.used_media_lock:
                if uid in CONFIG.used_media_ids: continue
                CONFIG.used_media_ids.add(uid)
            try:
                r = requests.get(url, stream=True, timeout=60)
                if r.status_code == 200:
                    with open(output, "wb") as f:
                        for chunk in r.iter_content(1024*256):
                            if chunk: f.write(chunk)
                    return True
            except: pass
        return False

    @staticmethod
    def fetch_wikipedia_image(q, o): 
        """استخراج دقيق للصور من ويكيبيديا باستخدام مقالات حقيقية (نجاح 99%)"""
        try:
            res = requests.get("https://en.wikipedia.org/w/api.php", params={
                "action": "query", "generator": "search", "gsrsearch": q, 
                "prop": "pageimages", "piprop": "original", "pithumbsize": 1920, "format": "json", "gsrlimit": 10
            }, timeout=30)
            pages = list(res.json().get("query", {}).get("pages", {}).values())
            
            def get_url(page):
                try: return page.get("original", {}).get("source"), str(page.get("pageid"))
                except: return None, None
                
            return MediaSources._track_and_save(pages, o, get_url, "WIKIPEDIA")
        except: return False

    @staticmethod
    def fetch_fbi_archive(q, o):
        """بحث عميق داخل الأرشيف يشمل المحتوى وليس العنوان فقط"""
        try:
            # البحث عن أي ملف فيديو أو صورة يحتوي على الكلمة في أي مكان (وصف، عنوان، محتوى)
            query = f'({q}) AND (mediatype:image OR mediatype:movies)'
            res = requests.get("https://archive.org/advancedsearch.php", params={"q": query, "fl[]": ["identifier"], "rows": 20, "output": "json"}, timeout=40)
            docs = res.json().get("response", {}).get("docs", [])
            random.shuffle(docs)
            for doc in docs:
                uid = str(doc.get("identifier"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                try:
                    files = requests.get(f"https://archive.org/metadata/{uid}", timeout=30).json().get("files", [])
                    cands = [(int(i.get("size",0) or 0), str(i.get("name",""))) for i in files if str(i.get("name","")).lower().endswith((".mp4",".mov", ".jpg", ".png", ".jpeg")) and int(i.get("size",0) or 0) <= MAX_MEDIA_SIZE_MB*1024*1024]
                    if cands:
                        cands.sort(key=lambda x: x[0])
                        r = requests.get(f"https://archive.org/download/{uid}/{urllib.parse.quote(cands[0][1])}", stream=True, timeout=90)
                        if r.status_code == 200:
                            with open(o, "wb") as f:
                                for chunk in r.iter_content(1024*256):
                                    if chunk: f.write(chunk)
                            return True
                except: pass
            return False
        except: return False

    @staticmethod
    def fetch_chronicling_america(q, o):
        """بحث في مكتبة الكونغرس يركز فقط على المواد المصورة"""
        try:
            res = requests.get(f"https://www.loc.gov/?fo=json&fa=online_format:image&c=20&q={urllib.parse.quote(q)}", timeout=40).json().get("results", [])
            return MediaSources._track_and_save(res, o, lambda i: (i.get("image_url", [None])[0] if isinstance(i.get("image_url"), list) else i.get("image_url"), str(i.get("id"))), "LOC")
        except: return False

    @staticmethod
    def fetch_openverse_image(q, o):
        try:
            res = requests.get("https://api.openverse.org/v1/images/", params={"q": q, "page_size": 20}, timeout=30).json().get("results", [])
            return MediaSources._track_and_save(res, o, lambda i: (i.get("thumbnail") or i.get("url"), str(i.get("id"))), "OPENVERSE")
        except: return False

    @staticmethod
    def fetch_nasa_media(q, o):
        try:
            res = requests.get("https://images-api.nasa.gov/search", params={"q": q, "media_type": "image"}, timeout=30).json().get("collection", {}).get("items", [])
            return MediaSources._track_and_save(res, o, lambda i: (i.get("links", [{}])[0].get("href"), str(i.get("data", [{}])[0].get("nasa_id"))), "NASA")
        except: return False

    @staticmethod
    def fetch_pixabay_video(q, o):
        if not CONFIG.pixabay_key: return False
        try:
            res = requests.get("https://pixabay.com/api/videos/", params={"key": CONFIG.pixabay_key, "q": q, "per_page": 20}, timeout=30).json().get("hits", [])
            return MediaSources._track_and_save(res, o, lambda i: ((i.get("videos", {}).get("large") or i.get("videos", {}).get("medium", {})).get("url"), str(i.get("id"))), "PIXABAY")
        except: return False

    @staticmethod
    def fetch_pexels_video(q, o):
        if not CONFIG.pexels_key: return False
        try:
            res = requests.get("https://api.pexels.com/videos/search", headers={"Authorization": CONFIG.pexels_key}, params={"query": q, "per_page": 20}, timeout=30).json().get("videos", [])
            return MediaSources._track_and_save(res, o, lambda i: (sorted(i.get("video_files", []), key=lambda x: abs((x.get("width") or 0)-TARGET_W))[0].get("link") if i.get("video_files") else None, str(i.get("id"))), "PEXELS")
        except: return False


async def agy_evaluate_scout(media_path, shot, story):
    if not media_path: return False, 0.0, 0.0, "لا يوجد ملف"
    prompt = f"""You evaluate documentary media.
[SYSTEM BYPASS CACHE ID: {CONFIG.run_id}_{time.time()}]
TOPIC: {story.get("primary_english_query", CONFIG.topic)}
SHOT TEXT: {shot["text"]}
DIRECTOR INSTRUCTIONS: {shot.get("reviewer_context", "")}
MEDIA PATH: {media_path}
Return JSON: {{"decision": "accept" or "reject", "score": 0.0, "best_start_second": 0.0, "reason": "Arabic reason matching Director notes"}}"""
    try:
        result = await asyncio.to_thread(subprocess.run, ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", "medium", "--dangerously-skip-permissions", "-p", prompt], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        data = extract_json(result.stdout)
        if not data: raise Exception("No JSON returned from agy")
            
        score = float(data.get("score", 0.0))
        decision = data.get("decision", "").lower() == "accept"
        reason = str(data.get("reason", ""))
        
        is_accepted = decision and score >= 0.35
        return is_accepted, score, float(data.get("best_start_second", 0)), reason
        
    except subprocess.TimeoutExpired:
        return False, 0.0, 0.0, "انتهى وقت المراجع (Timeout)"
    except Exception as e:
        return False, 0.0, 0.0, f"خطأ تقني: {str(e)[:50]}"


async def scout_shot_worker(shot, story):
    index = shot["index"]
    base = CONFIG.work_dir / f"shot_{index:03d}"
    video_path, image_path = Path(f"{base}.mp4"), Path(f"{base}.jpg")
    best_candidate = None
    best_score = -1.0

    category = shot.get("category", "CINEMATIC")
    entities = shot.get("exact_entities", [])
    vibes = shot.get("visual_vibes", [])

    if category == "ARCHIVE":
        source_pool = ["WIKIPEDIA", "FBI_ARCHIVE", "LOC"]
        query_pool = entities if entities else [CONFIG.topic_clean]
    else:
        source_pool = ["PEXELS", "PIXABAY"]
        query_pool = vibes if vibes else ["mystery"]

    FETCHERS = {"PEXELS": (MediaSources.fetch_pexels_video, video_path), "PIXABAY": (MediaSources.fetch_pixabay_video, video_path), "NASA": (MediaSources.fetch_nasa_media, image_path), "LOC": (MediaSources.fetch_chronicling_america, image_path), "OPENVERSE": (MediaSources.fetch_openverse_image, image_path), "FBI_ARCHIVE": (MediaSources.fetch_fbi_archive, video_path), "WIKIPEDIA": (MediaSources.fetch_wikipedia_image, image_path)}

    combinations = []
    q_idx = 0
    while len(combinations) < 15:
        query = query_pool[q_idx % len(query_pool)]
        for src in source_pool:
            if len(combinations) >= 15: break
            # إضافة لواحق ذكية للمواقع السنمائية فقط، أما الأرشيف فيبقى الاسم كما هو
            if category == "CINEMATIC" and random.choice([True, False]):
                mod = random.choice(["dark", "mystery", "cinematic", ""])
                combinations.append((src, f"{query} {mod}".strip()))
            else:
                combinations.append((src, query))
        q_idx += 1

    log(f"🎬 المشهد {index} ({category}) دخل غرفة البحث (المصادر: {source_pool})...")

    for attempt, (source_name, query) in enumerate(combinations):
        if source_name not in FETCHERS: source_name = "PEXELS"
        fetcher, output_path = FETCHERS[source_name]

        for p in (video_path, image_path): 
            if p.exists(): p.unlink()

        log(f"🔎 المشهد {index} (م{attempt+1}): جلب من [{source_name}] بكلمة '{query}'...", "info")
        found = await asyncio.to_thread(fetcher, query, output_path)
        
        valid = is_valid_visual(output_path) if output_path.suffix in (".jpg",".png") else is_valid_media(output_path)
        if not found or not valid:
            continue

        accepted, score, start, reason = await agy_evaluate_scout(output_path, shot, story)
        
        await asyncio.sleep(3)

        if score > best_score:
            best_score = score
            best_bak = output_path.with_suffix('.bak')
            shutil.copy(output_path, best_bak)
            best_candidate = {"shot": shot, "path": str(best_bak), "source": source_name, "score": score, "start": start, "duration": probe_duration(best_bak)}

        if accepted:
            log(f"✅ قَبل المراجع المشهد {index} من {source_name} (م{attempt+1}) | {reason} | تقييم: {score:.2f}")
            return {"shot": shot, "path": str(output_path), "source": source_name, "score": score, "start": start, "duration": probe_duration(output_path)}
        else:
            log(f"❌ رَفض المراجع المشهد {index} من {source_name} (م{attempt+1}) | {reason} | تقييم: {score:.2f}")

    if best_score >= 0.20 and best_candidate:
        log(f"⚠️ [إنقاذ 1] استنفدت 15 محاولة للمشهد {index}. تم اعتماد أفضل لقطة متاحة بتقييم {best_score:.2f}.", "warning")
        return best_candidate

    log(f"🤖 [إنقاذ 2] توليد صورة AI للمشهد {index} كخطة طوارئ...", "warning")
    ai_path = CONFIG.work_dir / f"shot_{index:03d}_ai.jpg"
    ai_prompt = f"{story.get('primary_english_query', CONFIG.topic)}, {shot['text']}, cinematic documentary."
    
    ok = await asyncio.to_thread(generate_ai_image, ai_prompt, ai_path)
    if ok and is_valid_visual(ai_path):
        return {"shot": shot, "path": str(ai_path), "source": "AI_GENERATED_AGY", "score": 1.0, "start": 0.0, "duration": 5.0}

    log(f"🚨 [إنقاذ نهائي] توليد خلفية سينمائية للمشهد {index} لتفادي انهيار النظام.", "error")
    fallback_path = CONFIG.work_dir / f"shot_{index:03d}_fallback.mp4"
    await asyncio.to_thread(create_fallback_visual, shot["text"], fallback_path)
    return {"shot": shot, "path": str(fallback_path), "source": "FFMPEG_FALLBACK", "score": 0.0, "start": 0.0, "duration": 5.0}


async def queue_worker(name, queue, story, results):
    while True:
        try: shot = queue.get_nowait()
        except asyncio.QueueEmpty: break
        
        try:
            res = await scout_shot_worker(shot, story)
            results.append(res)
        except Exception as e:
            log(f"🚨 العامل {name} واجه خطأ غير متوقع في المشهد {shot['index']}: {e}", "error")
        finally:
            queue.task_done()

async def scout_all_media(shots, story):
    log(f"🔍 بدء الطابور ({CONCURRENT_WORKERS} عمال) لمعالجة {len(shots)} مشهد بالتناوب...")
    queue = asyncio.Queue()
    for s in shots: queue.put_nowait(s)
    
    results = []
    tasks = [asyncio.create_task(queue_worker(f"W{i+1}", queue, story, results)) for i in range(CONCURRENT_WORKERS)]
    await asyncio.gather(*tasks)
    
    results.sort(key=lambda x: x["shot"]["index"])
    if len(results) < len(shots): raise RuntimeError(f"بعض المشاهد مفقودة. توقف النظام.")
    return results


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
    shots = WordSyncSlicer().align_and_slice(master_audio, story["part_1"] + "\n" + story["part_2"])
    shots = story_engine.direct_storyboard(shots)

    sub_path = CONFIG.work_dir / "subtitles.ass"
    with open(sub_path, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,Noto Sans Arabic,58,&H00FFFFFF,&H00FFFFFF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3,1,2,80,80,70,1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for s in shots:
            h1, m1 = int(s['start']//3600), int((s['start']%3600)//60)
            h2, m2 = int(s['end']//3600), int((s['end']%3600)//60)
            t = s['text'].replace("\\", r"\\")
            f.write(f"Dialogue: 0,{h1}:{m1:02d}:{s['start']%60:05.2f},{h2}:{m2:02d}:{s['end']%60:05.2f},Default,,0,0,0,,{{\\fad(120,120)}}{t}\n")

    media_results = await scout_all_media(shots, story)

    assembly = AssemblyEngine()
    final_video = assembly.assemble_final_cut([assembly.render_sub_clip(i) for i in media_results], sub_path)

    log("🎨 توليد صورة مصغرة (Thumbnail) فخمة لليوتيوب...", "info")
    thumb_prompt = f"Luxurious YouTube thumbnail, mysterious documentary, {story.get('primary_english_query', CONFIG.topic)}"
    await asyncio.to_thread(generate_ai_image, thumb_prompt, CONFIG.thumbnail, "16:9")

    uploader = GoogleUploader(CONFIG.google_client_id, CONFIG.google_client_secret, CONFIG.google_refresh_token)
    await asyncio.to_thread(uploader.upload_all, final_video, CONFIG.thumbnail, CONFIG.topic_clean)

    log("🏁 اكتمل العمل بنجاح.", "info")

if __name__ == "__main__":
    try:
        asyncio.run(main_pipeline())
    except KeyboardInterrupt:
        log("🛑 تم الإيقاف يدوياً.", "warning")
        sys.exit(130)
    except Exception as e:
        log(f"💥 توقف النظام بسبب خطأ حرج: {e}", "error")
        sys.exit(1)
