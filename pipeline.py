#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Professional Documentary Pipeline
- Research with Gemini + Google Search grounding
- Evidence-aware scene planning
- NEVER silently replaces real evidence with AI
- Gemini 3.8 Flash TTS with per-scene delivery style
- Arabic subtitle shaping
- Wikimedia Commons / Pexels media
- AI reenactments explicitly labeled
- Resumable scene rendering
- Source/license manifest
- Optional YouTube + Google Drive upload
- No music and no SFX by default
"""

import os
import re
import json
import time
import base64
import hashlib
import logging
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import arabic_reshaper
from bidi.algorithm import get_display
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# -----------------------------
# Configuration
# -----------------------------

ROOT = Path(".")
CACHE = ROOT / "data" / "cache"
SOURCES = ROOT / "data" / "sources"
MANIFESTS = ROOT / "data" / "manifests"
OUTPUT = ROOT / "output"
ASSETS = ROOT / "assets"
FONT_DIR = ASSETS / "fonts"

for d in (CACHE, SOURCES, MANIFESTS, OUTPUT, ASSETS, FONT_DIR):
    d.mkdir(parents=True, exist_ok=True)

TOPIC = os.getenv(
    "VIDEO_TOPIC",
    "حادثة ممر دياتلوف: اللغز الذي حيّر العالم"
).strip()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "").strip()

GEMINI_RESEARCH_MODEL = os.getenv("GEMINI_RESEARCH_MODEL", "gemini-3.8-flash")
GEMINI_TTS_MODEL = os.getenv("GEMINI_TTS_MODEL", "gemini-3.8-flash-tts")
GEMINI_TTS_VOICE = os.getenv("GEMINI_TTS_VOICE", "Charon")

SCENE_COUNT = int(os.getenv("SCENE_COUNT", "42"))
MIN_REAL_SCENES = float(os.getenv("MIN_REAL_SCENES", "0.55"))
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "3"))

ENABLE_YOUTUBE = os.getenv("ENABLE_YOUTUBE", "false").lower() == "true"
ENABLE_DRIVE = os.getenv("ENABLE_DRIVE", "false").lower() == "true"

# User explicitly requested no music.
ENABLE_MUSIC = False
ENABLE_SFX = False

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY غير موجود في GitHub Secrets.")

client = genai.Client(api_key=GEMINI_API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)
log = logging.getLogger("documentary")


# -----------------------------
# Utilities
# -----------------------------

def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256_text(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def atomic_write_json(path, data):
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    tmp.replace(path)


def run(cmd, check=True, capture=False):
    result = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.PIPE if capture else subprocess.DEVNULL
    )
    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed ({result.returncode}): {' '.join(map(str, cmd))}\n"
            f"{result.stderr[-3000:] if capture else ''}"
        )
    return result


def ffprobe_duration(path):
    result = run([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path)
    ], capture=True)
    return float(result.stdout.strip())


def get_arabic_font():
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p

    try:
        out = subprocess.check_output(
            ["find", "/usr/share/fonts", "-type", "f",
             "(", "-iname", "*Arabic*.ttf", "-o", "-iname", "*NotoSans*.ttf", ")"],
            text=True
        ).splitlines()
        if out:
            return out[0]
    except Exception:
        pass

    raise RuntimeError("لم يتم العثور على خط عربي مناسب.")


ARABIC_FONT = get_arabic_font()


def escape_ffmpeg_text(value):
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("[", "\\[")
        .replace("]", "\\]")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def write_arabic_text(text, path, max_chars=46):
    words = text.split()
    lines, current = [], []
    width = 0

    for word in words:
        new_width = width + len(word) + (1 if current else 0)
        if current and new_width > max_chars:
            lines.append(" ".join(current))
            current = [word]
            width = len(word)
        else:
            current.append(word)
            width = new_width

    if current:
        lines.append(" ".join(current))

    shaped = []
    for line in lines:
        shaped.append(get_display(arabic_reshaper.reshape(line)))

    Path(path).write_text("\n".join(shaped), encoding="utf-8")


# -----------------------------
# Research
# -----------------------------

RESEARCH_CACHE = CACHE / f"{sha256_text(TOPIC)[:16]}_research.json"
SCENES_CACHE = CACHE / f"{sha256_text(TOPIC)[:16]}_scenes.json"


def extract_grounding_sources(response):
    sources = []

    # GenerateContent responses expose grounding metadata on candidates.
    try:
        candidates = getattr(response, "candidates", []) or []
        for candidate in candidates:
            gm = getattr(candidate, "grounding_metadata", None)
            if not gm:
                continue

            chunks = getattr(gm, "grounding_chunks", None) or []
            for chunk in chunks:
                web = getattr(chunk, "web", None)
                if not web:
                    continue
                uri = getattr(web, "uri", None)
                title = getattr(web, "title", None)
                if uri:
                    sources.append({
                        "url": uri,
                        "title": title or uri,
                        "source_type": "web_grounding"
                    })
    except Exception as exc:
        log.warning("تعذر استخراج بعض مصادر Grounding: %s", exc)

    # Deduplicate
    unique = {}
    for s in sources:
        unique[s["url"]] = s
    return list(unique.values())


def research_topic():
    if RESEARCH_CACHE.exists():
        log.info("استئناف: تم العثور على بحث سابق.")
        return json.loads(RESEARCH_CACHE.read_text(encoding="utf-8"))

    prompt = f"""
أنت باحث وثائقي محترف. ابحث في الويب عن الموضوع التالي:

{TOPIC}

المطلوب:
1. أنشئ ملف بحث factual research وليس سيناريو.
2. افصل بين:
   - حقائق موثقة.
   - ادعاءات أو نظريات متنازع عليها.
   - معلومات غير مؤكدة.
3. أعط الأولوية للمصادر الأولية، المؤسسات الرسمية، الأرشيفات، الصحف الموثوقة،
   والكتب/المؤسسات الأكاديمية عند توفرها.
4. لا تخترع أي وثيقة أو صورة أو اقتباس.
5. لكل حقيقة، اذكر المصدر إن أمكن.
6. ركز على المعلومات التي يمكن تحويلها إلى مشاهد بصرية حقيقية.
7. اللغة العربية الفصحى.

أعد JSON فقط بالشكل:
{{
  "topic": "...",
  "facts": [
    {{
      "claim": "...",
      "status": "verified|disputed|uncertain",
      "sources": [
        {{"title": "...", "url": "..."}}
      ]
    }}
  ],
  "visual_evidence_targets": [
    {{
      "description": "...",
      "search_query": "...",
      "preferred_source": "primary|archive|wikimedia|news|generic"
    }}
  ]
}}
"""

    tool = types.Tool(google_search=types.GoogleSearch())

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_RESEARCH_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[tool],
                    temperature=0.2
                )
            )

            text = response.text.strip()
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"^```\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            data = json.loads(text)
            data["_grounding_sources"] = extract_grounding_sources(response)
            data["_generated_at"] = utc_now()

            atomic_write_json(RESEARCH_CACHE, data)
            return data

        except Exception as exc:
            log.warning("فشل البحث (%d/3): %s", attempt + 1, exc)
            time.sleep(4 * (attempt + 1))

    raise RuntimeError("تعذر إنشاء البحث الموثق.")


# -----------------------------
# Scene planning
# -----------------------------

def build_scenes(research):
    if SCENES_CACHE.exists():
        log.info("استئناف: تم العثور على مخطط المشاهد.")
        return json.loads(SCENES_CACHE.read_text(encoding="utf-8"))

    research_text = json.dumps(research, ensure_ascii=False)

    prompt = f"""
أنت مخرج وثائقي استقصائي ومخطط مونتاج.

الموضوع:
{TOPIC}

بيانات البحث:
{research_text}

أنشئ {SCENE_COUNT} مشهدًا تقريبًا لفيلم مدته 9-12 دقيقة.

قواعد صارمة:
- لا تصف أي شيء بأنه "دليل حقيقي" إلا إذا كان لدينا هدف مصدر حقيقي واضح.
- media_type يجب أن يكون واحدًا من:
  "primary_source", "archival", "stock", "ai_reenactment".
- primary_source/archival يتطلب search_query محددًا جدًا.
- ai_reenactment ليس دليلًا ولا يجوز أن يحاكي وثيقة حقيقية مع الادعاء بأنها أصلية.
- stock يستخدم فقط للقطات عامة: شارع، مطر، آلة كاتبة، سيارة، طبيعة، إلخ.
- حاول جعل 55% على الأقل من المشاهد primary_source أو archival عندما تسمح الأدلة.
- إذا لم تتوفر أدلة بصرية كافية، استخدم ai_reenactment أو stock بدل اختلاق دليل.
- لا تستخدم موسيقى ولا مؤثرات صوتية.
- كل narration بين 2 و4 جمل، ومناسب تقريبًا لـ 12-20 ثانية.
- استخدم العربية الفصحى الطبيعية غير المتكلفة.
- تجنب التشكيل الكامل؛ ضع التشكيل فقط عندما يمنع التباس النطق.
- speech_style يجب أن يكون وصفًا قصيرًا لأداء الصوت، وليس نصًا سيُقرأ.
- أضف inline_tags عند الحاجة فقط مثل <short pause> أو <breath>.
- لا تضع تعليمات مثل "قل بحزن" داخل narration؛ ضعها في speech_style.
- camera_move واحد من:
  zoom_in, zoom_out, pan_left, pan_right, tilt_down.
- search_query للصور الحقيقية يجب أن تكون بالإنجليزية.
- لكل مشهد حقل evidence_claim. إذا كان المشهد AI أو stock اجعله null.
- لا تستخدم أسماء مصادر أو وثائق من خيالك.

أخرج JSON Array فقط:
[
  {{
    "scene_num": 1,
    "narration": "...",
    "speech_style": "...",
    "media_type": "archival",
    "evidence_claim": "...",
    "search_query": "...",
    "ai_prompt": null,
    "camera_move": "zoom_in"
  }}
]
"""

    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_RESEARCH_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.35
                )
            )

            text = response.text.strip()
            text = re.sub(r"^```json\s*", "", text)
            text = re.sub(r"^```\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

            scenes = json.loads(text)

            if not isinstance(scenes, list) or len(scenes) < 5:
                raise ValueError("مخطط المشاهد غير صالح.")

            for i, scene in enumerate(scenes, 1):
                scene["scene_num"] = i
                scene.setdefault("media_type", "stock")
                scene.setdefault("evidence_claim", None)
                scene.setdefault("search_query", "")
                scene.setdefault("ai_prompt", "")
                scene.setdefault("camera_move", "zoom_in")
                scene.setdefault("speech_style", (
                    "natural, restrained investigative documentary narration, "
                    "clear Modern Standard Arabic, calm authority"
                ))

                if scene["media_type"] in {"primary_source", "archival"}:
                    if not scene.get("search_query") or not scene.get("evidence_claim"):
                        scene["media_type"] = "ai_reenactment"
                        scene["evidence_claim"] = None

            atomic_write_json(SCENES_CACHE, scenes)
            return scenes

        except Exception as exc:
            log.warning("فشل تخطيط المشاهد (%d/3): %s", attempt + 1, exc)
            time.sleep(3 * (attempt + 1))

    raise RuntimeError("تعذر إنشاء مخطط المشاهد.")


# -----------------------------
# Wikimedia evidence retrieval
# -----------------------------

def fetch_wikimedia(query, output_path):
    """
    Returns a source dict only when an actual Wikimedia image is downloaded.
    It does NOT claim that the image proves the narration; that distinction
    is recorded in the manifest.
    """
    headers = {
        "User-Agent": "ProfessionalDocumentaryPipeline/1.0"
    }

    api = "https://commons.wikimedia.org/w/api.php"
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": 8,
        "prop": "imageinfo",
        "iiprop": "url|extmetadata",
        "iiurlwidth": 1920,
        "format": "json"
    }

    try:
        r = requests.get(api, params=params, headers=headers, timeout=15)
        r.raise_for_status()
        pages = r.json().get("query", {}).get("pages", {})

        for page in pages.values():
            info = page.get("imageinfo", [])
            if not info:
                continue

            item = info[0]
            url = item.get("thumburl") or item.get("url")
            if not url or url.lower().endswith(".svg"):
                continue

            raw = requests.get(url, headers=headers, timeout=20)
            if raw.status_code != 200 or len(raw.content) < 15000:
                continue

            raw_path = Path(str(output_path) + ".raw")
            raw_path.write_bytes(raw.content)

            if sanitize_image(raw_path, output_path):
                try:
                    raw_path.unlink()
                except Exception:
                    pass

                meta = item.get("extmetadata", {})

                def meta_value(key):
                    value = meta.get(key, {})
                    return value.get("value") if isinstance(value, dict) else None

                return {
                    "source_type": "wikimedia_commons",
                    "title": page.get("title", ""),
                    "url": item.get("descriptionurl") or url,
                    "direct_url": url,
                    "license": meta_value("LicenseShortName"),
                    "artist": meta_value("Artist"),
                    "credit": meta_value("Credit"),
                    "retrieved_at": utc_now(),
                }

    except Exception as exc:
        log.warning("Wikimedia failed for %r: %s", query, exc)

    return None


def sanitize_image(raw_path, clean_path):
    try:
        run([
            "ffmpeg", "-y",
            "-i", str(raw_path),
            "-vf",
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,format=yuv420p",
            "-frames:v", "1",
            str(clean_path)
        ])
        return Path(clean_path).exists() and Path(clean_path).stat().st_size > 3000
    except Exception:
        return False


# -----------------------------
# Pexels
# -----------------------------

def fetch_pexels_video(query, output_path):
    if not PEXELS_API_KEY:
        return None

    headers = {"Authorization": PEXELS_API_KEY}
    url = "https://api.pexels.com/videos/search"
    params = {
        "query": query,
        "per_page": 8,
        "orientation": "landscape"
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()

        for video in r.json().get("videos", []):
            files = video.get("video_files", [])
            files = sorted(
                files,
                key=lambda x: abs((x.get("width") or 0) - 1920)
                         + abs((x.get("height") or 0) - 1080)
            )

            if not files:
                continue

            link = files[0].get("link")
            if not link:
                continue

            stream = requests.get(link, stream=True, timeout=30)
            if stream.status_code != 200:
                continue

            with open(output_path, "wb") as f:
                for chunk in stream.iter_content(1024 * 1024):
                    if chunk:
                        f.write(chunk)

            if Path(output_path).stat().st_size > 50000:
                return {
                    "source_type": "pexels_video",
                    "title": video.get("url", ""),
                    "url": video.get("url", link),
                    "license": "Pexels License",
                    "retrieved_at": utc_now()
                }

    except Exception as exc:
        log.warning("Pexels video failed for %r: %s", query, exc)

    return None


def fetch_pexels_photo(query, output_path):
    if not PEXELS_API_KEY:
        return None

    headers = {"Authorization": PEXELS_API_KEY}
    url = "https://api.pexels.com/v1/search"
    params = {
        "query": query,
        "per_page": 8,
        "orientation": "landscape"
    }

    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        r.raise_for_status()

        for photo in r.json().get("photos", []):
            src = photo.get("src", {})
            link = src.get("large2x") or src.get("original")
            if not link:
                continue

            raw = requests.get(link, timeout=20)
            if raw.status_code != 200 or len(raw.content) < 15000:
                continue

            raw_path = Path(str(output_path) + ".raw")
            raw_path.write_bytes(raw.content)

            if sanitize_image(raw_path, output_path):
                raw_path.unlink(missing_ok=True)
                return {
                    "source_type": "pexels_photo",
                    "title": photo.get("alt", ""),
                    "url": photo.get("url", link),
                    "license": "Pexels License",
                    "photographer": photo.get("photographer"),
                    "retrieved_at": utc_now()
                }

    except Exception as exc:
        log.warning("Pexels photo failed for %r: %s", query, exc)

    return None


# -----------------------------
# AI reenactment
# -----------------------------

def generate_ai_image(prompt, output_path):
    encoded = urllib.parse.quote(
        f"{prompt}, cinematic documentary reenactment, "
        "photorealistic, no text, no watermark"
    )
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        "?width=1920&height=1080&nologo=true&nofeed=true&model=flux"
    )

    for attempt in range(2):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=45) as response:
                data = response.read()

            if len(data) > 10000:
                Path(output_path).write_bytes(data)
                if sanitize_image(output_path, output_path):
                    return {
                        "source_type": "ai_reenactment",
                        "title": "AI-generated reenactment",
                        "url": None,
                        "license": "Generated by pipeline",
                        "retrieved_at": utc_now()
                    }
        except Exception as exc:
            log.warning("AI image attempt %d failed: %s", attempt + 1, exc)
            time.sleep(3)

    raise RuntimeError("فشل توليد إعادة التمثيل بالذكاء الاصطناعي.")


# -----------------------------
# TTS
# -----------------------------

def clean_tts_text(text):
    # Gemini 3.8 treats transcript as verbatim.
    # Only keep supported momentary tags.
    text = re.sub(r"\[(.*?)\]", r"\1", text)
    return text.strip()


def generate_tts(text, style, output_wav):
    text = clean_tts_text(text)

    if not text:
        raise ValueError("النص الصوتي فارغ.")

    # GenerateContent API: supported by Gemini 3.8 Flash TTS.
    # The transcript is separate from speech_metadata.
    response = client.models.generate_content(
        model=GEMINI_TTS_MODEL,
        contents=[{
            "role": "user",
            "parts": [{
                "text": text,
                "speech_metadata": {
                    "style": style or (
                        "natural, restrained investigative documentary narration, "
                        "clear Modern Standard Arabic, warm mature voice, "
                        "calm authority, subtle emotional variation, "
                        "natural pauses and breathing, never theatrical"
                    )
                }
            }]
        }],
        config={
            "response_modalities": ["AUDIO"],
            "speech_config": {
                "voice_config": {
                    "voice": GEMINI_TTS_VOICE
                }
            }
        }
    )

    part = response.candidates[0].content.parts[0]
    data = part.inline_data.data

    if isinstance(data, str):
        data = base64.b64decode(data)

    Path(output_wav).write_bytes(data)

    if Path(output_wav).stat().st_size < 1000:
        raise RuntimeError("TTS returned an unexpectedly small file.")

    # Normalize to broadcast-ish narration level, mono 24k WAV.
    normalized = str(output_wav) + ".normalized.wav"
    run([
        "ffmpeg", "-y",
        "-i", str(output_wav),
        "-ac", "1",
        "-ar", "24000",
        "-af", "loudnorm=I=-16:TP=-1.5:LRA=8",
        normalized
    ])
    Path(normalized).replace(output_wav)


# -----------------------------
# Rendering
# -----------------------------

def render_image_scene(image, audio, out, duration, move, evidence=False):
    fps = 25
    frames = max(1, int(duration * fps))

    if move == "zoom_out":
        zoom = "max(1.0,1.18-0.0007*on)"
        xy = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
    elif move == "pan_left":
        zoom = "1.15"
        xy = (
            f"x='max(0,min(iw-iw/zoom,(1-on/{frames})*(iw-iw/zoom)))':"
            "y='ih/2-(ih/zoom/2)'"
        )
    elif move == "pan_right":
        zoom = "1.15"
        xy = (
            f"x='max(0,min(iw-iw/zoom,(on/{frames})*(iw-iw/zoom)))':"
            "y='ih/2-(ih/zoom/2)'"
        )
    elif move == "tilt_down":
        zoom = "1.15"
        xy = (
            f"x='iw/2-(iw/zoom/2)':"
            f"y='max(0,min(ih-ih/zoom,(on/{frames})*(ih-ih/zoom)))'"
        )
    else:
        zoom = "min(1.18,1+0.0007*on)"
        xy = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

    badge = ""
    if evidence:
        badge = (
            ",drawbox=x=45:y=40:w=420:h=55:color=black@0.78:t=fill,"
            f"drawtext=fontfile='{escape_ffmpeg_text(ARABIC_FONT)}':"
            "text='أرشيف/مصدر بصري — راجع المصادر':"
            "fontcolor=white:fontsize=21:x=65:y=57"
        )

    filter_chain = (
        "[0:v]scale=3840:2160,"
        f"zoompan=z='{zoom}':{xy}:d={frames}:s=1920x1080:fps={fps},"
        "eq=contrast=1.04:brightness=-0.01,"
        "vignette=PI/4.5"
        f"{badge}[v]"
    )

    run([
        "ffmpeg", "-y",
        "-loop", "1", "-i", str(image),
        "-i", str(audio),
        "-filter_complex", filter_chain,
        "-map", "[v]", "-map", "1:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        str(out)
    ])


def render_video_scene(video, audio, out, duration):
    filter_chain = (
        "[0:v]scale=1920:1080:"
        "force_original_aspect_ratio=increase,"
        "crop=1920:1080,setsar=1,"
        "eq=contrast=1.04:brightness=-0.01,"
        "vignette=PI/4.5[v]"
    )

    run([
        "ffmpeg", "-y",
        "-stream_loop", "-1", "-i", str(video),
        "-i", str(audio),
        "-filter_complex", filter_chain,
        "-map", "[v]", "-map", "1:a",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "19",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        str(out)
    ])


def render_scene(index, scene):
    scene_id = int(scene["scene_num"])
    scene_dir = OUTPUT / f"scene_{scene_id:03d}"
    scene_dir.mkdir(parents=True, exist_ok=True)

    final_scene = scene_dir / "scene.mp4"
    manifest_file = scene_dir / "manifest.json"

    if final_scene.exists() and final_scene.stat().st_size > 50000 and manifest_file.exists():
        log.info("⏩ المشهد %03d موجود — استئناف.", scene_id)
        return json.loads(manifest_file.read_text(encoding="utf-8"))

    narration = scene["narration"]
    style = scene.get("speech_style", "")
    media_type = scene.get("media_type", "stock")
    query = scene.get("search_query", "")

    audio = scene_dir / "narration.wav"
    if not audio.exists():
        log.info("🎙️ TTS المشهد %03d", scene_id)
        generate_tts(narration, style, audio)

    duration = ffprobe_duration(audio)

    source = None
    visual = None

    # IMPORTANT: real/archival media can never silently fall back to AI.
    if media_type in {"primary_source", "archival"}:
        visual = scene_dir / "visual.jpg"
        source = fetch_wikimedia(query, visual)

        if source is None and PEXELS_API_KEY:
            source = fetch_pexels_photo(query, visual)

        if source is None:
            raise RuntimeError(
                f"المشهد {scene_id}: طُلب مصدر حقيقي/أرشيفي "
                f"لكن لم يتم العثور على أصل بصري. لن يتم استبداله بـAI."
            )

        # Important distinction:
        # successful retrieval != proof that it matches the claim.
        source["evidence_claim"] = scene.get("evidence_claim")
        source["verification_note"] = (
            "Retrieved from a named source. Human/source-level verification "
            "is still required before presenting the image as proof of the claim."
        )

        render_image_scene(
            visual, audio, final_scene, duration,
            scene.get("camera_move", "zoom_in"),
            evidence=True
        )

    elif media_type == "video":
        visual = scene_dir / "visual.mp4"
        source = fetch_pexels_video(query, visual)
        if source is None:
            raise RuntimeError(
                f"المشهد {scene_id}: تعذر العثور على فيديو Stock."
            )
        render_video_scene(visual, audio, final_scene, duration)

    elif media_type == "ai_reenactment":
        visual = scene_dir / "visual.jpg"
        source = generate_ai_image(
            scene.get("ai_prompt") or query or "historical documentary reenactment",
            visual
        )
        source["label_required"] = True
        render_image_scene(
            visual, audio, final_scene, duration,
            scene.get("camera_move", "zoom_in"),
            evidence=False
        )

    else:
        visual = scene_dir / "visual.jpg"
        source = fetch_pexels_photo(query or "cinematic documentary",
                                    visual)
        if source is None:
            # Generic stock failure is allowed to become AI reenactment,
            # but it remains labeled AI.
            source = generate_ai_image(
                scene.get("ai_prompt") or query or "cinematic documentary scene",
                visual
            )
            source["label_required"] = True

        render_image_scene(
            visual, audio, final_scene, duration,
            scene.get("camera_move", "zoom_in"),
            evidence=False
        )

    scene_manifest = {
        "scene_num": scene_id,
        "narration": narration,
        "speech_style": style,
        "media_type": media_type,
        "evidence_claim": scene.get("evidence_claim"),
        "search_query": query,
        "source": source,
        "duration_seconds": round(duration, 3),
        "rendered_at": utc_now(),
        "pipeline_version": "2.0"
    }

    atomic_write_json(manifest_file, scene_manifest)
    return scene_manifest


# -----------------------------
# Final assembly
# -----------------------------

def concat_scenes(manifests):
    concat_file = OUTPUT / "concat.txt"
    final_output = OUTPUT / "final_documentary.mp4"

    with concat_file.open("w", encoding="utf-8") as f:
        for m in manifests:
            path = OUTPUT / f"scene_{int(m['scene_num']):03d}" / "scene.mp4"
            if not path.exists():
                raise RuntimeError(f"ملف المشهد مفقود: {path}")
            f.write(f"file '{path.resolve()}'\n")

    run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(final_output)
    ])

    return final_output


def build_episode_manifest(research, scenes, rendered):
    real_count = sum(
        1 for s in scenes
        if s.get("media_type") in {"primary_source", "archival"}
    )

    data = {
        "pipeline_version": "2.0",
        "topic": TOPIC,
        "generated_at": utc_now(),
        "settings": {
            "scene_count": len(scenes),
            "real_or_archival_planned": real_count,
            "real_or_archival_ratio": real_count / max(1, len(scenes)),
            "music": False,
            "sfx": False,
            "tts_model": GEMINI_TTS_MODEL,
            "tts_voice": GEMINI_TTS_VOICE
        },
        "research_sources": research.get("_grounding_sources", []),
        "scenes": rendered
    }

    path = MANIFESTS / f"{sha256_text(TOPIC)[:16]}_manifest.json"
    atomic_write_json(path, data)
    return path


# -----------------------------
# Optional publishing
# -----------------------------

def upload_youtube(video):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh = os.getenv("YOUTUBE_REFRESH_TOKEN")

    if not (client_id and client_secret and refresh):
        log.info("YouTube: بيانات الاعتماد غير موجودة — تم التخطي.")
        return None

    creds = Credentials(
        None,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )

    service = build("youtube", "v3", credentials=creds)

    body = {
        "snippet": {
            "title": f"تحقيق وثائقي: {TOPIC}",
            "description": (
                f"وثائقي استقصائي حول: {TOPIC}\n\n"
                "تم إعداد قائمة مصادر لكل مشهد ضمن ملفات المشروع."
            ),
            "tags": ["وثائقي", "تحقيقات", "غموض", "تاريخ"],
            "categoryId": "27"
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False
        }
    }

    media = MediaFileUpload(
        str(video),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024
    )

    request = service.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media
    )

    response = None
    while response is None:
        _, response = request.next_chunk()

    video_id = response["id"]
    log.info("YouTube uploaded: https://youtu.be/%s", video_id)
    return video_id


def upload_drive(video):
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh = os.getenv("DRIVE_REFRESH_TOKEN")

    if not (client_id and client_secret and refresh):
        log.info("Drive: بيانات الاعتماد غير موجودة — تم التخطي.")
        return None

    creds = Credentials(
        None,
        refresh_token=refresh,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )

    service = build("drive", "v3", credentials=creds)

    q = (
        "name='AI_Documentaries' and "
        "mimeType='application/vnd.google-apps.folder' and trashed=false"
    )

    folders = service.files().list(q=q, spaces="drive").execute().get("files", [])

    if folders:
        parent_id = folders[0]["id"]
    else:
        parent_id = service.files().create(
            body={
                "name": "AI_Documentaries",
                "mimeType": "application/vnd.google-apps.folder"
            },
            fields="id"
        ).execute()["id"]

    metadata = {
        "name": (
            f"Documentary_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.mp4"
        ),
        "parents": [parent_id]
    }

    media = MediaFileUpload(
        str(video),
        mimetype="video/mp4",
        resumable=True,
        chunksize=10 * 1024 * 1024
    )

    result = service.files().create(
        body=metadata,
        media_body=media,
        fields="id,webViewLink"
    ).execute()

    log.info("Drive uploaded: %s", result.get("webViewLink"))
    return result.get("webViewLink")


# -----------------------------
# Main
# -----------------------------

def main():
    log.info("🎬 بدء الإنتاج: %s", TOPIC)
    log.info("🔤 الخط: %s", ARABIC_FONT)
    log.info("🎙️ TTS: %s / %s", GEMINI_TTS_MODEL, GEMINI_TTS_VOICE)
    log.info("🎵 Music: OFF | SFX: OFF")

    research = research_topic()
    scenes = build_scenes(research)

    planned_real = sum(
        1 for s in scenes
        if s.get("media_type") in {"primary_source", "archival"}
    )
    ratio = planned_real / max(1, len(scenes))

    log.info(
        "📚 نسبة المشاهد الأرشيفية/الأولية المخططة: %.1f%%",
        ratio * 100
    )

    rendered = []

    # Limited parallelism avoids hammering APIs and keeps memory reasonable.
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {
            pool.submit(render_scene, i, scene): scene
            for i, scene in enumerate(scenes)
        }

        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            log.info("✅ اكتمل المشهد %03d", result["scene_num"])

    rendered = sorted(results, key=lambda x: x["scene_num"])

    # Ensure every planned real scene actually remained real/archival.
    for item in rendered:
        if item["media_type"] in {"primary_source", "archival"}:
            if not item.get("source"):
                raise RuntimeError(
                    f"المشهد {item['scene_num']} معلن كأرشيفي بلا مصدر."
                )

    final_output = concat_scenes(rendered)
    manifest_path = build_episode_manifest(research, scenes, rendered)

    log.info("🎞️ الفيديو النهائي: %s", final_output)
    log.info("📋 Manifest: %s", manifest_path)

    if ENABLE_YOUTUBE:
        upload_youtube(final_output)

    if ENABLE_DRIVE:
        upload_drive(final_output)

    log.info("🏁 اكتمل الإنتاج بنجاح.")


if __name__ == "__main__":
    main()
 
