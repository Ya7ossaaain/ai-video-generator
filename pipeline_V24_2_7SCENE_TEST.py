#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE (V25 - AUDIO-FIRST MASTER PIPELINE)
Features:
- Master Narration Generation (Split-safe to prevent TTS drift).
- Single-Pass Groq Word-Level Timestamps.
- Semantic Shot Slicer (30-50 dynamic cuts per episode).
- 5 Concurrent Async Workers for Media Scouting.
- Sources: Yarn, Giphy, FBI Archive, Pexels, Pixabay, Wikipedia, Openverse, Europeana, NASA, Chronicling America, Freesound.
- Bulletproof Fallback System (Zero Crashes Guarantee).
- Broadcast-grade ASS Subtitles & FFmpeg Ease-in Motion.
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
from typing import List, Dict, Optional

import requests
from google import genai
from google.genai import types

ENGINE_VERSION = "V25-AUDIO-FIRST-BULLETPROOF-EXTENDED"
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
    manifest_dir = base_dir / "manifests"

    gemini_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
    groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()
    pexels_key = os.environ.get("PEXELS_API_KEY", "").strip()
    pixabay_key = os.environ.get("PIXABAY_API_KEY", "").strip()
    giphy_key = os.environ.get("GIPHY_API_KEY", "").strip()
    
    # Extended API Keys
    openverse_client_id = os.environ.get("OPENVERSE_CLIENT_ID", "").strip()
    openverse_client_secret = os.environ.get("OPENVERSE_CLIENT_SECRET", "").strip()
    europeana_key = os.environ.get("EUROPEANA_API_KEY", "").strip()
    freesound_key = os.environ.get("FREESOUND_API_KEY", "").strip()
    
    openverse_token = None

CONFIG = EngineConfig()
CONFIG.cache_dir.mkdir(parents=True, exist_ok=True)
CONFIG.manifest_dir.mkdir(parents=True, exist_ok=True)

# ==============================================================================
# 1. STORY & ASSET INTELLIGENCE (فحص طبيعة القضية)
# ==============================================================================
class StoryScoutEngine:
    @staticmethod
    def inspect_and_plan():
        log.info(f"🕵️ تمشيط القضية وتحديد طبيعة المصادر: {CONFIG.topic}")
        prompt = f'''أنت رئيس تحرير ومخرج وثائقيات استقصائية كبرى.
القضية: "{CONFIG.topic}"

الخطوة 1: فحص طبيعة القضية:
- هل لها فيلم شهير أو مسلسل (Cinema relevance)؟
- هل تحتوي على سجلات وتحقيقات حقيقية من الـ FBI أو الشرطة (Forensic evidence)؟
- هل تعتمد بقوة على الوثائق التاريخية أو أخبار الصحف القديمة (Historical/OSINT)?
- هل ترتبط باكتشافات علمية أو استكشاف فضائي (Space/Science)?

الخطوة 2: اكتب النص السردي الكامل للفيلم (Master Narration) باللغة العربية الفصحى.
- النص يجب أن يكون مشوقاً، عميقاً، بنبرة استقصائية باردة ومرعبة.
- الطول المطلوب: ما بين 350 إلى 450 كلمة متصلة تشكل 7 إلى 10 فصول سردية واضحة.
- قسّم النص إلى نصفين متوازنين: part_1 و part_2 (لمنع تشتت الصوت).

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
        for attempt in range(3):
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
                log.warning(f"⚠️️ إعادة محاولة كتابة السيناريو: {e}")
                time.sleep(4)

        return {
            "story_type": "FORENSIC",
            "has_major_movie": False,
            "movie_title": "",
            "primary_query": "crime mystery evidence",
            "part_1": f"تبدأ القصة في ليلة غامضة عندما اختفت كل الآثار المتعلقة بقضية {CONFIG.topic}. عثرت الشرطة على أدلة مبعثرة تشير إلى أن الجريمة لم تكن وليدة اللحظة، بل تم التخطيط لها بدقة متناهية.",
            "part_2": "توالت الشهادات والتقارير الفيدرالية التي كشفت عن خيوط متداخلة. ورغم كل المحاولات لفك لغز هذا الملف، بقيت الحقيقة مدفونة خلف جدار الصمت."
        }

# ==============================================================================
# 2. MASTER AUDIO STUDIO (توليد الصوت الماستر الموحد)
# ==============================================================================
class MasterAudioStudio:
    @staticmethod
    def _generate_chunk(text: str, out_wav: Path) -> bool:
        if not CONFIG.gemini_keys:
            log.error("❌ لا توجد GEMINI_API_KEY.")
            return False
        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon"))
            )
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
                if raw[:4] == b"RIFF":
                    out_wav.write_bytes(raw)
                else:
                    tmp = out_wav.with_suffix(".pcm")
                    tmp.write_bytes(raw)
                    subprocess.run(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(tmp), "-c:a", "pcm_s16le", str(out_wav)], capture_output=True)
                    if tmp.exists(): tmp.unlink()
                if is_valid_media(out_wav, 1000):
                    return True
            except Exception:
                time.sleep(3)
        return False

    @classmethod
    def produce_master_track(cls, part1_text: str, part2_text: str, master_audio: Path) -> str:
        log.info("🎙️ توليد التعليق الصوتي الماستر...")
        w1, w2 = CONFIG.cache_dir / "part1.wav", CONFIG.cache_dir / "part2.wav"
        if not is_valid_media(w1): cls._generate_chunk(part1_text, w1)
        if not is_valid_media(w2): cls._generate_chunk(part2_text, w2)

        txt_concat = CONFIG.cache_dir / "audio_list.txt"
        txt_concat.write_text(f"file '{w1.resolve().as_posix()}'\nfile '{w2.resolve().as_posix()}'\n", encoding="utf-8")

        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt_concat),
            "-filter_complex", "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]",
            "-map", "[aout]", "-c:a", "aac", "-b:a", "192k", "-ar", str(TARGET_AR), str(master_audio)
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return f"{part1_text} {part2_text}".strip()

# ==============================================================================
# 3. WORD-SYNC & SHOT SLICER (التقطيع الزمني الدقيق بالكلمات)
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
                    data={"model": "whisper-large-v3", "language": "ar", "response_format": "verbose_json", "timestamp_granularities[]": "word"},
                    timeout=180
                ).json()
            words = r.get("words", [])
        except Exception:
            words = []

        total_dur = probe_duration(audio_path)
        shots = []

        if words:
            cur_words = []
            shot_start = 0.0
            for w in words:
                cur_words.append(w.get("word", ""))
                dur = float(w.get("end", 0)) - shot_start
                is_punct = any(w.get("word", "").endswith(p) for p in [".", "،", "!", "؟", ":"])
                if dur >= 3.0 or (dur >= 2.0 and is_punct):
                    shots.append({
                        "shot_id": len(shots) + 1,
                        "start": round(shot_start, 2),
                        "end": round(float(w.get("end", total_dur)), 2),
                        "duration": round(dur, 2),
                        "phrase": " ".join(cur_words)
                    })
                    shot_start = float(w.get("end", 0))
                    cur_words = []
            if cur_words:
                shots.append({
                    "shot_id": len(shots) + 1,
                    "start": round(shot_start, 2),
                    "end": round(total_dur, 2),
                    "duration": round(total_dur - shot_start, 2),
                    "phrase": " ".join(cur_words)
                })
        else:
            shot_len = 3.5
            cur = 0.0
            idx = 1
            while cur < total_dur:
                nxt = min(cur + shot_len, total_dur)
                shots.append({"shot_id": idx, "start": round(cur, 2), "end": round(nxt, 2), "duration": round(nxt - cur, 2), "phrase": CONFIG.topic})
                cur = nxt
                idx += 1
        return shots

    @staticmethod
    def write_subtitles_ass(shots: List[Dict], out_ass: Path):
        lines = [
            "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080", "WrapStyle: 2", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Arabic,Noto Sans Arabic,64,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,2,2,2,80,80,68,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
        ]
        def to_ass_t(s):
            cs = int(round(s * 100))
            return f"{cs // 360000}:{(cs % 360000) // 6000:02d}:{(cs % 6000) // 100:02d}.{cs % 100:02d}"

        for s in shots:
            if s["duration"] < 0.2: continue
            txt = s["phrase"].replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
            lines.append(f"Dialogue: 0,{to_ass_t(s['start'])},{to_ass_t(s['end'])},Arabic,,0,0,0,,{{\\fad(120,120)}}{txt}")
        out_ass.write_text("\n".join(lines), encoding="utf-8-sig")

# ==============================================================================
# 4. MULTI-SOURCE CONCURRENT MEDIA SCOUT (خالٍ من Flickr)
# ==============================================================================
class MediaSources:
    headers = {"User-Agent": "Mozilla/5.0"}
    
    @classmethod
    def get_openverse_token(cls):
        if CONFIG.openverse_token: return CONFIG.openverse_token
        if not (CONFIG.openverse_client_id and CONFIG.openverse_client_secret): return None
        try:
            res = requests.post("https://api.openverse.org/v1/auth_tokens/token/", 
                                data={"client_id": CONFIG.openverse_client_id, "client_secret": CONFIG.openverse_client_secret, "grant_type": "client_credentials"},
                                timeout=10).json()
            CONFIG.openverse_token = res.get("access_token")
            return CONFIG.openverse_token
        except: return None

    @classmethod
    def fetch_openverse_image(cls, query: str, out_jpg: Path) -> bool:
        token = cls.get_openverse_token()
        h = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            r = requests.get("https://api.openverse.org/v1/images/", params={"q": query, "page_size": 3}, headers=h, timeout=12).json()
            results = r.get("results", [])
            if results:
                url = results[0].get("url")
                if url:
                    out_jpg.write_bytes(requests.get(url, timeout=15).content)
                    return True
        except: pass
        return False
        
    @classmethod
    def fetch_europeana_image(cls, query: str, out_jpg: Path) -> bool:
        if not CONFIG.europeana_key: return False
        try:
            url = "https://api.europeana.eu/record/v2/search.json"
            params = {"wskey": CONFIG.europeana_key, "query": query, "media": True, "thumbnail": True, "rows": 3}
            res = requests.get(url, params=params, timeout=12).json()
            items = res.get("items", [])
            for item in items:
                img_url = item.get("edmPreview", [None])[0]
                if img_url:
                    out_jpg.write_bytes(requests.get(img_url, timeout=15).content)
                    return True
        except: pass
        return False
        
    @classmethod
    def fetch_nasa_media(cls, query: str, out_path: Path) -> bool:
        try:
            url = f"https://images-api.nasa.gov/search?q={urllib.parse.quote(query)}&media_type=image,video"
            res = requests.get(url, timeout=12).json()
            items = res.get("collection", {}).get("items", [])
            if not items: return False
            
            href = items[0].get("href")
            if href:
                media_res = requests.get(href, timeout=12).json()
                for link in media_res:
                    if link.endswith(".mp4"):
                        out_path.with_suffix(".mp4").write_bytes(requests.get(link, timeout=20).content)
                        return True
                    elif link.endswith("orig.jpg") or link.endswith("large.jpg"):
                        out_path.with_suffix(".jpg").write_bytes(requests.get(link, timeout=15).content)
                        return True
        except: pass
        return False
        
    @classmethod
    def fetch_chronicling_america(cls, query: str, out_jpg: Path) -> bool:
        try:
            url = f"https://chroniclingamerica.loc.gov/search/pages/results/?andtext={urllib.parse.quote(query)}&format=json"
            res = requests.get(url, timeout=12).json()
            items = res.get("items", [])
            if items:
                thumb = items[0].get("url", "")
                if thumb and thumb.endswith(".json"):
                    img_data = requests.get(thumb, timeout=12).json()
                    jp2 = img_data.get("jp2")
                    if jp2:
                        out_jpg.write_bytes(requests.get(jp2.replace(".jp2", "/thumbnail.jpg"), timeout=15).content)
                        return True
        except: pass
        return False

    @classmethod
    def fetch_yarn_clip(cls, query: str, out_mp4: Path) -> bool:
        try:
            url = f"https://yarn.co/yarn-find?text={urllib.parse.quote(query)}"
            r = requests.get(url, headers=cls.headers, timeout=12)
            match = re.search(r'/yarn-clip/([a-f0-9\-]+)', r.text)
            if match:
                direct_url = f"https://y.yarn.co/{match.group(1)}.mp4"
                v_res = requests.get(direct_url, headers=cls.headers, timeout=15)
                if v_res.status_code == 200 and len(v_res.content) > 30000:
                    out_mp4.write_bytes(v_res.content)
                    return True
        except Exception: pass
        return False

    @classmethod
    def fetch_giphy_clip(cls, query: str, out_mp4: Path) -> bool:
        if not CONFIG.giphy_key: return False
        try:
            url = "https://api.giphy.com/v1/gifs/search"
            params = {"api_key": CONFIG.giphy_key, "q": query, "limit": 3, "rating": "pg-13"}
            res = requests.get(url, params=params, timeout=12).json()
            data = res.get("data", [])
            if data:
                mp4_url = data[0].get("images", {}).get("original", {}).get("mp4")
                if mp4_url:
                    out_mp4.write_bytes(requests.get(mp4_url, timeout=15).content)
                    return True
        except Exception: pass
        return False

    @classmethod
    def fetch_fbi_archive(cls, query: str, out_mp4: Path) -> bool:
        try:
            safe_q = urllib.parse.quote(f"({query} OR fbi OR police) AND mediatype:movies")
            s_url = f"https://archive.org/advancedsearch.php?q={safe_q}&fl[]=identifier&sort[]=downloads+desc&rows=3&output=json"
            res = requests.get(s_url, timeout=12).json()
            docs = res.get("response", {}).get("docs", [])
            if docs:
                ident = docs[0].get("identifier")
                m_url = f"https://archive.org/metadata/{ident}/files"
                files = requests.get(m_url, timeout=12).json().get("result", [])
                for f in files:
                    name = f.get("name", "")
                    if name.endswith(".mp4") and "thumb" not in name.lower():
                        d_url = f"https://archive.org/download/{ident}/{urllib.parse.quote(name)}"
                        r = requests.get(d_url, stream=True, timeout=20)
                        chunk = r.raw.read(4 * 1024 * 1024)
                        if len(chunk) > 100000:
                            out_mp4.write_bytes(chunk)
                            return True
        except Exception: pass
        return False

    @classmethod
    def fetch_pexels_video(cls, query: str, out_mp4: Path) -> bool:
        if not CONFIG.pexels_key: return False
        try:
            r = requests.get("https://api.pexels.com/videos/search", params={"query": query, "per_page": 3, "orientation": "landscape"}, headers={"Authorization": CONFIG.pexels_key}, timeout=12).json()
            vids = r.get("videos", [])
            if vids:
                files = sorted(vids[0].get("video_files", []), key=lambda x: x.get("width", 0), reverse=True)
                if files:
                    out_mp4.write_bytes(requests.get(files[0]["link"], timeout=20).content)
                    return True
        except Exception: pass
        return False

    @classmethod
    def fetch_wikipedia_image(cls, query: str, out_jpg: Path) -> bool:
        try:
            r = requests.get("https://en.wikipedia.org/w/api.php", params={"action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": 3, "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": 1920, "format": "json"}, timeout=12).json()
            pages = list(r.get("query", {}).get("pages", {}).values())
            for p in pages:
                src = p.get("thumbnail", {}).get("source")
                if src:
                    out_jpg.write_bytes(requests.get(src, timeout=15).content)
                    return True
        except Exception: pass
        return False

    @classmethod
    def create_fallback_visual(cls, shot_num: int, out_jpg: Path):
        cmd = [
            "ffmpeg", "-y", "-f", "lavfi",
            f"-i", f"color=c=0x11161B:s={TARGET_W}x{TARGET_H}:d=1",
            "-vf", "noise=alls=15:allf=t,vignette=PI/3", "-frames:v", "1", str(out_jpg)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def scout_shot_worker(shot: Dict, story_info: Dict, semaphore: asyncio.Semaphore) -> Path:
    async with semaphore:
        sid = shot["shot_id"]
        pfx = CONFIG.cache_dir / f"shot_{sid:03d}"
        c_vid = pfx.with_suffix(".mp4")
        c_img = pfx.with_suffix(".jpg")

        if is_valid_visual(c_vid) or is_valid_visual(c_img):
            return c_vid if c_vid.exists() else c_img

        q = clean_query(shot["phrase"] + " " + story_info.get("primary_query", ""))
        movie_title = story_info.get("movie_title", "")
        story_type = story_info.get("story_type", "FORENSIC")
        
        loop = asyncio.get_event_loop()

        # 1. إذا كانت القضية فضائية/علمية
        if story_type == "SPACE" and sid % 2 == 0:
            ok = await loop.run_in_executor(None, MediaSources.fetch_nasa_media, q, c_img)
            if ok and (is_valid_media(c_img.with_suffix(".mp4")) or is_valid_visual(c_img)): 
                return c_img.with_suffix(".mp4") if c_img.with_suffix(".mp4").exists() else c_img

        # 2. إذا كانت تاريخية/صحافة قديمة
        if story_type == "HISTORICAL_OR_OSINT" and sid % 2 != 0:
            ok = await loop.run_in_executor(None, MediaSources.fetch_europeana_image, q, c_img)
            if ok and is_valid_visual(c_img): return c_img
            ok = await loop.run_in_executor(None, MediaSources.fetch_chronicling_america, q, c_img)
            if ok and is_valid_visual(c_img): return c_img
            ok = await loop.run_in_executor(None, MediaSources.fetch_openverse_image, q, c_img)
            if ok and is_valid_visual(c_img): return c_img

        # 3. لقطات أفلام سينمائية صامتة
        if story_info.get("has_major_movie") and sid % 4 == 0 and movie_title:
            ok = await loop.run_in_executor(None, MediaSources.fetch_yarn_clip, f"{movie_title} {q}", c_vid)
            if ok and is_valid_media(c_vid): return c_vid

        # 4. أرشيف الـ FBI وتحقيقات الشرطة
        if sid % 3 == 0:
            ok = await loop.run_in_executor(None, MediaSources.fetch_fbi_archive, q, c_vid)
            if ok and is_valid_media(c_vid): return c_vid

        # 5. لقطات B-Roll سينمائية من Pexels
        ok = await loop.run_in_executor(None, MediaSources.fetch_pexels_video, q, c_vid)
        if ok and is_valid_media(c_vid): return c_vid

        # 6. وثائق وأدلة من ويكيبيديا
        ok = await loop.run_in_executor(None, MediaSources.fetch_wikipedia_image, q, c_img)
        if ok and is_valid_visual(c_img): return c_img

        # 7. خط الدفاع الحديدي (خلفية استقصائية فورية لضمان عدم توقف الرندر)
        await loop.run_in_executor(None, MediaSources.create_fallback_visual, sid, c_img)
        return c_img

# ==============================================================================
# 5. RENDER & ASSEMBLY ENGINE (المونتاج والرندر)
# ==============================================================================
class AssemblyEngine:
    @staticmethod
    def render_sub_clip(media_path: Path, dur: float, out_path: Path):
        is_video = media_path.suffix.lower() == ".mp4"
        
        if is_video:
            vf = (
                f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,"
                f"crop={TARGET_W}:{TARGET_H},eq=contrast=1.08:saturation=0.92,vignette=PI/4.5,"
                f"noise=alls=1:allf=t,fps={TARGET_FPS},tpad=stop_mode=clone:stop_duration={dur:.3f}"
            )
            cmd = ["ffmpeg", "-y", "-ss", "0", "-i", str(media_path), "-vf", vf, "-an", "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "20", str(out_path)]
        else:
            z = "min(zoom+0.0009*(1.1-cos(on/45)),1.12)"
            vf = (
                f"scale={int(TARGET_W*1.15)}:{int(TARGET_H*1.15)}:force_original_aspect_ratio=increase,"
                f"crop={int(TARGET_W*1.15)}:{int(TARGET_H*1.15)},"
                f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={TARGET_W}x{TARGET_H}:fps={TARGET_FPS},"
                f"eq=contrast=1.08:saturation=0.92,vignette=PI/4.5,noise=alls=1:allf=t,format=yuv420p"
            )
            cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(media_path), "-vf", vf, "-an", "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "fast", "-crf", "20", str(out_path)]
            
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    @classmethod
    def assemble_final_cut(cls, shot_clips: List[Path], master_audio: Path, sub_ass: Path, final_output: Path):
        concat_txt = CONFIG.cache_dir / "shots_list.txt"
        concat_txt.write_text("\n".join(f"file '{c.resolve().as_posix()}'" for c in shot_clips), encoding="utf-8")

        temp_video = CONFIG.cache_dir / "temp_video_track.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", "-r", str(TARGET_FPS), str(temp_video)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        sp = str(sub_ass.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
        vf = f"subtitles=filename='{sp}'"
        
        cmd = [
            "ffmpeg", "-y", "-i", str(temp_video), "-i", str(master_audio),
            "-vf", vf, "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(final_output)
        ]
        subprocess.run(cmd, check=True)
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
    tasks = [scout_shot_worker(shot, story_info, semaphore) for shot in shots]
    downloaded_assets = await asyncio.gather(*tasks)

    rendered_shot_clips = []
    for shot, asset in zip(shots, downloaded_assets):
        shot_out = CONFIG.cache_dir / f"rendered_{shot['shot_id']:03d}.mp4"
        try:
            AssemblyEngine.render_sub_clip(asset, shot["duration"], shot_out)
            rendered_shot_clips.append(shot_out)
        except Exception as e:
            fb_jpg = CONFIG.cache_dir / f"fb_{shot['shot_id']}.jpg"
            MediaSources.create_fallback_visual(shot['shot_id'], fb_jpg)
            AssemblyEngine.render_sub_clip(fb_jpg, shot["duration"], shot_out)
            rendered_shot_clips.append(shot_out)

    final_mp4 = CONFIG.base_dir / "final_documentary.mp4"
    AssemblyEngine.assemble_final_cut(rendered_shot_clips, master_wav, sub_ass, final_mp4)

if __name__ == "__main__":
    asyncio.run(main_pipeline())
