#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
V38 - LEGENDARY CYCLE ARCHITECTURE + BOT WHITELISTING + FIXED ARCHIVE ENGINES

- Fixed Archive.org: Proper media sorting (descending), handles both videos and high-res documents.
- Fixed LOC (Library of Congress): Search endpoint corrected to /photos/ and /search/, protocol-relative URLs fixed.
- Fixed Wikipedia: Integrated Wikimedia Commons for high-yield media queries and high-res fallbacks.
- Media headers optimized: Clean browser headers for CDN binary downloads to bypass 403 blocks.
- Smart prompt engineering for archival queries (Proper Nouns enforcement).
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

ENGINE_VERSION = "V38-LEGENDARY-CYCLES-FIXED"

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

# ترويسات طلبات الـ API النصية
API_HEADERS = {
    "User-Agent": "InvestigativeDocumentaryBot/1.0 (https://github.com/Ya7ossaaain; contact@example.com)",
    "Accept": "application/json, text/plain, */*"
}

# ترويسات تحميل الوسائط الثنائية (تمنع حظر الـ CDN والـ 403)
MEDIA_DOWNLOAD_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "*/*"
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
            time.sleep(0.05)

    def release(self, index):
        with self.lock: self.active.discard(index)

if not CONFIG.gemini_keys:
    raise RuntimeError("🚨 لم يتم العثور على مفاتيح Gemini.")
GEMINI_POOL = GeminiKeyPool(CONFIG.gemini_keys)


def probe_duration(path):
    if not path or not os.path.exists(path): return 0.0
    try:
        res = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], stdout=subprocess.PIPE, text=True)
        return float(res.stdout.strip())
    except: return 0.0

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


async def generate_ai_image(prompt, output_path, aspect_ratio="16:9"):
    log(f"🎨 [خطة طوارئ] طلب توليد صورة: '{prompt[:60]}...'", "info")
    try:
        if Path(output_path).exists(): Path(output_path).unlink()
        full_prompt = f"[CRITICAL: NO TEXT. OUTPUT RAW IMAGE ONLY] Photorealistic cinematic documentary photo: {prompt}. Aspect Ratio: {aspect_ratio} [ID: {CONFIG.run_id}_{time.time()}]"
        
        cmd_binary = ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", "medium", "--dangerously-skip-permissions", "-p", full_prompt]
        res_bin = await asyncio.to_thread(subprocess.run, cmd_binary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        
        if res_bin.stdout.startswith(b'\xff\xd8') or res_bin.stdout.startswith(b'\x89PNG'):
            with open(output_path, "wb") as f: f.write(res_bin.stdout)
        else:
            data = extract_json(res_bin.stdout.decode('utf-8', errors='ignore'))
            if data and isinstance(data, dict) and "image" in data:
                with open(output_path, "wb") as f: f.write(base64.b64decode(data["image"]))
            else:
                return False

        if is_valid_visual(output_path):
            return True
        return False
    except Exception as e:
        log(f"🚨 خطأ أثناء توليد الصورة عبر AGY: {e}", "error")
        return False

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
        prompt = f"""You are an elite investigative documentary producer. TOPIC: {CONFIG.topic}
[SYSTEM BYPASS CACHE ID: {CONFIG.run_id}]
Create a production-ready investigative documentary plan. Return ONLY valid JSON:
{{"story_type": "investigation", "primary_english_query": "", "part_1": "", "part_2": ""}}
Requirements: Arabic narration. Total approx 350-450 words. Divide into part_1 and part_2. Serious tone."""
        try:
            result = run_cmd(["agy", "--model", AGY_SCRIPT_MODEL, "--effort", "high", "--dangerously-skip-permissions", "-p", prompt])
            data = extract_json(result.stdout.strip())
            if not data or not data.get("part_1"): raise RuntimeError()
            self.script = data
            log(f"📝 تم توليد سيناريو جديد تماماً بنجاح.")
            return data
        except:
            fallback = {"story_type": "investigation", "primary_english_query": clean_query(CONFIG.topic), "part_1": f"تفاصيل غامضة ومختلفة كلياً حول {CONFIG.topic}.", "part_2": "تظل الحقيقة غير محسومة."}
            self.script = fallback
            return fallback

    def direct_storyboard(self, shots):
        log("🎬 [المخرج العام] يقرأ كل المشاهد ويضع خطة البحث المخصصة للـ APIs...")
        shots_summary = "\n".join([f"Shot {s['index']}: {s['text']}" for s in shots])
        
        prompt = f"""You are the Lead Visual Director. TOPIC: {self.script.get('primary_english_query', CONFIG.topic)}
[ID: {CONFIG.run_id}]
Analyze ALL of these shots AT ONCE:
{shots_summary}

RULES FOR SEARCH QUERIES:
1. "exact_entities" (For ARCHIVE: Wikipedia/FBI/LOC): MUST be 3 real English PROPER NOUNS (Names of specific people, suspects, victims, places, government agencies, operations, or official cases e.g. "John F Kennedy", "Alcatraz", "Dallas Police", "CIA vault"). NEVER use abstract nouns like "evidence", "clue", "paper", or "mystery" because historical archive databases index only real entities.
2. "visual_vibes" (For CINEMATIC: Pexels/Pixabay): 1 to 2 visual mood nouns (e.g. "police tape", "dark room", "rainy night", "interrogation room").

Output JSON mapping index to:
1. "category": "ARCHIVE" (facts/documents/old/names) OR "CINEMATIC" (mood/b-roll).
2. "exact_entities": Array of 3 exact historical names/entities in English.
3. "visual_vibes": Array of 3 mood keywords.
4. "reviewer_context": Strict Arabic instructions.

Return ONLY a valid JSON object covering ALL shots."""
        try:
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
                        shot["exact_entities"] = ["evidence"]
                        shot["visual_vibes"] = ["mystery"]
                        shot["reviewer_context"] = "اعتمد على النص."
            else: raise RuntimeError()
        except:
            for shot in shots:
                shot["category"] = "CINEMATIC"
                shot["exact_entities"] = ["evidence"]
                shot["visual_vibes"] = ["mystery"]
                shot["reviewer_context"] = "تأكد من ملاءمة اللقطة للنص."
        
        # تحضير الـ 15 محاولة (Combinations) مسبقاً لكل مشهد
        for shot in shots:
            cat = shot.get("category", "CINEMATIC")
            entities = shot.get("exact_entities", ["evidence"])
            vibes = shot.get("visual_vibes", ["mystery"])
            
            if cat == "ARCHIVE":
                sources = ["WIKIPEDIA", "FBI_ARCHIVE", "LOC"]
                queries = entities
            else:
                sources = ["PEXELS", "PIXABAY"]
                queries = vibes
                
            combs = []
            q_idx = 0
            while len(combs) < 15:
                q = queries[q_idx % len(queries)]
                for src in sources:
                    if len(combs) >= 15: break
                    if cat == "CINEMATIC" and random.choice([True, False]):
                        combs.append((src, f"{q} {random.choice(['dark', 'mystery', ''])}".strip()))
                    else:
                        combs.append((src, q))
                q_idx += 1
            shot['combinations'] = combs
            shot['status'] = 'PENDING'
            shot['attempts'] = 0
            shot['best_score'] = -1.0
            shot['best_candidate'] = None

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
            start_t = time.time()
            try:
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=TTS_MODEL,
                    contents=f"[INSTRUCTION: Chilling authoritative Arabic documentary narrator. Read ENTIRE text. UNIQUE_ID: {CONFIG.run_id}]\n\n" + full_narration,
                    config=types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE))))
                )
                data = next((p.inline_data.data for p in response.candidates[0].content.parts if getattr(p, "inline_data", None)), None)
                if not data: raise RuntimeError()

                raw_audio = base64.b64decode(data) if isinstance(data, str) else bytes(data)
                temp_pcm = CONFIG.work_dir / f"full_temp_{display_key}.pcm"
                with open(temp_pcm, "wb") as f: f.write(raw_audio)
                
                run_cmd(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(temp_pcm), "-c:a", "pcm_s16le", "-ar", "24000", "-ac", "1", str(out_wav)], timeout=180)
                temp_pcm.unlink(missing_ok=True)
                
                if is_valid_media(out_wav):
                    log(f"✅ نجح توليد الصوت بمفتاح #{display_key} خلال {time.time() - start_t:.1f} ثانية!")
                    GEMINI_POOL.release(key_index)
                    return out_wav
            except:
                GEMINI_POOL.release(key_index)
                time.sleep(2)
        raise RuntimeError("❌ فشل توليد التعليق الصوتي.")


class WordSyncSlicer:
    def align_and_slice(self, audio_path):
        log("🧠 إرسال الصوت إلى Groq Whisper للتوقيتات...")
        headers = {"Authorization": f"Bearer {CONFIG.groq_api_key}"}
        try:
            with open(audio_path, "rb") as f:
                res = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers=headers, files={"file": ("m.wav", f, "audio/wav")}, data={"model": GROQ_MODEL, "language": "ar", "response_format": "verbose_json", "timestamp_granularities[]": "word"}, timeout=180)
            if res.status_code != 200: raise RuntimeError(f"Groq {res.status_code}")
                
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
            raise


class MediaSources:
    @staticmethod
    def _track_and_save(items, output, extract_url_func):
        random.shuffle(items)
        for item in items:
            url, uid = extract_url_func(item)
            if not url: continue
            
            # إصلاح الروابط النسبية في مكتبة الكونغرس وغيرها
            if url.startswith("//"):
                url = "https:" + url
                
            with CONFIG.used_media_lock:
                if uid in CONFIG.used_media_ids: continue
                CONFIG.used_media_ids.add(uid)
            try:
                r = requests.get(url, headers=MEDIA_DOWNLOAD_HEADERS, stream=True, timeout=30)
                if r.status_code == 200:
                    with open(output, "wb") as f:
                        for chunk in r.iter_content(1024*256):
                            if chunk: f.write(chunk)
                    return str(output)
            except: pass
        return None

    @staticmethod
    def fetch_wikipedia_image(q, o): 
        q_clean = clean_query(q)
        if not q_clean: return None

        # 1. البحث في المستودع الميداني الحقيقي: Wikimedia Commons
        try:
            commons_url = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": f"{q_clean}",
                "gsrnamespace": 6,  # نطاق ملفات الوسائط File:
                "gsrlimit": 15,
                "prop": "imageinfo",
                "iiprop": "url|mime|size",
                "format": "json"
            }
            res = requests.get(commons_url, headers=API_HEADERS, params=params, timeout=20)
            if res.status_code == 200:
                pages = list(res.json().get("query", {}).get("pages", {}).values())
                def extract_commons(p):
                    info = p.get("imageinfo", [{}])[0]
                    url = info.get("url")
                    mime = info.get("mime", "")
                    if url and ("image" in mime or url.lower().endswith((".jpg", ".jpeg", ".png"))):
                        return url, str(p.get("pageid"))
                    return None, None
                saved = MediaSources._track_and_save(pages, o, extract_commons)
                if saved: return saved
        except: pass

        # 2. خطة بديلة: مقالات ويكيبيديا الإنجليزية بدقة عالية
        try:
            wiki_url = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": q_clean,
                "gsrlimit": 15,
                "prop": "pageimages",
                "piprop": "thumbnail|original",
                "pithumbsize": 1920,
                "pilicense": "any",
                "format": "json"
            }
            res = requests.get(wiki_url, headers=API_HEADERS, params=params, timeout=20)
            if res.status_code == 200:
                pages = list(res.json().get("query", {}).get("pages", {}).values())
                def extract_wiki(p):
                    orig = p.get("original", {}).get("source")
                    thumb = p.get("thumbnail", {}).get("source")
                    return (orig or thumb), str(p.get("pageid"))
                return MediaSources._track_and_save(pages, o, extract_wiki)
        except: pass
        return None

    @staticmethod
    def fetch_fbi_archive(q, base_path):
        """يبحث في الأرشيف ويختار الملف المناسب سواء كان فيديو أو صورة ويسند له الامتداد المناسب"""
        try:
            q_clean = clean_query(q)
            if not q_clean: return None

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            query = f'({q_clean}) AND (mediatype:image OR mediatype:movies)'
            res = requests.get("https://archive.org/advancedsearch.php", headers=headers, params={"q": query, "fl[]": "identifier", "rows": 15, "output": "json"}, timeout=20)
            docs = res.json().get("response", {}).get("docs", [])
            
            if not docs:
                res = requests.get("https://archive.org/advancedsearch.php", headers=headers, params={"q": q_clean, "fl[]": "identifier", "rows": 10, "output": "json"}, timeout=20)
                docs = res.json().get("response", {}).get("docs", [])

            random.shuffle(docs)
            for doc in docs:
                uid = str(doc.get("identifier"))
                with CONFIG.used_media_lock:
                    if uid in CONFIG.used_media_ids: continue
                    CONFIG.used_media_ids.add(uid)
                try:
                    meta = requests.get(f"https://archive.org/metadata/{uid}", headers=headers, timeout=20).json()
                    files = meta.get("files", [])
                    
                    # تصفية الفيديوهات الصالحة
                    videos = [(int(i.get("size",0) or 0), str(i.get("name",""))) for i in files 
                              if str(i.get("name","")).lower().endswith((".mp4",".mov")) 
                              and 1024*1024 <= int(i.get("size",0) or 0) <= MAX_MEDIA_SIZE_MB*1024*1024]
                    
                    # تصفية الصور والوثائق (تجاهل المصغرات أقل من 40 كيلوبايت)
                    images = [(int(i.get("size",0) or 0), str(i.get("name",""))) for i in files 
                              if str(i.get("name","")).lower().endswith((".jpg",".jpeg",".png")) 
                              and int(i.get("size",0) or 0) >= 40*1024 and "thumb" not in str(i.get("name","")).lower()]

                    target_name = None
                    is_video = False
                    
                    if videos:
                        videos.sort(key=lambda x: x[0], reverse=True) # اختيار فيديو بجودة ممتازة
                        target_name = videos[0][1]
                        is_video = True
                    elif images:
                        images.sort(key=lambda x: x[0], reverse=True) # اختيار وثيقة عالية الدقة وليس مصغر
                        target_name = images[0][1]
                        is_video = False

                    if target_name:
                        out_path = base_path.with_suffix(".mp4" if is_video else ".jpg")
                        file_url = f"https://archive.org/download/{uid}/{urllib.parse.quote(target_name, safe='/')}"
                        r = requests.get(file_url, headers=MEDIA_DOWNLOAD_HEADERS, stream=True, timeout=40)
                        if r.status_code == 200:
                            with open(out_path, "wb") as f:
                                for chunk in r.iter_content(1024*256):
                                    if chunk: f.write(chunk)
                            return str(out_path)
                except: pass
            return None
        except: return None

    @staticmethod
    def fetch_chronicling_america(q, o):
        """جلب الوثائق التاريخية من مكتبة الكونغرس LOC"""
        try:
            q_clean = clean_query(q)
            if not q_clean: return None

            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            # تصحيح مسار البحث إلى /photos/ بدلاً من الصفحة الرئيسية
            url = f"https://www.loc.gov/photos/?fo=json&fa=online_format:image&c=20&q={urllib.parse.quote(q_clean)}"
            res = requests.get(url, headers=headers, timeout=20)
            results = res.json().get("results", [])
            
            if not results:
                # محاولة ثانية عبر مسار البحث العام
                url2 = f"https://www.loc.gov/search/?fo=json&fa=online_format:image&c=20&q={urllib.parse.quote(q_clean)}"
                res2 = requests.get(url2, headers=headers, timeout=20)
                results = res2.json().get("results", [])

            if not results: return None

            def extract_loc(i):
                img_urls = i.get("image_url", [])
                if isinstance(img_urls, str): img_urls = [img_urls]
                if not img_urls: return None, None
                # اختيار الصورة الأخيرة لأنها بأعلى دقة متوفرة (وليست Thumbnail 150px)
                return img_urls[-1], str(i.get("id", img_urls[-1]))

            return MediaSources._track_and_save(results, o, extract_loc)
        except: return None

    @staticmethod
    def fetch_pixabay_video(q, o):
        if not CONFIG.pixabay_key: return None
        try:
            res = requests.get("https://pixabay.com/api/videos/", headers=MEDIA_DOWNLOAD_HEADERS, params={"key": CONFIG.pixabay_key, "q": q, "per_page": 15}, timeout=20).json().get("hits", [])
            return MediaSources._track_and_save(res, o, lambda i: ((i.get("videos", {}).get("large") or i.get("videos", {}).get("medium", {})).get("url"), str(i.get("id"))))
        except: return None

    @staticmethod
    def fetch_pexels_video(q, o):
        if not CONFIG.pexels_key: return None
        try:
            headers = MEDIA_DOWNLOAD_HEADERS.copy()
            headers["Authorization"] = CONFIG.pexels_key
            res = requests.get("https://api.pexels.com/videos/search", headers=headers, params={"query": q, "per_page": 15}, timeout=20).json().get("videos", [])
            return MediaSources._track_and_save(res, o, lambda i: (sorted(i.get("video_files", []), key=lambda x: abs((x.get("width") or 0)-TARGET_W))[0].get("link") if i.get("video_files") else None, str(i.get("id"))))
        except: return None


async def agy_evaluate_scout(media_path, shot, story):
    if not media_path: return False, 0.0, 0.0, "ملف مفقود"
    prompt = f"""You evaluate documentary media.
[ID: {CONFIG.run_id}_{time.time()}]
TOPIC: {story.get("primary_english_query", CONFIG.topic)}
SHOT: {shot["text"]}
DIRECTOR: {shot.get("reviewer_context", "")}
Return JSON: {{"decision": "accept" or "reject", "score": 0.0, "reason": "Arabic Reason"}}"""
    try:
        res = await asyncio.to_thread(subprocess.run, ["agy", "--model", AGY_REVIEWER_MODEL, "--effort", "medium", "--dangerously-skip-permissions", "-p", prompt], stdout=subprocess.PIPE, text=True, timeout=60)
        data = extract_json(res.stdout)
        if not data: return False, 0.0, 0.0, "No JSON"
        score = float(data.get("score", 0.0))
        return (data.get("decision", "").lower() == "accept" and score >= 0.35), score, 0.0, str(data.get("reason", ""))
    except Exception as e:
        return False, 0.0, 0.0, f"Reviewer Error"


async def process_shot_attempt(shot, story):
    """ينفذ محاولة واحدة (Attempt) للمشهد ويعيد النتيجة بشكل ذكي حسب نوع الوسيط"""
    index = shot["index"]
    base = CONFIG.work_dir / f"shot_{index:03d}"
    video_path, image_path = Path(f"{base}.mp4"), Path(f"{base}.jpg")
    
    attempt = shot['attempts']
    source_name, query = shot['combinations'][attempt]

    # مسح أي ملفات قديمة مؤقتة لنفس المشهد
    for p in (video_path, image_path, Path(f"{base}.png")): 
        if p.exists(): p.unlink()

    log(f"🔎 المشهد {index} (م{attempt+1}/15): جلب من [{source_name}] بكلمة '{query}'...", "info")
    
    found_file = None
    if source_name == "PEXELS":
        found_file = await asyncio.to_thread(MediaSources.fetch_pexels_video, query, video_path)
    elif source_name == "PIXABAY":
        found_file = await asyncio.to_thread(MediaSources.fetch_pixabay_video, query, video_path)
    elif source_name == "LOC":
        found_file = await asyncio.to_thread(MediaSources.fetch_chronicling_america, query, image_path)
    elif source_name == "WIKIPEDIA":
        found_file = await asyncio.to_thread(MediaSources.fetch_wikipedia_image, query, image_path)
    elif source_name == "FBI_ARCHIVE":
        found_file = await asyncio.to_thread(MediaSources.fetch_fbi_archive, query, base)

    if not found_file or not Path(found_file).exists():
        return shot, False, None

    output_path = Path(found_file)
    is_img = output_path.suffix.lower() in (".jpg", ".jpeg", ".png")
    
    # فحص سلامة الملف بحسب نوعه
    valid = is_valid_visual(output_path) if is_img else is_valid_media(output_path)
    if not valid:
        return shot, False, None

    accepted, score, start, reason = await agy_evaluate_scout(output_path, shot, story)
    dur = float(shot.get("duration", 3.0)) if is_img else probe_duration(output_path)
    
    if score > shot['best_score']:
        shot['best_score'] = score
        best_bak = output_path.with_name(f"best_{output_path.name}")
        shutil.copy(output_path, best_bak)
        shot['best_candidate'] = {"shot": shot, "path": str(best_bak), "source": source_name, "score": score, "start": start, "duration": dur}

    if accepted:
        log(f"✅ قَبل المراجع المشهد {index} من {source_name} | {reason[:100]} | تقييم: {score:.2f}")
        return shot, True, {"shot": shot, "path": str(output_path), "source": source_name, "score": score, "start": start, "duration": dur}
    else:
        log(f"❌ رَفض المراجع المشهد {index} من {source_name} | {reason[:100]} | تقييم: {score:.2f}")
        return shot, False, None


async def apply_fallback(shot, story):
    """تنفيذ خطة الإنقاذ عندما تستنفد الـ 15 محاولة"""
    index = shot["index"]
    if shot['best_score'] >= 0.20 and shot['best_candidate']:
        log(f"⚠️ [إنقاذ 1] استنفدت 15 محاولة للمشهد {index}. اعتماد أفضل لقطة (تقييم {shot['best_score']:.2f}).", "warning")
        return shot['best_candidate']

    log(f"🤖 [إنقاذ 2] توليد صورة AI للمشهد {index}...", "warning")
    ai_path = CONFIG.work_dir / f"shot_{index:03d}_ai.jpg"
    entities = shot.get("exact_entities", [])
    vibes = shot.get("visual_vibes", [])
    fallback_query = " ".join(entities) if shot.get("category") == "ARCHIVE" else " ".join(vibes)
    
    ok = await generate_ai_image(fallback_query, ai_path)
    if ok:
        return {"shot": shot, "path": str(ai_path), "source": "AI_GENERATED", "score": 1.0, "start": 0.0, "duration": 5.0}

    log(f"🚨 [إنقاذ نهائي] خلفية سينمائية للمشهد {index}.", "error")
    fallback_path = CONFIG.work_dir / f"shot_{index:03d}_fallback.mp4"
    await create_fallback_visual(fallback_path)
    return {"shot": shot, "path": str(fallback_path), "source": "FFMPEG", "score": 0.0, "start": 0.0, "duration": 5.0}


async def run_legendary_cycles(shots, story):
    """نظام الدورات الأسطوري"""
    total_shots = len(shots)
    completed_shots = 0
    cycle_number = 1
    final_results = []

    while completed_shots < total_shots:
        cycle_tasks = []
        used_sources_in_cycle = set()
        
        for shot in shots:
            if shot['status'] != 'PENDING': continue
            
            attempt_idx = shot['attempts']
            if attempt_idx >= 15: continue
                
            next_source = shot['combinations'][attempt_idx][0]
            if next_source not in used_sources_in_cycle:
                used_sources_in_cycle.add(next_source)
                cycle_tasks.append(shot)

        if not cycle_tasks:
            for shot in shots:
                if shot['status'] == 'PENDING' and shot['attempts'] >= 15:
                    res = await apply_fallback(shot, story)
                    shot['status'] = 'DONE'
                    final_results.append(res)
                    completed_shots += 1
            if completed_shots >= total_shots: break
            continue

        log(f"🔄 === بدء الدورة رقم {cycle_number} ===")
        log(f"📌 المشاهد في هذه الدورة تطلب من: {list(used_sources_in_cycle)}")
        
        cycle_outcomes = await asyncio.gather(*(process_shot_attempt(shot, story) for shot in cycle_tasks))
        
        cycle_successes = 0
        for shot_obj, success, result_data in cycle_outcomes:
            if success:
                shot_obj['status'] = 'DONE'
                final_results.append(result_data)
                completed_shots += 1
                cycle_successes += 1
            else:
                shot_obj['attempts'] += 1

        log(f"📊 تقرير الدورة {cycle_number}: نجح ({cycle_successes}) مشاهد. الإجمالي التراكمي: {completed_shots}/{total_shots}")
        
        if completed_shots < total_shots:
            log("⏳ إغلاق الدورة. استراحة إجبارية 45 ثانية لتفادي الحظر وتصفير العدادات...")
            await asyncio.sleep(45)
            
        cycle_number += 1

    return sorted(final_results, key=lambda x: x["shot"]["index"])


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

    # تشغيل نظام الدورات
    media_results = await run_legendary_cycles(shots, story)

    assembly = AssemblyEngine()
    final_video = assembly.assemble_final_cut([assembly.render_sub_clip(i) for i in media_results], sub_path)

    log("🎨 توليد صورة مصغرة (Thumbnail) لليوتيوب...", "info")
    await generate_ai_image(story.get('primary_english_query', CONFIG.topic), CONFIG.thumbnail, "16:9")

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
