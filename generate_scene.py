import bpy
import math
import random

# 1. تنظيف المشهد القديم
bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 160  # حوالي 6.5 ثانية

# إعدادات الرندر والحفظ (MP4 / H264)
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.filepath = "//lemmino_jump.mp4"
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

# محرك الرندر: Cycles بعينات قليلة جداً لسرعة فائقة وجودة نقية
scene.render.engine = 'CYCLES'
scene.cycles.samples = 4
scene.cycles.use_denoising = False

# 2. إنشاء الخامات التوهجية (LEMMiNO Minimalist Shaders)
def make_emission(name, color, strength=1.0):
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

mat_white_line = make_emission("WhiteLine", (1, 1, 1, 1), 2.0)
mat_red_cooper = make_emission("RedCooper", (1, 0.05, 0.05, 1), 3.0)
mat_tree_white = make_emission("TreeWhite", (0.9, 0.9, 0.9, 1), 1.5)
mat_tree_gray  = make_emission("TreeGray",  (0.2, 0.2, 0.2, 1), 0.8)

# ضبط خلفية العالم على أسود تام
world = bpy.data.worlds.new("BlackVoid")
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)
scene.world = world

# 3. بناء هيكل الطائرة التخطيطي (Wireframe Boeing 727)
# هيكل الطائرة (Fuselage)
bpy.ops.mesh.primitive_cylinder_add(radius=1.2, depth=14, location=(0, 0, 15))
fuselage = bpy.context.active_object
fuselage.rotation_euler = (math.radians(90), 0, 0)
wire = fuselage.modifiers.new("Wire", 'WIREFRAME')
wire.thickness = 0.03
fuselage.data.materials.append(mat_white_line)

# أجنحة الطائرة (Wings)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -1, 15))
wings = bpy.context.active_object
wings.scale = (16, 2.5, 0.05)
wings.rotation_euler = (0, 0, math.radians(15))
wire_w = wings.modifiers.new("Wire", 'WIREFRAME')
wire_w.thickness = 0.03
wings.data.materials.append(mat_white_line)

# الدرج الخلفي الأحمر المتوهج (Aft Airstair)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 6, 14.2))
stairs = bpy.context.active_object
stairs.scale = (0.6, 2.0, 0.08)
stairs.rotation_euler = (math.radians(-30), 0, 0)
stairs.data.materials.append(mat_red_cooper)

# تجميع الطائرة وتحريكها للأمام
plane_parts = [fuselage, wings, stairs]
for part in plane_parts:
    part.keyframe_insert(data_path="location", frame=1)
    part.location.y -= 30  # تتحرك للأمام في الفضاء
    part.keyframe_insert(data_path="location", frame=160)

# 4. بناء مجسم الشخصية الحمراء الساقطة (Red Jumper)
bpy.ops.mesh.primitive_cube_add(size=0.6, location=(0, 6.2, 14.0))
jumper = bpy.context.active_object
jumper.scale = (0.4, 0.8, 1.4)
jumper.data.materials.append(mat_red_cooper)

# تحريك القفزة والسقوط الحر المتخبط (Freefall & Tumbling)
# الإطار 1 إلى 25: داخل مخرج الطائرة
jumper.keyframe_insert(data_path="location", frame=1)
jumper.keyframe_insert(data_path="rotation_euler", frame=1)

# الإطار 35: ينفصل عن الطائرة ويهوي
jumper.location = (0, 8, 13.5)
jumper.keyframe_insert(data_path="location", frame=35)

# الإطار 160: السقوط الحر لأسفل باتجاه الغابة مع دوران متخبط
jumper.location = (1.5, 12, -18)
jumper.rotation_euler = (math.radians(720), math.radians(360), math.radians(180))
jumper.keyframe_insert(data_path="location", frame=160)
jumper.keyframe_insert(data_path="rotation_euler", frame=160)

# 5. بناء الغابة السفلية (Stylized Low-poly Pine Forest)
random.seed(42)
for i in range(80):
    tx = random.uniform(-25, 25)
    ty = random.uniform(-10, 35)
    tz = random.uniform(-25, -22)
    s = random.uniform(1.2, 2.8)
    
    bpy.ops.mesh.primitive_cone_add(vertices=5, radius1=1.0 * s, depth=3.0 * s, location=(tx, ty, tz))
    tree = bpy.context.active_object
    tree.data.materials.append(mat_tree_white if random.random() > 0.5 else mat_tree_gray)

# 6. الكاميرا السينمائية الانسيابية
cam_data = bpy.data.cameras.new("LemminoCam")
cam_data.lens = 45
cam = bpy.data.objects.new("LemminoCam", cam_data)
bpy.context.collection.objects.link(cam)
scene.camera = cam

# حركة الكاميرا: تبدأ بمحاذاة الطائرة ثم تلاحق السقوط للأسفل
cam.location = (7, 12, 17)
cam.rotation_euler = (math.radians(80), 0, math.radians(150))
cam.keyframe_insert(data_path="location", frame=1)
cam.keyframe_insert(data_path="rotation_euler", frame=1)

cam.location = (4, 14, 2)
cam.rotation_euler = (math.radians(65), 0, math.radians(160))
cam.keyframe_insert(data_path="location", frame=70)
cam.keyframe_insert(data_path="rotation_euler", frame=70)

cam.location = (2, 14, -12)
cam.rotation_euler = (math.radians(45), 0, math.radians(175))
cam.keyframe_insert(data_path="location", frame=160)
cam.keyframe_insert(data_path="rotation_euler", frame=160)

print(">> تم بناء مشهد LEMMiNO بنجاح، جاري بدء التصيير...")
bpy.ops.render.render(animation=True)
