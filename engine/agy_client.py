# -*- coding: utf-8 -*-
"""
engine/agy_client.py
Wrapper for calling the `agy` CLI (`gemini-3.8-flash`) with Strict Quota Law enforcement
(maximum 3-4 batched JSON calls per episode; zero per-image loops) and resilient extract_json.
"""

import re
import json
import time
import shutil
import subprocess
from typing import Optional, Any
from engine.config import AGY_MODEL, MAX_AGY_CALLS_PER_EPISODE
from engine.telemetry import log


def extract_json(text: str) -> Optional[Any]:
    if not text:
        return None
    cleaned = text.strip()

    fence_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
    if fence_match:
        candidate = fence_match.group(1).strip()
        try:
            return json.loads(candidate)
        except Exception:
            cleaned = candidate

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        sub = cleaned[first_brace:last_brace + 1]
        sub_fixed = re.sub(r",\s*([}\]])", r"\1", sub)
        try:
            return json.loads(sub_fixed)
        except Exception:
            pass

    first_bracket = cleaned.find("[")
    last_bracket = cleaned.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        sub = cleaned[first_bracket:last_bracket + 1]
        sub_fixed = re.sub(r",\s*([}\]])", r"\1", sub)
        try:
            return json.loads(sub_fixed)
        except Exception:
            pass

    return None


class AgyQuotaClient:
    def __init__(self, max_calls: int = MAX_AGY_CALLS_PER_EPISODE):
        self.max_calls = max_calls
        self.calls_made = 0

    def is_available(self) -> bool:
        return shutil.which("agy") is not None

    def call_json(
        self,
        prompt: str,
        effort_level: str = "high",
        purpose: str = "batched_task",
        max_retries: int = 2,
        timeout: int = 420,
    ) -> Optional[Any]:
        if self.calls_made >= self.max_calls:
            log(
                f"🛑 [Strict Quota Law] تم بلوغ الحد الأقصى لاستدعاءات agy ({self.max_calls}). تخطي الاستدعاء ({purpose}).",
                "warning",
            )
            return None

        if not self.is_available():
            log(f"⚠️ أداة الطرفية agy غير مثبتة في هذه البيئة؛ تفعيل البديل الهندسي لـ ({purpose}).", "warning")
            return None

        self.calls_made += 1
        call_num = self.calls_made
        log(f"⚡ [AGY Call #{call_num}/{self.max_calls}] ({purpose}) | model={AGY_MODEL} | effort={effort_level}")

        cmd = [
            "agy",
            "--model", "gemini-3.8-flash",
            "--effort", effort_level,  # "high" للتخطيط والسيناريو، "medium" للمهام البصرية
            "--dangerously-skip-permissions",
            "-p", prompt,
        ]

        for attempt in range(1, max_retries + 1):
            try:
                res = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=timeout,
                )
                parsed = extract_json(res.stdout)
                if parsed is not None:
                    log(f"✅ [AGY Call #{call_num}] نجح استخراج JSON من المحاولة {attempt}.")
                    return parsed
                log(f"⚠️ [AGY Call #{call_num}] فشل تحليل JSON في المحاولة {attempt}/{max_retries}.", "warning")
            except subprocess.TimeoutExpired:
                log(f"⚠️ [AGY Call #{call_num}] انتهت مهلة الاستدعاء في المحاولة {attempt}.", "warning")
            except Exception as exc:
                log(f"⚠️ [AGY Call #{call_num}] خطأ أثناء الاستدعاء: {exc}", "warning")
            time.sleep(2)

        return None


AGY_CLIENT = AgyQuotaClient()
