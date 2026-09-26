#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================================================
UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE (ENTERPRISE MASTER V13.2 - NETFLIX STANDARD)
====================================================================================================
"""

import os
import sys
import json
import time
import math
import re
import logging
import asyncio
import base64
import subprocess
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime
import urllib.parse

import requests
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ==================================================================================================
# 1. ADVANCED TELEMETRY, LOGGING & OBSERVABILITY
# ==================================================================================================

class ForensicTelemetryFormatter(logging.Formatter):
    COLORS = {
        'DEBUG': "\x1b[38;5;240m",
        'INFO': "\x1b[38;5;39m",
        'WARNING': "\x1b[38;5;214m",
        'ERROR': "\x1b[38;5;196m",
        'CRITICAL': "\x1b[48;5;196;38;5;231m\x1b[1m"
    }
    RESET = "\x1b[0m"
    BASE_FORMAT = "%(asctime)s | [%(levelname)-8s] | %(name)s | (%(filename)s:%(lineno)04d) | %(message)s"

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.RESET)
        formatter = logging.Formatter(f"{color}{self.BASE_FORMAT}{self.RESET}", datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

def setup_enterprise_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(ForensicTelemetryFormatter())
        logger.addHandler(console_handler)
    return logger

log = setup_enterprise_logger("BroadcastEngine")

# ==================================================================================================
# 2. ENTERPRISE CONFIGURATION & CREDENTIAL MANAGEMENT
# ==================================================================================================

class CredentialManager:
    @staticmethod
    def get_api_keys(env_var: str = "GEMINI_API_KEY") -> List[str]:
        raw = os.environ.get(env_var, "")
        keys = [k.strip() for k in raw.replace("\n", ",").split(",") if k.strip()]
        if not keys:
            log.critical(f"FATAL: Missing crucial environment variable: {env_var}")
            sys.exit(1)
        return keys

@dataclass
class BroadcastStandards:
    width: int = 1920
    height: int = 1080
    fps: int = 24
    crf: int = 17
    preset: str = "fast"
    tune: str = "film"
    audio_sample_rate: int = 48000
    audio_bitrate: str = "320k"
    ebu_lufs_target: float = -23.0
    ebu_lra_target: float = 11.0

@dataclass
class AIModels:
    architect_model: str = "gemini-flash-latest"
    writer_model: str = "gemini-flash-latest"
    tts_model: str = "gemini-3.8-flash-tts"
    tts_voice: str = "Charon"
    tts_temp: float = 0.15
    post_tts_cooldown: int = 5
    dramatic_pause_sec: float = 1.5

@dataclass
class PipelinePaths:
    base: Path = field(default_factory=lambda: Path("./output_build"))
    cache: Path = field(default_factory=lambda: Path("./output_build/cache"))
    scenes: Path = field(default_factory=lambda: Path("./output_build/scenes"))
    sfx: Path = field(default_factory=lambda: Path("./output_build/sfx"))
    manifest: Path = field(default_factory=lambda: Path("./output_build/master_manifest.json"))
    checkpoint: Path = field(default_factory=lambda: Path("./output_build/master_checkpoint.json"))

    def initialize(self) -> None:
        for path in [self.base, self.cache, self.scenes, self.sfx]:
            path.mkdir(parents=True, exist_ok=True)

class MasterConfig:
    topic: str = os.environ.get("VIDEO_TOPIC", "لغز اختفاء طائرة دي بي كوبر")
    standards = BroadcastStandards()
    models = AIModels()
    paths = PipelinePaths()
    api_keys = CredentialManager.get_api_keys()
    yt_client_id = os.environ.get("GOOGLE_CLIENT_ID", "")
    yt_client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "")
    yt_refresh = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    drive_refresh = os.environ.get("DRIVE_REFRESH_TOKEN", "")
    min_scenes = 64
    max_scenes = 66

CONFIG = MasterConfig()
CONFIG.paths.initialize()

# ==================================================================================================
# 3. ROBUST STATE MACHINE & FAULT TOLERANCE
# ==================================================================================================

class PipelineState:
    def __init__(self, path: Path):
        self.path = path
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    state = json.load(f)
                log.info(f"Checkpoint restored: {len(state.get('completed', []))} sequences done.")
                return state
            except Exception as e:
                log.error(f"Checkpoint corruption ({e}). Starting fresh.")
        return {"completed": [], "durations": {}, "status": "initialized"}

    def mark_done(self, idx: int, duration: float) -> None:
        if idx not in self.data["completed"]:
            self.data["completed"].append(idx)
            self.data["durations"][str(idx)] = duration
            self._save()

    def is_done(self, idx: int) -> bool:
        return idx in self.data["completed"]

    def _save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

# ==================================================================================================
# 4. AI MULTI-AGENT ARCHITECTURE
# ==================================================================================================

class MultiAgentDirector:
    def __init__(self, keys: List[str]):
        self.keys = keys
        self.key_idx = 0
        self.client = self._get_client()

    def _get_client(self) -> genai.Client:
        return genai.Client(api_key=self.keys[self.key_idx])

    def _rotate_key(self) -> None:
        self.key_idx = (self.key_idx + 1) % len(self.keys)
        k = self.keys[self.key_idx]
        log.warning(f"Rotating API Key -> Index {self.key_idx} (***{k[-4:]})")
        self.client = self._get_client()

    def _robust_call(self, model: str, prompt: str, is_json: bool = False, config_kwargs: dict = None) -> Any:
        kwargs = config_kwargs or {}
        if is_json:
            kwargs["response_mime_type"] = "application/json"
            
        # تعطيل فلاتر الأمان لضمان عدم حظر قضايا الجرائم والغموض (إلزامية للوثائقيات)
        kwargs["safety_settings"] = [
            types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
            types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
        ]
        
        cfg = types.GenerateContentConfig(**kwargs)
        max_retries = len(self.keys) * 3
        
        for attempt in range(max_retries):
            try:
                res = self.client.models.generate_content(model=model, contents=prompt, config=cfg)
                if is_json:
                    clean = res.text.strip()
                    match = re.search(r'\[.*\]', clean, re.DOTALL)
                    if match:
                        clean = match.group(0)
                    return json.loads(clean)
                return res.text
            except Exception as e:
                err = str(e)
                log.error(f"API Error ({model} - Attempt {attempt+1}): {err[:250]}")
                if "429" in err or "quota" in err.lower() or "503" in err:
                    self._rotate_key()
                    time.sleep(3)
                else:
                    time.sleep(5)
        log.critical("FATAL: Multi-agent system collapse. All keys exhausted.")
        sys.exit(1)

    def orchestrate_script_generation(self, topic: str) -> List[Dict[str, Any]]:
        log.info(f"Agent [Writer]: Constructing Narrative Architecture via {CONFIG.models.writer_model}...")
        sys_prompt = f"""
        أنت كبير مخرجي التحقيقات الوثائقيات في شبكات البث العالمية (Executive Documentary Director).
        الموضوع: "{topic}".
        
        المهمة:
        بناء سيناريو استقصائي من {CONFIG.min_scenes} إلى {CONFIG.max_scenes} مشهداً.
        
        القيود الصارمة:
        1. كثافة السرد: كل مشهد يحتوي على نص من 35-45 كلمة مشكولة بالحركات بشكل كامل.
        2. التعريب الصوتي: اكتب الأسماء الأجنبية صوتياً بالحروف العربية.
        3. الحظر: لا تستخدم التشبيهات الرخيصة. اعتمد لغة تقريرية، محايدة، ومرعبة.
        
        المخرجات المطلوبة (JSON Array Only):
        [
          {{
            "scene_num": 1,
            "chapter_title": "اسم الفصل",
            "narration": "نَصٌّ مُشَكَّلٌ يَبْدَأُ بِحَدَثٍ...",
            "media_type": "PRIMARY_ARCHIVE",
            "search_query": "English keywords for accurate archival photo search"
          }}
        ]
        """
        script_data = self._robust_call(CONFIG.models.writer_model, sys_prompt, is_json=True)
        if not isinstance(script_data, list) or len(script_data) < CONFIG.min_scenes:
            log.warning("Agent [Writer] failed to hit scene count. Re-orchestrating...")
            script_data = self._robust_call(CONFIG.models.writer_model, sys_prompt + "\nIMPORTANT: YOU MUST GENERATE AT LEAST 64 SCENES.", is_json=True)
        return script_data

    def generate_theatrical_voice(self, text: str, output_wav: Path) -> None:
        cue = (
            "You are a master true-crime documentary narrator. Deliver this text with a chilling, "
            "authoritative, deep, and measured tone. Slow down for emphasis on facts. "
            "Perfectly pronounce all Arabic diacritics."
        )
        prompt = f"[DIRECTOR INSTRUCTION: {cue}]\n\n{text}"
        
        cfg = types.GenerateContentConfig(
            response_modalities=["AUDIO"], 
            temperature=CONFIG.models.tts_temp,
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="BLOCK_NONE"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="BLOCK_NONE"),
            ],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=CONFIG.models.tts_voice)
                )
            )
        )
        
        max_retries = len(self.keys) * 2
        for attempt in range(max_retries):
            try:
                res = self.client.models.generate_content(model=CONFIG.models.tts_model, contents=prompt, config=cfg)
                for part in res.candidates[0].content.parts:
                    if part.inline_data and part.inline_data.data:
                        raw = part.inline_data.data
                        payload = base64.b64decode(raw) if isinstance(raw, str) else raw
                        with open(output_wav, "wb") as f:
                            f.write(payload)
                        time.sleep(CONFIG.models.post_tts_cooldown)
                        return
            except Exception as e:
                err = str(e)
                log.error(f"TTS API Error (Attempt {attempt+1}): {err[:150]}")
                if "429" in err or "503" in err:
                    self._rotate_key()
                    time.sleep(2)
                else:
                    time.sleep(5)
        log.error("Failed to generate TTS audio.")
        raise RuntimeError("TTS Generation Failure")

# ==================================================================================================
# 5. ASYNCHRONOUS MEDIA HARVESTER
# ==================================================================================================

class AsyncArchiveHarvester:
    def __init__(self):
        self.headers = {"User-Agent": "BroadcastPipeline/13.2 (research@broadcaster.internal)"}
        
    def harvest_sync(self, query: str, output_path: Path) -> Tuple[bool, str]:
        return asyncio.run(self._harvest_async(query, output_path))

    async def _harvest_async(self, query: str, output_path: Path) -> Tuple[bool, str]:
        success, attr = await self._search_wikimedia(query, output_path)
        if success: return True, attr
        success, attr = await self._search_wikipedia(query, output_path)
        if success: return True, attr
        return False, ""

    async def _search_wikimedia(self, query: str, output_path: Path) -> Tuple[bool, str]:
        url = "https://commons.wikimedia.org/w/api.php"
        params = {"action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": 4, 
                  "prop": "imageinfo", "iiprop": "url|extmetadata", "format": "json"}
        try:
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(None, lambda: requests.get(url, params=params, headers=self.headers, timeout=10))
            if res.status_code == 200:
                pages = res.json().get("query", {}).get("pages", {})
                for _, p in pages.items():
                    info = p.get("imageinfo", [])
                    if info:
                        img_url = info[0].get("url")
                        meta = info[0].get("extmetadata", {})
                        attr = meta.get("Credit", {}).get("value", "National Archives")
                        attr = "".join([c for c in attr if c.isalnum() or c in " -_()"])[:35]
                        if img_url and not img_url.endswith(".svg"):
                            if await self._download_and_blur(img_url, output_path):
                                return True, attr
        except Exception:
            pass
        return False, ""

    async def _search_wikipedia(self, query: str, output_path: Path) -> Tuple[bool, str]:
        url = "https://en.wikipedia.org/w/api.php"
        params = {"action": "query", "generator": "search", "gsrsearch": query, "gsrlimit": 4, 
                  "prop": "pageimages", "pithumbsize": 1920, "format": "json"}
        try:
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(None, lambda: requests.get(url, params=params, headers=self.headers, timeout=10))
            if res.status_code == 200:
                pages = res.json().get("query", {}).get("pages", {})
                for _, p in pages.items():
                    img_url = p.get("thumbnail", {}).get("source")
                    if img_url and not img_url.endswith(".svg"):
                        if await self._download_and_blur(img_url, output_path):
                            return True, "Historical Records"
        except Exception:
            pass
        return False, ""

    async def _download_and_blur(self, url: str, output_path: Path) -> bool:
        try:
            loop = asyncio.get_event_loop()
            res = await loop.run_in_executor(None, lambda: requests.get(url, headers=self.headers, timeout=15))
            if res.status_code == 200 and len(res.content) > 15000:
                tmp = output_path.with_suffix(".tmp")
                with open(tmp, "wb") as f: f.write(res.content)
                filter_chain = f"[0:v]scale={CONFIG.standards.width}:{CONFIG.standards.height}:force_original_aspect_ratio=increase,crop={CONFIG.standards.width}:{CONFIG.standards.height},boxblur=30:5[bg];[0:v]scale={CONFIG.standards.width}:{CONFIG.standards.height}:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
                cmd = ["ffmpeg", "-y", "-i", str(tmp), "-filter_complex", filter_chain, "-frames:v", "1", str(output_path)]
                proc = await asyncio.create_subprocess_exec(*cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                await proc.wait()
                tmp.unlink(missing_ok=True)
                return proc.returncode == 0
        except Exception:
            pass
        return False

    def generate_procedural_backdrop(self, output_path: Path) -> None:
        cmd = ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c=0x0a0c11:s={CONFIG.standards.width}x{CONFIG.standards.height}", "-frames:v", "1", str(output_path)]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

# ==================================================================================================
# 6. EBU R128 AUDIO MASTERING & PROCEDURAL FOLEY STUDIO
# ==================================================================================================

class AudioMasteringRack:
    def __init__(self):
        self.sfx = CONFIG.paths.sfx
        self.fx_snap = self.sfx / "snap.wav"
        self.fx_type = self.sfx / "type.wav"
        self.fx_radio = self.sfx / "radio.wav"
        self.fx_shutter = self.sfx / "shutter.wav"
        self.fx_drone = self.sfx / "drone.wav"
        self._init_rack()

    def _init_rack(self):
        assets = {
            self.fx_snap: "anoisesrc=d=0.20:c=white:a=0.08,bandpass=f=1600:w=700,afade=t=out:st=0.03:d=0.17,volume=0.25",
            self.fx_type: "anoisesrc=d=0.08:c=white:a=0.15,bandpass=f=2600:w=900,afade=t=out:st=0.01:d=0.07,volume=0.22",
            self.fx_shutter: "anoisesrc=d=0.12:c=white:a=0.18,bandpass=f=3200:w=1200,afade=t=out:st=0.02:d=0.10,volume=0.30",
            self.fx_radio: "anoisesrc=d=0.4:c=brown:a=0.06,lowpass=f=400,afade=t=in:st=0:d=0.05,afade=t=out:st=0.1:d=0.3,volume=0.15",
            self.fx_drone: "sine=f=44:d=30,lowpass=f=80,volume=0.06"
        }
        for path, lavfi in assets.items():
            if not path.exists():
                subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i", lavfi, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def master_scene_audio(self, voice_wav: Path, out_mp3: Path, is_primary: bool, idx: int, cut_sec: float) -> float:
        start_sfx = self.fx_snap if is_primary else (self.fx_type if idx % 2 == 0 else self.fx_radio)
        delay_ms = max(500, int(cut_sec * 1000))

        fc = (
            f"[1:a]adelay=40|40[f_st];"
            f"[2:a]adelay={delay_ms}|{delay_ms}[f_cut];"
            f"[3:a]aloop=loop=-1:size=2e+06[drn];"
            f"[0:a]acompressor=threshold=-14dB:ratio=4:attack=5:release=50[v_comp];"
            f"[v_comp][f_st]amix=inputs=2:duration=first:dropout_transition=2[m1];"
            f"[m1][f_cut]amix=inputs=2:duration=first:dropout_transition=2[m2];"
            f"[m2][drn]amix=inputs=2:duration=first:dropout_transition=3,"
            f"apad=pad_dur={CONFIG.models.dramatic_pause_sec},"
            f"loudnorm=I={CONFIG.standards.ebu_lufs_target}:TP=-1.5:LRA={CONFIG.standards.ebu_lra_target}[aout]"
        )

        cmd = [
            "ffmpeg", "-y", "-i", str(voice_wav), "-i", str(start_sfx), "-i", str(self.fx_shutter), "-i", str(self.fx_drone),
            "-filter_complex", fc, "-map", "[aout]", "-ar", str(CONFIG.standards.audio_sample_rate),
            "-b:a", CONFIG.standards.audio_bitrate, str(out_mp3)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        dur_cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(out_mp3)]
        return float(subprocess.check_output(dur_cmd).decode().strip())

# ==================================================================================================
# 7. TYPOGRAPHY & BROADCAST SUBTITLES (LIBASS)
# ==================================================================================================

class SubtitleRenderer:
    @staticmethod
    def _format_time(s: float) -> str:
        return f"{int(s//3600)}:{int((s%3600)//60):02d}:{s%60:05.2f}"

    @classmethod
    def generate_ass(cls, text: str, category: str, source: str, duration: float, out_ass: Path) -> None:
        words = text.strip().split()
        if len(words) > 12:
            mid = len(words) // 2
            text = " ".join(words[:mid]) + "\\N" + " ".join(words[mid:])

        badge = "● وثيقة رسمية أصلية | الأرشيف الموثق" if category == "PRIMARY_ARCHIVE" else "● سجلات التحليل والمقارنة الاستقصائية"
        if source: badge += f" | المصدر: {source}"

        ass_content = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: MainSub,Noto Sans Arabic,42,&H00FFFFFF,&H000000FF,&H00000000,&H90000000,-1,0,0,0,100,100,0,0,1,3.5,2.5,2,80,80,65,1
Style: TopBadge,Noto Sans Arabic,24,&H00FFFFFF,&H000000FF,&H00101010,&H90000000,-1,0,0,0,100,100,0,0,1,2,1.5,7,60,60,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,{cls._format_time(duration)},TopBadge,,0,0,0,,{badge}
Dialogue: 1,0:00:00.00,{cls._format_time(duration)},MainSub,,0,0,0,,{text}
"""
        with open(out_ass, "w", encoding="utf-8") as f: f.write(ass_content)

# ==================================================================================================
# 8. CINEMATIC VIDEO COMPOSITOR & TRANSITION MATRIX
# ==================================================================================================

class VideoCompositor:
    @staticmethod
    def render_scene(img: Path, ass: Path, audio: Path, out_mp4: Path, dur: float, idx: int, is_forensic: bool, cut_sec: float) -> None:
        fps = CONFIG.standards.fps
        frames = max(1, int(dur * fps))
        ass_esc = str(ass.resolve().as_posix()).replace('\\', '/').replace(':', r'\:').replace("'", r"\'")

        cg = "eq=contrast=1.12:brightness=-0.02:saturation=0.85,vignette=PI/3.6"

        if is_forensic or (idx % 4 == 2):
            fc = (
                f"[0:v]split=2[L][R];"
                f"[L]zoompan=z='min(1.05, 1.0+0.0002*on)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=960x1080:fps={fps}[vl];"
                f"[R]zoompan=z='min(1.40, 1.30+0.0003*on)':x='iw*0.3':y='ih*0.2':d={frames}:s=960x1080:fps={fps}[vr];"
                f"[vl][vr]hstack=inputs=2[vh];"
                f"[vh]drawbox=x=958:y=0:w=4:h=1080:color=0xbd1818@0.9:t=fill,{cg},"
                f"subtitles='{ass_esc}',fps={fps},settb=1/{fps},setpts=PTS-STARTPTS[v]"
            )
        elif idx % 3 == 0:
            g_f = int(cut_sec * fps)
            fc = (
                f"[0:v]zoompan=z='min(1.15, 1.05+0.0003*on)':x='min(iw-iw/zoom, (on/{frames})*(iw-iw/zoom))':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={fps},"
                f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.4:t=fill:enable='between(n,{g_f},{g_f+2})',"
                f"{cg},subtitles='{ass_esc}',fps={fps},settb=1/{fps},setpts=PTS-STARTPTS[v]"
            )
        else:
            f1 = int(cut_sec * fps)
            f2 = frames - f1
            fc = (
                f"[0:v]split=2[i1][i2];"
                f"[i1]zoompan=z='min(1.08, 1.0+0.0004*on)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={f1}:s=1920x1080:fps={fps}[v1];"
                f"[i2]zoompan=z='min(1.36, 1.25+0.0003*on)':x='iw/2-(iw/zoom/2)':y='ih*0.22':d={f2}:s=1920x1080:fps={fps},"
                f"fade=t=in:st=0:d=0.08:color=white[v2];"
                f"[v1][v2]concat=n=2:v=1:a=0[vc];"
                f"[vc]{cg},subtitles='{ass_esc}',fps={fps},settb=1/{fps},setpts=PTS-STARTPTS[v]"
            )

        cmd = [
            "ffmpeg", "-y", "-threads", "0", "-loop", "1", "-i", str(img), "-i", str(audio),
            "-filter_complex", fc, "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", CONFIG.standards.preset, "-tune", CONFIG.standards.tune, "-crf", str(CONFIG.standards.crf),
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", CONFIG.standards.audio_bitrate, "-ar", str(CONFIG.standards.audio_sample_rate),
            "-t", str(dur), str(out_mp4)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# ==================================================================================================
# 9. CLOUD DISTRIBUTION ENGINE (GCP INTEGRATION)
# ==================================================================================================

class CloudPublisher:
    @staticmethod
    def get_creds() -> Optional[Credentials]:
        if not (CONFIG.yt_client_id and CONFIG.yt_client_secret): return None
        return Credentials(None, refresh_token=CONFIG.yt_refresh, token_uri="https://oauth2.googleapis.com/token", client_id=CONFIG.yt_client_id, client_secret=CONFIG.yt_client_secret)

    @classmethod
    def to_youtube(cls, vid: Path, title: str, desc: str, tags: List[str]) -> Optional[str]:
        creds = cls.get_creds()
        if not creds: return None
        title = (title[:90] + "...") if len(title) > 90 else title
        log.info(f"Uploading to YouTube: {title}")
        try:
            yt = build("youtube", "v3", credentials=creds)
            body = {"snippet": {"title": title, "description": desc, "tags": tags, "categoryId": "27"}, "status": {"privacyStatus": "public"}}
            media = MediaFileUpload(str(vid), mimetype="video/mp4", resumable=True, chunksize=15*1024*1024)
            req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
            res = None
            while res is None:
                status, res = req.next_chunk()
                if status: log.info(f"YouTube Upload: {int(status.progress()*100)}%")
            return res.get("id")
        except Exception as e:
            log.error(f"YouTube Error: {e}")
            return None

    @classmethod
    def to_drive(cls, vid: Path, folder: str = "Enterprise_Broadcast_Vault") -> Optional[str]:
        creds = cls.get_creds()
        if not creds: return None
        try:
            creds.refresh_token = CONFIG.drive_refresh
            dr = build("drive", "v3", credentials=creds)
            res = dr.files().list(q=f"name='{folder}' and mimeType='application/vnd.google-apps.folder' and trashed=false", fields="files(id)").execute()
            fid = res.get("files", [])[0]["id"] if res.get("files") else dr.files().create(body={"name": folder, "mimeType": "application/vnd.google-apps.folder"}, fields="id").execute()["id"]
            media = MediaFileUpload(str(vid), mimetype="video/mp4", resumable=True)
            upl = dr.files().create(body={"name": vid.name, "parents": [fid]}, media_body=media, fields="id").execute()
            return upl.get("id")
        except Exception as e:
            log.error(f"Drive Error: {e}")
            return None

# ==================================================================================================
# 10. ENTERPRISE PIPELINE ORCHESTRATOR
# ==================================================================================================

class PipelineOrchestrator:
    def __init__(self):
        self.state = PipelineState(CONFIG.paths.checkpoint)
        self.ai = MultiAgentDirector(CONFIG.api_keys)
        self.harvester = AsyncArchiveHarvester()
        self.audio = AudioMasteringRack()

    def execute(self) -> None:
        start_time = datetime.now()
        log.info(f"▶ INITIATING ENTERPRISE PIPELINE. TOPIC: {CONFIG.topic}")

        manifest = self._get_or_create_manifest()
        
        clips, durs = [], []
        total = len(manifest)

        for i, scene in enumerate(manifest):
            text = scene.get("narration", "")
            cat = scene.get("media_type", "PRIMARY_ARCHIVE")
            query = scene.get("search_query", "")
            
            pfx = f"s_{i:03d}"
            c_mp4 = CONFIG.paths.scenes / f"{pfx}.mp4"
            c_wav = CONFIG.paths.cache / f"{pfx}.wav"
            c_mp3 = CONFIG.paths.cache / f"{pfx}.mp3"
            c_img = CONFIG.paths.cache / f"{pfx}.jpg"
            c_ass = CONFIG.paths.cache / f"{pfx}.ass"

            if self.state.is_done(i) and c_mp4.exists():
                clips.append(c_mp4)
                durs.append(self.state.data["durations"].get(str(i), 15.0))
                continue

            log.info(f"Processing Sequence [{i+1}/{total}]")

            ok, src = self.harvester.harvest_sync(query, c_img)
            if not ok:
                self.harvester.generate_procedural_backdrop(c_img)
                src = "Historical Archive"

            if not c_wav.exists() or c_wav.stat().st_size < 1000:
                self.ai.generate_theatrical_voice(text, c_wav)

            probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(c_wav)])
            cut_s = float(probe.decode().strip()) * 0.42
            dur = self.audio.master_scene_audio(c_wav, c_mp3, cat == "PRIMARY_ARCHIVE", i, cut_s)
            durs.append(dur)

            SubtitleRenderer.generate_ass(text, cat, src, dur, c_ass)

            is_f = any(k in text for k in ["شفرة", "تحليل", "دليل", "مقارنة"]) or cat == "FORENSIC_ANALYSIS"
            VideoCompositor.render_scene(c_img, c_ass, c_mp3, c_mp4, dur, i, is_f, cut_s)

            clips.append(c_mp4)
            self.state.mark_done(i, dur)

        log.info("Splicing Master Reel...")
        txt_list = CONFIG.paths.base / "list.txt"
        with open(txt_list, "w", encoding="utf-8") as f:
            for c in clips: f.write(f"file '{c.resolve().as_posix()}'\n")

        out_name = f"Master_{''.join([c for c in CONFIG.topic[:15] if c.isalnum()]).strip()}_{int(time.time())}.mp4"
        final_mp4 = CONFIG.paths.base / out_name
        subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(txt_list), "-c", "copy", str(final_mp4)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

        chapters = "الفصول الزمنية:\n00:00 - المقدمة\n"
        curr_t = 0.0
        last_t = ""
        for i, (sc, d) in enumerate(zip(manifest, durs)):
            ct = sc.get("chapter_title", "")
            if ct and ct != last_t and curr_t > 15:
                chapters += f"{int(curr_t//60):02d}:{int(curr_t%60):02d} - {ct}\n"
                last_t = ct
            curr_t += d

        title = f"تحقيق استقصائي: {CONFIG.topic}"
        desc = f"وثائقي استقصائي شامل يفتح الملفات الأرشيفية الموثقة حول: {CONFIG.topic}.\n\n{chapters}\n#وثائقي #غموض"
        
        CloudPublisher.to_drive(final_mp4)
        CloudPublisher.to_youtube(final_mp4, title, desc, ["وثائقي", "تحقيق", "غموض", "تاريخ"])
        
        log.info(f"✔ PIPELINE COMPLETE. Total Time: {datetime.now() - start_time}")

    def _get_or_create_manifest(self) -> List[Dict[str, Any]]:
        mf = CONFIG.paths.manifest
        if mf.exists():
            try:
                with open(mf, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    log.info("Restored script manifest.")
                    return data
            except Exception: pass
        data = self.ai.orchestrate_script_generation(CONFIG.topic)
        with open(mf, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)
        return data

if __name__ == "__main__":
    try:
        PipelineOrchestrator().execute()
    except KeyboardInterrupt:
        sys.exit(130)
    except Exception as e:
        log.critical(f"SYSTEM FAILURE: {e}", exc_info=True)
        sys.exit(1)
