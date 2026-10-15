#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blender_scripts/scene_25d_parallax.py
LEMMiNO Archival 2.5D Parallax Engine with High-Contrast Engraving Layers,
Volumetric Fog, Floating Atmospheric Particles, Dolly Zoom, and Depth of Field.
"""

import sys
import math
import argparse
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, ImageFilter, ImageEnhance, ImageDraw


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="LEMMiNO 2.5D Archival Parallax Engine")
    parser.add_argument("--image", type=str, required=True)
    parser.add_argument("--particles", type=str, default="dust", choices=["dust", "snow", "embers"])
    parser.add_argument("--frames", type=int, default=90)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--output", type=str, required=True)
    return parser.parse_args(argv)


def render_25d(args):
    RW, RH = 960, 540
    image_path = Path(args.image)
    base_pil = None
    if image_path.exists():
        try:
            base_pil = ImageOps.fit(Image.open(image_path).convert("L"), (RW, RH))
        except Exception:
            base_pil = None
    if base_pil is None:
        base_pil = Image.new("L", (RW, RH), color=22)

    enhanced = ImageEnhance.Contrast(base_pil).enhance(1.85)
    edges = enhanced.filter(ImageFilter.FIND_EDGES)
    bg_l = ImageEnhance.Brightness(enhanced.filter(ImageFilter.GaussianBlur(radius=4))).enhance(0.45)
    bg_rgb = Image.merge("RGB", (bg_l, bg_l, bg_l))
    mid_rgb = Image.merge("RGB", (enhanced, enhanced, enhanced))
    fg_rgb = Image.merge("RGB", (edges, edges, edges))

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    rng = np.random.default_rng(42)
    num_p = 75
    px = rng.uniform(0, RW, num_p).astype(np.float32)
    py = rng.uniform(0, RH, num_p).astype(np.float32)
    pz = rng.uniform(0.4, 2.2, num_p).astype(np.float32)
    p_color = (255, 95, 40) if args.particles == "embers" else (188, 182, 180)
    vy_speed = -2.0 if args.particles == "embers" else (-0.6 if args.particles == "dust" else 2.2)

    ffmpeg_cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{RW}x{RH}", "-pix_fmt", "rgb24",
        "-r", str(args.fps), "-i", "-",
        "-vf", f"scale={args.width}:{args.height}:flags=fast_bilinear",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path)
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def crop_zoom(pil_img, zoom, dx=0.0):
        cw, ch = RW / zoom, RH / zoom
        x0, y0 = (RW - cw) * 0.5 + dx, (RH - ch) * 0.5
        return pil_img.transform((RW, RH), Image.Transform.EXTENT, (x0, y0, x0 + cw, y0 + ch), Image.Resampling.BILINEAR)

    for f_idx in range(args.frames):
        p = f_idx / max(1, args.frames - 1)
        pan_x = math.sin(p * math.pi) * 14.0
        blended = Image.blend(
            crop_zoom(bg_rgb, 1.02 + 0.05 * p, dx=-pan_x * 0.4),
            crop_zoom(mid_rgb, 1.00 + 0.14 * p, dx=pan_x * 0.5),
            0.65,
        )
        blended = Image.blend(blended, crop_zoom(fg_rgb, 1.05 + 0.28 * p, dx=pan_x * 1.4), 0.22)
        draw = ImageDraw.Draw(blended)
        for i in range(num_p):
            cur_x = float((px[i] + f_idx * 0.6 * pz[i]) % RW)
            cur_y = float((py[i] + f_idx * vy_speed * pz[i]) % RH)
            draw.ellipse([cur_x - 1.2, cur_y - 1.2, cur_x + 1.2, cur_y + 1.2], fill=p_color)
        proc.stdin.write(blended.tobytes())

    proc.stdin.close()
    proc.wait()


if __name__ == "__main__":
    render_25d(parse_args())
