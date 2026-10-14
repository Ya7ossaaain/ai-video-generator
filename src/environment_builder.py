import math
import random
import bpy
import bmesh
from mathutils import Vector, Matrix

def create_pine_tree_template(collection, mat_forest):
    """إنشاء شجرة صنوبر مخروطية مسننة من 5 طبقات مطابقة لشكل الأشجار في اللقطة المرجعية الأولى."""
    bm = bmesh.new()
    tiers = [
        (0.0,  2.4, 2.35, 0.25),
        (1.3,  3.7, 2.00, 0.20),
        (2.6,  5.0, 1.60, 0.15),
        (3.9,  6.2, 1.15, 0.08),
        (5.1,  7.4, 0.70, 0.01),
    ]
    for idx, (z_bot, z_top, r_bot, r_top) in enumerate(tiers):
        tbm = bmesh.new()
        bmesh.ops.create_cone(
            tbm, cap_ends=True, cap_tris=True, segments=8,
            radius1=r_bot, radius2=r_top, depth=(z_top - z_bot)
        )
        bmesh.ops.rotate(tbm, verts=tbm.verts, matrix=Matrix.Rotation(math.radians(idx * 22.5), 3, 'Z'))
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

def build_forest_canopy(collection, mats, tree_count=520):
    """توزيع غابة الصنوبر الكثيفة على تلة منحنية لطيفة تملأ النصف السفلي للكادر كما في اللقطة الأولى."""
    forest_root = bpy.data.objects.new("Forest_Canopy_Root", None)
    collection.objects.link(forest_root)
    forest_root.location = (0.0, 0.0, -225.0)

    pine_mesh = create_pine_tree_template(collection, mats["forest_gradient"])
    pine_mesh.materials.append(mats["forest_gradient"])

    rng = random.Random(19711124)
    for i in range(tree_count):
        # توزيع كثيف ومتدرج من المقدمة الداكنة إلى المركز الأبيض المضيء
        rx = rng.uniform(-52.0, 52.0)
        ry = rng.uniform(-38.0, 32.0)
        # انحناء التلة بحيث ترتفع الأشجار الوسطى وتنخفض الأطراف بنعومة
        hill_drop = (rx * rx) * 0.0045 + (ry * ry) * 0.0035
        rz = rng.uniform(-0.8, 0.8) - hill_drop
        scale_xy = rng.uniform(1.35, 1.95)
        scale_z  = rng.uniform(1.55, 2.25)

        tree_obj = bpy.data.objects.new(f"PineTree_{i:03d}", pine_mesh)
        collection.objects.link(tree_obj)
        tree_obj.parent = forest_root
        tree_obj.location = (rx, ry, rz)
        tree_obj.rotation_euler = (
            rng.uniform(-0.04, 0.04),
            rng.uniform(-0.04, 0.04),
            rng.uniform(0, 2 * math.pi)
        )
        tree_obj.scale = (scale_xy, scale_xy, scale_z)

    return forest_root

def build_city_bokeh_cluster(collection, mats):
    """
    إنشاء عنقود أضواء المدينة الليلية الضبابية (Soft Bokeh) في الربع السفلي الأيسر للقطة السادسة.
    كل ضوء هو مربع مستقل بإحداثيات UV كاملة لتطبيق التمويه الشعاعي الناعم.
    """
    bokeh_root = bpy.data.objects.new("City_Bokeh_Root", None)
    collection.objects.link(bokeh_root)

    # إنشاء شريحة مربعة قياسية لتوليد إحداثيات Generated من 0 إلى 1 لكل نقطة ضوء
    bm = bmesh.new()
    v1 = bm.verts.new((-0.5, -0.5, 0.0))
    v2 = bm.verts.new(( 0.5, -0.5, 0.0))
    v3 = bm.verts.new(( 0.5,  0.5, 0.0))
    v4 = bm.verts.new((-0.5,  0.5, 0.0))
    bm.faces.new((v1, v2, v3, v4))
    dot_mesh = bpy.data.meshes.new("Soft_Bokeh_Quad")
    bm.to_mesh(dot_mesh)
    bm.free()
    dot_mesh.materials.append(mats["city_bokeh"])

    rng = random.Random(305)
    for idx in range(220):
        # توزيع على شكل قبة/تلة مائلة في الربع السفلي الأيسر كما في اللقطة الثانية المرجعية
        u = rng.uniform(-16.0, 6.0)
        v = rng.uniform(-10.0, 4.0)
        if ((u + 5.0) / 11.5) ** 2 + ((v + 3.0) / 7.5) ** 2 > 1.0:
            continue
        rad = rng.uniform(0.65, 1.35)
        dot_obj = bpy.data.objects.new(f"BokehDot_{idx:03d}", dot_mesh)
        collection.objects.link(dot_obj)
        dot_obj.parent = bokeh_root
        dot_obj.location = (u, rng.uniform(-0.5, 0.5), v)
        dot_obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
        dot_obj.scale = (rad, rad * 0.75, 1.0)

    return bokeh_root

def build_rain_and_birds(collection, mats, rain_count=450, bird_count=42):
    """بناء نقاط المطر الدقيقة وسرب الطيور البيضاء الذي يتطاير من الغابة بعد سقوط Cooper."""
    rain_root = bpy.data.objects.new("Night_Rain_Root", None)
    collection.objects.link(rain_root)
    bm_rain = bmesh.new()
    rng = random.Random(727)
    for _ in range(rain_count):
        px = rng.uniform(-38.0, 38.0)
        py = rng.uniform(-38.0, 38.0)
        pz = rng.uniform(-215.0, 20.0)
        sbm = bmesh.new()
        bmesh.ops.create_icosphere(sbm, subdivisions=1, radius=rng.uniform(0.018, 0.038))
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

    # سرب الطيور البيضاء المتطايرة
    birds = []
    bm_bird = bmesh.new()
    v_center = bm_bird.verts.new((0.0, 0.0, 0.0))
    v_back   = bm_bird.verts.new((0.18, 0.0, 0.0))
    v_wing_l = bm_bird.verts.new((0.06, 0.32, 0.10))
    v_wing_r = bm_bird.verts.new((0.06, -0.32, 0.10))
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