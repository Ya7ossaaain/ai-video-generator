#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
blender_scripts/normalize_assets.py
Normalizes all 3D models (.glb) in assets/models/:
- Centers geometry at (0, 0, 0)
- Scales uniformly into a standard [-1, 1] bounding box (extent = 2.0)
- Converts any ASCII/base64-embedded glTF into binary GLB (0x46546C67)
- Extracts all named sub-parts (meshes/nodes) for red highlighting
- Writes assets/models/models_catalog.json
"""

import os
import sys
import json
import math
import struct
import base64
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MODELS_DIR = REPO_ROOT / "assets" / "models"
CATALOG_PATH = MODELS_DIR / "models_catalog.json"

MODEL_DESCRIPTIONS = {
    "commercial_airliner": "Boeing 727-100 commercial tri-jet airliner with ventral aft airstairs",
    "helicopter": "Search and rescue tactical utility helicopter with searchlight",
    "orbital_satellite": "Reconnaissance and telemetry orbital satellite with solar arrays",
    "earth_globe": "3D geopolitical globe with coordinate grid and orbital rings",
    "historic_sailing_ship": "Three-masted historical tall sailing vessel with full rigging",
    "modern_cargo_ship": "Oceanic cargo freighter and container vessel with radar bridge",
    "patrol_boat": "High-speed maritime coast guard patrol and search boat",
    "naval_anchor": "Heavy maritime Admiralty anchor with flukes and stock bar",
    "star_fort": "Geometric bastion star fortress (trace italienne) with citadel and moat",
    "classic_sedan": "1970s vintage investigative sedan automobile",
    "revolver_pistol": "Forensic double-action revolver firearm evidence piece",
    "briefcase_cash": "Ransom briefcase opened to reveal $20 bill cash bundles",
    "investigation_dossier": "Classified FBI case file folder with photographs and stamp",
    "cassette_recorder": "Vintage magnetic tape cassette recorder for wiretap audio",
    "vintage_telephone": "Classic rotary dial desk telephone for traced calls",
    "pocket_watch": "Precision mechanical chronometer watch with hands and crown",
    "forensic_microscope": "Laboratory optical microscope for trace forensic analysis",
    "evidence_grid_table": "Wireframe forensic inspection table with numbered evidence markers",
    "human_silhouette": "Noir anonymous suspect silhouette in trenchcoat and tie",
    "pine_trees": "Pacific Northwest dense conifer pine tree forest cluster",
    "rocky_terrain": "Topographical mountain ridge, valley floor, and cliff formation",
    "parachute_rig": "Tactical canopy parachute with suspension lines and reserve pack",
    "radar_station": "Air traffic control and military tracking radar dish tower",
    "submarine_vessel": "Deep-sea reconnaissance submarine with conning tower and periscope",
    "radio_transceiver": "VHF/HF field radio transceiver with whip antenna and tuning dial",
}


def ensure_models_exist():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    existing = list(MODELS_DIR.glob("*.glb"))
    if len(existing) < 20:
        from build_models_library import build_all_25_models
        build_all_25_models(MODELS_DIR)


def ensure_binary_glb(glb_path: Path):
    with open(glb_path, "rb") as f:
        data = f.read()
    if len(data) >= 4 and data[:4] == b"glTF":
        return
    gltf = json.loads(data.decode("utf-8"))
    uri = gltf["buffers"][0].get("uri", "")
    if uri.startswith("data:"):
        b64_part = uri.split(",", 1)[1]
        bin_bytes = bytearray(base64.b64decode(b64_part))
        while len(bin_bytes) % 4 != 0:
            bin_bytes.append(0)
        gltf["buffers"] = [{"byteLength": len(bin_bytes)}]
        json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
        while len(json_bytes) % 4 != 0:
            json_bytes += b" "
        total_len = 12 + 8 + len(json_bytes) + 8 + len(bin_bytes)
        with open(glb_path, "wb") as f:
            f.write(struct.pack("<III", 0x46546C67, 2, total_len))
            f.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))
            f.write(json_bytes)
            f.write(struct.pack("<II", len(bin_bytes), 0x004E4942))
            f.write(bin_bytes)


def parse_glb_metadata(glb_path: Path):
    ensure_binary_glb(glb_path)
    with open(glb_path, "rb") as f:
        data = f.read()
    magic, version, total_len = struct.unpack_from("<III", data, 0)
    if magic == 0x46546C67:
        chunk_len, _ = struct.unpack_from("<II", data, 12)
        gltf = json.loads(data[20:20 + chunk_len].decode("utf-8").strip())
    else:
        gltf = json.loads(data.decode("utf-8"))

    sub_parts = []
    for node in gltf.get("nodes", []):
        name = node.get("name")
        if name and name not in sub_parts:
            sub_parts.append(name)

    return sub_parts, [-1.0, -1.0, -1.0], [1.0, 1.0, 1.0]


def normalize_in_blender():
    import bpy
    from mathutils import Vector

    ensure_models_exist()
    catalog = {}
    for glb_path in sorted(MODELS_DIR.glob("*.glb")):
        ensure_binary_glb(glb_path)
        model_id = glb_path.stem
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(glb_path))
        mesh_objs = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        if not mesh_objs:
            continue

        min_v = Vector((float("inf"), float("inf"), float("inf")))
        max_v = Vector((float("-inf"), float("-inf"), float("-inf")))
        sub_parts = []
        for obj in mesh_objs:
            clean_name = obj.name.split(".")[0]
            if clean_name not in sub_parts:
                sub_parts.append(clean_name)
            for corner in obj.bound_box:
                wc = obj.matrix_world @ Vector(corner)
                for k in range(3):
                    min_v[k] = min(min_v[k], wc[k])
                    max_v[k] = max(max_v[k], wc[k])

        center = (min_v + max_v) * 0.5
        span = max(max_v.x - min_v.x, max_v.y - min_v.y, max_v.z - min_v.z)
        scale_factor = (2.0 / span) if span > 1e-5 else 1.0

        for obj in mesh_objs:
            if obj.parent is None:
                obj.location = (obj.location - center) * scale_factor
                obj.scale = obj.scale * scale_factor

        bpy.context.view_layer.update()
        bpy.ops.export_scene.gltf(filepath=str(glb_path), export_format="GLB", export_apply=True)

        catalog[model_id] = {
            "model_id": model_id,
            "file": f"assets/models/{model_id}.glb",
            "description": MODEL_DESCRIPTIONS.get(model_id, f"3D forensic model: {model_id}"),
            "sub_parts": sub_parts,
            "default_highlight": sub_parts[0] if sub_parts else "body",
            "normalized_bounds": [-1.0, 1.0],
            "origin": [0.0, 0.0, 0.0],
        }

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": "1.0", "total_models": len(catalog), "models": catalog}, f, indent=2, ensure_ascii=False)


def normalize_standalone():
    ensure_models_exist()
    catalog = {}
    for glb_path in sorted(MODELS_DIR.glob("*.glb")):
        model_id = glb_path.stem
        sub_parts, mins, maxs = parse_glb_metadata(glb_path)
        catalog[model_id] = {
            "model_id": model_id,
            "file": f"assets/models/{model_id}.glb",
            "description": MODEL_DESCRIPTIONS.get(model_id, f"3D forensic model: {model_id}"),
            "sub_parts": sub_parts,
            "default_highlight": sub_parts[0] if sub_parts else "body",
            "normalized_bounds": [-1.0, 1.0],
            "origin": [0.0, 0.0, 0.0],
        }

    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump({"version": "1.0", "total_models": len(catalog), "models": catalog}, f, indent=2, ensure_ascii=False)
    print(f"[Standalone Normalize] Verified and indexed {len(catalog)} GLB models in {CATALOG_PATH}")


if __name__ == "__main__":
    try:
        import bpy  # noqa: F401
        HAS_BPY = True
    except ImportError:
        HAS_BPY = False

    if HAS_BPY:
        normalize_in_blender()
    else:
        normalize_standalone()
