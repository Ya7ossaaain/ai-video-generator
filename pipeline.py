#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
HYBRID V22.33 - Stable Render / Audio / Concat / Cache

أهم الإصلاحات:
- توحيد كل المشاهد على 1920x1080 / 30fps / H.264 / AAC 48kHz.
- الدمج النهائي يعيد الترميز بدل concat -c copy لتجنب تضخم المدة وPTS/DTS غير المتوافقة.
- فحص مدة كل مشهد بعد الرندر، ومنع ملفات الفيديو التالفة من دخول القائمة.
- عدم استخدام google.antigravity Python import؛ المراجع تعمل عبر agy CLI فقط.
- تنظيف الكاش القديم عند اختلاف نسخة المحرك.
- حماية أفضل من JSON غير الصالح وملفات الصوت الفارغة.
- الحفاظ على تبريد الصوت 30 ثانية بعد نجاح التوليد.
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
from pathlib import Path
from datetime import datetime
from typing import List, Dict

import requests
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


ENGINE_VERSION = "V22.35"
TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
TARGET_AR = 48000


class ProTelemetryFormatter(logging.Formatter):
    COLORS = {
        "INFO": "\x1b[38;5;39m",
        "WARNING": "\x1b[38;5;214m",
        "ERROR": "\x1b[38;5;196m",
    }
    RESET = "\x1b[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, self.RESET)
        fmt = f"{color}%(asctime)s | [%(levelname)s] | %(message)s{self.RESET}"
        return logging.Formatter(fmt, datefmt="%H:%M:%S").format(record)


def setup_logger():
    logger = logging.getLogger("HybridMaster")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(ProTelemetryFormatter())
    logger.addHandler(ch)
    fh = logging.FileHandler("production_logs.txt", encoding="utf-8")
    logger.addHandler(fh)
    logger.propagate = False
    return logger


log = setup_logger()
MEMORY_FILE = Path("director_memory.md")


def append_memory(summary):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(MEMORY_FILE, "a", encoding="utf-8") as f:
        f.write(f"\n\n### [{now}]\n{summary}")


def run_cmd(cmd, timeout=300, capture=False):
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL,
        text=True if capture else False,
        timeout=timeout,
    )


def probe_duration(path):
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            return 0.0
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def is_valid_media(path, minimum=1000):
    return path.exists() and path.is_file() and path.stat().st_size >= minimum and probe_duration(path) > 0.1


def enforce_english_query(query, max_chars=90):
    query = str(query or "")
    safe_q = re.sub(r"[\u0600-\u06FF]", "", query)
    safe_q = re.sub(r"[^A-Za-z0-9,._' -]", " ", safe_q)
    safe_q = re.sub(r"\s+", " ", safe_q).strip()
    words, seen = [], set()
    for word in safe_q.split():
        key = word.lower()
        if key not in seen:
            seen.add(key)
            words.append(word)
    safe_q = " ".join(words)
    if len(safe_q) < 2:
        safe_q = "mystery evidence"
    if len(safe_q) > max_chars:
        safe_q = safe_q[:max_chars].rsplit(" ", 1)[0].strip()
    return safe_q


class HybridConfig:
    topic = os.environ.get("VIDEO_TOPIC", "لغز الجريمة الغامضة")
    paths = type("Paths", (), {
        "base": Path("./output_build"),
        "cache": Path("./output_build/cache"),
        "manifest": Path("./output_build/master_manifest.json"),
    })()
    gemini_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
    os.environ.pop("GEMINI_API_KEY", None)
    pexels = os.environ.get("PEXELS_API_KEY", "")
    pixabay = os.environ.get("PIXABAY_API_KEY", "")
    freesound = os.environ.get("FREESOUND_API_KEY", "")
    yt_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    yt_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    drive_token = os.environ.get("DRIVE_REFRESH_TOKEN", "")
    yt_refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    tts_model = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")


CONFIG = HybridConfig()
CONFIG.paths.base.mkdir(parents=True, exist_ok=True)
CONFIG.paths.cache.mkdir(parents=True, exist_ok=True)


class Hybrid_Director:
    def plan_documentary(self) -> List[Dict]:
        if CONFIG.paths.manifest.exists():
            try:
                data = json.loads(CONFIG.paths.manifest.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    log.info(f"📋 استخدام master_manifest.json: {len(data)} مشهداً.")
                    return data
            except Exception as e:
                log.warning(f"⚠️ تعذر قراءة manifest: {e}")

        prompt = f'''أنت كبير المخرجين ومخطط أفلام وثائقية تحقيقية.
القضية: "{CONFIG.topic}"
أنشئ 40 إلى 50 مشهداً. اجعل التعليق الصوتي لكل مشهد 60 إلى 80 كلمة تقريباً.
لكل مشهد أخرج: scene_num, media_type, search_query, foley_type, narration.
media_type المسموح: PEXELS, PIXABAY, WIKIPEDIA, ARCHIVE.
search_query إنجليزية فقط، narration عربية.
أخرج JSON Array فقط بلا Markdown.
'''

        for round_num in range(3):
            try:
                cmd = [
                    "agy", "--model", "gemini-3.1-pro", "--effort", "high",
                    "--dangerously-skip-permissions", "-p", prompt,
                ]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=360)
                if result.returncode != 0:
                    log.warning(f"⚠️ Agy Error {round_num + 1}: {result.stderr[-1000:]}")
                    time.sleep(5)
                    continue
                match = re.search(r"\[\s*\{.*\}\s*\]", result.stdout, re.DOTALL)
                if not match:
                    log.warning("⚠️ لم يتم العثور على JSON Array.")
                    time.sleep(5)
                    continue
                data = json.loads(match.group(0))
                if not isinstance(data, list) or not data:
                    continue
                cleaned = []
                for n, s in enumerate(data, 1):
                    if not isinstance(s, dict):
                        continue
                    cleaned.append({
                        "scene_num": n,
                        "media_type": str(s.get("media_type", "WIKIPEDIA")).upper(),
                        "search_query": enforce_english_query(s.get("search_query", "mystery evidence")),
                        "foley_type": str(s.get("foley_type", "none")),
                        "narration": str(s.get("narration", "")).strip(),
                    })
                CONFIG.paths.manifest.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
                log.info(f"✅ تم إنشاء السيناريو: {len(cleaned)} مشهداً.")
                return cleaned
            except subprocess.TimeoutExpired:
                log.warning("⏳ انتهت مهلة توليد السيناريو 360 ثانية.")
            except Exception as e:
                log.warning(f"⚠️ خطأ السيناريو: {e}")
            time.sleep(5)
        raise RuntimeError("🛑 فشل إنشاء السيناريو بعد 3 جولات.")

    async def _async_evaluate_scout(self, media_path, narration, source):
        prompt = f'''أنت المراجع البصري الفوري لفيلم وثائقي بعنوان "{CONFIG.topic}".
نوع المصدر: {source}
التعليق الصوتي: "{narration}"
الوسيط المراد فحصه موجود في المسار المحلي التالي:
{Path(media_path).resolve()}

مهم: إذا كان إصدار agy الحالي لا يدعم إرفاق الملف تلقائياً عبر النص، فلا تدّع أنك شاهدت الصورة.
في هذه الحالة أرجع decision="REJECT", score=0, reason="MEDIA_NOT_ATTACHED".
إذا كنت قادراً فعلياً على رؤية الوسيط، قيّم ملاءمته للجو الوثائقي، واقبل اللقطات التعبيرية والرمزية إذا كانت تخدم النص.
أخرج JSON فقط:
{{"decision":"ACCEPT","score":0.85,"reason":"...","montage":"NORMAL","new_query":"English query"}}
'''
        try:
            proc = await asyncio.create_subprocess_exec(
                "agy", "--model", "gemini-3.8-flash", "--effort", "high",
                "--dangerously-skip-permissions", "-p", prompt,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=180)
            if proc.returncode != 0:
                raise RuntimeError(stderr.decode("utf-8", "ignore")[-1000:])
            return stdout.decode("utf-8", "ignore").strip()
        except Exception as e:
            log.error(f"⚠️ انهيار المراجع الفوري: {e}")
            return ""

    def evaluate_scene_with_scout(self, media_path, narration, source):
        log.info(f"👁 Vision Scout يفحص وسيط {source}...")
        try:
            result_text = str(asyncio.run(self._async_evaluate_scout(media_path, narration, source))).strip()
            if not result_text:
                return {"accepted": False, "montage": "NORMAL", "new_query": "investigation evidence", "score": 0.0, "reason": "Empty response"}
            log.info(f"🗣️ نتيجة المراجع: {result_text[:1200]}")
            match = re.search(r"\{[\s\S]*\}", result_text)
            if not match:
                return {"accepted": False, "montage": "NORMAL", "new_query": "archival evidence", "score": 0.0, "reason": "Parse error"}
            data = json.loads(match.group(0))
            score = max(0.0, min(1.0, float(data.get("score", 0))))
            decision = str(data.get("decision", "")).upper()
            return {
                "accepted": decision == "ACCEPT" and score >= 0.60,
                "montage": str(data.get("montage", "NORMAL")),
                "new_query": enforce_english_query(data.get("new_query", "")),
                "score": score,
                "reason": str(data.get("reason", "")),
            }
        except Exception as e:
            log.error(f"⚠️ خطأ المراجع: {e}")
            return {"accepted": False, "montage": "NORMAL", "new_query": "", "score": 0.0, "reason": str(e)}

    def generate_voice(self, text, out_wav):
        if not CONFIG.gemini_keys:
            log.error("❌ لا توجد GEMINI_API_KEY.")
            return False
        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
                )
            ),
        )
        for round_num in range(3):
            for i, key in enumerate(CONFIG.gemini_keys):
                try:
                    client = genai.Client(api_key=key)
                    res = client.models.generate_content(
                        model=CONFIG.tts_model,
                        contents="[INSTRUCTION: Deep chilling narrator]\n" + text,
                        config=cfg,
                    )
                    part = res.candidates[0].content.parts[0]
                    audio = part.inline_data.data
                    mime = getattr(part.inline_data, "mime_type", "") or ""
                    raw = base64.b64decode(audio) if isinstance(audio, str) else audio
                    # Gemini قد يعيد PCM خاماً؛ حوّله إلى WAV حقيقي إذا لم تكن البيانات WAV.
                    if raw[:4] == b"RIFF":
                        out_wav.write_bytes(raw)
                    else:
                        tmp_pcm = out_wav.with_suffix(".pcm")
                        tmp_pcm.write_bytes(raw)
                        rate_match = re.search(r"rate=(\d+)", mime)
                        sample_rate = int(rate_match.group(1)) if rate_match else 24000
                        r = subprocess.run([
                            "ffmpeg", "-y", "-f", "s16le", "-ar", str(sample_rate), "-ac", "1",
                            "-i", str(tmp_pcm), "-c:a", "pcm_s16le", str(out_wav)
                        ], capture_output=True, text=True, timeout=60)
                        try: tmp_pcm.unlink()
                        except Exception: pass
                        if r.returncode != 0:
                            raise RuntimeError(r.stderr[-500:])
                    if is_valid_media(out_wav, 1000):
                        log.info("⏳ تم توليد الصوت بنجاح. تبريد 30 ثانية...")
                        time.sleep(30)
                        return True
                except Exception as e:
                    log.warning(f"⚠️ فشل مفتاح الصوت {i + 1}: {str(e)[:250]}")
                    time.sleep(2)
            time.sleep(10)
        log.error("❌ استنفدت محاولات توليد الصوت.")
        return False


class MediaFetcher:
    def __init__(self):
        self.h = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://en.wikipedia.org/",
        }

    def _get(self, url, **kwargs):
        kwargs.setdefault("timeout", 30)
        kwargs.setdefault("headers", self.h)
        r = requests.get(url, **kwargs)
        r.raise_for_status()
        return r

    def fetch_media(self, source, query, out, index):
        safe_query = enforce_english_query(query)
        try:
            if source == "PEXELS":
                if not CONFIG.pexels: return False
                r = self._get("https://api.pexels.com/videos/search", params={"query": safe_query, "orientation": "landscape", "per_page": 10}, headers={"Authorization": CONFIG.pexels, "User-Agent": self.h["User-Agent"]})
                videos = r.json().get("videos", [])
                if len(videos) <= index: return False
                files = sorted(videos[index].get("video_files", []), key=lambda x: x.get("width", 0), reverse=True)
                if not files or not files[0].get("link"): return False
                out.write_bytes(self._get(files[0]["link"], timeout=90).content)
                return is_valid_media(out, 50000)

            if source == "PIXABAY":
                if not CONFIG.pixabay: return False
                r = self._get("https://pixabay.com/api/videos/", params={"key": CONFIG.pixabay, "q": safe_query[:100], "per_page": 10})
                hits = r.json().get("hits", [])
                if len(hits) <= index: return False
                vids = hits[index].get("videos", {})
                info = vids.get("large") or vids.get("medium") or vids.get("small")
                if not info or not info.get("url"): return False
                out.write_bytes(self._get(info["url"], timeout=90).content)
                return is_valid_media(out, 50000)

            if source == "WIKIPEDIA":
                r = self._get("https://en.wikipedia.org/w/api.php", params={"action":"query","generator":"search","gsrsearch":safe_query,"gsrnamespace":0,"gsrlimit":10,"prop":"pageimages","piprop":"thumbnail","pithumbsize":1920,"format":"json"})
                pages = [p for p in r.json().get("query", {}).get("pages", {}).values() if p.get("thumbnail", {}).get("source")]
                if not pages: return False
                out.write_bytes(self._get(pages[index % len(pages)]["thumbnail"]["source"], timeout=60).content)
                return out.exists() and out.stat().st_size > 10000

            if source == "ARCHIVE":
                r = self._get("https://archive.org/advancedsearch.php", params={"q": f"{safe_query} AND mediatype:image", "fl[]":"identifier", "output":"json", "rows":10})
                docs = r.json().get("response", {}).get("docs", [])
                if len(docs) <= index: return False
                identifier = docs[index].get("identifier")
                if not identifier: return False
                url = "https://archive.org/services/img/" + urllib.parse.quote(identifier)
                out.write_bytes(self._get(url, timeout=60).content)
                return out.exists() and out.stat().st_size > 10000

            if source == "FREESOUND":
                if not CONFIG.freesound: return False
                r = self._get("https://freesound.org/apiv2/search/text/", params={"query":safe_query,"token":CONFIG.freesound,"fields":"previews","page_size":5})
                results = r.json().get("results", [])
                if not results: return False
                url = results[0].get("previews", {}).get("preview-hq-mp3")
                if not url: return False
                out.write_bytes(self._get(url, timeout=60).content)
                return out.exists() and out.stat().st_size > 1000
        except requests.RequestException as e:
            log.warning(f"🌐 خطأ شبكة {source}: {str(e)[:180]}")
        except Exception as e:
            log.warning(f"⚠️ خطأ {source}: {str(e)[:180]}")
        return False


def get_source_pool(media_type):
    if str(media_type).upper() in ["PEXELS", "PIXABAY"]:
        return ["PEXELS", "PEXELS", "PEXELS", "PIXABAY", "PIXABAY", "PIXABAY"]
    return ["WIKIPEDIA", "WIKIPEDIA", "WIKIPEDIA", "ARCHIVE", "ARCHIVE", "ARCHIVE"]


def process_audio(voice, foley, has_foley, out):
    if not is_valid_media(voice, 1000):
        return 0.0
    if has_foley and is_valid_media(foley, 1000):
        fc = "[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[v];[1:a]volume=0.04[bg];[v][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]"
        cmd = ["ffmpeg","-y","-i",str(voice),"-stream_loop","-1","-i",str(foley),"-filter_complex",fc,"-map","[aout]","-ar",str(TARGET_AR),"-ac","2","-c:a","aac","-b:a","192k",str(out)]
    else:
        cmd = ["ffmpeg","-y","-i",str(voice),"-filter_complex","[0:a]loudnorm=I=-16:TP=-1.5:LRA=11[aout]","-map","[aout]","-ar",str(TARGET_AR),"-ac","2","-c:a","aac","-b:a","192k",str(out)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if r.returncode != 0:
            log.error(f"❌ FFmpeg audio: {r.stderr[-1000:]}")
            return 0.0
        dur = probe_duration(out)
        return dur if dur >= 0.5 else 0.0
    except Exception as e:
        log.error(f"❌ خطأ معالجة الصوت: {e}")
        return 0.0


def render_scene(media, is_vid, aud, out, dur, montage):
    if not is_valid_media(media, 1000) or not is_valid_media(aud, 1000):
        raise RuntimeError("Media/audio invalid before render")

    fx = ",hue=s=0" if "BW" in str(montage).upper() else ",eq=contrast=1.12:saturation=0.85"
    common_v = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H}{fx},fps={TARGET_FPS},format=yuv420p"

    if is_vid:
        cmd = [
            "ffmpeg","-y","-stream_loop","-1","-i",str(media),"-i",str(aud),
            "-filter_complex",f"[0:v]{common_v}[v]",
            "-map","[v]","-map","1:a:0",
            "-c:v","libx264","-preset","veryfast","-crf","20",
            "-r",str(TARGET_FPS),"-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","192k","-ar",str(TARGET_AR),"-ac","2",
            "-t",f"{max(0.5,dur):.3f}","-movflags","+faststart",str(out)
        ]
    else:
        # zoompan مضبوط على عدد إطارات يساوي المدة * FPS، ثم نحدد مدة الصوت/الفيديو صراحة.
        frames = max(TARGET_FPS, int(round(dur * TARGET_FPS)))
        vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H},zoompan=z='min(zoom+0.00035,1.08)':d={frames}:s={TARGET_W}x{TARGET_H}:fps={TARGET_FPS}{fx},format=yuv420p"
        cmd = [
            "ffmpeg","-y","-loop","1","-i",str(media),"-i",str(aud),
            "-filter_complex",f"[0:v]{vf}[v]",
            "-map","[v]","-map","1:a:0",
            "-c:v","libx264","-preset","veryfast","-crf","20",
            "-r",str(TARGET_FPS),"-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","192k","-ar",str(TARGET_AR),"-ac","2",
            "-t",f"{max(0.5,dur):.3f}","-movflags","+faststart",str(out)
        ]

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-2000:])
    actual = probe_duration(out)
    if actual < 0.5 or not is_valid_media(out, 50000):
        raise RuntimeError(f"Rendered scene invalid: duration={actual}")
    log.info(f"🎬 Render OK | {out.name} | {actual:.2f}s")


def clean_old_scene_cache(pfx):
    for suffix in [".mp4", ".wav", ".m4a", ".mp3", ".jpg", ".pcm", "_foley.mp3", "_best_backup.mp4", "_best_backup.jpg"]:
        p = Path(str(pfx) + suffix) if suffix.startswith("_") else pfx.with_suffix(suffix)
        if p.exists():
            try: p.unlink()
            except Exception: pass


def upload_drive(vid):
    if not (CONFIG.yt_id and CONFIG.drive_token): return
    try:
        credentials = Credentials(None, refresh_token=CONFIG.drive_token, token_uri="https://oauth2.googleapis.com/token", client_id=CONFIG.yt_id, client_secret=CONFIG.yt_secret)
        dr = build("drive", "v3", credentials=credentials)
        res = dr.files().list(q="name='Broadcast_Vault' and mimeType='application/vnd.google-apps.folder'", fields="files(id)").execute()
        files = res.get("files", [])
        fid = files[0]["id"] if files else dr.files().create(body={"name":"Broadcast_Vault","mimeType":"application/vnd.google-apps.folder"}, fields="id").execute()["id"]
        req = dr.files().create(body={"name":vid.name,"parents":[fid]}, media_body=MediaFileUpload(str(vid), mimetype="video/mp4", resumable=True, chunksize=5*1024*1024))
        while True:
            status, response = req.next_chunk()
            if response is not None:
                break
        log.info("✅ تم حفظ نسخة في Google Drive.")
    except Exception as e:
        log.error(f"⚠️ فشل Google Drive: {e}")


def upload_youtube(vid):
    if not (CONFIG.yt_id and CONFIG.yt_refresh): return
    try:
        credentials = Credentials(None, refresh_token=CONFIG.yt_refresh, token_uri="https://oauth2.googleapis.com/token", client_id=CONFIG.yt_id, client_secret=CONFIG.yt_secret)
        yt = build("youtube", "v3", credentials=credentials)
        body = {"snippet":{"title":f"نسخة المخرج | {CONFIG.topic} - {int(time.time())}","description":f"UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE {ENGINE_VERSION}","categoryId":"24"},"status":{"privacyStatus":"private"}}
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(vid), chunksize=-1, resumable=True, mimetype="video/mp4"))
        while True:
            status, response = req.next_chunk()
            if response is not None:
                break
        log.info("✅ تم الرفع إلى YouTube.")
    except Exception as e:
        log.error(f"⚠️ فشل YouTube: {e}")


def concat_final(clips, final_vid):
    txt_list = CONFIG.paths.base / "video_list.txt"
    concat_lines = []
    for c in clips:
        path_str = c.resolve().as_posix().replace("'", "'\''")
        concat_lines.append("file '" + path_str + "'")
    txt_list.write_text("\n".join(concat_lines), encoding="utf-8")
    # لا نستخدم -c copy؛ هذا هو الإصلاح الأساسي لمشكلة تضخم مدة الفيلم عند اختلاف timebase/fps بين المشاهد.
    cmd = [
        "ffmpeg","-y","-f","concat","-safe","0","-i",str(txt_list),
        "-c:v","libx264","-preset","veryfast","-crf","20","-r",str(TARGET_FPS),
        "-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-ar",str(TARGET_AR),"-ac","2",
        "-movflags","+faststart",str(final_vid)
    ]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    if r.returncode != 0:
        raise RuntimeError(r.stderr[-3000:])
    duration = probe_duration(final_vid)
    if duration < 1 or not is_valid_media(final_vid, 50000):
        raise RuntimeError("Final video failed validation")
    log.info(f"🎬 الفيلم النهائي: {duration/60:.2f} دقيقة ({duration:.1f}s)")
    return duration


def main():
    start_time = datetime.now()
    log.info(f"▶ بدء المحرك {ENGINE_VERSION} | القضية: {CONFIG.topic}")
    director = Hybrid_Director()
    fetcher = MediaFetcher()
    try:
        script = director.plan_documentary()
    except Exception as e:
        log.error(str(e)); sys.exit(1)

    clips = []
    total_expected = 0.0

    for i, scene in enumerate(script):
        if (datetime.now() - start_time).total_seconds() > 13500:
            log.warning("⏳ تم تجاوز الحد الزمني الكلي."); break

        typ = str(scene.get("media_type", "WIKIPEDIA")).upper()
        original_q = scene.get("search_query", "")
        foley = scene.get("foley_type", "none")
        txt = str(scene.get("narration", "")).strip()
        pfx = CONFIG.paths.cache / f"s_{i:03d}"
        c_mp4 = pfx.with_suffix(".mp4")
        c_wav = pfx.with_suffix(".wav")
        c_foley = Path(str(pfx) + "_foley.mp3")
        c_mp3 = pfx.with_suffix(".m4a")

        # الكاش يستخدم فقط إذا كان الفيديو نفسه صالحاً ويمكن قياس مدته.
        if is_valid_media(c_mp4, 50000):
            cached_dur = probe_duration(c_mp4)
            clips.append(c_mp4)
            total_expected += cached_dur
            log.info(f"⏭ المشهد {i+1} من الكاش | {cached_dur:.1f}s")
            continue
        if c_mp4.exists():
            try: c_mp4.unlink()
            except Exception: pass

        log.info(f"\n🎥 المشهد {i+1}/{len(script)}...")
        if not is_valid_media(c_wav, 1000):
            if not director.generate_voice(txt, c_wav):
                log.error(f"❌ فشل صوت المشهد {i+1}."); continue

        has_foley = False
        if foley and str(foley).lower() != "none":
            has_foley = fetcher.fetch_media("FREESOUND", enforce_english_query(foley), c_foley, 0)
        dur = process_audio(c_wav, c_foley, has_foley, c_mp3)
        if dur <= 0:
            log.error(f"❌ تعذر تجهيز الصوت للمشهد {i+1}."); continue

        scene_approved = False
        montage_style = "NORMAL"
        current_q = enforce_english_query(original_q)
        base_q = current_q
        sources_pool = get_source_pool(typ)
        max_attempts = 15
        best_score = -1.0
        best_media = None
        best_montage = "NORMAL"
        query_variants = ["documentary evidence","archival photograph","investigation scene","crime investigation","police investigation","historical evidence","news archive","forensic evidence","mysterious location","case evidence"]

        for attempt in range(max_attempts):
            source = sources_pool[attempt % len(sources_pool)]
            idx = attempt % 3
            ext = ".mp4" if source in ["PEXELS","PIXABAY"] else ".jpg"
            c_media = pfx.with_suffix(ext)
            if c_media.exists():
                try: c_media.unlink()
                except Exception: pass
            safe_q = enforce_english_query(current_q)
            log.info(f"🔎 محاولة {attempt+1}/{max_attempts} | {source} | {safe_q}")
            found = fetcher.fetch_media(source, safe_q, c_media, idx)
            if found:
                eval_res = director.evaluate_scene_with_scout(c_media, txt, source)
                score = float(eval_res.get("score", 0))
                if score > best_score:
                    best_score = score
                    best_montage = eval_res.get("montage", "NORMAL")
                    best_media = Path(str(pfx) + f"_best_backup{ext}")
                    try: shutil.copy2(c_media, best_media)
                    except Exception: best_media = None
                if eval_res.get("accepted"):
                    scene_approved = True
                    montage_style = eval_res.get("montage", "NORMAL")
                    break
                new_q = enforce_english_query(eval_res.get("new_query", ""))
                current_q = new_q if new_q not in ["mystery evidence", safe_q] else enforce_english_query(f"{base_q} {query_variants[attempt % len(query_variants)]}")
            else:
                current_q = enforce_english_query(f"{base_q} {query_variants[attempt % len(query_variants)]}")
            time.sleep(3)

        if not scene_approved and best_media and is_valid_media(best_media, 1000):
            log.warning(f"⚠️ إنقاذ المشهد {i+1} بأفضل لقطة Score={best_score:.2f}")
            c_media = pfx.with_suffix(".mp4" if best_media.name.endswith(".mp4") else ".jpg")
            shutil.copy2(best_media, c_media)
            scene_approved = True
            montage_style = best_montage

        if not scene_approved:
            append_memory(f"Scene {i+1} failed after {max_attempts} attempts. Query: {original_q}")
            log.error(f"❌ فشل المشهد {i+1}.")
            continue

        try:
            render_scene(c_media, c_media.suffix.lower() == ".mp4", c_mp3, c_mp4, dur, montage_style)
            clips.append(c_mp4)
            total_expected += probe_duration(c_mp4)
            for b in CONFIG.paths.cache.glob(pfx.name + "_best_backup*"):
                try: b.unlink()
                except Exception: pass
        except Exception as e:
            log.error(f"⚠️ فشل رندر المشهد {i+1}: {e}")

    final_vid = CONFIG.paths.base / f"MasterDoc_{int(time.time())}.mp4"
    if not clips:
        log.error("❌ لا توجد مشاهد جاهزة للدمج."); return

    try:
        final_duration = concat_final(clips, final_vid)
        log.info(f"📐 مجموع مدد المشاهد: {total_expected/60:.2f} دقيقة")
        log.info(f"📐 مدة الفيلم بعد الدمج: {final_duration/60:.2f} دقيقة")
        if final_duration > total_expected * 1.15 and total_expected > 10:
            log.error("🚨 تحذير: مدة الفيلم أكبر بكثير من مجموع مدد المشاهد؛ تم اكتشاف مشكلة زمنية.")
        upload_drive(final_vid)
        upload_youtube(final_vid)
    except Exception as e:
        log.error(f"❌ فشل إخراج الفيلم النهائي: {e}")


if __name__ == "__main__":
    main()
