#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================================================
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE (HYBRID V17.3 - Multi-Key)
- السيناريو: حصرياً عبر وكيل Google Antigravity (agy CLI).
- الصوت: يولد عبر Google AI Studio (Gemini TTS) مع نظام التبديل التلقائي للمفاتيح.
- الوسائط: Pexels, Pixabay, Mapbox, Wikipedia, Freesound.
- المونتاج: FFmpeg + Groq (لصناعة الترجمة).
- النشر: YouTube + Google Drive.
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
# 1. إعدادات النظام والمراقبة
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
    return logger

log = setup_logger()

# ==================================================================================================
# 2. الإعدادات والمسارات
# ==================================================================================================
@dataclass
class PipelinePaths:
    base: Path = field(default_factory=lambda: Path("./output_build"))
    cache: Path = field(default_factory=lambda: Path("./output_build/cache"))
    scenes: Path = field(default_factory=lambda: Path("./output_build/scenes"))
    manifest: Path = field(default_factory=lambda: Path("./output_build/master_manifest.json"))
    def initialize(self):
        for p in [self.base, self.cache, self.scenes]: p.mkdir(parents=True, exist_ok=True)

class HybridConfig:
    topic = os.environ.get("VIDEO_TOPIC", "لغز اختفاء طائرة دي بي كوبر")
    paths = PipelinePaths()
    
    # جلب جميع المفاتيح مفصولة بفاصلة وتحويلها إلى قائمة
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

if not CONFIG.gemini_keys:
    sys.exit("🛑 حرج: لم يتم العثور على أي مفاتيح في GEMINI_API_KEY!")

# ==================================================================================================
# 3. العقل الهجين (Antigravity للسيناريو + AI Studio للصوت)
# ==================================================================================================
class Hybrid_Director:
    def plan_documentary(self) -> List[Dict]:
        if CONFIG.paths.manifest.exists():
            log.info("استعادة خطة السيناريو من الملف المحلي...")
            return json.loads(CONFIG.paths.manifest.read_text(encoding="utf-8"))

        log.info(f"تخطيط الوثائقي حصرياً عبر وكيل Google Antigravity | الموضوع: {CONFIG.topic}")
        
        prompt = f"""
        أنت كبير مخرجي الوثائقيات الجنائية. موضوعنا هو: "{CONFIG.topic}".
        مهمتك بناء سيناريو استقصائي متكامل من 20 إلى 25 مشهداً.
        
        الأدوات المتاحة (media_type): PEXELS, PIXABAY, MAPBOX, WIKIPEDIA.
        وحدد المؤثر الصوتي الخلفي (foley_type) بالإنجليزية (مثال: "rain", "none").
        
        القيود: السرد 30 كلمة بالعربية الفصحى المشكولة بدقة تامة.
        أخرج الرد كـ JSON Array فقط:
        [
          {{
            "scene_num": 1,
            "media_type": "PEXELS",
            "search_query": "dark street rain",
            "foley_type": "heavy rain",
            "narration": "فِي لَيْلَةٍ عَاصِفَةٍ، بَدَأَتْ الْقِصَّةُ..."
          }}
        ]
        """
        
        for attempt in range(3):
            try:
                log.info(f"جاري الطلب من Antigravity (المحاولة {attempt + 1}/3)...")
                cmd = ["agy", "--model", "gemini-3.1-pro", "--effort", "high", "-p", prompt]
                result = subprocess.run(cmd, capture_output=True, text=True, check=True)
                
                clean = re.search(r'\[.*\]', result.stdout.strip(), re.DOTALL).group(0)
                data = json.loads(clean)
                
                CONFIG.paths.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                log.info("✅ تم توليد السيناريو عبر Antigravity بنجاح!")
                return data
                
            except subprocess.CalledProcessError as e:
                log.warning(f"⚠️ فشل Antigravity في الاستجابة: {e.stderr}")
                time.sleep(5)
            except Exception as e:
                log.warning(f"⚠️ فشل في قراءة أو استخراج الرد: {e}")
                time.sleep(5)
                
        sys.exit("🛑 فشل Antigravity نهائياً في توليد السيناريو بعد 3 محاولات.")

    def generate_voice(self, text: str, out_wav: Path):
        prompt = f"[INSTRUCTION: Documentary narrator. Deep, chilling voice. Read normally.]\n\n{text}"
        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"], 
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
                )
            )
        )
        
        # نظام تدوير المفاتيح (Key Rotation)
        total_keys = len(CONFIG.gemini_keys)
        for i, key in enumerate(CONFIG.gemini_keys):
            try:
                temp_client = genai.Client(api_key=key)
                res = temp_client.models.generate_content(model="gemini-3.8-flash-tts", contents=prompt, config=cfg)
                raw = res.candidates[0].content.parts[0].inline_data.data
                out_wav.write_bytes(base64.b64decode(raw) if isinstance(raw, str) else raw)
                return # تم توليد الصوت بنجاح، اخرج من الحلقة
            except Exception as e:
                log.warning(f"⚠️ فشل المفتاح ({i+1}/{total_keys}) - جاري التبديل للمفتاح التالي... | السبب المباشر: {str(e)[:100]}")
                time.sleep(2)
                
        log.error("❌ استنفدت جميع المفاتيح ولم نتمكن من توليد الصوت لهذا المشهد!")

# ==================================================================================================
# 4. محرك استدعاء الوسائط
# ==================================================================================================
class MediaFetcher:
    def __init__(self):
        self.h = {"User-Agent": "HybridPipeline/17.3"}

    def get_pexels_video(self, query: str, out: Path) -> bool:
        if not CONFIG.pexels: return False
        try:
            r = requests.get(f"https://api.pexels.com/videos/search?query={query}&orientation=landscape", headers={"Authorization": CONFIG.pexels}, timeout=10).json()
            if r.get("videos"):
                url = sorted(r["videos"][0]["video_files"], key=lambda x: x.get("width", 0), reverse=True)[0]["link"]
                out.write_bytes(requests.get(url, timeout=15).content)
                return True
        except: pass
        return False

    def get_pixabay_video(self, query: str, out: Path) -> bool:
        if not CONFIG.pixabay: return False
        try:
            r = requests.get(f"https://pixabay.com/api/videos/?key={CONFIG.pixabay}&q={query}", timeout=10).json()
            if int(r.get("totalHits", 0)) > 0:
                url = r["hits"][0]["videos"]["large"]["url"]
                out.write_bytes(requests.get(url, timeout=15).content)
                return True
        except: pass
        return False

    def get_mapbox(self, query: str, out: Path) -> bool:
        if not CONFIG.mapbox: return False
        try:
            url = f"https://api.mapbox.com/styles/v1/mapbox/dark-v11/static/{query},14,0,0/1920x1080?access_token={CONFIG.mapbox}"
            out.write_bytes(requests.get(url, timeout=10).content)
            return True
        except: pass
        return False

    def get_wikipedia(self, query: str, out: Path) -> bool:
        try:
            r = requests.get(f"https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch={query}&prop=pageimages&pithumbsize=1920&format=json", headers=self.h, timeout=10).json()
            pages = r.get("query", {}).get("pages", {})
            for _, p in pages.items():
                img_url = p.get("thumbnail", {}).get("source")
                if img_url and not img_url.endswith((".svg", ".webm")):
                    out.write_bytes(requests.get(img_url, headers=self.h, timeout=15).content)
                    return True
        except: pass
        return False

    def get_freesound_foley(self, query: str, out: Path) -> bool:
        if not CONFIG.freesound or query.lower() == "none": return False
        try:
            r = requests.get(f"https://freesound.org/apiv2/search/text/?query={query}&token={CONFIG.freesound}&fields=previews", timeout=10).json()
            if r.get("results"):
                url = r["results"][0]["previews"]["preview-hq-mp3"]
                out.write_bytes(requests.get(url, timeout=10).content)
                return True
        except: pass
        return False

    def fallback_graphic(self, query: str, out: Path):
        canvas = Image.new("RGB", (1920, 1080), (20, 22, 25))
        d = ImageDraw.Draw(canvas)
        d.text((960, 540), f"CLASSIFIED EVIDENCE\n{query[:30]}", fill=(180, 50, 50), anchor="mm")
        canvas.save(out, "JPEG")

# ==================================================================================================
# 5. المزامنة والتفريغ الصوتي والمونتاج
# ==================================================================================================
def groq_transcribe(audio_path: Path) -> List[Dict]:
    if not CONFIG.groq: return []
    try:
        with open(audio_path, "rb") as f:
            res = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions", 
                headers={"Authorization": f"Bearer {CONFIG.groq}"}, 
                files={"file": (audio_path.name, f, "audio/mpeg")}, 
                data={"model": "whisper-large-v3", "response_format": "verbose_json", "timestamp_granularities[]": "word"}
            )
        return res.json().get("words", [])
    except: return []

def generate_ass(words_data: List[Dict], fallback_text: str, duration: float, out_ass: Path, badge: str):
    def ft(s: float) -> str: return f"{int(s//3600)}:{int((s%3600)//60):02d}:{s%60:05.2f}"
    events = []
    if words_data:
        chunk, start = [], 0.0
        for i, w in enumerate(words_data):
            if not chunk: start = w['start']
            chunk.append(w['word'])
            if len(chunk) == 5 or i == len(words_data)-1:
                events.append(f"Dialogue: 1,{ft(start)},{ft(w['end'])},MainSub,,0,0,0,,{get_display(arabic_reshaper.reshape(' '.join(chunk)))}")
                chunk = []
    else:
        w_list = fallback_text.split()
        ch_dur = duration / max(1, len(w_list)//5)
        for i in range(0, len(w_list), 5):
            events.append(f"Dialogue: 1,{ft(i//5 * ch_dur)},{ft((i//5 + 1) * ch_dur)},MainSub,,0,0,0,,{get_display(arabic_reshaper.reshape(' '.join(w_list[i:i+5])))}")

    badge_disp = get_display(arabic_reshaper.reshape(badge))
    ass = f"""[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, ScaleX, ScaleY, Spacing, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: MainSub,Noto Sans Arabic,110,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,100,100,0,1,4,4,2,80,80,100
Style: TopBadge,Noto Sans Arabic,35,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,-1,100,100,0,1,2,2,7,60,60,50
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{ft(duration)},TopBadge,,0,0,0,,{badge_disp}\n{chr(10).join(events)}"""
    out_ass.write_text(ass, encoding="utf-8")

def process_audio(voice: Path, foley: Path, has_foley: bool, out_mp3: Path) -> float:
    if has_foley:
        fc = "[0:a]silenceremove=stop_periods=-1:stop_duration=0.8:stop_threshold=-45dB[v_trim]; [1:a]volume=0.15[bg]; [v_trim][bg]amix=inputs=2:duration=first:dropout_transition=2[aout]; [aout]loudnorm=I=-23[norm]"
        cmd = ["ffmpeg", "-y", "-i", str(voice), "-stream_loop", "-1", "-i", str(foley), "-filter_complex", fc, "-map", "[norm]", "-ar", "48000", str(out_mp3)]
    else:
        fc = "[0:a]silenceremove=stop_periods=-1:stop_duration=0.8:stop_threshold=-45dB,loudnorm=I=-23[aout]"
        cmd = ["ffmpeg", "-y", "-i", str(voice), "-filter_complex", fc, "-map", "[aout]", "-ar", "48000", str(out_mp3)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    probe_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_mp3)]
    return float(subprocess.check_output(probe_cmd).decode().strip())

def render_scene(media: Path, is_video: bool, ass: Path, audio: Path, out_mp4: Path, dur: float):
    fps = 24
    if is_video:
        fc = f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,eq=contrast=1.12:saturation=0.85,vignette=PI/3.6,subtitles='{ass}',fps={fps}[v]"
        cmd = ["ffmpeg", "-y", "-stream_loop", "-1", "-i", str(media), "-i", str(audio), "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out_mp4)]
    else:
        media = media.with_suffix(".jpg") if media.suffix == ".png" else media
        fc = f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,zoompan=z='min(1.15, 1.05+0.0003*on)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={int(dur*fps)}:s=1920x1080,eq=contrast=1.12,vignette=PI/3.6,subtitles='{ass}',fps={fps}[v]"
        cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(media), "-i", str(audio), "-filter_complex", fc, "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(out_mp4)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ==================================================================================================
# 6. النشر والأرشفة السحابية
# ==================================================================================================
def upload_drive(vid: Path):
    if not (CONFIG.yt_id and CONFIG.drive_token): return
    log.info("الرفع إلى Google Drive كنسخة احتياطية...")
    try:
        dr = build("drive", "v3", credentials=Credentials(None, refresh_token=CONFIG.drive_token, token_uri="https://oauth2.googleapis.com/token", client_id=CONFIG.yt_id, client_secret=CONFIG.yt_secret))
        res = dr.files().list(q="name='Broadcast_Vault' and mimeType='application/vnd.google-apps.folder'", fields="files(id)").execute()
        fid = res.get("files")[0]["id"] if res.get("files") else dr.files().create(body={"name": "Broadcast_Vault", "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]
        req = dr.files().create(body={"name": vid.name, "parents": [fid]}, media_body=MediaFileUpload(str(vid), mimetype="video/mp4", resumable=True, chunksize=5*1024*1024))
        while req.next_chunk()[1] is None: pass
        log.info("✅ تم الرفع لدرايف بنجاح!")
    except Exception as e: log.error(f"فشل درايف: {e}")

def upload_youtube(vid: Path, title: str):
    if not (CONFIG.yt_id and CONFIG.yt_refresh): return
    log.info("النشر الحصري على YouTube...")
    try:
        yt = build("youtube", "v3", credentials=Credentials(None, refresh_token=CONFIG.yt_refresh, token_uri="https://oauth2.googleapis.com/token", client_id=CONFIG.yt_id, client_secret=CONFIG.yt_secret))
        body = {
            "snippet": {"title": f"تحقيق استقصائي: {title}", "description": "فيلم وثائقي تحقيقي تم إنتاجه بالكامل عبر خط الإنتاج المستقل.", "tags": ["وثائقي", "تحقيق", "غموض"], "categoryId": "24"},
            "status": {"privacyStatus": "private"}
        }
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(vid), mimetype="video/mp4", resumable=True, chunksize=5*1024*1024))
        while req.next_chunk()[1] is None: pass
        log.info("✅ تم النشر على يوتيوب بنجاح!")
    except Exception as e: log.error(f"فشل الرفع ليوتيوب: {e}")

# ==================================================================================================
# 7. وحدة التحكم المركزية
# ==================================================================================================
def main():
    start = datetime.now()
    log.info(f"▶ بدء محرك الإنتاج الهجين V17.3 | القضية: {CONFIG.topic}")
    
    director = Hybrid_Director()
    fetcher = MediaFetcher()
    
    script = director.plan_documentary()
    clips = []

    for i, s in enumerate(script):
        typ, q, foley = s.get("media_type", "WIKIPEDIA"), s.get("search_query", ""), s.get("foley_type", "none")
        txt = s.get("narration", "")
        pfx = CONFIG.paths.cache / f"s_{i:03d}"
        
        c_mp4 = pfx.with_suffix(".mp4")
        c_wav = pfx.with_suffix(".wav")
        c_foley = Path(f"{pfx}_foley.mp3") 
        c_mp3 = pfx.with_suffix(".mp3")
        c_ass = pfx.with_suffix(".ass")
        
        if c_mp4.exists() and c_mp4.stat().st_size > 50000: 
            clips.append(c_mp4)
            continue
            
        log.info(f"المشهد {i+1} | الأداة: {typ} | المؤثر: {foley}")

        director.generate_voice(txt, c_wav)
        has_foley = fetcher.get_freesound_foley(foley, c_foley)
        
        if c_wav.exists():
            dur = process_audio(c_wav, c_foley, has_foley, c_mp3)
            words = groq_transcribe(c_mp3)
        else:
            log.warning("تخطي المشهد لفشل توليد الصوت.")
            continue

        is_vid = False
        if typ == "PEXELS": is_vid = fetcher.get_pexels_video(q, pfx.with_suffix(".mp4"))
        elif typ == "PIXABAY": is_vid = fetcher.get_pixabay_video(q, pfx.with_suffix(".mp4"))
        elif typ == "MAPBOX": fetcher.get_mapbox(q, pfx.with_suffix(".jpg"))
        elif typ == "WIKIPEDIA": fetcher.get_wikipedia(q, pfx.with_suffix(".jpg"))
        
        c_media = pfx.with_suffix(".mp4") if is_vid else pfx.with_suffix(".jpg")
        if not c_media.exists(): 
            fetcher.fallback_graphic(q, c_media.with_suffix(".jpg"))
            c_media = pfx.with_suffix(".jpg")
        
        badges = {"PEXELS": "لقطات سينمائية", "PIXABAY": "أرشيف عام", "MAPBOX": "إحداثيات جغرافية تكتيكية", "WIKIPEDIA": "سجلات التحقيق الرسمية"}
        
        generate_ass(words, txt, dur, c_ass, f"● {badges.get(typ, 'ملف سري')} | {q}")
        render_scene(c_media, is_vid, c_ass, c_mp3, c_mp4, dur)
        clips.append(c_mp4)

    log.info("تجميع الفيلم النهائي وتصديره...")
    txt_list = CONFIG.paths.base / "list.txt"
    txt_list.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in clips), encoding="utf-8")
    
    final_vid = CONFIG.paths.base / f"MasterDoc_{int(time.time())}.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt_list), "-c", "copy", str(final_vid)], stdout=subprocess.DEVNULL)
    
    upload_drive(final_vid)
    upload_youtube(final_vid, CONFIG.topic)
    
    log.info(f"✔ اكتمل الفيلم بنجاح! الوقت المستغرق: {datetime.now() - start}")

if __name__ == "__main__": 
    main()
