#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Procedural 3D Asset Library Generator for LEMMiNO Hybrid Documentary Engine.
Builds 25 multi-part 3D models (.glb) with separate named nodes/meshes for each sub-part,
centers each model at (0,0,0), normalizes into a standard [-1, 1] bounding box,
and outputs assets/models/models_catalog.json.
"""

import os
import json
import math
import struct
import base64
from pathlib import Path
import numpy as np


def make_box(center=(0, 0, 0), size=(1, 1, 1)):
    cx, cy, cz = center
    sx, sy, sz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    faces = [
        ([(-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz)], (0, 0, 1)),
        ([(-sx, sy, -sz), (sx, sy, -sz), (sx, -sy, -sz), (-sx, -sy, -sz)], (0, 0, -1)),
        ([(-sx, sy, sz), (sx, sy, sz), (sx, sy, -sz), (-sx, sy, -sz)], (0, 1, 0)),
        ([(-sx, -sy, -sz), (sx, -sy, -sz), (sx, -sy, sz), (-sx, -sy, sz)], (0, -1, 0)),
        ([(sx, -sy, sz), (sx, -sy, -sz), (sx, sy, -sz), (sx, sy, sz)], (1, 0, 0)),
        ([(-sx, -sy, -sz), (-sx, -sy, sz), (-sx, sy, sz), (-sx, sy, -sz)], (-1, 0, 0)),
    ]
    verts, norms, idx = [], [], []
    for f_verts, n in faces:
        base = len(verts)
        for vx, vy, vz in f_verts:
            verts.append((vx + cx, vy + cy, vz + cz))
            norms.append(n)
        idx.extend([base, base + 1, base + 2, base, base + 2, base + 3])
    return np.array(verts, dtype=np.float32), np.array(norms, dtype=np.float32), np.array(idx, dtype=np.uint16)


def make_cylinder(center=(0, 0, 0), radius_bottom=0.5, radius_top=0.5, height=1.0, segments=20, axis='Z'):
    cx, cy, cz = center
    half_h = height / 2.0
    verts, norms, idx = [], [], []
    for i in range(segments):
        a0 = 2.0 * math.pi * i / segments
        a1 = 2.0 * math.pi * (i + 1) / segments
        c0, s0 = math.cos(a0), math.sin(a0)
        c1, s1 = math.cos(a1), math.sin(a1)
        p00 = (radius_bottom * c0, radius_bottom * s0, -half_h)
        p10 = (radius_bottom * c1, radius_bottom * s1, -half_h)
        p11 = (radius_top * c1, radius_top * s1, half_h)
        p01 = (radius_top * c0, radius_top * s0, half_h)
        n0 = (c0, s0, 0.0)
        n1 = (c1, s1, 0.0)
        base = len(verts)
        for p, n in [(p00, n0), (p10, n1), (p11, n1), (p01, n0)]:
            verts.append(p)
            norms.append(n)
        idx.extend([base, base + 1, base + 2, base, base + 2, base + 3])

    if radius_top > 1e-4:
        top_center_idx = len(verts)
        verts.append((0.0, 0.0, half_h))
        norms.append((0.0, 0.0, 1.0))
        for i in range(segments):
            a0 = 2.0 * math.pi * i / segments
            a1 = 2.0 * math.pi * (i + 1) / segments
            b = len(verts)
            verts.append((radius_top * math.cos(a0), radius_top * math.sin(a0), half_h))
            norms.append((0.0, 0.0, 1.0))
            verts.append((radius_top * math.cos(a1), radius_top * math.sin(a1), half_h))
            norms.append((0.0, 0.0, 1.0))
            idx.extend([top_center_idx, b, b + 1])

    if radius_bottom > 1e-4:
        bot_center_idx = len(verts)
        verts.append((0.0, 0.0, -half_h))
        norms.append((0.0, 0.0, -1.0))
        for i in range(segments):
            a0 = 2.0 * math.pi * i / segments
            a1 = 2.0 * math.pi * (i + 1) / segments
            b = len(verts)
            verts.append((radius_bottom * math.cos(a1), radius_bottom * math.sin(a1), -half_h))
            norms.append((0.0, 0.0, -1.0))
            verts.append((radius_bottom * math.cos(a0), radius_bottom * math.sin(a0), -half_h))
            norms.append((0.0, 0.0, -1.0))
            idx.extend([bot_center_idx, b, b + 1])

    v_arr = np.array(verts, dtype=np.float32)
    n_arr = np.array(norms, dtype=np.float32)
    if axis == 'X':
        v_arr = v_arr[:, [2, 1, 0]]
        n_arr = n_arr[:, [2, 1, 0]]
    elif axis == 'Y':
        v_arr = v_arr[:, [0, 2, 1]]
        n_arr = n_arr[:, [0, 2, 1]]
    v_arr += np.array([cx, cy, cz], dtype=np.float32)
    return v_arr, n_arr, np.array(idx, dtype=np.uint16)


def make_sphere(center=(0, 0, 0), radius=0.5, rings=14, sectors=20, scale=(1.0, 1.0, 1.0)):
    cx, cy, cz = center
    sx, sy, sz = scale
    verts, norms, idx = [], [], []
    for r in range(rings + 1):
        phi = math.pi * r / rings
        for s in range(sectors + 1):
            theta = 2.0 * math.pi * s / sectors
            nx = math.sin(phi) * math.cos(theta)
            ny = math.sin(phi) * math.sin(theta)
            nz = math.cos(phi)
            verts.append((cx + radius * sx * nx, cy + radius * sy * ny, cz + radius * sz * nz))
            norms.append((nx, ny, nz))
    for r in range(rings):
        for s in range(sectors):
            first = r * (sectors + 1) + s
            second = first + sectors + 1
            idx.extend([first, second, first + 1, second, second + 1, first + 1])
    return np.array(verts, dtype=np.float32), np.array(norms, dtype=np.float32), np.array(idx, dtype=np.uint16)


def make_grid_surface(center=(0, 0, 0), width=2.0, depth=2.0, nx=24, ny=24, height_fn=None):
    cx, cy, cz = center
    verts, norms, idx = [], [], []
    xs = np.linspace(-width / 2.0, width / 2.0, nx)
    ys = np.linspace(-depth / 2.0, depth / 2.0, ny)
    z_grid = np.zeros((nx, ny), dtype=np.float32)
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            z_grid[i, j] = height_fn(x, y) if height_fn else 0.0
    for i, x in enumerate(xs):
        for j, y in enumerate(ys):
            z = z_grid[i, j]
            dzdx = (z_grid[min(nx - 1, i + 1), j] - z_grid[max(0, i - 1), j]) / (width / max(1, nx - 1))
            dzdy = (z_grid[i, min(ny - 1, j + 1)] - z_grid[i, max(0, j - 1)]) / (depth / max(1, ny - 1))
            n = np.array([-dzdx, -dzdy, 1.0], dtype=np.float32)
            n /= (np.linalg.norm(n) + 1e-8)
            verts.append((cx + x, cy + y, cz + z))
            norms.append(tuple(n))
    for i in range(nx - 1):
        for j in range(ny - 1):
            v0 = i * ny + j
            v1 = (i + 1) * ny + j
            v2 = (i + 1) * ny + (j + 1)
            v3 = i * ny + (j + 1)
            idx.extend([v0, v1, v2, v0, v2, v3])
    return np.array(verts, dtype=np.float32), np.array(norms, dtype=np.float32), np.array(idx, dtype=np.uint16)


def merge_geoms(geoms):
    all_v, all_n, all_i = [], [], []
    offset = 0
    for v, n, i in geoms:
        all_v.append(v)
        all_n.append(n)
        all_i.append(i + offset)
        offset += len(v)
    return (
        np.vstack(all_v).astype(np.float32),
        np.vstack(all_n).astype(np.float32),
        np.concatenate(all_i).astype(np.uint16),
    )


def normalize_parts(parts_dict, target_extent=2.0):
    all_pts = np.vstack([v for v, _, _ in parts_dict.values()])
    mins = all_pts.min(axis=0)
    maxs = all_pts.max(axis=0)
    center = (mins + maxs) / 2.0
    max_span = float(np.max(maxs - mins))
    scale = (target_extent / max_span) if max_span > 1e-6 else 1.0
    normalized = {}
    for name, (v, n, idx) in parts_dict.items():
        v_norm = (v - center) * scale
        normalized[name] = (v_norm.astype(np.float32), n.astype(np.float32), idx.astype(np.uint16))
    return normalized


def export_glb_and_embedded(parts_dict, out_glb_path):
    parts_dict = normalize_parts(parts_dict, target_extent=2.0)

    buffer_bytes = bytearray()
    buffer_views = []
    accessors = []
    meshes = []
    nodes = []

    materials = [
        {
            "name": "LEMMiNO_Clay_Dark",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.08, 0.085, 0.095, 1.0],
                "metallicFactor": 0.2,
                "roughnessFactor": 0.7,
            },
            "doubleSided": True,
        }
    ]

    for part_name, (verts, norms, indices) in parts_dict.items():
        v_bytes = verts.astype(np.float32).tobytes()
        n_bytes = norms.astype(np.float32).tobytes()
        i_bytes = indices.astype(np.uint16).tobytes()

        def append_aligned(data_bytes, target):
            while len(buffer_bytes) % 4 != 0:
                buffer_bytes.append(0)
            offset = len(buffer_bytes)
            buffer_bytes.extend(data_bytes)
            while len(buffer_bytes) % 4 != 0:
                buffer_bytes.append(0)
            bv_idx = len(buffer_views)
            bv = {"buffer": 0, "byteOffset": offset, "byteLength": len(data_bytes)}
            if target:
                bv["target"] = target
            buffer_views.append(bv)
            return bv_idx

        bv_v = append_aligned(v_bytes, 34962)
        bv_n = append_aligned(n_bytes, 34962)
        bv_i = append_aligned(i_bytes, 34963)

        v_min = verts.min(axis=0).tolist()
        v_max = verts.max(axis=0).tolist()

        acc_v = len(accessors)
        accessors.append({
            "bufferView": bv_v,
            "byteOffset": 0,
            "componentType": 5126,
            "count": int(len(verts)),
            "type": "VEC3",
            "min": [round(float(x), 5) for x in v_min],
            "max": [round(float(x), 5) for x in v_max],
        })

        acc_n = len(accessors)
        accessors.append({
            "bufferView": bv_n,
            "byteOffset": 0,
            "componentType": 5126,
            "count": int(len(norms)),
            "type": "VEC3",
        })

        acc_i = len(accessors)
        accessors.append({
            "bufferView": bv_i,
            "byteOffset": 0,
            "componentType": 5123,
            "count": int(len(indices)),
            "type": "SCALAR",
        })

        mesh_idx = len(meshes)
        meshes.append({
            "name": part_name,
            "primitives": [{
                "attributes": {"POSITION": acc_v, "NORMAL": acc_n},
                "indices": acc_i,
                "material": 0,
                "mode": 4,
            }],
        })

        nodes.append({"name": part_name, "mesh": mesh_idx})

    gltf_bin_dict = {
        "asset": {"version": "2.0", "generator": "LEMMiNO Hybrid Engine Asset Builder"},
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(buffer_bytes)}],
    }

    json_str = json.dumps(gltf_bin_dict, separators=(",", ":"))
    json_bytes = json_str.encode("utf-8")
    while len(json_bytes) % 4 != 0:
        json_bytes += b" "

    total_len = 12 + 8 + len(json_bytes) + 8 + len(buffer_bytes)
    with open(out_glb_path, "wb") as f:
        f.write(struct.pack("<III", 0x46546C67, 2, total_len))
        f.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
        f.write(json_bytes)
        f.write(struct.pack("<II", len(buffer_bytes), 0x004E4942))
        f.write(buffer_bytes)


def build_all_25_models(models_dir: Path):
    models_dir.mkdir(parents=True, exist_ok=True)
    catalog = {}

    airliner_parts = {
        "fuselage": merge_geoms([
            make_cylinder((0.0, 0.0, 0.0), 0.16, 0.16, 1.8, 24, axis='X'),
            make_cylinder((-1.05, 0.0, -0.02), 0.02, 0.16, 0.35, 20, axis='X'),
            make_cylinder((1.02, 0.0, 0.03), 0.16, 0.04, 0.30, 20, axis='X'),
        ]),
        "cockpit": make_box((-0.88, 0.0, 0.09), (0.24, 0.22, 0.12)),
        "wings": merge_geoms([
            make_box((0.05, -0.75, -0.04), (0.38, 1.35, 0.04)),
            make_box((0.05, 0.75, -0.04), (0.38, 1.35, 0.04)),
        ]),
        "flaps": merge_geoms([
            make_box((0.26, -0.65, -0.06), (0.10, 1.05, 0.03)),
            make_box((0.26, 0.65, -0.06), (0.10, 1.05, 0.03)),
        ]),
        "landing_gear": merge_geoms([
            make_cylinder((-0.78, 0.0, -0.22), 0.02, 0.02, 0.22, 12, axis='Z'),
            make_cylinder((-0.78, 0.0, -0.32), 0.06, 0.06, 0.05, 14, axis='Y'),
            make_cylinder((0.12, -0.28, -0.22), 0.025, 0.025, 0.24, 12, axis='Z'),
            make_cylinder((0.12, -0.28, -0.34), 0.08, 0.08, 0.07, 14, axis='Y'),
            make_cylinder((0.12, 0.28, -0.22), 0.025, 0.025, 0.24, 12, axis='Z'),
            make_cylinder((0.12, 0.28, -0.34), 0.08, 0.08, 0.07, 14, axis='Y'),
        ]),
        "aft_stairs": merge_geoms([
            make_box((0.82, 0.0, -0.22), (0.36, 0.12, 0.03)),
            make_box((0.72, 0.0, -0.15), (0.16, 0.12, 0.03)),
        ]),
        "engines": merge_geoms([
            make_cylinder((0.68, -0.24, 0.06), 0.07, 0.06, 0.34, 16, axis='X'),
            make_cylinder((0.68, 0.24, 0.06), 0.07, 0.06, 0.34, 16, axis='X'),
            make_cylinder((0.88, 0.0, 0.22), 0.07, 0.06, 0.36, 16, axis='X'),
            make_box((0.95, 0.0, 0.35), (0.28, 0.04, 0.42)),
            make_box((1.02, 0.0, 0.56), (0.24, 0.62, 0.03)),
        ]),
    }

    helicopter_parts = {
        "fuselage": merge_geoms([
            make_sphere((-0.15, 0.0, 0.0), 0.36, scale=(1.5, 0.85, 0.9)),
            make_cylinder((0.55, 0.0, 0.05), 0.10, 0.04, 0.95, 14, axis='X'),
        ]),
        "cockpit_glass": make_sphere((-0.38, 0.0, 0.04), 0.28, scale=(1.1, 0.78, 0.75)),
        "main_rotor": merge_geoms([
            make_cylinder((-0.12, 0.0, 0.38), 0.04, 0.04, 0.14, 12, axis='Z'),
            make_box((-0.12, 0.0, 0.44), (1.85, 0.09, 0.02)),
            make_box((-0.12, 0.0, 0.44), (0.09, 1.85, 0.02)),
        ]),
        "tail_rotor": merge_geoms([
            make_box((0.98, 0.0, 0.18), (0.14, 0.03, 0.32)),
            make_box((1.0, 0.06, 0.22), (0.04, 0.02, 0.42)),
            make_box((1.0, 0.06, 0.22), (0.42, 0.02, 0.04)),
        ]),
        "landing_skids": merge_geoms([
            make_cylinder((-0.15, -0.26, -0.38), 0.025, 0.025, 1.05, 10, axis='X'),
            make_cylinder((-0.15, 0.26, -0.38), 0.025, 0.025, 1.05, 10, axis='X'),
        ]),
        "searchlight": make_cylinder((-0.55, 0.0, -0.24), 0.07, 0.05, 0.14, 14, axis='X'),
    }

    satellite_parts = {
        "core_bus": make_cylinder((0.0, 0.0, 0.0), 0.28, 0.28, 0.65, 8, axis='Z'),
        "solar_array_left": make_box((-0.95, 0.0, 0.0), (1.25, 0.48, 0.02)),
        "solar_array_right": make_box((0.95, 0.0, 0.0), (1.25, 0.48, 0.02)),
        "dish_antenna": make_cylinder((0.0, 0.0, 0.42), 0.34, 0.06, 0.14, 20, axis='Z'),
        "optical_sensor": make_cylinder((0.0, 0.26, -0.12), 0.11, 0.09, 0.28, 16, axis='Y'),
    }

    globe_parts = {
        "sphere_core": make_sphere((0.0, 0.0, 0.0), 0.72, rings=18, sectors=24),
        "continents_shell": make_sphere((0.0, 0.0, 0.0), 0.74, rings=10, sectors=14),
        "equator_ring": make_cylinder((0.0, 0.0, 0.0), 0.84, 0.84, 0.03, 32, axis='Z'),
        "orbital_ring": make_cylinder((0.0, 0.0, 0.0), 0.96, 0.96, 0.025, 32, axis='X'),
    }

    sailing_ship_parts = {
        "hull": make_box((0.0, 0.0, -0.25), (1.55, 0.44, 0.28)),
        "quarterdeck": make_box((0.55, 0.0, -0.04), (0.48, 0.42, 0.18)),
        "main_mast": make_cylinder((0.0, 0.0, 0.38), 0.035, 0.02, 1.15, 12, axis='Z'),
        "fore_mast": make_cylinder((-0.45, 0.0, 0.32), 0.03, 0.018, 0.95, 12, axis='Z'),
        "sails": merge_geoms([
            make_box((0.0, 0.0, 0.42), (0.04, 0.68, 0.52)),
            make_box((-0.45, 0.0, 0.36), (0.04, 0.56, 0.44)),
        ]),
        "rudder": make_box((0.84, 0.0, -0.28), (0.14, 0.03, 0.26)),
    }

    cargo_ship_parts = {
        "hull": make_box((0.0, 0.0, -0.18), (1.85, 0.42, 0.26)),
        "bridge_tower": make_box((0.62, 0.0, 0.16), (0.28, 0.36, 0.44)),
        "cargo_containers": make_box((-0.20, 0.0, 0.05), (0.95, 0.36, 0.22)),
        "radar_mast": make_cylinder((0.62, 0.0, 0.48), 0.02, 0.01, 0.24, 10, axis='Z'),
        "propeller_stern": make_cylinder((0.94, 0.0, -0.26), 0.07, 0.07, 0.06, 12, axis='X'),
    }

    patrol_boat_parts = {
        "hull": make_box((0.05, 0.0, -0.12), (1.35, 0.48, 0.20)),
        "cabin": make_box((-0.05, 0.0, 0.08), (0.55, 0.36, 0.22)),
        "radar_arch": make_box((0.12, 0.0, 0.28), (0.08, 0.34, 0.18)),
        "outboard_motor": make_box((0.76, 0.0, -0.08), (0.14, 0.16, 0.28)),
        "searchlight_mount": make_cylinder((-0.28, 0.0, 0.24), 0.05, 0.04, 0.12, 12, axis='X'),
    }

    anchor_parts = {
        "shank": make_cylinder((0.0, 0.0, 0.05), 0.06, 0.05, 1.35, 14, axis='Z'),
        "stock_bar": make_cylinder((0.0, 0.0, 0.52), 0.04, 0.04, 0.85, 12, axis='X'),
        "crown": make_box((0.0, 0.0, -0.62), (0.78, 0.14, 0.16)),
        "flukes": merge_geoms([
            make_cylinder((-0.42, 0.0, -0.42), 0.12, 0.02, 0.38, 10, axis='Z'),
            make_cylinder((0.42, 0.0, -0.42), 0.12, 0.02, 0.38, 10, axis='Z'),
        ]),
        "shackle_ring": make_cylinder((0.0, 0.0, 0.78), 0.14, 0.14, 0.05, 18, axis='Y'),
    }

    star_fort_parts = {
        "outer_bastions": merge_geoms([
            make_cylinder((0.65 * math.cos(2 * math.pi * k / 5), 0.65 * math.sin(2 * math.pi * k / 5), 0.0), 0.28, 0.22, 0.24, 4, axis='Z')
            for k in range(5)
        ]),
        "curtain_walls": make_cylinder((0.0, 0.0, 0.0), 0.62, 0.58, 0.22, 10, axis='Z'),
        "inner_citadel": make_cylinder((0.0, 0.0, 0.12), 0.32, 0.30, 0.32, 5, axis='Z'),
        "watchtowers": merge_geoms([
            make_cylinder((0.55 * math.cos(2 * math.pi * k / 5), 0.55 * math.sin(2 * math.pi * k / 5), 0.18), 0.06, 0.05, 0.22, 8, axis='Z')
            for k in range(5)
        ]),
        "moat_perimeter": make_cylinder((0.0, 0.0, -0.14), 0.96, 0.96, 0.04, 20, axis='Z'),
    }

    sedan_parts = {
        "body_chassis": make_box((0.0, 0.0, -0.06), (1.65, 0.68, 0.26)),
        "hood": make_box((-0.55, 0.0, 0.02), (0.52, 0.64, 0.14)),
        "trunk": make_box((0.58, 0.0, 0.01), (0.46, 0.64, 0.14)),
        "windshield": make_box((-0.02, 0.0, 0.18), (0.72, 0.58, 0.24)),
        "wheels": merge_geoms([
            make_cylinder((-0.52, -0.36, -0.20), 0.16, 0.16, 0.08, 16, axis='Y'),
            make_cylinder((-0.52, 0.36, -0.20), 0.16, 0.16, 0.08, 16, axis='Y'),
            make_cylinder((0.52, -0.36, -0.20), 0.16, 0.16, 0.08, 16, axis='Y'),
            make_cylinder((0.52, 0.36, -0.20), 0.16, 0.16, 0.08, 16, axis='Y'),
        ]),
        "headlights": merge_geoms([
            make_cylinder((-0.83, -0.22, -0.02), 0.06, 0.06, 0.04, 12, axis='X'),
            make_cylinder((-0.83, 0.22, -0.02), 0.06, 0.06, 0.04, 12, axis='X'),
        ]),
    }

    revolver_parts = {
        "frame": make_box((0.0, 0.0, 0.05), (0.55, 0.10, 0.24)),
        "barrel": make_cylinder((-0.52, 0.0, 0.14), 0.055, 0.055, 0.62, 16, axis='X'),
        "cylinder": make_cylinder((-0.04, 0.0, 0.08), 0.13, 0.13, 0.24, 12, axis='X'),
        "grip": make_box((0.32, 0.0, -0.22), (0.20, 0.11, 0.44)),
        "trigger": make_box((0.06, 0.0, -0.12), (0.08, 0.03, 0.12)),
        "hammer": make_box((0.26, 0.0, 0.22), (0.10, 0.03, 0.10)),
    }

    briefcase_parts = {
        "lower_shell": make_box((0.0, 0.0, -0.12), (1.35, 0.95, 0.22)),
        "upper_lid": make_box((0.0, 0.42, 0.28), (1.35, 0.18, 0.68)),
        "handle": make_box((0.0, -0.54, -0.12), (0.36, 0.08, 0.05)),
        "locks": merge_geoms([
            make_box((-0.42, -0.48, -0.04), (0.10, 0.05, 0.08)),
            make_box((0.42, -0.48, -0.04), (0.10, 0.05, 0.08)),
        ]),
        "cash_bundles": merge_geoms([
            make_box((-0.36 + 0.36 * ix, -0.18 + 0.28 * iy, -0.01), (0.28, 0.20, 0.10))
            for ix in range(3) for iy in range(2)
        ]),
    }

    dossier_parts = {
        "folder_cover": make_box((0.0, 0.0, -0.04), (1.35, 1.05, 0.04)),
        "classified_documents": make_box((-0.05, 0.02, 0.01), (1.18, 0.88, 0.03)),
        "evidence_photos": make_box((-0.32, 0.18, 0.07), (0.42, 0.36, 0.02)),
        "paperclip": make_box((-0.48, 0.36, 0.09), (0.14, 0.05, 0.02)),
        "red_stamp_tab": make_box((0.35, 0.28, 0.08), (0.38, 0.14, 0.025)),
    }

    cassette_parts = {
        "main_casing": make_box((0.0, 0.0, 0.0), (1.40, 0.88, 0.28)),
        "tape_deck_door": make_box((-0.28, 0.05, 0.16), (0.64, 0.44, 0.04)),
        "reel_left": make_cylinder((-0.42, 0.05, 0.19), 0.10, 0.10, 0.03, 16, axis='Z'),
        "reel_right": make_cylinder((-0.14, 0.05, 0.19), 0.10, 0.10, 0.03, 16, axis='Z'),
        "speaker_grille": make_box((0.38, 0.05, 0.15), (0.46, 0.46, 0.03)),
        "control_buttons": make_box((-0.15, -0.38, 0.08), (0.65, 0.12, 0.08)),
    }

    telephone_parts = {
        "base_housing": make_box((0.0, 0.0, -0.14), (0.92, 0.82, 0.26)),
        "rotary_dial": make_cylinder((0.0, -0.22, 0.06), 0.24, 0.24, 0.05, 20, axis='Z'),
        "cradle_forks": make_box((0.0, 0.14, 0.20), (0.52, 0.08, 0.14)),
        "handset": make_cylinder((0.0, 0.14, 0.28), 0.06, 0.06, 0.78, 14, axis='X'),
    }

    watch_parts = {
        "case_body": make_cylinder((0.0, 0.0, -0.04), 0.68, 0.68, 0.16, 28, axis='Z'),
        "bezel_ring": make_cylinder((0.0, 0.0, 0.05), 0.70, 0.64, 0.06, 28, axis='Z'),
        "dial_face": make_cylinder((0.0, 0.0, 0.05), 0.60, 0.60, 0.02, 28, axis='Z'),
        "hour_hand": make_box((0.14, 0.08, 0.08), (0.32, 0.04, 0.02)),
        "minute_hand": make_box((-0.06, 0.22, 0.09), (0.04, 0.46, 0.02)),
        "crown_winder": make_cylinder((0.0, 0.78, 0.0), 0.08, 0.08, 0.14, 14, axis='Y'),
    }

    microscope_parts = {
        "base_plate": make_box((0.0, 0.0, -0.58), (0.68, 0.82, 0.12)),
        "arm_column": make_box((0.0, 0.26, -0.10), (0.14, 0.16, 0.86)),
        "eyepiece_tube": make_cylinder((0.0, -0.12, 0.52), 0.07, 0.06, 0.42, 16, axis='Z'),
        "objective_turret": make_cylinder((0.0, -0.12, 0.16), 0.12, 0.12, 0.12, 16, axis='Z'),
        "specimen_stage": make_box((0.0, -0.10, -0.14), (0.48, 0.48, 0.05)),
        "focus_knobs": make_cylinder((0.0, 0.26, -0.22), 0.09, 0.09, 0.28, 14, axis='X'),
    }

    evidence_table_parts = {
        "table_frame": make_box((0.0, 0.0, 0.15), (1.75, 1.05, 0.06)),
        "wire_grid_surface": make_box((0.0, 0.0, 0.19), (1.68, 0.98, 0.02)),
        "legs": merge_geoms([
            make_box((-0.80, -0.46, -0.25), (0.06, 0.06, 0.78)),
            make_box((0.80, -0.46, -0.25), (0.06, 0.06, 0.78)),
            make_box((-0.80, 0.46, -0.25), (0.06, 0.06, 0.78)),
            make_box((0.80, 0.46, -0.25), (0.06, 0.06, 0.78)),
        ]),
        "evidence_markers": make_cylinder((-0.35, -0.15, 0.26), 0.08, 0.02, 0.14, 4, axis='Z'),
        "specimen_trays": make_box((0.25, 0.12, 0.23), (0.34, 0.26, 0.05)),
    }

    human_parts = {
        "head": make_sphere((0.0, 0.0, 0.74), 0.14, rings=12, sectors=16),
        "torso": make_box((0.0, 0.0, 0.30), (0.38, 0.22, 0.56)),
        "trenchcoat": make_cylinder((0.0, 0.0, 0.05), 0.28, 0.20, 0.68, 14, axis='Z'),
        "arms": merge_geoms([
            make_box((-0.26, 0.0, 0.26), (0.11, 0.12, 0.52)),
            make_box((0.26, 0.0, 0.26), (0.11, 0.12, 0.52)),
        ]),
        "legs": merge_geoms([
            make_box((-0.10, 0.0, -0.48), (0.13, 0.14, 0.68)),
            make_box((0.10, 0.0, -0.48), (0.13, 0.14, 0.68)),
        ]),
        "tie_collar": make_box((0.0, -0.12, 0.42), (0.07, 0.03, 0.28)),
    }

    pine_parts = {
        "forest_floor_base": make_cylinder((0.0, 0.0, -0.58), 0.85, 0.88, 0.08, 20, axis='Z'),
        "trunks": make_cylinder((0.0, 0.0, -0.25), 0.06, 0.04, 0.65, 10, axis='Z'),
        "lower_canopy": make_cylinder((0.0, 0.0, -0.02), 0.38, 0.08, 0.44, 12, axis='Z'),
        "mid_canopy": make_cylinder((0.0, 0.0, 0.26), 0.30, 0.05, 0.42, 12, axis='Z'),
        "upper_canopy": make_cylinder((0.0, 0.0, 0.52), 0.20, 0.01, 0.38, 12, axis='Z'),
    }

    terrain_parts = {
        "valley_floor": make_grid_surface(
            (0.0, 0.0, -0.15), 1.9, 1.9, 20, 20,
            lambda x, y: 0.18 * math.sin(2.5 * x) * math.cos(2.5 * y)
        ),
        "main_ridge": make_cylinder((-0.38, 0.15, 0.14), 0.48, 0.08, 0.56, 7, axis='Z'),
        "cliff_face": make_cylinder((0.42, -0.24, 0.10), 0.42, 0.10, 0.48, 6, axis='Z'),
        "boulder_cluster": make_sphere((0.12, 0.35, -0.05), 0.16, rings=6, sectors=8),
    }

    parachute_parts = {
        "canopy_dome": make_sphere((0.0, 0.0, 0.55), 0.68, rings=10, sectors=18, scale=(1.0, 1.0, 0.45)),
        "suspension_lines": make_cylinder((0.0, 0.0, 0.05), 0.32, 0.12, 0.72, 8, axis='Z'),
        "harness_pack": make_box((0.0, 0.0, -0.45), (0.28, 0.18, 0.38)),
        "ripcord_handle": make_box((0.18, -0.11, -0.38), (0.08, 0.04, 0.08)),
    }

    radar_parts = {
        "pedestal_tower": make_cylinder((0.0, 0.0, -0.32), 0.24, 0.16, 0.65, 8, axis='Z'),
        "rotary_azimuth_mount": make_box((0.0, 0.0, 0.08), (0.26, 0.26, 0.18)),
        "parabolic_dish": make_cylinder((0.0, -0.14, 0.34), 0.56, 0.12, 0.18, 22, axis='Y'),
        "feed_horn": make_cylinder((0.0, -0.42, 0.34), 0.04, 0.02, 0.38, 10, axis='Y'),
        "control_bunker": make_box((0.48, 0.22, -0.48), (0.46, 0.38, 0.28)),
    }

    submarine_parts = {
        "pressure_hull": make_cylinder((0.0, 0.0, 0.0), 0.18, 0.18, 1.45, 20, axis='X'),
        "conning_tower": make_box((-0.18, 0.0, 0.24), (0.34, 0.12, 0.26)),
        "periscope_mast": make_cylinder((-0.22, 0.0, 0.46), 0.018, 0.018, 0.22, 10, axis='Z'),
        "dive_planes": make_box((-0.18, 0.0, 0.26), (0.12, 0.38, 0.02)),
        "propeller_shroud": make_cylinder((0.96, 0.0, 0.0), 0.11, 0.11, 0.08, 16, axis='X'),
    }

    radio_parts = {
        "chassis_box": make_box((0.0, 0.0, -0.08), (1.15, 0.58, 0.56)),
        "tuning_dial": make_cylinder((0.28, -0.31, -0.05), 0.14, 0.14, 0.06, 18, axis='Y'),
        "frequency_scale": make_box((-0.18, -0.30, 0.06), (0.52, 0.03, 0.18)),
        "whip_antenna": make_cylinder((-0.44, 0.18, 0.52), 0.02, 0.008, 0.85, 10, axis='Z'),
        "microphone_handset": make_box((0.68, -0.10, -0.14), (0.16, 0.14, 0.28)),
        "toggle_switches": make_box((-0.20, -0.31, -0.18), (0.42, 0.05, 0.06)),
    }

    definitions = [
        ("commercial_airliner", "Boeing 727-100 commercial tri-jet airliner with ventral aft airstairs", airliner_parts),
        ("helicopter", "Search and rescue tactical utility helicopter with searchlight", helicopter_parts),
        ("orbital_satellite", "Reconnaissance and telemetry orbital satellite with solar arrays", satellite_parts),
        ("earth_globe", "3D geopolitical globe with coordinate grid and orbital rings", globe_parts),
        ("historic_sailing_ship", "Three-masted historical tall sailing vessel with full rigging", sailing_ship_parts),
        ("modern_cargo_ship", "Oceanic cargo freighter and container vessel with radar bridge", cargo_ship_parts),
        ("patrol_boat", "High-speed maritime coast guard patrol and search boat", patrol_boat_parts),
        ("naval_anchor", "Heavy maritime Admiralty anchor with flukes and stock bar", anchor_parts),
        ("star_fort", "Geometric bastion star fortress (trace italienne) with citadel and moat", star_fort_parts),
        ("classic_sedan", "1970s vintage investigative sedan automobile", sedan_parts),
        ("revolver_pistol", "Forensic double-action revolver firearm evidence piece", revolver_parts),
        ("briefcase_cash", "Ransom briefcase opened to reveal $20 bill cash bundles", briefcase_parts),
        ("investigation_dossier", "Classified FBI case file folder with photographs and stamp", dossier_parts),
        ("cassette_recorder", "Vintage magnetic tape cassette recorder for wiretap audio", cassette_parts),
        ("vintage_telephone", "Classic rotary dial desk telephone for traced calls", telephone_parts),
        ("pocket_watch", "Precision mechanical chronometer watch with hands and crown", watch_parts),
        ("forensic_microscope", "Laboratory optical microscope for trace forensic analysis", microscope_parts),
        ("evidence_grid_table", "Wireframe forensic inspection table with numbered evidence markers", evidence_table_parts),
        ("human_silhouette", "Noir anonymous suspect silhouette in trenchcoat and tie", human_parts),
        ("pine_trees", "Pacific Northwest dense conifer pine tree forest cluster", pine_parts),
        ("rocky_terrain", "Topographical mountain ridge, valley floor, and cliff formation", terrain_parts),
        ("parachute_rig", "Tactical canopy parachute with suspension lines and reserve pack", parachute_parts),
        ("radar_station", "Air traffic control and military tracking radar dish tower", radar_parts),
        ("submarine_vessel", "Deep-sea reconnaissance submarine with conning tower and periscope", submarine_parts),
        ("radio_transceiver", "VHF/HF field radio transceiver with whip antenna and tuning dial", radio_parts),
    ]

    for model_id, desc, parts in definitions:
        glb_path = models_dir / f"{model_id}.glb"
        export_glb_and_embedded(parts, glb_path)
        catalog[model_id] = {
            "model_id": model_id,
            "file": f"assets/models/{model_id}.glb",
            "description": desc,
            "sub_parts": list(parts.keys()),
            "default_highlight": list(parts.keys())[0],
            "normalized_bounds": [-1.0, 1.0],
            "origin": [0.0, 0.0, 0.0],
        }

    catalog_path = models_dir / "models_catalog.json"
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump({"version": "1.0", "total_models": len(catalog), "models": catalog}, f, indent=2, ensure_ascii=False)

    print(f"Built {len(catalog)} normalized 3D models in {models_dir} and wrote {catalog_path}")


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent
    build_all_25_models(repo_root / "assets" / "models")
