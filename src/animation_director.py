import math
import random
import bpy
from mathutils import Vector, Quaternion

def keyframe_transform(obj, frame, loc=None, rot_deg=None, scale=None):
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if rot_deg is not None:
        obj.rotation_mode = 'XYZ'
        obj.rotation_euler = tuple(math.radians(a) for a in rot_deg)
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)

def aim_camera_at(cam_obj, frame, cam_loc, target_loc, roll_deg=0.0):
    """توجيه الكاميرا رياضيًا بدقة 100% نحو الهدف باستخدام الكواترنيون دون أخطاء زوايا أويلر."""
    cam_vec = Vector(cam_loc)
    tgt_vec = Vector(target_loc)
    direction = (tgt_vec - cam_vec).normalized()
    rot_quat = direction.to_track_quat('-Z', 'Y')
    if abs(roll_deg) > 1e-4:
        roll_quat = Quaternion(direction, math.radians(roll_deg))
        rot_quat = roll_quat @ rot_quat
    cam_obj.location = cam_vec
    cam_obj.rotation_mode = 'QUATERNION'
    cam_obj.rotation_quaternion = rot_quat
    cam_obj.keyframe_insert(data_path="location", frame=frame)
    cam_obj.keyframe_insert(data_path="rotation_quaternion", frame=frame)

def get_aircraft_pos(frame):
    """حساب موقع الطائرة الحتمي في كل إطار."""
    t = (frame - 1) / 24.0
    if frame <= 352:
        ax = -t * 0.35
        az = math.sin(t * 1.4) * 0.14
    else:
        dt = (frame - 352) / 24.0
        ax = -14.6 * 0.35 - (dt ** 1.35) * 7.5
        az = 0.6 + dt * 1.8
    return Vector((ax, 0.0, az))

def get_cooper_pos(frame):
    """حساب موقع شخصية D.B. Cooper الحتمي في كل إطار."""
    if frame <= 352:
        ac = get_aircraft_pos(frame)
        # Cooper يقف في أسفل السلم الخلفي تمامًا كما في اللقطة الرابعة المرجعية
        return Vector((ac.x + 13.05, 0.0, ac.z - 2.95))
    else:
        ac_jump = get_aircraft_pos(352)
        start_x = ac_jump.x + 13.05
        start_z = ac_jump.z - 2.95
        jt = (frame - 352) / 24.0
        decay = math.exp(-jt * 0.32)
        cx = start_x * decay + math.sin(jt * 1.1) * 0.25 * decay
        cy = math.sin(jt * 0.8) * 0.20 * decay
        # يصل إلى قمم الأشجار البيضاء (Z = -218.5) عند الإطار 795
        progress = min(1.0, jt / 18.45)
        cz = start_z - (progress ** 1.32) * (abs(-219.5 - start_z))
        return Vector((cx, cy, cz))

def animate_scene(scene, aircraft_root, stair_pivot, cooper_root, pivots, bokeh_root, birds):
    """تحريك الطائرة، السلم الخلفي، مفاصل Cooper، أضواء الـ Bokeh، وسرب الطيور."""
    # 1. تحريك الطائرة
    for f in range(1, 865, 6):
        pos = get_aircraft_pos(f)
        t = (f - 1) / 24.0
        roll = math.sin(t * 1.1) * 1.4
        pitch = 1.8 + math.cos(t * 0.9) * 0.5
        if f > 352:
            dt = (f - 352) / 24.0
            pitch += math.sin(dt * 5.5) * 1.8 * math.exp(-dt * 0.45)
        keyframe_transform(aircraft_root, f, loc=pos, rot_deg=(roll, pitch, 0.0))

    # اهتزاز السلم الخلفي عند القفز (Oscillation)
    keyframe_transform(stair_pivot, 1,   rot_deg=(0.0, 33.0, 0.0))
    keyframe_transform(stair_pivot, 348, rot_deg=(0.0, 34.5, 0.0))
    keyframe_transform(stair_pivot, 365, rot_deg=(0.0, 19.0, 0.0))
    keyframe_transform(stair_pivot, 385, rot_deg=(0.0, 31.0, 0.0))
    keyframe_transform(stair_pivot, 410, rot_deg=(0.0, 27.0, 0.0))

    # 2. تحريك شخصية D.B. Cooper ومفاصله
    for f in range(1, 865, 4):
        c_pos = get_cooper_pos(f)
        if f <= 352:
            # وضعية الانحناء على السلم الخلفي (مطابقة للقطة الرابعة المرجعية)
            c_rot = (0.0, 16.0, 180.0)
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, 22, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, 18, 0))
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(0, -45, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(0, -35, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, 52, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, 42, 0))
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-18, -32, 0))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(18, -32, 0))
            keyframe_transform(pivots["Elbow_L"], f, rot_deg=(0, -25, 0))
            keyframe_transform(pivots["Elbow_R"], f, rot_deg=(0, -25, 0))
        elif f < 600:
            # مرحلة السقوط الحر والتقلب في الفراغ الأسود (مطابقة للقطة الثالثة المرجعية عند الإطار 530)
            jt = (f - 352) / 24.0
            # عند الإطار 530 يتجه الرأس لليمين والأسفل قليلًا مع امتداد الذراعين والساقين
            c_rot = (
                math.sin(jt * 1.8) * 14.0,
                -108.0 + math.cos(jt * 1.5) * 12.0,
                math.sin(jt * 0.9) * 18.0
            )
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, -8, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, -14, 0))
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-55, -85 + math.sin(jt*4)*15, 0))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(45, -30 + math.cos(jt*4)*15, 0))
            keyframe_transform(pivots["Elbow_L"], f, rot_deg=(0, -20, 0))
            keyframe_transform(pivots["Elbow_R"], f, rot_deg=(0, -35, 0))
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(-10, 15 + math.sin(jt*3)*15, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(10, -22 + math.cos(jt*3)*15, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, 58, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, 18, 0))
        else:
            # مرحلة الاستقرار الأفقي Belly-to-Earth والوجه لليسار (مطابقة للقطة الثانية المرجعية عند الإطار 660)
            jt = (f - 352) / 24.0
            c_rot = (
                math.sin(jt * 3.0) * 4.0,
                84.0 + math.cos(jt * 2.5) * 3.0,
                0.0
            )
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, -6, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, -16, 0))
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-35, -62 + math.sin(jt*7)*6, 0))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(35, -48 + math.cos(jt*7)*6, 0))
            keyframe_transform(pivots["Elbow_L"], f, rot_deg=(0, -38, 0))
            keyframe_transform(pivots["Elbow_R"], f, rot_deg=(0, -32, 0))
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(-8, -14 + math.sin(jt*6)*5, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(8, 12 + math.cos(jt*6)*5, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, -52, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, -45, 0))

        # تصغير حجم Cooper قليلًا في لقطة الغابة الواسعة ليطابق النقطة الحمراء الصغيرة في اللقطة الأولى، ثم إخفاؤه عند 796
        if f < 721:
            s_val = (1.0, 1.0, 1.0)
        elif f <= 795:
            s_val = (0.55, 0.55, 0.55)
        else:
            s_val = (0.0001, 0.0001, 0.0001)
        keyframe_transform(cooper_root, f, loc=c_pos, rot_deg=c_rot, scale=s_val)

    # 3. التحكم الصارم بظهور أضواء المدينة الضبابية (تظهر فقط في اللقطة السادسة 601–720 وتختفي تمامًا في الغابة!)
    keyframe_transform(bokeh_root, 1,   loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))
    keyframe_transform(bokeh_root, 600, loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))
    for f in range(601, 721, 4):
        c_pos = get_cooper_pos(f)
        prog = (f - 601) / 120.0
        keyframe_transform(
            bokeh_root, f,
            loc=(c_pos.x - 1.5 + prog * 2.5, c_pos.y + 18.0, c_pos.z - 2.2),
            rot_deg=(0.0, 0.0, 0.0),
            scale=(1.0, 1.0, 1.0)
        )
    keyframe_transform(bokeh_root, 721, loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))
    keyframe_transform(bokeh_root, 864, loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))

    # 4. تحريك سرب الطيور البيضاء لحظة ارتطام Cooper بقمم الأشجار البيضاء (الإطار 795 إلى 864)
    rng = random.Random(1980)
    for idx, b_obj in enumerate(birds):
        start_x = rng.uniform(-9.0, 9.0)
        start_y = rng.uniform(-5.0, 3.0)
        start_z = -218.5 + rng.uniform(-1.5, 1.0)
        vx = rng.uniform(-11.0, 11.0)
        vy = rng.uniform(-4.0, 4.0)
        vz = rng.uniform(9.5, 17.5)

        keyframe_transform(b_obj, 1,   loc=(start_x, start_y, start_z), scale=(0.0001, 0.0001, 0.0001))
        keyframe_transform(b_obj, 794, loc=(start_x, start_y, start_z), scale=(0.0001, 0.0001, 0.0001))
        for bf in range(796, 865, 3):
            bt = (bf - 796) / 24.0
            bx = start_x + vx * bt + math.sin(bt * 5.0 + idx) * 0.8
            by = start_y + vy * bt
            bz = start_z + vz * bt
            flap = math.sin(bt * 24.0 + idx) * 35.0
            keyframe_transform(
                b_obj, bf,
                loc=(bx, by, bz),
                rot_deg=(flap, -12.0, math.degrees(math.atan2(vy, vx))),
                scale=(0.85, 0.85, 0.85)
            )

def setup_cinematic_cameras(scene, collection, aircraft_root, cooper_root, bokeh_root):
    """إعداد الكاميرات السبع في الإحداثيات العالمية مع توجيه رياضي مباشر 100% نحو الأهداف."""
    cam_specs = [
        ("Cam_01_FrontApproach",   1,   42.0),
        ("Cam_02_OrbitalSide",     121, 42.0),
        ("Cam_03_AftStairProfile", 241, 45.0),
        ("Cam_04_TheJumpExit",     349, 38.0),
        ("Cam_05_FreefallTumble",  469, 45.0),
        ("Cam_06_NightBokeh",      601, 50.0),
        ("Cam_07_ForestFinale",    721, 62.0),
    ]

    cameras = {}
    scene.timeline_markers.clear()

    for name, f_start, lens in cam_specs:
        cam_data = bpy.data.cameras.new(name)
        cam_data.lens = lens
        cam_data.clip_start = 0.1
        cam_data.clip_end = 1000.0
        cam_obj = bpy.data.objects.new(name, cam_data)
        collection.objects.link(cam_obj)
        cameras[name] = cam_obj

        marker = scene.timeline_markers.new(name=name, frame=f_start)
        marker.camera = cam_obj

    scene.camera = cameras["Cam_01_FrontApproach"]

    # 1. الكاميرا 1 (الإطارات 1–120): الاقتراب الأمامي السفلي (تطابق اللقطة الخامسة المرجعية عند الإطار 85)
    c1 = cameras["Cam_01_FrontApproach"]
    for f in range(1, 122, 4):
        ac = get_aircraft_pos(f)
        u = (f - 1) / 119.0
        # تقترب من (-68, +7.5, -6.5) إلى (-34.5, +4.2, -3.5) وتنظر لمركز الطائرة
        cam_loc = ac + Vector((-68.0 + u * 35.5, 7.2 - u * 3.0, -6.2 + u * 2.8))
        tgt_loc = ac + Vector((0.0, -0.3, 1.1))
        aim_camera_at(c1, f, cam_loc, tgt_loc, roll_deg=-2.5)

    # 2. الكاميرا 2 (الإطارات 121–240): الالتفاف المداري حول جانب الطائرة الأيسر
    c2 = cameras["Cam_02_OrbitalSide"]
    for f in range(121, 242, 4):
        ac = get_aircraft_pos(f)
        u = (f - 121) / 119.0
        angle = math.radians(155.0 - u * 65.0)  # من المقدمة الجانبية إلى المنتصف الجانبي
        dist = 32.0 - u * 6.0
        cam_loc = ac + Vector((math.cos(angle) * dist + 2.0, -math.sin(angle) * dist, -2.5 + u * 1.2))
        tgt_loc = ac + Vector((3.0 + u * 4.0, 0.0, 0.4))
        aim_camera_at(c2, f, cam_loc, tgt_loc)

    # 3. الكاميرا 3 (الإطارات 241–348): لقطة السلم الخلفي وشخصية Cooper الحمراء (تطابق اللقطة الرابعة المرجعية عند الإطار 300)
    c3 = cameras["Cam_03_AftStairProfile"]
    for f in range(241, 350, 4):
        ac = get_aircraft_pos(f)
        u = (f - 241) / 107.0
        cam_loc = ac + Vector((6.5 + u * 2.0, -24.5 + u * 2.5, -0.4))
        tgt_loc = ac + Vector((7.8 + u * 1.0, 0.0, 0.25))
        aim_camera_at(c3, f, cam_loc, tgt_loc)

    # 4. الكاميرا 4 (الإطارات 349–468): لحظة القفز من السلم الخلفي والانفصال عن الطائرة
    c4 = cameras["Cam_04_TheJumpExit"]
    for f in range(349, 470, 3):
        cp = get_cooper_pos(f)
        ac = get_aircraft_pos(f)
        u = (f - 349) / 119.0
        # تبدأ مركزة بين السلم وCooper ثم تتبع سقوط Cooper بينما يخرج ذيل الطائرة من أعلى يسار الكادر
        cam_loc = cp + Vector((-1.5 + u * 1.5, -16.5 + u * 3.5, 1.8 - u * 1.2))
        tgt_loc = cp * (0.4 + 0.6 * u) + (ac + Vector((12.5, 0.0, -2.0))) * (0.6 - 0.6 * u)
        aim_camera_at(c4, f, cam_loc, tgt_loc)

    # 5. الكاميرا 5 (الإطارات 469–600): السقوط الحر والتقلب في الظلام (تطابق اللقطة الثالثة المرجعية عند الإطار 530)
    c5 = cameras["Cam_05_FreefallTumble"]
    for f in range(469, 602, 3):
        cp = get_cooper_pos(f)
        u = (f - 469) / 131.0
        cam_loc = cp + Vector((math.sin(u * 1.2) * 1.5, -14.8, math.cos(u * 1.2) * 1.2))
        tgt_loc = cp + Vector((0.0, 0.0, 0.15))
        aim_camera_at(c5, f, cam_loc, tgt_loc)

    # 6. الكاميرا 6 (الإطارات 601–720): السقوط الحر فوق أضواء المدينة الضبابية (تطابق اللقطة الثانية المرجعية عند الإطار 660)
    c6 = cameras["Cam_06_NightBokeh"]
    for f in range(601, 722, 3):
        cp = get_cooper_pos(f)
        u = (f - 601) / 119.0
        cam_loc = cp + Vector((0.4 - u * 0.8, -10.2, 0.8))
        tgt_loc = cp + Vector((0.0, 0.0, 0.05))
        aim_camera_at(c6, f, cam_loc, tgt_loc)

    # 7. الكاميرا 7 (الإطارات 721–864): غابة الصنوبر المضاءة وتطاير الطيور (تطابق اللقطة الأولى المرجعية عند الإطار 785)
    c7 = cameras["Cam_07_ForestFinale"]
    for f in range(721, 865, 3):
        u = min(1.0, (f - 721) / 55.0)
        # ترتفع الغابة من أسفل الكادر وتستقر في النصف السفلي بينما يسقط Cooper كنقطة حمراء صغيرة في قمم الأشجار البيضاء
        cam_loc = Vector((0.0, -64.0, -196.0 - u * 6.0))
        tgt_loc = Vector((0.0, 0.0, -206.0 - u * 10.5))
        aim_camera_at(c7, f, cam_loc, tgt_loc)

    return cameras