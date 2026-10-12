import bpy
import math
import random

# ============================================================
# 1. إعداد المشهد ومحرك الرندر
# ============================================================
bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 150  # 6.25 ثانية سينمائية مركزة ومثالية

scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.filepath = "./lemmino_jump.mp4"
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

scene.render.engine = 'CYCLES'
scene.cycles.samples = 8
scene.cycles.use_denoising = False

# خلفية سوداء نقية
world = bpy.data.worlds.new("LemminoVoid")
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)
scene.world = world

# ============================================================
# 2. الخامات التخطيطية النقية (CAD / Blueprint Shaders)
# ============================================================
def get_emission_mat(name, color, strength=2.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    em = nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = color
    em.inputs['Strength'].default_value = strength
    mat.node_tree.links.new(em.outputs['Emission'], out.inputs['Surface'])
    return mat

mat_body_black = get_emission_mat("BodyBlack", (0.005, 0.005, 0.005, 1), strength=0.0)
mat_white_edge = get_emission_mat("WhiteEdge", (1.0, 1.0, 1.0, 1), strength=3.0)
mat_red_cooper = get_emission_mat("RedCooper", (1.0, 0.03, 0.03, 1), strength=4.5)
mat_forest_center = get_emission_mat("ForestWhite", (0.9, 0.9, 0.9, 1), strength=2.2)
mat_forest_dark   = get_emission_mat("ForestDark",  (0.08, 0.08, 0.08, 1), strength=0.4)

# ============================================================
# 3. بناء طائرة الـ 727 وعجلات الهبوط والدرج المفتوح
# ============================================================
plane_objects = []

# هيكل الطائرة الرئيسي
bpy.ops.mesh.primitive_cylinder_add(radius=0.9, depth=11.0, location=(0, 0, 8.0))
fuselage = bpy.context.active_object
fuselage.rotation_euler = (math.radians(90), 0, 0)
plane_objects.append(fuselage)

# مقدمة الطائرة
bpy.ops.mesh.primitive_cone_add(radius1=0.9, depth=2.5, location=(0, -6.5, 8.0))
nose = bpy.context.active_object
nose.rotation_euler = (math.radians(-90), 0, 0)
plane_objects.append(nose)

# الأجنحة الرئيسية المائلة
bpy.ops.mesh.primitive_cube_add(size=1, location=(-4.8, 0.2, 7.8))
left_wing = bpy.context.active_object
left_wing.scale = (8.5, 2.0, 0.08)
left_wing.rotation_euler = (math.radians(3), math.radians(3), math.radians(28))
plane_objects.append(left_wing)

bpy.ops.mesh.primitive_cube_add(size=1, location=(4.8, 0.2, 7.8))
right_wing = bpy.context.active_object
right_wing.scale = (8.5, 2.0, 0.08)
right_wing.rotation_euler = (math.radians(3), math.radians(-3), math.radians(-28))
plane_objects.append(right_wing)

# ذيل الـ T-Tail
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 4.4, 9.8))
fin = bpy.context.active_object
fin.scale = (0.15, 2.4, 2.8)
fin.rotation_euler = (math.radians(-30), 0, 0)
plane_objects.append(fin)

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 5.3, 11.2))
h_tail = bpy.context.active_object
h_tail.scale = (4.8, 1.2, 0.08)
plane_objects.append(h_tail)

# المحركات الجانبية الخلفية
for s in [-1.2, 1.2]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.4, depth=2.4, location=(s, 3.4, 8.5))
    eng = bpy.context.active_object
    eng.rotation_euler = (math.radians(90), 0, 0)
    plane_objects.append(eng)

# عجلات الهبوط المفتوحة (Landing Gear)
for gx in [-1.5, 0, 1.5]:
    gy = -3.5 if gx == 0 else 0.8
    bpy.ops.mesh.primitive_cylinder_add(radius=0.25, depth=0.15, location=(gx, gy, 6.7))
    gear = bpy.context.active_object
    gear.rotation_euler = (0, math.radians(90), 0)
    plane_objects.append(gear)

# الدرج الخلفي المفتوح (Aft Airstair) بلون أحمر متوهج
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 5.2, 7.1))
stair = bpy.context.active_object
stair.scale = (0.5, 1.8, 0.06)
stair.rotation_euler = (math.radians(-40), 0, 0)
stair.data.materials.append(mat_red_cooper)

# دمج مجسم الطائرة وتطبيق الخطوط الخارجية البيضاء
bpy.ops.object.select_all(action='DESELECT')
for p in plane_objects:
    p.select_set(True)
bpy.context.view_layer.objects.active = fuselage
bpy.ops.object.join()
plane = bpy.context.active_object
plane.data.materials.append(mat_body_black)

# خط الحواف الخارجي
wire_mod = plane.modifiers.new("LineArt", 'WIREFRAME')
wire_mod.thickness = 0.025
wire_mod.use_replace = False
plane.data.materials.append(mat_white_edge)
wire_mod.material_offset = 1

stair.parent = plane

# حركة الطائرة
plane.location = (0, 0, 0)
plane.keyframe_insert(data_path="location", frame=1)
plane.location = (0, -45, 0)
plane.keyframe_insert(data_path="location", frame=150)

# ============================================================
# 4. بناء شخصية المظلي الأحمر (Skydiving Arch Pose)
# ============================================================
jumper_parts = []

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.22, location=(0, 0, 0.65))
jumper_parts.append(bpy.context.active_object)

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.15))
torso = bpy.context.active_object
torso.scale = (0.55, 0.35, 0.75)
jumper_parts.append(torso)

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.18, 0.2))
pack = bpy.context.active_object
pack.scale = (0.42, 0.18, 0.55)
jumper_parts.append(pack)

for s in [-1, 1]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.09, depth=0.9, location=(s * 0.6, -0.15, 0.35))
    arm = bpy.context.active_object
    arm.rotation_euler = (math.radians(-20), math.radians(s * 50), 0)
    jumper_parts.append(arm)

for s in [-1, 1]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.11, depth=1.0, location=(s * 0.35, 0.25, -0.55))
    leg = bpy.context.active_object
    leg.rotation_euler = (math.radians(35), math.radians(s * 15), 0)
    jumper_parts.append(leg)

bpy.ops.object.select_all(action='DESELECT')
for jp in jumper_parts:
    jp.select_set(True)
bpy.context.view_layer.objects.active = torso
bpy.ops.object.join()
skydiver = bpy.context.active_object
skydiver.data.materials.append(mat_red_cooper)

# مسار القفز والسقوط
skydiver.location = (0, 5.8, 7.0)
skydiver.rotation_euler = (math.radians(-15), 0, 0)
skydiver.keyframe_insert(data_path="location", frame=1)
skydiver.keyframe_insert(data_path="rotation_euler", frame=1)

skydiver.location = (0, 7.0, 6.6)
skydiver.keyframe_insert(data_path="location", frame=25)

skydiver.location = (0.5, 9.0, -4.0)
skydiver.rotation_euler = (math.radians(160), math.radians(45), math.radians(30))
skydiver.keyframe_insert(data_path="location", frame=85)
skydiver.keyframe_insert(data_path="rotation_euler", frame=85)

skydiver.location = (0, 11.0, -18.0)
skydiver.rotation_euler = (math.radians(320), math.radians(90), math.radians(60))
skydiver.keyframe_insert(data_path="location", frame=150)
skydiver.keyframe_insert(data_path="rotation_euler", frame=150)

# ============================================================
# 5. خطوط الرياح النفقية (Tunnel Speed Lines)
# ============================================================
random.seed(42)
for i in range(40):
    lx = random.uniform(-14, 14)
    ly = random.uniform(-20, 20)
    lz = random.uniform(2, 14)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=random.uniform(3, 7), location=(lx, ly, lz))
    line = bpy.context.active_object
    line.rotation_euler = (math.radians(90), 0, 0)
    line.data.materials.append(mat_white_edge)
    
    line.keyframe_insert(data_path="location", frame=1)
    line.location.y += random.uniform(30, 50)
    line.keyframe_insert(data_path="location", frame=150)

# ============================================================
# 6. سجادة الغابة مع بقعة الضوء المركزية
# ============================================================
for i in range(150):
    gx = random.uniform(-30, 30)
    gy = random.uniform(-5, 30)
    gz = -22.0
    dist = math.sqrt(gx**2 + (gy - 11.0)**2)
    s = random.uniform(0.9, 2.0)
    
    bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=0.8 * s, depth=2.4 * s, location=(gx, gy, gz))
    tree = bpy.context.active_object
    tree.data.materials.append(mat_forest_center if dist < 9.5 else mat_forest_dark)

# ============================================================
# 7. الكاميرا السينمائية مع نظام التتبع الصحيح (Constraints)
# ============================================================
target = bpy.data.objects.new("CamTarget", None)
scene.collection.objects.link(target)

target.location = (0, 3, 7.5)
target.keyframe_insert(data_path="location", frame=1)
target.location = (0, 7.5, 0.0)
target.keyframe_insert(data_path="location", frame=85)
target.location = (0, 11.0, -17.0)
target.keyframe_insert(data_path="location", frame=150)

cam_data = bpy.data.cameras.new("MainCam")
cam_data.lens = 45
cam = bpy.data.objects.new("MainCam", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam

# التصحيح هنا: استخدام constraints بدلاً من modifiers
track = cam.constraints.new(type='TRACK_TO')
track.target = target
track.track_axis = 'TRACK_NEGATIVE_Z'
track.up_axis = 'UP_Y'

# مسار الكاميرا السينمائي الموزون
cam.location = (11.0, 16.0, 11.5)
cam.keyframe_insert(data_path="location", frame=1)

cam.location = (7.5, 17.5, 2.5)
cam.keyframe_insert(data_path="location", frame=85)

cam.location = (4.0, 18.0, -11.0)
cam.keyframe_insert(data_path="location", frame=150)

print(">> تم تصحيح الكود بالكامل وبدء الرندر بنجاح...")
bpy.ops.render.render(animation=True)
