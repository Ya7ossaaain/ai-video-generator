import bpy
import math
import random

# ==========================================
# 1. تنظيف المشهد وضبط إعدادات الرندر
# ==========================================
bpy.ops.wm.read_factory_settings(use_empty=True)

scene = bpy.context.scene
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 180  # 7.5 ثوانٍ كاملة للمشهد

# تصدير فيديو عالي الدقة MP4 (H.264)
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.filepath = "//lemmino_db_cooper.mp4"
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

# محرك الرندر
scene.render.engine = 'CYCLES'
scene.cycles.samples = 8
scene.cycles.use_denoising = False

# ==========================================
# 2. الخامات (LEMMiNO Minimalist Style)
# ==========================================
def create_mat(name, color, is_emission=True, strength=1.0):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()
    out = nodes.new('ShaderNodeOutputMaterial')
    if is_emission:
        shader = nodes.new('ShaderNodeEmission')
        shader.inputs['Color'].default_value = color
        shader.inputs['Strength'].default_value = strength
        mat.node_tree.links.new(shader.outputs['Emission'], out.inputs['Surface'])
    else:
        shader = nodes.new('ShaderNodeBsdfDiffuse')
        shader.inputs['Color'].default_value = color
        mat.node_tree.links.new(shader.outputs['BSDF'], out.inputs['Surface'])
    return mat

mat_solid_black = create_mat("SolidBlack", (0.01, 0.01, 0.01, 1), is_emission=False)
mat_white_line  = create_mat("WhiteLine", (1.0, 1.0, 1.0, 1), is_emission=True, strength=3.0)
mat_red_cooper  = create_mat("RedCooper", (1.0, 0.02, 0.02, 1), is_emission=True, strength=4.0)
mat_tree_white  = create_mat("TreeWhite", (0.95, 0.95, 0.95, 1), is_emission=True, strength=2.0)
mat_tree_dark   = create_mat("TreeDark",  (0.12, 0.12, 0.12, 1), is_emission=True, strength=0.6)

# خلفية سوداء تامة
world = bpy.data.worlds.new("BlackVoid")
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0, 0, 0, 1)
scene.world = world

# وظيفة تطبيق الخط الأبيض الخارجي (Inverted Hull Outline)
def apply_inverted_hull(obj, thickness=0.035):
    obj.data.materials.append(mat_solid_black)
    obj.data.materials.append(mat_white_line)
    solid = obj.modifiers.new(name="Outline", type='SOLIDIFY')
    solid.thickness = thickness
    solid.offset = 1.0
    solid.material_offset = 1
    solid.use_flip_normals = True

# ==========================================
# 3. بناء طائرة Boeing 727 الحقيقية بتفاصيلها
# ==========================================
plane_mesh_parts = []

# جسم الطائرة الرئيسي (Fuselage)
bpy.ops.mesh.primitive_cylinder_add(radius=1.1, depth=14, location=(0, 0, 16))
fuselage = bpy.context.active_object
fuselage.rotation_euler = (math.radians(90), 0, 0)
fuselage.scale = (1.0, 1.0, 1.1)
plane_mesh_parts.append(fuselage)

# مقدمة الطائرة الانسيابية (Nose Cone)
bpy.ops.mesh.primitive_cone_add(radius1=1.1, depth=3.2, location=(0, -8.5, 16))
nose = bpy.context.active_object
nose.rotation_euler = (math.radians(-90), 0, 0)
plane_mesh_parts.append(nose)

# الأجنحة الرئيسية المائلة للخلف (Swept Wings)
bpy.ops.mesh.primitive_cube_add(size=1, location=(-6.5, 0, 15.6))
left_wing = bpy.context.active_object
left_wing.scale = (11.0, 2.8, 0.12)
left_wing.rotation_euler = (math.radians(4), math.radians(4), math.radians(28))
plane_mesh_parts.append(left_wing)

bpy.ops.mesh.primitive_cube_add(size=1, location=(6.5, 0, 15.6))
right_wing = bpy.context.active_object
right_wing.scale = (11.0, 2.8, 0.12)
right_wing.rotation_euler = (math.radians(4), math.radians(-4), math.radians(-28))
plane_mesh_parts.append(right_wing)

# ذيل Boeing 727 العمودي (T-Tail Fin)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 5.5, 18.2))
tail_fin = bpy.context.active_object
tail_fin.scale = (0.2, 3.2, 3.8)
tail_fin.rotation_euler = (math.radians(-32), 0, 0)
plane_mesh_parts.append(tail_fin)

# الجناح الأفقي أعلى الذيل (Horizontal Stabilizer)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 6.8, 20.0))
tail_wing = bpy.context.active_object
tail_wing.scale = (6.0, 1.6, 0.1)
tail_wing.rotation_euler = (math.radians(-5), 0, 0)
plane_mesh_parts.append(tail_wing)

# المحركات النفاثة الخلفية الثلاثة (3 Jet Engines)
for side in [-1.5, 1.5]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.55, depth=3.2, location=(side, 4.2, 16.5))
    eng = bpy.context.active_object
    eng.rotation_euler = (math.radians(90), 0, 0)
    plane_mesh_parts.append(eng)

# الدرج الخلفي الهابط المتوهج (Aft Airstair)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 6.4, 14.7))
stairs = bpy.context.active_object
stairs.scale = (0.7, 2.4, 0.08)
stairs.rotation_euler = (math.radians(-42), 0, 0)
stairs.data.materials.append(mat_red_cooper)

# تجميع الطائرة وإضافة التحديد الهندسي الفخم
bpy.ops.object.select_all(action='DESELECT')
for p in plane_mesh_parts:
    p.select_set(True)
bpy.context.view_layer.objects.active = fuselage
bpy.ops.object.join()
airplane = bpy.context.active_object
apply_inverted_hull(airplane, thickness=0.035)

# ربط الدرج بالطائرة وتحريكها
stairs.parent = airplane

# تحريك الطائرة تشق الظلام للأمام
airplane.location = (0, 0, 0)
airplane.keyframe_insert(data_path="location", frame=1)
airplane.location = (0, -70, 4)
airplane.keyframe_insert(data_path="location", frame=180)

# ==========================================
# 4. بناء شخصية المظلي الحقيقية (Skydiving Skydiver)
# ==========================================
jumper_parts = []

# الرأس
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.32, location=(0, 0, 0.9))
jumper_parts.append(bpy.context.active_object)

# الجذع المقوس (Arched Torso)
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -0.1, 0.2))
torso = bpy.context.active_object
torso.scale = (0.75, 0.45, 1.0)
jumper_parts.append(torso)

# حقيبة المظلة على الظهر
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0.22, 0.3))
rig = bpy.context.active_object
rig.scale = (0.55, 0.25, 0.75)
jumper_parts.append(rig)

# الأذرع المفرودة لوضعية القفز
for side in [-1, 1]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.13, depth=1.1, location=(side * 0.75, -0.2, 0.5))
    arm = bpy.context.active_object
    arm.rotation_euler = (math.radians(-25), math.radians(side * 55), 0)
    jumper_parts.append(arm)

# الأرجل المثنية بزاوية السقوط الحر
for side in [-1, 1]:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.15, depth=1.3, location=(side * 0.45, 0.3, -0.7))
    leg = bpy.context.active_object
    leg.rotation_euler = (math.radians(45), math.radians(side * 20), 0)
    jumper_parts.append(leg)

bpy.ops.object.select_all(action='DESELECT')
for jp in jumper_parts:
    jp.select_set(True)
bpy.context.view_layer.objects.active = torso
bpy.ops.object.join()
skydiver = bpy.context.active_object
skydiver.data.materials.append(mat_red_cooper)

# أنيميشن القفز: ينطلق من الدرج ويهوي بحرية
skydiver.location = (0, 7.2, 14.2)
skydiver.rotation_euler = (math.radians(-20), 0, 0)
skydiver.keyframe_insert(data_path="location", frame=1)
skydiver.keyframe_insert(data_path="rotation_euler", frame=1)

# لحظة الانفصال عن الطائرة
skydiver.location = (0, 8.5, 13.6)
skydiver.keyframe_insert(data_path="location", frame=25)

# السقوط الحر التدويري في الفضاء المظلم
skydiver.location = (1.5, 16.0, -14.0)
skydiver.rotation_euler = (math.radians(180), math.radians(120), math.radians(45))
skydiver.keyframe_insert(data_path="location", frame=110)
skydiver.keyframe_insert(data_path="rotation_euler", frame=110)

# الهبوط في قلب بقعة ضوء الغابة
skydiver.location = (0.2, 28.0, -32.0)
skydiver.rotation_euler = (math.radians(380), math.radians(240), math.radians(90))
skydiver.keyframe_insert(data_path="location", frame=180)
skydiver.keyframe_insert(data_path="rotation_euler", frame=180)

# ==========================================
# 5. خطوط السرعة والرياح (Speed Lines)
# ==========================================
random.seed(1971)
for i in range(45):
    sx = random.uniform(-16, 16)
    sy = random.uniform(-25, 25)
    sz = random.uniform(8, 22)
    slen = random.uniform(2.5, 6.0)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.015, depth=slen, location=(sx, sy, sz))
    sline = bpy.context.active_object
    sline.rotation_euler = (math.radians(90), 0, 0)
    sline.data.materials.append(mat_white_line)
    
    # تحريك خطوط الرياح مسرعة للأمام والخلف
    sline.keyframe_insert(data_path="location", frame=1)
    sline.location.y += random.uniform(35, 60)
    sline.keyframe_insert(data_path="location", frame=180)

# ==========================================
# 6. سجادة الغابة المتراصة الكثيفة (Dense Forest Canopy)
# ==========================================
for i in range(160):
    tx = random.uniform(-35, 35)
    ty = random.uniform(5, 55)
    tz = random.uniform(-36, -34)
    dist_center = math.sqrt(tx**2 + (ty - 30)**2)
    scale_val = random.uniform(1.2, 2.4)
    
    # شجرة صنوبر ثلاثية الطبقات
    bpy.ops.mesh.primitive_cone_add(vertices=6, radius1=1.1 * scale_val, depth=2.8 * scale_val, location=(tx, ty, tz))
    tree = bpy.context.active_object
    
    # الأشجار في مركز بقعة الضوء بيضاء تماماً والأطراف داكنة
    if dist_center < 12.0:
        tree.data.materials.append(mat_tree_white)
    else:
        tree.data.materials.append(mat_tree_dark)

# ==========================================
# 7. الإخراج السينمائي للكاميرا (LEMMiNO Cinematography)
# ==========================================
cam_data = bpy.data.cameras.new("DirectorCam")
cam_data.lens = 50  # عدسة 50mm تمنع التشوه
cam = bpy.data.objects.new("DirectorCam", cam_data)
bpy.context.collection.objects.link(cam)
scene.camera = cam

# اللقطة الأولى (1-40): ملاحقة الطائرة والدرج الخلفي بزاوية مائلة فخمة
cam.location = (8.5, 12.5, 18.0)
cam.rotation_euler = (math.radians(78), 0, math.radians(148))
cam.keyframe_insert(data_path="location", frame=1)
cam.keyframe_insert(data_path="rotation_euler", frame=1)

# اللقطة الثانية (40-110): النزول لتتبع الشخصية الساقطة في الظلام
cam.location = (4.2, 13.5, 4.0)
cam.rotation_euler = (math.radians(65), 0, math.radians(160))
cam.keyframe_insert(data_path="location", frame=70)
cam.keyframe_insert(data_path="rotation_euler", frame=70)

# اللقطة الثالثة (110-180): زاوية علوية تلاحق السقوط في بقعة ضوء الغابة
cam.location = (2.0, 20.0, -18.0)
cam.rotation_euler = (math.radians(48), 0, math.radians(175))
cam.keyframe_insert(data_path="location", frame=180)
cam.keyframe_insert(data_path="rotation_euler", fra
