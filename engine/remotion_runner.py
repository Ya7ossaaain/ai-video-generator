# -*- coding: utf-8 -*-
"""
engine/remotion_runner.py
Executes Remotion CLI compositions (`VectorMapTracker`, `ForensicDossier`, `HudOverlay`,
`DocumentScanner`, `TimelineComparison`, `ChapterCard`) with dynamic JSON props,
and provides a high-speed Cairo + Pillow RTL Arabic renderer when running in offline environments.
"""

import os
import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
import cairo
from PIL import Image, ImageDraw, ImageFont

from engine.config import CONFIG, TARGET_W, TARGET_H, TARGET_FPS
from engine.telemetry import log, is_valid_media

ARABIC_FONT_PATHS = [
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
    "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
MONO_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _load_font(paths, size: int):
    for p in paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


class RemotionRunner:
    def __init__(self):
        self.remotion_dir = CONFIG.remotion_dir
        self.npx_bin = shutil.which("npx")

    def is_remotion_cli_ready(self) -> bool:
        cli_dir = self.remotion_dir / "node_modules" / "@remotion" / "cli"
        return bool(self.npx_bin and cli_dir.exists())

    def render_composition(
        self,
        composition_id: str,
        props: Dict[str, Any],
        exact_frames: int,
        output_path: Path,
        background_video: Optional[Path] = None,
    ) -> Path:
        props = dict(props)
        props["durationInFrames"] = exact_frames
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if self.is_remotion_cli_ready() and background_video is None:
            props_file = output_path.parent / f"_props_{output_path.stem}.json"
            with open(props_file, "w", encoding="utf-8") as f:
                json.dump(props, f, ensure_ascii=False)
            cmd = [
                self.npx_bin,
                "remotion",
                "render",
                composition_id,
                str(output_path.resolve()),
                f"--props={props_file.resolve()}",
                f"--frames=0-{max(1, exact_frames - 1)}",
                "--concurrency=2",
            ]
            try:
                res = subprocess.run(
                    cmd,
                    cwd=str(self.remotion_dir),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=240,
                )
                props_file.unlink(missing_ok=True)
                if res.returncode == 0 and is_valid_media(output_path):
                    return output_path
                log(f"⚠️ Remotion CLI fallback triggered for {composition_id}: {res.stderr[:200]}", "warning")
            except Exception as exc:
                props_file.unlink(missing_ok=True)
                log(f"⚠️ Remotion CLI exception for {composition_id} ({exc}); using native Cairo/Pillow renderer.", "warning")

        if composition_id == "HudOverlay" and background_video and background_video.exists():
            return self._composite_hud_over_video(background_video, props, exact_frames, output_path)

        return self._render_native_motion_graphics(composition_id, props, exact_frames, output_path)

    def _composite_hud_over_video(
        self,
        bg_video: Path,
        props: Dict[str, Any],
        exact_frames: int,
        output_path: Path,
    ) -> Path:
        RW, RH = TARGET_W, TARGET_H
        hud_png = output_path.parent / f"_hud_overlay_{output_path.stem}.png"

        anchors = props.get("anchors", [])
        mid_anchor = anchors[len(anchors) // 2] if anchors else {"x": 960, "y": 540}
        tx = int(mid_anchor.get("x", 960))
        ty = int(mid_anchor.get("y", 540))

        img = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        font_ar = _load_font(ARABIC_FONT_PATHS, 28)
        font_mono = _load_font(MONO_FONT_PATHS, 18)
        font_sm = _load_font(MONO_FONT_PATHS, 15)

        c_red = (229, 37, 33, 255)
        c_white = (245, 248, 252, 245)
        draw.line([(40, 95), (40, 40), (95, 40)], fill=c_red, width=3)
        draw.line([(1880, 95), (1880, 40), (1825, 40)], fill=c_red, width=3)
        draw.line([(40, 985), (40, 1040), (95, 1040)], fill=c_red, width=3)
        draw.line([(1880, 985), (1880, 1040), (1825, 1040)], fill=c_red, width=3)

        box_x = 1240 if tx < 1100 else 180
        box_y = 260
        elbow_x = tx + (95 if box_x > tx else -95)
        elbow_y = box_y + 45

        draw.ellipse([tx - 9, ty - 9, tx + 9, ty + 9], fill=c_red)
        draw.ellipse([tx - 24, ty - 24, tx + 24, ty + 24], outline=c_red, width=2)
        draw.line([(tx, ty), (elbow_x, elbow_y), (box_x, elbow_y)], fill=c_white, width=3)

        draw.rectangle([box_x, box_y, box_x + 520, box_y + 135], fill=(8, 11, 16, 230), outline=c_white, width=2)
        draw.rectangle([box_x + 512, box_y, box_x + 520, box_y + 135], fill=c_red)
        draw.text((box_x + 22, box_y + 18), str(props.get("hud_label", "3D FORENSIC TELEMETRY")), fill=c_red, font=font_mono)
        draw.text((box_x + 22, box_y + 52), str(props.get("arabicTitle", "تحليل البنية الهندسية للمجسم"))[:42], fill=c_white, font=font_ar)
        draw.text((box_x + 22, box_y + 98), f"PART LOCK: {props.get('highlightPart', 'PRIMARY_NODE').upper()}", fill=(148, 163, 184, 255), font=font_sm)

        draw.rectangle([70, 48, 920, 132], fill=(8, 11, 16, 220), outline=(45, 55, 72, 255), width=1)
        draw.rectangle([70, 48, 76, 132], fill=c_red)
        draw.text((96, 58), str(props.get("modelName", "LEMMiNO 3D ASSET INSPECTOR")), fill=c_white, font=font_mono)
        draw.text((96, 92), f"COORDS: {props.get('coordinates', '45.9214 N, 122.2819 W')} // 30 FPS SYNC", fill=c_red, font=font_sm)

        img.save(hud_png)

        subprocess.run([
            "ffmpeg", "-nostdin", "-y",
            "-i", str(bg_video),
            "-i", str(hud_png),
            "-filter_complex", "[0:v][1:v]overlay=0:0:format=auto",
            "-frames:v", str(exact_frames),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(output_path),
        ], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        hud_png.unlink(missing_ok=True)
        return output_path

    def _render_native_motion_graphics(
        self,
        composition_id: str,
        props: Dict[str, Any],
        exact_frames: int,
        output_path: Path,
    ) -> Path:
        RW, RH = 960, 540
        font_ar = _load_font(ARABIC_FONT_PATHS, 22)
        font_ar_lg = _load_font(ARABIC_FONT_PATHS, 32)
        font_mono = _load_font(MONO_FONT_PATHS, 14)

        overlay_pil = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_pil)

        title_ar = str(props.get("arabicTitle") or props.get("arabicHeader") or props.get("arabicRole") or "تحليل الأدلة الجنائية والبيانات")
        sub_en = str(props.get("title") or props.get("englishSubtitle") or props.get("documentTitle") or composition_id.upper())

        draw.rectangle([40, 28, RW - 40, 96], fill=(10, 14, 20, 225), outline=(40, 52, 68, 255), width=1)
        draw.rectangle([RW - 45, 28, RW - 40, 96], fill=(229, 37, 33, 255))
        draw.text((60, 38), sub_en[:55], fill=(229, 37, 33, 255), font=font_mono)
        draw.text((60, 60), title_ar[:55], fill=(245, 248, 252, 255), font=font_ar)

        if composition_id == "ForensicDossier":
            draw.rectangle([50, 120, 340, 480], fill=(14, 18, 26, 230), outline=(55, 68, 88, 255), width=2)
            draw.text((70, 435), str(props.get("subjectName", "DAN COOPER // #305")), fill=(255, 255, 255, 255), font=font_mono)
            points = [
                ("✓  تطابق الأدلة المادية مع سجلات التحقيق الفيدرالي", (46, 204, 113, 255)),
                ("✓  توثيق التسلسل الزمني وشهادات الشهود العيان", (46, 204, 113, 255)),
                ("✗  غياب التطابق البيومتري الحاسم في الأرشيف", (229, 37, 33, 255)),
            ]
            for idx, (pt_txt, col) in enumerate(points):
                by = 135 + idx * 110
                draw.rectangle([370, by, RW - 50, by + 88], fill=(14, 18, 26, 230), outline=col, width=2)
                draw.text((395, by + 28), pt_txt, fill=(245, 248, 252, 255), font=font_ar)

        elif composition_id == "DocumentScanner":
            draw.rectangle([90, 125, RW - 90, 475], fill=(18, 22, 30, 240), outline=(70, 82, 102, 255), width=2)
            quote = str(props.get("highlightedQuote", "DECLASSIFIED ARCHIVAL RECORD // FLIGHT 305"))
            draw.text((125, 160), "NATIONAL ARCHIVES // FORENSIC EXHIBIT", fill=(148, 163, 184, 255), font=font_mono)
            draw.text((125, 240), quote[:52], fill=(255, 255, 255, 255), font=font_mono)
            draw.text((125, 340), title_ar[:58], fill=(245, 248, 252, 255), font=font_ar)
            draw.rectangle([RW - 310, 405, RW - 120, 450], outline=(229, 37, 33, 255), width=3)
            draw.text((RW - 295, 418), "VERIFIED EVIDENCE", fill=(229, 37, 33, 255), font=font_mono)

        elif composition_id == "ChapterCard":
            overlay_pil = Image.new("RGBA", (RW, RH), (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay_pil)
            draw.text((RW // 2 - 180, 195), sub_en[:45], fill=(229, 37, 33, 255), font=font_mono)
            draw.text((RW // 2 - 240, 245), title_ar[:45], fill=(255, 255, 255, 255), font=font_ar_lg)

        r, g, b, a = overlay_pil.split()
        bgra_pil = Image.merge("RGBA", (b, g, r, a))
        overlay_surface = cairo.ImageSurface.create_for_data(
            bytearray(bgra_pil.tobytes()), cairo.FORMAT_ARGB32, RW, RH
        )

        ffmpeg_cmd = [
            "ffmpeg", "-nostdin", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{RW}x{RH}", "-pix_fmt", "bgr0",
            "-r", str(TARGET_FPS), "-i", "-",
            "-vf", f"scale={TARGET_W}:{TARGET_H}:flags=fast_bilinear",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(output_path),
        ]
        proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, RW, RH)
        ctx = cairo.Context(surface)

        for f_idx in range(exact_frames):
            prog = f_idx / max(1, exact_frames - 1)
            ctx.set_source_rgb(0.024, 0.030, 0.042)
            ctx.paint()

            ctx.set_source_rgba(0.10, 0.14, 0.20, 0.45)
            ctx.set_line_width(0.8)
            for gx in range(0, RW, 60):
                ctx.move_to(gx, 0)
                ctx.line_to(gx, RH)
            for gy in range(0, RH, 60):
                ctx.move_to(0, gy)
                ctx.line_to(RW, gy)
            ctx.stroke()

            if composition_id == "VectorMapTracker":
                pts = [(220, 420), (480, 290), (740, 170)]
                ctx.set_source_rgba(0.90, 0.14, 0.13, 0.16)
                ctx.rectangle(390, 210, 210, 150)
                ctx.fill_preserve()
                ctx.set_source_rgba(0.90, 0.14, 0.13, 0.75)
                ctx.set_dash([8.0, 5.0])
                ctx.stroke()
                ctx.set_dash([])

                ctx.set_source_rgba(0.90, 0.14, 0.13, 0.95)
                ctx.set_line_width(3.0)
                ctx.move_to(*pts[0])
                if prog < 0.5:
                    p2 = prog * 2.0
                    ix = pts[0][0] + (pts[1][0] - pts[0][0]) * p2
                    iy = pts[0][1] + (pts[1][1] - pts[0][1]) * p2
                    ctx.line_to(ix, iy)
                else:
                    p2 = (prog - 0.5) * 2.0
                    ctx.line_to(*pts[1])
                    ix = pts[1][0] + (pts[2][0] - pts[1][0]) * p2
                    iy = pts[1][1] + (pts[2][1] - pts[1][1]) * p2
                    ctx.line_to(ix, iy)
                ctx.stroke()

                pulse_r = 10.0 + 48.0 * ((f_idx % 30) / 30.0)
                ctx.set_source_rgba(0.90, 0.14, 0.13, 1.0 - ((f_idx % 30) / 30.0))
                ctx.set_line_width(2.0)
                ctx.arc(480, 290, pulse_r, 0, 2 * math.pi)
                ctx.stroke()

            elif composition_id == "DocumentScanner":
                hl_w = 640.0 * min(1.0, max(0.0, (prog - 0.15) / 0.65))
                ctx.set_source_rgba(0.90, 0.14, 0.13, 0.45)
                ctx.rectangle(118, 232, hl_w, 34)
                ctx.fill()

            elif composition_id == "TimelineComparison":
                wipe_x = 120.0 + (RW - 240.0) * prog
                ctx.set_source_rgba(0.90, 0.14, 0.13, 0.85)
                ctx.set_line_width(3.0)
                ctx.move_to(120, 310)
                ctx.line_to(wipe_x, 310)
                ctx.stroke()
                for n_idx in range(4):
                    nx = 160 + n_idx * 210
                    active = wipe_x >= nx
                    ctx.set_source_rgba(0.18, 0.80, 0.44, 0.95) if active else ctx.set_source_rgba(0.35, 0.40, 0.48, 0.7)
                    ctx.arc(nx, 310, 14, 0, 2 * math.pi)
                    ctx.fill()

            elif composition_id == "ChapterCard":
                line_w = 380.0 * min(1.0, prog * 1.8)
                ctx.set_source_rgba(0.90, 0.14, 0.13, 0.95)
                ctx.rectangle(RW * 0.5 - line_w * 0.5, 310, line_w, 3)
                ctx.fill()

            ctx.set_source_surface(overlay_surface, 0, 0)
            ctx.paint()

            surface.flush()
            proc.stdin.write(surface.get_data())

        proc.stdin.close()
        proc.wait()
        return output_path
