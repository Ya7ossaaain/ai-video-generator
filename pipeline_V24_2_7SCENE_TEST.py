#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE
HYBRID V22.41 - Original Script Subtitles / Whisper Timing / RTL Fix

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
import difflib
import unicodedata
import logging
import subprocess
import base64
import hashlib
import asyncio
import urllib.parse
import shutil

try:
    import opentimelineio as otio
except Exception:
    otio = None
from pathlib import Path
from datetime import datetime
from typing import List, Dict

import requests
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


ENGINE_VERSION = "V24.2-7SCENE-ORIGINAL-SCRIPT-SUBTITLES"
TARGET_W = 1920
TARGET_H = 1080
TARGET_FPS = 30
TARGET_AR = 48000
TEST_SCENE_COUNT = 7
TEST_MODE = True


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
        "edit_bible": Path(f"./output_build/manifests/edit_bible_{topic_key}.json"),
        "timeline": Path(f"./output_build/manifests/timeline_{topic_key}.otio"),
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
    thumbnail_enabled = os.environ.get("GENERATE_THUMBNAIL", "0").strip().lower() not in {"0", "false", "no"}
    groq_api_key = os.environ.get("GROQ_API_KEY", "").strip()
    groq_model = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3")
    yt_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    yt_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    drive_token = os.environ.get("DRIVE_REFRESH_TOKEN", "")
    yt_refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    tts_model = os.environ.get("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")


# Groq transcription API currently limits the optional context prompt to 468 characters.
# Keep this guard in one place so a long Arabic narration can NEVER generate an HTTP 400
# merely because it was copied into the optional prompt field.
GROQ_PROMPT_MAX_CHARS = 468


def _safe_groq_prompt(narration: str) -> str:
    """Return a Groq-safe optional context prompt, or an empty string if it is too long.

    The narration itself is still sent as audio; dropping the optional prompt does not
    remove any spoken content. We intentionally prefer omitting the prompt over blindly
    truncating Arabic text, which could leave a name or phrase half-written.
    """
    if not narration:
        return ""
    prompt = " ".join(str(narration).split())
    prompt_len = len(prompt)
    if prompt_len <= GROQ_PROMPT_MAX_CHARS:
        log.info(f"🛡️ Groq prompt check: {prompt_len}/{GROQ_PROMPT_MAX_CHARS} chars — OK")
        return prompt

    log.warning(
        f"🛡️ Groq prompt check: {prompt_len}/{GROQ_PROMPT_MAX_CHARS} chars — "
        "prompt too long; sending NO optional prompt. Audio transcription continues normally."
    )
    return ""


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




def _default_edit_bible():
    return {
        "version": "24.2",
        "visual_language": "premium investigative documentary; restrained, cinematic, editorial rather than flashy",
        "pacing": {
            "default_change_seconds": [1.5, 3.5],
            "high_tension_seconds": [0.5, 1.6],
            "explanation_seconds": [2.2, 5.0],
            "evidence_seconds": [1.4, 3.8],
            "allow_long_shot_seconds": 6.0
        },
        "camera": ["slow_push", "slow_pull", "lateral_drift", "static_with_micro_motion"],
        "transitions": ["hard_cut", "dip_black", "match_cut", "soft_dissolve"],
        "graphics": {"style": "minimal evidence graphics", "accent": "single restrained accent", "avoid": ["random_glitch", "overuse_of_hud"]},
        "subtitles": {"style": "clean_arabic_cinematic", "alignment": 2},
        "sound": {"duck_music_on_narration": True, "use_silence_for_revelations": True},
        "continuity": {"avoid_repeated_media": True, "avoid_repeated_transition": True, "preserve_motif": True}
    }


def normalize_edit_bible(data):
    base = _default_edit_bible()
    if not isinstance(data, dict):
        return base
    # Controlled shallow/deep merge; never let malformed model output break production.
    for k,v in data.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k].update(v)
        else:
            base[k] = v
    return base


def save_edit_bible(bible):
    CONFIG.paths.edit_bible.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"🎬 Edit Bible محفوظ: {CONFIG.paths.edit_bible}")


def write_otio_timeline(clips, final_path, scene_directives=None):
    """Create an editorial timeline manifest. Rendering remains FFmpeg-native; OTIO is the review/edit memory."""
    if otio is None:
        log.warning("⚠️ OpenTimelineIO غير مثبت؛ سيتم حفظ timeline JSON بديل.")
        payload=[]
        for i,c in enumerate(clips):
            payload.append({"index":i,"path":str(Path(c).resolve()),"duration":probe_duration(c),"directive":(scene_directives or [None]*len(clips))[i] if i < len(scene_directives or []) else None})
        final_path.with_suffix(".json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
        return
    tl=otio.schema.Timeline(name=f"V24.2 | {CONFIG.topic}")
    track=otio.schema.Track(name="MASTER_VIDEO")
    for i,c in enumerate(clips):
        dur=probe_duration(c)
        rate=TARGET_FPS
        clip=otio.schema.Clip(name=Path(c).stem, media_reference=otio.schema.ExternalReference(target_url=Path(c).resolve().as_uri()))
        clip.source_range=otio.opentime.TimeRange(start_time=otio.opentime.RationalTime(0,rate), duration=otio.opentime.RationalTime(max(1,int(round(dur*rate))),rate))
        track.append(clip)
    tl.tracks.append(track)
    otio.adapters.write_to_file(tl, str(final_path), adapter_name="otio_json")
    log.info(f"🧭 OTIO timeline محفوظ: {final_path}")

class Hybrid_Director:
    def plan_documentary(self) -> List[Dict]:
        if CONFIG.paths.manifest.exists():
            try:
                data = json.loads(CONFIG.paths.manifest.read_text(encoding="utf-8"))
                if isinstance(data, list) and data:
                    # V24.2 requires editorial directives. Old V24 manifests are not reused
                    # because they lack the episode-level Edit Bible/beat plan.
                    if data and all(isinstance(x, dict) and bool(x.get("beat_plan")) for x in data):
                        if not CONFIG.paths.edit_bible.exists(): save_edit_bible(_default_edit_bible())
                        log.info(f"📋 استخدام manifest V24.2 الخاص بالموضوع الحالي: {len(data)} مشهداً | topic_key={CONFIG.topic_key}")
                        return data
                    log.info("♻️ manifest قديم بدون Edit Plan؛ سيتم بناء خطة V24.2 جديدة.")
            except Exception as e:
                log.warning(f"⚠️ تعذر قراءة manifest: {e}")

        research = gather_research_context(CONFIG.topic)
        prompt = f'''أنت كبير المخرجين ومخطط أفلام وثائقية تحقيقية.
القضية: "{CONFIG.topic}"
أنت لا تكتب السيناريو فقط؛ أنت SHOWRUNNER والمخرج التحريري للحلقة كاملة.
للاختبار الحالي أنشئ 7 مشاهد مترابطة فقط، لكن خطط الإيقاع البصري للحلقة كاملة قبل التنفيذ. لا تجعل كل مشهد يبدو كفيديو مستقل. كل مشهد يجب أن يحتوي على تعليق صوتي عربي أصلي بطول تقريبي 95 إلى 125 كلمة (حوالي 38 إلى 55 ثانية بصوت وثائقي طبيعي). لا تختصر المشهد إلى جملة أو فقرة قصيرة. اجعل المشاهد السبعة تشكل بداية/تصعيد/أدلة/تحول/كشف/خاتمة مصغرة واحدة.
أخرج JSON Object واحداً يحتوي على: edit_bible و scenes.
edit_bible يجب أن يحدد لغة بصرية واحدة للحلقة، قواعد pacing، camera movement، transition vocabulary، graphics/evidence language، subtitle style، sound strategy، recurring motifs، وما يجب تجنبه.
لكل مشهد أخرج: scene_num, media_type, search_query, foley_type, narration, attention_level, visual_role, beat_plan, camera_motion, transition_in, transition_out, graphic_intent. narration يجب أن يكون 95-125 كلمة عربية تقريباً، مع علامات ترقيم عربية واضحة عند الحاجة.
beat_plan قائمة من 2 إلى 6 beats، وكل beat يحتوي تقريباً: relative_start, relative_end, action, visual_priority. اجعل beats مرتبطة بمعنى الجملة لا بمؤثرات عشوائية.
لا تستخدم glitch إلا عندما يخدم السرد. لا تكرر نفس transition بشكل متتالٍ. لا تجعل كل beat يحتاج ملف media جديداً؛ يمكن أن تكون beats حركة/تكبير/كشف دليل داخل نفس الوسيط.
media_type المسموح: PEXELS, PIXABAY, UNSPLASH, WIKIMEDIA, WIKIPEDIA, ARCHIVE, MAPBOX, APIFLASH.
اختر الوسيط بحسب ما يخدم السرد: فيديو للحدث/الحركة، صورة أرشيفية للأدلة التاريخية، MAPBOX للأماكن والمسارات. search_query إنجليزية فقط، narration عربية.
لا تخترع حقائق. اعتبر الروابط التالية مصادر بحث مساعدة فقط، ولا تنسب معلومة إلى مصدر إلا إذا كانت ظاهرة فيها.

{research or "لا توجد نتائج بحث إضافية متاحة؛ اعتمد على المعرفة الموثوقة ولا تختلق مصادر."}

أخرج JSON Object فقط بلا Markdown.
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
                match = re.search(r"\{[\s\S]*\}", result.stdout)
                if not match:
                    log.warning("⚠️ لم يتم العثور على JSON Object.")
                    time.sleep(5)
                    continue
                data = json.loads(match.group(0))
                if isinstance(data, list):
                    data = {"edit_bible": _default_edit_bible(), "scenes": data}
                if not isinstance(data, dict) or not data.get("scenes"):
                    continue
                bible = normalize_edit_bible(data.get("edit_bible"))
                save_edit_bible(bible)
                cleaned = []
                for n, s in enumerate(data.get("scenes", []), 1):
                    if not isinstance(s, dict):
                        continue
                    cleaned.append({
                        "scene_num": n,
                        "media_type": str(s.get("media_type", "WIKIPEDIA")).upper() if str(s.get("media_type", "WIKIPEDIA")).upper() in {"PEXELS","PIXABAY","UNSPLASH","WIKIMEDIA","WIKIPEDIA","ARCHIVE","MAPBOX","APIFLASH"} else "WIKIPEDIA",
                        "search_query": enforce_english_query(s.get("search_query", "mystery evidence")),
                        "foley_type": str(s.get("foley_type", "none")),
                        "narration": str(s.get("narration", "")).strip(),
                        "attention_level": str(s.get("attention_level", "MEDIUM")).upper(),
                        "visual_role": str(s.get("visual_role", "BROLL")),
                        "beat_plan": s.get("beat_plan", []) if isinstance(s.get("beat_plan", []), list) else [],
                        "camera_motion": str(s.get("camera_motion", "slow_push")),
                        "transition_in": str(s.get("transition_in", "hard_cut")),
                        "transition_out": str(s.get("transition_out", "hard_cut")),
                        "graphic_intent": str(s.get("graphic_intent", "none")),
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
        """Gemini TTS with key rotation + differentiated 429/503 backoff.
        Never changes the user's local agy installation; this is only API retry logic.
        """
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
        total_attempts = max(6, len(CONFIG.gemini_keys) * 4)
        attempt = 0
        while attempt < total_attempts:
            key = CONFIG.gemini_keys[attempt % len(CONFIG.gemini_keys)]
            attempt += 1
            try:
                client = genai.Client(api_key=key)
                res = client.models.generate_content(
                    model=CONFIG.tts_model,
                    contents="[INSTRUCTION: Deep chilling narrator. Natural Arabic documentary delivery. Do not shorten the text.]\n" + text,
                    config=cfg,
                )
                part = res.candidates[0].content.parts[0]
                audio = part.inline_data.data
                mime = getattr(part.inline_data, "mime_type", "") or ""
                raw = base64.b64decode(audio) if isinstance(audio, str) else audio
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
                        raise RuntimeError(r.stderr[-700:])
                if is_valid_media(out_wav, 1000):
                    log.info(f"✅ Gemini TTS OK | attempt={attempt} | duration={probe_duration(out_wav):.1f}s")
                    time.sleep(8)
                    return True
            except Exception as e:
                msg = str(e)
                if "429" in msg or "RESOURCE_EXHAUSTED" in msg:
                    delay = min(60, 12 * (2 ** min(attempt - 1, 2)))
                    log.warning(f"⏳ Gemini TTS rate limit (429) | attempt={attempt}/{total_attempts} | sleep={delay}s")
                    time.sleep(delay)
                elif "503" in msg or "UNAVAILABLE" in msg:
                    delay = min(45, 8 * (2 ** min(attempt - 1, 2)))
                    log.warning(f"⏳ Gemini TTS unavailable (503) | attempt={attempt}/{total_attempts} | sleep={delay}s")
                    time.sleep(delay)
                else:
                    log.warning(f"⚠️ فشل مفتاح الصوت {attempt}/{total_attempts}: {msg[:350]}")
                    time.sleep(3)
        log.error("❌ استنفدت محاولات توليد الصوت بعد تدوير المفاتيح والـbackoff.")
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


def _normalize_subtitle_text(text: str) -> str:
    """Normalize Arabic punctuation/Unicode without changing the spoken words."""
    import unicodedata
    t = unicodedata.normalize("NFC", str(text or ""))
    replacements = {
        "\u00a0": " ", "\u200b": "", "\u200c": "", "\u200d": "",
        "\u2026": "…", "\u201c": "«", "\u201d": "»",
        "\u2018": "'", "\u2019": "'", "\u2013": "—", "\u2014": "—",
        "\u2212": "-", "\u00ad": "",
    }
    for a,b in replacements.items(): t=t.replace(a,b)
    # Remove control characters that can corrupt ASS events, but preserve Arabic shaping marks.
    t = "".join(ch for ch in t if not unicodedata.category(ch).startswith("C") or ch in "\n\t")
    return re.sub(r"[ \t]+", " ", t).strip()

def _ass_escape(text: str) -> str:
    # ASS uses braces for override tags; escape them so narration cannot become a tag.
    t = _normalize_subtitle_text(text)
    return t.replace("\\", "\\\\").replace("{", "\\{" ).replace("}", "\\}")


def _normalize_alignment_token(text: str) -> str:
    """Normalize a token only for script↔Whisper matching; never alter display text."""
    t = unicodedata.normalize("NFKC", str(text or ""))
    t = t.replace("ـ", "")
    # Arabic diacritics / Quranic marks: matching-only removal.
    t = "".join(ch for ch in t if not unicodedata.category(ch).startswith("M"))
    t = t.translate(str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ؤ": "و", "ئ": "ي", "ى": "ي",
        "ة": "ه",
        "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
        "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
    }))
    # Keep letters/numbers from Arabic, Latin and other scripts; discard punctuation.
    t = "".join(ch.lower() if (ch.isalnum() or '\u0600' <= ch <= '\u06ff') else " " for ch in t)
    return " ".join(t.split())


def _tokenize_script(narration: str) -> List[str]:
    """Whitespace-tokenize the original script so its exact wording remains the display source."""
    return [x for x in re.split(r"\s+", str(narration or "").strip()) if x]


def _align_original_script_to_whisper(narration: str, whisper_words, audio_duration: float):
    """Attach Whisper timing to the ORIGINAL script without replacing or shortening its text.

    Whisper is used only as a timing reference. Matching is fuzzy/sequence-based because
    Whisper may normalize punctuation, Arabic orthography, numbers, or occasionally omit a word.
    The subtitle text always comes from the original Gemini narration.
    """
    script_tokens = _tokenize_script(narration)
    clean_whisper = []
    for w in whisper_words or []:
        if not isinstance(w, dict):
            continue
        raw = str(w.get("word", "")).strip()
        if not raw:
            continue
        try:
            st = max(0.0, float(w.get("start", 0)))
            en = max(st + 0.04, float(w.get("end", st)))
        except Exception:
            continue
        norm = _normalize_alignment_token(raw)
        if not norm:
            continue
        clean_whisper.append({"word": raw, "norm": norm, "start": st, "end": en})

    if not script_tokens:
        return []

    # Build one normalized token per script token. SequenceMatcher gives robust matching
    # when Whisper changes punctuation or a few words while preserving the spoken order.
    script_norm = [_normalize_alignment_token(x) for x in script_tokens]
    whisper_norm = [x["norm"] for x in clean_whisper]
    matcher = difflib.SequenceMatcher(a=script_norm, b=whisper_norm, autojunk=False)
    mapped = [None] * len(script_tokens)

    for i1, j1, size in matcher.get_matching_blocks():
        if size <= 0:
            continue
        for k in range(size):
            mapped[i1 + k] = clean_whisper[j1 + k]

    # Interpolate timestamps for unmatched script tokens between neighboring matches.
    matched_indices = [i for i, v in enumerate(mapped) if v is not None]
    if matched_indices:
        # Prefix
        first = matched_indices[0]
        if first > 0:
            right = mapped[first]["start"]
            step = max(0.05, right / first)
            for i in range(first):
                st = max(0.0, i * step)
                en = min(right, max(st + 0.05, (i + 1) * step))
                mapped[i] = {"start": st, "end": en}

        # Gaps
        for left_i, right_i in zip(matched_indices, matched_indices[1:]):
            if right_i - left_i <= 1:
                continue
            left_end = mapped[left_i]["end"]
            right_start = mapped[right_i]["start"]
            span = max(0.05, right_start - left_end)
            count = right_i - left_i - 1
            step = span / (count + 1)
            for n, idx in enumerate(range(left_i + 1, right_i), start=1):
                st = left_end + step * (n - 1)
                en = left_end + step * n
                mapped[idx] = {"start": st, "end": max(st + 0.05, en)}

        # Suffix
        last = matched_indices[-1]
        if last < len(script_tokens) - 1:
            left = mapped[last]["end"]
            right = max(left + 0.05, audio_duration)
            count = len(script_tokens) - last - 1
            step = (right - left) / count
            for n, idx in enumerate(range(last + 1, len(script_tokens)), start=0):
                st = left + step * n
                en = left + step * (n + 1)
                mapped[idx] = {"start": st, "end": max(st + 0.05, en)}
    else:
        # Extremely unusual fallback: distribute the exact script across the full audio
        # duration proportionally to visible token length.
        weights = [max(1, len(_normalize_alignment_token(x))) for x in script_tokens]
        total = float(sum(weights)) or 1.0
        cursor = 0.0
        duration = max(0.1, audio_duration)
        for i, weight in enumerate(weights):
            st = cursor
            cursor += duration * weight / total
            mapped[i] = {"start": st, "end": max(st + 0.05, cursor)}

    result = []
    for token, timing in zip(script_tokens, mapped):
        if timing is None:
            continue
        st = max(0.0, float(timing["start"]))
        en = max(st + 0.05, float(timing["end"]))
        if audio_duration > 0:
            st = min(st, max(0.0, audio_duration - 0.05))
            en = min(max(en, st + 0.05), audio_duration)
        result.append({"word": token, "start": st, "end": en})
    return result


def _write_ass_subtitles(words, out_ass: Path, audio_duration: float):
    """Create RTL subtitles whose DISPLAY TEXT is the original narration.

    The `words` argument is already aligned to the original script. Whisper supplies only
    timing; it is never allowed to replace the script wording.
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

    if audio_duration > 0:
        for w in valid:
            w["start"] = min(w["start"], max(0.0, audio_duration - 0.05))
            w["end"] = min(max(w["end"], w["start"] + 0.05), audio_duration)

    groups=[]; current=[]
    MAX_WORDS=9; MAX_DURATION=3.2; MAX_CHARS=38
    hard_punct=re.compile(r"[.!؟?!؛:]$")
    soft_punct=re.compile(r"[,،]$")
    for w in valid:
        if not current:
            current=[w]; continue
        gap=w["start"]-current[-1]["end"]
        prospective=" ".join(x["word"] for x in current+[w])
        sentence_end=bool(hard_punct.search(current[-1]["word"]))
        soft_end=bool(soft_punct.search(current[-1]["word"]))
        should_break=(sentence_end or gap>=0.42 or len(current)>=MAX_WORDS or
                      (w["end"]-current[0]["start"]>MAX_DURATION) or
                      (len(prospective)>MAX_CHARS and len(current)>=3) or
                      (soft_end and len(current)>=4 and gap>=0.18))
        if should_break:
            groups.append(current); current=[w]
        else:
            current.append(w)
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
        if audio_duration > 0:
            end = min(end, audio_duration)
        if end <= start:
            continue
        lines.append(f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Arabic,,0,0,0,,{_ass_escape(text)}")

    out_ass.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
    return bool(groups)

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
            # IMPORTANT: the full narration is NEVER placed in Groq's optional `prompt`.
            # Groq uses that field only as a small contextual hint and limits it to 468 chars.
            # The complete narration remains the source-of-truth subtitle text below.
            # Whisper receives the FULL AUDIO and returns timing; it does not need the script.
            log.info("🛡️ Groq subtitle mode: full narration kept intact; optional prompt omitted. "
                     "Whisper supplies timing only.")
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
        whisper_words = payload.get("words") or []
        if not whisper_words:
            raise RuntimeError("Groq لم يُرجع word timestamps")

        audio_duration = probe_duration(audio_path)
        aligned_words = _align_original_script_to_whisper(narration, whisper_words, audio_duration)
        if not aligned_words:
            raise RuntimeError("تعذر ربط النص الأصلي بتوقيتات Whisper")

        # Keep Groq's raw response for debugging, plus the exact original script and
        # the timing map actually used to render subtitles.
        payload["subtitle_source_text"] = narration
        payload["subtitle_mode"] = "ORIGINAL_SCRIPT_WITH_WHISPER_TIMING"
        payload["aligned_script_words"] = aligned_words
        out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        ok = _write_ass_subtitles(aligned_words, out_ass, audio_duration)
        if not ok:
            raise RuntimeError("تعذر إنشاء ملف ASS من timestamps")
        log.info(f"📝 Subtitles OK | النص الأصلي كاملًا | {len(aligned_words)} كلمة | توقيتات Whisper | {out_ass.name}")
        return True
    except Exception as e:
        log.error(f"⚠️ فشل Groq subtitles: {e}")
        return False


def _escape_subtitle_path(path: Path) -> str:
    # FFmpeg subtitles filter escaping for Linux paths. GitHub runners use POSIX paths.
    p = str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return p


def _motion_filter(motion, dur, w=TARGET_W, h=TARGET_H):
    """Robust Ken-Burns filter. Avoids the fragile `t` variable that broke V24.2.
    zoompan officially supports `zoom`, `x`, `y`, `d`, `s`, and `fps`; we use the
    persistent `zoom`/`on` variables only. See FFmpeg zoompan docs.
    """
    m = str(motion or "slow_push").lower()
    # First create a safe oversized canvas. zoompan then emits one frame per input frame.
    pre = f"scale={int(w*1.14)}:{int(h*1.14)}:force_original_aspect_ratio=increase,crop={int(w*1.14)}:{int(h*1.14)}"
    if m in {"static", "none"}:
        return f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    if m in {"slow_pull", "pull_out"}:
        z = "if(eq(on,0),1.10,max(zoom-0.0012,1.0))"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif m in {"lateral_drift", "pan_right"}:
        z = "min(zoom+0.0005,1.06)"
        x = "max(0,min(iw-iw/zoom,(iw-iw/zoom)*on/1800))"
        y = "ih/2-(ih/zoom/2)"
    else:
        z = "min(zoom+0.0012,1.10)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    return f"{pre},zoompan=z='{z}':x='{x}':y='{y}':d=1:s={w}x{h}:fps={TARGET_FPS}"


def render_scene(media, is_vid, aud, out, dur, montage, subtitle_ass=None, directive=None, edit_bible=None):
    media_ok = is_valid_media(media, 1000) if is_vid else is_valid_visual(media, 10000)
    if not media_ok or not is_valid_media(aud, 1000): raise RuntimeError("Media/audio invalid before render")
    directive=directive or {}
    bible=edit_bible or _default_edit_bible()
    motion=str(directive.get("camera_motion","slow_push"))
    attention=str(directive.get("attention_level","MEDIUM")).upper()
    fx=",hue=s=0" if "BW" in str(montage).upper() else ",eq=contrast=1.08:saturation=0.92"
    if attention=="HIGH": fx += ",eq=gamma=1.02"
    subtitle_filter=""
    if subtitle_ass and Path(subtitle_ass).exists():
        sp=_escape_subtitle_path(Path(subtitle_ass))
        subtitle_filter=f",subtitles=filename='{sp}':force_style='FontName=Noto Sans Arabic,FontSize=62,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,Outline=1,Shadow=2,Alignment=2,MarginV=65'"
    if is_vid:
        # Video sources are never looped. We slow them slightly, normalize framing,
        # then hold the final frame when narration outlasts the source.
        vf0=f"setpts=PTS*1.08,scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H}{fx},fps={TARGET_FPS},tpad=stop_mode=clone:stop_duration={max(0.0,dur):.3f}"
        if subtitle_filter:
            vf=f"[0:v]{vf0}[base];[base]{subtitle_filter.lstrip(',')}[v]"
        else:
            vf=f"[0:v]{vf0}[v]"
        cmd=["ffmpeg","-y","-i",str(media),"-i",str(aud),"-filter_complex",vf,
             "-map","[v]","-map","1:a:0","-c:v","libx264","-preset","medium","-crf","18",
             "-r",str(TARGET_FPS),"-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-ar",str(TARGET_AR),"-ac","2",
             "-af","loudnorm=I=-16:TP=-1.5:LRA=11","-t",f"{max(.5,dur):.3f}","-movflags","+faststart",str(out)]
    else:
        vf=_motion_filter(motion,dur)+fx+",format=yuv420p"
        if subtitle_filter: vf+=subtitle_filter
        cmd=["ffmpeg","-y","-loop","1","-i",str(media),"-i",str(aud),"-filter_complex",f"[0:v]{vf}[v]",
             "-map","[v]","-map","1:a:0","-c:v","libx264","-preset","medium","-crf","18","-r",str(TARGET_FPS),
             "-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-ar",str(TARGET_AR),"-ac","2",
             "-af","loudnorm=I=-16:TP=-1.5:LRA=11","-t",f"{max(.5,dur):.3f}","-movflags","+faststart",str(out)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=900)
    if r.returncode!=0 and not is_vid:
        # Deterministic emergency fallback: never lose a scene because of an expression parser issue.
        log.warning("⚠️ Zoompan فشل؛ إعادة الرندر بحركة ثابتة آمنة.")
        safe_vf=f"scale={TARGET_W}:{TARGET_H}:force_original_aspect_ratio=increase,crop={TARGET_W}:{TARGET_H}{fx},fps={TARGET_FPS},format=yuv420p"
        if subtitle_filter:
            safe_complex=f"[0:v]{safe_vf}[base];[base]{subtitle_filter.lstrip(',')}[v]"
        else:
            safe_complex=f"[0:v]{safe_vf}[v]"
        safe_cmd=["ffmpeg","-y","-loop","1","-i",str(media),"-i",str(aud),"-filter_complex",safe_complex,
                  "-map","[v]","-map","1:a:0","-c:v","libx264","-preset","medium","-crf","18",
                  "-r",str(TARGET_FPS),"-pix_fmt","yuv420p","-c:a","aac","-b:a","192k","-ar",str(TARGET_AR),"-ac","2",
                  "-af","loudnorm=I=-16:TP=-1.5:LRA=11","-t",f"{max(.5,dur):.3f}","-movflags","+faststart",str(out)]
        r=subprocess.run(safe_cmd,capture_output=True,text=True,timeout=900)
    if r.returncode!=0: raise RuntimeError(r.stderr[-3000:])
    actual=probe_duration(out)
    if actual<.5 or not is_valid_media(out,50000): raise RuntimeError(f"Rendered scene invalid: duration={actual}")
    log.info(f"🎬 Render 24.2 OK | {out.name} | {actual:.2f}s | motion={motion} | attention={attention}")

def clean_old_scene_cache(pfx):
    for suffix in [".mp4", ".wav", ".m4a", ".mp3", ".jpg", ".pcm", "_media.mp4", "_media.jpg", "_foley.mp3", "_best_backup.mp4", "_best_backup.jpg"]:
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


def upload_youtube(vid, thumbnail=None):
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
    edit_bible = _default_edit_bible()
    if CONFIG.paths.edit_bible.exists():
        try: edit_bible = normalize_edit_bible(json.loads(CONFIG.paths.edit_bible.read_text(encoding="utf-8")))
        except Exception: pass
    try:
        script = director.plan_documentary()
        # V24.2 may create the Edit Bible during planning; reload it before rendering.
        if CONFIG.paths.edit_bible.exists():
            try:
                edit_bible = normalize_edit_bible(json.loads(CONFIG.paths.edit_bible.read_text(encoding="utf-8")))
            except Exception as e:
                log.warning(f"⚠️ تعذر إعادة تحميل Edit Bible بعد التخطيط: {e}")
        # اختبار حقيقي متعدد المشاهد: نأخذ أول 7 مشاهد من الخطة نفسها،
        # وليس 7 مشاهد مولدة بصورة مستقلة. هذا يحافظ على استمرارية المخرج واللغة البصرية.
        script = script[:TEST_SCENE_COUNT]
        for n, sc in enumerate(script, 1):
            sc["scene_num"] = n
        if len(script) < TEST_SCENE_COUNT:
            raise RuntimeError(f"الخطة أعادت {len(script)} مشاهد فقط؛ مطلوب {TEST_SCENE_COUNT}.")
        test_manifest = CONFIG.paths.base / "manifests" / "7scene_test_plan.json"
        test_manifest.parent.mkdir(parents=True, exist_ok=True)
        test_manifest.write_text(json.dumps({
            "engine": ENGINE_VERSION,
            "topic": CONFIG.topic,
            "scene_count": len(script),
            "edit_bible": edit_bible,
            "scenes": script,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info(f"🧪 7-SCENE TEST: سيتم تنفيذ {len(script)} مشاهد مترابطة فقط.")
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
            render_scene(c_media, c_media.suffix.lower() == ".mp4", c_mp3, c_mp4, dur, montage_style, c_ass if subtitles_ok else None, directive=scene, edit_bible=edit_bible)
            clips.append(c_mp4)
            total_expected += probe_duration(c_mp4)
            for b in CONFIG.paths.cache.glob(pfx.name + "_best_backup*"):
                try: b.unlink()
                except Exception: pass
        except Exception as e:
            log.error(f"⚠️ فشل رندر المشهد {i+1}: {e}")

    final_vid = CONFIG.paths.base / "final_documentary.mp4"
    if len(clips) != TEST_SCENE_COUNT:
        raise RuntimeError(f"❌ الاختبار غير مكتمل: تم رندر {len(clips)}/{TEST_SCENE_COUNT} مشاهد فقط.")

    try:
        final_duration = concat_final(clips, final_vid)
        log.info(f"📐 مجموع مدد المشاهد: {total_expected/60:.2f} دقيقة")
        log.info(f"📐 مدة الفيلم بعد الدمج: {final_duration/60:.2f} دقيقة")
        if final_duration < 240:
            raise RuntimeError(f"❌ مدة اختبار 7 مشاهد قصيرة جداً: {final_duration:.1f}s؛ المطلوب 4 دقائق على الأقل.")
        if not final_vid.exists() or final_vid.stat().st_size < 100000:
            raise RuntimeError("❌ final_documentary.mp4 غير صالح أو غير موجود.")
        if final_duration > total_expected * 1.15 and total_expected > 10:
            log.error("🚨 تحذير: مدة الفيلم أكبر بكثير من مجموع مدد المشاهد؛ تم اكتشاف مشكلة زمنية.")
        write_otio_timeline(clips, CONFIG.paths.timeline, script)
        thumbnail = generate_thumbnail(final_vid)
        if thumbnail: log.info(f"🖼️ Thumbnail: {thumbnail}")
        # اختبار محلي/GitHub فقط: لا رفع إلى Drive أو YouTube.
        log.info("🧪 TEST MODE: تم تعطيل Google Drive وYouTube upload.")
    except Exception as e:
        log.error(f"❌ فشل إخراج الفيلم النهائي: {e}")


if __name__ == "__main__":
    main()
