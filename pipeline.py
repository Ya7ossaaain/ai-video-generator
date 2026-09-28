#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================================================
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE (HYBRID V22.12 - Multi-Source Fallback)
- منع البحث بالعربي: فلترة صارمة لمنع إرسال أي أحرف عربية لمحركات البحث لضمان النتائج.
- هندسة القفز (3x3): 3 محاولات Pexels ثم 3 Pixabay. و 3 محاولات Wiki ثم 3 Internet Archive.
- تصحيح الروابط: تغليف استعلامات البحث بـ URL Encoding لضمان عدم تعطل الـ APIs.
- استخدام SDK الرسمي: المراجعة البصرية والنهائية تُدار عبر google.antigravity للتحليل الحقيقي.
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

# الصوت فقط (Gemini API)
from google import genai
from google.genai import types

# التصدير السحابي
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# الرؤية والمراجعة (Antigravity SDK)
import google.antigravity as ag
from google.antigravity import Agent, LocalAgentConfig

# ==================================================================================================
# 1. إعدادات النظام وتوثيق السجلات
# ==================================================================================================
class ProTelemetryFormatter(logging.Formatter):
    COLORS = {'INFO': "\x1b[38;5;39m", 'WARNING': "\x1b[38;5;214m", 'ERROR': "\x1b[38;5;196m"}
    RESET = "\x1b[0m"
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        return logging.Formatter(f"{color}%(asctime)s | [%(levelname)s] | %(message)s{self.RESET}", datefmt="%H:%M:%S").format(record)

def setup_logger() -> logging.Logger:
    logger = logging.getLogger("HybridMaster")
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(ProTelemetryFormatter())
        logger.addHandler(ch)
        fh = logging.FileHandler("production_logs.txt", encoding="utf-8")
        logger.addHandler(fh)
    return logger

log = setup_logger()
MEMORY_FILE = Path("director_memory.md")

def append_memory(summary: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MEMORY_FILE, "a", encoding="utf-8") as f: f.write(f"\n\n### [{now}]\n{summary}")

# ==================================================================================================
# 2. المستكشف الديناميكي لوسائط Antigravity وفلتر اللغة
# ==================================================================================================
def load_ag_media(file_path: Path):
    ext = file_path.suffix.lower()
    path_str = str(file_path.resolve())
    
    if ext in [".mp4", ".mov", ".webm", ".avi"]:
        if hasattr(ag, "Video"): return getattr(ag, "Video").from_file(path_str)
        if hasattr(ag, "media") and hasattr(ag.media, "Video"): return getattr(ag.media, "Video").from_file(path_str)
        if hasattr(ag, "from_file"): return getattr(ag, "from_file")(path_str)
    else:
        if hasattr(ag, "Image"): return getattr(ag, "Image").from_file(path_str)
        if hasattr(ag, "media") and hasattr(ag.media, "Image"): return getattr(ag.media, "Image").from_file(path_str)
        if hasattr(ag, "from_file"): return getattr(ag, "from_file")(path_str)
        
    raise RuntimeError("لم يتم العثور على فئة الوسائط في حزمة google.antigravity")

def enforce_english_query(query: str) -> str:
    """إزالة أي حروف عربية من كلمة البحث لضمان توافقها مع الـ APIs"""
    safe_q = re.sub(r'[\u0600-\u06FF]', '', query).strip()
    # إذا مسحنا كل شيء (كان كله عربي)، نعطيه كلمة افتراضية إنجليزية
    if not safe_q or len(safe_q) < 2:
        safe_q = "mystery evidence"
    return safe_q

# ==================================================================================================
# 3. المسارات والمفاتيح
# ==================================================================================================
class HybridConfig:
    topic = os.environ.get("VIDEO_TOPIC", "لغز الجريمة الغامضة")
    paths = type('Paths', (), {'base': Path("./output_build"), 'cache': Path("./output_build/cache"), 'manifest': Path("./output_build/master_manifest.json")})()
    gemini_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
    pexels = os.environ.get("PEXELS_API_KEY", "")
    pixabay = os.environ.get("PIXABAY_API_KEY", "")
    freesound = os.environ.get("FREESOUND_API_KEY", "")
    yt_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    yt_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    drive_token = os.environ.get("DRIVE_REFRESH_TOKEN", "")
    yt_refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

CONFIG = HybridConfig()
for p in [CONFIG.paths.base, CONFIG.paths.cache]: p.mkdir(parents=True, exist_ok=True)

# ==================================================================================================
# 4. العقل المدبر (CLI للسيناريو / SDK للرؤية)
# ==================================================================================================
class Hybrid_Director:
    def plan_documentary(self) -> List[Dict]:
        if CONFIG.paths.manifest.exists(): return json.loads(CONFIG.paths.manifest.read_text(encoding="utf-8"))

        log.info(f"كتابة السيناريو (agy CLI: gemini-3.1-pro) | القضية: {CONFIG.topic}")
        prompt = f"""أنت كبير المخرجين. قضيتنا: "{CONFIG.topic}".
        قم ببناء سيناريو ضخم (40-50 مشهداً، كل مشهد 60-80 كلمة).
        استخدم PEXELS, PIXABAY, WIKIPEDIA.
        تنبيه صارم: قيمة "search_query" يجب أن تكون باللغة الإنجليزية حصراً (ENGLISH ONLY) لضمان نجاح البحث.
        أخرج JSON Array فقط: [{{"scene_num": 1, "media_type": "PEXELS", "search_query": "dark street", "foley_type": "rain", "narration": "في ليلة..."}}]"""
        
        for _ in range(3):
            try:
                cmd = ["agy", "--model", "gemini-3.1-pro", "--effort", "high", "--dangerously-skip-permissions", "-p", prompt]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if result.returncode != 0:
                    log.warning(f"Agy Error: {result.stderr.strip()}")
                    time.sleep(5)
                    continue
                    
                match = re.search(r'\[.*\]', result.stdout.strip(), re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    CONFIG.paths.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    return data
            except Exception as e: log.warning(f"⚠️ خطأ السيناريو: {e}"); time.sleep(5)
        sys.exit("🛑 فشل كتابة السيناريو.")

    async def _async_evaluate_scout(self, media_path: Path, narration: str, source: str) -> str:
        config = LocalAgentConfig(model="gemini-3.6-flash", effort="high")
        agent = Agent(config=config)
        
        prompt = f"""أنت مراجع بصري فوري لمشروع وثائقي تحقيقي بعنوان: "{CONFIG.topic}".
نوع المصدر: {source}
التعليق الصوتي المرافق للمشهد: "{narration}"

شاهد الوسيط المرفق بعناية. هل يتطابق مرئياً وحرفياً مع النص؟
قواعد:
1. اختر ACCEPT فقط إذا كان المحتوى مرتبطاً ارتباطاً مباشراً.
2. إذا كان التطابق غير مؤكد، اختر REJECT.
3. اشرح تبريرك بدقة (reason).
4. اقترح (new_query) بالإنجليزية حصراً إذا رفضت اللقطة.

أخرج JSON فقط بالهيكلة التالية:
{{
  "decision": "ACCEPT" أو "REJECT",
  "score": 0.95,
  "reason": "وصف مختصر يوضح التطابق بالعربية",
  "montage": "ZOOM_IN أو NORMAL أو BW",
  "new_query": "English replacement query"
}}"""

        media_input = load_ag_media(media_path)
        return await agent.chat([prompt, media_input])

    def evaluate_scene_with_scout(self, media_path: Path, narration: str, source: str) -> Dict:
        log.info(f"👁️ المراجع الفوري (Antigravity SDK) يحلل الوسيط المرفق من {source}...")
        try:
            result_text = asyncio.run(self._async_evaluate_scout(media_path, narration, source))
            log.info(f"🗣️ المراجع الفوري يقول:\n{result_text}")

            match = re.search(r'\{.*\}', result_text, re.DOTALL)
            if not match:
                log.warning("⚠️ فشل استخراج JSON، سيتم الرفض للبحث عن مشهد أوضح.")
                return {"accepted": False, "montage": "ZOOM_IN", "new_query": ""}
                
            data = json.loads(match.group(0))
            score = float(data.get("score", 0.0))
            accepted = (data.get("decision") == "ACCEPT" and score >= 0.70)

            return {
                "accepted": accepted,
                "montage": data.get("montage", "NORMAL"),
                "new_query": data.get("new_query", "")
            }

        except Exception as e:
            log.error(f"⚠️ انهيار المراجع الفوري: {e}")
            return {"accepted": False, "montage": "ZOOM_IN", "new_query": ""}

    async def _async_critique(self, final_video: Path, logs: str) -> str:
        config = LocalAgentConfig(model="gemini-3.1-pro", effort="high")
        agent = Agent(config=config)
        
        prompt = f"""أنت الذكاء الاصطناعي المؤسس والمراجع النهائي للفيلم.
إليك سجلات النظام:
{logs}

شاهد الفيلم الوثائقي النهائي المرفق (Video+Audio) بالكامل.
1. هل الفيديو والصوت متزامنان؟
2. هل ظهرت أخطاء برمجية أدت إلى شاشات معطوبة؟

إذا كان هناك خلل برمجي يحتاج لإصلاح جذري، اكتب كود `pipeline.py` جديد داخل كتلة ```python .
إذا كان الفيلم مثالياً، أجب بكلمة PERFECT فقط."""

        media_input = load_ag_media(final_video)
        return await agent.chat([prompt, media_input])

    def self_critique_and_recode(self, final_video: Path) -> bool:
        log.info(f"🧠 المراجع النهائي يشاهد الفيلم الكامل MP4 عبر SDK...")
        logs = Path("production_logs.txt").read_text()[-2500:] if Path("production_logs.txt").exists() else "No logs"
        
        try:
            result_text = asyncio.run(self._async_critique(final_video, logs))
            log.info(f"🗣️ المراجع النهائي يقول:\n{result_text}")
            
            if "PERFECT" in result_text:
                log.info("✅ المراجع النهائي فخور بالفيلم واعتمد الكود الحالي.")
                return True
                
            code_match = re.search(r'```python(.*?)```', result_text, re.DOTALL)
            if code_match:
                new_code = code_match.group(1).strip()
                log.warning("🔄 تحذير: المراجع اكتشف خللاً برمجياً وقام بتحديث نفسه! جاري إعادة التشغيل...")
                append_memory("المراجع النهائي شاهد الفيلم المدمج وقام بإصلاح كود pipeline.py.")
                Path(__file__).write_text(new_code, encoding="utf-8")
                os.execv(sys.executable, ['python'] + sys.argv)
                
            return True
        except Exception as e:
            log.error(f"فشل التعديل الذاتي: {e}")
            return True

    def generate_voice(self, text: str, out_wav: Path):
        cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon"))))
        
        for round_num in range(3):
            log.info(f"🎙️ توليد الصوت (الجولة {round_num + 1}/3)...")
            for i, key in enumerate(CONFIG.gemini_keys):
                try:
                    client = genai.Client(api_key=key)
                    res = client.models.generate_content(
                        model="gemini-3.8-flash-tts", 
                        contents=f"[INSTRUCTION: Deep chilling narrator]\n{text}", 
                        config=cfg
                    )
                    audio_data = res.candidates[0].content.parts[0].inline_data.data
                    if isinstance(audio_data, str): out_wav.write_bytes(base64.b64decode(audio_data))
                    else: out_wav.write_bytes(audio_data)
                    
                    if out_wav.exists() and out_wav.stat().st_size > 1000:
                        log.info("⏳ تم توليد الصوت بنجاح. تبريد 30 ثانية...")
                        time.sleep(30)
                        return
                except Exception as e: 
                    log.warning(f"⚠️ فشل المفتاح {i+1}: {str(e)[:50]}")
                    time.sleep(2)
            time.sleep(10)
        log.error("❌ استنفدت جميع المفاتيح لتوليد الصوت!")

# ==================================================================================================
# 5. محرك الوسائط (مع تحويل الروابط بأمان ودعم أرشيف الإنترنت)
# ==================================================================================================
class MediaFetcher:
    def __init__(self): self.h = {"User-Agent": "HybridPipeline/22.12"}
    
    def fetch_media(self, source: str, query: str, out: Path, index: int) -> bool:
        safe_query = urllib.parse.quote(query)
        try:
            if source == "PEXELS" and CONFIG.pexels:
                url = f"[https://api.pexels.com/videos/search?query=](https://api.pexels.com/videos/search?query=){safe_query}&orientation=landscape"
                r = requests.get(url, headers={"Authorization": CONFIG.pexels}).json()
                if r.get("videos") and len(r["videos"]) > index: 
                    out.write_bytes(requests.get(sorted(r["videos"][index]["video_files"], key=lambda x: x.get("width", 0), reverse=True)[0]["link"]).content)
                    return True
            elif source == "PIXABAY" and CONFIG.pixabay:
                url = f"[https://pixabay.com/api/videos/?key=](https://pixabay.com/api/videos/?key=){CONFIG.pixabay}&q={safe_query}"
                r = requests.get(url).json()
                if int(r.get("totalHits", 0)) > index: 
                    out.write_bytes(requests.get(r["hits"][index]["videos"]["large"]["url"]).content)
                    return True
            elif source == "WIKIPEDIA":
                url = f"[https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch=](https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch=){safe_query}&prop=pageimages&pithumbsize=1920&format=json"
                r = requests.get(url, headers=self.h).json()
                pages = list(r.get("query", {}).get("pages", {}).values())
                if pages and pages[index % len(pages)].get("thumbnail", {}).get("source"):
                    out.write_bytes(requests.get(pages[index % len(pages)]["thumbnail"]["source"], headers=self.h).content)
                    return True
            elif source == "ARCHIVE":
                url = f"[https://archive.org/advancedsearch.php?q=](https://archive.org/advancedsearch.php?q=){safe_query}+AND+mediatype:image&fl[]=identifier&output=json&rows=10"
                r = requests.get(url, headers=self.h).json()
                docs = r.get("response", {}).get("docs", [])
                if docs and len(docs) > index:
                    identifier = docs[index]["identifier"]
                    img_url = f"[https://archive.org/services/img/](https://archive.org/services/img/){identifier}"
                    out.write_bytes(requests.get(img_url).content)
                    return True
            elif source == "FREESOUND" and CONFIG.freesound:
                url = f"[https://freesound.org/apiv2/search/text/?query=](https://freesound.org/apiv2/search/text/?query=){safe_query}&token={CONFIG.freesound}&fields=previews"
                r = requests.get(url, timeout=15).json()
                if r.get("results"): 
                    out.write_bytes(requests.get(r["results"][0]["previews"]["preview-hq-mp3"], timeout=30).content)
                    return True
        except Exception as e:
            pass
        return False

def process_audio(voice: Path, foley: Path, has_foley: bool, out: Path) -> float:
    if has_foley:
        fc = "[0:a]loudnorm=I=-16[v]; [1:a]volume=0.04[bg]; [v][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        cmd = ["ffmpeg", "-y", "-i", str(voice), "-stream_loop", "-1", "-i", str(foley), "-filter_complex", fc, "-map", "[aout]", "-ar", "48000", str(out)]
    else:
        fc = "[0:a]loudnorm=I=-16[aout]"
        cmd = ["ffmpeg", "-y", "-i", str(voice), "-filter_complex", fc, "-map", "[aout]", "-ar", "48000", str(out)]
    
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out)]).decode().strip())
        if dur < 0.5: raise ValueError("Audio duration is too short")
        return dur
    except: return 3.0

def render_scene(media: Path, is_vid: bool, aud: Path, out: Path, dur: float, montage: str):
    fx = ",hue=s=0" if "BW" in montage else ",eq=contrast=1.12:saturation=0.85"
    if is_vid: cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(media), "-i", str(aud), "-filter_complex", f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080{fx}[v]", "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out)]
    else: cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(media), "-i", str(aud), "-filter_complex", f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z=1.05:d={int(dur*24)}{fx}[v]", "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def upload_drive(vid: Path):
    if not (CONFIG.yt_id and CONFIG.drive_token): return
    log.info("☁️ الرفع إلى Google Drive...")
    try:
        dr = build("drive", "v3", credentials=Credentials(None, refresh_token=CONFIG.drive_token, token_uri="[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)", client_id=CONFIG.yt_id, client_secret=CONFIG.yt_secret))
        res = dr.files().list(q="name='Broadcast_Vault' and mimeType='application/vnd.google-apps.folder'", fields="files(id)").execute()
        fid = res.get("files")[0]["id"] if res.get("files") else dr.files().create(body={"name": "Broadcast_Vault", "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]
        req = dr.files().create(body={"name": vid.name, "parents": [fid]}, media_body=MediaFileUpload(str(vid), mimetype="video/mp4", resumable=True, chunksize=5*1024*1024))
        while req.next_chunk()[1] is None: pass
        log.info("✅ تم حفظ نسخة في درايف بنجاح!")
    except Exception as e: log.error(f"⚠️ فشل درايف: {e}")

def upload_youtube(vid: Path):
    if not (CONFIG.yt_id and CONFIG.yt_refresh): return
    log.info("▶️ الرفع إلى YouTube (مسودة خاصة)...")
    try:
        yt = build("youtube", "v3", credentials=Credentials(None, refresh_token=CONFIG.yt_refresh, token_uri="[https://oauth2.googleapis.com/token](https://oauth2.googleapis.com/token)", client_id=CONFIG.yt_id, client_secret=CONFIG.yt_secret))
        body = {
            "snippet": {"title": f"نسخة المخرج | {CONFIG.topic} - {int(time.time())}", "description": "تم الإنتاج عبر المحرك الذاتي V22.12 باستخدام Antigravity SDK", "categoryId": "24"},
            "status": {"privacyStatus": "private"}
        }
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(vid), chunksize=-1, resumable=True, mimetype="video/mp4"))
        while req.next_chunk()[1] is None: pass
        log.info("✅ تم الرفع لليوتيوب بنجاح (Private)!")
    except Exception as e: log.error(f"⚠️ فشل يوتيوب: {e}")

# ==================================================================================================
# 6. الدورة الرئيسية للمحرك (هندسة القفز الثلاثية)
# ==================================================================================================
def main():
    start_time = datetime.now()
    log.info(f"▶ بدء محرك Skynet V22.12 (Multi-Source Fallback) | القضية: {CONFIG.topic}")
    
    director = Hybrid_Director()
    fetcher = MediaFetcher()
    
    script = director.plan_documentary()
    clips = []

    for i, s in enumerate(script):
        if (datetime.now() - start_time).total_seconds() > 13500: 
            log.warning("⏳ تم تجاوز الوقت المسموح، سيتم دمج ما تم إنجازه والتوقف لضمان الحفظ.")
            break 
        
        typ, original_q, foley, txt = s.get("media_type", "WIKIPEDIA"), s.get("search_query", ""), s.get("foley_type", "none"), s.get("narration", "")
        pfx = CONFIG.paths.cache / f"s_{i:03d}"
        c_mp4, c_wav, c_foley, c_mp3 = pfx.with_suffix(".mp4"), pfx.with_suffix(".wav"), Path(f"{pfx}_foley.mp3"), pfx.with_suffix(".mp3")
        
        if c_mp4.exists() and c_mp4.stat().st_size > 50000: clips.append(c_mp4); continue
            
        log.info(f"\n🎥 جاري العمل على المشهد {i+1}...")
        if not c_wav.exists(): director.generate_voice(txt, c_wav)
        if not c_wav.exists(): continue
        
        has_foley = fetcher.fetch_media("FREESOUND", enforce_english_query(foley), c_foley, 0) if foley != "none" else False
        dur = process_audio(c_wav, c_foley, has_foley, c_mp3)

        scene_approved = False
        montage_style = "NORMAL"
        current_q = original_q
        
        # إعداد مصادر البحث (3 محاولات لكل مصدر ثم القفز)
        sources_vid = ["PEXELS", "PEXELS", "PEXELS", "PIXABAY", "PIXABAY", "PIXABAY"]
        sources_img = ["WIKIPEDIA", "WIKIPEDIA", "WIKIPEDIA", "ARCHIVE", "ARCHIVE", "ARCHIVE"]
        
        sources_pool = sources_vid if typ in ["PEXELS", "PIXABAY"] else sources_img
        attempt_counter = 0

        while not scene_approved:
            if (datetime.now() - start_time).total_seconds() > 13500: break
                
            current_source = sources_pool[attempt_counter % len(sources_pool)]
            c_media = pfx.with_suffix(".mp4") if current_source in ["PEXELS", "PIXABAY"] else pfx.with_suffix(".jpg")
            
            # تنظيف الكلمة إجبارياً من أي أحرف عربية
            safe_q = enforce_english_query(current_q)
            index_in_source = attempt_counter % 3
            
            is_vid = fetcher.fetch_media(current_source, safe_q, c_media, index_in_source)
            
            if is_vid or c_media.exists():
                eval_res = director.evaluate_scene_with_scout(c_media, txt, current_source)
                
                if eval_res["accepted"]:
                    scene_approved = True
                    montage_style = eval_res["montage"]
                else:
                    new_q = eval_res.get("new_query", "")
                    new_q = enforce_english_query(new_q)
                    current_q = new_q if new_q else safe_q + " alternative"
                    log.warning(f"🔄 المراجع رفض اللقطة. الانتقال للبحث بكلمة: {current_q}")
                    try: c_media.unlink()
                    except: pass
            else:
                log.warning(f"⚠️ المصدر {current_source} لم يعطِ نتائج لـ '{safe_q}'. المحاولة {index_in_source+1}/3...")
                time.sleep(2) # كبح جماح الحلقة
                
                # إذا جربنا 3 مرات (نفس المصدر) وفشلت كلها، نعدل الكلمة قليلاً للهروب من الفشل المتكرر
                if index_in_source == 2:
                    current_q = safe_q.split()[0] if len(safe_q.split()) > 1 else safe_q + " mystery"
                
            attempt_counter += 1

        if scene_approved:
            render_scene(c_media, c_media.suffix == ".mp4", c_mp3, c_mp4, dur, montage_style)
            if c_mp4.exists(): clips.append(c_mp4)

    final_vid = CONFIG.paths.base / f"MasterDoc_{int(time.time())}.mp4"
    if clips:
        txt_list = CONFIG.paths.base / "video_list.txt"
        txt_list.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in clips), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt_list), "-c", "copy", str(final_vid)], stdout=subprocess.DEVNULL)
        log.info("🎬 تم تصدير الفيلم. جاري الرفع للسحابة لحفظ النسخة...")
        upload_drive(final_vid)
        upload_youtube(final_vid)

    if final_vid.exists():
        director.self_critique_and_recode(final_vid)

if __name__ == "__main__": main()
