#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================================================
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE (HYBRID V21.2 - The Vault)
- السيناريو والنقد النهائي: Google Antigravity (gemini-3.1-pro-high).
- المراجع الفوري العميق: gemini-3.6-flash-high (يفهم سياق الفيلم والنص السردي).
- أمان التصدير: دمج ورفع الفيديو (Drive + YouTube Private) **قبل** جلسة النقد وإعادة التشغيل.
- التبديل التلقائي: PEXELS <-> PIXABAY (3 محاولات) وحلقات WIKIPEDIA.
- التعديل الذاتي: المراجع النهائي يعدل الكود ويعيد التشغيل بعد تأمين النسخة.
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
# 1. إعدادات النظام
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

def read_memory() -> str:
    return MEMORY_FILE.read_text(encoding="utf-8") if MEMORY_FILE.exists() else "جلسة جديدة."

def append_memory(summary: str):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MEMORY_FILE, "a", encoding="utf-8") as f: f.write(f"\n\n### [{now}]\n{summary}")

# ==================================================================================================
# 2. المسارات والمفاتيح
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
# 3. العقل المدبر والمراجع الفوري 
# ==================================================================================================
class Hybrid_Director:
    def plan_documentary(self) -> List[Dict]:
        if CONFIG.paths.manifest.exists(): return json.loads(CONFIG.paths.manifest.read_text(encoding="utf-8"))

        log.info(f"كتابة السيناريو (gemini-3.1-pro-high) | القضية: {CONFIG.topic}")
        prompt = f"""أنت كبير المخرجين. قضيتنا: "{CONFIG.topic}".
        قم ببناء سيناريو ضخم (40-50 مشهداً، كل مشهد 60-80 كلمة).
        استخدم PEXELS, PIXABAY, WIKIPEDIA.
        أخرج JSON Array فقط: [{{"scene_num": 1, "media_type": "PEXELS", "search_query": "dark street", "foley_type": "rain", "narration": "في ليلة..."}}]"""
        
        for _ in range(3):
            try:
                result = subprocess.run(["agy", "--model", "gemini-3.1-pro-high", "--effort", "high", "-p", prompt], capture_output=True, text=True, timeout=900)
                match = re.search(r'\[.*\]', result.stdout.strip(), re.DOTALL)
                if match:
                    data = json.loads(match.group(0))
                    CONFIG.paths.manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                    return data
            except Exception as e: log.warning(f"⚠️ خطأ السيناريو: {e}"); time.sleep(5)
        sys.exit("🛑 فشل كتابة السيناريو.")

    def evaluate_scene_flash(self, media_path: Path, narration: str) -> Dict:
        log.info("👁️ المراجع الفوري (gemini-3.6-flash-high) يحلل السياق والمشهد...")
        eval_img_path = media_path.with_suffix(".eval.jpg")
        try:
            if media_path.suffix == ".mp4": subprocess.run(["ffmpeg", "-y", "-i", str(media_path), "-vframes", "1", "-q:v", "2", str(eval_img_path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else: eval_img_path = media_path
        except: pass

        prompt = f"""أنت مخرج مونتاج لفيلم وثائقي جنائي غامض بعنوان: "{CONFIG.topic}".
        النص السردي لهذا المشهد: "{narration}"
        
        هل المشهد يتطابق مع سياق النص وجو الجريمة والغموض؟
        إذا رفضت المشهد، اقترح كلمات بحث باللغة الإنجليزية (search_query) لمقطع أدق.
        حدد فلتر المونتاج: ZOOM_IN, PAN_RIGHT, BW, NORMAL.
        أخرج JSON فقط: {{"decision": "ACCEPT" أو "REJECT", "montage": "ZOOM_IN", "new_query": "creepy dark alley"}}"""
        
        try:
            cmd = ["agy", "--model", "gemini-3.6-flash-high", "--dangerously-skip-permissions", prompt, str(eval_img_path.resolve())]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            output = result.stdout.strip()
            
            if eval_img_path != media_path and eval_img_path.exists(): eval_img_path.unlink()
            
            match = re.search(r'\{.*\}', output, re.DOTALL)
            if match:
                return json.loads(match.group(0))
        except Exception as e:
            log.warning(f"⚠️ فشل المراجع الفوري: {str(e)[:50]}")
            if eval_img_path != media_path and eval_img_path.exists(): eval_img_path.unlink()
            
        return {"decision": "ACCEPT", "montage": "ZOOM_IN", "new_query": ""}

    def self_critique_and_recode(self, final_audio: Path) -> bool:
        log.info("🧠 المراجع النهائي يقوم بالتحليل الشامل للمشروع...")
        logs = Path("production_logs.txt").read_text()[-2000:] if Path("production_logs.txt").exists() else "No logs"
        
        prompt = f"""أنت الذكاء الاصطناعي المؤسس. استمع للمسار الصوتي واقرأ سجلات الأخطاء:
        {logs}
        إذا كان هناك خلل فادح (انقطاع صوت، توقف)، قم بكتابة كود `pipeline.py` جديد بالكامل ومُعدّل داخل كتلة ```python .
        إذا كان النظام يعمل بكفاءة، أجب بكلمة PERFECT فقط."""
        
        try:
            cmd = ["agy", "--model", "gemini-3.1-pro-high", "--dangerously-skip-permissions", prompt, str(final_audio.resolve())]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
            output = result.stdout.strip()
            
            if "PERFECT" in output:
                log.info("✅ المراجع النهائي يعتمد الكود والإنتاج الحالي.")
                return True
                
            code_match = re.search(r'```python(.*?)```', output, re.DOTALL)
            if code_match:
                new_code = code_match.group(1).strip()
                log.warning("🔄 تحذير: المراجع قام بتحديث الكود المصدري! جاري إعادة التشغيل...")
                append_memory("تم رصد خلل برمجي، السكربت قام بتحديث نفسه وأعاد التشغيل.")
                Path(__file__).write_text(new_code, encoding="utf-8")
                os.execv(sys.executable, ['python'] + sys.argv)
                
            return True
        except Exception as e:
            log.error(f"فشل التعديل الذاتي: {e}")
            return True

    def generate_voice(self, text: str, out_wav: Path):
        cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon"))))
        for key in CONFIG.gemini_keys:
            try:
                res = genai.Client(api_key=key).models.generate_content(model="gemini-3.8-flash-tts", contents=f"[INSTRUCTION: Deep chilling narrator]\n{text}", config=cfg)
                out_wav.write_bytes(base64.b64decode(res.candidates[0].content.parts[0].inline_data.data) if isinstance(res.candidates[0].content.parts[0].inline_data.data, str) else res.candidates[0].content.parts[0].inline_data.data)
                
                if out_wav.exists() and out_wav.stat().st_size > 1000:
                    time.sleep(30); return
            except: time.sleep(2)
        log.error("❌ استنفدت المفاتيح لتوليد الصوت!")

# ==================================================================================================
# 4. محرك الوسائط والمونتاج الآمن والرفع
# ==================================================================================================
class MediaFetcher:
    def __init__(self): self.h = {"User-Agent": "HybridPipeline/21.2"}
    
    def fetch_media(self, source: str, query: str, out: Path, index: int) -> bool:
        try:
            if source == "PEXELS" and CONFIG.pexels:
                r = requests.get(f"[https://api.pexels.com/videos/search?query=](https://api.pexels.com/videos/search?query=){query}&orientation=landscape", headers={"Authorization": CONFIG.pexels}).json()
                if r.get("videos") and len(r["videos"]) > index: out.write_bytes(requests.get(sorted(r["videos"][index]["video_files"], key=lambda x: x.get("width", 0), reverse=True)[0]["link"]).content); return True
            elif source == "PIXABAY" and CONFIG.pixabay:
                r = requests.get(f"[https://pixabay.com/api/videos/?key=](https://pixabay.com/api/videos/?key=){CONFIG.pixabay}&q={query}").json()
                if int(r.get("totalHits", 0)) > index: out.write_bytes(requests.get(r["hits"][index]["videos"]["large"]["url"]).content); return True
            elif source == "WIKIPEDIA":
                r = requests.get(f"[https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch=](https://en.wikipedia.org/w/api.php?action=query&generator=search&gsrsearch=){query}&prop=pageimages&pithumbsize=1920&format=json", headers=self.h).json()
                pages = list(r.get("query", {}).get("pages", {}).values())
                if pages and pages[index % len(pages)].get("thumbnail", {}).get("source"):
                    out.write_bytes(requests.get(pages[index % len(pages)]["thumbnail"]["source"], headers=self.h).content); return True
        except: pass
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
    except:
        return 3.0

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
            "snippet": {"title": f"نسخة المخرج | {CONFIG.topic} - {int(time.time())}", "description": "تم الإنتاج عبر المحرك الذاتي V21.2", "categoryId": "24"},
            "status": {"privacyStatus": "private"}
        }
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(vid), chunksize=-1, resumable=True, mimetype="video/mp4"))
        while req.next_chunk()[1] is None: pass
        log.info("✅ تم الرفع لليوتيوب بنجاح (Private)!")
    except Exception as e: log.error(f"⚠️ فشل يوتيوب: {e}")

# ==================================================================================================
# 5. وحدة التحكم المركزية (ترتيب العمليات لحفظ الفيديو قبل المراجعة)
# ==================================================================================================
def main():
    start_time = datetime.now()
    log.info(f"▶ بدء محرك Skynet V21.2 | القضية: {CONFIG.topic}")
    
    director = Hybrid_Director()
    fetcher = MediaFetcher()
    
    script = director.plan_documentary()
    clips = []
    final_audio_segments = []

    for i, s in enumerate(script):
        if (datetime.now() - start_time).total_seconds() > 13500: break 
        
        typ, original_q, foley, txt = s.get("media_type", "WIKIPEDIA"), s.get("search_query", ""), s.get("foley_type", "none"), s.get("narration", "")
        pfx = CONFIG.paths.cache / f"s_{i:03d}"
        c_mp4, c_wav, c_foley, c_mp3 = pfx.with_suffix(".mp4"), pfx.with_suffix(".wav"), Path(f"{pfx}_foley.mp3"), pfx.with_suffix(".mp3")
        
        if c_mp4.exists(): clips.append(c_mp4); final_audio_segments.append(c_mp3); continue
            
        log.info(f"المشهد {i+1} | الأساس: {typ}")
        if not c_wav.exists(): director.generate_voice(txt, c_wav)
        if not c_wav.exists(): continue
        
        has_foley = fetcher.fetch_media("FREESOUND", foley, c_foley, 0) if foley != "none" else False
        dur = process_audio(c_wav, c_foley, has_foley, c_mp3)
        final_audio_segments.append(c_mp3)

        montage_style = "NORMAL"
        scene_approved = False
        
        if typ in ["PEXELS", "PIXABAY"]:
            sources_to_try = [typ, "PIXABAY" if typ == "PEXELS" else "PEXELS", typ]
            current_q = original_q
            for current_source in sources_to_try:
                if scene_approved: break
                for attempt in range(3):
                    c_media = pfx.with_suffix(".mp4")
                    is_vid = fetcher.fetch_media(current_source, current_q, c_media, attempt)
                    if not is_vid or not c_media.exists(): continue
                    
                    eval_res = director.evaluate_scene_flash(c_media, txt)
                    if eval_res.get("decision") == "ACCEPT":
                        scene_approved = True
                        montage_style = eval_res.get("montage", "NORMAL")
                        break
                    else:
                        log.warning(f"❌ المشهد مرفوض. الاقتراح الجديد: {eval_res.get('new_query')}")
                        current_q = eval_res.get("new_query", current_q + " mysterious")
                        c_media.unlink()
        else:
            current_q = original_q
            attempt = 0
            while not scene_approved and attempt < 20:
                c_media = pfx.with_suffix(".jpg")
                is_vid = False
                has_media = fetcher.fetch_media("WIKIPEDIA", current_q, c_media, attempt)
                if has_media and c_media.exists():
                    eval_res = director.evaluate_scene_flash(c_media, txt)
                    if eval_res.get("decision") == "ACCEPT":
                        log.info(f"✅ ويكيبيديا: تم اعتماد الدليل ({current_q})")
                        scene_approved = True
                        montage_style = eval_res.get("montage", "ZOOM_IN")
                    else:
                        current_q = eval_res.get("new_query", current_q)
                        c_media.unlink()
                else: current_q += " evidence"
                attempt += 1

        if not scene_approved:
            c_media = pfx.with_suffix(".jpg"); is_vid = False
            canvas = Image.new("RGB", (1920, 1080), (20, 22, 25)); ImageDraw.Draw(canvas).text((960, 540), "CLASSIFIED", fill=(180, 50, 50), anchor="mm"); canvas.save(c_media, "JPEG")

        render_scene(c_media, is_vid, c_mp3, c_mp4, dur, montage_style)
        if c_mp4.exists(): clips.append(c_mp4)

    # المرحلة 1: دمج الفيديو وتصديره للسحابة (لحفظ النسخة مهما حدث لاحقاً)
    if clips:
        txt_list = CONFIG.paths.base / "video_list.txt"
        txt_list.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in clips), encoding="utf-8")
        final_vid = CONFIG.paths.base / f"MasterDoc_{int(time.time())}.mp4"
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt_list), "-c", "copy", str(final_vid)], stdout=subprocess.DEVNULL)
        log.info("🎬 تم تصدير الفيلم محلياً. جاري الحفظ السحابي...")
        upload_drive(final_vid)
        upload_youtube(final_vid)

    # المرحلة 2: دمج الصوت والنقد الذاتي (آمن الآن للقيام بإعادة التشغيل إذا لزم الأمر)
    master_audio = CONFIG.paths.base / "master_audio.wav"
    if final_audio_segments:
        txt_list = CONFIG.paths.base / "audio_list.txt"
        txt_list.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in final_audio_segments), encoding="utf-8")
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt_list), "-c", "copy", str(master_audio)], stdout=subprocess.DEVNULL)
        
        # بعد أن تم حفظ الفيديو، يمكن للمراجع أن يتخذ قراره بتعديل الكود أو الموافقة
        director.self_critique_and_recode(master_audio)

if __name__ == "__main__": main()
