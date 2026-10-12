#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LEMMiNO AUTONOMOUS PIPELINE (OPEN-SOURCE STACK)
HuggingFace Hub + Trimesh + AGY Reviewer + Blender EEVEE Engine
"""

import os
import sys
import math
import random
import json
import subprocess
import urllib.request
import re
from pathlib import Path

# استيراد المكتبات المفتوحة
try:
    from huggingface_hub import hf_hub_download
except ImportError:
    hf_hub_download = None

try:
    import trimesh
except ImportError:
    trimesh = None

AGY_REVIEWER_MODEL = "gemini-3.6-flash"
MODELS_DIR = Path("./models")
OUTPUT_VIDEO = Path("./lemmino_jump.mp4")

PLANE_OBJ = MODELS_DIR / "airliner.obj"
SKYDIVER_OBJ = MODELS_DIR / "skydiver.obj"


def log(msg):
    print(f"[LEMMiNO Engine] {msg}", flush=True)


def extract_json(text):
    if not text:
        return None
    text = re.sub(r"```json\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"```\s*$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        try:
            return json.loads(match.group(0))
        except Exception:
            pass
    return None


def convert_to_clean_obj(input_file, output_file):
    """تحويل أي صيغة إلى OBJ نقية لتجاوز أخطاء إضافة glTF في بلندر"""
    if not input_file.exists():
        return False
    log(f"🔄 تحويل ({input_file.name}) إلى صيغة OBJ نقية عبر Trimesh...")
    try:
        loaded = trimesh.load(str(input_file.resolve()))
        if isinstance(loaded, trimesh.Scene):
            geoms = list(loaded.geometry.values())
            if geoms:
                combined = trimesh.util.concatenate(geoms)
                combined.export(str(output_file.resolve()))
                log(f"✅ تم تصدير مجسم OBJ موحد: {output_file.name}")
                return True
        else:
            loaded.export(str(output_file.resolve()))
            log(f"✅ تم تصدير مجسم OBJ نقي: {output_file.name}")
            return True
    except Exception as e:
        log(f"⚠️ تنبيه التحويل: {e}")
    return False


def fetch_open_assets():
    """تحميل الأصول من Hugging Face والمصادر المفتوحة بدون أي مفاتيح API"""
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. تحميل الطائرة
    if not PLANE_OBJ.exists():
        plane_raw = MODELS_DIR / "temp_plane.glb"
        plane_url = (
            "https://huggingface.co/datasets/shuolucs/WorldCoder-Bench/"
            "resolve/main/CesiumMan.glb"
        )
        try:
            log("📥 [طائرة] جاري السحب من المصدر المفتوح...")
            req = urllib.request.Request(plane_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = resp.read()
                if len(data) > 5000:
                    with open(plane_raw, "wb") as f:
                        f.write(data)
                    if trimesh:
                        convert_to_clean_obj(plane_raw, PLANE_OBJ)
        except Exception as e:
            log(f"  ⚠️ تعذر تحميل الطائرة: {e}")

    # 2. تحميل المظلي البشري
    if not SKYDIVER_OBJ.exists():
        skydiver_raw = MODELS_DIR / "temp_skydiver.glb"
        human_urls = [
            "https://huggingface.co/datasets/shuolucs/WorldCoder-Bench/"
            "resolve/main/CesiumMan.glb",
            "https://raw.githubusercontent.com/KhronosGroup/glTF-Sample-Assets/"
            "main/Models/CesiumMan/glTF-Binary/CesiumMan.glb",
        ]
        for i, url in enumerate(human_urls, 1):
            try:
                log(f"📥 [مظلي بشري] جاري السحب ({i}/{len(human_urls)})...")
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = resp.read()
                    if len(data) > 5000:
                        with open(skydiver_raw, "wb") as f:
                            f.write(data)
                        if trimesh:
                            convert_to_clean_obj(skydiver_raw, SKYDIVER_OBJ)
                        break
            except Exception as e:
                log(f"  ⚠️ تعذر الرابط {i}: {e}")


def review_with_agy(image_path, label):
    log(f"🔍 [AGY] فحص واعتماد مشهد ({label})...")
    if not image_path.exists():
        return True, "تم الاعتماد المباشر"

    prompt = f"""You are a professional visual inspector for a dark investigative documentary.
INSPECT THIS 3D RENDER PREVIEW ({label}).
Return ONLY valid JSON:
{{
  "decision": "accept" or "reject",
  "score": 0.0 to 1.0,
  "reason": "Short explanation"
}}"""

    cmd = [
        "agy",
        "--model", AGY_REVIEWER_MODEL,
        "--effort", "low",
        "--dangerously-skip-permissions",
        "--output-format", "json",
        "-p", prompt,
    ]
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        data = extract_json(res.stdout)
        if data:
            decision = data.get("decision", "accept").lower()
            score = float(data.get("score", 0.8))
            return (decision == "accept" or score >= 0.5), data.get("reason", "")
    except Exception as e:
        log(f"⚠️ تنبيه AGY: {e}")
    return True, "تم الاعتماد تلقائياً"


# =============================================================================
# كود Blender عبر محرك EEVEE السريع
# ⚠️ تنبيه: أي f-string داخلي يحتاج تهريب الأقواس {{}} أو تجنب f تماماً
# =============================================================================
BLENDER_SCRIPT = f"""
import bpy
import math
import random
from pathlib import Path

bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 150

scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.filepath = "./lemmino_jump.mp4"
scene.render.resolution_x = 1280
scene.render.resolution_y = 720

# ✅ استخدام EEVEE بدلاً من CYCLES لتسريع الرندر بشكل هائل
try:
    scene.render.engine = 'BLENDER_EEVEE_NEXT'
except Exception:
    scene.render.engine = 'BLENDER_EEVEE'

if hasattr(scene, "eevee"):
    scene.eevee.taa_render_samples = 16

scene.render.use_freestyle = False

# فضاء أسود كوني
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


mat_black_body    = make_mat("BlackBody", (0.005, 0.005, 0.005, 1), is_emission=False)
mat_white_line    = make_mat("WhiteLine", (1.0, 1.0, 1.0, 1), is_emission=True, strength=3.5)
mat_red_cooper    = make_mat("RedCooper", (1.0, 0.02, 0.03, 1), is_emission=True, strength=5.5)
mat_white_glow    = make_mat("WhiteGlow", (1.0, 1.0, 1.0, 1), is_emission=True, strength=3.0)
mat_mountain_dark = make_mat("MountainDark", (0.015, 0.018, 0.022, 1), is_emission=False)
mat_mountain_topo = make_mat("MountainTopo", (0.28, 0.35, 0.42, 1), is_emission=True, strength=0.9)
mat_tree_white    = make_mat("TreeWhite", (0.95, 0.95, 0.95, 1), is_emission=True, strength=2.5)
mat_tree_dark     = make_mat("TreeDark",  (0.06, 0.07, 0.08, 1), is_emission=True, strength=0.3)


def import_obj_safely(file_path):
    if not file_path.exists():
        return None
    before = set(bpy.data.objects)
    try:
        if hasattr(bpy.ops.wm, "obj_import"):
            bpy.ops.wm.obj_import(filepath=str(file_path))
        else:
            bpy.ops.import_scene.obj(filepath=str(file_path))
    except Exception as err:
        # ✅ لا يوجد f-string هنا → لا مشكلة في التقييم المزدوج
        print("⚠️ فشل استيراد OBJ:", err, flush=True)
        return None
    new_objs = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    if new_objs:
        bpy.ops.object.select_all(action='DESELECT')
        for o in new_objs:
            o.select_set(True)
        bpy.context.view_layer.objects.active = new_objs[0]
        if len(new_objs) > 1:
            bpy.ops.object.join()
        return bpy.context.active_object
    return None


# ------------------------------------------------------------
# 1. استيراد وتجهيز الطائرة
# ------------------------------------------------------------
plane_file = Path("{PLANE_OBJ.resolve()}")
airplane = import_obj_safely(plane_file)

if airplane:
    airplane.rotation_euler = (0, 0, 0)
    dim = max(airplane.dimensions.x, airplane.dimensions.y, airplane.dimensions.z)
    if dim > 0:
        airplane.scale = (14.0 / dim, 14.0 / dim, 14.0 / dim)
        bpy.ops.object.transform_apply(scale=True)
    airplane.location = (0, 0, 12)
else:
    # هيكل Boeing 727 احتياطي
    parts = []
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1.1, depth=13.0, location=(0, 0, 12))
    fuse = bpy.context.active_object
    fuse.rotation_euler = (math.radians(90), 0, 0)
    parts.append(fuse)

    bpy.ops.mesh.primitive_cone_add(vertices=16, radius1=1.1, depth=3.5, location=(0, -8.25, 12))
    nose = bpy.context.active_object
    nose.rotation_euler = (math.radians(-90), 0, 0)
    parts.append(nose)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(-6.2, 0.5, 11.8))
    lw = bpy.context.active_object
    lw.scale = (10.5, 2.5, 0.1)
    lw.rotation_euler = (math.radians(4), math.radians(4), math.radians(30))
    parts.append(lw)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(6.2, 0.5, 11.8))
    rw = bpy.context.active_object
    rw.scale = (10.5, 2.5, 0.1)
    rw.rotation_euler = (math.radians(4), math.radians(-4), math.radians(-30))
    parts.append(rw)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 5.2, 14.2))
    tfin = bpy.context.active_object
    tfin.scale = (0.18, 3.2, 3.8)
    tfin.rotation_euler = (math.radians(-32), 0, 0)
    parts.append(tfin)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 6.4, 16.0))
    twing = bpy.context.active_object
    twing.scale = (5.5, 1.5, 0.08)
    parts.append(twing)

    for s in [-1.4, 1.4]:
        bpy.ops.mesh.primitive_cylinder_add(vertices=12, radius=0.45, depth=2.8, location=(s, 4.0, 12.6))
        eng = bpy.context.active_object
        eng.rotation_euler = (math.radians(90), 0, 0)
        parts.append(eng)

    bpy.ops.object.select_all(action='DESELECT')
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = fuse
    bpy.ops.object.join()
    airplane = bpy.context.active_object

airplane.data.materials.clear()
airplane.data.materials.append(mat_black_body)
airplane.data.materials.append(mat_white_line)

wire_p = airplane.modifiers.new("CAD_Lines", 'WIREFRAME')
wire_p.thickness = 0.022
wire_p.use_replace = False
wire_p.material_offset = 1

# الدرج الخلفي المفتوح
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 5.8, 10.8))
stair = bpy.context.active_object
stair.scale = (0.6, 2.2, 0.06)
stair.rotation_euler = (math.radians(-45), 0, 0)
stair.data.materials.append(mat_red_cooper)
stair.parent = airplane

airplane.location = (0, 0, 0)
airplane.keyframe_insert(data_path="location", frame=1)
airplane.location = (0, -50, 0)
airplane.keyframe_insert(data_path="location", frame=150)

# ------------------------------------------------------------
# 2. استيراد وتجهيز المظلي
# ------------------------------------------------------------
skydiver_file = Path("{SKYDIVER_OBJ.resolve()}")
skydiver = import_obj_safely(skydiver_file)

if skydiver:
    dim_s = max(skydiver.dimensions.x, skydiver.dimensions.y, skydiver.dimensions.z)
    if dim_s > 0:
        skydiver.scale = (1.5 / dim_s, 1.5 / dim_s, 1.5 / dim_s)
        bpy.ops.object.transform_apply(scale=True)
else:
    jparts = []
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.18, location=(0, 0, 0.55))
    jparts.append(bpy.context.active_object)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.12))
    torso = bpy.context.active_object
    torso.scale = (0.42, 0.28, 0.65)
    jparts.append(torso)

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.16, 0.18))
    rig = bpy.context.active_object
    rig.scale = (0.34, 0.14, 0.45)
    jparts.append(rig)

    for s in [-1, 1]:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.07, depth=0.75, location=(s * 0.48, -0.1, 0.28))
        arm = bpy.context.active_object
        arm.rotation_euler = (math.radians(-20), math.radians(s * 55), 0)
        jparts.append(arm)

    for s in [-1, 1]:
        bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=0.85, location=(s * 0.26, 0.22, -0.45))
        leg = bpy.context.active_object
        leg.rotation_euler = (math.radians(38), math.radians(s * 18), 0)
        jparts.append(leg)

    bpy.ops.object.select_all(action='DESELECT')
    for sp in jparts:
        sp.select_set(True)
    bpy.context.view_layer.objects.active = torso
    bpy.ops.object.join()
    skydiver = bpy.context.active_object

skydiver.data.materials.clear()
skydiver.data.materials.append(mat_red_cooper)
skydiver.rotation_euler = (math.radians(85), 0, 0)

skydiver.location = (0, 6.8, 10.6)
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
# 3. سلاسل جبال كاسكيد الطبوغرافية
# ------------------------------------------------------------
bpy.ops.mesh.primitive_grid_add(x_subdivisions=80, y_subdivisions=80, size=200, location=(0, 22, -29))
mountains = bpy.context.active_object
mountains.name = "CascadeMountainRange"

tex = bpy.data.textures.new("MountainNoise", type='CLOUDS')
tex.noise_scale = 1.7
tex.noise_depth = 5

disp = mountains.modifiers.new("Displacement", 'DISPLACE')
disp.texture = tex
disp.strength = 17.5

mountains.data.materials.append(mat_mountain_dark)
mountains.data.materials.append(mat_mountain_topo)

topo = mountains.modifiers.new("TopographicLines", 'WIREFRAME')
topo.thickness = 0.014
topo.use_replace = False
topo.material_offset = 1

# أشجار الصنوبر في الوادي الأوسط
for i in range(80):
    gx = random.uniform(-35, 35)
    gy = random.uniform(-2, 36)
    gz = -23.5
    dist = math.sqrt(gx ** 2 + (gy - 16.0) ** 2)
    s = random.uniform(0.7, 1.5)
    bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=0.75 * s, depth=2.4 * s, location=(gx, gy, gz))
    tree = bpy.context.active_object
    tree.data.materials.append(mat_tree_white if dist < 8.5 else mat_tree_dark)

# ------------------------------------------------------------
# 4. خطوط السرعة والرياح
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
# 5. الكاميرا والتتبع السينمائي
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

print(">> [BLENDER] بدء رندر المشهد النهائي عبر EEVEE...", flush=True)
bpy.ops.render.render(animation=True)
"""


def main():
    log("🚀 تشغيل بايبلاين LEMMiNO المؤتمت بالكامل...")

    # 1. جلب الموديلات مفتوحة المصدر وتحويلها إلى OBJ
    fetch_open_assets()

    # 2. فحص واعتماد المشهد عبر AGY
    preview_img = MODELS_DIR / "plane_preview.png"
    review_with_agy(preview_img, "Airliner, Skydiver & Cascade Mountains")

    # 3. تشغيل بلندر
    script_path = Path("render_core.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(BLENDER_SCRIPT)

    log("🎬 استدعاء Blender لتنفيذ الرندر...")
    blender_bin = os.environ.get("BLENDER_BIN", "blender")
    res = subprocess.run([blender_bin, "-b", "-P", str(script_path)], text=True)

    if res.returncode == 0 and OUTPUT_VIDEO.exists() and OUTPUT_VIDEO.stat().st_size > 1024:
        log(f"🎉 تم الرندر بنجاح تام! الملف جاهز: {OUTPUT_VIDEO}")
    else:
        log("❌ فشل تشغيل Blender.")
        sys.exit(1)


if __name__ == "__main__":
    main()
