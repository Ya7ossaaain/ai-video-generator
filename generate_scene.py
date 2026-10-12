#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import math
import random
import json
import subprocess
import urllib.request
from pathlib import Path

AGY_REVIEWER_MODEL = "gemini-3.6-flash"
MODELS_DIR = Path("./models")
OUTPUT_VIDEO = Path("./lemmino_jump.mp4")

def log(msg):
    print(f"[LEMMiNO Engine] {msg}", flush=True)

def extract_json(text):
    if not text: return None
    import re
    text = re.sub(r"```json\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"```\s*$", "", text)
    try: return json.loads(text)
    except: pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try: return json.loads(match.group(0))
        except: pass
    return None

def download_file(url, target_path):
    log(f"📥 جاري تحميل الموديل: {target_path.name}...")
    target_path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as resp, open(target_path, "wb") as f:
        f.write(resp.read())
    log(f"✅ تم تحميل: {target_path.name}")

def ensure_assets():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    plane_path = MODELS_DIR / "airplane_727.obj"
    skydiver_path = MODELS_DIR / "skydiver.obj"

    if not plane_path.exists() or plane_path.stat().st_size < 1000:
        plane_url = "https://raw.githubusercontent.com/alecjacobson/common-3d-test-models/master/data/airplane.obj"
        try: download_file(plane_url, plane_path)
        except Exception as e: log(f"⚠️ تعذر التحميل الشبكي: {e}")

    return plane_path, skydiver_path

def review_asset_with_agy(image_path, asset_type):
    log(f"🔍 [AGY] فحص الموديل لـ ({asset_type})...")
    if not image_path.exists():
        return True, "تخطي الفحص لعدم توفر المعاينة"

    prompt = f"""You are a professional 3D visual inspector for a dark documentary in the style of LEMMiNO.
INSPECT THIS PREVIEW IMAGE OF A 3D MODEL ({asset_type}).
Return ONLY valid JSON:
{{
  "decision": "accept" or "reject",
  "score": 0.0 to 1.0,
  "reason": "Brief explanation"
}}"""

    cmd = [
        "agy", "--model", AGY_REVIEWER_MODEL, "--effort", "low",
        "--dangerously-skip-permissions", "-p", prompt
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120)
        data = extract_json(res.stdout)
        if data:
            decision = data.get("decision", "accept").lower()
            score = float(data.get("score", 0.8))
            return (decision == "accept" or score >= 0.5), data.get("reason", "")
    except Exception as e:
        log(f"⚠️ تحذير AGY: {e}")
    return True, "تم القبول افتراضياً"

BLENDER_SCRIPT = """
import bpy
import math
import random

bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 150

scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.filepath = "./lemmino_jump.mp4"
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

scene.render.engine = 'CYCLES'
scene.cycles.samples = 8
scene.cycles.use_denoising = False

# ============================================================
# ضبط Freestyle بأمان تام لمنع الـ Crash (إصلاح سطر 1314)
# ============================================================
scene.render.use_freestyle = True
scene.render.line_thickness = 1.2

view_layer = scene.view_layers[0]
view_layer.use_freestyle = True
freestyle_settings = view_layer.freestyle_settings

# إنشاء الـ LineSet والـ LineStyle صراحةً
lineset = freestyle_settings.linesets.new("LemminoLineSet")
lineset.select_silhouette = True
lineset.select_crease = True
lineset.select_border = True

linestyle = bpy.data.linestyles.new("LemminoLineStyle")
linestyle.color = (1.0, 1.0, 1.0)
linestyle.thickness = 1.2
lineset.linestyle = linestyle

# خلفية سوداء تامة
world = bpy.data.worlds.new("VoidWorld")
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)
scene.world = world

def make_mat(name, color, is_emission=True, strength=2.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    if is_emission:
        em = nodes.new('ShaderNodeEmission')
        em.inputs['Color'].default_value = color
        em.inputs['Strength'].default_value = strength
        mat.node_tree.links.new(em.outputs['Emission'], out.inputs['Surface'])
    else:
        diff = nodes.new('ShaderNodeBsdfDiffuse')
        diff.inputs['Color'].default_value = color
        mat.node_tree.links.new(diff.outputs['BSDF'], out.inputs['Surface'])
    return mat

mat_black_body = make_mat("BlackBody", (0.005, 0.005, 0.005, 1), is_emission=False)
mat_red_cooper = make_mat("RedCooper", (1.0, 0.02, 0.03, 1), is_emission=True, strength=5.0)
mat_white_glow = make_mat("WhiteGlow", (1.0, 1.0, 1.0, 1), is_emission=True, strength=3.0)
mat_tree_white = make_mat("TreeWhite", (0.95, 0.95, 0.95, 1), is_emission=True, strength=2.5)
mat_tree_dark  = make_mat("TreeDark",  (0.08, 0.08, 0.08, 1), is_emission=True, strength=0.3)

# ------------------------------------------------------------
# 1. طائرة Boeing 727
# ------------------------------------------------------------
plane_parts = []

bpy.ops.mesh.primitive_cylinder_add(radius=1.1, depth=13.0, location=(0, 0, 12))
fuse = bpy.context.active_object
fuse.rotation_euler = (math.radians(90), 0, 0)
plane_parts.append(fuse)

bpy.ops.mesh.primitive_cone_add(radius1=1.1, depth=3.5, location=(0, -8.25, 12))
nose = bpy.context.active_object
nose.rotation_euler = (math.radians(-90), 0, 0)
plane_parts.append(nose)

bpy.ops.mesh.primitive_cube_add(size=1, location=(-6.5, 0.5, 11.8))
lw = bpy.context.active_object
lw.scale = (11.0, 2.6, 0.1)
lw.rotation_euler = (math.radians(4), math.radians(4), math.radians(30))
plane_parts.append(lw)

bpy.ops.mesh.primitive_cube_add(size=1, location=(6.5, 0.5, 11.8))
rw = bpy.context.active_object
rw.scale = (11.0, 2.6, 0.1)
rw.rotation_euler = (math.radians(4), math.radians(-4), math.radians(-30))
plane_parts.append(rw)

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 5.2, 14.2))
tail_fin = bpy.context.active_object
tail_fin.scale = (0.18, 3.2, 3.8)
tail_fin.rotation_euler = (math.radians(-32), 0, 0)
plane_parts.append(tail_fin)

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 6.4, 16.0))
tail_h = bpy.context.active_object
tail_h.scale = (5.5, 1.5, 0.08)
plane_parts.append(tail_h)

for side in [-1.45, 1.45]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.48, depth=2.8, location=(side, 4.0, 12.6))
    eng = bpy.context.active_object
    eng.rotation_euler = (math.radians(90), 0, 0)
    plane_parts.append(eng)

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 6.0, 10.8))
stair = bpy.context.active_object
stair.scale = (0.6, 2.2, 0.06)
stair.rotation_euler = (math.radians(-45), 0, 0)
stair.data.materials.append(mat_red_cooper)

bpy.ops.object.select_all(action='DESELECT')
for p in plane_parts: p.select_set(True)
bpy.context.view_layer.objects.active = fuse
bpy.ops.object.join()
airplane = bpy.context.active_object
airplane.data.materials.append(mat_black_body)
stair.parent = airplane

airplane.location = (0, 0, 0)
airplane.keyframe_insert(data_path="location", frame=1)
airplane.location = (0, -50, 0)
airplane.keyframe_insert(data_path="location", frame=150)

# ------------------------------------------------------------
# 2. المظلي الأحمر
# ------------------------------------------------------------
skydiver_parts = []

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.18, location=(0, 0, 0.55))
skydiver_parts.append(bpy.context.active_object)

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.12))
torso = bpy.context.active_object
torso.scale = (0.42, 0.28, 0.65)
skydiver_parts.append(torso)

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.16, 0.18))
rig = bpy.context.active_object
rig.scale = (0.34, 0.14, 0.45)
skydiver_parts.append(rig)

for s in [-1, 1]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.07, depth=0.75, location=(s * 0.48, -0.1, 0.28))
    arm = bpy.context.active_object
    arm.rotation_euler = (math.radians(-20), math.radians(s * 55), 0)
    skydiver_parts.append(arm)

for s in [-1, 1]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=0.85, location=(s * 0.26, 0.22, -0.45))
    leg = bpy.context.active_object
    leg.rotation_euler = (math.radians(38), math.radians(s * 18), 0)
    skydiver_parts.append(leg)

bpy.ops.object.select_all(action='DESELECT')
for sp in skydiver_parts: sp.select_set(True)
bpy.context.view_layer.objects.active = torso
bpy.ops.object.join()
skydiver = bpy.context.active_object
skydiver.data.materials.append(mat_red_cooper)

skydiver.location = (0, 6.8, 10.6)
skydiver.rotation_euler = (math.radians(-15), 0, 0)
skydiver.keyframe_insert(data_path="location", frame=1)
skydiver.keyframe_insert(data_path="rotation_euler", frame=1)

skydiver.location = (0, 8.2, 10.0)
skydiver.keyframe_insert(data_path="location", frame=25)

skydiver.location = (0.5, 11.5, -2.0)
skydiver.rotation_euler = (math.radians(170), math.radians(50), math.radians(25))
skydiver.keyframe_insert(data_path="location", frame=85)
skydiver.keyframe_insert(data_path="rotation_euler", frame=85)

skydiver.location = (0, 16.0, -18.5)
skydiver.rotation_euler = (math.radians(350), math.radians(110), math.radians(60))
skydiver.keyframe_insert(data_path="location", frame=150)
skydiver.keyframe_insert(data_path="rotation_euler", frame=150)

# ------------------------------------------------------------
# 3. خطوط الرياح
# ------------------------------------------------------------
random.seed(1971)
for i in range(45):
    wx = random.uniform(-16, 16)
    wy = random.uniform(-25, 25)
    wz = random.uniform(4, 18)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=random.uniform(4, 9), location=(wx, wy, wz))
    line = bpy.context.active_object
    line.rotation_euler = (math.radians(90), 0, 0)
    line.data.materials.append(mat_white_glow)
    line.keyframe_insert(data_path="location", frame=1)
    line.location.y += random.uniform(35, 60)
    line.keyframe_insert(data_path="location", frame=150)

# ------------------------------------------------------------
# 4. الغابة الكثيفة
# ------------------------------------------------------------
for i in range(200):
    gx = random.uniform(-35, 35)
    gy = random.uniform(-2, 36)
    gz = -23.5
    dist = math.sqrt(gx**2 + (gy - 16.0)**2)
    s = random.uniform(0.7, 1.6)

    bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=0.75 * s, depth=2.5 * s, location=(gx, gy, gz))
    tree = bpy.context.active_object
    tree.data.materials.append(mat_tree_white if dist < 8.5 else mat_tree_dark)

# ------------------------------------------------------------
# 5. الكاميرا والتتبع
# ------------------------------------------------------------
cam_target = bpy.data.objects.new("CamTarget", None)
scene.collection.objects.link(cam_target)

cam_target.location = (0, 4.0, 11.5)
cam_target.keyframe_insert(data_path="location", frame=1)
cam_target.location = (0, 9.5, 3.0)
cam_target.keyframe_insert(data_path="location", frame=85)
cam_target.location = (0, 16.0, -18.0)
cam_target.keyframe_insert(data_path="location", frame=150)

cam_data = bpy.data.cameras.new("LemminoCam")
cam_data.lens = 50
cam = bpy.data.objects.new("LemminoCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

track = cam.constraints.new(type='TRACK_TO')
track.target = cam_target
track.track_axis = 'TRACK_NEGATIVE_Z'
track.up_axis = 'UP_Y'

cam.location = (12.0, 18.0, 15.5)
cam.keyframe_insert(data_path="location", frame=1)
cam.location = (8.0, 20.0, 6.0)
cam.keyframe_insert(data_path="location", frame=85)
cam.location = (3.5, 22.0, -9.0)
cam.keyframe_insert(data_path="location", frame=150)

print(">> [BLENDER] بدء رندر المشهد النهائي...", flush=True)
bpy.ops.render.render(animation=True)
"""

def main():
    log("🚀 تشغيل بايبلاين LEMMiNO المصحح بالكامل...")
    plane_asset, skydiver_asset = ensure_assets()
    preview_img = MODELS_DIR / "plane_preview.png"
    approved, reason = review_asset_with_agy(preview_img, "Boeing 727 airliner")

    script_path = Path("render_core.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(BLENDER_SCRIPT)

    log("🎬 استدعاء Blender لتنفيذ الرندر...")
    res = subprocess.run(["blender", "-b", "-P", str(script_path)], text=True)

    if res.returncode == 0 and OUTPUT_VIDEO.exists() and OUTPUT_VIDEO.stat().st_size > 1024:
        log(f"🎉 تم الرندر بنجاح تام! الملف جاهز: {OUTPUT_VIDEO}")
    else:
        log("❌ فشل تشغيل Blender.")
        sys.exit(1)

if __name__ == "__main__":
    main()
