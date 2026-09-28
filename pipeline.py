#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================================================
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE (HYBRID V19.1 - Resilience)
- السيناريو والنقد: Google Antigravity (gemini-3.1-pro).
- الصوت: Google AI Studio (Charon) + تبريد 30 ثانية + الدوران حول المفاتيح 3 جولات.
- المراجع البصري-السمعي: gemini-3.5-flash (متعدد الجولات لضمان عدم الفشل).
- الهندسة الصوتية: إصلاح مشكلة تداخل الصوت (Audio Pumping).
- الذاكرة وحلقة الكمال: تسجيل الأخطاء والتعلم، بحد 3.75 ساعات.
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
    COLORS = {'INFO': "\x1b[38;5;39m", 'WARNING': "\x1b[38;5;214m", 'ERROR': "\x1b[38;5;196m", 'CRITICAL': "\x1b[48;5;196;38;5;231m\x1b[1m"}
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
        fh.setFormatter(logging.Formatter("%(asctime)s | [%(levelname)s] | %(message)s"))
        logger.addHandler(fh)
    return logger

log = setup_logger()

MEMORY_FILE = Path("director_memory.md")
def read_memory() -> str:
    if MEMORY_FILE.exists(): return MEMORY_FILE.read_text(encoding="utf-8")
    return "هذه أول جلسة لك. ركز على إنتاج سيناريو من 40-50 مشهداً بكلمات طويلة للوصول لـ 20 دقيقة."

def append_memory(session_summary: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"\n\n### تقرير الجلسة [{now}]\n{session_summary}"
    with open(MEMORY_FILE, "a", encoding="utf-8") as f: f.write(entry)

# ==================================================================================================
# 2. الإعدادات والمسارات
# ==================================================================================================
@dataclass
class PipelinePaths:
    base: Path = field(default_factory=lambda: Path("./output_build"))
    cache: Path = field(default_factory=lambda: Path("./output_build/cache"))
    manifest: Path = field(default_factory=lambda: Path("./output_build/master_manifest.json"))
    def initialize(self):
        for p in [self.base, self.cache]: p.mkdir(parents=True, exist_ok=True)

class HybridConfig:
    topic = os.environ.get("VIDEO_TOPIC", "لغز اختفاء طائرة دي بي كوبر")
    paths = PipelinePaths()
    gemini_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
    pexels = os.environ.get("PEXELS_API_KEY", "")
    pixabay = os.environ.get("PIXABAY_API_KEY", "")
    mapbox = os.environ.get("MAPBOX_API_KEY", "")
    groq = os.environ.get("GROQ_API_KEY", "")
    freesound = os.environ.get("FREESOUND_API_KEY", "")
    yt_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    yt_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    drive_token = os.environ.get("DRIVE_REFRESH_TOKEN", "")
    yt_refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")

CONFIG = HybridConfig()
CONFIG.paths.initialize()
if not CONFIG.gemini_keys: sys.exit("🛑 حرج: مفاتيح GEMINI_API_KEY مفقودة!")

# ==================================================================================================
# 3. العقل الهجين والمراجع السمعي-البصري الفوري
# ==================================================================================================
class Hybrid_Director:
    def plan_documentary(self) -> List[Dict]:
        if CONFIG.paths.manifest.exists(): return json.loads(CONFIG.paths.manifest.read_text(encoding="utf-8"))

        log.info(f"كتابة السيناريو الضخم عبر Antigravity (Pro) | القضية: {CONFIG.topic}")
        prompt = f"""
        أنت كبير المخرجين. موضوعنا: "{CONFIG.topic}".
        قم ببناء سيناريو ضخم جداً من 40 إلى 50 مشهداً (لضمان مدة تتجاوز 18 دقيقة).
        القيود:
        1. النص في كل مشهد من 60 إلى 80 كلمة.
        2. عربية فصحى مشكولة بدقة تامة.
        3. الأدوات: PEXELS, PIXABAY, MAPBOX, WIKIPEDIA. المؤثر (foley_type) بالإنجليزية.
        
        [الذاكرة التراكمية]:\n{read_memory()}
        
        أخرج JSON Array فقط:
        [
          {{"scene_num": 1, "media_type": "PEXELS", "search_query": "dark street", "foley_type": "rain", "narration": "فِي لَيْلَةٍ عَاصِفَةٍ..."}}
        ]
        """
        for attempt in range(3):
            try:
                cmd = ["agy", "--model", "gemini-3.1-pro", "--effort", "high", "-p", prompt]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=900)
                clean = re.search(r'\[.*\]', result.stdout.strip(), re.DOTALL).group(0)
                data = json.loads(clean)
                CONFIG.paths.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                return data
            except subprocess.TimeoutExpired: log.warning(f"⚠️ انتهى وقت Antigravity (المحاولة {attempt+1})")
            except Exception as e: log.warning(f"⚠️ خطأ أثناء التوليد: {e}"); time.sleep(5)
        sys.exit("🛑 فشل Antigravity نهائياً في كتابة السيناريو.")

    def critique_and_improve(self) -> bool:
        log.info("🧠 بدء جلسة التقييم الذاتي الشاملة...")
        manifest_text = CONFIG.paths.manifest.read_text(encoding="utf-8")
        logs_text = ""
        if Path("production_logs.txt").exists():
            logs = Path("production_logs.txt").read_text(encoding="utf-8").split("\n")
            logs_text = "\n".join([line for line in logs if "WARNING" in line or "ERROR" in line or "CRITICAL" in line][-50:])
        
        if not logs_text.strip():
            log.info("✅ الفيلم مثالي بناءً على السجلات.")
            append_memory("تم إنتاج الفيديو بسلاسة بدون أخطاء تقنية.")
            return True

        prompt = f"""أنت المخرج والمراجع. حاولنا إنتاج السيناريو:\n{manifest_text}\nواجهتنا الأخطاء:\n{logs_text}\nأصلح السيناريو وأخرج JSON جديد. إذا كانت الأخطاء طفيفة ولا تستدعي تعديلاً، أخرج كلمة PERFECT فقط."""
        try:
            cmd = ["agy", "--model", "gemini-3.1-pro", "--effort", "high", "-p", prompt]
            output = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=600).stdout.strip()
            
            if "PERFECT" in output:
                append_memory("ظهرت تحذيرات لكن تم تجاوزها لاعتماد المقطع.")
                return True
                
            clean = re.search(r'\[.*\]', output, re.DOTALL).group(0)
            CONFIG.paths.manifest.write_text(json.dumps(json.loads(clean), ensure_ascii=False, indent=2), encoding="utf-8")
            log.info("🔄 تم تحديث السيناريو بناءً على النقد!")
            append_memory(f"تم إصلاح أخطاء بصرية/برمجية وتحديث السيناريو بنجاح.")
            Path("production_logs.txt").write_text("")
            return False 
        except Exception as e:
            log.warning(f"⚠️ فشل التقييم، سيتم الاعتماد على النسخة الحالية: {e}")
            return True

    def generate_voice(self, text: str, out_wav: Path):
        prompt = f"[INSTRUCTION: Documentary narrator. Deep, chilling voice. Read normally.]\n\n{text}"
        cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon"))))
        
        max_rounds = 3 # 3 دورات كاملة حول المفاتيح
        for round_num in range(max_rounds):
            for i, key in enumerate(CONFIG.gemini_keys):
                try:
                    temp_client = genai.Client(api_key=key)
                    res = temp_client.models.generate_content(model="gemini-3.8-flash-tts", contents=prompt, config=cfg)
                    raw = res.candidates[0].content.parts[0].inline_data.data
                    out_wav.write_bytes(base64.b64decode(raw) if isinstance(raw, str) else raw)
                    log.info(f"⏳ تم توليد الصوت بنجاح (الجولة {round_num+1}). بدء فترة التبريد (30 ثانية)...")
                    time.sleep(30)
                    return 
                except Exception as e: 
                    log.warning(f"⚠️ فشل المفتاح ({i+1}/{len(CONFIG.gemini_keys)}) | السبب: {str(e)[:50]}... التبديل للتالي.")
                    time.sleep(2)
            
            log.warning(f"🔄 انتهت الجولة {round_num+1} من تجربة المفاتيح للصوت. أخذ استراحة 10 ثوانٍ قبل المحاولة مجدداً...")
            time.sleep(10)
            
        log.error("❌ استنفدت جميع المفاتيح بعد 3 جولات! تم التخطي.")

    def evaluate_scene_multimodal(self, media_path: Path, audio_path: Path, narration: str) -> Dict:
        """يستخدم نموذج Flash 3.5 لسماع الصوت، رؤية المشهد، وتقييمهما معاً، مع نظام الدوران للمفاتيح"""
        log.info("👁️🎧 المراجع الفوري (Flash 3.5) يسمع ويشاهد المشهد...")
        
        eval_img_path = media_path.with_suffix(".eval.jpg")
        try:
            if media_path.suffix == ".mp4": subprocess.run(["ffmpeg", "-y", "-i", str(media_path), "-vframes", "1", "-q:v", "2", str(eval_img_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else: eval_img_path = media_path
        except: pass

        prompt = f"""
        أنت مخرج مونتاج لوثائقي جنائي. السرد: "{narration}"
        قيّم ما إذا كان المشهد يتناسب مع الصوت ومع جو الجريمة الغامض. 
        ثم حدد أسلوب المونتاج الأنسب من هذه الخيارات: ZOOM_IN, PAN_RIGHT, BW (لأبيض وأسود), NORMAL.
        أخرج ردك كـ JSON فقط بالصيغة التالية:
        {{"decision": "ACCEPT" أو "REJECT", "montage": "ZOOM_IN"}}
        """
        
        max_rounds = 2 # دورتان كافيتان للمراجع الفوري
        for round_num in range(max_rounds):
            for i, key in enumerate(CONFIG.gemini_keys):
                audio_file = None
                img_file = None
                try:
                    client = genai.Client(api_key=key)
                    audio_file = client.files.upload(file=str(audio_path))
                    img_file = client.files.upload(file=str(eval_img_path))
                    
                    res = client.models.generate_content(
                        model="gemini-3.5-flash", 
                        contents=[prompt, img_file, audio_file],
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    
                    # تنظيف السيرفر
                    try: client.files.delete(name=audio_file.name); client.files.delete(name=img_file.name)
                    except: pass
                    if eval_img_path != media_path and eval_img_path.exists(): eval_img_path.unlink()
                    
                    data = json.loads(res.text)
                    if data.get("decision") == "ACCEPT":
                        log.info(f"✅ الناقد اعتمد اللقطة. طلب مونتاج: {data.get('montage', 'NORMAL')}")
                        return {"valid": True, "montage": data.get("montage", "NORMAL")}
                    else:
                        log.warning("❌ الناقد رفض اللقطة لعدم التوافق.")
                        return {"valid": False, "montage": "NORMAL"}
                        
                except Exception as e:
                    if audio_file:
                        try: client.files.delete(name=audio_file.name)
                        except: pass
                    if img_file:
                        try: client.files.delete(name=img_file.name)
                        except: pass
                    log.warning(f"⚠️ فشل المفتاح ({i+1}) في المراجعة. التبديل للتالي...")
                    time.sleep(2)
            time.sleep(5)

        log.warning("⚠️ استنفدت المفاتيح للمراجع الفوري. سيتم الاعتماد الافتراضي للقطة.")
        if eval_img_path != media_path and eval_img_path.exists(): eval_img_path.unlink()
        return {"valid": True, "montage": "ZOOM_IN"} # افتراضي

# ==================================================================================================
# 4. محرك استدعاء الوسائط ومعالجة الصوت والمونتاج (محسن)
# ==================================================================================================
class MediaFetcher:
    def __init__(self): self.h = {"User-Agent": "HybridPipeline/19.1"}
    
    def fetch_video(self, source: str, query: str, out: Path, index: int = 0) -> bool:
        try:
            if source == "PEXELS" and CONFIG.pexels:
                r = requests.get(f"https://api.pexels.com/videos/search?query={query}&orientation=landscape", headers={"Authorization": CONFIG.pexels}, timeout=15).json()
                if r.get("videos") and len(r["videos"]) > index:
                    out.write_bytes(requests.get(sorted(r["videos"][index]["video_files"], key=lambda x: x.get("width", 0), reverse=True)[0]["link"], timeout=60).content); return True
            elif source == "PIXABAY" and CONFIG.pixabay:
                r = requests.get(f"https://pixabay.com/api/videos/?key={CONFIG.pixabay}&q={query}", timeout=15).json()
                if int(r.get("totalHits", 0)) > index:
                    out.write_bytes(requests.get(r["hits"][index]["videos"]["large"]["url"], timeout=60).content); return True
        except: pass; return False

    def fetch_image(self, source: str, query: str, out: Path) -> bool:
        try:
            if source == "MAPBOX" and CONFIG.mapbox:
                res = requests.get(f"https://api.mapbox.com/styles/v1/mapbox/dark-v11/static/{query},14,0,0/1920x1080?access_token={CONFIG.mapbox}", timeout=20)
                if res.status_code == 200 and b"{" not in res.content[:10]: out.write_bytes(res.content); return True
            elif source == "WIKIPEDIA":
                r = requests.get(f"https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={query}&prop=pageimages&pithumbsize=1920&format=json", headers=self.h, timeout=15).json()
                pages = list(r.get("query", {}).get("pages", {}).values())
                if pages and pages[0].get("thumbnail", {}).get("source"):
                    out.write_bytes(requests.get(pages[0]["thumbnail"]["source"], headers=self.h, timeout=20).content); return True
        except: pass; return False

    def get_freesound_foley(self, query: str, out: Path) -> bool:
        if not CONFIG.freesound or query.lower() == "none": return False
        try:
            r = requests.get(f"https://freesound.org/apiv2/search/text/?query={query}&token={CONFIG.freesound}&fields=previews", timeout=15).json()
            if r.get("results"): out.write_bytes(requests.get(r["results"][0]["previews"]["preview-hq-mp3"], timeout=30).content); return True
        except: pass; return False

    def fallback_graphic(self, query: str, out: Path):
        canvas = Image.new("RGB", (1920, 1080), (20, 22, 25)); d = ImageDraw.Draw(canvas)
        d.text((960, 540), f"CLASSIFIED EVIDENCE\n{query[:30]}", fill=(180, 50, 50), anchor="mm"); canvas.save(out, "JPEG")

def groq_transcribe(audio_path: Path) -> List[Dict]:
    if not CONFIG.groq: return []
    try:
        with open(audio_path, "rb") as f:
            res = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": f"Bearer {CONFIG.groq}"}, files={"file": (audio_path.name, f, "audio/mpeg")}, data={"model": "whisper-large-v3", "response_format": "verbose_json", "timestamp_granularities[]": "word"}, timeout=60)
        return res.json().get("words", [])
    except Exception as e: log.warning(f"⚠️ خطأ Groq: {e}"); return []

def generate_ass(words: List[Dict], fallback: str, dur: float, out: Path, badge: str):
    def ft(s): return f"{int(s//3600)}:{int((s%3600)//60):02d}:{s%60:05.2f}"
    evs = []
    if words:
        ch, st = [], 0.0
        for i, w in enumerate(words):
            if not ch: st = w['start']
            ch.append(w['word'])
            if len(ch) == 5 or i == len(words)-1: evs.append(f"Dialogue: 1,{ft(st)},{ft(w['end'])},Sub,,0,0,0,,{get_display(arabic_reshaper.reshape(' '.join(ch)))}"); ch = []
    else:
        wl = fallback.split(); cd = dur/max(1, len(wl)//5)
        for i in range(0, len(wl), 5): evs.append(f"Dialogue: 1,{ft(i//5*cd)},{ft((i//5+1)*cd)},Sub,,0,0,0,,{get_display(arabic_reshaper.reshape(' '.join(wl[i:i+5])))}")
    bdg = get_display(arabic_reshaper.reshape(badge))
    ass = f"[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]\nStyle: Sub,Noto Sans Arabic,110,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,100,100,0,1,4,4,2,80,80,100\nStyle: Bdg,Noto Sans Arabic,35,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,-1,100,100,0,1,2,2,7,60,60,50\n[Events]\nDialogue: 0,0:00:00.00,{ft(dur)},Bdg,,0,0,0,,{bdg}\n" + "\n".join(evs)
    out.write_text(ass, encoding="utf-8")

def process_audio(voice: Path, foley: Path, has_foley: bool, out: Path) -> float:
    # [الإصلاح الجذري] لتداخل الصوت المزعج
    if has_foley:
        fc = "[0:a]silenceremove=stop_periods=-1:stop_duration=0.8:stop_threshold=-45dB,loudnorm=I=-16[v]; [1:a]volume=0.04[bg]; [v][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        cmd = ["ffmpeg", "-y", "-i", str(voice), "-stream_loop", "-1", "-i", str(foley), "-filter_complex", fc, "-map", "[aout]", "-ar", "48000", str(out)]
    else:
        fc = "[0:a]silenceremove=stop_periods=-1:stop_duration=0.8:stop_threshold=-45dB,loudnorm=I=-16[aout]"
        cmd = ["ffmpeg", "-y", "-i", str(voice), "-filter_complex", fc, "-map", "[aout]", "-ar", "48000", str(out)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out)]).decode().strip())

def render_scene(media: Path, is_vid: bool, ass: Path, aud: Path, out: Path, dur: float, montage_hint: str):
    fps = 24
    color_fx = ",hue=s=0" if "BW" in montage_hint else ",eq=contrast=1.12:saturation=0.85"
    
    if is_vid:
        fc = f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080{color_fx},vignette=PI/3.6,subtitles='{ass}',fps={fps}[v]"
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(media), "-i", str(aud), "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out)]
    else:
        # ترجمة أوامر الناقد إلى حركة حقيقية
        if "PAN_RIGHT" in montage_hint: motion = "z=1.1:x='x+1':y='ih/2-(ih/zoom/2)'"
        elif "NORMAL" in montage_hint: motion = "z=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        else: motion = "z='min(1.15, 1.05+0.0003*on)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'" # ZOOM_IN
        
        fc = f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan={motion}:d={int(dur*fps)}:s=1920x1080{color_fx},vignette=PI/3.6,subtitles='{ass}',fps={fps}[v]"
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(media), "-i", str(aud), "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out)]
        
    try: subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    except: log.error("⚠️ FFmpeg تخطى الوقت.")

def upload_drive(vid: Path):
    if not (CONFIG.yt_id and CONFIG.drive_token): return
    log.info("الرفع إلى Google Drive...")
    try:
        dr = build("drive", "v3", credentials=Credentials(None, refresh_token=CONFIG.drive_token, token_uri="https://oauth2.googleapis.com/token", client_id=CONFIG.yt_id, client_secret=CONFIG.yt_secret))
        res = dr.files().list(q="name='Broadcast_Vault' and mimeType='application/vnd.google-apps.folder'", fields="files(id)").execute()
        fid = res.get("files")[0]["id"] if res.get("files") else dr.files().create(body={"name": "Broadcast_Vault", "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]
        req = dr.files().create(body={"name": vid.name, "parents": [fid]}, media_body=MediaFileUpload(str(vid), mimetype="video/mp4", resumable=True, chunksize=5*1024*1024))
        while req.next_chunk()[1] is None: pass
        log.info("✅ تم الرفع لدرايف بنجاح!")
    except Exception as e: log.error(f"فشل درايف: {e}")

# ==================================================================================================
# 5. وحدة التحكم المركزية (الزمن والإنتاج)
# ==================================================================================================
def main():
    start_time = datetime.now()
    max_seconds = 3 * 3600 + 45 * 60 # 3.75 ساعات
    log.info(f"▶ بدء محرك الإنتاج V19.1 | القضية: {CONFIG.topic}")
    
    director = Hybrid_Director()
    fetcher = MediaFetcher()
    
    while True:
        if (datetime.now() - start_time).total_seconds() > max_seconds:
            log.warning("⏳ اقتربنا من الحد الأقصى (4 ساعات). سيتم إنهاء الحلقة ورفع أفضل نسخة.")
            append_memory("توقفنا للحفاظ على السيرفر ورفعنا أفضل نسخة تم رندرتها.")
            break
            
        script = director.plan_documentary()
        clips = []

        for i, s in enumerate(script):
            typ, q, foley, txt = s.get("media_type", "WIKIPEDIA"), s.get("search_query", ""), s.get("foley_type", "none"), s.get("narration", "")
            pfx = CONFIG.paths.cache / f"s_{i:03d}"
            c_mp4, c_wav, c_foley, c_mp3, c_ass = pfx.with_suffix(".mp4"), pfx.with_suffix(".wav"), Path(f"{pfx}_foley.mp3"), pfx.with_suffix(".mp3"), pfx.with_suffix(".ass")
            
            if c_mp4.exists() and c_mp4.stat().st_size > 50000: clips.append(c_mp4); continue
                
            log.info(f"المشهد {i+1} | الأداة: {typ} | المؤثر: {foley}")

            if not c_wav.exists(): director.generate_voice(txt, c_wav)
            has_foley = fetcher.get_freesound_foley(foley, c_foley)
            
            if c_wav.exists(): dur = process_audio(c_wav, c_foley, has_foley, c_mp3); words = groq_transcribe(c_mp3)
            else: continue

            c_media = pfx.with_suffix(".mp4") if typ in ["PEXELS", "PIXABAY"] else pfx.with_suffix(".jpg")
            is_vid = False
            montage_style = "NORMAL"
            
            for attempt in range(3):
                if typ in ["PEXELS", "PIXABAY"]: is_vid = fetcher.fetch_video(typ, q, c_media, attempt)
                else: is_vid = not fetcher.fetch_image(typ, q, c_media)
                
                if not c_media.exists(): break
                
                # التقييم المتعدد (صوت + صورة + نص)
                eval_result = director.evaluate_scene_multimodal(c_media, c_wav, txt)
                if eval_result["valid"]:
                    montage_style = eval_result["montage"]
                    break
                else: c_media.unlink()
            
            if not c_media.exists(): 
                fetcher.fallback_graphic(q, c_media.with_suffix(".jpg"))
                c_media, is_vid, montage_style = pfx.with_suffix(".jpg"), False, "ZOOM_IN"
            
            badges = {"PEXELS": "لقطات سينمائية", "PIXABAY": "أرشيف عام", "MAPBOX": "إحداثيات جغرافية تكتيكية", "WIKIPEDIA": "سجلات التحقيق الرسمية"}
            generate_ass(words, txt, dur, c_ass, f"● {badges.get(typ, 'ملف سري')} | {q}")
            
            # الرندر مع الفلاتر الذكية
            render_scene(c_media, is_vid, c_ass, c_mp3, c_mp4, dur, montage_style)
            if c_mp4.exists(): clips.append(c_mp4)

        if director.critique_and_improve():
            log.info("🎬 المخرج النهائي اعتمد النسخة. جاري التصدير...")
            break
        else:
            log.info("🛠️ جاري إعادة هندسة المشاهد المعيبة...")

    if clips:
        txt_list = CONFIG.paths.base / "list.txt"
        txt_list.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in clips), encoding="utf-8")
        final_vid = CONFIG.paths.base / f"MasterDoc_{int(time.time())}.mp4"
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt_list), "-c", "copy", str(final_vid)], stdout=subprocess.DEVNULL)
        upload_drive(final_vid)
    log.info(f"✔ اكتملت الجلسة! الوقت الإجمالي: {datetime.now() - start_time}")

if __name__ == "__main__": main()
