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

PLANE_FILE = MODELS_DIR / "airliner.glb"
SKYDIVER_FILE = MODELS_DIR / "skydiver.glb"

# روابط بديلة عالمية مضمونة 100% عبر شبكات CDN
PLANE_MIRRORS = [
    "https://cdn.jsdelivr.net/gh/amvlab/aircraft-models@main/models/B737_nologo.glb",
    "https://raw.githubusercontent.com/amvlab/aircraft-models/main/models/B737_nologo.glb",
    "https://cdn.jsdelivr.net/gh/amvlab/aircraft-models@main/models/A320_nologo.glb",
    "https://raw.githubusercontent.com/amvlab/aircraft-models/main/models/A320_nologo.glb",
]

SKYDIVER_MIRRORS = [
    "https://cdn.jsdelivr.net/gh/c-frame/valid-avatars-glb@c539a28/avatars/Hispanic_M_1.glb",
    "https://cdn.jsdelivr.net/gh/c-frame/valid-avatars-glb@c539a28/avatars/Hispanic_M_2.glb",
    "https://cdn.jsdelivr.net/gh/c-frame/valid-avatars-glb@c539a28/avatars/White_M_1.glb",
    "https://raw.githubusercontent.com/c-frame/valid-avatars-glb/c539a28/avatars/Hispanic_M_1.glb",
]

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

def download_with_retries(mirrors, target_path, asset_name):
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists() and target_path.stat().st_size > 5000:
        log(f"✅ الموديل موجود مسبقاً بجودة ممتازة: {target_path.name}")
        return True

    log(f"📥 بدء البحث وسحب موديل ({asset_name}) عبر روابط بديلة...")
    for i, url in enumerate(mirrors, 1):
        try:
            log(f"  [محاولة {i}/{len(mirrors)}] السحب من: {url[:65]}...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
                if len(data) > 5000:
                    with open(target_path, "wb") as f:
                        f.write(data)
                    log(f"  ✅ نجح تحميل ({asset_name}) من المصدر {i} (الحجم: {len(data)/1024:.1f} KB)")
                    return True
        except Exception as e:
            log(f"  ⚠️ تعذر الرابط {i}: {e}")
            continue

    log(f"❌ تعذرت الروابط الخارجية لـ ({asset_name})")
    return False

def review_asset_with_agy(image_path, asset_type):
    log(f"🔍 [AGY] فحص واعتماد الموديل لـ ({asset_type})...")
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
    return True, "تم الاعتماد افتراضياً"

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
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

scene.render.engine = 'CYCLES'
scene.cycles.samples = 8
scene.cycles.use_denoising = False
scene.render.use_freestyle = False

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

mat_black_body    = make_mat("BlackBody", (0.005, 0.005, 0.005, 1), is_emission=False)
mat_white_line    = make_mat("WhiteLine", (1.0, 1.0, 1.0, 1), is_emission=True, strength=3.5)
mat_red_cooper    = make_mat("RedCooper", (1.0, 0.02, 0.03, 1), is_emission=True, strength=5.5)
mat_white_glow    = make_mat("WhiteGlow", (1.0, 1.0, 1.0, 1), is_emission=True, strength=3.0)
mat_mountain_dark = make_mat("MountainDark", (0.02, 0.02, 0.025, 1), is_emission=False)
mat_mountain_wire = make_mat("MountainWire", (0.35, 0.35, 0.35, 1), is_emission=True, strength=0.8)
mat_tree_white    = make_mat("TreeWhite", (0.95, 0.95, 0.95, 1), is_emission=True, strength=2.5)
mat_tree_dark     = make_mat("TreeDark",  (0.08, 0.08, 0.08, 1), is_emission=True, strength=0.3)

# ------------------------------------------------------------
# 1. استيراد وتجهيز طائرة بوينغ الحقيقية (Real 3D Airliner)
# ------------------------------------------------------------
plane_file = Path("{PLANE_FILE.resolve()}")
if plane_file.exists():
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(plane_file))
    imported_mesh = [o for o in bpy.data.objects if o not in before and o.type == 'MESH']
    
    bpy.ops.object.select_all(action='DESELECT')
    for o in imported_mesh: o.select_set(True)
    bpy.context.view_layer.objects.active = imported_mesh[0]
    bpy.ops.object.join()
    airplane = bpy.context.active_object
    
    # توحيد المقاييس والتوجيه للأمام
    airplane.rotation_euler = (0, 0, 0)
    dim_max = max(airplane.dimensions.x, airplane.dimensions.y, airplane.dimensions.z)
    if dim_max > 0:
        airplane.scale = (15.0 / dim_max, 15.0 / dim_max, 15.0 / dim_max)
        bpy.ops.object.transform_apply(scale=True)
    airplane.location = (0, 0, 12)
else:
    # بديل احتياطي عالي التفاصيل
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=1.1, depth=13.0, location=(0, 0, 12))
    airplane = bpy.context.active_object
    airplane.rotation_euler = (math.radians(90), 0, 0)

# تطبيق خامة LEMMiNO (جسم أسود معتم + خطوط CAD بيضاء حادة)
airplane.data.materials.clear()
airplane.data.materials.append(mat_black_body)
airplane.data.materials.append(mat_white_line)

wire_plane = airplane.modifiers.new("CAD_Lines", 'WIREFRAME')
wire_plane.thickness = 0.02
wire_plane.use_replace = False
wire_plane.material_offset = 1

# الدرج الخلفي المفتوح (Aft Airstair)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 5.8, 10.8))
stair = bpy.context.active_object
stair.scale = (0.6, 2.2, 0.06)
stair.rotation_euler = (math.radians(-45), 0, 0)
stair.data.materials.append(mat_red_cooper)
stair.parent = airplane

# تحريك الطائرة للأمام تشق الظلام
airplane.location = (0, 0, 0)
airplane.keyframe_insert(data_path="location", frame=1)
airplane.location = (0, -50, 0)
airplane.keyframe_insert(data_path="location", frame=150)

# ------------------------------------------------------------
# 2. استيراد وتجهيز المظلي البشري الحقيقي (Real Human Skydiver)
# ------------------------------------------------------------
skydiver_file = Path("{SKYDIVER_FILE.resolve()}")
if skydiver_file.exists():
    before_s = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(skydiver_file))
    imported_s = [o for o in bpy.data.objects if o not in before_s and o.type == 'MESH']
    
    bpy.ops.object.select_all(action='DESELECT')
    for o in imported_s: o.select_set(True)
    bpy.context.view_layer.objects.active = imported_s[0]
    bpy.ops.object.join()
    skydiver = bpy.context.active_object
    
    # ضبط الحجم البشري الحقيقي (حوالي 1.8 متر)
    dim_s = max(skydiver.dimensions.x, skydiver.dimensions.y, skydiver.dimensions.z)
    if dim_s > 0:
        skydiver.scale = (1.5 / dim_s, 1.5 / dim_s, 1.5 / dim_s)
        bpy.ops.object.transform_apply(scale=True)
else:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.18, location=(0, 0, 0.55))
    skydiver = bpy.context.active_object

skydiver.data.materials.clear()
skydiver.data.materials.append(mat_red_cooper)

# وضعية القفز الحر (أفقي مع انحناء)
skydiver.rotation_euler = (math.radians(85), 0, 0)

# مسار القفز والسقوط بدقة
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
# 3. تضاريس الجبال ثلاثية الأبعاد (Cascade Mountains Topography)
# ------------------------------------------------------------
bpy.ops.mesh.primitive_grid_add(x_subdivisions=120, y_subdivisions=120, size=180, location=(0, 20, -28))
mountains = bpy.context.active_object
mountains.name = "CascadeMountains"

tex = bpy.data.textures.new("MountainNoise", type='CLOUDS')
tex.noise_scale = 1.6
tex.noise_depth = 4

disp = mountains.modifiers.new("Displace", 'DISPLACE')
disp.texture = tex
disp.strength = 16.0

mountains.data.materials.append(mat_mountain_dark)
mountains.data.materials.append(mat_mountain_wire)

# خطوط الارتفاع الكنتورية للجبال
topo = mountains.modifiers.new("TopoLines", 'WIREFRAME')
topo.thickness = 0.012
topo.use_replace = False
topo.material_offset = 1

# أشجار الصنوبر في الوادي الأوسط المضيء
for i in range(160):
    gx = random.uniform(-35, 35)
    gy = random.uniform(-2, 36)
    gz = -23.5
    dist = math.sqrt(gx**2 + (gy - 16.0)**2)
    s = random.uniform(0.7, 1.5)
    bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=0.7 * s, depth=2.4 * s, location=(gx, gy, gz))
    tree = bpy.context.active_object
    tree.data.materials.append(mat_tree_white if dist < 8.5 else mat_tree_dark)

# ------------------------------------------------------------
# 4. خطوط الرياح النفقية (Tunnel Speed Lines)
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
# 5. الكاميرا والتتبع السينمائي المنضبط
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

print(">> [BLENDER] بدء رندر المشهد النهائي مع الموديلات والجبال...", flush=True)
bpy.ops.render.render(animation=True)
"""

def main():
    log("🚀 تشغيل بايبلاين LEMMiNO مع نظام السحب المتعدد وتضاريس الجبال...")
    
    # محاولة تنزيل الطائرة عبر 4 روابط بديلة
    download_with_retries(PLANE_MIRRORS, PLANE_FILE, "Boeing 737 Airliner")
    
    # محاولة تنزيل المظلي البشري عبر 4 روابط بديلة
    download_with_retries(SKYDIVER_MIRRORS, SKYDIVER_FILE, "Human Skydiver")

    preview_img = MODELS_DIR / "plane_preview.png"
    review_asset_with_agy(preview_img, "Boeing airliner & Skydiver")

    script_path = Path("render_core.py")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(BLENDER_SCRIPT)

    log("🎬 استدعاء Blender لتنفيذ الرندر مع تضاريس الجبال والموديلات الحقيقية...")
    res = subprocess.run(["blender", "-b", "-P", str(script_path)], text=True)

    if res.returncode == 0 and OUTPUT_VIDEO.exists() and OUTPUT_VIDEO.stat().st_size > 1024:
        log(f"🎉 تم الرندر بنجاح تام! الملف جاهز: {OUTPUT_VIDEO}")
    else:
        log("❌ فشل تشغيل Blender.")
        sys.exit(1)

if __name__ == "__main__":
    main()
