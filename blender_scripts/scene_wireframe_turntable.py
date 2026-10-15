#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blender_scripts/scene_wireframe_turntable.py
LEMMiNO Noir Minimalist 3D Wireframe / Clay Turntable Engine with Red Highlight Sub-Part.
"""

import os
import sys
import json
import math
import time
import struct
import base64
import argparse
import subprocess
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
MODELS_DIR = REPO_ROOT / "assets" / "models"


def parse_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="LEMMiNO 3D Wireframe/Clay Turntable Renderer")
    parser.add_argument("--model", type=str, default="commercial_airliner")
    parser.add_argument("--highlight_part", type=str, default="aft_stairs")
    parser.add_argument("--style", type=str, default="wireframe", choices=["wireframe", "clay"])
    parser.add_argument("--frames", type=int, default=90)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--anchors_out", type=str, default="")
    return parser.parse_args(argv)


def load_glb_meshes(glb_path: Path):
    with open(glb_path, "rb") as f:
        data = f.read()
    if data[:4] == b"glTF":
        json_len, _ = struct.unpack_from("<II", data, 12)
        gltf = json.loads(data[20:20 + json_len].decode("utf-8").strip())
        bin_data = data[20 + json_len + 8:]
    else:
        gltf = json.loads(data.decode("utf-8"))
        uri = gltf["buffers"][0].get("uri", "")
        bin_data = base64.b64decode(uri.split(",", 1)[1])

    bvs = gltf["bufferViews"]
    accs = gltf["accessors"]
    meshes = gltf["meshes"]
    parts = {}

    for node in gltf.get("nodes", []):
        name = node.get("name", "part")
        m_idx = node.get("mesh")
        if m_idx is None:
            continue
        prim = meshes[m_idx]["primitives"][0]
        acc_v = accs[prim["attributes"]["POSITION"]]
        bv_v = bvs[acc_v["bufferView"]]
        v_start = bv_v.get("byteOffset", 0) + acc_v.get("byteOffset", 0)
        verts = np.frombuffer(bin_data, dtype=np.float32, count=acc_v["count"] * 3, offset=v_start).reshape(-1, 3)

        acc_n = accs[prim["attributes"]["NORMAL"]]
        bv_n = bvs[acc_n["bufferView"]]
        n_start = bv_n.get("byteOffset", 0) + acc_n.get("byteOffset", 0)
        norms = np.frombuffer(bin_data, dtype=np.float32, count=acc_n["count"] * 3, offset=n_start).reshape(-1, 3)

        acc_i = accs[prim["indices"]]
        bv_i = bvs[acc_i["bufferView"]]
        i_start = bv_i.get("byteOffset", 0) + acc_i.get("byteOffset", 0)
        dtype_i = np.uint16 if acc_i["componentType"] == 5123 else np.uint32
        indices = np.frombuffer(bin_data, dtype=dtype_i, count=acc_i["count"], offset=i_start).reshape(-1, 3)
        parts[name] = (verts.copy(), norms.copy(), indices.copy())
    return parts


def render_software_3d(args):
    import cairo

    glb_path = MODELS_DIR / f"{args.model}.glb"
    if not glb_path.exists():
        from blender_scripts.normalize_assets import ensure_models_exist
        ensure_models_exist()
    if not glb_path.exists():
        glb_path = MODELS_DIR / "commercial_airliner.glb"

    parts = load_glb_meshes(glb_path)
    all_v = np.vstack([v for v, _, _ in parts.values()])
    b_center = (all_v.min(axis=0) + all_v.max(axis=0)) * 0.5
    b_span = float(np.max(all_v.max(axis=0) - all_v.min(axis=0)))
    scale = 1.9 / max(b_span, 1e-4)

    RW, RH = 960, 540
    sx_out, sy_out = args.width / RW, args.height / RH
    focal = RH * 1.15
    cam_dist = 3.25
    pitch = math.radians(22.0)
    cp, sp = math.cos(pitch), math.sin(pitch)

    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

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
    anchors = []

    for f_idx in range(args.frames):
        progress = f_idx / max(1, args.frames - 1)
        yaw = math.radians(-35.0 + 95.0 * progress)
        cy, sy = math.cos(yaw), math.sin(yaw)
        rot_z = np.array([[cy, -sy, 0.0], [sy, cy, 0.0], [0.0, 0.0, 1.0]], dtype=np.float32)
        rot_x = np.array([[1.0, 0.0, 0.0], [0.0, cp, -sp], [0.0, sp, cp]], dtype=np.float32)
        rot = rot_x @ rot_z

        ctx.set_source_rgb(0.035, 0.038, 0.045)
        ctx.paint()

        highlight_screen_pts, fallback_screen_pts, part_draw_data = [], [], []
        for part_name, (verts, norms, indices) in parts.items():
            v_cam = ((verts - b_center) * scale) @ rot.T
            z_safe = np.maximum(v_cam[:, 1] + cam_dist, 0.2)
            u = RW * 0.5 + (v_cam[:, 0] * focal) / z_safe
            v = RH * 0.5 - (v_cam[:, 2] * focal) / z_safe
            screen_uv = np.stack([u, v], axis=-1)
            is_high = bool(args.highlight_part and args.highlight_part.lower() in part_name.lower())
            if is_high:
                highlight_screen_pts.append(screen_uv)
            fallback_screen_pts.append(screen_uv)
            part_draw_data.append((float(z_safe.mean()), is_high, screen_uv, indices))

        part_draw_data.sort(key=lambda x: x[0], reverse=True)
        for _, is_high, screen_uv, indices in part_draw_data:
            for tri in screen_uv[indices]:
                ctx.move_to(float(tri[0, 0]), float(tri[0, 1]))
                ctx.line_to(float(tri[1, 0]), float(tri[1, 1]))
                ctx.line_to(float(tri[2, 0]), float(tri[2, 1]))
                ctx.close_path()
            if is_high:
                ctx.set_source_rgba(0.898, 0.145, 0.129, 0.88)
                ctx.fill_preserve()
                ctx.set_source_rgba(1.0, 0.35, 0.32, 0.95)
                ctx.set_line_width(1.3)
                ctx.stroke()
            else:
                ctx.set_source_rgba(0.06, 0.065, 0.075, 0.92)
                ctx.fill_preserve()
                ctx.set_source_rgba(0.86, 0.88, 0.92, 0.85)
                ctx.set_line_width(0.9)
                ctx.stroke()

        target_pts = highlight_screen_pts if highlight_screen_pts else fallback_screen_pts
        all_target_uv = np.vstack(target_pts)
        anchors.append({
            "frame": f_idx,
            "x": int(np.clip(all_target_uv[:, 0].mean() * sx_out, 160, args.width - 160)),
            "y": int(np.clip(all_target_uv[:, 1].mean() * sy_out, 160, args.height - 160)),
        })
        surface.flush()
        proc.stdin.write(surface.get_data())

    proc.stdin.close()
    proc.wait()
    if args.anchors_out:
        Path(args.anchors_out).write_text(json.dumps({"anchors": anchors}), encoding="utf-8")


if __name__ == "__main__":
    render_software_3d(parse_args())
