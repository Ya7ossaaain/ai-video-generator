# -*- coding: utf-8 -*-
"""
engine/telemetry.py
Professional telemetry logger and ffprobe media verification utilities.
"""

import os
import sys
import json
import logging
import subprocess
from pathlib import Path
from datetime import datetime


class TelemetryFormatter(logging.Formatter):
    def format(self, record):
        ts = datetime.now().strftime("%H:%M:%S")
        lvl = record.levelname.ljust(7)
        return f"{ts} | [{lvl}] | {record.getMessage()}"


def setup_logger(log_file: str = "production_logs.txt") -> logging.Logger:
    logger = logging.getLogger("LEMMiNO_ENGINE")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:
        logger.handlers.clear()

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(TelemetryFormatter())
    logger.addHandler(console_handler)

    try:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(TelemetryFormatter())
        logger.addHandler(file_handler)
    except Exception:
        pass

    return logger


LOGGER = setup_logger()


def log(msg: str, level: str = "info"):
    lvl = level.lower()
    if lvl in ("warn", "warning"):
        LOGGER.warning(msg)
    elif lvl == "error":
        LOGGER.error(msg)
    elif lvl == "debug":
        LOGGER.debug(msg)
    else:
        LOGGER.info(msg)


def run_cmd(cmd: list, timeout: int = 300, cwd=None) -> subprocess.CompletedProcess:
    cmd_strs = [str(c) for c in cmd]
    if cmd_strs and cmd_strs[0] == "ffmpeg" and "-nostdin" not in cmd_strs:
        cmd_strs.insert(1, "-nostdin")
    return subprocess.run(
        cmd_strs,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
        cwd=str(cwd) if cwd else None,
    )


def probe_duration(path) -> float:
    p = Path(path) if path else None
    if not p or not p.exists():
        return 0.0
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(p),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def probe_dimensions(path) -> tuple:
    p = Path(path) if path else None
    if not p or not p.exists():
        return (0, 0)
    try:
        res = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                str(p),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
        raw = res.stdout.strip().splitlines()[0] if res.stdout.strip() else ""
        parts = raw.split("x")
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except Exception:
        pass
    return (0, 0)


def probe_media_info(path) -> dict:
    p = Path(path) if path else None
    if not p or not p.exists():
        return {"valid": False, "width": 0, "height": 0, "duration": 0.0, "size": 0}
    w, h = probe_dimensions(p)
    dur = probe_duration(p)
    sz = p.stat().st_size
    return {
        "valid": (w > 0 and h > 0) or dur > 0.0,
        "width": w,
        "height": h,
        "resolution": f"{w}x{h}" if w and h else "unknown",
        "duration": round(dur, 3),
        "size": sz,
    }


def is_valid_media(path, min_duration: float = 0.05) -> bool:
    p = Path(path) if path else None
    if not p or not p.exists() or p.stat().st_size < 512:
        return False
    return probe_duration(p) >= min_duration


def is_valid_image(path, min_bytes: int = 1024) -> bool:
    p = Path(path) if path else None
    if not p or not p.exists() or p.stat().st_size < min_bytes:
        return False
    w, h = probe_dimensions(p)
    return w >= 64 and h >= 64
