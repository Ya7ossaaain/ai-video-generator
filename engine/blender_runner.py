# -*- coding: utf-8 -*-
"""
engine/blender_runner.py
Executes Blender Headless CLI scripts (`normalize_assets.py`, `scene_wireframe_turntable.py`,
`scene_25d_parallax.py`, `scene_terrain_ocean.py`) with automatic Xvfb/EEVEE detection
and high-speed software 3D GLB fallback.
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from engine.config import CONFIG, TARGET_W, TARGET_H, TARGET_FPS
from engine.telemetry import log


class BlenderRunner:
    def __init__(self):
        self.blender_bin = shutil.which("blender")
        self.xvfb_bin = shutil.which("xvfb-run")

    def _run_blender_script(self, script_name: str, script_args: list, timeout: int = 240) -> bool:
        script_path = CONFIG.blender_scripts_dir / script_name
        env = os.environ.copy()
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"

        if self.blender_bin:
            cmd = []
            if self.xvfb_bin:
                cmd.extend([self.xvfb_bin, "-a"])
            cmd.extend([self.blender_bin, "-b", "-P", str(script_path), "--"])
            cmd.extend([str(a) for a in script_args])
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout, env=env)
                if res.returncode == 0:
                    return True
                log(f"⚠️ Blender CLI returned {res.returncode} for {script_name}; activating software 3D engine.", "warning")
            except Exception as exc:
                log(f"⚠️ Blender CLI exception for {script_name} ({exc}); activating software 3D engine.", "warning")

        cmd_py = [sys.executable, str(script_path)] + [str(a) for a in script_args]
        res_py = subprocess.run(cmd_py, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        if res_py.returncode != 0:
            log(f"❌ خطأ في تشغيل {script_name}: {res_py.stderr[:300]}", "error")
            return False
        return True

    def normalize_all_models(self) -> bool:
        log("📐 معايرة وفهرسة حقيبة المجسمات ثلاثية الأبعاد (normalize_assets.py)...")
        return self._run_blender_script("normalize_assets.py", [])

    def render_wireframe_turntable(
        self,
        model_id: str,
        highlight_part: str,
        style: str,
        exact_frames: int,
        output_path: Path,
        anchors_out: Optional[Path] = None,
    ) -> Path:
        args = [
            "--model", model_id,
            "--highlight_part", highlight_part,
            "--style", style,
            "--frames", str(exact_frames),
            "--fps", str(TARGET_FPS),
            "--width", str(TARGET_W),
            "--height", str(TARGET_H),
            "--output", str(output_path),
        ]
        if anchors_out:
            args.extend(["--anchors_out", str(anchors_out)])

        self._run_blender_script("scene_wireframe_turntable.py", args)
        return output_path

    def render_25d_parallax(
        self,
        image_path: Path,
        particles: str,
        exact_frames: int,
        output_path: Path,
    ) -> Path:
        args = [
            "--image", str(image_path),
            "--particles", particles,
            "--frames", str(exact_frames),
            "--fps", str(TARGET_FPS),
            "--width", str(TARGET_W),
            "--height", str(TARGET_H),
            "--output", str(output_path),
        ]
        self._run_blender_script("scene_25d_parallax.py", args)
        return output_path

    def render_terrain_ocean(
        self,
        mode: str,
        coords: str,
        exact_frames: int,
        output_path: Path,
    ) -> Path:
        args = [
            "--mode", mode,
            "--coords", coords,
            "--frames", str(exact_frames),
            "--fps", str(TARGET_FPS),
            "--width", str(TARGET_W),
            "--height", str(TARGET_H),
            "--output", str(output_path),
        ]
        self._run_blender_script("scene_terrain_ocean.py", args)
        return output_path
