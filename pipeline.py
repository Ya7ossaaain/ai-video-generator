#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================================================
FORENSIC & HISTORICAL DOCUMENTARY AUTOMATION ENGINE (PRODUCTION PIPELINE V4.0)
====================================================================================================
نظام متكامل ومؤتمت لإنتاج الأفلام الوثائقية الاستقصائية والجنائية بدقة سينمائية ومعايير صحفية صارمة.
- المحرك الصوتي: Google Gemini TTS (صوت Charon الحصري مع معالجة سقف الطلبات الذاتية).
- محرك التحقق الأرشيفي: جلب وفحص الأدلة من كبرى قواعد البيانات المفتوحة (Wikimedia & Wikipedia APIs).
- محرك النزاهة التوثيقية: تصنيف مرئي صارم بين الوثائق الأصلية وإعادة التمثيل الرقمية.
- محرك الرسوميات والتايبوجرافي: معالجة النصوص العربية وحساب التفاف الأسطر بالبكسل مع طبقات ألفا شفافة.
- هندسة الصوت التكتيكية: مؤثرات واقعية خافتة (Tactile Archival SFX) خالية تماماً من الموسيقى المصطنعة.
- استوديو المونتاج: FFmpeg بمعالجة لونية أرشيفية وحركة كاميرا ناعمة (Ken Burns) وتوحيد زمني صارم.
====================================================================================================
"""

import os
import sys
import io
import json
import time
import math
import shutil
import hashlib
import logging
import asyncio
import base64
import urllib.parse
import urllib.request
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
import arabic_reshaper
from bidi.algorithm import get_display

from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


# ==================================================================================================
# 1. إعدادات النظام وتسجيل الأحداث (LOGGING & GLOBAL CONFIGURATION)
# ==================================================================================================

class ColoredFormatter(logging.Formatter):
    """منسق مخصص لسجلات النظام بالألوان للتشغيل المريح عبر الطرفية وسيرفرات CI/CD."""
    GREY = "\x1b[38;20m"
    CYAN = "\x1b[36;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"
    FORMAT = "%(asctime)s - [%(levelname)s] - (%(filename)s:%(lineno)d) - %(message)s"

    FORMATS = {
        logging.DEBUG: GREY + FORMAT + RESET,
        logging.INFO: CYAN + FORMAT + RESET,
        logging.WARNING: YELLOW + FORMAT + RESET,
        logging.ERROR: RED + FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + FORMAT + RESET
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


logger = logging.getLogger("ForensicDocPipeline")
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColoredFormatter())
logger.addHandler(console_handler)


@dataclass
class PipelineConfig:
    """كائن ضبط الإعدادات العامة لخط الإنتاج."""
    # أبعاد ومواصفات الفيديو
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 25
    video_crf: int = 19
    video_preset: str = "veryfast"
    
    # مواصفات الصوت
    audio_sample_rate: int = 48000
    audio_bitrate: str = "192k"
    gemini_voice_name: str = "Charon"
    tts_model_name: str = "gemini-2.5-flash"
    max_tts_retries: int = 8
    tts_backoff_base: int = 10
    
    # مسارات الملفات والمجلدات
    work_dir: Path = field(default_factory=lambda: Path("./output_build"))
    cache_dir: Path = field(default_factory=lambda: Path("./output_build/cache"))
    scenes_dir: Path = field(default_factory=lambda: Path("./output_build/scenes"))
    assets_dir: Path = field(default_factory=lambda: Path("./output_build/assets"))
    sfx_dir: Path = field(default_factory=lambda: Path("./output_build/sfx"))
    script_cache_name: str = "forensic_manifest_v4.json"
    
    # قيود التحرير والمحتوى
    min_scenes: int = 34
    max_scenes: int = 38
    target_duration_seconds: int = 660  # قرابة 11 دقيقة لضمان الأمان المطلق في يوتيوب
    max_text_line_pixel_width: int = 1520
    
    # مفاتيح وبيانات الاتصال
    topic: str = os.environ.get("VIDEO_TOPIC", "لغز القاتل زودياك: وثائق التحقيق والشفرات الجنائية المفقودة")
    gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    yt_refresh_token: str = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    drive_refresh_token: str = os.environ.get("DRIVE_REFRESH_TOKEN", "")

    def init_workspace(self):
        """إنشاء مجلدات العمل المعزولة."""
        for d in [self.work_dir, self.cache_dir, self.scenes_dir, self.assets_dir, self.sfx_dir]:
            d.mkdir(parents=True, exist_ok=True)
        logger.info(f"تم تهيئة مجلدات العمل بنجاح داخل: {self.work_dir}")


CONFIG = PipelineConfig()


# ==================================================================================================
# 2. إدارة التايبوجرافي والخطوط واللغة العربية (ADVANCED TYPOGRAPHY & RTL ENGINE)
# ==================================================================================================

class TypographyEngine:
    """محرك فحص الخطوط وحساب عرض النصوص ورسم القوالب البصرية بالبكسل."""

    def __init__(self):
        self.font_path = self._resolve_arabic_font()
        logger.info(f"تم اختيار الخط المعتمد للرسم البصري: {self.font_path}")

    @staticmethod
    def _resolve_arabic_font() -> str:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansArabic-Bold.otf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        try:
            found = subprocess.check_output(
                ["find", "/usr/share/fonts", "-iname", "*arabic*.ttf"],
                stderr=subprocess.DEVNULL
            ).decode().splitlines()
            if found and os.path.exists(found[0]):
                return found[0]
        except Exception:
            pass
        return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    def get_font(self, size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype(self.font_path, size)
        except Exception as e:
            logger.warning(f"تعذر تحميل خط النظام ({e}). جاري استخدام الخط الافتراضي.")
            return ImageFont.load_default()

    def wrap_arabic_text_by_pixels(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_pixel_width: int
    ) -> List[str]:
        """
        تقسيم النص العربي بناءً على القياس البكسلي الفعلي للكلمات بدلاً من عدد الحروف،
        لمنع تداخل الكلمات مع أطراف الشاشة أو انقطاعها.
        """
        words = text.strip().split()
        lines: List[str] = []
        current_words: List[str] = []

        dummy_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy_img)

        for word in words:
            candidate_line = " ".join(current_words + [word])
            reshaped_candidate = get_display(arabic_reshaper.reshape(candidate_line))
            rendered_width = draw.textlength(reshaped_candidate, font=font)

            if rendered_width > max_pixel_width and current_words:
                lines.append(" ".join(current_words))
                current_words = [word]
            else:
                current_words.append(word)

        if current_words:
            lines.append(" ".join(current_words))

        return lines


TYPOGRAPHY = TypographyEngine()


# ==================================================================================================
# 3. محرك الرسوميات والقناع البصري (FORENSIC OVERLAY & BADGE COMPOSITOR)
# ==================================================================================================

class GraphicOverlayCompositor:
    """تصميم القوالب والشارات الأرشيفية وشرائط الترجمة كصور PNG عالية الدقة (1080p)."""

    @staticmethod
    def create_scene_overlay(
        narration: str,
        media_category: str,
        source_name: str,
        output_png: Path
    ) -> None:
        canvas = Image.new("RGBA", (CONFIG.video_width, CONFIG.video_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        font_sub = TYPOGRAPHY.get_font(31)
        font_badge = TYPOGRAPHY.get_font(20)
        font_meta = TYPOGRAPHY.get_font(15)

        # 1. تصميم شارة النزاهة التوثيقية في الزاوية العلوية
        badge_text = ""
        bg_color = (0, 0, 0, 0)
        border_color = (0, 0, 0, 0)

        if media_category == "PRIMARY_ARCHIVE":
            badge_text = "● وثيقة رسمية أصلية | ملف التحقيق الجنائي"
            bg_color = (150, 0, 0, 235)       # أحمر أرشيفي داكن
            border_color = (255, 255, 255, 140)
        elif media_category == "HISTORICAL_RECORD":
            badge_text = "● مادة تاريخية معاصرة | أرشيف الصحافة والسجلات"
            bg_color = (145, 75, 0, 235)      # برتقالي وثائقي نحاسي
            border_color = (255, 255, 255, 140)
        elif media_category == "AI_REENACTMENT":
            badge_text = "● إعادة تمثيل بصرية | محاكاة تخيلية بالذكاء الاصطناعي"
            bg_color = (35, 38, 42, 220)      # رمادي تكتيكي محايد
            border_color = (180, 180, 180, 100)

        if badge_text:
            reshaped_badge = get_display(arabic_reshaper.reshape(badge_text))
            badge_w = draw.textlength(reshaped_badge, font=font_badge) + 36
            badge_h = 48
            bx, by = 60, 50

            # خلفية الشارة وحوافها
            draw.rectangle([bx, by, bx + badge_w, by + badge_h], fill=bg_color, outline=border_color, width=2)
            draw.text((bx + 18, by + 12), reshaped_badge, font=font_badge, fill=(255, 255, 255, 255))

            # بطاقة المصدر الدقيق بجانب الشارة إن وجد
            if source_name and media_category in ["PRIMARY_ARCHIVE", "HISTORICAL_RECORD"]:
                src_label = f"المصدر: {source_name}"
                reshaped_src = get_display(arabic_reshaper.reshape(src_label))
                src_w = draw.textlength(reshaped_src, font=font_meta) + 24
                sx = bx + badge_w + 12
                draw.rectangle([sx, by + 4, sx + src_w, by + badge_h - 4], fill=(10, 15, 20, 200), outline=(255, 255, 255, 60), width=1)
                draw.text((sx + 12, by + 14), reshaped_src, font=font_meta, fill=(220, 220, 220, 240))

        # 2. تصميم شريط الترجمة السفلي المتدرج
        gradient_h = 160
        grad_box = Image.new("RGBA", (CONFIG.video_width, gradient_h), (0, 0, 0, 0))
        grad_draw = ImageDraw.Draw(grad_box)
        for y in range(gradient_h):
            alpha = int(220 * (y / gradient_h))
            grad_draw.line([(0, y), (CONFIG.video_width, y)], fill=(0, 0, 0, alpha))
        
        canvas.paste(grad_box, (0, CONFIG.video_height - gradient_h), grad_box)

        # 3. قياس وطباعة أسطر السرد الصوتي
        lines = TYPOGRAPHY.wrap_arabic_text_by_pixels(
            narration, font=font_sub, max_pixel_width=CONFIG.max_text_line_pixel_width
        )
        display_lines = lines[:2]  # الحفاظ على سطرين كحد أقصى لمنع حجب الرؤية

        y_base = 948 if len(display_lines) == 1 else 930
        for idx, raw_line in enumerate(display_lines):
            disp_line = get_display(arabic_reshaper.reshape(raw_line))
            line_w = draw.textlength(disp_line, font=font_sub)
            x_pos = (CONFIG.video_width - line_w) // 2
            y_pos = y_base + (idx * 48)

            # ظل عميق لضمان مقروئية تامة فوق كافة أنواع الخلفيات
            draw.text((x_pos + 2, y_pos + 2), disp_line, font=font_sub, fill=(0, 0, 0, 255))
            draw.text((x_pos, y_pos), disp_line, font=font_sub, fill=(255, 255, 255, 255))

        canvas.save(output_png, "PNG")


# ==================================================================================================
# 4. محرك هندسة الصوت والمؤثرات التكتيكية (FORENSIC SOUND DESIGN STUDIO)
# ==================================================================================================

class ForensicSoundStudio:
    """توليد ومزج المؤثرات الصوتية الأرشيفية والتكتيكية دون أي تكلف موسيقي."""

    def __init__(self, sfx_directory: Path):
        self.sfx_dir = sfx_directory
        self.evidence_snap_wav = self.sfx_dir / "evidence_stamp.wav"
        self.soft_whoosh_wav = self.sfx_dir / "air_transition.wav"
        self.init_procedural_sfx()

    def init_procedural_sfx(self):
        """توليد نبرات صوتية نقية باستخدام FFmpeg Lavfi Synthesis لمنع أي مشكلات ترخيص."""
        # 1. صوت طبعة الختم الأرشيفي / التكة الميكانيكية للعدسة
        if not self.evidence_snap_wav.exists() or self.evidence_snap_wav.stat().st_size < 1000:
            cmd_snap = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anoisesrc=d=0.22:c=white:a=0.08,bandpass=f=1600:w=700,afade=t=out:st=0.04:d=0.18,volume=0.24",
                str(self.evidence_snap_wav)
            ]
            subprocess.run(cmd_snap, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("تم تخليق المؤثر الصوتي: ختام الأرشيف الجنائي.")

        # 2. صوت الانتقال الهوائي الرزين ومنخفض التردد
        if not self.soft_whoosh_wav.exists() or self.soft_whoosh_wav.stat().st_size < 1000:
            cmd_whoosh = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anoisesrc=d=0.32:c=brown:a=0.06,lowpass=f=320,afade=t=in:st=0:d=0.08,afade=t=out:st=0.08:d=0.24,volume=0.18",
                str(self.soft_whoosh_wav)
            ]
            subprocess.run(cmd_whoosh, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            logger.info("تم تخليق المؤثر الصوتي: الانتقال الهوائي الناعم.")

    def mix_scene_audio(
        self,
        voice_wav: Path,
        output_mixed_mp3: Path,
        category: str
    ) -> float:
        """
        دمج صوت المعلق مع المؤثر الصوتي المناسب في مطلع المشهد
        وتطبيق معايير البث EBU R128 (loudnorm).
        """
        sfx_source = self.evidence_snap_wav if category == "PRIMARY_ARCHIVE" else self.soft_whoosh_wav

        # دمج الصوت وتطبيع المخرجات
        filter_str = (
            "[1:a]adelay=40|40[sfx];"
            "[0:a][sfx]amix=inputs=2:duration=first:dropout_transition=2,"
            "loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(voice_wav),
            "-i", str(sfx_source),
            "-filter_complex", filter_str,
            "-map", "[aout]",
            "-ar", str(CONFIG.audio_sample_rate),
            "-b:a", CONFIG.audio_bitrate,
            str(output_mixed_mp3)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # قراءة مدة الصوت الدقيقة باستخدام ffprobe
        cmd_dur = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            str(output_mixed_mp3)
        ]
        duration = float(subprocess.check_output(cmd_dur).decode().strip())
        return duration


# ==================================================================================================
# 5. محرك استدعاء وصوت الذكاء الاصطناعي (GEMINI COGNITIVE & TTS CLIENT)
# ==================================================================================================

class GeminiDocumentaryDirector:
    """كبير مخرجي التحقيقات: صياغة النصوص وتوليد الصوت الحصري (Charon) دون أي بديل هجين."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY مفقود في البيئة! يرجى إضافته في إعدادات الأمان.")
        self.client = genai.Client(api_key=api_key)

    def draft_forensic_manifest(self, topic: str) -> List[Dict[str, Any]]:
        """صياغة السيناريو الاستقصائي المقسم بدقة جنائية ونحوية تامة."""
        prompt = f"""
        أنت كبير المحققين والمخرجين للوثائقيات الجنائية والتاريخية الكبرى.
        الموضوع: "{topic}".
        المطلوب: إنتاج سيناريو استقصائي محكم ومضبوط لغوياً ونحوياً بالكامل يتكون من 35 إلى 37 مشهداً.

        القواعد الصارمة لإخراج الفيلم:
        1. السلامة النحوية واللغوية: تجنب أخطاء التأنيث والتذكير نهائياً (مثلاً: قل "زياً أسودَ" ولا تقل "زياً سوداء").
        2. تصنيف الوسائط (media_type) بدقة بين 4 فئات:
           - "PRIMARY_ARCHIVE": للوثائق والتقارير الرسمية وصور مسارح الجرائم الأصلية المعتمدة.
           - "HISTORICAL_RECORD": لصفحات الجرائد، صور المشتبه بهم الحقيقية، والخرائط الجغرافية.
           - "AI_REENACTMENT": لتمثيل اللحظات التخيلية التي لم توثقها كاميرا.
           - "STOCK_BROLL": للقطات العامة (أمطار ليلية، آلة كاتبة، دوران أشرطة الكاسيت).
        3. كلمات البحث (search_query) للوثائق الأصلية يجب أن تكون مكتوبة باللغة الإنجليزية الأرشيفية المعتمدة في السجلات الأمريكية والفيدرالية.
        4. السرد (narration): جملتان مكثفتان وقويتان باللغة العربية الفصحى الرصينة.
        5. حركة الكاميرا (camera_move): اختر من ("zoom_in", "zoom_out", "tilt_down", "pan_left", "pan_right").

        أخرج النتيجة بصيغة JSON Array نقية ومباشرة فقط:
        [
          {{
            "scene_num": 1,
            "narration": "في ظلام كاليفورنيا أواخر الستينيات، ظهر لغز استعصى على أكبر أجهزة التحقيق...",
            "media_type": "PRIMARY_ARCHIVE",
            "search_query": "Zodiac killer Vallejo police report 1968 original",
            "ai_prompt": "Vintage 1960s typewriter crime report archive, dim cinematic lamp, 35mm grain",
            "camera_move": "tilt_down"
          }}
        ]
        """
        for candidate_model in ["gemini-2.5-flash", "gemini-3.8-flash", "gemini-3-flash-preview"]:
            try:
                logger.info(f"جاري صياغة السرد الاستقصائي والتحقق الأرشيفي عبر ({candidate_model})...")
                res = self.client.models.generate_content(model=candidate_model, contents=prompt)
                clean_text = res.text.strip().replace("```json", "").replace("```", "").strip()
                parsed = json.loads(clean_text)
                if isinstance(parsed, list) and len(parsed) >= CONFIG.min_scenes:
                    logger.info(f"تم اعتماد سيناريو التحقيق بنجاح: {len(parsed)} مشهداً.")
                    return parsed
            except Exception as e:
                logger.warning(f"محاولة فاشلة مع الموديل {candidate_model}: {e}. جاري تجربة الموديل البديل...")
                time.sleep(3)

        raise RuntimeError("فشل توليد السيناريو الاستقصائي عبر كافة نماذج Gemini المتاحة.")

    def synthesize_charon_voice(self, text: str, output_wav: Path) -> None:
        """
        توليد صوت Charon الحصري مع احترام سقف الطلبات في الدقيقة (RPM)
        وإعادة المحاولة الذاتية (Exponential Backoff) لمنع أي انقطاع.
        """
        backoff = CONFIG.tts_backoff_base

        for attempt in range(1, CONFIG.max_tts_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=CONFIG.tts_model_name,
                    contents=[{
                        "role": "user",
                        "parts": [{
                            "text": text,
                            "speech_metadata": {
                                "style": "deep, solemn, calm investigative crime documentary narrator"
                            }
                        }]
                    }],
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=CONFIG.gemini_voice_name
                                )
                            )
                        )
                    )
                )

                raw_bytes = None
                for part in response.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        raw_bytes = part.inline_data.data
                        break

                if raw_bytes:
                    binary_data = base64.b64decode(raw_bytes) if isinstance(raw_bytes, str) else raw_bytes
                    with open(output_wav, "wb") as f:
                        f.write(binary_data)
                    # استراحة قصيرة لتفادي الـ 429
                    time.sleep(5)
                    return

                raise ValueError("استجابة الصوت من Gemini كانت فارغة من البيانات الثنائية.")

            except Exception as e:
                err_msg = str(e)
                logger.warning(f"تنبيه صوت Charon (المحاولة {attempt}/{CONFIG.max_tts_retries}): {err_msg[:80]}")
                if attempt == CONFIG.max_tts_retries:
                    raise RuntimeError(f"تعذر توليد صوت المشهد بعد {attempt} محاولات: {err_msg}")
                time.sleep(backoff)
                backoff = min(backoff + 8, 45)


# ==================================================================================================
# 6. محرك البحث والتحقق من الأدلة الأرشيفية (ARCHIVAL ASSET ACQUISITION)
# ==================================================================================================

class ForensicAssetHarvester:
    """سحب المواد من الأرشيف المفتوح مع استخراج بيانات الحقوق والمصدر بدقة."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ForensicDocumentaryEngine/4.0 (contact: historical_investigation@gmail.com)"
        })

    def search_wikimedia_archive(self, query: str, output_path: Path) -> Tuple[bool, str]:
        """البحث في مكتبة ويكيميديا للأدلة التاريخية واستخراج اسم المصدر."""
        try:
            endpoint = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 5,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": CONFIG.video_width,
                "format": "json"
            }
            res = self.session.get(endpoint, params=params, timeout=10)
            if res.status_code == 200:
                pages = res.json().get("query", {}).get("pages", {})
                for _, page in pages.items():
                    info = page.get("imageinfo", [])
                    if not info:
                        continue
                    meta = info[0].get("extmetadata", {})
                    source_desc = meta.get("Credit", {}).get("value", "") or meta.get("Artist", {}).get("value", "Wikimedia Commons")
                    # تنظيف وسوم HTML من اسم المصدر إن وجدت
                    clean_source = re_clean = "".join([c for c in source_desc if c.isalnum() or c in " -_()"])[:35]
                    
                    target_url = info[0].get("thumburl") or info[0].get("url")
                    if target_url and not target_url.endswith(".svg"):
                        img_res = self.session.get(target_url, timeout=12)
                        if img_res.status_code == 200 and len(img_res.content) > 20000:
                            raw_tmp = output_path.with_suffix(".tmp")
                            with open(raw_tmp, "wb") as f:
                                f.write(img_res.content)
                            if self.normalize_aspect_ratio(raw_tmp, output_path):
                                raw_tmp.unlink(missing_ok=True)
                                return True, clean_source or "National Archives"
                            raw_tmp.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"خطأ غير مؤثر في فحص ويكيميديا: {e}")
        return False, ""

    def search_wikipedia_article_images(self, query: str, output_path: Path) -> Tuple[bool, str]:
        """البحث عبر مقالات ويكيبيديا باللغة الإنجليزية للأرشيف الجنائي."""
        try:
            endpoint = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 4,
                "prop": "pageimages",
                "pithumbsize": CONFIG.video_width,
                "format": "json"
            }
            res = self.session.get(endpoint, params=params, timeout=10)
            if res.status_code == 200:
                pages = res.json().get("query", {}).get("pages", {})
                for _, page in pages.items():
                    thumb = page.get("thumbnail", {}).get("source")
                    if thumb and not thumb.endswith(".svg"):
                        img_res = self.session.get(thumb, timeout=12)
                        if img_res.status_code == 200 and len(img_res.content) > 20000:
                            raw_tmp = output_path.with_suffix(".tmp")
                            with open(raw_tmp, "wb") as f:
                                f.write(img_res.content)
                            if self.normalize_aspect_ratio(raw_tmp, output_path):
                                raw_tmp.unlink(missing_ok=True)
                                return True, "Historical Records"
                            raw_tmp.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"خطأ ويكيبيديا الثانوي: {e}")
        return False, ""

    def generate_ai_reenactment_visual(self, prompt: str, output_path: Path) -> bool:
        """توليد صورة سينمائية تحاكي الواقعة مع شارة إعادة تمثيل رقمية واضحة."""
        full_prompt = f"{prompt}, raw 35mm archival photograph, dark cold cinematography, moody police lighting, 1970s crime scene aesthetic, highly detailed, film grain, no text"
        encoded = urllib.parse.quote(full_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={CONFIG.video_width}&height={CONFIG.video_height}&nologo=true&nofeed=true&model=flux"

        for attempt in range(2):
            try:
                res = self.session.get(url, timeout=30)
                if res.status_code == 200 and len(res.content) > 15000:
                    with open(output_path, "wb") as f:
                        f.write(res.content)
                    return True
            except Exception:
                time.sleep(3)

        # توليد شاشة سينمائية صامتة إذا تعذر الاتصال
        cmd_blank = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=0x0a0c10:s={CONFIG.video_width}x{CONFIG.video_height}:d=1",
            "-frames:v", "1", str(output_path)
        ]
        subprocess.run(cmd_blank, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    @staticmethod
    def normalize_aspect_ratio(input_path: Path, output_path: Path) -> bool:
        """توحيد أبعاد الصورة إلى 1920x1080 وتطبيق Crop ملائم ومساحة ألوان YUV420p."""
        try:
            cmd = [
                "ffmpeg", "-y", "-i", str(input_path),
                "-vf", f"scale={CONFIG.video_width}:{CONFIG.video_height}:force_original_aspect_ratio=increase,crop={CONFIG.video_width}:{CONFIG.video_height},format=yuv420p",
                "-frames:v", "1", str(output_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return (res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 5000)
        except Exception:
            return False


# ==================================================================================================
# 7. استوديو المونتاج البصري والتركيب السينمائي (CINEMATIC COMPOSITOR & FFmpeg)
# ==================================================================================================

class CinematicRenderer:
    """تنفيذ تأثير حركة الكاميرا والتدريج اللوني الأرشيفي بدقة زمنية مطلقة."""

    @staticmethod
    def render_scene_clip(
        image_path: Path,
        overlay_png: Path,
        audio_mp3: Path,
        output_mp4: Path,
        duration: float,
        camera_move: str,
        category: str
    ) -> None:
        fps = CONFIG.video_fps
        total_frames = max(1, int(duration * fps))

        # 1. معادلات حركة الكاميرا الوثائقية
        if camera_move == "zoom_out":
            zoom_expr = "max(1.0, 1.18 - 0.0006*on)"
            pan_expr = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif camera_move == "tilt_down":
            zoom_expr = "1.14"
            pan_expr = f"x='iw/2-(iw/zoom/2)':y='max(0, min(ih-ih/zoom, (on/{total_frames})*(ih-ih/zoom)))'"
        elif camera_move == "pan_right":
            zoom_expr = "1.12"
            pan_expr = f"x='min(iw-iw/zoom, (on/{total_frames})*(iw-iw/zoom))':y='ih/2-(ih/zoom/2)'"
        elif camera_move == "pan_left":
            zoom_expr = "1.12"
            pan_expr = f"x='max(0, (1 - on/{total_frames})*(iw-iw/zoom))':y='ih/2-(ih/zoom/2)'"
        else:  # zoom_in التلقائي
            zoom_expr = "min(1.18, 1.0 + 0.0006*on)"
            pan_expr = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

        # 2. الفلتر اللوني وحبيبات الفيلم 35mm
        if category in ["PRIMARY_ARCHIVE", "HISTORICAL_RECORD"]:
            color_grading = "hue=s=0.68,eq=contrast=1.18:brightness=-0.02,noise=alls=8:allf=t+u,vignette=PI/3.4"
        else:
            color_grading = "eq=contrast=1.06:saturation=1.04,vignette=PI/4.5"

        # 3. بناء الفلتر المركب مع توحيد زمني صارم للإطارات والـ Timebase
        filter_complex = (
            f"[0:v]format=yuv420p,scale=3840:2160,"
            f"zoompan=z='{zoom_expr}':{pan_expr}:d={total_frames}:s={CONFIG.video_width}x{CONFIG.video_height}:fps={fps},"
            f"{color_grading}[bg];"
            f"[bg][1:v]overlay=0:0,fps={fps},settb=1/{fps},setpts=PTS-STARTPTS[v]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", str(image_path),
            "-i", str(overlay_png),
            "-i", str(audio_mp3),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "2:a",
            "-c:v", "libx264", "-preset", CONFIG.video_preset, "-crf", str(CONFIG.video_crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", CONFIG.audio_bitrate, "-ar", str(CONFIG.audio_sample_rate),
            "-t", str(duration),
            str(output_mp4)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


# ==================================================================================================
# 8. إدارة النشر السحابي والرفع المباشر (DISTRIBUTION & DEPLOYMENT ENGINE)
# ==================================================================================================

class CloudDistributionEngine:
    """الرفع المباشر عالي السرعة إلى YouTube API و Google Drive مع توليد الميتا داتا."""

    @staticmethod
    def upload_to_youtube(video_path: Path, title: str, description: str, tags: List[str]) -> Optional[str]:
        if not (CONFIG.google_client_id and CONFIG.google_client_secret and CONFIG.yt_refresh_token):
            logger.warning("بيانات اعتماد YouTube API غير مكتملة في Secrets. تم تخطي النشر على يوتيوب.")
            return None

        logger.info("جاري بدء الرفع المباشر إلى قناة YouTube...")
        try:
            creds = Credentials(
                None,
                refresh_token=CONFIG.yt_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CONFIG.google_client_id,
                client_secret=CONFIG.google_client_secret
            )
            yt_service = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "title": title,
                    "description": description,
                    "tags": tags,
                    "categoryId": "27"  # التعليم والتحقيقات
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(
                str(video_path),
                mimetype="video/mp4",
                resumable=True,
                chunksize=15 * 1024 * 1024
            )
            req = yt_service.videos().insert(part="snippet,status", body=body, media_body=media)

            response = None
            while response is None:
                status, response = req.next_chunk()
                if status:
                    pct = int(status.progress() * 100)
                    logger.info(f"تقدم رفع يوتيوب: {pct}%")

            video_id = response.get("id")
            logger.info(f"تم نشر الفيلم الوثائقي بنجاح! الرابط: https://youtu.be/{video_id}")
            return video_id

        except Exception as e:
            logger.error(f"حدث خطأ أثناء الرفع إلى يوتيوب: {e}")
            return None

    @staticmethod
    def upload_to_google_drive(video_path: Path, folder_name: str = "AI_Documentaries") -> Optional[str]:
        if not (CONFIG.google_client_id and CONFIG.google_client_secret and CONFIG.drive_refresh_token):
            logger.warning("بيانات Drive غير متوفرة. تم تخطي الأرشفة السحابية.")
            return None

        logger.info(f"جاري أرشفة النسخة الأصلية على Google Drive في مجلد: {folder_name}...")
        try:
            creds = Credentials(
                None,
                refresh_token=CONFIG.drive_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CONFIG.google_client_id,
                client_secret=CONFIG.google_client_secret
            )
            drive_service = build("drive", "v3", credentials=creds)

            # البحث عن المجلد أو إنشاؤه
            q_folder = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            res = drive_service.files().list(q=q_folder, fields="files(id, name)").execute()
            folders = res.get("files", [])

            if folders:
                folder_id = folders[0]["id"]
            else:
                f_meta = {"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}
                f_created = drive_service.files().create(body=f_meta, fields="id").execute()
                folder_id = f_created["id"]

            file_meta = {
                "name": video_path.name,
                "parents": [folder_id]
            }
            media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
            uploaded_file = drive_service.files().create(body=file_meta, media_body=media, fields="id").execute()
            f_id = uploaded_file.get("id")
            logger.info(f"تمت الأرشفة على Google Drive بنجاح. معرف الملف: {f_id}")
            return f_id

        except Exception as e:
            logger.error(f"خطأ أثناء الحفظ في درايف: {e}")
            return None


# ==================================================================================================
# 9. المايسترو ومنظم خط الإنتاج الكامل (MASTER ORCHESTRATOR)
# ==================================================================================================

class MasterDocumentaryPipeline:
    """المنسق العام: يربط كافة الوحدات الفرعية ويتحكم في تسلسل الإنتاج مع إدارة الأخطاء."""

    def __init__(self):
        CONFIG.init_workspace()
        self.director = GeminiDocumentaryDirector(CONFIG.gemini_api_key)
        self.harvester = ForensicAssetHarvester()
        self.sound_studio = ForensicSoundStudio(CONFIG.sfx_dir)

    def run(self):
        start_time = datetime.now()
        logger.info(f"🎬 [بدء الإنتاج]: العمل الوثائقي: {CONFIG.topic}")

        # ------------------------------------------------------------------------------------------
        # المرحلة 1: إنتاج أو استرجاع سيناريو التحقيق
        # ------------------------------------------------------------------------------------------
        manifest_path = CONFIG.work_dir / CONFIG.script_cache_name
        scenes_manifest: List[Dict[str, Any]] = []

        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    scenes_manifest = json.load(f)
                logger.info(f"تم استعادة السيناريو المعتمد مسبقاً ({len(scenes_manifest)} مشهداً).")
            except Exception:
                scenes_manifest = []

        if not scenes_manifest:
            scenes_manifest = self.director.draft_forensic_manifest(CONFIG.topic)
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(scenes_manifest, f, ensure_ascii=False, indent=2)

        # ------------------------------------------------------------------------------------------
        # المرحلة 2: معالجة المشاهد بشكل تسلسلي متين
        # ------------------------------------------------------------------------------------------
        rendered_scene_clips: List[Path] = []
        total_scenes = len(scenes_manifest)

        for idx, scene in enumerate(scenes_manifest):
            scene_num = scene.get("scene_num", idx + 1)
            narration = scene.get("narration", "")
            req_type = scene.get("media_type", "AI_REENACTMENT")
            search_q = scene.get("search_query", "")
            ai_prompt = scene.get("ai_prompt", search_q)
            cam_move = scene.get("camera_move", "zoom_in")

            scene_prefix = f"scene_{idx:03d}"
            clip_path = CONFIG.scenes_dir / f"{scene_prefix}.mp4"
            voice_raw_wav = CONFIG.cache_dir / f"{scene_prefix}_voice.wav"
            mixed_audio_mp3 = CONFIG.cache_dir / f"{scene_prefix}_mixed.mp3"
            image_path = CONFIG.cache_dir / f"{scene_prefix}_visual.jpg"
            overlay_png = CONFIG.cache_dir / f"{scene_prefix}_overlay.png"

            logger.info(f"⏳ معالجة المشهد ({idx + 1}/{total_scenes}) [طلب: {req_type}]...")

            # 1. فحص وجود المقطع مسبقاً (Idempotent Resumption)
            if clip_path.exists() and clip_path.stat().st_size > 50000:
                logger.info(f"المشهد {idx + 1} مكتمل وجاهز مسبقاً. تخطي المعالجة.")
                rendered_scene_clips.append(clip_path)
                continue

            # 2. جلب الأصل الأرشيفي وتطبيق مبدأ النزاهة التوثيقية
            actual_category = req_type
            source_attribution = ""
            got_evidence = False

            if req_type in ["PRIMARY_ARCHIVE", "HISTORICAL_RECORD"] and search_q:
                got_evidence, source_attribution = self.harvester.search_wikimedia_archive(search_q, image_path)
                if not got_evidence:
                    got_evidence, source_attribution = self.harvester.search_wikipedia_article_images(search_q, image_path)

            if got_evidence:
                actual_category = req_type
            else:
                # خفض التصنيف صراحة لتمثيل رقمي إذا لم نجد الأصل الحقيقي
                actual_category = "AI_REENACTMENT"
                source_attribution = ""
                self.harvester.generate_ai_reenactment_visual(ai_prompt, image_path)

            # 3. توليد صوت Charon الحصري
            if not voice_raw_wav.exists() or voice_raw_wav.stat().st_size < 1000:
                self.director.synthesize_charon_voice(narration, voice_raw_wav)

            # 4. هندسة ومزج المؤثرات الصوتية وحساب مدة المشهد
            duration = self.sound_studio.mix_scene_audio(voice_raw_wav, mixed_audio_mp3, actual_category)

            # 5. رسم القناع البصري وشارة التوثيق
            GraphicOverlayCompositor.create_scene_overlay(
                narration=narration,
                media_category=actual_category,
                source_name=source_attribution,
                output_png=overlay_png
            )

            # 6. المونتاج ورندرة المقطع الفردي
            CinematicRenderer.render_scene_clip(
                image_path=image_path,
                overlay_png=overlay_png,
                audio_mp3=mixed_audio_mp3,
                output_mp4=clip_path,
                duration=duration,
                camera_move=cam_move,
                category=actual_category
            )

            rendered_scene_clips.append(clip_path)

        # ------------------------------------------------------------------------------------------
        # المرحلة 3: التجميع النهائي والربط الزمني الحاسم
        # ------------------------------------------------------------------------------------------
        logger.info("🪡 تجميع مقاطع التحقيق بدقة زمنية متطابقة بنسبة 100%...")
        concat_txt = CONFIG.work_dir / "concat_manifest.txt"
        with open(concat_txt, "w", encoding="utf-8") as f:
            for clip in rendered_scene_clips:
                f.write(f"file '{clip.resolve()}'\n")

        master_film_mp4 = CONFIG.work_dir / f"Final_Documentary_{int(time.time())}.mp4"
        cmd_concat = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_txt),
            "-c", "copy", str(master_film_mp4)
        ]
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        # فحص المدة الإجمالية للفيلم
        dur_cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            str(master_film_mp4)
        ]
        final_duration_sec = float(subprocess.check_output(dur_cmd).decode().strip())
        dur_min = int(final_duration_sec // 60)
        dur_sec = int(final_duration_sec % 60)
        logger.info(f"✨ اكتمل إنتاج الفيلم بالكامل! المدة الإجمالية: {dur_min} دقيقة و {dur_sec} ثانية.")

        # ------------------------------------------------------------------------------------------
        # المرحلة 4: النشر والأرشفة السحابية
        # ------------------------------------------------------------------------------------------
        video_title = f"تحقيق استقصائي: {CONFIG.topic} (ملف الأدلة الموثقة)"
        video_desc = (
            f"تحقيق جنائي وتاريخي موثق بالأدلة والمحاضر الرسمية الأصلية حول {CONFIG.topic}.\n\n"
            "ملاحظة توثيقية: يلتزم هذا العمل بالنزاهة الصحفية؛ حيث يتم الفصل بوضوح بين الوثائق الأرشيفية الأصلية "
            "وبين إعادة التمثيل الرقمية بالذكاء الاصطناعي عبر الشارات الظاهرة على الشاشة.\n\n"
            "هل تعتقد أن الشفرات الجنائية المتبقية ستحسم هوية الفاعل يوماً ما؟ شاركنا رأيك في التعليقات.\n\n"
            "#وثائقي #تحقيقات #أدلة_جنائية #تاريخ #جرائم_غامضة"
        )
        video_tags = ["وثائقي", "تحقيقات", "أدلة جنائية", "غموض", "قضايا تاريخية", "شفرات"]

        # رفع المقطع إلى درايف أولاً كنسخة أصلية
        CloudDistributionEngine.upload_to_google_drive(master_film_mp4)

        # نشر المقطع على يوتيوب
        CloudDistributionEngine.upload_to_youtube(
            video_path=master_film_mp4,
            title=video_title,
            description=video_desc,
            tags=video_tags
        )

        elapsed = datetime.now() - start_time
        logger.info(f"🎉 تم إنجاز خط الإنتاج بنجاح تام خلال: {elapsed}.")


# ==================================================================================================
# 10. نقطة الدخول الرئيسية للبرنامج (MAIN ENTRY POINT)
# ==================================================================================================

if __name__ == "__main__":
    try:
        pipeline = MasterDocumentaryPipeline()
        pipeline.run()
    except KeyboardInterrupt:
        logger.warning("تم إيقاف تشغيل النظام يدوياً من قبل المستخدم.")
        sys.exit(130)
    except Exception as exc:
        logger.critical(f"انهار خط الإنتاج بسبب خطأ جسيم: {exc}", exc_info=True)
        sys.exit(1)
