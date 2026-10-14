import math
import random
import bpy
import bmesh
from mathutils import Vector, Matrix

def create_pine_tree_template(collection, mat_forest):
    """
    إنشاء شجرة صنوبر ذات 5 طبقات أغصان عريضة ومسننة (Sawtooth Conifer Silhouette)
    تطابق تمامًا شكل الأشجار في لقطة LEMMiNO (00:27–00:35).
    """
    bm = bmesh.new()
    # كل طبقة لها قاعدة عريضة بارزة وانحسار واضح قبل الطبقة التي فوقها
    tiers = [
        (0.0,  2.1, 2.75, 0.70),
        (1.4,  3.5, 2.30, 0.55),
        (2.8,  4.8, 1.85, 0.42),
        (4.1,  6.0, 1.35, 0.25),
        (5.3,  7.3, 0.85, 0.02),
    ]
    for idx, (z_bot, z_top, r_bot, r_top) in enumerate(tiers):
        tbm = bmesh.new()
        bmesh.ops.create_cone(
            tbm, cap_ends=True, cap_tris=True, segments=7,
            radius1=r_bot, radius2=r_top, depth=(z_top - z_bot)
        )
        bmesh.ops.rotate(tbm, verts=tbm.verts, matrix=Matrix.Rotation(math.radians(idx * 25.0), 3, 'Z'))
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

def build_forest_canopy(collection, mats, tree_count=620):
    """توزيع غابة الصنوبر بحيث تشغل النصف السفلي من الكادر مع مقدمة مظلمة وقلب أبيض ساطع."""
    forest_root = bpy.data.objects.new("Forest_Canopy_Root", None)
    collection.objects.link(forest_root)
    forest_root.location = (0.0, 0.0, -225.0)

    pine_mesh = create_pine_tree_template(collection, mats["forest_gradient"])
    pine_mesh.materials.append(mats["forest_gradient"])

    rng = random.Random(19711124)
    for i in range(tree_count):
        rx = rng.uniform(-58.0, 58.0)
        ry = rng.uniform(-34.0, 36.0)
        # انحناء التلة بحيث ترتفع الأشجار الوسطى وتنحدر الأطراف الجانبية برفق
        hill_curve = -(rx * rx) * 0.0038 - ((ry - 2.0) ** 2) * 0.0032
        rz = hill_curve + rng.uniform(-0.7, 0.7)
        scale_xy = rng.uniform(1.15, 1.65)
        scale_z  = rng.uniform(1.35, 1.95)

        tree_obj = bpy.data.objects.new(f"PineTree_{i:03d}", pine_mesh)
        collection.objects.link(tree_obj)
        tree_obj.parent = forest_root
        tree_obj.location = (rx, ry, rz)
        tree_obj.rotation_euler = (
            rng.uniform(-0.03, 0.03),
            rng.uniform(-0.03, 0.03),
            rng.uniform(0, 2 * math.pi)
        )
        tree_obj.scale = (scale_xy, scale_xy, scale_z)

    return forest_root

def build_city_bokeh_cluster(collection, mats):
    """
    إنشاء شبكة أضواء المدينة الليلية الضبابية (Bokeh Grid — 00:18 إلى 00:21 في مقطع LEMMiNO).
    نستخدم كرات مفلطحة ناعمة تتفاعل مع LayerWeight->Facing ومع عمق الميدان لتبدو مموهة تمامًا.
    """
    bokeh_root = bpy.data.objects.new("City_Bokeh_Root", None)
    collection.objects.link(bokeh_root)

    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.42)
    bmesh.ops.scale(bm, verts=bm.verts, vec=(1.0, 1.0, 0.35))
    dot_mesh = bpy.data.meshes.new("Soft_Bokeh_Sphere")
    bm.to_mesh(dot_mesh)
    bm.free()
    dot_mesh.materials.append(mats["city_bokeh"])
    for poly in dot_mesh.polygons:
        poly.use_smooth = True

    rng = random.Random(305)
    # توزيع الأضواء في صفوف شوارع عضوية مائلة كما في 00:18–00:20 من مقطع LEMMiNO
    for gx in range(-22, 12):
        for gy in range(-18, 14):
            if rng.random() < 0.38:
                continue
            u = gx * 0.95 + rng.uniform(-0.28, 0.28)
            v = gy * 0.95 + rng.uniform(-0.28, 0.28)
            # حصر التجمع في قوس يغطي الربع السفلي الأيسر والأوسط
            if ((u + 5.5) / 16.5) ** 2 + ((v + 2.5) / 13.5) ** 2 > 1.0:
                continue
            dot_obj = bpy.data.objects.new(f"BokehLight_{gx}_{gy}", dot_mesh)
            collection.objects.link(dot_obj)
            dot_obj.parent = bokeh_root
            dot_obj.location = (u, v, rng.uniform(-0.15, 0.15))
            s = rng.uniform(0.75, 1.35)
            dot_obj.scale = (s, s, s)

    return bokeh_root

def build_rain_and_birds(collection, mats, rain_count=350, bird_count=48):
    """
    بناء:
    1. خطوط الرياح الافتتاحية المندفعة (00:00–00:02).
    2. جزيئات المطر الدقيقة أثناء السقوط الحر + خطوط المطر القطرية فوق الغابة (00:28–00:36).
    3. سرب الطيور البيضاء المتطايرة من قمم الأشجار (00:30–00:36).
    """
    rain_root = bpy.data.objects.new("Night_Rain_Root", None)
    collection.objects.link(rain_root)

    # 1. خطوط الرياح/الضباب الافتتاحية حول مسار اقتراب الكاميرا (00:00–00:02)
    bm_wind = bmesh.new()
    rng_w = random.Random(1971)
    for _ in range(95):
        angle = rng_w.uniform(0, 2 * math.pi)
        radius = rng_w.uniform(3.2, 11.5)
        wx = rng_w.uniform(-95.0, -28.0)
        wy = radius * math.cos(angle)
        wz = radius * math.sin(angle) * 0.65 - 1.5
        sbm = bmesh.new()
        bmesh.ops.create_cone(sbm, cap_ends=True, segments=6, radius1=0.045, radius2=0.015, depth=rng_w.uniform(3.5, 7.5))
        bmesh.ops.rotate(sbm, verts=sbm.verts, matrix=Matrix.Rotation(math.radians(90), 3, 'Y'))
        bmesh.ops.translate(sbm, verts=sbm.verts, vec=(wx, wy, wz))
        m_tmp = bpy.data.meshes.new("tmp_wind")
        sbm.to_mesh(m_tmp)
        sbm.free()
        bm_wind.from_mesh(m_tmp)
        bpy.data.meshes.remove(m_tmp)

    wind_mesh = bpy.data.meshes.new("Intro_Wind_Streaks_Mesh")
    bm_wind.to_mesh(wind_mesh)
    bm_wind.free()
    wind_mesh.materials.append(mats["rain_streak"])
    wind_obj = bpy.data.objects.new("Intro_Wind_Streaks", wind_mesh)
    collection.objects.link(wind_obj)
    wind_obj.parent = rain_root

    # 2. نقاط المطر الدقيقة في الفراغ + خطوط المطر القطرية فوق الغابة
    bm_rain = bmesh.new()
    rng = random.Random(727)
    for _ in range(rain_count):
        px = rng.uniform(-28.0, 28.0)
        py = rng.uniform(-28.0, 28.0)
        pz = rng.uniform(-210.0, 12.0)
        sbm = bmesh.new()
        bmesh.ops.create_icosphere(sbm, subdivisions=1, radius=rng.uniform(0.016, 0.032))
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

    # 3. سرب الطيور البيضاء المتطايرة
    birds = []
    bm_bird = bmesh.new()
    v_center = bm_bird.verts.new((0.0, 0.0, 0.0))
    v_back   = bm_bird.verts.new((0.16, 0.0, 0.0))
    v_wing_l = bm_bird.verts.new((0.05, 0.28, 0.09))
    v_wing_r = bm_bird.verts.new((0.05, -0.28, 0.09))
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
