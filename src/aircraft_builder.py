import math
import bpy
import bmesh
from mathutils import Vector, Matrix
from .compat import set_smooth_shading
from .materials import add_inverted_hull_outline

def create_mesh_object(name, bm, collection, material=None, mark_sharp_angle=32.0):
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    # تعليم الحواف الهندسية الحادة ليظهرها Freestyle باللون الأبيض بوضوح
    angle_rad = math.radians(mark_sharp_angle)
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            a = edge.link_faces[0].normal.angle(edge.link_faces[1].normal, 0.0)
            if a >= angle_rad:
                edge.smooth = False
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    set_smooth_shading(obj, mark_sharp_angle)
    # تفعيل علامات Freestyle على الحواف الحادة
    for edge in obj.data.edges:
        if not edge.use_smooth:
            edge.use_freestyle_mark = True
    return obj

def build_lofted_fuselage(collection, mat_body, mat_white):
    """نسج بدن طائرة Boeing 727-100 عبر مقاطع عرضية انسيابية (Lofted Stations)."""
    bm = bmesh.new()
    # محطات البدن: (x_pos, radius_y, radius_z, z_offset)
    # الطائرة تتجه نحو المحور -X (المقدمة عند X = -19.5، الذيل عند X = +18.0)
    stations = [
        (-19.6, 0.04, 0.04, -0.35),
        (-19.1, 0.45, 0.42, -0.32),
        (-18.2, 0.92, 0.85, -0.25),
        (-17.0, 1.32, 1.18, -0.12),  # زجاج قمرة القيادة
        (-15.5, 1.68, 1.72, 0.02),
        (-13.0, 1.88, 2.02, 0.08),
        (-9.0,  1.90, 2.05, 0.08),
        (-3.0,  1.90, 2.05, 0.08),
        (3.5,   1.90, 2.05, 0.08),
        (8.0,   1.85, 1.98, 0.12),
        (10.8,  1.62, 1.78, 0.25),   # بداية فتحة السلم الخلفي السفلي
        (13.8,  1.22, 1.42, 0.52),
        (16.5,  0.68, 0.85, 0.78),
        (18.2,  0.32, 0.38, 0.92),   # فوهة المحرك الأوسط رقم 2
    ]

    ring_Factor = 32
    rings = []
    for x, ry, rz, z_off in stations:
        ring_verts = []
        for i in range(ring_Factor):
            theta = (2.0 * math.pi * i) / ring_Factor
            y = ry * math.cos(theta)
            z_raw = math.sin(theta)
            # تسطيح خفيف للبطن السفلي في منطقة السلم الخلفي
            if 9.5 <= x <= 14.5 and z_raw < -0.55:
                z_raw = -0.55
            z = rz * z_raw + z_off
            v = bm.verts.new((x, y, z))
            ring_verts.append(v)
        rings.append(ring_verts)

    for r_idx in range(len(rings) - 1):
        r1 = rings[r_idx]
        r2 = rings[r_idx + 1]
        for i in range(ring_Factor):
            i_next = (i + 1) % ring_Factor
            bm.faces.new((r1[i], r1[i_next], r2[i_next], r2[i]))

    # إغلاق المقدمة والفوهة الخلفية
    bmesh.ops.contextual_create(bm, geom=rings[0])
    bmesh.ops.contextual_create(bm, geom=rings[-1])

    fuselage = create_mesh_object("B727_Fuselage", bm, collection, mat_body, 28.0)
    add_inverted_hull_outline(fuselage, mat_white, thickness=0.028)
    return fuselage

def build_swept_wings_and_flaps(collection, parent_obj, mat_body, mat_white):
    """بناء الجناحين المرتدين بزاوية 32°، مع الجنيحات الممتدة بزاوية 15° وأربعة مسارات جنيحات لكل جناح."""
    for side in [-1, 1]:
        side_name = "L" if side == 1 else "R"
        bm = bmesh.new()
        # مقاطع الجناح من الجذر إلى الطرف (Airfoil Profile)
        wing_sections = [
            # (x_lead, x_trail, y_span, z_pos, thickness)
            (-3.2, 4.2, side * 1.75, -0.55, 0.52),
            (0.2,  5.6, side * 6.50, -0.35, 0.38),
            (4.8,  8.1, side * 12.8, -0.10, 0.24),
            (8.6, 10.3, side * 17.2,  0.15, 0.12),
        ]
        sec_rings = []
        pts_profile = [
            (0.0, 0.0), (0.15, 0.55), (0.50, 0.45), (1.0, 0.04),
            (1.0, -0.04), (0.50, -0.30), (0.15, -0.32)
        ]
        for xl, xt, y, z, th in wing_sections:
            chord = xt - xl
            ring = []
            for px, pz in pts_profile:
                vx = xl + px * chord
                vz = z + pz * th
                ring.append(bm.verts.new((vx, y, vz)))
            sec_rings.append(ring)

        n_pts = len(pts_profile)
        for s in range(len(sec_rings) - 1):
            r1, r2 = sec_rings[s], sec_rings[s + 1]
            for i in range(n_pts):
                inext = (i + 1) % n_pts
                bm.faces.new((r1[i], r1[inext], r2[inext], r2[i])) if side == 1 else bm.faces.new((r1[inext], r1[i], r2[i], r2[inext]))
        bmesh.ops.contextual_create(bm, geom=sec_rings[-1])

        wing_obj = create_mesh_object(f"B727_Wing_{side_name}", bm, collection, mat_body, 25.0)
        wing_obj.parent = parent_obj
        add_inverted_hull_outline(wing_obj, mat_white, thickness=0.022)

        # بناء 4 هياكل لمسارات الجنيحات (Flap Track Fairings) كما في اللقطة الرابعة المرجعية
        fairing_spans = [3.4, 5.8, 8.4, 11.2]
        for idx, sp in enumerate(fairing_spans):
            t_ratio = (sp - 1.75) / (17.2 - 1.75)
            fx = 4.2 + t_ratio * (10.3 - 4.2)
            fz = -0.62 + t_ratio * 0.55
            fbm = bmesh.new()
            bmesh.ops.create_cone(fbm, cap_ends=True, cap_tris=False, segments=12, radius1=0.16, radius2=0.03, depth=2.1)
            bmesh.ops.rotate(fbm, verts=fbm.verts, matrix=Matrix.Rotation(math.radians(90), 3, 'Y'))
            bmesh.ops.translate(fbm, verts=fbm.verts, vec=(fx + 0.35, side * sp, fz - 0.12))
            f_obj = create_mesh_object(f"B727_FlapFairing_{side_name}_{idx}", fbm, collection, mat_body, 28.0)
            f_obj.parent = parent_obj
            add_inverted_hull_outline(f_obj, mat_white, thickness=0.018)

        # بناء الجنيحات الممتدة بزاوية 15 درجة (Extended 15-Degree Flaps)
        for f_idx, (y_in, y_out, x_in, x_out) in enumerate([(2.2, 6.8, 4.3, 5.7), (7.1, 12.2, 5.8, 7.9)]):
            fl_bm = bmesh.new()
            v1 = fl_bm.verts.new((x_in, side * y_in, -0.58))
            v2 = fl_bm.verts.new((x_out, side * y_out, -0.32))
            v3 = fl_bm.verts.new((x_out + 1.15, side * y_out, -0.64))
            v4 = fl_bm.verts.new((x_in + 1.35, side * y_in, -0.92))
            fl_bm.faces.new((v1, v2, v3, v4) if side == 1 else (v4, v3, v2, v1))
            bmesh.ops.solidify(fl_bm, geom=fl_bm.faces[:], thickness=0.08)
            flap_obj = create_mesh_object(f"B727_Flap_{side_name}_{f_idx}", fl_bm, collection, mat_body, 20.0)
            flap_obj.parent = parent_obj
            add_inverted_hull_outline(flap_obj, mat_white, thickness=0.016)

def build_ttail_and_engines(collection, parent_obj, mat_body, mat_white):
    """بناء الذيل T-Tail، قناة المحرك الأوسط S-Duct، والمحركين الجانبيين JT8D مع شفرات المروحة."""
    # 1. الزعنفة الرأسية (Swept Vertical Fin)
    bm_fin = bmesh.new()
    fin_base = [(10.2, -0.22, 1.75), (10.2, 0.22, 1.75), (17.6, 0.14, 0.90), (17.6, -0.14, 0.90)]
    fin_top  = [(15.2, -0.12, 6.85), (15.2, 0.12, 6.85), (19.4, 0.08, 6.85), (19.4, -0.08, 6.85)]
    vb = [bm_fin.verts.new(p) for p in fin_base]
    vt = [bm_fin.verts.new(p) for p in fin_top]
    for i in range(4):
        inext = (i + 1) % 4
        bm_fin.faces.new((vb[i], vb[inext], vt[inext], vt[i]))
    bm_fin.faces.new(vt)
    fin_obj = create_mesh_object("B727_VerticalFin", bm_fin, collection, mat_body, 25.0)
    fin_obj.parent = parent_obj
    add_inverted_hull_outline(fin_obj, mat_white, thickness=0.024)

    # 2. الجناح الأفقي العلوي للذيل (T-Tail Horizontal Stabilizer)
    for side in [-1, 1]:
        sname = "L" if side == 1 else "R"
        bm_hs = bmesh.new()
        r_in = [(15.0, 0.0, 6.75), (19.3, 0.0, 6.75), (19.3, 0.0, 6.95), (15.0, 0.0, 6.95)]
        r_out = [(17.6, side * 5.4, 6.65), (20.2, side * 5.4, 6.65), (20.2, side * 5.4, 6.78), (17.6, side * 5.4, 6.78)]
        vi = [bm_hs.verts.new(p) for p in r_in]
        vo = [bm_hs.verts.new(p) for p in r_out]
        for i in range(4):
            inext = (i + 1) % 4
            bm_hs.faces.new((vi[i], vi[inext], vo[inext], vo[i]) if side == 1 else (vi[inext], vi[i], vo[i], vo[inext]))
        bm_hs.faces.new(vo if side == 1 else list(reversed(vo)))
        hs_obj = create_mesh_object(f"B727_HStab_{sname}", bm_hs, collection, mat_body, 25.0)
        hs_obj.parent = parent_obj
        add_inverted_hull_outline(hs_obj, mat_white, thickness=0.020)

    # 3. مدخل المحرك الأوسط العلوي (Center Engine #2 S-Duct Intake)
    bm_sduct = bmesh.new()
    s_stations = [
        (8.8,  0.62, 0.62, 2.38),
        (10.5, 0.68, 0.65, 2.28),
        (13.5, 0.62, 0.58, 1.85),
        (16.8, 0.48, 0.48, 1.15),
    ]
    s_rings = []
    for sx, sry, srz, sz in s_stations:
        ring = []
        for i in range(20):
            th = 2.0 * math.pi * i / 20
            ring.append(bm_sduct.verts.new((sx, sry * math.cos(th), sz + srz * math.sin(th))))
        s_rings.append(ring)
    for r in range(len(s_rings) - 1):
        for i in range(20):
            inext = (i + 1) % 20
            bm_sduct.faces.new((s_rings[r][i], s_rings[r][inext], s_rings[r+1][inext], s_rings[r+1][i]))
    sduct_obj = create_mesh_object("B727_SDuct_CenterEngine", bm_sduct, collection, mat_body, 28.0)
    sduct_obj.parent = parent_obj
    add_inverted_hull_outline(sduct_obj, mat_white, thickness=0.022)

    # 4. المحركان الجانبيان الخلفيان (Side-Mounted Pratt & Whitney JT8D Nacelles #1 & #3)
    for side in [-1, 1]:
        sname = "L" if side == 1 else "R"
        bm_eng = bmesh.new()
        eng_stations = [
            (7.2, 0.62), (7.5, 0.74), (9.8, 0.76), (12.4, 0.66), (13.6, 0.52)
        ]
        ey = side * 2.55
        ez = 0.72
        e_rings = []
        for ex, er in eng_stations:
            ring = [bm_eng.verts.new((ex, ey + er * math.cos(2*math.pi*i/24), ez + er * math.sin(2*math.pi*i/24))) for i in range(24)]
            e_rings.append(ring)
        for r in range(len(e_rings) - 1):
            for i in range(24):
                inext = (i + 1) % 24
                bm_eng.faces.new((e_rings[r][i], e_rings[r][inext], e_rings[r+1][inext], e_rings[r+1][i]))
        # إضافة حلقة المدخل الأمامي ومخروط المروحة ليظهر بوضوح في اللقطة الخامسة المرجعية
        bmesh.ops.contextual_create(bm_eng, geom=e_rings[0])
        bmesh.ops.contextual_create(bm_eng, geom=e_rings[-1])
        eng_obj = create_mesh_object(f"B727_Engine_{sname}", bm_eng, collection, mat_body, 26.0)
        eng_obj.parent = parent_obj
        add_inverted_hull_outline(eng_obj, mat_white, thickness=0.022)

        # حلقة بيضاء داخلية لمدخل المحرك ومخروط المروحة
        bm_fan = bmesh.new()
        bmesh.ops.create_circle(bm_fan, cap_ends=True, radius=0.56, segments=20)
        bmesh.ops.rotate(bm_fan, verts=bm_fan.verts, matrix=Matrix.Rotation(math.radians(90), 3, 'Y'))
        bmesh.ops.translate(bm_fan, verts=bm_fan.verts, vec=(7.18, ey, ez))
        fan_obj = create_mesh_object(f"B727_EngineIntakeRing_{sname}", bm_fan, collection, mat_white, 20.0)
        fan_obj.parent = parent_obj

def build_landing_gear(collection, parent_obj, mat_body, mat_white):
    """بناء عجلات الهبوط الأمامية المزدوجة وعجلات الهبوط الرئيسية أسفل الجناحين."""
    def make_wheel_pair(name_prefix, x, y_center, z_axle, wheel_radius, wheel_width, strut_height):
        bm = bmesh.new()
        # الدعامة الرأسية (Strut)
        bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.11, radius2=0.09, depth=strut_height)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(x, y_center, z_axle + strut_height * 0.5))
        # العجلتان المزدوجتان
        for w_side in [-1, 1]:
            wbm = bmesh.new()
            bmesh.ops.create_cone(wbm, cap_ends=True, segments=20, radius1=wheel_radius, radius2=wheel_radius, depth=wheel_width)
            bmesh.ops.rotate(wbm, verts=wbm.verts, matrix=Matrix.Rotation(math.radians(90), 3, 'X'))
            bmesh.ops.translate(wbm, verts=wbm.verts, vec=(x, y_center + w_side * (wheel_width + 0.14), z_axle))
            w_obj = create_mesh_object(f"{name_prefix}_Wheel_{w_side}", wbm, collection, mat_body, 24.0)
            w_obj.parent = parent_obj
            add_inverted_hull_outline(w_obj, mat_white, thickness=0.020)

        strut_obj = create_mesh_object(f"{name_prefix}_Strut", bm, collection, mat_white, 24.0)
        strut_obj.parent = parent_obj

    # عجلة الأنف الأمامية (Nose Gear) — تظهر في اللقطتين الرابعة والخامسة
    make_wheel_pair("B727_NoseGear", -15.4, 0.0, -2.55, 0.42, 0.18, 1.35)
    # عجلتا الهبوط الرئيسيتان (Main Landing Gear)
    make_wheel_pair("B727_MainGear_L", 2.2, 3.05, -2.65, 0.62, 0.26, 2.15)
    make_wheel_pair("B727_MainGear_R", 2.2, -3.05, -2.65, 0.62, 0.26, 2.15)

def build_aft_stairway(collection, parent_obj, mat_body, mat_white):
    """بناء السلم الخلفي السفلي (Ventral Aft Airstair) كمجسم مفصلي مستقل قابل للتحريك والاهتزاز."""
    stair_pivot = bpy.data.objects.new("B727_AftStair_Pivot", None)
    collection.objects.link(stair_pivot)
    stair_pivot.parent = parent_obj
    # نقطة مفصل السلم تحت مؤخرة البدن
    stair_pivot.location = (9.8, 0.0, -0.88)
    # زاوية فتح السلم أثناء الطيران (نحو 34 درجة للأسفل)
    stair_pivot.rotation_euler = (0.0, math.radians(-34.0), 0.0)

    bm = bmesh.new()
    stair_len = 3.9
    stair_width = 0.92

    # العوارض الجانبية للسلم (Side Stringers)
    for side in [-1, 1]:
        y = side * (stair_width * 0.5)
        v1 = bm.verts.new((0.0, y - 0.05, 0.0))
        v2 = bm.verts.new((0.0, y + 0.05, 0.0))
        v3 = bm.verts.new((stair_len, y + 0.05, 0.0))
        v4 = bm.verts.new((stair_len, y - 0.05, 0.0))
        f = bm.faces.new((v1, v2, v3, v4))
        bmesh.ops.extrude_face_region(bm, geom=[f])
        for v in bm.verts[-4:]:
            v.co.z -= 0.24

    # الدرجات الثماني للسلم (8 Steps)
    num_steps = 8
    for s in range(num_steps):
        sx = 0.35 + (s / num_steps) * (stair_len - 0.45)
        sbm = bmesh.new()
        bmesh.ops.create_cube(sbm, size=1.0)
        bmesh.ops.scale(sbm, verts=sbm.verts, vec=(0.32, stair_width - 0.08, 0.06))
        bmesh.ops.translate(sbm, verts=sbm.verts, vec=(sx, 0.0, -0.10))
        step_obj = create_mesh_object(f"B727_AftStair_Step_{s}", sbm, collection, mat_body, 20.0)
        step_obj.parent = stair_pivot
        add_inverted_hull_outline(step_obj, mat_white, thickness=0.015)

    # القضبان اليدوية والمكابس الهيدروليكية (Handrails & Hydraulic Actuators)
    for side in [-1, 1]:
        y = side * (stair_width * 0.48)
        rbm = bmesh.new()
        # القائمان والعارضة العلوية للقضيب اليدوي
        posts = [
            ((0.3, y, 0.0), (0.3, y, 0.85)),
            ((stair_len - 0.25, y, 0.0), (stair_len - 0.25, y, 0.85)),
            ((0.0, y, 0.85), (stair_len - 0.15, y, 0.85)),
            ((1.4, y, 0.0), (0.9, y, 1.35)),  # ذراع المكبس الهيدروليكي
        ]
        for p_start, p_end in posts:
            vec = Vector(p_end) - Vector(p_start)
            mid = (Vector(p_start) + Vector(p_end)) * 0.5
            pbm = bmesh.new()
            bmesh.ops.create_cone(pbm, cap_ends=True, segments=8, radius1=0.032, radius2=0.032, depth=vec.length)
            rot_quat = Vector((0, 0, 1)).rotation_difference(vec.normalized())
            bmesh.ops.rotate(pbm, verts=pbm.verts, matrix=rot_quat.to_matrix())
            bmesh.ops.translate(pbm, verts=pbm.verts, vec=mid)
            rail_obj = create_mesh_object(f"B727_AftStair_Rail_{side}_{mid.x:.1f}", pbm, collection, mat_white, 20.0)
            rail_obj.parent = stair_pivot

    stair_frame = create_mesh_object("B727_AftStair_Frame", bm, collection, mat_body, 22.0)
    stair_frame.parent = stair_pivot
    add_inverted_hull_outline(stair_frame, mat_white, thickness=0.018)
    return stair_pivot

def build_boeing_727(collection, mats):
    """التجميع الكامل لطائرة Boeing 727-100 مع إرجاع جذر الطائرة ومفصل السلم الخلفي."""
    aircraft_root = bpy.data.objects.new("Boeing_727_Root", None)
    collection.objects.link(aircraft_root)

    fuselage = build_lofted_fuselage(collection, mats["aircraft_body"], mats["white_line"])
    fuselage.parent = aircraft_root

    build_swept_wings_and_flaps(collection, aircraft_root, mats["aircraft_body"], mats["white_line"])
    build_ttail_and_engines(collection, aircraft_root, mats["aircraft_body"], mats["white_line"])
    build_landing_gear(collection, aircraft_root, mats["aircraft_body"], mats["white_line"])
    stair_pivot = build_aft_stairway(collection, aircraft_root, mats["aircraft_body"], mats["white_line"])

    return aircraft_root, stair_pivot