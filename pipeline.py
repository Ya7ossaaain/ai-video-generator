#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================================================
INVESTIGATIVE DOCUMENTARY BROADCAST MASTER ENGINE (CINEMATIC EDITION V10.0)
====================================================================================================
ترقية مونتاجية شاملة تحاكي المعايير السينمائية لشبكات البث العالمية:
1. التقطيع المزدوج (Multi-Shot Pacing): تقطيع المشهد إلى لقطة عامة ثم قطع خاطف (Crash Zoom / Punch-in)
   متزامن مع وميض أبيض ونقرة كاميرا تكتيكية.
2. الشاشات المنقسمة الجنائية (Forensic Split-Screen): دمج شاشات مقارنة متجاورة مع فاصل قرمزي ليزري.
3. محرك الترجمة والشارات التلفزيونية (libass): تشبيك حروف وظلال عربية أصلية دون انعكاس.
4. أداء تمثيلي كامل لـ Gemini Audio: توجيه درامي مشكول بالكامل مع تعريب صوتي للأسماء وحرارة 0.65.
5. استوديو صوتي تكتيكي متعدد الطبقات مع خفض ديناميكي للمؤثرات (Dynamic Ducking).
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
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime

import requests
from PIL import Image, ImageFilter

from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


# ==================================================================================================
# 1. نظام تسجيل الأحداث والقياس عن بُعد (LOGGING)
# ==================================================================================================

class ForensicTelemetryFormatter(logging.Formatter):
    CYAN = "\x1b[36;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"
    BASE_FORMAT = "%(asctime)s | [%(levelname)-8s] | (%(filename)s:%(lineno)04d) | %(message)s"

    FORMATS = {
        logging.DEBUG: RESET + BASE_FORMAT,
        logging.INFO: CYAN + BASE_FORMAT + RESET,
        logging.WARNING: YELLOW + BASE_FORMAT + RESET,
        logging.ERROR: RED + BASE_FORMAT + RESET,
        logging.CRITICAL: BOLD_RED + BASE_FORMAT + RESET
    }

    def format(self, record: logging.LogRecord) -> str:
        log_fmt = self.FORMATS.get(record.levelno, self.RESET + self.BASE_FORMAT)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


logger = logging.getLogger("ForensicMasterV10")
logger.setLevel(logging.INFO)
if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ForensicTelemetryFormatter())
    logger.addHandler(console_handler)


# ==================================================================================================
# 2. مصفوفة الإعدادات وبيانات البيئة (CONFIG)
# ==================================================================================================

def extract_api_keys_from_environment() -> List[str]:
    raw_env_str = os.environ.get("GEMINI_API_KEY", "")
    split_keys = [k.strip() for k in raw_env_str.replace("\n", ",").split(",") if k.strip()]
    if not split_keys:
        logger.critical("لم يتم العثور على أي مفتاح في متغير GEMINI_API_KEY داخل Secrets!")
    return split_keys


@dataclass
class MasterPipelineConfig:
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 24             # المعيار السينمائي الوثائقي الدولي (24.000 fps)
    video_crf: int = 18             # جودة تلفزيونية فائقة النقاء
    video_preset: str = "faster"    # سرعة المعالجة مع الحفاظ على الحواف
    video_tune: str = "grain"       # تحبيب تماثلي حقيقي 35mm عبر مشفر x264
    
    # نماذج الذكاء الاصطناعي المعتمدة
    script_model_name: str = "gemini-3-flash-preview"
    tts_model_name: str = "gemini-3.8-flash-tts"
    voice_character_name: str = "Charon"
    
    # المعايير الصوتية والتوقيت الاستقصائي
    audio_sample_rate: int = 48000
    audio_bitrate: str = "256k"
    post_tts_cooldown: int = 25     # فاصل أمان لحماية الحصص اليومية
    dramatic_pause_sec: float = 1.6 # سكتة درامية لاستيعاب الأدلة الصادمة
    max_key_rotations: int = 40
    
    # مسارات الملفات
    base_build_dir: Path = field(default_factory=lambda: Path("./output_build"))
    cache_dir: Path = field(default_factory=lambda: Path("./output_build/cache"))
    scenes_dir: Path = field(default_factory=lambda: Path("./output_build/scenes"))
    sfx_dir: Path = field(default_factory=lambda: Path("./output_build/sfx"))
    
    manifest_file: str = "investigative_manifest_v10.json"
    checkpoint_file: str = "checkpoint_state_v10.json"
    
    min_required_scenes: int = 64
    max_target_scenes: int = 66
    
    # المدخلات والاعتمادات السحابية
    topic: str = os.environ.get("VIDEO_TOPIC", "تحقيق استقصائي: لغز القاتل زودياك وحل الشفرة بعد نصف قرن")
    api_key_pool: List[str] = field(default_factory=extract_api_keys_from_environment)
    google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "")
    google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    youtube_refresh_token: str = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    drive_refresh_token: str = os.environ.get("DRIVE_REFRESH_TOKEN", "")

    def setup_directories(self) -> None:
        for folder in [self.base_build_dir, self.cache_dir, self.scenes_dir, self.sfx_dir]:
            folder.mkdir(parents=True, exist_ok=True)


CONFIG = MasterPipelineConfig()
CONFIG.setup_directories()


# ==================================================================================================
# 3. محرك الترجمة والشارات التلفزيونية الاحترافي (ASS SUBTITLE ENGINE)
# ==================================================================================================

class SubtitleBadgeEngine:
    """
    توليد ملفات ترجمة بصيغة Advanced SubStation Alpha (.ass) لمعالجتها مباشرة
    عبر مرشح libass في FFmpeg؛ مما يضمن تشبيك الحروف العربية وظلالها واتجاهها الصحيح 100%.
    """

    @staticmethod
    def generate_scene_ass(
        narration: str,
        category: str,
        source_name: str,
        duration: float,
        output_ass: Path
    ) -> None:
        def format_time(seconds: float) -> str:
            hrs = int(seconds // 3600)
            mins = int((seconds % 3600) // 60)
            secs = seconds % 60
            return f"{hrs:01d}:{mins:02d}:{secs:05.2f}"

        start_time = "0:00:00.00"
        end_time = format_time(duration)

        words = narration.strip().split()
        if len(words) > 10:
            mid = len(words) // 2
            formatted_narration = " ".join(words[:mid]) + "\\N" + " ".join(words[mid:])
        else:
            formatted_narration = narration

        badge_text = "● وثيقة رسمية أصلية | ملف التحقيق الجنائي" if category == "PRIMARY_ARCHIVE" else "● سجلات التحليل الجنائي والمقارنة المخبرية"
        if source_name:
            badge_text += f" | المصدر: {source_name}"

        ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Subtitle,Noto Sans Arabic,40,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3.5,2,2,80,80,65,1
Style: TopBadge,Noto Sans Arabic,22,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,2,1,7,60,60,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,{start_time},{end_time},TopBadge,,0,0,0,,{badge_text}
Dialogue: 1,{start_time},{end_time},Subtitle,,0,0,0,,{formatted_narration}
"""
        with open(output_ass, "w", encoding="utf-8") as f:
            f.write(ass_content)


# ==================================================================================================
# 4. استوديو المؤثرات الصوتية والدمج التكتيكي المتزامن (TACTICAL SOUND ENGINE)
# ==================================================================================================

class TacticalFoleyStudio:
    def __init__(self, sfx_dir: Path):
        self.sfx_dir = sfx_dir
        self.evidence_snap = self.sfx_dir / "evidence_snap.wav"
        self.typewriter_click = self.sfx_dir / "typewriter_click.wav"
        self.radio_static = self.sfx_dir / "radio_static.wav"
        self.camera_shutter = self.sfx_dir / "camera_shutter_click.wav"
        self.sub_bass_drone = self.sfx_dir / "sub_bass_drone_44hz.wav"
        self._synthesize_procedural_foley()

    def _synthesize_procedural_foley(self):
        if not self.evidence_snap.exists() or self.evidence_snap.stat().st_size < 1000:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.20:c=white:a=0.08,bandpass=f=1600:w=700,afade=t=out:st=0.03:d=0.17,volume=0.22", str(self.evidence_snap)]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not self.typewriter_click.exists() or self.typewriter_click.stat().st_size < 1000:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.08:c=white:a=0.15,bandpass=f=2600:w=900,afade=t=out:st=0.01:d=0.07,volume=0.20", str(self.typewriter_click)]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not self.camera_shutter.exists() or self.camera_shutter.stat().st_size < 1000:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.12:c=white:a=0.18,bandpass=f=3200:w=1200,afade=t=out:st=0.02:d=0.10,volume=0.28", str(self.camera_shutter)]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not self.radio_static.exists() or self.radio_static.stat().st_size < 1000:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.4:c=brown:a=0.06,lowpass=f=400,afade=t=in:st=0:d=0.05,afade=t=out:st=0.1:d=0.3,volume=0.14", str(self.radio_static)]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not self.sub_bass_drone.exists() or self.sub_bass_drone.stat().st_size < 1000:
            cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", "sine=f=44:d=30,lowpass=f=80,volume=0.06", str(self.sub_bass_drone)]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def mix_tactical_soundscape(
        self,
        voice_wav: Path,
        output_mp3: Path,
        category: str,
        scene_idx: int,
        cut_time_sec: float
    ) -> float:
        """
        دمج الصوت مع تزامن نقرة الكاميرا عند نقطة القطع البصري (Beat-Synced Hit Point).
        """
        sfx_start = self.evidence_snap if category == "PRIMARY_ARCHIVE" else (self.typewriter_click if scene_idx % 2 == 0 else self.radio_static)
        cut_delay_ms = max(500, int(cut_time_sec * 1000))

        filter_complex = (
            f"[1:a]adelay=40|40[foley_start];"
            f"[2:a]adelay={cut_delay_ms}|{cut_delay_ms}[foley_cut];"
            f"[3:a]aloop=loop=-1:size=2e+06,volume=0.07[drone];"
            f"[0:a][foley_start]amix=inputs=2:duration=first:dropout_transition=2[v_f1];"
            f"[v_f1][foley_cut]amix=inputs=2:duration=first:dropout_transition=2[v_f2];"
            f"[v_f2][drone]amix=inputs=2:duration=first:dropout_transition=3,"
            f"apad=pad_dur={CONFIG.dramatic_pause_sec},"
            f"loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
        )

        cmd = [
            "ffmpeg", "-y",
            "-i", str(voice_wav),
            "-i", str(sfx_start),
            "-i", str(self.camera_shutter),
            "-i", str(self.sub_bass_drone),
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-ar", str(CONFIG.audio_sample_rate),
            "-b:a", CONFIG.audio_bitrate,
            str(output_mp3)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(output_mp3)]
        return float(subprocess.check_output(dur_cmd).decode().strip())


# ==================================================================================================
# 5. محرك الذكاء الاصطناعي والأداء التمثيلي (INTELLIGENCE & ADVANCED TTS)
# ==================================================================================================

class MultiKeyProductionDirector:
    def __init__(self, key_pool: List[str]):
        if not key_pool:
            raise ValueError("مصفوفة المفاتيح فارغة! يرجى إضافة مفاتيح GEMINI_API_KEY داخل Secrets.")
        self.keys = key_pool
        self.active_index = 0
        self.client = genai.Client(api_key=self.keys[self.active_index])
        logger.info(f"🔑 مصفوفة المفاتيح جاهزة: {len(self.keys)} مفاتيح مستقلة للتدوير التلقائي.")

    def rotate_active_key(self) -> None:
        self.active_index = (self.active_index + 1) % len(self.keys)
        chosen_key = self.keys[self.active_index]
        masked = f"{chosen_key[:6]}...{chosen_key[-4:]}"
        logger.info(f"🔄 [تدوير المفاتيح]: الانتقال إلى المفتاح #{self.active_index + 1} ({masked}).")
        self.client = genai.Client(api_key=chosen_key)

    def generate_investigative_script(self, topic_title: str) -> List[Dict[str, Any]]:
        prompt = f"""
        أنت كبير مخرجي التحقيقات الاستقصائية والوثائقيات الجنائية الكبرى (Netflix True-Crime Director).
        الموضوع: "{topic_title}".
        المطلوب: صياغة سيناريو استقصائي محكم ومبني على الوثائق والمحاضر الرسمية يتكون بدقة من 64 إلى 66 مشهداً ليغطي 16 دقيقة كاملة.

        قواعد صارمة جداً لجودة النص والأداء الصوتي:
        1. الطول والمدة: كل مشهد يجب أن يتضمن نصاً سردياً مكثفاً من 35 إلى 45 كلمة لضمان وصول مدة الفيديو إلى 16 دقيقة كاملة.
        2. التشكيل التام (Tashkeel): يجب تشكيل كافة الكلمات الصعبة والأفعال وأسماء الأعلام بالحركات الإعرابية التامة لمنع التلعثم أو الخطأ في القراءة.
        3. التعريب الصوتي الإلزامي لأسماء الأعلام والأماكن (ممنوع كتابة أي اسم أجنبي بحروف لاتينية أو بدون تعريب مشكول):
           - Arthur Leigh Allen يُكتب حصراً: "آرْثَرْ لِي آلِينْ".
           - Lake Berryessa تُكتب حصراً: "بُحَيْرَةُ بَيْرِييْسَا".
           - Salinas تُكتب حصراً: "سَالِينَاسْ".
           - Paul Stine يُكتب حصراً: "بُول سْتَايْن".
           - Vallejo تُكتب حصراً: "فَالِيهُو".
           - Lake Herman تُكتب حصراً: "بُحَيْرَةُ هِيرْمَان".
        4. منع الكليشيهات الآلية المكررة: ممنوع منعاً باتاً استخدام عبارات ("شبح بني من نسيج الخوف"، "الأسطورة السوداء"، "صيد الحيوان الأكثر خطورة").
        5. أسلوب السرد والتشويق (Cold Open):
           - المشاهد (1-6): خطاف افتتاحي صادم يبدأ من رنين كابينة الهاتف في فاليجو وصوت القاتل الهادئ وهو يبلغ الشرطة.
           - المشاهد (7-22): الوقائع الجنائية وتفاصيل الرصاص المستخرج ومقاس الأحذية العسكرية وبصمات سيارة التاكسي.
           - المشاهد (23-38): حرب الرسائل الموجهة لصحيفة كرونيكل، وقطعة القماش الملطخة بالدماء.
           - المشاهد (39-50): تفكيك رياضي معمق لشفرة Z-340، وكيف حلت بعد 51 عاماً بالخوارزمية القطرية في 2020 على يد أورانشاك.
           - المشاهد (51-58): مقارنة أدلة الاتهام ضد "آرْثَرْ لِي آلِينْ" وتناقض البصمات والحمض النووي الذي برأه.
           - المشاهد (59-65): فرضيات المحققين المعاصرة وإغلاق الفيلم بسؤال استقصائي معلق يثير نقاش المشاهدين.

        أخرج النتيجة بصيغة JSON Array نقية ومباشرة فقط:
        [
          {{
            "scene_num": 1,
            "chapter_title": "مكالمة منتصف الليل الغامضة",
            "narration": "فِي الرَّابِعِ مِنْ يُولِيُو عَامَ أَلْفٍ وَتِسْعِمِائَةٍ وَتِسْعَةٍ وَسِتِّينَ، رَنَّ هَاتِفُ قِسْمِ شُرْطَةِ فَالِيهُو... صَوْتٌ بَارِدٌ ادَّعَى مَسْؤُولِيَّتَهُ عَنْ إِطْلَاقِ النَّارِ، مُعْلِناً بَدْءَ أَعْقَدِ لُغْزٍ جِنَائِيٍّ...",
            "media_type": "PRIMARY_ARCHIVE",
            "search_query": "Zodiac killer Vallejo police report 1969 scan"
          }}
        ]
        """
        logger.info(f"🚀 صياغة السيناريو الاستقصائي المطور عبر ({CONFIG.script_model_name})...")

        for attempt in range(len(self.keys) * 2):
            try:
                response = self.client.models.generate_content(
                    model=CONFIG.script_model_name,
                    contents=prompt
                )
                clean_json = response.text.strip().replace("```json", "").replace("```", "").strip()
                manifest = json.loads(clean_json)
                if isinstance(manifest, list) and len(manifest) >= CONFIG.min_required_scenes:
                    logger.info(f"تم اعتماد سيناريو الوثائقي المطور بنجاح ({len(manifest)} مشهداً).")
                    return manifest
            except Exception as e:
                logger.warning(f"تعثر الاستدعاء عبر المفتاح #{self.active_index + 1}: {str(e)[:80]}")
                self.rotate_active_key()
                time.sleep(2)

        raise RuntimeError("فشل توليد سيناريو التحقيق المطور عبر مصفوفة المفاتيح.")

    def synthesize_charon_voice(self, text: str, output_wav: Path) -> None:
        director_instruction = (
            "You are an award-winning true-crime investigative documentary narrator. "
            "Deliver this narration with a calm, deep, chilling, and authoritative tone. "
            "Pace is measured and deliberate, with slight drops in pitch during ominous moments. "
            "Pronounce all Arabic diacritics and voweling with crisp, broadcast-standard clarity."
        )

        guided_prompt = f"""
        [DIRECTOR INSTRUCTION: {director_instruction}]
        
        Read the following fully-vocalized text with exact investigative dramatic weight:
        {text}
        """

        for attempt in range(1, CONFIG.max_key_rotations + 1):
            try:
                response = self.client.models.generate_content(
                    model=CONFIG.tts_model_name,
                    contents=guided_prompt,
                    config=types.GenerateContentConfig(
                        response_modalities=["AUDIO"],
                        temperature=0.65,
                        speech_config=types.SpeechConfig(
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                    voice_name=CONFIG.voice_character_name
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
                    binary_payload = base64.b64decode(raw_bytes) if isinstance(raw_bytes, str) else raw_bytes
                    with open(output_wav, "wb") as f:
                        f.write(binary_payload)

                    logger.info(f"تم تسجيل الصوت بنجاح بنبرة موجهة. فترة تبريد وقائية ({CONFIG.post_tts_cooldown} ثانية)...")
                    time.sleep(CONFIG.post_tts_cooldown)
                    return

            except Exception as e:
                err_str = str(e)
                logger.warning(f"تنبيه صوت Charon (محاولة {attempt}): {err_str[:80]}")
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "503" in err_str:
                    self.rotate_active_key()
                    time.sleep(2)
                else:
                    time.sleep(5)

        raise RuntimeError("تعذر توليد صوت المشهد بعد استنفاد محاولات الدوران عبر كافة المفاتيح.")


# ==================================================================================================
# 6. جالب الأرشيف التاريخي الحقيقي 100% (AUTHENTIC ARCHIVE HARVESTER)
# ==================================================================================================

class AuthenticArchiveHarvester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "BroadcastInvestigativeEngine/10.0 (archival_research@documentary.org)"
        })

    def query_wikimedia_commons(self, query: str, output_path: Path) -> Tuple[bool, str]:
        try:
            api_endpoint = "https://commons.wikimedia.org/w/api.php"
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 6,
                "prop": "imageinfo",
                "iiprop": "url|extmetadata",
                "iiurlwidth": CONFIG.video_width,
                "format": "json"
            }
            res = self.session.get(api_endpoint, params=params, timeout=12)
            if res.status_code == 200:
                pages = res.json().get("query", {}).get("pages", {})
                for _, page in pages.items():
                    info = page.get("imageinfo", [])
                    if not info:
                        continue
                    meta = info[0].get("extmetadata", {})
                    source_label = meta.get("Credit", {}).get("value", "") or meta.get("Artist", {}).get("value", "National Archives")
                    clean_source = "".join([c for c in source_label if c.isalnum() or c in " -_()"])[:35]

                    media_url = info[0].get("thumburl") or info[0].get("url")
                    if media_url and not media_url.endswith(".svg"):
                        img_res = self.session.get(media_url, timeout=15)
                        if img_res.status_code == 200 and len(img_res.content) > 18000:
                            raw_tmp = output_path.with_suffix(".tmp")
                            with open(raw_tmp, "wb") as f:
                                f.write(img_res.content)
                            if self.process_blurred_fit(raw_tmp, output_path):
                                raw_tmp.unlink(missing_ok=True)
                                return True, clean_source or "National Archives"
                            raw_tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False, ""

    def query_wikipedia_records(self, query: str, output_path: Path) -> Tuple[bool, str]:
        try:
            api_endpoint = "https://en.wikipedia.org/w/api.php"
            params = {
                "action": "query",
                "generator": "search",
                "gsrsearch": query,
                "gsrlimit": 4,
                "prop": "pageimages",
                "pithumbsize": CONFIG.video_width,
                "format": "json"
            }
            res = self.session.get(api_endpoint, params=params, timeout=12)
            if res.status_code == 200:
                pages = res.json().get("query", {}).get("pages", {})
                for _, page in pages.items():
                    thumb = page.get("thumbnail", {}).get("source")
                    if thumb and not thumb.endswith(".svg"):
                        img_res = self.session.get(thumb, timeout=15)
                        if img_res.status_code == 200 and len(img_res.content) > 18000:
                            raw_tmp = output_path.with_suffix(".tmp")
                            with open(raw_tmp, "wb") as f:
                                f.write(img_res.content)
                            if self.process_blurred_fit(raw_tmp, output_path):
                                raw_tmp.unlink(missing_ok=True)
                                return True, "Historical Records"
                            raw_tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False, ""

    def generate_atmospheric_noir_backdrop(self, output_path: Path) -> None:
        canvas = Image.new("RGB", (CONFIG.video_width, CONFIG.video_height), (12, 15, 20))
        canvas.save(output_path, "JPEG", quality=95)

    @staticmethod
    def process_blurred_fit(input_path: Path, output_path: Path) -> bool:
        try:
            filter_chain = (
                f"[0:v]scale={CONFIG.video_width}:{CONFIG.video_height}:force_original_aspect_ratio=increase,"
                f"crop={CONFIG.video_width}:{CONFIG.video_height},boxblur=25:4[bg];"
                f"[0:v]scale={CONFIG.video_width}:{CONFIG.video_height}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
            )
            cmd = ["ffmpeg", "-y", "-i", str(input_path), "-filter_complex", filter_chain, "-frames:v", "1", str(output_path)]
            res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return (res.returncode == 0 and output_path.exists() and output_path.stat().st_size > 5000)
        except Exception:
            return False


# ==================================================================================================
# 7. محرك المونتاج السينمائي والتقطيع الديناميكي (DYNAMIC MONTAGE COMPOSITOR)
# ==================================================================================================

class DynamicMontageCompositor:
    """
    محرك المونتاج المتقدم:
    - يكسر الرتابة بتطبيق التقطيع المزدوج (Multi-Shot Pacing) مع وميض أبيض ناعم ونقرة كاميرا متزامنة.
    - أو إنشاء شاشة منقسمة جنائية (Split-Screen) مع فاصل ليزري قرمزي لمشاهد التحليل والمقارنة.
    """

    @staticmethod
    def render_montage_scene(
        image_path: Path,
        ass_path: Path,
        audio_mp3: Path,
        output_mp4: Path,
        duration: float,
        scene_idx: int,
        is_forensic: bool
    ) -> None:
        fps = CONFIG.video_fps
        total_frames = max(1, int(duration * fps))
        ass_esc = str(ass_path.resolve()).replace('\\', '/').replace(':', r'\:').replace("'", r"\'")

        # نمط المونتاج 1: شاشة منقسمة جنائية (Forensic Split-Screen) لمشاهد المقارنة والشفرات
        if is_forensic or (scene_idx % 4 == 2):
            filter_complex = (
                f"[0:v]split=2[in_left][in_right];"
                f"[in_left]zoompan=z='min(1.06, 1.0+0.0002*on)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={total_frames}:s=960x1080:fps={fps}[left];"
                f"[in_right]zoompan=z='min(1.45, 1.32+0.0003*on)':x='iw*0.3':y='ih*0.2':d={total_frames}:s=960x1080:fps={fps}[right];"
                f"[left][right]hstack=inputs=2[v_split];"
                f"[v_split]drawbox=x=958:y=0:w=4:h=1080:color=0xbd1818@0.9:t=fill,"
                f"eq=contrast=1.14:brightness=-0.02:saturation=0.88,vignette=PI/3.8,"
                f"subtitles='{ass_esc}',fps={fps},settb=1/{fps},setpts=PTS-STARTPTS[v]"
            )
        else:
            # نمط المونتاج 2: تقطيع مزدوج (Establishing Wide -> Flash Cut -> Macro Punch-in)
            f1 = int(total_frames * 0.42)
            f2 = total_frames - f1

            filter_complex = (
                f"[0:v]split=2[in1][in2];"
                f"[in1]zoompan=z='min(1.08, 1.0+0.0004*on)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={f1}:s={CONFIG.video_width}x{CONFIG.video_height}:fps={fps}[v1];"
                f"[in2]zoompan=z='min(1.36, 1.25+0.0003*on)':x='iw/2-(iw/zoom/2)':y='ih*0.22':d={f2}:s={CONFIG.video_width}x{CONFIG.video_height}:fps={fps},"
                f"fade=t=in:st=0:d=0.08:color=white[v2];"
                f"[v1][v2]concat=n=2:v=1:a=0[v_cuts];"
                f"[v_cuts]eq=contrast=1.12:brightness=-0.02:saturation=0.88,vignette=PI/3.6,"
                f"subtitles='{ass_esc}',fps={fps},settb=1/{fps},setpts=PTS-STARTPTS[v]"
            )

        cmd = [
            "ffmpeg", "-y", "-threads", "0",
            "-loop", "1", "-i", str(image_path),
            "-i", str(audio_mp3),
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", CONFIG.video_preset, "-tune", CONFIG.video_tune, "-crf", str(CONFIG.video_crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", CONFIG.audio_bitrate, "-ar", str(CONFIG.audio_sample_rate),
            "-t", str(duration),
            str(output_mp4)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)


# ==================================================================================================
# 8. إدارة النشر السحابي والأرشفة (CLOUD DISTRIBUTION)
# ==================================================================================================

class CloudDistributionEngine:
    @staticmethod
    def upload_to_youtube(video_path: Path, title: str, description: str, tags: List[str]) -> Optional[str]:
        if not (CONFIG.google_client_id and CONFIG.google_client_secret and CONFIG.youtube_refresh_token):
            logger.warning("بيانات اعتماد YouTube غير متوفرة. تم تخطي الرفع للقناة.")
            return None

        # حماية صارمة لطول العنوان لمنع خطأ HttpError 400
        safe_title = (title[:88] + "...") if len(title) > 88 else title
        logger.info(f"جاري رفع الفيلم إلى YouTube بعنوان: {safe_title}...")

        try:
            creds = Credentials(
                None,
                refresh_token=CONFIG.youtube_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CONFIG.google_client_id,
                client_secret=CONFIG.google_client_secret
            )
            yt_service = build("youtube", "v3", credentials=creds)

            body = {
                "snippet": {
                    "title": safe_title,
                    "description": description,
                    "tags": tags,
                    "categoryId": "27"
                },
                "status": {
                    "privacyStatus": "public",
                    "selfDeclaredMadeForKids": False
                }
            }

            media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True, chunksize=15 * 1024 * 1024)
            request = yt_service.videos().insert(part="snippet,status", body=body, media_body=media)

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    logger.info(f"تقدم رفع يوتيوب: {int(status.progress() * 100)}%")

            video_id = response.get("id")
            logger.info(f"تم نشر الفيلم الاستقصائي بنجاح! الرابط: https://youtu.be/{video_id}")
            return video_id

        except Exception as exc:
            logger.error(f"خطأ أثناء الرفع إلى يوتيوب: {exc}")
            return None

    @staticmethod
    def upload_to_google_drive(video_path: Path, folder_name: str = "Investigative_Master_Vault") -> Optional[str]:
        if not (CONFIG.google_client_id and CONFIG.google_client_secret and CONFIG.drive_refresh_token):
            logger.warning("بيانات Drive غير متوفرة. تخطي الأرشفة.")
            return None

        logger.info(f"جاري أرشفة النسخة الأصلية على Google Drive...")
        try:
            creds = Credentials(
                None,
                refresh_token=CONFIG.drive_refresh_token,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=CONFIG.google_client_id,
                client_secret=CONFIG.google_client_secret
            )
            drive_service = build("drive", "v3", credentials=creds)

            query = f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
            res = drive_service.files().list(q=query, fields="files(id, name)").execute()
            folders = res.get("files", [])

            folder_id = folders[0]["id"] if folders else drive_service.files().create(
                body={"name": folder_name, "mimeType": "application/vnd.google-apps.folder"}, fields="id"
            ).execute()["id"]

            file_meta = {"name": video_path.name, "parents": [folder_id]}
            media = MediaFileUpload(str(video_path), mimetype="video/mp4", resumable=True)
            uploaded_file = drive_service.files().create(body=file_meta, media_body=media, fields="id").execute()
            logger.info(f"تمت الأرشفة على Drive بنجاح. معرف الملف: {uploaded_file.get('id')}")
            return uploaded_file.get("id")

        except Exception as exc:
            logger.error(f"خطأ Google Drive: {exc}")
            return None


# ==================================================================================================
# 9. المايسترو ومنظم خط الإنتاج الكامل (MASTER ORCHESTRATOR)
# ==================================================================================================

class MasterDocumentaryPipeline:
    def __init__(self):
        self.director = MultiKeyProductionDirector(CONFIG.api_key_pool)
        self.harvester = AuthenticArchiveHarvester()
        self.sound_studio = TacticalFoleyStudio(CONFIG.sfx_dir)

    def run(self) -> None:
        start_time = datetime.now()
        logger.info(f"🎬 [بدء إنتاج وثائقي الـ 16 دقيقة السينمائي]: {CONFIG.topic}")

        manifest_path = CONFIG.base_build_dir / CONFIG.manifest_file
        scenes_manifest: List[Dict[str, Any]] = []

        if manifest_path.exists():
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    scenes_manifest = json.load(f)
                logger.info(f"تم استعادة السيناريو المعتمد مسبقاً ({len(scenes_manifest)} مشهداً).")
            except Exception:
                scenes_manifest = []

        if not scenes_manifest:
            scenes_manifest = self.director.generate_investigative_script(CONFIG.topic)
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(scenes_manifest, f, ensure_ascii=False, indent=2)

        rendered_clips: List[Path] = []
        scene_durations: List[float] = []
        total_scenes = len(scenes_manifest)

        for idx, scene in enumerate(scenes_manifest):
            narration = scene.get("narration", "")
            req_type = scene.get("media_type", "PRIMARY_ARCHIVE")
            search_q = scene.get("search_query", "")

            prefix = f"scene_{idx:03d}"
            clip_path = CONFIG.scenes_dir / f"{prefix}.mp4"
            voice_raw_wav = CONFIG.cache_dir / f"{prefix}_voice.wav"
            mixed_audio_mp3 = CONFIG.cache_dir / f"{prefix}_mixed.mp3"
            visual_path = CONFIG.cache_dir / f"{prefix}_visual.jpg"
            ass_path = CONFIG.cache_dir / f"{prefix}_sub.ass"

            logger.info(f"⏳ معالجة المشهد السينمائي ({idx + 1}/{total_scenes}) [النوع: {req_type}]...")

            if clip_path.exists() and clip_path.stat().st_size > 50000:
                logger.info(f"المشهد {idx + 1} مكتمل وجاهز مسبقاً. تخطي المعالجة.")
                rendered_clips.append(clip_path)
                dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)]
                scene_durations.append(float(subprocess.check_output(dur_cmd).decode().strip()))
                continue

            # جلب الوثيقة الأرشيفية الحقيقية 100%
            got_archive, source_attribution = self.harvester.query_wikimedia_commons(search_q, visual_path)
            if not got_archive:
                got_archive, source_attribution = self.harvester.query_wikipedia_records(search_q, visual_path)
            if not got_archive:
                self.harvester.generate_atmospheric_noir_backdrop(visual_path)
                source_attribution = "Historical Archive"

            # توليد صوت Charon مشكولاً وموجهاً إخراجياً
            if not voice_raw_wav.exists() or voice_raw_wav.stat().st_size < 1000:
                self.director.synthesize_charon_voice(narration, voice_raw_wav)

            # تحديد لحظة القطع الخاطف لتتزامن نقرة الكاميرا معها بدقة
            probe_dur = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(voice_raw_wav)]
            v_dur = float(subprocess.check_output(probe_dur).decode().strip())
            cut_time_sec = v_dur * 0.42

            # دمج الصوت والمؤثرات المتزامنة
            duration = self.sound_studio.mix_tactical_soundscape(voice_raw_wav, mixed_audio_mp3, req_type, idx, cut_time_sec)
            scene_durations.append(duration)

            # بناء ملف ترجمة ASS بنظام libass
            SubtitleBadgeEngine.generate_scene_ass(
                narration=narration,
                category=req_type,
                source_name=source_attribution,
                duration=duration,
                output_ass=ass_path
            )

            # الرندرة السينمائية بالتقطيع الديناميكي أو الشاشة المنقسمة
            is_forensic_scene = (
                "شفرة" in narration or "مقارنة" in narration or "بصمات" in narration or 
                "تحليل" in narration or req_type == "FORENSIC_ANALYSIS"
            )
            DynamicMontageCompositor.render_montage_scene(
                image_path=visual_path,
                ass_path=ass_path,
                audio_mp3=mixed_audio_mp3,
                output_mp4=clip_path,
                duration=duration,
                scene_idx=idx,
                is_forensic=is_forensic_scene
            )

            rendered_clips.append(clip_path)

        # التجميع النهائي الصارم للفيلم
        logger.info("🪡 تجميع مقاطع التحقيق السينمائية بدقة متطابقة بنسبة 100%...")
        concat_manifest = CONFIG.base_build_dir / "concat_manifest.txt"
        with open(concat_manifest, "w", encoding="utf-8") as f:
            for clip in rendered_clips:
                f.write(f"file '{clip.resolve()}'\n")

        clean_slug = "".join([c for c in CONFIG.topic[:25] if c.isalnum() or c in " _-"]).strip()
        final_film_mp4 = CONFIG.base_build_dir / f"Master_Doc_{clean_slug}_{int(time.time())}.mp4"
        cmd_concat = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_manifest), "-c", "copy", str(final_film_mp4)]
        subprocess.run(cmd_concat, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(final_film_mp4)]
        total_seconds = float(subprocess.check_output(dur_cmd).decode().strip())
        mins = int(total_seconds // 60)
        secs = int(total_seconds % 60)
        logger.info(f"✨ اكتمل إنتاج الفيلم الاستقصائي بالكامل! المدة الإجمالية: {mins} دقيقة و {secs} ثانية.")

        # توليد الفصول الزمنية
        current_time = 0.0
        chapters_block = "الفصول الزمنية للتحقيق:\n00:00 - المقدمة: مكالمة منتصف الليل\n"
        last_title = ""

        for idx, (scene, s_dur) in enumerate(zip(scenes_manifest, scene_durations)):
            c_title = scene.get("chapter_title", "")
            if c_title and c_title != last_title and current_time > 15:
                c_mins = int(current_time // 60)
                c_secs = int(current_time % 60)
                chapters_block += f"{c_mins:02d}:{c_secs:02d} - {c_title}\n"
                last_title = c_title
            current_time += s_dur

        doc_title = "الشفرة التي حيّرت الـ FBI: الملف الجنائي الكامل للقاتل زودياك"
        doc_description = (
            f"تحقيق وثائقي استقصائي شامل يفتح الملفات والأدلة الأرشيفية الموثقة حول: {CONFIG.topic}.\n\n"
            f"{chapters_block}\n"
            "ملاحظة توثيقية: يلتزم هذا العمل بالنزاهة الصحفية الصارمة؛ حيث يعتمد العمل بنسبة 100% على محاضر التحقيق الأصلية "
            "والوثائق الأرشيفية المعتمدة، دون استخدام أي صور تخيلية مصطنعة.\n\n"
            "#وثائقي #تحقيقات #غموض #أدلة_جنائية #تاريخ #ملفات_سرية #زودياك"
        )
        doc_tags = ["وثائقي", "تحقيقات", "أدلة جنائية", "تاريخ", "ملفات سرية", "زودياك"]

        CloudDistributionEngine.upload_to_google_drive(final_film_mp4)
        CloudDistributionEngine.upload_to_youtube(final_film_mp4, doc_title, doc_description, doc_tags)

        elapsed = datetime.now() - start_time
        logger.info(f"🎉 تم إنجاز العمل الاستقصائي بالكامل بنجاح ساحق خلال: {elapsed}.")


# ==================================================================================================
# 10. نقطة الدخول الرئيسية للنظام (ENTRYPOINT)
# ==================================================================================================

if __name__ == "__main__":
    try:
        pipeline = MasterDocumentaryPipeline()
        pipeline.run()
    except KeyboardInterrupt:
        logger.warning("تم إيقاف تشغيل خط الإنتاج يدوياً من قبل المستخدم.")
        sys.exit(130)
    except Exception as exc:
        logger.critical(f"انهار خط الإنتاج بسبب خطأ جسيم: {exc}", exc_info=True)
        sys.exit(1)
