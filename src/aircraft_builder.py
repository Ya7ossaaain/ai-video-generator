import math
import bpy
import bmesh
from mathutils import Vector, Matrix
from .compat import set_smooth_shading

def create_mesh_object(name, bm, collection, material=None, mark_sharp_angle=28.0, mark_all_edges=False):
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    angle_rad = math.radians(mark_sharp_angle)
    sharp_edge_indices = []
    for idx, edge in enumerate(bm.edges):
        if mark_all_edges:
            edge.smooth = False
            sharp_edge_indices.append(idx)
        elif len(edge.link_faces) == 2:
            a = edge.link_faces[0].normal.angle(edge.link_faces[1].normal, 0.0)
            if a >= angle_rad:
                edge.smooth = False
                sharp_edge_indices.append(idx)
        elif len(edge.link_faces) == 1:
            edge.smooth = False
            sharp_edge_indices.append(idx)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    if material:
        obj.data.materials.append(material)
    set_smooth_shading(obj, mark_sharp_angle)
    for idx in sharp_edge_indices:
        if idx < len(obj.data.edges):
            e = obj.data.edges[idx]
            if hasattr(e, "use_edge_sharp"):
                e.use_edge_sharp = True
            if hasattr(e, "use_freestyle_mark"):
                e.use_freestyle_mark = True
    return obj

def close_ring_cap(bm, ring_verts, flip=False):
    try:
        verts = list(reversed(ring_verts)) if flip else list(ring_verts)
        bm.faces.new(verts)
    except Exception:
        pass

def add_white_strip(name, points, radius, collection, parent_obj, mat_white, closed=False):
    bm = bmesh.new()
    n = len(points)
    segs = n if closed else (n - 1)
    for i in range(segs):
        p1 = Vector(points[i])
        p2 = Vector(points[(i + 1) % n])
        vec = p2 - p1
        if vec.length < 1e-4:
            continue
        mid = (p1 + p2) * 0.5
        sbm = bmesh.new()
        bmesh.ops.create_cone(sbm, cap_ends=True, segments=8, radius1=radius, radius2=radius, depth=vec.length)
        rot = Vector((0, 0, 1)).rotation_difference(vec.normalized()).to_matrix()
        bmesh.ops.rotate(sbm, verts=sbm.verts, matrix=rot)
        bmesh.ops.translate(sbm, verts=sbm.verts, vec=mid)
        m_tmp = bpy.data.meshes.new("tmp_seg")
        sbm.to_mesh(m_tmp)
        sbm.free()
        bm.from_mesh(m_tmp)
        bpy.data.meshes.remove(m_tmp)
    obj = create_mesh_object(name, bm, collection, mat_white, 45.0)
    obj.parent = parent_obj
    return obj

def build_lofted_fuselage(collection, parent_obj, mat_body, mat_white):
    """بناء بدن طائرة Boeing 727-100 بأنف انسيابي ملحوم في نقطة واحدة لمنع ظهور أي دائرة بيضاء على الأنف."""
    bm = bmesh.new()
    nose_tip = bm.verts.new((-19.75, 0.0, -0.36))

    stations = [
        (-19.3, 0.42, 0.38, -0.34),
        (-18.4, 0.92, 0.84, -0.26),
        (-17.1, 1.35, 1.20, -0.12),
        (-15.5, 1.72, 1.75, 0.02),
        (-12.8, 1.90, 2.04, 0.08),
        (-8.0,  1.92, 2.06, 0.08),
        (-2.0,  1.92, 2.06, 0.08),
        (4.0,   1.92, 2.06, 0.08),
        (7.8,   1.86, 1.98, 0.12),
        (10.5,  1.62, 1.76, 0.24),
        (13.8,  1.18, 1.38, 0.54),
        (16.6,  0.65, 0.82, 0.80),
        (18.3,  0.34, 0.38, 0.94),
    ]

    ring_Factor = 36
    rings = []
    for x, ry, rz, z_off in stations:
        ring_verts = []
        for i in range(ring_Factor):
            theta = (2.0 * math.pi * i) / ring_Factor
            y = ry * math.cos(theta)
            z_raw = math.sin(theta)
            if 9.2 <= x <= 14.2 and z_raw < -0.58:
                z_raw = -0.58
            z = rz * z_raw + z_off
            ring_verts.append(bm.verts.new((x, y, z)))
        rings.append(ring_verts)

    # لحام رأس الأنف بسلاسة تامة
    first_ring = rings[0]
    for i in range(ring_Factor):
        i_next = (i + 1) % ring_Factor
        bm.faces.new((nose_tip, first_ring[i_next], first_ring[i]))

    for r_idx in range(len(rings) - 1):
        r1 = rings[r_idx]
        r2 = rings[r_idx + 1]
        for i in range(ring_Factor):
            i_next = (i + 1) % ring_Factor
            bm.faces.new((r1[i], r1[i_next], r2[i_next], r2[i]))

    close_ring_cap(bm, rings[-1], flip=False)

    fuselage = create_mesh_object("B727_Fuselage", bm, collection, mat_body, 32.0)
    fuselage.parent = parent_obj

    # هوائي السقف الصغير الظاهر في لقطات LEMMiNO
    ant_pts = [(-4.5, 0.0, 2.12), (-4.2, 0.0, 2.42), (-3.9, 0.0, 2.12)]
    add_white_strip("B727_TopAntenna", ant_pts, 0.022, collection, parent_obj, mat_white)
    return fuselage

def build_swept_wings_and_flaps(collection, parent_obj, mat_body, mat_white):
    """بناء الجناحين المرتدين ومسارات الجنيحات الأربعة بدون أي خطوط سفلية مشوهة."""
    for side in [-1, 1]:
        side_name = "L" if side == -1 else "R"
        bm = bmesh.new()
        wing_sections = [
            (-3.2, 4.3, side * 1.72, -0.52, 0.50),
            (0.4,  5.7, side * 6.60, -0.32, 0.36),
            (4.9,  8.2, side * 13.0, -0.08, 0.22),
            (8.8, 10.5, side * 17.5,  0.18, 0.10),
        ]
        sec_rings = []
        pts_profile = [
            (0.0, 0.0), (0.15, 0.48), (0.50, 0.40), (1.0, 0.02),
            (1.0, -0.02), (0.50, -0.24), (0.15, -0.26)
        ]
        for xl, xt, y, z, th in wing_sections:
            chord = xt - xl
            ring = [bm.verts.new((xl + px * chord, y, z + pz * th)) for px, pz in pts_profile]
            sec_rings.append(ring)

        n_pts = len(pts_profile)
        for s in range(len(sec_rings) - 1):
            r1, r2 = sec_rings[s], sec_rings[s + 1]
            for i in range(n_pts):
                inext = (i + 1) % n_pts
                if side == 1:
                    bm.faces.new((r1[i], r1[inext], r2[inext], r2[i]))
                else:
                    bm.faces.new((r1[inext], r1[i], r2[i], r2[inext]))
        close_ring_cap(bm, sec_rings[-1], flip=(side != 1))

        wing_obj = create_mesh_object(f"B727_Wing_{side_name}", bm, collection, mat_body, 26.0)
        wing_obj.parent = parent_obj

        # 4 هياكل انسيابية لمسارات الجنيحات (Flap Track Fairings) على الحافة الخلفية للجناح
        fairing_spans = [3.4, 5.9, 8.6, 11.4]
        for idx, sp in enumerate(fairing_spans):
            t_ratio = (sp - 1.72) / (17.5 - 1.72)
            fx_trail = 4.3 + t_ratio * (10.5 - 4.3)
            fz = -0.55 + t_ratio * 0.65
            fbm = bmesh.new()
            bmesh.ops.create_cone(fbm, cap_ends=True, cap_tris=False, segments=12, radius1=0.16, radius2=0.02, depth=2.2)
            bmesh.ops.rotate(fbm, verts=fbm.verts, matrix=Matrix.Rotation(math.radians(90), 3, 'Y'))
            bmesh.ops.translate(fbm, verts=fbm.verts, vec=(fx_trail + 0.35, side * sp, fz - 0.12))
            f_obj = create_mesh_object(f"B727_FlapFairing_{side_name}_{idx}", fbm, collection, mat_body, 26.0)
            f_obj.parent = parent_obj

def build_ttail_and_engines(collection, parent_obj, mat_body, mat_white):
    """بناء الذيل T-Tail، قناة S-Duct، والمحركين الجانبيين الخلفيين."""
    bm_fin = bmesh.new()
    fin_base = [(10.0, -0.20, 1.72), (10.0, 0.20, 1.72), (17.5, 0.14, 0.92), (17.5, -0.14, 0.92)]
    fin_top  = [(15.2, -0.12, 6.85), (15.2, 0.12, 6.85), (19.5, 0.08, 6.85), (19.5, -0.08, 6.85)]
    vb = [bm_fin.verts.new(p) for p in fin_base]
    vt = [bm_fin.verts.new(p) for p in fin_top]
    for i in range(4):
        inext = (i + 1) % 4
        bm_fin.faces.new((vb[i], vb[inext], vt[inext], vt[i]))
    bm_fin.faces.new(vt)
    fin_obj = create_mesh_object("B727_VerticalFin", bm_fin, collection, mat_body, 24.0)
    fin_obj.parent = parent_obj

    for side in [-1, 1]:
        sname = "L" if side == -1 else "R"
        bm_hs = bmesh.new()
        r_in = [(14.9, 0.0, 6.72), (19.4, 0.0, 6.72), (19.4, 0.0, 6.94), (14.9, 0.0, 6.94)]
        r_out = [(17.6, side * 5.5, 6.62), (20.3, side * 5.5, 6.62), (20.3, side * 5.5, 6.76), (17.6, side * 5.5, 6.76)]
        vi = [bm_hs.verts.new(p) for p in r_in]
        vo = [bm_hs.verts.new(p) for p in r_out]
        for i in range(4):
            inext = (i + 1) % 4
            bm_hs.faces.new((vi[i], vi[inext], vo[inext], vo[i]) if side == 1 else (vi[inext], vi[i], vo[i], vo[inext]))
        bm_hs.faces.new(vo if side == 1 else list(reversed(vo)))
        hs_obj = create_mesh_object(f"B727_HStab_{sname}", bm_hs, collection, mat_body, 24.0)
        hs_obj.parent = parent_obj

    # مدخل المحرك الأوسط العلوي (S-Duct)
    bm_sduct = bmesh.new()
    s_stations = [
        (8.6,  0.64, 0.64, 2.40),
        (10.5, 0.70, 0.66, 2.30),
        (13.6, 0.64, 0.60, 1.85),
        (17.0, 0.48, 0.48, 1.15),
    ]
    s_rings = []
    for sx, sry, srz, sz in s_stations:
        ring = [bm_sduct.verts.new((sx, sry * math.cos(2*math.pi*i/24), sz + srz * math.sin(2*math.pi*i/24))) for i in range(24)]
        s_rings.append(ring)
    for r in range(len(s_rings) - 1):
        for i in range(24):
            inext = (i + 1) % 24
            bm_sduct.faces.new((s_rings[r][i], s_rings[r][inext], s_rings[r+1][inext], s_rings[r+1][i]))
    close_ring_cap(bm_sduct, s_rings[0], flip=True)
    sduct_obj = create_mesh_object("B727_SDuct_CenterEngine", bm_sduct, collection, mat_body, 26.0)
    sduct_obj.parent = parent_obj

    # المحركان الجانبيان الخلفيان (#1 و #3)
    for side in [-1, 1]:
        sname = "L" if side == -1 else "R"
        bm_eng = bmesh.new()
        eng_stations = [(7.1, 0.64), (7.5, 0.78), (9.9, 0.80), (12.5, 0.68), (13.7, 0.54)]
        ey = side * 2.58
        ez = 0.74
        e_rings = []
        for ex, er in eng_stations:
            ring = [bm_eng.verts.new((ex, ey + er * math.cos(2*math.pi*i/24), ez + er * math.sin(2*math.pi*i/24))) for i in range(24)]
            e_rings.append(ring)
        for r in range(len(e_rings) - 1):
            for i in range(24):
                inext = (i + 1) % 24
                bm_eng.faces.new((e_rings[r][i], e_rings[r][inext], e_rings[r+1][inext], e_rings[r+1][i]))
        close_ring_cap(bm_eng, e_rings[0], flip=True)
        close_ring_cap(bm_eng, e_rings[-1], flip=False)
        eng_obj = create_mesh_object(f"B727_Engine_{sname}", bm_eng, collection, mat_body, 26.0)
        eng_obj.parent = parent_obj

        lip_pts = [(7.08, ey + 0.64 * math.cos(2*math.pi*i/20), ez + 0.64 * math.sin(2*math.pi*i/20)) for i in range(20)]
        inner_pts = [(7.12, ey + 0.36 * math.cos(2*math.pi*i/16), ez + 0.36 * math.sin(2*math.pi*i/16)) for i in range(16)]
        add_white_strip(f"B727_EngineLip_{sname}", lip_pts, 0.036, collection, parent_obj, mat_white, closed=True)
        add_white_strip(f"B727_EngineSpinner_{sname}", inner_pts, 0.026, collection, parent_obj, mat_white, closed=True)

def build_landing_gear(collection, parent_obj, mat_body, mat_white):
    def make_wheel_pair(name_prefix, x, y_center, z_axle, wheel_radius, wheel_width, strut_height):
        add_white_strip(
            f"{name_prefix}_Strut",
            [(x, y_center, z_axle), (x, y_center, z_axle + strut_height)],
            0.048, collection, parent_obj, mat_white
        )
        for w_side in [-1, 1]:
            wy = y_center + w_side * (wheel_width + 0.14)
            wbm = bmesh.new()
            bmesh.ops.create_cone(wbm, cap_ends=True, segments=20, radius1=wheel_radius, radius2=wheel_radius, depth=wheel_width)
            bmesh.ops.rotate(wbm, verts=wbm.verts, matrix=Matrix.Rotation(math.radians(90), 3, 'X'))
            bmesh.ops.translate(wbm, verts=wbm.verts, vec=(x, wy, z_axle))
            w_obj = create_mesh_object(f"{name_prefix}_Wheel_{w_side}", wbm, collection, mat_body, 24.0)
            w_obj.parent = parent_obj

            rim_pts = [(x + wheel_radius * math.cos(2*math.pi*i/18), wy + w_side*wheel_width*0.5, z_axle + wheel_radius * math.sin(2*math.pi*i/18)) for i in range(18)]
            hub_pts = [(x + wheel_radius*0.42 * math.cos(2*math.pi*i/14), wy + w_side*wheel_width*0.52, z_axle + wheel_radius*0.42 * math.sin(2*math.pi*i/14)) for i in range(14)]
            add_white_strip(f"{name_prefix}_Rim_{w_side}", rim_pts, 0.024, collection, parent_obj, mat_white, closed=True)
            add_white_strip(f"{name_prefix}_Hub_{w_side}", hub_pts, 0.020, collection, parent_obj, mat_white, closed=True)

    make_wheel_pair("B727_NoseGear", -15.4, 0.0, -2.55, 0.44, 0.18, 1.40)
    make_wheel_pair("B727_MainGear_L", 2.1, -3.05, -2.65, 0.65, 0.26, 2.15)
    make_wheel_pair("B727_MainGear_R", 2.1,  3.05, -2.65, 0.65, 0.26, 2.15)

def build_aft_stairway(collection, parent_obj, mat_body, mat_white):
    stair_pivot = bpy.data.objects.new("B727_AftStair_Pivot", None)
    collection.objects.link(stair_pivot)
    stair_pivot.parent = parent_obj
    stair_pivot.location = (9.8, 0.0, -0.88)
    stair_pivot.rotation_euler = (0.0, math.radians(33.0), 0.0)

    stair_len = 4.1
    stair_width = 0.94

    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, verts=bm.verts, vec=(stair_len, stair_width, 0.12))
    bmesh.ops.translate(bm, verts=bm.verts, vec=(stair_len * 0.5, 0.0, -0.10))
    stair_frame = create_mesh_object("B727_AftStair_Base", bm, collection, mat_body, 22.0)
    stair_frame.parent = stair_pivot

    num_steps = 8
    for s in range(num_steps):
        sx = 0.35 + (s / num_steps) * (stair_len - 0.45)
        sbm = bmesh.new()
        bmesh.ops.create_cube(sbm, size=1.0)
        bmesh.ops.scale(sbm, verts=sbm.verts, vec=(0.28, stair_width - 0.08, 0.05))
        bmesh.ops.translate(sbm, verts=sbm.verts, vec=(sx, 0.0, -0.02))
        step_obj = create_mesh_object(f"B727_AftStair_Step_{s}", sbm, collection, mat_body, 22.0, mark_all_edges=True)
        step_obj.parent = stair_pivot

    for side in [-1, 1]:
        y = side * (stair_width * 0.48)
        rail_loop = [
            (0.0, y, 0.0),
            (stair_len, y, 0.0),
            (stair_len - 0.25, y, 0.78),
            (0.25, y, 0.78),
            (0.25, y, 0.0)
        ]
        add_white_strip(f"B727_AftStair_Rail_{side}", rail_loop, 0.028, collection, stair_pivot, mat_white)
        add_white_strip(f"B727_AftStair_Strut_{side}", [(1.6, y, 0.0), (0.9, y, 1.35)], 0.026, collection, stair_pivot, mat_white)

    return stair_pivot

def build_boeing_727(collection, mats):
    aircraft_root = bpy.data.objects.new("Boeing_727_Root", None)
    collection.objects.link(aircraft_root)

    build_lofted_fuselage(collection, aircraft_root, mats["aircraft_body"], mats["white_line"])
    build_swept_wings_and_flaps(collection, aircraft_root, mats["aircraft_body"], mats["white_line"])
    build_ttail_and_engines(collection, aircraft_root, mats["aircraft_body"], mats["white_line"])
    build_landing_gear(collection, aircraft_root, mats["aircraft_body"], mats["white_line"])
    stair_pivot = build_aft_stairway(collection, aircraft_root, mats["aircraft_body"], mats["white_line"])

    return aircraft_root, stair_pivot
