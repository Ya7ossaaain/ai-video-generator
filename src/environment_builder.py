import math
import random
import bpy
import bmesh
from mathutils import Vector, Matrix
from .compat import set_smooth_shading

def create_pine_tree_template(collection, mat_forest):
    """إنشاء نموذج شجرة صنوبر مضلعة متعددة الطبقات (4 طبقات مخروطية) مطابقة للقطة الأولى المرجعية."""
    bm = bmesh.new()
    tiers = [
        (0.0,  2.2, 2.2, 0.2),
        (1.4,  3.8, 1.85, 0.15),
        (2.8,  5.2, 1.45, 0.10),
        (4.1,  6.5, 0.95, 0.02),
    ]
    for z_bot, z_top, r_bot, r_top in tiers:
        tbm = bmesh.new()
        bmesh.ops.create_cone(
            tbm, cap_ends=True, cap_tris=True, segments=7,
            radius1=r_bot, radius2=r_top, depth=(z_top - z_bot)
        )
        bmesh.ops.translate(tbm, verts=tbm.verts, vec=(0.0, 0.0, (z_bot + z_top) * 0.5))
        mesh_tmp = bpy.data.meshes.new("tmp_tier")
        tbm.to_mesh(mesh_tmp)
        tbm.free()
        bm.from_mesh(mesh_tmp)
        bpy.data.meshes.remove(mesh_tmp)

    mesh = bpy.data.meshes.new("LEMMiNO_PineTree_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    return mesh

def build_forest_canopy(collection, mats, tree_count=400):
    """توزيع غابة الصنوبر الكثيفة في مستوى الهبوط (Z = -225) مع التدرج اللوني الشعاعي."""
    forest_root = bpy.data.objects.new("Forest_Canopy_Root", None)
    collection.objects.link(forest_root)
    forest_root.location = (0.0, 0.0, -225.0)

    pine_mesh = create_pine_tree_template(collection, mats["forest_gradient"])
    pine_mesh.materials.append(mats["forest_gradient"])

    rng = random.Random(19711124)  # بذرة ثابتة مرتبطة بتاريخ القفزة 24 نوفمبر 1971
    for i in range(tree_count):
        # توزيع كثيف في منطقة المنتصف والكاميرا
        rx = rng.uniform(-75.0, 75.0)
        ry = rng.uniform(-45.0, 55.0)
        rz = rng.uniform(-2.5, 2.5) - abs(rx) * 0.04
        scale_xy = rng.uniform(1.4, 2.3)
        scale_z  = rng.uniform(1.6, 2.7)

        tree_obj = bpy.data.objects.new(f"PineTree_{i:03d}", pine_mesh)
        collection.objects.link(tree_obj)
        tree_obj.parent = forest_root
        tree_obj.location = (rx, ry, rz)
        tree_obj.rotation_euler = (
            rng.uniform(-0.05, 0.05),
            rng.uniform(-0.05, 0.05),
            rng.uniform(0, 2 * math.pi)
        )
        tree_obj.scale = (scale_xy, scale_xy, scale_z)
        # إخفاء الأشجار من حسابات Freestyle لتبقى ناعمة كما في اللقطة المرجعية الأولى
        tree_obj.hide_render = False

    return forest_root

def build_city_bokeh_cluster(collection, mats):
    """إنشاء عنقود أضواء المدينة الليلية البعيدة ليظهر مموهًا (Bokeh) في اللقطة الثانية المرجعية."""
    bokeh_root = bpy.data.objects.new("City_Bokeh_Root", None)
    collection.objects.link(bokeh_root)
    # يوضع أسفل وخلف Cooper ليظهر في الربع السفلي الأيسر خلال اللقطة السادسة
    bokeh_root.location = (-18.0, 28.0, -145.0)

    bm = bmesh.new()
    rng = random.Random(305)
    for _ in range(260):
        # توزيع على شكل قوس حضري مائل كما يظهر في اللقطة المرجعية الثانية
        u = rng.uniform(-28.0, 16.0)
        v = rng.uniform(-18.0, 12.0)
        if (u * 0.6)**2 + v**2 > 320.0:
            continue
        rad = rng.uniform(0.22, 0.52)
        cbm = bmesh.new()
        bmesh.ops.create_circle(cbm, cap_ends=True, radius=rad, segments=8)
        bmesh.ops.translate(cbm, verts=cbm.verts, vec=(u, v, rng.uniform(-1.5, 1.5)))
        m_tmp = bpy.data.meshes.new("tmp_dot")
        cbm.to_mesh(m_tmp)
        cbm.free()
        bm.from_mesh(m_tmp)
        bpy.data.meshes.remove(m_tmp)

    mesh = bpy.data.meshes.new("City_Bokeh_Mesh")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(mats["city_bokeh"])
    bokeh_obj = bpy.data.objects.new("City_Bokeh_Lights", mesh)
    collection.objects.link(bokeh_obj)
    bokeh_obj.parent = bokeh_root
    return bokeh_root

def build_rain_and_birds(collection, mats, rain_count=600, bird_count=40):
    """بناء جزيئات المطر الليلي وسرب الطيور البيضاء الذي يتطاير من الغابة بعد سقوط Cooper."""
    # 1. جزيئات ونقاط المطر في الهواء (Rain Specks — اللقطة الثالثة المرجعية)
    rain_root = bpy.data.objects.new("Night_Rain_Root", None)
    collection.objects.link(rain_root)
    bm_rain = bmesh.new()
    rng = random.Random(727)
    for _ in range(rain_count):
        px = rng.uniform(-45.0, 45.0)
        py = rng.uniform(-45.0, 45.0)
        pz = rng.uniform(-210.0, 25.0)
        sbm = bmesh.new()
        bmesh.ops.create_icosphere(sbm, subdivisions=1, radius=rng.uniform(0.025, 0.055))
        bmesh.ops.scale(sbm, verts=sbm.verts, vec=(1.0, 1.0, rng.uniform(1.5, 3.5)))
        bmesh.ops.translate(sbm, verts=sbm.verts, vec=(px, py, pz))
        m_tmp = bpy.data.meshes.new("tmp_rain")
        sbm.to_mesh(m_tmp)
        sbm.free()
        bm_rain.from_mesh(m_tmp)
        bpy.data.meshes.remove(m_tmp)

    rain_mesh = bpy.data.meshes.new("Night_Rain_Mesh")
    bm_rain.to_mesh(rain_mesh)
    bm_rain.free()
    rain_mesh.materials.append(mats["white_line"])
    rain_obj = bpy.data.objects.new("Night_Rain_Particles", rain_mesh)
    collection.objects.link(rain_obj)
    rain_obj.parent = rain_root

    # 2. سرب الطيور البيضاء المتطايرة من قمم الأشجار (Flock of Birds — 00:35 في الفيديو)
    birds = []
    bm_bird = bmesh.new()
    v_center = bm_bird.verts.new((0.0, 0.0, 0.0))
    v_back   = bm_bird.verts.new((0.22, 0.0, 0.0))
    v_wing_l = bm_bird.verts.new((0.08, 0.38, 0.12))
    v_wing_r = bm_bird.verts.new((0.08, -0.38, 0.12))
    bm_bird.faces.new((v_center, v_back, v_wing_l))
    bm_bird.faces.new((v_center, v_wing_r, v_back))
    bird_mesh = bpy.data.meshes.new("White_Bird_Mesh")
    bm_bird.to_mesh(bird_mesh)
    bm_bird.free()
    bird_mesh.materials.append(mats["white_line"])

    for b in range(bird_count):
        b_obj = bpy.data.objects.new(f"Forest_Bird_{b:02d}", bird_mesh)
        collection.objects.link(b_obj)
        birds.append(b_obj)

    return rain_root, birds