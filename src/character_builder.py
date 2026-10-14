import math
import bpy
import bmesh
from mathutils import Vector, Matrix
from .compat import set_smooth_shading

def create_limb_segment(name, p1, p2, r1, r2, collection, material):
    bm = bmesh.new()
    vec = Vector(p2) - Vector(p1)
    mid = (Vector(p1) + Vector(p2)) * 0.5
    bmesh.ops.create_cone(bm, cap_ends=True, segments=14, radius1=r1, radius2=r2, depth=vec.length)
    rot = Vector((0, 0, 1)).rotation_difference(vec.normalized()).to_matrix()
    bmesh.ops.rotate(bm, verts=bm.verts, matrix=rot)
    bmesh.ops.translate(bm, verts=bm.verts, vec=mid)
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    obj.data.materials.append(material)
    set_smooth_shading(obj, 45.0)
    return obj

def build_db_cooper_rigged(collection, mats):
    """
    بناء شخصية D.B. Cooper مفصلية بالكامل (معطف Trench Coat، بدلة، حذاء Loafers،
    نظارة شمسية، وحقيبة مظلة عسكرية NB-6 على الظهر) مربوطة بهيكل مفاصل قابل للتحريك.
    """
    mat_red = mats["cooper_red"]
    cooper_root = bpy.data.objects.new("DB_Cooper_Root", None)
    collection.objects.link(cooper_root)

    # مفاصل التحريك (Articulated Pivots) لضمان استقرار كامل على كافة إصدارات Blender بدون أخطاء أوزان
    pivots = {}
    def make_pivot(name, parent, loc):
        p = bpy.data.objects.new(f"Cooper_Joint_{name}", None)
        collection.objects.link(p)
        p.parent = parent
        p.location = loc
        pivots[name] = p
        return p

    pelvis = make_pivot("Pelvis", cooper_root, (0.0, 0.0, 0.95))
    spine  = make_pivot("Spine", pelvis, (0.0, 0.0, 0.25))
    head_p = make_pivot("Head", spine, (0.0, 0.0, 0.42))

    # الجذع والمعطف العلوي (Torso & Trench Coat Lapels)
    torso = create_limb_segment("Cooper_Torso", (0, 0, -0.05), (0, 0, 0.40), 0.16, 0.21, collection, mat_red)
    torso.parent = spine
    torso.scale.y = 1.35

    hips = create_limb_segment("Cooper_Hips", (0, 0, -0.12), (0, 0, 0.26), 0.15, 0.17, collection, mat_red)
    hips.parent = pelvis
    hips.scale.y = 1.25

    # أذيال المعطف الطويل (Flapping Trench Coat Tails)
    coat_tail_p = make_pivot("CoatTail", pelvis, (0.08, 0.0, 0.02))
    coat_tail = create_limb_segment("Cooper_CoatTail", (0, 0, 0.0), (0.06, 0, -0.45), 0.18, 0.24, collection, mat_red)
    coat_tail.parent = coat_tail_p
    coat_tail.scale = (0.45, 1.45, 1.0)

    # الرأس والنظارة الشمسية (Head + 1970s Hair + Sunglasses Silhouette)
    bm_head = bmesh.new()
    bmesh.ops.create_uvsphere(bm_head, u_segments=16, v_segments=12, radius=0.115)
    bmesh.ops.scale(bm_head, verts=bm_head.verts, vec=(1.05, 0.92, 1.18))
    bmesh.ops.translate(bm_head, verts=bm_head.verts, vec=(0.0, 0.0, 0.12))
    mesh_head = bpy.data.meshes.new("Cooper_Head_Mesh")
    bm_head.to_mesh(mesh_head)
    bm_head.free()
    head_obj = bpy.data.objects.new("Cooper_Head", mesh_head)
    collection.objects.link(head_obj)
    head_obj.data.materials.append(mat_red)
    head_obj.parent = head_p
    set_smooth_shading(head_obj)

    # حقيبة المظلة العسكرية على الظهر (Military NB-6 Parachute Pack — واضحة جدًا في اللقطتين 2 و3)
    bm_pack = bmesh.new()
    bmesh.ops.create_cube(bm_pack, size=1.0)
    bmesh.ops.scale(bm_pack, verts=bm_pack.verts, vec=(0.22, 0.34, 0.46))
    bmesh.ops.bevel(bm_pack, geom=bm_pack.edges[:], offset=0.05, segments=3)
    bmesh.ops.translate(bm_pack, verts=bm_pack.verts, vec=(0.18, 0.0, 0.18))
    mesh_pack = bpy.data.meshes.new("Cooper_ParachutePack")
    bm_pack.to_mesh(mesh_pack)
    bm_pack.free()
    pack_obj = bpy.data.objects.new("Cooper_ParachutePack", mesh_pack)
    collection.objects.link(pack_obj)
    pack_obj.data.materials.append(mat_red)
    pack_obj.parent = spine
    set_smooth_shading(pack_obj)

    # الذراعان والمرفقان (Shoulders, Elbows, Hands)
    for side, sname in [(1, "L"), (-1, "R")]:
        sh = make_pivot(f"Shoulder_{sname}", spine, (0.0, side * 0.23, 0.34))
        u_arm = create_limb_segment(f"Cooper_UpperArm_{sname}", (0, 0, 0), (0, 0, -0.30), 0.068, 0.055, collection, mat_red)
        u_arm.parent = sh

        el = make_pivot(f"Elbow_{sname}", sh, (0.0, 0.0, -0.29))
        f_arm = create_limb_segment(f"Cooper_ForeArm_{sname}", (0, 0, 0), (0, 0, -0.28), 0.054, 0.042, collection, mat_red)
        f_arm.parent = el

        hand = create_limb_segment(f"Cooper_Hand_{sname}", (0, 0, -0.27), (0, 0, -0.37), 0.042, 0.025, collection, mat_red)
        hand.parent = el

    # الساقان والركبتان والحذاء (Thighs, Knees, Calves, Loafers)
    for side, sname in [(1, "L"), (-1, "R")]:
        hip_j = make_pivot(f"Hip_{sname}", pelvis, (0.0, side * 0.11, 0.0))
        thigh = create_limb_segment(f"Cooper_Thigh_{sname}", (0, 0, 0), (0, 0, -0.44), 0.092, 0.068, collection, mat_red)
        thigh.parent = hip_j

        knee_j = make_pivot(f"Knee_{sname}", hip_j, (0.0, 0.0, -0.43))
        calf = create_limb_segment(f"Cooper_Calf_{sname}", (0, 0, 0), (0, 0, -0.42), 0.066, 0.048, collection, mat_red)
        calf.parent = knee_j

        shoe = create_limb_segment(f"Cooper_Shoe_{sname}", (0.02, 0, -0.43), (-0.18, 0, -0.45), 0.052, 0.036, collection, mat_red)
        shoe.parent = knee_j

    return cooper_root, pivots