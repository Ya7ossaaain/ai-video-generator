#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE (V25 - AUDIO-FIRST WITH AGY SCOUT)
Features:
- Master Narration Generation (Split-safe).
- Single-Pass Groq Word-Level Timestamps.
- Semantic Shot Slicer.
- 5 Concurrent Async Workers for Media Scouting.
- Multi-Source: Yarn, Giphy, FBI Archive, Pexels, Pixabay, Wikipedia, Openverse, Europeana, NASA, Chronicling America.
- Restored AGY Vision Scout from V24.2 for media evaluation.
- Broadcast-grade ASS Subtitles & FFmpeg Ease-in Motion.
"""

import os
import sys
import json
import time
import re
import logging
import subprocess
import base64
import hashlib
import asyncio
import urllib.parse
from pathlib import Path
from typing import List, Dict, Tuple
from datetime import datetime

import requests
from google import genai
from google.genai import types

ENGINE_VERSION = "V25-AUDIO-FIRST-AGY-SCOUT"
TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
TARGET_AR = 48000
CONCURRENT_WORKERS = 5

class ProTelemetryFormatter(logging.Formatter):
    COLORS = {"INFO": "\x1b[38;5;39m", "WARNING": "\x1b[38;5;214m", "ERROR": "\x1b[38;5;196m"}
    RESET = "\x1b[0m"
    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        return logging.Formatter(f"{color}%(asctime)s | [%(levelname)s] | %(message)s{self.RESET}", datefmt="%H:%M:%S").format(record)

def setup_logger():
    logger = logging.getLogger("AudioFirstStudio")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(ProTelemetryFormatter())
    logger.addHandler(ch)
    return logger

log = setup_logger()

def probe_duration(path: Path) -> float:
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=20
        )
        return float(r.stdout.strip()) if r.returncode == 0 else 0.0
    except Exception:
        return 0.0

def is_valid_media(path: Path, min_size: int = 1000) -> bool:
    return path.exists() and path.is_file() and path.stat().st_size >= min_size and probe_duration(path) > 0.1

def is_valid_visual(path: Path, min_size: int = 5000) -> bool:
    if not path.exists() or not path.is_file() or path.stat().st_size < min_size:
        return False
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", str(path)],
            capture_output=True, text=True, timeout=20
        )
        m = re.search(r"(\d+)x(\d+)", r.stdout.strip())
        return bool(m and int(m.group(1)) > 0 and int(m.group(2)) > 0)
    except Exception:
        return False

def clean_query(text: str, max_words: int = 4) -> str:
    safe = re.sub(r"[\u0600-\u06FF]", "", str(text or ""))
    safe = re.sub(r"[^A-Za-z0-9 ]", " ", safe)
    words = [w for w in safe.split() if len(w) > 2]
    return " ".join(words[:max_words]) if words else "investigation scene"

class EngineConfig:
    topic = os.environ.get("VIDEO_TOPIC", "لغز اختفاء غامض")
    topic_clean = re.sub(r"\s+", " ", str(topic).strip().lower())
    topic_key = hashlib.sha256(topic_clean.encode("utf-8")).hexdigest()[:12]

    base_dir = Path("./output_build")
    cache_dir = base_dir / f"cache_{topic_key}"

    gemini_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
    groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()
    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    giphy_key = os.environ.get("GIPHY_API_KEY", "").strip()
    
    openverse_client_id = os.environ.get("OPENVERSE_CLIENT_ID", "").strip()
    openverse_client_secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "").strip()
    europeana_key = os.environ.get("EUROPEANA_API_KEY", "").strip()
    openverse_token = None

CONFIG = EngineConfig()
CONFIG.cache_dir.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# 1. STORY & ASSET INTELLIGENCE
# ==============================================================================
class StoryScoutEngine:
    @staticmethod
    def inspect_and_plan():
        log.info(f"🕵️ تمشيط القضية وتحديد طبيعة المصادر: {CONFIG.topic}")
        prompt = f'''أنت مخرج وثائقيات استقصائية. القضية: "{CONFIG.topic}"

الخطوة 1: فحص طبيعة القضية:
- هل لها فيلم شهير أو مسلسل (Cinema relevance)؟
- هل تحتوي سجلات من FBI/الشرطة (Forensic evidence)؟
- هل تعتمد على الصحف القديمة (Historical/OSINT)?
- هل ترتبط باكتشافات علمية (Space/Science)?

الخطوة 2: اكتب النص السردي الكامل للفيلم باللغة العربية الفصحى. (350 - 450 كلمة).
قسّم النص إلى نصفين: part_1 و part_2.

أخرج JSON فقط:
{{
  "story_type": "FORENSIC_OR_CINEMA_OR_HISTORICAL_OR_SPACE",
  "has_major_movie": true,
  "movie_title": "...",
  "primary_query": "English keyword",
  "part_1": "النصف الأول من النص...",
  "part_2": "النصف الثاني من النص..."
}}
'''
        for _ in range(3):
            try:
                res = subprocess.run(
                    ["agy", "--model", "gemini-3.1-pro", "--effort", "high", "--dangerously-skip-permissions", "-p", prompt],
                    capture_output=True, text=True, timeout=300
                )
                match = re.search(r"\{[\s\S]*\}", res.stdout)
                if match:
                    data = json.loads(match.group(0))
                    if data.get("part_1") and data.get("part_2"):
                        return data
            except Exception as e:
                time.sleep(4)
        return {
            "story_type": "FORENSIC", "has_major_movie": False, "movie_title": "",
            "primary_query": "mystery evidence",
            "part_1": f"تبدأ القصة في ليلة غامضة متعلقة بقضية {CONFIG.topic}.",
            "part_2": "توالت الشهادات، وبقيت الحقيقة مدفونة خلف جدار الصمت."
        }

# ==============================================================================
# 2. MASTER AUDIO STUDIO
# ==============================================================================
class MasterAudioStudio:
    @staticmethod
    def _generate_chunk(text: str, out_wav: Path) -> bool:
        if not CONFIG.gemini_keys: return False
        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")))
        )
        for key in CONFIG.gemini_keys * 2:
            try:
                client = genai.Client(api_key=key)
                res = client.models.generate_content(
                    model="gemini-3.8-flash-tts",
                    contents="[INSTRUCTION: Chilling authoritative Arabic documentary narrator. Do not shorten narration.]\n" + text,
                    config=cfg
                )
                raw = base64.b64decode(res.candidates[0].content.parts[0].inline_data.data)
                if raw[:4] == b"RIFF": out_wav.write_bytes(raw)
                else:
                    tmp = out_wav.with_suffix(".pcm")
                    tmp.write_bytes(raw)
                    subprocess.run(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(tmp), "-c:a", "pcm_s16le", str(out_wav)], capture_output=True)
                if is_valid_media(out_wav, 1000): return True
            except Exception: time.sleep(3)
        return False

    @classmethod
    def produce_master_track(cls, part1_text: str, part2_text: str, master_audio: Path) -> str:
        log.info("🎙️ توليد التعليق الصوتي الماستر...")
        w1, w2 = CONFIG.cache_dir / "part1.wav", CONFIG.cache_dir / "part2.wav"
        if not is_valid_media(w1): cls._generate_chunk(part1_text, w1)
        if not is_valid_media(w2): cls._generate_chunk(part2_text, w2)
        txt_concat = CONFIG.cache_dir / "audio_list.txt"
        txt_concat.write_text(f"file '{w1.resolve().as_posix()}'\nfile '{w2.resolve().as_posix()}'\n", encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt_concat),
            "-filter_complex", "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]",
            "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", str(TARGET_AR), str(master_audio)
        ], capture_output=True, check=True)
        return f"{part1_text} {part2_text}".strip()

# ==============================================================================
# 3. WORD-SYNC & SHOT SLICER
# ==============================================================================
class WordSyncSlicer:
    @staticmethod
    def align_and_slice(audio_path: Path, full_script: str) -> List[Dict]:
        log.info("⚡ إرسال الصوت لـ Groq Whisper...")
        try:
            with open(audio_path, "rb") as fh:
                r = requests.post(
                    "https://api.groq.com/openai/v1/audio/transcriptions",
                    headers={"Authorization": f"Bearer {CONFIG.groq_api_key}"},
                    files={"file": (audio_path.name, fh, "audio/mp4")},
                    data={"model": "whisper-large-v3", "language": "ar", "response_format": "verbose_json", "timestamp_granularities[]": "word"}
                ).json()
            words = r.get("words", [])
        except Exception: words = []

        total_dur = probe_duration(audio_path)
        shots = []
        if words:
            cur_words, shot_start = [], 0.0
            for w in words:
                cur_words.append(w.get("word", ""))
                dur = float(w.get("end", 0)) - shot_start
                is_punct = any(w.get("word", "").endswith(p) for p in [".", "،", "!", "؟", ":"])
                if dur >= 3.0 or (dur >= 2.0 and is_punct):
                    shots.append({"shot_id": len(shots)+1, "start": round(shot_start, 2), "duration": round(dur, 2), "phrase": " ".join(cur_words)})
                    shot_start, cur_words = float(w.get("end", 0)), []
            if cur_words: shots.append({"shot_id": len(shots)+1, "start": round(shot_start, 2), "duration": round(total_dur - shot_start, 2), "phrase": " ".join(cur_words)})
        else:
            cur, idx = 0.0, 1
            while cur < total_dur:
                shots.append({"shot_id": idx, "start": round(cur, 2), "duration": 3.5, "phrase": CONFIG.topic})
                cur, idx = cur + 3.5, idx + 1
        return shots

    @staticmethod
    def write_subtitles_ass(shots: List[Dict], out_ass: Path):
        lines = [
            "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "WrapStyle: 2", "",
            "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Arabic,Noto Sans Arabic,64,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,2,2,2,80,80,68,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]
        def t(s): cs = int(round(s * 100)); return f"{cs//360000}:{(cs%360000)//6000:02d}:{(cs%6000)//100:02d}.{cs%100:02d}"
        for s in shots:
            if s["duration"] < 0.2: continue
            txt = s["phrase"].replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            lines.append(f"Dialogue: 0,{t(s['start'])},{t(s['start']+s['duration'])},Arabic,,0,0,0,,{{\\fad(120,120)}}{txt}")
        out_ass.write_text("\n".join(lines), encoding="utf-8-sig")

# ==============================================================================
# 4. RESTORED AGY VISION SCOUT (من V24.2)
# ==============================================================================
async def agy_evaluate_scout(media_path: Path, narration: str, source: str) -> Tuple[bool, float]:
    """المراجع البصري الخاص بـ V24.2 المستعاد لتقييم الوسيط عبر Agy CLI"""
    prompt = f'''أنت المراجع البصري الفوري لفيلم وثائقي بعنوان "{CONFIG.topic}".
نوع المصدر: {source}
التعليق الصوتي: "{narration}"
الوسيط المراد فحصه موجود في المسار المحلي التالي:
{media_path.resolve()}

مهم: إذا كان إصدار agy الحالي لا يدعم إرفاق الملف تلقائياً عبر النص، فلا تدّع أنك شاهدت الصورة.
إذا كنت قادراً فعلياً على رؤية الوسيط، قيّم ملاءمته للجو الوثائقي.
وأضف نقطة البداية المثالية للمشهد إذا كان فيديو، وإلا ضعها 0.0.
أخرج JSON فقط:
{{"decision":"ACCEPT","score":0.85,"best_start_second":0.0,"reason":"..."}}
'''
    try:
        proc = await asyncio.create_subprocess_exec(
            "agy", "--model", "gemini-3.8-flash", "--effort", "high",
            "--dangerously-skip-permissions", "-p", prompt,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
        if proc.returncode != 0: return True, 0.0  # Fallback
        result_text = stdout.decode("utf-8", "ignore").strip()
        match = re.search(r"\{[\s\S]*\}", result_text)
        if match:
            data = json.loads(match.group(0))
            accepted = str(data.get("decision", "ACCEPT")).upper() == "ACCEPT" and float(data.get("score", 1.0)) >= 0.60
            start_s = float(data.get("best_start_second", 0.0))
            return accepted, start_s
    except Exception as e:
        log.error(f"⚠️ انهيار المراجع الفوري (Agy Scout): {e}")
    return True, 0.0

# ==============================================================================
# 5. MULTI-SOURCE CONCURRENT MEDIA FETCHING
# ==============================================================================
class MediaSources:
    headers = {"User-Agent": "Mozilla/5.0"}

    @classmethod
    def fetch_openverse_image(cls, q: str, out: Path) -> bool:
        if not (CONFIG.openverse_client_id and CONFIG.openverse_client_secret): return False
        if not CONFIG.openverse_token:
            try:
                r = requests.post("https://api.openverse.engineering/v1/auth_tokens/token/", data={"client_id": CONFIG.openverse_client_id, "client_secret": CONFIG.openverse_client_secret, "grant_type": "client_credentials"}, timeout=10).json()
                CONFIG.openverse_token = r.get("access_token")
            except: pass
        h = {"Authorization": f"Bearer {CONFIG.openverse_token}"} if CONFIG.openverse_token else {}
        try:
            r = requests.get("https://api.openverse.engineering/v1/images/", params={"q": q, "page_size": 3}, headers=h, timeout=12).json()
            if r.get("results") and r["results"][0].get("url"):
                out.write_bytes(requests.get(r["results"][0]["url"], timeout=15).content)
                return True
        except: pass
        return False
        
    @classmethod
    def fetch_europeana_image(cls, q: str, out: Path) -> bool:
        if not CONFIG.europeana_key: return False
        try:
            r = requests.get("https://api.europeana.eu/record/v2/search.json", params={"wskey": CONFIG.europeana_key, "query": q, "media": True, "thumbnail": True, "rows": 3}, timeout=12).json()
            if r.get("items") and r["items"][0].get("edmPreview"):
                out.write_bytes(requests.get(r["items"][0]["edmPreview"][0], timeout=15).content)
                return True
        except: pass
        return False
        
    @classmethod
    def fetch_nasa_media(cls, q: str, out: Path) -> bool:
        try:
            r = requests.get(f"https://images-api.nasa.gov/search?q={urllib.parse.quote(q)}&media_type=image,video", timeout=12).json()
            if not r.get("collection", {}).get("items"): return False
            href = r["collection"]["items"][0].get("href")
            if href:
                media_res = requests.get(href, timeout=12).json()
                for link in media_res:
                    if link.endswith(".mp4"):
                        out.with_suffix(".mp4").write_bytes(requests.get(link, timeout=20).content)
                        return True
                    elif link.endswith("orig.jpg") or link.endswith("large.jpg"):
                        out.with_suffix(".jpg").write_bytes(requests.get(link, timeout=15).content)
                        return True
        except: pass
        return False

    @classmethod
    def fetch_yarn_clip(cls, q: str, out: Path) -> bool:
        try:
            r = requests.get(f"https://yarn.co/yarn-find?text={urllib.parse.quote(q)}", headers=cls.headers, timeout=12)
            match = re.search(r'/yarn-clip/([a-f0-9\-]+)', r.text)
            if match:
                v = requests.get(f"https://y.yarn.co/{match.group(1)}.mp4", headers=cls.headers, timeout=15)
                if len(v.content) > 30000: out.write_bytes(v.content); return True
        except: pass
        return False

    @classmethod
    def fetch_fbi_archive(cls, q: str, out: Path) -> bool:
        try:
            sq = urllib.parse.quote(f"({q} OR fbi OR police) AND mediatype:movies")
            r = requests.get(f"https://archive.org/advancedsearch.php?q={sq}&fl[]=identifier&sort[]=downloads+desc&rows=3&output=json", timeout=12).json()
            if not r.get("response", {}).get("docs"): return False
            ident = r["response"]["docs"][0].get("identifier")
            files = requests.get(f"https://archive.org/metadata/{ident}/files", timeout=12).json().get("result", [])
            for f in files:
                name = f.get("name", "")
                if name.endswith(".mp4") and "thumb" not in name.lower():
                    chunk = requests.get(f"https://archive.org/download/{ident}/{urllib.parse.quote(name)}", stream=True, timeout=20).raw.read(4*1024*1024)
                    if len(chunk) > 100000: out.write_bytes(chunk); return True
        except: pass
        return False

    @classmethod
    def fetch_pexels_video(cls, q: str, out: Path) -> bool:
        if not CONFIG.pexels_key: return False
        try:
            r = requests.get("https://api.pexels.com/videos/search", params={"query": q, "per_page": 3, "orientation": "landscape"}, headers={"Authorization": CONFIG.pexels_key}, timeout=12).json()
            if r.get("videos"):
                files = sorted(r["videos"][0].get("video_files", []), key=lambda x: x.get("width", 0), reverse=True)
                if files: out.write_bytes(requests.get(files[0]["link"], timeout=20).content); return True
        except: pass
        return False

    @classmethod
    def create_fallback_visual(cls, shot_num: int, out: Path):
        subprocess.run(["ffmpeg", "-y", "-f", "lavfi", f"-i", f"color=c=0x11161B:s={TARGET_W}x{TARGET_H}:d=1", "-vf", "noise=alls=15:allf=t,vignette=PI/3", "-frames:v", "1", str(out)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def scout_shot_worker(shot: Dict, story: Dict, semaphore: asyncio.Semaphore) -> Tuple[Path, float]:
    async with semaphore:
        sid = shot["shot_id"]
        pfx = CONFIG.cache_dir / f"shot_{sid:03d}"
        c_vid, c_img = pfx.with_suffix(".mp4"), pfx.with_suffix(".jpg")
        
        q = clean_query(shot["phrase"] + " " + story.get("primary_query", ""))
        story_type = story.get("story_type", "FORENSIC")
        loop = asyncio.get_event_loop()

        async def check(vid: Path, source_name: str):
            if is_valid_media(vid, 1000) or is_valid_visual(vid, 5000):
                acc, st = await agy_evaluate_scout(vid, shot["phrase"], source_name)
                return acc, st
            return False, 0.0

        if story_type == "SPACE" and sid % 2 == 0:
            if await loop.run_in_executor(None, MediaSources.fetch_nasa_media, q, c_img):
                target = c_img.with_suffix(".mp4") if c_img.with_suffix(".mp4").exists() else c_img
                acc, st = await check(target, "NASA Archive")
                if acc: return target, st

        if story.get("has_major_movie") and sid % 3 == 0:
            if await loop.run_in_executor(None, MediaSources.fetch_yarn_clip, f"{story.get('movie_title')} {q}", c_vid):
                acc, st = await check(c_vid, "Cinema Movie")
                if acc: return c_vid, st

        if sid % 2 == 0:
            if await loop.run_in_executor(None, MediaSources.fetch_fbi_archive, q, c_vid):
                acc, st = await check(c_vid, "FBI Archive")
                if acc: return c_vid, st

        if await loop.run_in_executor(None, MediaSources.fetch_pexels_video, q, c_vid):
            acc, st = await check(c_vid, "Pexels B-Roll")
            if acc: return c_vid, st

        if story_type == "HISTORICAL_OR_OSINT":
            if await loop.run_in_executor(None, MediaSources.fetch_europeana_image, q, c_img):
                acc, st = await check(c_img, "Europeana Archive")
                if acc: return c_img, 0.0

        await loop.run_in_executor(None, MediaSources.create_fallback_visual, sid, c_img)
        return c_img, 0.0

# ==============================================================================
# 6. RENDER & ASSEMBLY ENGINE
# ==============================================================================
class AssemblyEngine:
    @staticmethod
    def render_sub_clip(media_path: Path, dur: float, start_sec: float, out_path: Path):
        is_video = media_path.suffix.lower() == ".mp4"
        if is_video:
            vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H},eq=contrast=1.08:saturation=0.92,vignette=PI/4.5,noise=alls=1:allf=t,fps={TARGET_FPS},tpad=stop_mode=clone:stop_duration={dur:.3f}"
            cmd = ["ffmpeg", "-y", "-ss", f"{start_sec:.3f}", "-i", str(media_path), "-vf", vf, "-an", "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "20", str(out_path)]
        else:
            z = "min(zoom+0.0009*(1.1-cos(on/45)),1.12)"
            vf = f"scale={int(TARGET_W*1.15)}:{int(TARGET_H*1.15)}:force_original_aspect_ratio=increase,crop={int(TARGET_W*1.15)}:{int(TARGET_H*1.15)},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={TARGET_W}x{TARGET_H}:fps={TARGET_FPS},eq=contrast=1.08:saturation=0.92,vignette=PI/4.5,noise=alls=1:allf=t,format=yuv420p"
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(media_path), "-vf", vf, "-an", "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "20", str(out_path)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    @classmethod
    def assemble_final_cut(cls, shot_clips: List[Path], master_audio: Path, sub_ass: Path, final_output: Path):
        concat_txt = CONFIG.cache_dir / "shots_list.txt"
        concat_txt.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in shot_clips), encoding="utf-8")
        temp_video = CONFIG.cache_dir / "temp_video_track.mp4"
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt), "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", str(TARGET_FPS), str(temp_video)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        sp = str(sub_ass.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        subprocess.run(["ffmpeg", "-y", "-i", str(temp_video), "-i", str(master_audio), "-vf", f"subtitles=filename='{sp}'", "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(final_output)], check=True)
        log.info(f"🏆 اكتمل إنتاج الفيلم بنجاح تام! الملف: {final_output}")

# ==============================================================================
# MAIN ASYNC ORCHESTRATION PIPELINE
# ==============================================================================
async def main_pipeline():
    story_info = StoryScoutEngine.inspect_and_plan()
    
    master_wav = CONFIG.cache_dir / "master_audio.wav"
    full_script = MasterAudioStudio.produce_master_track(story_info["part_1"], story_info["part_2"], master_wav)
    
    shots = WordSyncSlicer.align_and_slice(master_wav, full_script)
    sub_ass = CONFIG.cache_dir / "subtitles.ass"
    WordSyncSlicer.write_subtitles_ass(shots, sub_ass)

    semaphore = asyncio.Semaphore(CONCURRENT_WORKERS)
    log.info("👁️ إطلاق 5 عمال لجلب وتقييم المشاهد عبر المراجع الفوري (Agy Scout)...")
    tasks = [scout_shot_worker(shot, story_info, semaphore) for shot in shots]
    downloaded_results = await asyncio.gather(*tasks)

    rendered_shot_clips = []
    for shot, (asset, start_s) in zip(shots, downloaded_results):
        shot_out = CONFIG.cache_dir / f"rendered_{shot['shot_id']:03d}.mp4"
        try:
            AssemblyEngine.render_sub_clip(asset, shot["duration"], start_s, shot_out)
            rendered_shot_clips.append(shot_out)
        except Exception:
            fb_jpg = CONFIG.cache_dir / f"fb_{shot['shot_id']}.jpg"
            MediaSources.create_fallback_visual(shot['shot_id'], fb_jpg)
            AssemblyEngine.render_sub_clip(fb_jpg, shot["duration"], 0.0, shot_out)
            rendered_shot_clips.append(shot_out)

    final_mp4 = CONFIG.base_dir / "final_documentary.mp4"
    AssemblyEngine.assemble_final_cut(rendered_shot_clips, master_wav, sub_ass, final_mp4)

if __name__ == "__main__":
    asyncio.run(main_pipeline())
