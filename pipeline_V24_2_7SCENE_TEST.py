#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
HYBRID V26 - ELITE VFX EDITION (OpenCV + ImageMagick + Rembg + FFmpeg)
"""

import os
import sys
import json
import time
import re
import difflib
import unicodedata
import logging
import subprocess
import base64
import hashlib
import asyncio
import urllib.parse
import shutil

from pathlib import Path
from datetime import datetime
from typing import List, Dict

import requests
from PIL import Image, ImageFilter
import numpy as np
import cv2

try:
    from rembg import remove as remove_bg
except ImportError:
    remove_bg = None

from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ENGINE_VERSION = "V26-ELITE-VFX-STUDIO"
TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
TARGET_AR = 48000
TEST_SCENE_COUNT = 7

class ProTelemetryFormatter(logging.Formatter):
    COLORS = {"INFO": "\x1b[38;5;39m", "WARNING": "\x1b[38;5;214m", "ERROR": "\x1b[38;5;196m"}
    RESET = "\x1b[0m"
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        return logging.Formatter(f"{color}%(asctime)s | [%(levelname)s] | %(message)s{self.RESET}", datefmt="%H:%M:%S").format(record)

def setup_logger():
    logger = logging.getLogger("StudioMaster")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(ProTelemetryFormatter())
    logger.addHandler(ch)
    return logger

log = setup_logger()

def probe_duration(path):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)], capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip()) if r.returncode == 0 else 0.0
    except Exception: return 0.0

def is_valid_media(path, minimum=1000):
    return path.exists() and path.is_file() and path.stat().st_size >= minimum and probe_duration(path) > 0.1

def is_valid_visual(path, minimum=10000):
    if not path.exists() or not path.is_file() or path.stat().st_size < minimum: return False
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)], capture_output=True, text=True, timeout=30)
        m = re.search(r"(\d+)x(\d+)", r.stdout.strip())
        return bool(m and int(m.group(1)) > 0 and int(m.group(2)) > 0)
    except Exception: return False

def enforce_english_query(query, max_chars=90):
    safe_q = re.sub(r"[\u0600-\u06FF]", "", str(query or ""))
    safe_q = re.sub(r"[^A-Za-z0-9,._' -]", " ", safe_q)
    safe_q = " ".join(dict.fromkeys(safe_q.split()))
    return safe_q[:max_chars].rsplit(" ", 1)[0].strip() if len(safe_q) > max_chars else (safe_q if len(safe_q) >= 2 else "investigation evidence")

class HybridConfig:
    topic = os.environ.get("VIDEO_TOPIC", "لغز الجريمة الغامضة")
    _topic_normalized = re.sub(r"\s+", " ", str(topic).strip().lower())
    topic_key = hashlib.sha256(_topic_normalized.encode("utf-8")).hexdigest()[:16]

    paths = type("Paths", (), {
        "base": Path("./output_build"),
        "cache": Path(f"./output_build/cache/topic_{topic_key}"),
        "manifest": Path(f"./output_build/manifests/manifest_{topic_key}.json")
    })()
    gemini_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
    pexels = os.environ.get("PEXELS_API_KEY", "")
    pixabay = os.environ.get("PIXABAY_API_KEY", "")
    groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()

CONFIG = HybridConfig()
CONFIG.paths.base.mkdir(parents=True, exist_ok=True)
CONFIG.paths.cache.mkdir(parents=True, exist_ok=True)
CONFIG.paths.manifest.parent.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# ELITE VFX COMPOSITOR (محرك المؤثرات البصرية للصور الثابتة)
# ==============================================================================
class AdvancedVFXStudio:
    @staticmethod
    def create_cyber_scan(img_path: Path, out_path: Path) -> bool:
        """يستخدم OpenCV لتحويل الصورة إلى ماسح استخباراتي نيون (Wireframe Edge Detection)"""
        try:
            img = cv2.imread(str(img_path))
            if img is None: return False
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            # استخراج الحواف
            edges = cv2.Canny(gray, 70, 150)
            
            # صناعة التوهج النيون (لون سيان استخباراتي)
            neon_color = (255, 255, 0) # Cyan in BGR
            neon_img = np.zeros_like(img)
            neon_img[edges == 255] = neon_color
            
            # دمج التوهج (Bloom effect)
            blur = cv2.GaussianBlur(neon_img, (9, 9), 0)
            final_hologram = cv2.addWeighted(neon_img, 1.5, blur, 2.0, 0)
            
            # دمج الحواف المضيئة مع الصورة الأصلية بعد تعتيمها
            dark_bg = cv2.convertScaleAbs(img, alpha=0.3, beta=-30)
            composite = cv2.addWeighted(dark_bg, 0.8, final_hologram, 1.0, 0)
            
            cv2.imwrite(str(out_path), composite)
            log.info(f"🧬 OpenCV Cyber Scan Created: {out_path.name}")
            return True
        except Exception as e:
            log.warning(f"⚠️ فشل تأثير OpenCV: {e}")
            return False

    @staticmethod
    def create_grunge_archive(img_path: Path, out_path: Path) -> bool:
        """يستخدم ImageMagick لصناعة ملمس حبر الجرائد القديمة (Halftone Dithering)"""
        try:
            # نستدعي أمر convert الخاص بـ ImageMagick
            cmd = [
                "convert", str(img_path),
                "-colorspace", "gray",
                "-contrast-stretch", "2%x98%",
                "-ordered-dither", "h8x8a",
                str(out_path)
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            log.info(f"📰 ImageMagick Grunge Archive Created: {out_path.name}")
            return True
        except Exception as e:
            log.warning(f"⚠️ فشل تأثير ImageMagick: {e}")
            return False

    @staticmethod
    def create_paper_cutout(img_path: Path, out_path: Path) -> bool:
        """يستخدم Rembg و Pillow لصناعة القصاصات الورقية"""
        try:
            inp = Image.open(img_path).convert("RGBA")
            cutout = remove_bg(inp) if remove_bg else inp
            alpha = cutout.split()[-1]
            stroke_mask = alpha.filter(ImageFilter.MaxFilter(17)).filter(ImageFilter.SMOOTH)
            stroke_img = Image.new("RGBA", cutout.size, (245, 245, 240, 255))
            paper_sticker = Image.composite(stroke_img, Image.new("RGBA", cutout.size, (0, 0, 0, 0)), stroke_mask)
            paper_sticker.paste(cutout, (0, 0), cutout)
            
            canvas = Image.new("RGBA", (TARGET_W, TARGET_H), (20, 22, 24, 255))
            noise = np.random.randint(25, 38, (TARGET_H, TARGET_W, 3), dtype=np.uint8)
            canvas = Image.blend(canvas, Image.fromarray(noise).convert("RGBA"), 0.4)

            sticker_ratio = min((TARGET_W * 0.7) / paper_sticker.width, (TARGET_H * 0.75) / paper_sticker.height)
            new_size = (int(paper_sticker.width * sticker_ratio), int(paper_sticker.height * sticker_ratio))
            paper_sticker = paper_sticker.resize(new_size, Image.Resampling.LANCZOS).rotate(3.5, expand=True)

            pos_x, pos_y = (TARGET_W - paper_sticker.width) // 2, (TARGET_H - paper_sticker.height) // 2
            canvas.paste(paper_sticker, (pos_x, pos_y), paper_sticker)
            canvas.convert("RGB").save(out_path, "JPEG", quality=95)
            log.info(f"✂️ Rembg Paper Cutout Created: {out_path.name}")
            return True
        except Exception: return False


# ==============================================================================
# PRO DIRECTOR 
# ==============================================================================
class Hybrid_Director:
    def plan_documentary(self) -> List[Dict]:
        prompt = f'''أنت Showrunner ومخرج وثائقيات استقصائية.
القضية: "{CONFIG.topic}"
المطلوب 7 مشاهد تشكل قصة مشدودة.
اختر "visual_style" بدقة:
- "PAPER_COLLAGE": للوثائق والأدلة الجنائية (قص ورق ستوب موشن).
- "CYBER_SCAN": للأدلة التقنية والخطيرة (تحويل الصورة لمسح شبكي نيون ثلاثي الأبعاد).
- "GRUNGE_ARCHIVE": للصور التاريخية والمشتبه بهم (ملمس حبر جرائد قديمة ومرعب).
- "CINEMATIC_PARALLAX": للمشاهد الوثائقية العامة بحركة ناعمة.

لكل مشهد أخرج:
scene_num, media_type (PEXELS, PIXABAY, WIKIPEDIA, ARCHIVE), search_query (English), narration (Arabic 95-120 words), visual_style, camera_motion (slow_push, slow_pull, lateral_drift).
أخرج JSON فقط (مصفوفة Scenes).
'''
        for _ in range(3):
            try:
                res = subprocess.run(["agy", "--model", "gemini-3.1-pro", "--effort", "high", "--dangerously-skip-permissions", "-p", prompt], capture_output=True, text=True, timeout=360)
                match = re.search(r"\[[\s\S]*\]", res.stdout)
                if match:
                    scenes = json.loads(match.group(0))[:TEST_SCENE_COUNT]
                    CONFIG.paths.manifest.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding="utf-8")
                    return scenes
            except Exception: time.sleep(4)
        raise RuntimeError("فشل تخطيط السيناريو")

    def generate_voice(self, text, out_wav):
        if not CONFIG.gemini_keys: return False
        cfg = types.GenerateContentConfig(response_modalities=["AUDIO"], speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon"))))
        for key in CONFIG.gemini_keys * 3:
            try:
                res = genai.Client(api_key=key).models.generate_content(model="gemini-3.8-flash-tts", contents="[INSTRUCTION: Chilling authoritative Arabic documentary narrator. Do not shorten narration.]\n" + text, config=cfg)
                raw = base64.b64decode(res.candidates[0].content.parts[0].inline_data.data)
                if raw[:4] == b"RIFF": out_wav.write_bytes(raw)
                else:
                    tmp = out_wav.with_suffix(".pcm")
                    tmp.write_bytes(raw)
                    subprocess.run(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(tmp), "-c:a", "pcm_s16le", str(out_wav)], capture_output=True)
                    try: tmp.unlink()
                    except Exception: pass
                if is_valid_media(out_wav, 1000): return True
            except Exception: time.sleep(3)
        return False

# ==============================================================================
# RENDER ENGINE
# ==============================================================================
class Studio_Render_Engine:
    @staticmethod
    def render_scene(media, is_vid, aud, out, dur, style="CINEMATIC_PARALLAX", motion="slow_push", subtitle_ass=None):
        v_filters = []
        if is_vid: v_filters.append(f"setpts=PTS*1.08,scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H}")
        else:
            pre = f"scale={int(TARGET_W*1.15)}:{int(TARGET_H*1.15)}:force_original_aspect_ratio=increase,crop={int(TARGET_W*1.15)}:{int(TARGET_H*1.15)}"
            z = "min(zoom+0.001*(1.2-cos(on/40)),1.14)" if motion != "slow_pull" else "if(eq(on,0),1.14,max(zoom-0.0009*(1.2-cos(on/40)),1.0))"
            v_filters.append(f"{pre},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={TARGET_W}x{TARGET_H}:fps={TARGET_FPS}")

        if style == "PAPER_COLLAGE": v_filters.append("fps=12,fps=30,eq=contrast=1.18:saturation=0.88,noise=alls=2:allf=t")
        elif style == "CYBER_SCAN":
            v_filters.append("eq=contrast=1.2:saturation=1.2")
            v_filters.append("drawtext=text='● TARGET LOCK':x=80:y=80:fontsize=42:fontcolor=cyan:enable='lt(mod(t,1),0.6)'")
        elif style == "GRUNGE_ARCHIVE":
            v_filters.append("eq=contrast=1.4:saturation=0.1:gamma=0.8")
            v_filters.append("vignette=PI/3.5,noise=alls=10:allf=t")
        else: v_filters.append("boxblur=lr='max(12-t*24,0)':lp='max(12-t*24,0)',eq=contrast=1.08:saturation=0.92")

        if style not in ["GRUNGE_ARCHIVE"]: v_filters.append("vignette=PI/4.5,noise=alls=1:allf=t")
        if is_vid: v_filters.append(f"fps={TARGET_FPS},tpad=stop_mode=clone:stop_duration={max(0.0,dur):.3f}")
        else: v_filters.append("format=yuv420p")

        vf_str = ",".join(v_filters)
        
        if subtitle_ass and Path(subtitle_ass).exists():
            sp = str(Path(subtitle_ass).resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
            sub_filter = f"subtitles=filename='{sp}':force_style='FontName=Noto Sans Arabic,FontSize=64,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,Outline=2,Shadow=2,Alignment=2,MarginV=70'"
            vf_complex = f"[0:v]{vf_str}[base];[base]{sub_filter}[v]"
        else: vf_complex = f"[0:v]{vf_str}[v]"

        cmd = ["ffmpeg", "-y"] + ([] if is_vid else ["-loop", "1"]) + [
            "-i", str(media), "-i", str(aud), "-filter_complex", vf_complex, "-map", "[v]", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-r", str(TARGET_FPS), "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(TARGET_AR), "-ac", "2", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-t", f"{max(.5,dur):.3f}", "-movflags", "+faststart", str(out)
        ]
        subprocess.run(cmd, capture_output=True, check=True)

# Helper Functions
def fetch_media(source, q, out):
    q = enforce_english_query(q)
    try:
        if source == "PEXELS" and CONFIG.pexels:
            r = requests.get("https://api.pexels.com/videos/search", params={"query": q, "per_page": 5}, headers={"Authorization": CONFIG.pexels}).json()
            if r.get("videos"):
                out.write_bytes(requests.get(r["videos"][0]["video_files"][0]["link"], timeout=90).content)
                return True
        r = requests.get("https://en.wikipedia.org/w/api.php", params={"action":"query","generator":"search","gsrsearch":q,"gsrlimit":5,"prop":"pageimages","piprop":"thumbnail","pithumbsize":1920,"format":"json"}).json()
        if [p for p in r.get("query", {}).get("pages", {}).values() if p.get("thumbnail")]:
            out.write_bytes(requests.get([p for p in r.get("query", {}).get("pages", {}).values() if p.get("thumbnail")][0]["thumbnail"]["source"], timeout=60).content)
            return True
    except Exception: pass
    return False

def generate_subtitles(audio_path, out_ass):
    if not CONFIG.groq_api_key: return False
    try:
        with open(audio_path, "rb") as f:
            r = requests.post("https://api.groq.com/openai/v1/audio/transcriptions", headers={"Authorization": f"Bearer {CONFIG.groq_api_key}"}, files={"file": (audio_path.name, f, "audio/wav")}, data={"model": "whisper-large-v3", "language": "ar", "response_format": "verbose_json", "timestamp_granularities[]": "word"}).json()
        words = r.get("words", [])
        if not words: return False
        
        lines = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "", "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding", "Style: Arabic,Noto Sans Arabic,64,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,2,2,2,80,80,70,1", "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
        chunk = []
        for w in words:
            chunk.append(w)
            if len(chunk) >= 7 or (w.get("end",0) - chunk[0].get("start",0)) > 2.8:
                lines.append(f"Dialogue: 0,{chunk[0]['start']:.2f},{chunk[-1]['end']:.2f},Arabic,,0,0,0,,{{\\fad(150,150)}}{' '.join(x['word'] for x in chunk)}")
                chunk = []
        out_ass.write_text("\n".join(lines), encoding="utf-8-sig")
        return True
    except Exception: return False

def main():
    log.info(f"▶ تشغيل استوديو ELITE VFX {ENGINE_VERSION} | القضية: {CONFIG.topic}")
    script = Hybrid_Director().plan_documentary()
    clips = []
    
    for i, scene in enumerate(script):
        pfx = CONFIG.paths.cache / f"scene_{i:02d}"
        c_mp4, c_wav, c_ass, raw_media = pfx.with_suffix(".mp4"), pfx.with_suffix(".wav"), pfx.with_suffix(".ass"), pfx.with_name(pfx.name + "_raw.jpg")
        
        log.info(f"\n🎬 إنتاج المشهد {i+1}/{len(script)} | النمط: {scene.get('visual_style', 'CINEMATIC_PARALLAX')}")
        Hybrid_Director().generate_voice(scene["narration"], c_wav)
        dur = probe_duration(c_wav)
        sub_ok = generate_subtitles(c_wav, c_ass)
        fetch_media(scene.get("media_type", "WIKIPEDIA"), scene.get("search_query", "evidence"), raw_media)
        
        render_input, is_video, style = raw_media, raw_media.suffix.lower() == ".mp4", scene.get("visual_style", "CINEMATIC_PARALLAX")
        
        if not is_video and raw_media.exists():
            mod_img = pfx.with_name(pfx.name + "_vfx.jpg")
            if style == "CYBER_SCAN" and AdvancedVFXStudio.create_cyber_scan(raw_media, mod_img): render_input = mod_img
            elif style == "GRUNGE_ARCHIVE" and AdvancedVFXStudio.create_grunge_archive(raw_media, mod_img): render_input = mod_img
            elif style == "PAPER_COLLAGE" and AdvancedVFXStudio.create_paper_cutout(raw_media, mod_img): render_input = mod_img

        try:
            Studio_Render_Engine.render_scene(render_input, is_video, c_wav, c_mp4, dur, style=style, motion=scene.get("camera_motion", "slow_push"), subtitle_ass=c_ass if sub_ok else None)
            clips.append(c_mp4)
        except Exception as e: log.error(f"❌ خطأ رندر المشهد {i+1}: {e}")

    final_video = CONFIG.paths.base / "final_documentary.mp4"
    txt = CONFIG.paths.base / "list.txt"
    txt.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in clips), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", str(TARGET_FPS), "-c:a", "aac", "-b:a", "192k", "-ar", str(TARGET_AR), "-movflags", "+faststart", str(final_video)], check=True)
    log.info(f"🏆 اكتمل الفيلم! المدة: {probe_duration(final_video)/60:.2f} دقيقة | الملف: {final_video}")

if __name__ == "__main__": main()
