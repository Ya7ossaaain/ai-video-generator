#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================================================
FORENSIC & HISTORICAL DOCUMENTARY ENGINE (PRODUCTION PIPELINE V5.4 - NANO BANANA 2 LITE)
====================================================================================================
- محرك الصور المجاني: gemini-3.1-flash-lite-image (Nano Banana 2 Lite) حصرياً عبر Google AI Studio.
- محرك السيناريو: gemini-3.5-flash عبر كافة المفاتيح، ثم التراجع التلقائي إلى gemini-3-flash-preview.
- المحرك الصوتي: gemini-3.8-flash-tts حصرياً (بصوت Charon التوثيقي) مع فاصل أمان 25 ثانية.
- هندسة البرومبت: محاكاة فوتوغرافية أرشيفية حقيقية (1969 35mm Harsh Flash) واستبعاد مظهر الـ 3D.
- معالجة التناظر: خلفية ضبابية ذكية (Blurred Fit) لحماية الوجوه والوثائق من الاقتصاص.
- التايبوجرافي: تنزيل وتثبيت خط Amiri-Bold وتصحيح الاتجاه العربي بنسبة 100%.
- المدة والفصول: 16 دقيقة (62-68 مشهداً)، وقفات درامية (1.4 ثانية)، وحقن الفصول تلقائياً.
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
from dataclasses import dataclass, field
from datetime import datetime

import requests
from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ==================================================================================================
# 1. إعدادات النظام وتسجيل الأحداث (LOGGING & GLOBAL CONFIGURATION)
# ==================================================================================================

class ColoredFormatter(logging.Formatter):
    CYAN = "\x1b[36;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"
    FORMAT = "%(asctime)s - [%(levelname)s] - (%(filename)s:%(lineno)d) - %(message)s"

    FORMATS = {
        logging.DEBUG: RESET + FORMAT,
        logging.INFO: CYAN + FORMAT + RESET,
        logging.WARNING: YELLOW + FORMAT + RESET,
        logging.ERROR: RED + FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + FORMAT + RESET
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.RESET + self.FORMAT)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


logger = logging.getLogger("ForensicDocPipeline")
logger.setLevel(logging.INFO)
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(ColoredFormatter())
logger.addHandler(console_handler)


def parse_api_keys() -> List[str]:
    raw = os.environ.get("GEMINI_API_KEY", "")
    keys = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
    return keys


@dataclass
class PipelineConfig:
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 25
    video_crf: int = 19
    video_preset: str = "veryfast"
    
    # نموذج الصور المجاني الوحيد من Google AI Studio
    free_image_model: str = "gemini-3.1-flash-lite-image"
    tts_models: List[str] = field(default_factory=lambda: ["gemini-3.8-flash-tts"])
    gemini_voice_name: str = "Charon"
    
    # إعدادات الصوت وتدوير المفاتيح
    audio_sample_rate: int = 48000
    audio_bitrate: str = "192k"
    post_tts_cooldown: int = 25     # فاصل أمان 25 ثانية لحماية الحصص
    dramatic_pause_sec: float = 1.4 # سكتة درامية تتيح استيعاب الأدلة
    max_rotation_attempts: int = 30
    
    # مسارات الملفات والمجلدات
    work_dir: Path = field(default_factory=lambda: Path("./output_build"))
    cache_dir: Path = field(default_factory=lambda: Path("./output_build/cache"))
    scenes_dir: Path = field(default_factory=lambda: Path("./output_build/scenes"))
    assets_dir: Path = field(default_factory=lambda: Path("./output_build/assets"))
    sfx_dir: Path = field(default_factory=lambda: Path("./output_build/sfx"))
    script_cache_name: str = "forensic_manifest_v5_pool10.json"
    
    min_scenes: int = 62
    max_scenes: int = 68
    max_text_line_pixel_width: int = 1500
    
    topic: str = os.environ.get("VIDEO_TOPIC", "لغز القاتل زودياك: وثائق التحقيق وحل الشفرة المستحيلة بعد 50 عاماً")
    gemini_api_keys: List[str] = field(default_factory=parse_api_keys)
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    yt_refresh_token: str = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    drive_refresh_token: str = os.environ.get("DRIVE_REFRESH_TOKEN", "")

    def init_workspace(self):
        for d in [self.work_dir, self.cache_dir, self.scenes_dir, self.assets_dir, self.sfx_dir]:
            d.mkdir(parents=True, exist_ok=True)
        logger.info(f"تم تهيئة مجلدات العمل بنجاح داخل: {self.work_dir}")


CONFIG = PipelineConfig()


# ==================================================================================================
# 2. إدارة التايبوجرافي والخطوط واللغة العربية (AMIRI ARABIC ENGINE)
# ==================================================================================================

class TypographyEngine:
    def __init__(self):
        self.font_path = self._resolve_or_download_font()
        logger.info(f"تم اعتماد الخط العربي الأرشيفي الموثوق: {self.font_path}")

    @staticmethod
    def _resolve_or_download_font() -> str:
        target_font = CONFIG.work_dir / "Amiri-Bold.ttf"
        if not target_font.exists() or target_font.stat().st_size < 10000:
            font_url = "https://raw.githubusercontent.com/google/fonts/main/ofl/amiri/Amiri-Bold.ttf"
            try:
                logger.info("جاري تنزيل خط Amiri-Bold لضمان صحة اتصال الحروف والتشكيل...")
                res = requests.get(font_url, timeout=15)
                if res.status_code == 200:
                    with open(target_font, "wb") as f:
                        f.write(res.content)
                    return str(target_font)
            except Exception as e:
                logger.warning(f"تعذر تنزيل Amiri-Bold ({e}). الانتقال لخطوط النظام...")

        if target_font.exists():
            return str(target_font)

        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

    def get_font(self, size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype(self.font_path, size)
        except Exception:
            return ImageFont.load_default()

    def reshape_and_bidi(self, text: str) -> str:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped, base_dir='R')

    def wrap_arabic_text_by_pixels(
        self,
        text: str,
        font: ImageFont.FreeTypeFont,
        max_pixel_width: int
    ) -> List[str]:
        words = text.strip().split()
        lines: List[str] = []
        current_words: List[str] = []

        dummy_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(dummy_img)

        for word in words:
            candidate_line = " ".join(current_words + [word])
            disp = self.reshape_and_bidi(candidate_line)
            rendered_width = draw.textlength(disp, font=font)

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
    @staticmethod
    def create_scene_overlay(
        narration: str,
        media_category: str,
        source_name: str,
        output_png: Path
    ) -> None:
        canvas = Image.new("RGBA", (CONFIG.video_width, CONFIG.video_height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        font_sub = TYPOGRAPHY.get_font(33)
        font_badge = TYPOGRAPHY.get_font(21)
        font_meta = TYPOGRAPHY.get_font(16)

        badge_text = ""
        bg_color = (0, 0, 0, 0)
        border_color = (0, 0, 0, 0)

        if media_category == "PRIMARY_ARCHIVE":
            badge_text = "● وثيقة رسمية أصلية | ملف التحقيق الجنائي"
            bg_color = (150, 0, 0, 235)
            border_color = (255, 255, 255, 140)
        elif media_category == "HISTORICAL_RECORD":
            badge_text = "● مادة تاريخية معاصرة | أرشيف الصحافة والسجلات"
            bg_color = (145, 75, 0, 235)
            border_color = (255, 255, 255, 140)
        elif media_category == "AI_REENACTMENT":
            badge_text = "● إعادة تمثيل بصرية | محاكاة أرشيفية بالذكاء الاصطناعي"
            bg_color = (35, 38, 42, 220)
            border_color = (180, 180, 180, 100)

        if badge_text:
            reshaped_badge = TYPOGRAPHY.reshape_and_bidi(badge_text)
            badge_w = draw.textlength(reshaped_badge, font=font_badge) + 36
            badge_h = 48
            bx, by = 60, 50

            draw.rectangle([bx, by, bx + badge_w, by + badge_h], fill=bg_color, outline=border_color, width=2)
            draw.text((bx + 18, by + 10), reshaped_badge, font=font_badge, fill=(255, 255, 255, 255))

            if source_name and media_category in ["PRIMARY_ARCHIVE", "HISTORICAL_RECORD"]:
                src_label = f"المصدر: {source_name}"
                reshaped_src = TYPOGRAPHY.reshape_and_bidi(src_label)
                src_w = draw.textlength(reshaped_src, font=font_meta) + 24
                sx = bx + badge_w + 12
                draw.rectangle([sx, by + 4, sx + src_w, by + badge_h - 4], fill=(10, 15, 20, 200), outline=(255, 255, 255, 60), width=1)
                draw.text((sx + 12, by + 12), reshaped_src, font=font_meta, fill=(220, 220, 220, 240))

        gradient_h = 175
        grad_box = Image.new("RGBA", (CONFIG.video_width, gradient_h), (0, 0, 0, 0))
        grad_draw = ImageDraw.Draw(grad_box)
        for y in range(gradient_h):
            alpha = int(230 * (y / gradient_h))
            grad_draw.line([(0, y), (CONFIG.video_width, y)], fill=(0, 0, 0, alpha))
        
        canvas.paste(grad_box, (0, CONFIG.video_height - gradient_h), grad_box)

        lines = TYPOGRAPHY.wrap_arabic_text_by_pixels(
            narration, font=font_sub, max_pixel_width=CONFIG.max_text_line_pixel_width
        )
        display_lines = lines[:2]

        y_base = 935 if len(display_lines) == 1 else 915
        for idx, raw_line in enumerate(display_lines):
            disp_line = TYPOGRAPHY.reshape_and_bidi(raw_line)
            line_w = draw.textlength(disp_line, font=font_sub)
            x_pos = (CONFIG.video_width - line_w) // 2
            y_pos = y_base + (idx * 50)

            draw.text((x_pos + 2, y_pos + 2), disp_line, font=font_sub, fill=(0, 0, 0, 255))
            draw.text((x_pos, y_pos), disp_line, font=font_sub, fill=(255, 255, 255, 255))

        canvas.save(output_png, "PNG")


# ==================================================================================================
# 4. محرك هندسة الصوت والوقفات الدرامية (AUDIO PACING & SFX STUDIO)
# ==================================================================================================

class ForensicSoundStudio:
    def __init__(self, sfx_directory: Path):
        self.sfx_dir = sfx_directory
        self.evidence_snap_wav = self.sfx_dir / "evidence_stamp.wav"
        self.soft_whoosh_wav = self.sfx_dir / "air_transition.wav"
        self.init_procedural_sfx()

    def init_procedural_sfx(self):
        if not self.evidence_snap_wav.exists() or self.evidence_snap_wav.stat().st_size < 1000:
            cmd_snap = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anoisesrc=d=0.22:c=white:a=0.08,bandpass=f=1600:w=700,afade=t=out:st=0.04:d=0.18,volume=0.22",
                str(self.evidence_snap_wav)
            ]
            subprocess.run(cmd_snap, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not self.soft_whoosh_wav.exists() or self.soft_whoosh_wav.stat().st_size < 1000:
            cmd_whoosh = [
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", "anoisesrc=d=0.32:c=brown:a=0.06,lowpass=f=320,afade=t=in:st=0:d=0.08,afade=t=out:st=0.08:d=0.24,volume=0.16",
                str(self.soft_whoosh_wav)
            ]
            subprocess.run(cmd_whoosh, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def mix_scene_audio(
        self,
        voice_wav: Path,
        output_mixed_mp3: Path,
        category: str
    ) -> float:
        sfx_source = self.evidence_snap_wav if category == "PRIMARY_ARCHIVE" else self.soft_whoosh_wav

        filter_str = (
            "[1:a]adelay=40|40[sfx];"
            "[0:a][sfx]amix=inputs=2:duration=first:dropout_transition=2,"
            f"apad=pad_dur={CONFIG.dramatic_pause_sec},"
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

        cmd_dur = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            str(output_mixed_mp3)
        ]
        duration = float(subprocess.check_output(cmd_dur).decode().strip())
        return duration


# ==================================================================================================
# 5. محرك استدعاء وصور الذكاء الاصطناعي (GOOGLE AI STUDIO NANO BANANA 2 LITE CLIENT)
# ==================================================================================================

class GeminiDocumentaryDirector:
    def __init__(self, api_keys: List[str]):
        if not api_keys:
            raise ValueError("لم يتم العثور على أي GEMINI_API_KEY! يرجى إضافتها في Secrets.")
        self.api_keys = api_keys
        self.current_key_idx = 0
        self.client = genai.Client(api_key=self.api_keys[self.current_key_idx])
        logger.info(f"🔑 جاهزية مصفوفة المفاتيح: تم تحميل {len(self.api_keys)} مفتاح(مفاتيح) بنجاح.")

    def rotate_to_next_key(self):
        self.current_key_idx = (self.current_key_idx + 1) % len(self.api_keys)
        new_key = self.api_keys[self.current_key_idx]
        masked = f"{new_key[:5]}...{new_key[-4:]}"
        logger.info(f"🔄 [تدوير المفاتيح]: الانتقال إلى المفتاح #{self.current_key_idx + 1} ({masked}).")
        self.client = genai.Client(api_key=new_key)

    def draft_forensic_manifest(self, topic: str) -> List[Dict[str, Any]]:
        prompt = f"""
        أنت كبير مخرجي ومحققي الوثائقيات الاستقصائية الكبرى (True-Crime Documentaries).
        الموضوع: "{topic}".
        المطلوب: إنتاج سيناريو استقصائي وقصصي واقعي متكامل يتكون بدقة من 64 إلى 66 مشهداً (16 دقيقة).

        الهيكل الدرامي الصارم للفيلم:
        1. خطاف البداية (Hook - المشاهد 1 إلى 5): لقطة مكثفة وصادمة للشفرة الموجهة للصحافة وعجز الـ FBI، وتساؤل حاد يشد المشاهد فوراً.
        2. الوقائع والجرائم الموثقة (المشاهد 6 إلى 25): بحيرة هيرمان، سبرينغز، بحيرة "بيرييسا" بدقة نطق الاسم، وحادثة مقتل "بول ستاين" في سان فرانسيسكو.
        3. حرب الرسائل والشفرات (المشاهد 26 إلى 42): تحليل شفرة Z-408، وطريقة كسرها، ورسائل الاستفزاز، ورمز الصليب والدائرة الشهير.
        4. المشتبه بهم والتحقيقات الجنائية (المشاهد 43 إلى 52): مراجعة ملف آرثر لي ألين، وبصمات اليد، وعينات الخط، وأسباب براءته قانونياً.
        5. فرضية القاتل الفرد مقابل الشركاء (المشاهد 53 إلى 58): مقارنة تفصيلية بين نظرية القاتل الواحد ونظرية وجود أكثر من شخص تلاعب بالأدلة.
        6. حل الشفرة المستحيلة بعد نصف قرن والخاتمة (المشاهد 59 إلى 65): حل شفرة Z-340 عام 2020 على يد أورانشاك وفريقه، وتأكيد النص الفعلي، ولغز القضية المفتوحة حتى اليوم.

        قواعد الإخراج والتصوير التوثيقي:
        - السرد (narration): جملتان باللغة العربية الفصحى الرصينة، تطابق المذكر والمؤنث بدقة تامة.
        - تصنيف الوسائط (media_type): بدقة بين ("PRIMARY_ARCHIVE", "HISTORICAL_RECORD", "AI_REENACTMENT", "STOCK_BROLL").
        - البحث الأرشيفي (search_query): كلمات إنجليزية دقيقة مأخوذة من سجلات الأرشيف الأمريكي الحقيقي.
        - وصف المشاهد التخيلية (ai_prompt): تجنب تماماً المؤثرات الدرامية المبتذلة (مثل الدخان، والإضاءة السينمائية الملونة، والوجوه البلاستيكية). صف مشاهد كأنها صور فوتوغرافية أرشيفية خام التقطتها كاميرا محقق في مسرح الحادث عام 1969 بفلاش مباشر وألوان واقعية باهتة.
        - الفصول (chapter_title): حدد اسم الفصل العام للمشهد لإنشاء الفهرس الزمني.

        أخرج النتيجة بصيغة JSON Array نقية ومباشرة فقط:
        [
          {{
            "scene_num": 1,
            "chapter_title": "لغز شفرة الموت الأولى",
            "narration": "في أواخر الستينيات، لم تكن كاليفورنيا تواجه مجرد قاتل متسلسل، بل لغزاً رياضياً عجزت أمامه أكثر العقول الاستخباراتية تطوراً...",
            "media_type": "PRIMARY_ARCHIVE",
            "search_query": "Zodiac killer Vallejo cipher letter 1969",
            "ai_prompt": "1969 authentic crime scene investigation, vintage typewriter on worn wooden desk, forensic cipher documents, harsh direct camera flash, analog photo, Kodak Tri-X grain",
            "camera_move": "zoom_in"
          }}
        ]
        """
        model_hierarchy = ["gemini-3.5-flash", "gemini-3-flash-preview"]

        for model_name in model_hierarchy:
            logger.info(f"🚀 بدء محاولات توليد السيناريو عبر النموذج ({model_name}) على مصفوفة المفاتيح...")
            for _ in range(len(self.api_keys)):
                try:
                    logger.info(f"محاولة توليد السيناريو عبر ({model_name}) بالمفتاح #{self.current_key_idx + 1}...")
                    res = self.client.models.generate_content(model=model_name, contents=prompt)
                    clean_text = res.text.strip().replace("```json", "").replace("```", "").strip()
                    parsed = json.loads(clean_text)
                    if isinstance(parsed, list) and len(parsed) >= CONFIG.min_scenes:
                        logger.info(f"تم اعتماد سيناريو الـ 16 دقيقة بنجاح عبر ({model_name}): {len(parsed)} مشهداً.")
                        return parsed
                except Exception as e:
                    err_msg = str(e)
                    logger.warning(f"تعثر التوليد بـ ({model_name}) عبر المفتاح #{self.current_key_idx + 1}: {err_msg[:80]}")
                    self.rotate_to_next_key()
                    time.sleep(2)
            
            logger.warning(f"⚠️ استُنفدت كافة المفاتيح مع ({model_name}). الانتقال للبديل...")

        raise RuntimeError("فشل توليد السيناريو عبر كلا النموذجين بعد فحص كافة المفاتيح.")

    def synthesize_charon_voice(self, text: str, output_wav: Path) -> None:
        """توليد صوت Charon بنموذج gemini-3.8-flash-tts مع التدوير وفاصل الأمان."""
        for attempt in range(1, CONFIG.max_rotation_attempts + 1):
            for model_name in CONFIG.tts_models:
                try:
                    response = self.client.models.generate_content(
                        model=model_name,
                        contents=text,
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
                    if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                        for part in response.candidates[0].content.parts:
                            if part.inline_data and part.inline_data.data:
                                raw_bytes = part.inline_data.data
                                break

                    if raw_bytes:
                        binary_data = base64.b64decode(raw_bytes) if isinstance(raw_bytes, str) else raw_bytes
                        with open(output_wav, "wb") as f:
                            f.write(binary_data)
                        
                        logger.info(f"تم إنتاج الصوت بنجاح. فترة راحة وقائية ({CONFIG.post_tts_cooldown} ثانية)...")
                        time.sleep(CONFIG.post_tts_cooldown)
                        return

                except Exception as e:
                    err_msg = str(e)
                    logger.warning(f"تنبيه صوت ({model_name} - محاولة {attempt}): {err_msg[:80]}")
                    
                    if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "503" in err_msg:
                        self.rotate_to_next_key()
                        time.sleep(2)
                        break
                    
                    time.sleep(5)

        raise RuntimeError(f"تعذر توليد صوت المشهد بعد استنزاف محاولات التدوير عبر كافة المفاتيح.")

    def generate_google_ai_studio_image(self, prompt: str, output_path: Path) -> bool:
        """
        توليد الصور مجاناً 100% عبر النموذج المجاني الرسمي:
        gemini-3.1-flash-lite-image (Nano Banana 2 Lite)
        """
        forensic_prompt = (
            f"Archival 1969 police documentary crime scene evidence photograph of {prompt}. "
            "Captured on 35mm analog film, direct camera flash, deep dark shadows, Kodak Tri-X grain texture. "
            "Mundane late 1960s authentic forensic realism, muted period colors. "
            "No CGI, no 3D render, no plastic skin, no digital drawing, no fantasy neon lights"
        )

        for attempt in range(len(self.api_keys)):
            try:
                logger.info(f"جاري طلب صورة مجانية من Google AI Studio عبر ({CONFIG.free_image_model}) [المفتاح #{self.current_key_idx + 1}]...")
                response = self.client.models.generate_content(
                    model=CONFIG.free_image_model,
                    contents=forensic_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["IMAGE"],
                        image_config=types.ImageConfig(
                            aspect_ratio="16:9"
                        )
                    )
                )

                if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
                    for part in response.candidates[0].content.parts:
                        if part.inline_data and part.inline_data.data:
                            raw_bytes = part.inline_data.data
                            bin_data = base64.b64decode(raw_bytes) if isinstance(raw_bytes, str) else raw_bytes
                            raw_tmp = output_path.with_suffix(".tmp")
                            with open(raw_tmp, "wb") as f:
                                f.write(bin_data)
                            
                            if ForensicAssetHarvester.process_image_blurred_fit(raw_tmp, output_path):
                                raw_tmp.unlink(missing_ok=True)
                                logger.info(f"✨ تم إنتاج صورة أرشيفية بنجاح عبر Nano Banana 2 Lite ({CONFIG.free_image_model}).")
                                return True
                            raw_tmp.unlink(missing_ok=True)

            except Exception as e:
                err_msg = str(e)
                logger.warning(f"تنبيه صورة Google AI Studio ({CONFIG.free_image_model}): {err_msg[:80]}")
                if "429" in err_msg or "RESOURCE_EXHAUSTED" in err_msg or "503" in err_msg:
                    self.rotate_to_next_key()
                    time.sleep(2)
                else:
                    break
        return False


# ==================================================================================================
# 6. محرك البحث والتحقق من الأدلة الأرشيفية (ARCHIVAL ASSET ACQUISITION)
# ==================================================================================================

class ForensicAssetHarvester:
    def __init__(self, director: GeminiDocumentaryDirector):
        self.director = director
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ForensicDocumentaryEngine/5.4 (contact: historical_investigation@gmail.com)"
        })

    def search_wikimedia_archive(self, query: str, output_path: Path) -> Tuple[bool, str]:
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
                    clean_source = "".join([c for c in source_desc if c.isalnum() or c in " -_()"])[:35]
                    
                    target_url = info[0].get("thumburl") or info[0].get("url")
                    if target_url and not target_url.endswith(".svg"):
                        img_res = self.session.get(target_url, timeout=12)
                        if img_res.status_code == 200 and len(img_res.content) > 20000:
                            raw_tmp = output_path.with_suffix(".tmp")
                            with open(raw_tmp, "wb") as f:
                                f.write(img_res.content)
                            if self.process_image_blurred_fit(raw_tmp, output_path):
                                raw_tmp.unlink(missing_ok=True)
                                return True, clean_source or "National Archives"
                            raw_tmp.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"فحص ويكيميديا الثانوي: {e}")
        return False, ""

    def search_wikipedia_article_images(self, query: str, output_path: Path) -> Tuple[bool, str]:
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
                            if self.process_image_blurred_fit(raw_tmp, output_path):
                                raw_tmp.unlink(missing_ok=True)
                                return True, "Historical Records"
                            raw_tmp.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"ويكيبيديا الثانوي: {e}")
        return False, ""

    def generate_ai_reenactment_visual(self, prompt: str, output_path: Path) -> bool:
        # المحاولة الأساسية: النموذج المجاني المتاح في حسابك
        if self.director.generate_google_ai_studio_image(prompt, output_path):
            return True

        # خطة طوارئ في حال الضغط لضمان عدم توقف الفيلم
        logger.info("جاري الاستعانة بمحرك FLUX-Realism كبديل طارئ...")
        forensic_prompt = (
            f"Authentic 1969 police crime scene evidence photo of {prompt}. "
            "Shot on 35mm analog film, harsh direct camera flash, deep shadows, Kodak Tri-X grain texture. "
            "No 3D render, no CGI, no smooth plastic skin, no illustration"
        )
        encoded = urllib.parse.quote(forensic_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={CONFIG.video_width}&height={CONFIG.video_height}&nologo=true&nofeed=true&model=flux-realism&seed={int(time.time()) % 10000}"

        for attempt in range(2):
            try:
                res = self.session.get(url, timeout=35)
                if res.status_code == 200 and len(res.content) > 15000:
                    raw_tmp = output_path.with_suffix(".tmp")
                    with open(raw_tmp, "wb") as f:
                        f.write(res.content)
                    if self.process_image_blurred_fit(raw_tmp, output_path):
                        raw_tmp.unlink(missing_ok=True)
                        return True
                    raw_tmp.unlink(missing_ok=True)
            except Exception:
                time.sleep(3)

        cmd_blank = [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=0x0a0c10:s={CONFIG.video_width}x{CONFIG.video_height}:d=1",
            "-frames:v", "1", str(output_path)
        ]
        subprocess.run(cmd_blank, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    @staticmethod
    def process_image_blurred_fit(input_path: Path, output_path: Path) -> bool:
        try:
            filter_chain = (
                f"[0:v]scale={CONFIG.video_width}:{CONFIG.video_height}:force_original_aspect_ratio=increase,"
                f"crop={CONFIG.video_width}:{CONFIG.video_height},boxblur=25:5[bg];"
                f"[0:v]scale={CONFIG.video_width}:{CONFIG.video_height}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
            )
            cmd = [
                "ffmpeg", "-y", "-i", str(input_path),
                "-filter_complex", filter_chain,
                "-frames:v", "1", str(output_path)
            ]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return (res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 5000)
        except Exception:
            return False


# ==================================================================================================
# 7. استوديو المونتاج البصري والمعالجة التماثلية (CINEMATIC COMPOSITOR & FFmpeg)
# ==================================================================================================

class CinematicRenderer:
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

        if camera_move == "zoom_out":
            zoom_expr = "max(1.0, 1.12 - 0.0003*on)"
            pan_expr = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif camera_move == "tilt_down":
            zoom_expr = "1.08"
            pan_expr = f"x='iw/2-(iw/zoom/2)':y='max(0, min(ih-ih/zoom, (on/{total_frames})*(ih-ih/zoom)))'"
        elif camera_move == "pan_right":
            zoom_expr = "1.08"
            pan_expr = f"x='min(iw-iw/zoom, (on/{total_frames})*(iw-iw/zoom))':y='ih/2-(ih/zoom/2)'"
        elif camera_move == "pan_left":
            zoom_expr = "1.08"
            pan_expr = f"x='max(0, (1 - on/{total_frames})*(iw-iw/zoom))':y='ih/2-(ih/zoom/2)'"
        else:
            zoom_expr = "min(1.12, 1.0 + 0.0003*on)"
            pan_expr = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

        if category in ["PRIMARY_ARCHIVE", "HISTORICAL_RECORD"]:
            color_grading = "hue=s=0.72,eq=contrast=1.15:brightness=-0.02,noise=alls=10:allf=t+u,vignette=PI/3.6"
        else:
            color_grading = "eq=contrast=1.12:saturation=0.88:brightness=-0.02,noise=alls=14:allf=t+u,vignette=PI/4.0"

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
# 8. إدارة النشر السحابي وتوليد الفصول (DISTRIBUTION & CHAPTER ENGINE)
# ==================================================================================================

class CloudDistributionEngine:
    @staticmethod
    def upload_to_youtube(video_path: Path, title: str, description: str, tags: List[str]) -> Optional[str]:
        if not (CONFIG.google_client_id and CONFIG.google_client_secret and CONFIG.yt_refresh_token):
            logger.warning("بيانات اعتماد YouTube API غير مكتملة في Secrets. تم تخطي النشر على يوتيوب.")
            return None

        logger.info("جاري بدء الرفع المباشر إلى قناة YouTube مع الفصول الزمنية...")
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
                    "categoryId": "27"
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
    def __init__(self):
        CONFIG.init_workspace()
        self.director = GeminiDocumentaryDirector(CONFIG.gemini_api_keys)
        self.harvester = ForensicAssetHarvester(self.director)
        self.sound_studio = ForensicSoundStudio(CONFIG.sfx_dir)

    def run(self):
        start_time = datetime.now()
        logger.info(f"🎬 [بدء الإنتاج الموسع]: العمل الوثائقي (16 دقيقة): {CONFIG.topic}")

        # المرحلة 1: إنتاج أو استرجاع سيناريو التحقيق
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

        # المرحلة 2: معالجة المشاهد بشكل تسلسلي متين
        rendered_scene_clips: List[Path] = []
        scene_durations: List[float] = []
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

            if clip_path.exists() and clip_path.stat().st_size > 50000:
                logger.info(f"المشهد {idx + 1} مكتمل وجاهز مسبقاً.")
                rendered_scene_clips.append(clip_path)
                dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)]
                scene_durations.append(float(subprocess.check_output(dur_cmd).decode().strip()))
                continue

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
                actual_category = "AI_REENACTMENT"
                source_attribution = ""
                self.harvester.generate_ai_reenactment_visual(ai_prompt, image_path)

            # توليد صوت Charon بنموذج gemini-3.8-flash-tts
            if not voice_raw_wav.exists() or voice_raw_wav.stat().st_size < 1000:
                self.director.synthesize_charon_voice(narration, voice_raw_wav)

            duration = self.sound_studio.mix_scene_audio(voice_raw_wav, mixed_audio_mp3, actual_category)
            scene_durations.append(duration)

            GraphicOverlayCompositor.create_scene_overlay(
                narration=narration,
                media_category=actual_category,
                source_name=source_attribution,
                output_png=overlay_png
            )

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

        # المرحلة 3: التجميع النهائي والربط الزمني الحاسم
        logger.info("🪡 تجميع مقاطع التحقيق الـ 16 دقيقة بدقة متطابقة...")
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

        dur_cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1:nokey=1",
            str(master_film_mp4)
        ]
        final_duration_sec = float(subprocess.check_output(dur_cmd).decode().strip())
        dur_min = int(final_duration_sec // 60)
        dur_sec = int(final_duration_sec % 60)
        logger.info(f"✨ اكتمل إنتاج الفيلم بالكامل! المدة الإجمالية: {dur_min} دقيقة و {dur_sec} ثانية.")

        # المرحلة 4: حساب الفصول الزمنية التلقائية
        current_time = 0.0
        chapters_text = "الفصول الزمنية:\n00:00 - المقدمة: خطاف اللغز والشفرة الأولى\n"
        last_chapter_title = ""

        for idx, (scene, s_dur) in enumerate(zip(scenes_manifest, scene_durations)):
            c_title = scene.get("chapter_title", "")
            if c_title and c_title != last_chapter_title and current_time > 15:
                mins = int(current_time // 60)
                secs = int(current_time % 60)
                chapters_text += f"{mins:02d}:{secs:02d} - {c_title}\n"
                last_chapter_title = c_title
            current_time += s_dur

        # المرحلة 5: النشر السحابي
        video_title = "لغز القاتل زودياك: وثائق التحقيق وحل الشفرة المستحيلة بعد 50 عاماً"
        video_desc = (
            "تحقيق استقصائي شامل يفتح الملفات الجنائية الأرشيفية لأعقد قضايا الاغتيال والشفرات في القرن العشرين: "
            "قضية القاتل زودياك، من أولى الوقائع عام 1968 إلى فك شفرة Z-340 المستحيلة عام 2020.\n\n"
            f"{chapters_text}\n"
            "ملاحظة توثيقية: يلتزم هذا العمل بالنزاهة والشفافية التامة؛ حيث يتم الفصل بوضوح بين الوثائق الأرشيفية الأصلية "
            "وبين إعادة التمثيل الرقمية بالذكاء الاصطناعي عبر الشارات الظاهرة على الشاشة.\n\n"
            "هل تعتقد أن الشفرات المتبقية ستحسم هوية الفاعل يوماً ما؟ شاركنا رأيك في التعليقات.\n\n"
            "#الحسين #حكايات_واقعية #وثائقي #جرائم_غامضة #زودياك #أدلة_جنائية"
        )
        video_tags = ["الحسين", "حكايات واقعية", "زودياك", "وثائقي", "تحقيقات", "أدلة جنائية", "حل شفرة زودياك"]

        CloudDistributionEngine.upload_to_google_drive(master_film_mp4)

        CloudDistributionEngine.upload_to_youtube(
            video_path=master_film_mp4,
            title=video_title,
            description=video_desc,
            tags=video_tags
        )

        elapsed = datetime.now() - start_time
        logger.info(f"🎉 تم إنجاز العمل الوثائقي الموسع بنجاح تام خلال: {elapsed}.")


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
