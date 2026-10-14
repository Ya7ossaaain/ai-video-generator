import math
import random
import bpy
import bmesh
from mathutils import Vector, Matrix

def create_pine_tree_template(collection, mat_forest):
    """
    إنشاء شجرة صنوبر ذات 5 طبقات أغصان بارزة ومسننة بوضوح (Deep-Notched Pine Silhouette)
    مع جذع سفلي رفيع، لتطابق تمامًا شكل الأشجار في لقطة LEMMiNO (00:27–00:35).
    """
    bm = bmesh.new()
    # جذع الشجرة السفلي
    trunk_bm = bmesh.new()
    bmesh.ops.create_cone(trunk_bm, cap_ends=True, cap_tris=True, segments=6, radius1=0.28, radius2=0.22, depth=1.6)
    bmesh.ops.translate(trunk_bm, verts=trunk_bm.verts, vec=(0.0, 0.0, 0.8))
    m_tr = bpy.data.meshes.new("tmp_trunk")
    trunk_bm.to_mesh(m_tr)
    trunk_bm.free()
    bm.from_mesh(m_tr)
    bpy.data.meshes.remove(m_tr)

    # 5 طبقات مخروطية بأغصان عريضة بارزة وانحسار عميق بين كل طبقة والتي تليها
    tiers = [
        (1.0,  2.7, 2.55, 0.35),
        (2.1,  3.8, 2.20, 0.30),
        (3.2,  4.9, 1.80, 0.24),
        (4.3,  5.9, 1.35, 0.16),
        (5.3,  7.0, 0.88, 0.01),
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

def build_forest_canopy(collection, mats, tree_count=720):
    """توزيع غابة الصنوبر بحيث تشغل النصف السفلي (42%) من الكادر مع مقدمة مظلمة وقلب أبيض ساطع."""
    forest_root = bpy.data.objects.new("Forest_Canopy_Root", None)
    collection.objects.link(forest_root)
    forest_root.location = (0.0, 0.0, -225.0)

    pine_mesh = create_pine_tree_template(collection, mats["forest_gradient"])
    pine_mesh.materials.append(mats["forest_gradient"])

    rng = random.Random(19711124)
    for i in range(tree_count):
        rx = rng.uniform(-56.0, 56.0)
        ry = rng.uniform(-34.0, 36.0)
        # انحناء لطيف للتلة بحيث تبرز قمم الأشجار منفصلة عن بعضها
        hill_curve = -(rx * rx) * 0.0028 - ((ry - 4.0) ** 2) * 0.0045
        rz = hill_curve + rng.uniform(-0.9, 0.9)
        scale_xy = rng.uniform(0.90, 1.32)
        scale_z  = rng.uniform(1.10, 1.55)

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
    إنشاء حقل أضواء المدينة الليلية الضبابية (900 نقطة Bokeh غاوسية ناعمة)
    على مستوى أرضي مائل يظهر في الربع السفلي الأيسر والأوسط خلال الثواني 00:18–00:20.
    """
    bokeh_root = bpy.data.objects.new("City_Bokeh_Root", None)
    collection.objects.link(bokeh_root)

    # قرص دائري مسطح نصف قطره 1.0 لتعمل عليه عقدة TexCoord->Object->Length بدقة 100%
    bm = bmesh.new()
    bmesh.ops.create_circle(bm, cap_ends=True, radius=1.0, segments=16)
    dot_mesh = bpy.data.meshes.new("Soft_Bokeh_Disc")
    bm.to_mesh(dot_mesh)
    bm.free()
    dot_mesh.materials.append(mats["city_bokeh"])

    rng = random.Random(305)
    # توليد 850 نقطة ضوئية صغيرة متداخلة بنعومة على شكل شبكة شوارع مدينة بعيدة
    for idx in range(850):
        # توزيع يغطي الربع السفلي الأيسر ويمتد قطريًا نحو الأسفل الأيمن كما في 00:18–00:20
        u = rng.uniform(-26.0, 14.0)
        v = rng.uniform(-18.0, 12.0)
        # معادلة قطع ناقص مائل ليطابق الحد المنحني لأضواء المدينة في اللقطة المرجعية الثانية
        u_rot = (u + 6.0) * math.cos(0.35) - (v + 3.5) * math.sin(0.35)
        v_rot = (u + 6.0) * math.sin(0.35) + (v + 3.5) * math.cos(0.35)
        if (u_rot / 19.5) ** 2 + (v_rot / 12.5) ** 2 > 1.0:
            continue

        dot_obj = bpy.data.objects.new(f"BokehDisc_{idx:03d}", dot_mesh)
        collection.objects.link(dot_obj)
        dot_obj.parent = bokeh_root
        dot_obj.location = (u, v, rng.uniform(-0.08, 0.08))
        rad = rng.uniform(0.38, 0.82)
        dot_obj.scale = (rad, rad * 0.85, 1.0)

    return bokeh_root

def build_rain_and_birds(collection, mats, rain_count=320, bird_count=55):
    """
    بناء:
    1. خطوط الضباب الافتتاحية المحيطية (00:00–00:02) خارج مركز الشاشة.
    2. جزيئات المطر الليلي + خطوط المطر القطرية فوق الغابة (00:28–00:36).
    3. سرب الطيور البيضاء المتطايرة من قمم الأشجار (00:29.5–00:36).
    """
    rain_root = bpy.data.objects.new("Night_Rain_Root", None)
    collection.objects.link(rain_root)

    # 1. خطوط الرياح الافتتاحية (في المحيط الخارجي فقط radius = 14..28 حتى لا تقطع الطائرة أبدًا!)
    bm_wind = bmesh.new()
    rng_w = random.Random(1971)
    for _ in range(75):
        angle = rng_w.uniform(0, 2 * math.pi)
        radius = rng_w.uniform(14.0, 28.0)
        wx = rng_w.uniform(-155.0, -52.0)
        wy = radius * math.cos(angle)
        wz = radius * math.sin(angle) * 0.65
        sbm = bmesh.new()
        bmesh.ops.create_cone(sbm, cap_ends=True, segments=6, radius1=0.035, radius2=0.010, depth=rng_w.uniform(4.5, 9.0))
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

    # 2. نقاط المطر الدقيقة في الفراغ
    bm_rain = bmesh.new()
    rng = random.Random(727)
    for _ in range(rain_count):
        px = rng.uniform(-26.0, 26.0)
        py = rng.uniform(-26.0, 26.0)
        pz = rng.uniform(-210.0, 12.0)
        sbm = bmesh.new()
        bmesh.ops.create_icosphere(sbm, subdivisions=1, radius=rng.uniform(0.014, 0.028))
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

    # 3. خطوط المطر القطرية المتساقطة أمام الغابة (00:28–00:36 في فيديو LEMMiNO)
    bm_f_rain = bmesh.new()
    for _ in range(180):
        rx = rng.uniform(-38.0, 38.0)
        ry = rng.uniform(-32.0, -18.0)
        rz = rng.uniform(-225.0, -185.0)
        sbm = bmesh.new()
        bmesh.ops.create_cone(sbm, cap_ends=True, segments=5, radius1=0.022, radius2=0.012, depth=rng.uniform(0.9, 1.8))
        # إمالة قطرية بزاوية 22 درجة كما في 00:31–00:35
        bmesh.ops.rotate(sbm, verts=sbm.verts, matrix=Matrix.Rotation(math.radians(22.0), 3, 'Y'))
        bmesh.ops.translate(sbm, verts=sbm.verts, vec=(rx, ry, rz))
        m_tmp = bpy.data.meshes.new("tmp_frain")
        sbm.to_mesh(m_tmp)
        sbm.free()
        bm_f_rain.from_mesh(m_tmp)
        bpy.data.meshes.remove(m_tmp)

    f_rain_mesh = bpy.data.meshes.new("Forest_Diagonal_Rain_Mesh")
    bm_f_rain.to_mesh(f_rain_mesh)
    bm_f_rain.free()
    f_rain_mesh.materials.append(mats["rain_streak"])
    f_rain_obj = bpy.data.objects.new("Forest_Diagonal_Rain", f_rain_mesh)
    collection.objects.link(f_rain_obj)
    f_rain_obj.parent = rain_root

    # 4. سرب الطيور البيضاء المتطايرة
    birds = []
    bm_bird = bmesh.new()
    v_center = bm_bird.verts.new((0.0, 0.0, 0.0))
    v_back   = bm_bird.verts.new((0.15, 0.0, 0.0))
    v_wing_l = bm_bird.verts.new((0.04, 0.25, 0.08))
    v_wing_r = bm_bird.verts.new((0.04, -0.25, 0.08))
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
