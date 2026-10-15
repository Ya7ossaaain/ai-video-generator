#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blender_scripts/scene_terrain_ocean.py
LEMMiNO 3D Topographical Terrain & Animated Ocean Surface Engine.
"""

import sys
import math
import argparse
import subprocess
from pathlib import Path
import numpy as np
import cairo


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="LEMMiNO 3D Terrain & Ocean Engine")
    parser.add_argument("--mode", type=str, default="terrain", choices=["terrain", "ocean"])
    parser.add_argument("--coords", type=str, default="45.92° N, 122.28° W")
    parser.add_argument("--frames", type=int, default=90)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--output", type=str, required=True)
    return parser.parse_args(argv)


def render_terrain_ocean(args):
    RW, RH = 960, 540
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    nx, ny = 36, 36
    xs = np.linspace(-3.2, 3.2, nx, dtype=np.float32)
    ys = np.linspace(-3.2, 3.2, ny, dtype=np.float32)
    X, Y = np.meshgrid(xs, ys)

    focal = RH * 1.05
    cam_dist = 4.6
    pitch = math.radians(58.0)
    cp, sp = math.cos(pitch), math.sin(pitch)

    ffmpeg_cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-f", "rawvideo", "-vcodec", "rawvideo",
        "-s", f"{RW}x{RH}", "-pix_fmt", "bgr0",
        "-r", str(args.fps), "-i", "-",
        "-vf", f"scale={args.width}:{args.height}:flags=fast_bilinear",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
        "-pix_fmt", "yuv420p", str(out_path)
    ]
    proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, RW, RH)
    ctx = cairo.Context(surface)

    for f_idx in range(args.frames):
        p = f_idx / max(1, args.frames - 1)
        phase = f_idx * 0.11 if args.mode == "ocean" else p * 0.25
        if args.mode == "ocean":
            Z = 0.16 * np.sin(2.2 * X + phase) * np.cos(2.0 * Y + phase * 0.8)
        else:
            Z = (0.55 * np.sin(1.1 * X) * np.cos(1.1 * Y) + 0.28 * np.cos(2.3 * X - 1.7 * Y)) * np.exp(-0.08 * (X ** 2 + Y ** 2))

        yaw = math.radians(-18.0 + 36.0 * p)
        cy, sy = math.cos(yaw), math.sin(yaw)
        xr = cy * X - sy * Y
        yr = sy * X + cy * Y
        yc = np.maximum(cp * yr - sp * Z + cam_dist, 0.3)
        zc = sp * yr + cp * Z - 0.35

        u = RW * 0.5 + (xr * focal) / yc
        v = RH * 0.5 - (zc * focal) / yc

        ctx.set_source_rgb(0.03, 0.035, 0.045)
        ctx.paint()
        ctx.set_line_width(0.85)
        ctx.set_source_rgba(0.65, 0.67, 0.72, 0.75)
        for r in range(ny):
            ctx.move_to(float(u[r, 0]), float(v[r, 0]))
            for c in range(1, nx):
                ctx.line_to(float(u[r, c]), float(v[r, c]))
        ctx.stroke()

        bx, by = float(u[ny // 2, nx // 2]), float(v[ny // 2, nx // 2])
        ctx.set_source_rgba(0.90, 0.14, 0.13, 0.95)
        ctx.arc(bx, by, 4.0, 0, 2 * math.pi)
        ctx.fill()
        surface.flush()
        proc.stdin.write(surface.get_data())

    proc.stdin.close()
    proc.wait()


if __name__ == "__main__":
    render_terrain_ocean(parse_args())
