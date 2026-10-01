#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
HYBRID V22.39 - Groq Word-Timed Arabic Subtitles / RTL Fix

أهم الإصلاحات:
- توحيد كل المشاهد على 1920x1080 / 30fps / H.264 / AAC 48kHz.
- الدمج النهائي يعيد الترميز بدل concat -c copy لتجنب تضخم المدة وPTS/DTS غير المتوافقة.
- فحص مدة كل مشهد بعد الرندر، ومنع ملفات الفيديو التالفة من دخول القائمة.
- عدم استخدام google.antigravity Python import؛ المراجع تعمل عبر agy CLI فقط.
- تنظيف الكاش القديم عند اختلاف نسخة المحرك.
- حماية أفضل من JSON غير الصالح وملفات الصوت الفارغة.
- الحفاظ على تبريد الصوت 30 ثانية بعد نجاح التوليد.
- إصلاح التحقق من صور WIKIPEDIA وARCHIVE: الصور لا تحتاج ffprobe duration.
- فيديو المشهد يبطؤ قليلاً قبل إعادة التكرار، بدلاً من التكرار الفوري بالسرعة الأصلية.
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
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Dict

import requests
from google import genai
from google.genai import types


ENGINE_VERSION = "V24.0"
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
    """تحقق مخصص للفيديو/الصوت: يجب أن يكون له duration قابلة للقياس."""
    return path.exists() and path.is_file() and path.stat().st_size >= minimum and probe_duration(path) > 0.1


def is_valid_visual(path, minimum=10000):
    """تحقق للصور الثابتة: لا تستخدم ffprobe duration لأن الصورة ليس لها مدة زمنية."""
    if not path.exists() or not path.is_file() or path.stat().st_size < minimum:
        return False
    try:
        r = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=p=0:s=x",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode != 0:
            return False
        m = re.search(r"(\d+)x(\d+)", r.stdout.strip())
        return bool(m and int(m.group(1)) > 0 and int(m.group(2)) > 0)
    except Exception:
        return False


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

    # هوية مستقلة لكل موضوع حتى لا يمكن لـ manifest/cache الخاص بقصة
    # سابقة أن يتسلل إلى قصة جديدة.
    _topic_normalized = re.sub(r"\\s+", " ", str(topic).strip().lower())
    topic_key = hashlib.sha256(_topic_normalized.encode("utf-8")).hexdigest()[:16]

    paths = type("Paths", (), {
        "base": Path("./output_build"),
        "cache": Path(f"./output_build/cache/topic_{topic_key}"),
        "manifest": Path(f"./output_build/manifests/manifest_{topic_key}.json"),
    })()
    gemini_keys = [k.strip() for k in os.environ.get("GEMINI_API_KEY", "").split(",") if k.strip()]
    os.environ.pop("GEMINI_API_KEY", None)
    pexels = os.environ.get("PEXELS_API_KEY", "")
    pixabay = os.environ.get("PIXABAY_API_KEY", "")
    freesound = os.environ.get("FREESOUND_API_KEY", "")
    unsplash = os.environ.get("UNSPLASH_API_KEY", "")
    mapbox = os.environ.get("MAPBOX_API_KEY", "")
    opencage = os.environ.get("OPENCAGE_API_KEY", "")
    apiflash = os.environ.get("APIFLASH_ACCESS_KEY", "")
    newsapi = os.environ.get("NEWS_API_KEY", "")
    nyt = os.environ.get("NYT_API_KEY", "")
    thumbnail_model = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.8-flash")
    thumbnail_enabled = os.environ.get("GENERATE_THUMBNAIL", "1").strip().lower() not in {"0", "false", "no"}
    groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()
    groq_model = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3")
    yt_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    yt_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    drive_token = os.environ.get("DRIVE_REFRESH_TOKEN", "")
    yt_refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    tts_model = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")


CONFIG = HybridConfig()
CONFIG.paths.base.mkdir(parents=True, exist_ok=True)
CONFIG.paths.cache.mkdir(parents=True, exist_ok=True)
CONFIG.paths.manifest.parent.mkdir(parents=True, exist_ok=True)


def _safe_json_get(url, params=None, headers=None, timeout=25):
    try:
        r = requests.get(url, params=params or {}, headers=headers or {}, timeout=timeout)
        if r.status_code >= 400:
            return None
        return r.json()
    except Exception:
        return None


def gather_research_context(topic):
    blocks = []
    if CONFIG.newsapi:
        data = _safe_json_get("https://newsapi.org/v2/everything", {"q": topic, "language": "en", "sortBy": "relevancy", "pageSize": 8, "apiKey": CONFIG.newsapi})
        if data:
            arts = data.get("articles", [])[:8]
            if arts: blocks.append("NEWSAPI:\n" + "\n".join(f"- {a.get('title','')} | {a.get('url','')}" for a in arts if a.get('title')))
    if CONFIG.nyt:
        data = _safe_json_get("https://api.nytimes.com/svc/search/v2/articlesearch.json", {"q": topic, "sort": "relevance", "api-key": CONFIG.nyt}, timeout=20)
        if data:
            docs = data.get("response", {}).get("docs", [])[:6]
            if docs: blocks.append("NYT:\n" + "\n".join(f"- {d.get('headline',{}).get('main','')} | {d.get('web_url','')}" for d in docs if d.get('headline')))
    wd = _safe_json_get("https://www.wikidata.org/w/api.php", {"action":"wbsearchentities", "search":topic, "language":"en", "format":"json", "limit":5})
    if wd:
        ents = wd.get("search", [])[:5]
        if ents: blocks.append("WIKIDATA:\n" + "\n".join(f"- {e.get('id')} | {e.get('label','')} | {e.get('description','')}" for e in ents))
    return "\n\n".join(blocks)[:12000]


class Hybrid_Director:
    def plan_documentary(self) -> List[Dict]:
        if CONFIG.paths.manifest.exists():
            try:
                data = json.loads(CONFIG.paths.manifest.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    log.info(f"📋 استخدام manifest الخاص بالموضوع الحالي: {len(data)} مشهداً | topic_key={CONFIG.topic_key}")
                    return data
            except Exception as e:
                log.warning(f"⚠️ تعذر قراءة manifest: {e}")

        research = gather_research_context(CONFIG.topic)
        prompt = f'''أنت كبير المخرجين ومخطط أفلام وثائقية تحقيقية.
القضية: "{CONFIG.topic}"
أنشئ 40 إلى 50 مشهداً. اجعل التعليق الصوتي لكل مشهد 60 إلى 80 كلمة تقريباً.
لكل مشهد أخرج: scene_num, media_type, search_query, foley_type, narration.
media_type المسموح: PEXELS, PIXABAY, UNSPLASH, WIKIMEDIA, WIKIPEDIA, ARCHIVE, MAPBOX, APIFLASH.
اختر الوسيط بحسب ما يخدم السرد: فيديو للحدث/الحركة، صورة أرشيفية للشخصيات/الأدلة التاريخية، MAPBOX للأماكن والمسارات، APIFLASH لصفحات ويب/أدلة رقمية عندما تكون مفيدة.
search_query إنجليزية فقط، narration عربية.
لا تخترع حقائق. اعتبر الروابط التالية مصادر بحث مساعدة فقط، ولا تنسب معلومة إلى مصدر إلا إذا كانت ظاهرة فيه.

{research or "لا توجد نتائج بحث إضافية متاحة؛ اعتمد على المعرفة الموثوقة ولا تختلق مصادر."}

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
                        "media_type": str(s.get("media_type", "WIKIPEDIA")).upper() if str(s.get("media_type", "WIKIPEDIA")).upper() in {"PEXELS","PIXABAY","UNSPLASH","WIKIMEDIA","WIKIPEDIA","ARCHIVE","MAPBOX","APIFLASH"} else "WIKIPEDIA",
                        "search_query": enforce_english_query(s.get("search_query", "mystery evidence")),
                        "foley_type": str(s.get("foley_type", "none")),
                        "narration": str(s.get("narration", "")).strip(),
                    })
                CONFIG.paths.manifest.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
                log.info(f"✅ تم إنشاء السيناريو الجديد: {len(cleaned)} مشهداً | topic_key={CONFIG.topic_key}")
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
                return is_valid_visual(out, 10000)

            if source == "ARCHIVE":
                r = self._get("https://archive.org/advancedsearch.php", params={"q": f"{safe_query} AND mediatype:image", "fl[]":"identifier", "output":"json", "rows":10})
                docs = r.json().get("response", {}).get("docs", [])
                if len(docs) <= index: return False
                identifier = docs[index].get("identifier")
                if not identifier: return False
                url = "https://archive.org/services/img/" + urllib.parse.quote(identifier)
                out.write_bytes(self._get(url, timeout=60).content)
                return is_valid_visual(out, 10000)


            if source == "UNSPLASH":
                if not CONFIG.unsplash: return False
                r = self._get("https://api.unsplash.com/search/photos", params={"query":safe_query,"orientation":"landscape","per_page":10,"client_id":CONFIG.unsplash})
                results = r.json().get("results", [])
                if len(results) <= index: return False
                url = results[index].get("urls", {}).get("regular") or results[index].get("urls", {}).get("full")
                if not url: return False
                out.write_bytes(self._get(url, timeout=60).content)
                return is_valid_visual(out, 10000)

            if source == "WIKIMEDIA":
                # Commons first; Wikipedia image search is the network fallback because
                # commons.wikimedia.org can occasionally fail DNS on restricted networks.
                commons = _safe_json_get("https://commons.wikimedia.org/w/api.php", {"action":"query","generator":"search","gsrsearch":safe_query,"gsrnamespace":6,"gsrlimit":10,"prop":"imageinfo","iiprop":"url","iiurlwidth":1920,"format":"json"}, timeout=30)
                if commons:
                    pages = list(commons.get("query", {}).get("pages", {}).values())
                    urls=[]
                    for pg in pages:
                        ii=(pg.get("imageinfo") or [{}])[0]
                        u=ii.get("thumburl") or ii.get("url")
                        if u: urls.append(u)
                    if urls:
                        out.write_bytes(self._get(urls[index % len(urls)], timeout=60).content)
                        return is_valid_visual(out,10000)
                # fallback to Wikipedia's accessible API
                r = self._get("https://en.wikipedia.org/w/api.php", params={"action":"query","generator":"search","gsrsearch":safe_query,"gsrnamespace":0,"gsrlimit":10,"prop":"pageimages","piprop":"thumbnail","pithumbsize":1920,"format":"json"})
                pages=[p for p in r.json().get("query", {}).get("pages", {}).values() if p.get("thumbnail", {}).get("source")]
                if not pages: return False
                out.write_bytes(self._get(pages[index % len(pages)]["thumbnail"]["source"], timeout=60).content)
                return is_valid_visual(out,10000)

            if source == "WIKIPEDIA":
                r = self._get("https://en.wikipedia.org/w/api.php", params={"action":"query","generator":"search","gsrsearch":safe_query,"gsrnamespace":0,"gsrlimit":10,"prop":"pageimages","piprop":"thumbnail","pithumbsize":1920,"format":"json"})
                pages=[p for p in r.json().get("query", {}).get("pages", {}).values() if p.get("thumbnail", {}).get("source")]
                if not pages: return False
                out.write_bytes(self._get(pages[index % len(pages)]["thumbnail"]["source"], timeout=60).content)
                return is_valid_visual(out,10000)

            if source == "MAPBOX":
                if not CONFIG.mapbox: return False
                coords = None
                mb = _safe_json_get("https://api.mapbox.com/geocoding/v5/mapbox.places/" + urllib.parse.quote(safe_query) + ".json", {"access_token":CONFIG.mapbox,"limit":1,"language":"en"})
                if mb and mb.get("features"): coords = mb["features"][0].get("center")
                if not coords and CONFIG.opencage:
                    oc = _safe_json_get("https://api.opencagedata.com/geocode/v1/json", {"q":safe_query,"key":CONFIG.opencage,"limit":1,"language":"en"})
                    if oc and oc.get("results"):
                        g=oc["results"][0].get("geometry",{})
                        if "lng" in g and "lat" in g: coords=[g["lng"],g["lat"]]
                if not coords: return False
                lon,lat=coords
                url=f"https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/static/pin-s+ff0000({lon},{lat})/{lon},{lat},11/1280x720?access_token={CONFIG.mapbox}"
                out.write_bytes(self._get(url, timeout=60).content)
                return is_valid_visual(out, 10000)

            if source == "APIFLASH":
                if not CONFIG.apiflash: return False
                target="https://en.wikipedia.org/wiki/"+urllib.parse.quote(safe_query.replace(" ","_"),safe="_")
                r=self._get("https://api.apiflash.com/v1/urltoimage",params={"access_key":CONFIG.apiflash,"url":target,"format":"jpeg","width":1280,"height":720,"fresh":"true"},timeout=90)
                out.write_bytes(r.content)
                return is_valid_visual(out,10000)

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
    pools = {
        "PEXELS":["PEXELS","PEXELS","PIXABAY","PIXABAY","UNSPLASH","WIKIPEDIA","ARCHIVE"],
        "PIXABAY":["PIXABAY","PIXABAY","PEXELS","PEXELS","UNSPLASH","WIKIPEDIA","ARCHIVE"],
        "UNSPLASH":["UNSPLASH","UNSPLASH","PEXELS","PIXABAY","WIKIPEDIA","ARCHIVE"],
        "WIKIMEDIA":["WIKIMEDIA","WIKIPEDIA","ARCHIVE","UNSPLASH"],
        "WIKIPEDIA":["WIKIPEDIA","WIKIMEDIA","ARCHIVE","UNSPLASH"],
        "ARCHIVE":["ARCHIVE","ARCHIVE","WIKIMEDIA","WIKIPEDIA","UNSPLASH"],
        "MAPBOX":["MAPBOX","MAPBOX","WIKIMEDIA","WIKIPEDIA"],
        "APIFLASH":["APIFLASH","WIKIMEDIA","WIKIPEDIA","ARCHIVE"],
    }
    return pools.get(str(media_type).upper(), pools["WIKIPEDIA"])


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


# =====================================================================================
# GROQ WORD-TIMED ARABIC SUBTITLES
# =====================================================================================

def _ass_time(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    total_cs = int(round(seconds * 100))
    hours, rem = divmod(total_cs, 360000)
    minutes, rem = divmod(rem, 6000)
    secs, cs = divmod(rem, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    # ASS uses braces for override tags; escape them so narration cannot become a tag.
    return str(text or "").replace("\\", "\\\\").replace("{", "\\{" ).replace("}", "\\}")


def _write_ass_subtitles(words, out_ass: Path, audio_duration: float):
    """Create short RTL subtitle groups from Groq word timestamps.

    We deliberately keep Arabic in logical order and let libass/HarfBuzz perform
    Arabic shaping + bidi. Do NOT use python-bidi/get_display here; that was the
    source of the visually reversed Arabic seen in the old subtitles.
    """
    valid = []
    for w in words or []:
        if not isinstance(w, dict):
            continue
        text = str(w.get("word", "")).strip()
        try:
            start = float(w.get("start", 0))
            end = float(w.get("end", start))
        except Exception:
            continue
        if not text or end <= start:
            continue
        valid.append({"word": text, "start": max(0.0, start), "end": max(0.0, end)})

    # Groq can occasionally return a timestamp a few milliseconds beyond the audio.
    if audio_duration > 0:
        for w in valid:
            w["start"] = min(w["start"], max(0.0, audio_duration - 0.02))
            w["end"] = min(max(w["end"], w["start"] + 0.05), audio_duration)

    groups=[]; current=[]
    MAX_WORDS=9; MAX_DURATION=3.2; MAX_CHARS=38
    hard_punct=re.compile(r"[.!؟?!؛:]$")
    soft_punct=re.compile(r"[,،]$")
    for w in valid:
        if not current: current=[w]; continue
        gap=w["start"]-current[-1]["end"]
        prospective=" ".join(x["word"] for x in current+[w])
        sentence_end=bool(hard_punct.search(current[-1]["word"]))
        soft_end=bool(soft_punct.search(current[-1]["word"]))
        should_break=(sentence_end or gap>=0.42 or len(current)>=MAX_WORDS or (w["end"]-current[0]["start"]>MAX_DURATION) or (len(prospective)>MAX_CHARS and len(current)>=3) or (soft_end and len(current)>=4 and gap>=0.18))
        if should_break:
            groups.append(current); current=[w]
        else: current.append(w)
    if current: groups.append(current)

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: None",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Arabic,Noto Sans Arabic,62,&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,-1,0,0,0,100,100,0,0,1,0,2,2,80,80,65,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for group in groups:
        start = group[0]["start"]
        end = group[-1]["end"]
        if end <= start:
            continue
        text = " ".join(w["word"] for w in group).strip()
        # Keep the subtitle comfortably inside the actual audio duration.
        if audio_duration > 0:
            end = min(end, audio_duration)
        if end <= start:
            continue
        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Arabic,,0,0,0,,{_ass_escape(text)}"
        )

    out_ass.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return bool(groups)


def generate_fallback_subtitles(narration: str, duration: float, out_ass: Path, out_json: Path) -> bool:
    """Guaranteed subtitle fallback: show the generated narration across the scene if Groq fails."""
    try:
        text = re.sub(r"\s+", " ", str(narration or "")).strip()
        if not text or duration <= 0.1:
            return False
        lines = [
            "[Script Info]", "ScriptType: v4.00+", "PlayResX: 1920", "PlayResY: 1080",
            "[V4+ Styles]",
            "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding",
            "Style: Arabic,Noto Sans Arabic,62,&H00FFFFFF,&H00FFFFFF,&H00101010,&H80000000,1,0,0,0,100,100,0,0,1,3,2,2,80,80,75,1",
            "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
            f"Dialogue: 0,{_ass_time(0)},{_ass_time(duration)},Arabic,,0,0,0,,{_ass_escape(text)}",
        ]
        out_ass.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
        out_json.write_text(json.dumps({"fallback": True, "text": text, "duration": duration}, ensure_ascii=False, indent=2), encoding="utf-8")
        log.warning("⚠️ تم استخدام ترجمة احتياطية؛ Groq word-timing غير متاح.")
        return True
    except Exception as e:
        log.error(f"⚠️ فشل إنشاء الترجمة الاحتياطية: {e}")
        return False


def generate_word_timed_subtitles(audio_path: Path, narration: str, out_ass: Path, out_json: Path) -> bool:
    """Transcribe the generated Arabic narration with Groq Whisper word timestamps."""
    if not CONFIG.groq_api_key:
        log.warning("⚠️ GROQ_API_KEY غير موجود؛ سيتم إنتاج المشهد بدون ترجمة.")
        return False

    # Reuse a valid transcription cache for this exact scene.
    if out_ass.exists() and out_ass.stat().st_size > 500 and out_json.exists():
        return True

    try:
        with open(audio_path, "rb") as fh:
            files = {"file": (audio_path.name, fh, "audio/wav")}
            data = {
                "model": CONFIG.groq_model,
                "language": "ar",
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
                "temperature": "0",
            }
            if narration:
                # Context prompt helps Whisper preserve unusual names/terms from the script.
                data["prompt"] = narration[:900]
            r = requests.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {CONFIG.groq_api_key}"},
                files=files,
                data=data,
                timeout=180,
            )
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}: {r.text[:1000]}")
        payload = r.json()
        words = payload.get("words") or []
        if not words:
            raise RuntimeError("Groq لم يُرجع word timestamps")

        audio_duration = probe_duration(audio_path)
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = _write_ass_subtitles(words, out_ass, audio_duration)
        if not ok:
            raise RuntimeError("تعذر إنشاء ملف ASS من timestamps")
        log.info(f"📝 Groq subtitles OK | {len(words)} كلمة | {out_ass.name}")
        return True
    except Exception as e:
        log.error(f"⚠️ فشل Groq subtitles: {e}")
        return False


def _escape_subtitle_path(path: Path) -> str:
    # FFmpeg subtitles filter escaping for Linux paths. GitHub runners use POSIX paths.
    p = str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return p


def render_scene(media, is_vid, aud, out, dur, montage, subtitle_ass=None):
    # الفيديو يحتاج duration، أما الصور فتحتاج فقط أن تكون صورة صالحة.
    media_ok = is_valid_media(media, 1000) if is_vid else is_valid_visual(media, 10000)
    if not media_ok or not is_valid_media(aud, 1000):
        raise RuntimeError("Media/audio invalid before render")

    fx = ",hue=s=0" if "BW" in str(montage).upper() else ",eq=contrast=1.12:saturation=0.85"
    common_v = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H}{fx},fps={TARGET_FPS},format=yuv420p"
    subtitle_filter = ""
    if subtitle_ass and Path(subtitle_ass).exists():
        sp = _escape_subtitle_path(Path(subtitle_ass))
        # libass performs Arabic shaping + bidi. Keeping the original logical Arabic
        # text is essential; manually applying python-bidi here would reverse it.
        subtitle_filter = f",subtitles=filename='{sp}':force_style='FontName=Noto Sans Arabic,FontSize=62,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,Outline=0,Shadow=2,Alignment=2,MarginV=65'"

    if is_vid:
        # لا نكرر الفيديو. نبطئه قليلاً ثم نمدد آخر فريم إذا انتهى قبل الصوت.
        SLOW_FACTOR = 1.15
        slow_v = f"setpts=PTS*{SLOW_FACTOR:.2f},{common_v},tpad=stop_mode=clone:stop_duration={max(0.5,dur):.3f}"
        if subtitle_filter:
            slow_v += subtitle_filter
        cmd = [
            "ffmpeg","-y","-i",str(media),"-i",str(aud),
            "-filter_complex",f"[0:v]{slow_v}[v]",
            "-map","[v]","-map","1:a:0",
            "-c:v","libx264","-preset","veryfast","-crf","20",
            "-r",str(TARGET_FPS),"-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","192k","-ar",str(TARGET_AR),"-ac","2",
            "-t",f"{max(0.5,dur):.3f}","-movflags","+faststart",str(out)
        ]
    else:
        # zoompan مضبوط على عدد إطارات يساوي المدة * FPS، ثم نحدد مدة الصوت/الفيديو صراحة.
        frames = max(TARGET_FPS, int(round(dur * TARGET_FPS)))
        vf = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H},zoompan=z='min(zoom+0.00035,1.08)':d={frames}:s={TARGET_W}x{TARGET_H}:fps={TARGET_FPS}{fx},format=yuv420p{subtitle_filter}"
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



def _find_font(preferred=None):
    candidates = [
        preferred,
        "/system/fonts/NotoSansArabic-Regular.ttf",
        "/system/fonts/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if p and Path(p).exists():
            return p
    return None


def create_pro_graphics(out_png: Path, topic: str, source: str, scene_num: int = 1):
    """Create a transparent broadcast graphics layer; Pillow keeps FFmpeg's filter graph sane."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as e:
        raise RuntimeError("Pillow is required for professional scene graphics: " + str(e))

    W, H = TARGET_W, TARGET_H
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    font_path = _find_font()
    def font(size, bold=False):
        p = font_path or "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        try: return ImageFont.truetype(p, size)
        except Exception: return ImageFont.load_default()

    # Top broadcast line
    d.rectangle((0, 0, W, 3), fill=(225, 225, 225, 210))
    d.rectangle((48, 44, 58, 128), fill=(225, 225, 225, 235))
    d.text((78, 48), "INVESTIGATIVE FILE", font=font(31, True), fill=(245,245,245,235))
    d.text((78, 88), f"SCENE {scene_num:02d}  /  {source}", font=font(22), fill=(210,210,210,205))

    # Bottom evidence rail
    rail_y = H - 108
    d.rectangle((42, rail_y, W-42, H-42), fill=(7, 9, 12, 205), outline=(205,205,205,90), width=1)
    d.rectangle((42, rail_y, 54, H-42), fill=(225,225,225,220))
    topic_clean = re.sub(r"\s+", " ", str(topic)).strip()
    if len(topic_clean) > 85: topic_clean = topic_clean[:82] + "..."
    d.text((78, rail_y+20), topic_clean, font=font(28, True), fill=(245,245,245,245))
    d.text((78, rail_y+58), "SOURCE-VERIFIED VISUAL  •  EDITORIAL TEST", font=font(19), fill=(190,190,190,220))

    # Right-side technical marker
    x = W - 78
    d.text((x-125, 52), "REC  /  30 FPS", font=font(18, True), fill=(225,225,225,180))
    for i in range(5):
        yy=112+i*13
        d.rectangle((x-60,yy,x,yy+4), fill=(210,210,210,100 if i%2 else 190))

    # Corner framing marks
    c=(225,225,225,145)
    for (x1,y1,x2,y2) in [(36,36,115,36),(36,36,36,115),(W-36,36,W-115,36),(W-36,36,W-36,115),
                           (36,H-36,115,H-36),(36,H-36,36,H-115),(W-36,H-36,W-115,H-36),(W-36,H-36,W-36,H-115)]:
        d.line((x1,y1,x2,y2), fill=c, width=2)
    img.save(out_png)


def render_scene_professional(media, is_vid, aud, out, dur, montage="NORMAL", subtitle_ass=None, topic="", source="", scene_num=1):
    """Professional single-scene FFmpeg render used by --scene-test and later reusable by production."""
    media = Path(media); aud = Path(aud); out = Path(out)
    if not (is_valid_media(media, 1000) if is_vid else is_valid_visual(media, 10000)):
        raise RuntimeError("Invalid visual media before professional render")
    if not is_valid_media(aud, 1000):
        raise RuntimeError("Invalid audio before professional render")

    work = out.parent
    gfx = work / (out.stem + "_graphics.png")
    create_pro_graphics(gfx, topic, source, scene_num)

    fx = "eq=contrast=1.08:saturation=0.88:gamma=0.98,unsharp=5:5:0.35:5:5:0.15,noise=alls=3:allf=t+u,vignette=PI/5"
    subtitle_filter = ""
    if subtitle_ass and Path(subtitle_ass).exists():
        sp = _escape_subtitle_path(Path(subtitle_ass))
        subtitle_filter = f",subtitles=filename='{sp}':force_style='FontName=Noto Sans Arabic,FontSize=62,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,Outline=2,Shadow=2,Alignment=2,MarginV=75'"

    # Video sources are NEVER looped. If the source is shorter than the narration,
    # clone the final frame just long enough to reach the audio duration. This prevents
    # the distracting replay/jump that the old -stream_loop implementation caused.
    if is_vid:
        base = f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H},fps={TARGET_FPS},{fx}"
        # tpad supplies a cinematic hold instead of replaying the source. The final
        # -t hard-stops the scene at the exact processed-audio duration.
        vf = f"setpts=PTS*1.06,{base},tpad=stop_mode=clone:stop_duration={max(0.5,dur):.3f},format=yuv420p"
        filters=f"[0:v]{vf}[base];[1:v]format=rgba[g];[base][g]overlay=0:0:format=auto[v0]"
        if subtitle_filter:
            filters += f";[v0]{subtitle_filter.lstrip(',')}[v]"
            vmap="[v]"
        else:
            vmap="[v0]"
        cmd = [
            "ffmpeg","-y","-i",str(media),"-loop","1","-i",str(gfx),"-i",str(aud),
            "-filter_complex",filters,
            "-map",vmap,"-map","2:a:0",
            "-c:v","libx264","-preset","veryfast","-crf","19","-r",str(TARGET_FPS),"-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","192k","-ar",str(TARGET_AR),"-ac","2","-t",f"{max(.5,dur):.3f}",
            "-movflags","+faststart",str(out)
        ]
    else:
        frames=max(TARGET_FPS,int(round(dur*TARGET_FPS)))
        # Tiny drift + push-in prevents the still-image look without becoming a slideshow effect.
        zoom = f"min(zoom+0.00042,1.075)"
        vf=(f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H},"
            f"zoompan=z='{zoom}':x='iw/2-(iw/zoom/2)+sin(on/45)*8':y='ih/2-(ih/zoom/2)+cos(on/57)*5':"
            f"d={frames}:s={TARGET_W}x{TARGET_H}:fps={TARGET_FPS},"
            f"{fx},format=yuv420p")
        # Subtitle layer is kept separate so libass can shape Arabic after the camera motion.
        filters=f"[0:v]{vf}[base];[1:v]format=rgba[g];[base][g]overlay=0:0:format=auto[v0]"
        if subtitle_filter:
            filters += f";[v0]{subtitle_filter.lstrip(',')}[v]"
            vmap="[v]"
        else:
            vmap="[v0]"
        cmd=[
            "ffmpeg","-y","-loop","1","-i",str(media),"-loop","1","-i",str(gfx),"-i",str(aud),
            "-filter_complex",filters,
            "-map",vmap,"-map","2:a:0",
            "-c:v","libx264","-preset","veryfast","-crf","19","-r",str(TARGET_FPS),"-pix_fmt","yuv420p",
            "-c:a","aac","-b:a","192k","-ar",str(TARGET_AR),"-ac","2","-t",f"{max(.5,dur):.3f}",
            "-movflags","+faststart",str(out)
        ]

    log.info("🎞️ Professional FFmpeg render started...")
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=900)
    if r.returncode!=0:
        raise RuntimeError(r.stderr[-5000:])
    actual=probe_duration(out)
    if actual < 0.5 or not is_valid_media(out,50000):
        raise RuntimeError(f"Professional render failed validation: {actual}s")
    log.info(f"🏁 Professional render OK | {out.name} | {actual:.2f}s")
    return actual


def build_single_scene_plan(topic):
    """Generate exactly one production scene. Use agy when available; GitHub falls back to Gemini API."""
    prompt=f"""أنت مخرج أفلام وثائقية تحقيقية. القضية: "{topic}".
أريد مشهداً واحداً فقط للاختبار، لا أكثر.
اختر لقطة يمكن جلبها فعلياً من PEXELS أو PIXABAY أو WIKIMEDIA/WIKIPEDIA أو ARCHIVE.
اكتب تعليقاً صوتياً عربياً فصيحاً مناسباً لمشهد وثائقي مدته نحو 8-15 ثانية.
أخرج JSON فقط بهذا الشكل:
{{"media_type":"WIKIPEDIA","search_query":"English search query","foley_type":"none","narration":"Arabic narration"}}
لا تخترع حقائق محددة غير مؤكدة، واجعل search_query إنجليزية فقط."""

    if shutil.which("agy"):
        r=subprocess.run(["agy","--model","gemini-3.1-pro","--effort","high","--dangerously-skip-permissions","-p",prompt],capture_output=True,text=True,timeout=360)
        if r.returncode == 0:
            m=re.search(r"\{[\s\S]*\}",r.stdout)
            if m:
                data=json.loads(m.group(0))
                log.info("🧠 Scene plan generated by Antigravity (agy).")
                return {
                    "media_type":str(data.get("media_type","WIKIPEDIA")).upper(),
                    "search_query":enforce_english_query(data.get("search_query","investigation evidence")),
                    "foley_type":str(data.get("foley_type","none")),
                    "narration":str(data.get("narration","")).strip(),
                }
        log.warning("⚠️ agy failed; switching to Gemini API fallback for GitHub test.")

    # GitHub Actions has no interactive Antigravity login. The fallback keeps the
    # test focused on the real media/TTS/subtitle/FFmpeg pipeline.
    if not CONFIG.gemini_keys:
        raise RuntimeError("لا يوجد agy ولا GEMINI_API_KEY صالح لخطة المشهد.")
    client=genai.Client(api_key=CONFIG.gemini_keys[0])
    cfg=types.GenerateContentConfig(response_mime_type="application/json")
    res=client.models.generate_content(model=os.environ.get("GITHUB_PLANNER_MODEL","gemini-3-flash-preview"),contents=prompt,config=cfg)
    raw=getattr(res,"text","") or ""
    m=re.search(r"\{[\s\S]*\}",raw)
    if not m:
        raise RuntimeError("Gemini API لم يُرجع JSON للمشهد")
    data=json.loads(m.group(0))
    log.info("🧠 Scene plan generated by Gemini API fallback (GitHub).")
    return {
        "media_type":str(data.get("media_type","WIKIPEDIA")).upper(),
        "search_query":enforce_english_query(data.get("search_query","investigation evidence")),
        "foley_type":str(data.get("foley_type","none")),
        "narration":str(data.get("narration","")).strip(),
    }


def scene_test_main():
    parser=argparse.ArgumentParser(description="V24 automatic professional single-scene lab")
    parser.add_argument("--topic",default=CONFIG.topic)
    parser.add_argument("--duration",type=float,default=0.0,help="0 = use actual generated audio duration")
    args=parser.parse_args()
    CONFIG.topic=args.topic
    test_dir=CONFIG.paths.base / "scene_test"
    test_dir.mkdir(parents=True,exist_ok=True)
    log.info(f"🧪 SCENE TEST | {CONFIG.topic}")

    if not CONFIG.gemini_keys:
        raise RuntimeError("GEMINI_API_KEY غير موجود في البيئة؛ هو مطلوب للسيناريو وTTS.")
    if shutil.which("agy") is None:
        raise RuntimeError("agy غير موجود في PATH.")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("FFmpeg/FFprobe غير موجودين.")

    director=Hybrid_Director(); fetcher=MediaFetcher()
    scene=build_single_scene_plan(CONFIG.topic)
    log.info(f"🧠 Scene plan: {json.dumps(scene,ensure_ascii=False)}")

    wav=test_dir/"scene_voice.wav"
    processed=test_dir/"scene_audio.m4a"
    ass=test_dir/"scene.ass"
    words=test_dir/"scene.words.json"
    if not director.generate_voice(scene["narration"],wav):
        raise RuntimeError("فشل توليد TTS للمشهد.")
    dur=process_audio(wav,Path("/dev/null"),False,processed)
    if dur<=0: raise RuntimeError("فشل تجهيز صوت المشهد.")
    subtitles_ok = generate_word_timed_subtitles(processed,scene["narration"],ass,words)
    if not subtitles_ok:
        subtitles_ok = generate_fallback_subtitles(scene["narration"],dur,ass,words)
    if args.duration>0: dur=min(dur,args.duration)

    # Prefer the scene's requested source, then automatically fall back to sources
    # that do not require paid API keys. No manual image/audio is needed.
    pool=get_source_pool(scene["media_type"])
    media=None; used_source=None
    q=scene["search_query"]
    for attempt,source in enumerate(pool+ ["WIKIPEDIA","WIKIMEDIA","ARCHIVE"]):
        ext=".mp4" if source in {"PEXELS","PIXABAY"} else ".jpg"
        candidate=test_dir/f"source_{attempt:02d}{ext}"
        log.info(f"🔎 Media attempt {attempt+1} | {source} | {q}")
        if fetcher.fetch_media(source,q,candidate,attempt%3):
            media=candidate; used_source=source; break
        # If the primary query is too narrow, progressively broaden it.
        q=enforce_english_query(q + " documentary evidence")
    if media is None:
        raise RuntimeError("لم أستطع جلب أي وسيط. تحقق من الإنترنت ومفاتيح PEXELS/PIXABAY؛ WIKIPEDIA/WIKIMEDIA/ARCHIVE تعمل دون مفاتيح.")

    out=test_dir/"scene_test_professional.mp4"
    render_scene_professional(media,media.suffix.lower()==".mp4",processed,out,dur,"NORMAL",ass if ass.exists() else None,CONFIG.topic,used_source,1)
    (test_dir/"scene_plan.json").write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding="utf-8")
    log.info(f"\n✅ اكتمل اختبار المشهد.\n🎬 الفيديو: {out.resolve()}\n🖼 المصدر: {media.resolve()}\n🎙 الصوت: {processed.resolve()}")


def clean_old_scene_cache(pfx):
    for suffix in [".mp4", ".wav", ".m4a", ".mp3", ".jpg", ".pcm", "_media.mp4", "_media.jpg", "_foley.mp3", "_best_backup.mp4", "_best_backup.jpg"]:
        p = Path(str(pfx) + suffix) if suffix.startswith("_") else pfx.with_suffix(suffix)
        if p.exists():
            try: p.unlink()
            except Exception: pass


def upload_drive(vid):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
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


def upload_youtube(vid, thumbnail=None):
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    if not (CONFIG.yt_id and CONFIG.yt_refresh): return
    try:
        credentials = Credentials(None, refresh_token=CONFIG.yt_refresh, token_uri="https://oauth2.googleapis.com/token", client_id=CONFIG.yt_id, client_secret=CONFIG.yt_secret)
        yt = build("youtube", "v3", credentials=credentials)
        body = {"snippet":{"title":f"نسخة المخرج | {CONFIG.topic} - {int(time.time())}","description":f"UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE {ENGINE_VERSION}","categoryId":"24"},"status":{"privacyStatus":"private"}}
        req = yt.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(str(vid), chunksize=-1, resumable=True, mimetype="video/mp4"))
        video_id = None
        while True:
            status, response = req.next_chunk()
            if response is not None:
                video_id = response.get("id")
                break
        log.info("✅ تم الرفع إلى YouTube.")
        if thumbnail and video_id and Path(thumbnail).exists():
            try:
                yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(thumbnail), mimetype="image/png" if str(thumbnail).lower().endswith(".png") else "image/jpeg")).execute()
                log.info("🖼️ تم تعيين الصورة المصغرة على YouTube.")
            except Exception as e:
                log.warning(f"⚠️ تعذر تعيين الصورة المصغرة على YouTube: {e}")
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


def generate_thumbnail(final_vid: Path):
    if not CONFIG.thumbnail_enabled or not CONFIG.gemini_keys: return None
    out=CONFIG.paths.base/f"thumbnail_{CONFIG.topic_key}.png"
    if out.exists() and out.stat().st_size>10000: return out
    prompt=("Create a professional cinematic 16:9 YouTube investigative documentary thumbnail about: " + CONFIG.topic + ".\nRealistic documentary photography, dramatic lighting, strong focal subject, premium broadcast look, deep contrast, no logo, no watermark, no tiny unreadable text, leave negative space for Arabic title added separately. Avoid inventing recognizable real people; use symbolic or archival-style imagery when necessary.")
    for model in dict.fromkeys([CONFIG.thumbnail_model,"gemini-2.5-flash-image"]):
        for key in CONFIG.gemini_keys:
            try:
                client=genai.Client(api_key=key); res=client.models.generate_content(model=model,contents=prompt)
                cand=(getattr(res,"candidates",None) or [None])[0]; content=getattr(cand,"content",None)
                for part in (getattr(content,"parts",[]) if content else []):
                    blob=getattr(part,"inline_data",None); data=getattr(blob,"data",None) if blob else None
                    if not data: continue
                    raw=base64.b64decode(data) if isinstance(data,str) else data
                    target=out if raw[:8]==b"\x89PNG\r\n\x1a\n" else out.with_suffix(".jpg") if raw[:2]==b"\xff\xd8" else None
                    if not target: continue
                    target.write_bytes(raw)
                    if target.stat().st_size>10000:
                        log.info(f"🖼 Thumbnail generated: {target}"); return target
            except Exception as e: log.warning(f"⚠️ Thumbnail {model}: {str(e)[:220]}")
    try:
        fallback=CONFIG.paths.base/f"thumbnail_fallback_{CONFIG.topic_key}.jpg"
        r=subprocess.run(["ffmpeg","-y","-sseof","-3","-i",str(final_vid),"-frames:v","1","-q:v","2",str(fallback)],capture_output=True,text=True,timeout=60)
        if r.returncode==0 and fallback.exists(): return fallback
    except Exception: pass
    return None


def main():
    start_time = datetime.now()
    log.info(f"▶ بدء المحرك {ENGINE_VERSION} | القضية: {CONFIG.topic}")
    log.info(f"🧬 Topic Cache Key: {CONFIG.topic_key} | Manifest: {CONFIG.paths.manifest}")
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
        # لا تعتمد هوية الكاش على رقم المشهد فقط.
        # fingerprint يتغير إذا تغير النص أو query أو نوع الوسيط، وبالتالي
        # لا يمكن لصوت/فيديو قديم أن يُركّب على قصة جديدة بالصدفة.
        scene_signature = json.dumps({
            "scene_num": i,
            "media_type": typ,
            "search_query": original_q,
            "foley_type": foley,
            "narration": txt,
        }, ensure_ascii=False, sort_keys=True)
        scene_key = hashlib.sha256(scene_signature.encode("utf-8")).hexdigest()[:12]
        pfx = CONFIG.paths.cache / f"s_{i:03d}_{scene_key}"
        c_mp4 = pfx.with_suffix(".mp4")
        c_wav = pfx.with_suffix(".wav")
        c_foley = Path(str(pfx) + "_foley.mp3")
        c_mp3 = pfx.with_suffix(".m4a")
        c_ass = pfx.with_suffix(".ass")
        c_words = pfx.with_suffix(".words.json")

        # الكاش هنا مرتبط ببصمة الموضوع + بصمة محتوى المشهد، لذلك لا يُعاد استخدام مشهد من قصة أخرى.
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

        # Groq reads the FINAL processed narration audio so subtitle timing matches
        # the exact audio that is placed under the scene.
        subtitles_ok = generate_word_timed_subtitles(c_mp3, txt, c_ass, c_words)
        if not subtitles_ok:
            subtitles_ok = generate_fallback_subtitles(txt, dur, c_ass, c_words)
        if not subtitles_ok:
            log.warning(f"⚠️ المشهد {i+1}: تعذر توليد الترجمة؛ سيستمر الفيديو بدونها.")

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
            # مهم: ملف الوسيط الخام يجب أن يكون منفصلاً عن ملف المشهد النهائي.
            # النسخة السابقة كانت تستخدم s_000.mp4 للاثنين معاً، فيحاول FFmpeg
            # قراءة s_000.mp4 وكتابته في الوقت نفسه، فينتج:
            # "FFmpeg cannot edit existing files in-place" / "Invalid argument".
            c_media = pfx.with_name(pfx.name + "_media" + ext)
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

        if not scene_approved and best_media:
            best_is_video = best_media.suffix.lower() == ".mp4"
            best_is_valid = (
                is_valid_media(best_media, 1000)
                if best_is_video
                else is_valid_visual(best_media, 10000)
            )
            if best_is_valid:
                log.warning(f"⚠️ إنقاذ المشهد {i+1} بأفضل لقطة Score={best_score:.2f}")
                media_ext = ".mp4" if best_is_video else ".jpg"
                c_media = pfx.with_name(pfx.name + "_media" + media_ext)
                shutil.copy2(best_media, c_media)
                scene_approved = True
                montage_style = best_montage

        if not scene_approved:
            append_memory(f"Scene {i+1} failed after {max_attempts} attempts. Query: {original_q}")
            log.error(f"❌ فشل المشهد {i+1}.")
            continue

        try:
            log.info(f"🧩 Render input: {c_media.name} → output: {c_mp4.name}")
            render_scene(c_media, c_media.suffix.lower() == ".mp4", c_mp3, c_mp4, dur, montage_style, c_ass if subtitles_ok else None)
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
        thumbnail = generate_thumbnail(final_vid)
        if thumbnail: log.info(f"🖼️ Thumbnail: {thumbnail}")
        upload_drive(final_vid)
        upload_youtube(final_vid, thumbnail)
    except Exception as e:
        log.error(f"❌ فشل إخراج الفيلم النهائي: {e}")


if __name__ == "__main__":
    if "--scene-test" in sys.argv:
        sys.argv.remove("--scene-test")
        try:
            scene_test_main()
        except Exception as e:
            log.error(f"❌ SCENE TEST FAILED: {e}")
            sys.exit(1)
    else:
        main()
