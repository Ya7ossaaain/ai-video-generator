import math
import bpy
import bmesh
from mathutils import Vector
from .compat import set_smooth_shading

def create_smooth_capsule(name, p1, p2, r1, r2, collection, material, scale_y=1.0):
    """إنشاء قطعة عضوية ناعمة مع كرات مفاصل عند الطرفين لضمان اتصال سلس بدون فجوات."""
    bm = bmesh.new()
    v1 = Vector(p1)
    v2 = Vector(p2)
    vec = v2 - v1
    mid = (v1 + v2) * 0.5

    bmesh.ops.create_cone(bm, cap_ends=True, segments=18, radius1=r1, radius2=r2, depth=vec.length)
    rot = Vector((0, 0, 1)).rotation_difference(vec.normalized()).to_matrix()
    bmesh.ops.rotate(bm, verts=bm.verts, matrix=rot)
    bmesh.ops.translate(bm, verts=bm.verts, vec=mid)

    # كرات المفاصل عند النهايتين
    for pt, rad in [(v1, r1 * 0.98), (v2, r2 * 0.98)]:
        sbm = bmesh.new()
        bmesh.ops.create_uvsphere(sbm, u_segments=14, v_segments=10, radius=rad)
        bmesh.ops.translate(sbm, verts=sbm.verts, vec=pt)
        m_tmp = bpy.data.meshes.new("tmp_joint")
        sbm.to_mesh(m_tmp)
        sbm.free()
        bm.from_mesh(m_tmp)
        bpy.data.meshes.remove(m_tmp)

    if abs(scale_y - 1.0) > 1e-3:
        bmesh.ops.scale(bm, verts=bm.verts, vec=(1.0, scale_y, 1.0))

    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    set_smooth_shading(obj, 60.0)
    return obj

def build_db_cooper_rigged(collection, mats):
    """
    بناء شخصية D.B. Cooper بنسب بشرية انسيابية مطابقة تمامًا للقطتين المرجعيتين 2 و 3:
    رأس متناسق، جذع بمعطف، حقيبة مظلة منحنية مندمجة في أعلى الظهر، وأطراف كاملة مع حذاء واضح.
    """
    mat_red = mats["cooper_red"]
    cooper_root = bpy.data.objects.new("DB_Cooper_Root", None)
    collection.objects.link(cooper_root)

    pivots = {}
    def make_pivot(name, parent, loc):
        p = bpy.data.objects.new(f"Cooper_Joint_{name}", None)
        collection.objects.link(p)
        p.parent = parent
        p.location = loc
        pivots[name] = p
        return p

    pelvis = make_pivot("Pelvis", cooper_root, (0.0, 0.0, 0.94))
    spine  = make_pivot("Spine", pelvis, (0.0, 0.0, 0.22))
    head_p = make_pivot("Head", spine, (0.0, 0.0, 0.40))

    # الجذع العلوي والسفلي
    torso = create_smooth_capsule("Cooper_Torso", (0, 0, -0.02), (0, 0, 0.36), 0.135, 0.165, collection, mat_red, scale_y=1.28)
    torso.parent = spine

    hips = create_smooth_capsule("Cooper_Hips", (0, 0, -0.06), (0, 0, 0.24), 0.130, 0.138, collection, mat_red, scale_y=1.22)
    hips.parent = pelvis

    # ذيل معطف خفيف ومدمج حول الورك (وليس مثلثًا منفصلًا ضخمًا)
    coat_tail_p = make_pivot("CoatTail", pelvis, (0.03, 0.0, -0.02))
    coat_tail = create_smooth_capsule("Cooper_CoatTail", (0, 0, 0.0), (0.04, 0, -0.24), 0.135, 0.155, collection, mat_red, scale_y=1.25)
    coat_tail.parent = coat_tail_p

    # الرأس والرقبة
    neck = create_smooth_capsule("Cooper_Neck", (0, 0, -0.04), (0, 0, 0.06), 0.065, 0.060, collection, mat_red)
    neck.parent = head_p

    bm_head = bmesh.new()
    bmesh.ops.create_uvsphere(bm_head, u_segments=18, v_segments=14, radius=0.108)
    bmesh.ops.scale(bm_head, verts=bm_head.verts, vec=(1.12, 0.94, 1.18))
    bmesh.ops.translate(bm_head, verts=bm_head.verts, vec=(-0.015, 0.0, 0.13))
    mesh_head = bpy.data.meshes.new("Cooper_Head_Mesh")
    bm_head.to_mesh(mesh_head)
    bm_head.free()
    head_obj = bpy.data.objects.new("Cooper_Head", mesh_head)
    collection.objects.link(head_obj)
    head_obj.data.materials.append(mat_red)
    head_obj.parent = head_p
    set_smooth_shading(head_obj, 60.0)

    # حقيبة المظلة المنحنية المندمجة في أعلى الظهر (Contoured Parachute Pack)
    bm_pack = bmesh.new()
    bmesh.ops.create_uvsphere(bm_pack, u_segments=16, v_segments=12, radius=0.16)
    bmesh.ops.scale(bm_pack, verts=bm_pack.verts, vec=(0.72, 1.05, 1.38))
    bmesh.ops.translate(bm_pack, verts=bm_pack.verts, vec=(0.13, 0.0, 0.20))
    mesh_pack = bpy.data.meshes.new("Cooper_ParachutePack")
    bm_pack.to_mesh(mesh_pack)
    bm_pack.free()
    pack_obj = bpy.data.objects.new("Cooper_ParachutePack", mesh_pack)
    collection.objects.link(pack_obj)
    pack_obj.data.materials.append(mat_red)
    pack_obj.parent = spine
    set_smooth_shading(pack_obj, 60.0)

    # الذراعان والمرفقان واليدان
    for side, sname in [(1, "L"), (-1, "R")]:
        sh = make_pivot(f"Shoulder_{sname}", spine, (0.0, side * 0.20, 0.33))
        u_arm = create_smooth_capsule(f"Cooper_UpperArm_{sname}", (0, 0, 0), (0, 0, -0.28), 0.058, 0.048, collection, mat_red)
        u_arm.parent = sh

        el = make_pivot(f"Elbow_{sname}", sh, (0.0, 0.0, -0.28))
        f_arm = create_smooth_capsule(f"Cooper_ForeArm_{sname}", (0, 0, 0), (0, 0, -0.25), 0.046, 0.036, collection, mat_red)
        f_arm.parent = el

        hand = create_smooth_capsule(f"Cooper_Hand_{sname}", (0, 0, -0.25), (-0.03, 0, -0.35), 0.036, 0.022, collection, mat_red)
        hand.parent = el

    # الساقان والركبتان والحذاء الكلاسيكي (Loafers)
    for side, sname in [(1, "L"), (-1, "R")]:
        hip_j = make_pivot(f"Hip_{sname}", pelvis, (0.0, side * 0.10, -0.02))
        thigh = create_smooth_capsule(f"Cooper_Thigh_{sname}", (0, 0, 0), (0, 0, -0.42), 0.082, 0.060, collection, mat_red)
        thigh.parent = hip_j

        knee_j = make_pivot(f"Knee_{sname}", hip_j, (0.0, 0.0, -0.42))
        calf = create_smooth_capsule(f"Cooper_Calf_{sname}", (0, 0, 0), (0, 0, -0.40), 0.058, 0.042, collection, mat_red)
        calf.parent = knee_j

        shoe = create_smooth_capsule(f"Cooper_Shoe_{sname}", (0.04, 0, -0.41), (-0.19, 0, -0.43), 0.046, 0.032, collection, mat_red)
        shoe.parent = knee_j

    return cooper_root, pivots