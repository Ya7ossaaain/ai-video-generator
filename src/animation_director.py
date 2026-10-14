import math
import random
import bpy
from mathutils import Vector

def keyframe_transform(obj, frame, loc=None, rot_deg=None, scale=None):
    if loc is not None:
        obj.location = loc
        obj.keyframe_insert(data_path="location", frame=frame)
    if rot_deg is not None:
        obj.rotation_euler = tuple(math.radians(a) for a in rot_deg)
        obj.keyframe_insert(data_path="rotation_euler", frame=frame)
    if scale is not None:
        obj.scale = scale
        obj.keyframe_insert(data_path="scale", frame=frame)

def animate_scene(scene, aircraft_root, stair_pivot, cooper_root, pivots, bokeh_root, birds):
    """
    تحريك كامل متسق مكانيًا وزمنيًا على مدار 864 إطارًا (36 ثانية):
    - مسار الطائرة واهتزاز السلم الخلفي لحظة القفز.
    - حركة مفاصل D.B. Cooper في التأهب، الوثب، التقلب الحر، والاستقرار الهوائي.
    - تطاير سرب الطيور لحظة دخول Cooper في الغابة.
    - نظام الكاميرات السينمائية السبع مع الربط الزمني عبر Timeline Markers.
    """
    # 1. حركة الطائرة (Boeing 727 Flight Path + Oscillation after jump)
    # الطائرة تحلق عند ارتفاع Z = 0 وتتحرك للأمام ببطء نسبي مع اهتزاز جوي طفيف
    for f in range(1, 620, 12):
        t = (f - 1) / 24.0
        # قبل القفزة (الإطار 350) تتحرك الطائرة بثبات، وبعد الإطار 360 تندفع للأمام وتبتعد
        if f <= 355:
            ax = -t * 0.4
            az = math.sin(t * 1.6) * 0.18
            roll = math.sin(t * 1.1) * 1.8
            pitch = 2.0 + math.cos(t * 0.9) * 0.6
        else:
            dt = (f - 355) / 24.0
            ax = -14.8 * 0.4 - (dt ** 1.45) * 8.5
            az = 0.8 + dt * 2.4 + math.sin(dt * 5.0) * 0.35 * math.exp(-dt * 0.4)
            roll = -4.0 + math.sin(dt * 3.0) * 2.0
            pitch = 3.5 + math.sin(dt * 6.0) * 2.2 * math.exp(-dt * 0.5)
        keyframe_transform(aircraft_root, f, loc=(ax, 0.0, az), rot_deg=(roll, pitch, 0.0))

    # اهتزاز السلم الخلفي لحظة القفز (Aft Stairway Oscillation عند الإطار 350–410)
    keyframe_transform(stair_pivot, 1,   rot_deg=(0.0, -34.0, 0.0))
    keyframe_transform(stair_pivot, 345, rot_deg=(0.0, -35.5, 0.0))
    keyframe_transform(stair_pivot, 362, rot_deg=(0.0, -18.0, 0.0))  # ارتداد السلم للأعلى بعد مغادرة وزن Cooper
    keyframe_transform(stair_pivot, 380, rot_deg=(0.0, -31.0, 0.0))
    keyframe_transform(stair_pivot, 405, rot_deg=(0.0, -26.0, 0.0))

    # 2. مسار وحركة شخصية D.B. Cooper
    # من الإطار 1 إلى 350: يقف Cooper في نهاية السلم الخلفي (عند X=+13.1 بالنسبة للطائرة، Z=-3.15)
    # ابتداءً من الإطار 351: يثب للخلف والأسفل في الهواء الحر حتى يصل إلى قمم أشجار الغابة (Z=-218) عند الإطار 805
    for f in range(1, 865, 4):
        if f <= 350:
            t = (f - 1) / 24.0
            ax = -t * 0.4
            az = math.sin(t * 1.6) * 0.18
            # موقع نهاية السلم الخلفي بدقة بدون أي تداخل مع البدن أو الجناح
            cx = ax + 12.85
            cy = 0.0
            cz = az - 3.12
            c_rot = (0.0, 18.0, 0.0)

            # وضعية الانحناء والتأهب على السلم (مطابقة للقطة الرابعة المرجعية)
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, 28, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, 22, 0))
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(0, -48, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(0, -38, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, 55, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, 45, 0))
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-25, -35, 0))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(25, -35, 0))
        else:
            # مرحلة القفز والسقوط الحر (الإطارات 351 إلى 864)
            jt = (f - 350) / 24.0  # الزمن بالثواني منذ لحظة القفز (0 إلى 21.4 ثانية)
            # ينحرف للخلف في البداية ثم يسقط عموديًا باتجاه مركز الغابة المضاءة (0, 0, -220)
            decay = math.exp(-jt * 0.35)
            cx = 7.1 * decay + math.sin(jt * 1.3) * 0.4
            cy = math.sin(jt * 0.9) * 0.5 * decay
            # تسارع السقوط من Z = -3.12 إلى Z = -224 عند الإطار 805 (jt = 18.9s)
            progress = min(1.0, jt / 18.9)
            cz = -3.12 - (progress ** 1.35) * 221.0

            if f < 600:
                # مرحلة التخبط والدوران في الرياح (اللقطة الثالثة المرجعية)
                c_rot = (
                    math.sin(jt * 2.8) * 35.0,
                    72.0 + math.cos(jt * 2.2) * 28.0,
                    jt * 42.0
                )
                keyframe_transform(pivots["Pelvis"], f, rot_deg=(math.sin(jt*4)*12, 10, 0))
                keyframe_transform(pivots["Spine"], f, rot_deg=(0, -15 + math.cos(jt*5)*10, 0))
                keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-65 + math.sin(jt*6)*25, -40, 20))
                keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(65 + math.cos(jt*6)*25, 30, -20))
                keyframe_transform(pivots["Elbow_L"], f, rot_deg=(0, -35 + math.sin(jt*7)*20, 0))
                keyframe_transform(pivots["Elbow_R"], f, rot_deg=(0, -25 + math.cos(jt*7)*20, 0))
                keyframe_transform(pivots["Hip_L"], f, rot_deg=(-18, -25 + math.sin(jt*5)*30, 0))
                keyframe_transform(pivots["Hip_R"], f, rot_deg=(18, 20 + math.cos(jt*5)*30, 0))
                keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, 48 + math.sin(jt*6)*22, 0))
                keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, 35 + math.cos(jt*6)*22, 0))
            else:
                # مرحلة الاستقرار الأفقي Belly-to-Earth فوق أضواء المدينة والغابة (اللقطة الثانية والأولى)
                c_rot = (
                    math.sin(jt * 3.5) * 6.0,
                    82.0 + math.cos(jt * 3.0) * 5.0,
                    180.0 + math.sin(jt * 1.5) * 8.0
                )
                keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, 8, 0))
                keyframe_transform(pivots["Spine"], f, rot_deg=(0, -18, 0))
                keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-45, -70 + math.sin(jt*9)*8, 0))
                keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(45, -65 + math.cos(jt*9)*8, 0))
                keyframe_transform(pivots["Elbow_L"], f, rot_deg=(0, -45, 0))
                keyframe_transform(pivots["Elbow_R"], f, rot_deg=(0, -40, 0))
                keyframe_transform(pivots["Hip_L"], f, rot_deg=(-12, 18 + math.sin(jt*8)*6, 0))
                keyframe_transform(pivots["Hip_R"], f, rot_deg=(12, 28 + math.cos(jt*8)*6, 0))
                keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, 62 + math.sin(jt*10)*8, 0))
                keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, 52 + math.cos(jt*10)*8, 0))

            # رفرفة ذيل المعطف في الهواء
            keyframe_transform(pivots["CoatTail"], f, rot_deg=(math.sin(jt*14)*12, -35 + math.cos(jt*16)*18, 0))

        # إخفاء Cooper داخل الأشجار بعد الإطار 808 (كما في الفيديو الأصلي عند 00:34)
        s_val = (1.0, 1.0, 1.0) if f <= 808 else (0.001, 0.001, 0.001)
        keyframe_transform(cooper_root, f, loc=(cx, cy, cz), rot_deg=c_rot, scale=s_val)

    # 3. تحريك سرب الطيور البيضاء لحظة ارتطام Cooper بقمم الأشجار (الإطار 802 إلى 864)
    rng = random.Random(1980)
    for idx, b_obj in enumerate(birds):
        start_x = rng.uniform(-12.0, 12.0)
        start_y = rng.uniform(-6.0, 6.0)
        start_z = -215.0 + rng.uniform(-2.0, 1.5)
        vx = rng.uniform(-18.0, 18.0)
        vy = rng.uniform(-8.0, 8.0)
        vz = rng.uniform(14.0, 26.0)

        keyframe_transform(b_obj, 1,   loc=(start_x, start_y, start_z), scale=(0.001, 0.001, 0.001))
        keyframe_transform(b_obj, 800, loc=(start_x, start_y, start_z), scale=(0.001, 0.001, 0.001))
        for bf in range(802, 865, 4):
            bt = (bf - 802) / 24.0
            bx = start_x + vx * bt + math.sin(bt * 6.0 + idx) * 1.2
            by = start_y + vy * bt
            bz = start_z + vz * bt
            flap = math.sin(bt * 22.0 + idx) * 35.0
            keyframe_transform(
                b_obj, bf,
                loc=(bx, by, bz),
                rot_deg=(flap, -15.0, math.degrees(math.atan2(vy, vx))),
                scale=(1.1, 1.1, 1.1)
            )

def setup_cinematic_cameras(scene, collection, aircraft_root, cooper_root, bokeh_root):
    """إنشاء الكاميرات السينمائية السبع وربطها بالـ Timeline Markers."""
    cam_specs = [
        # (name, start_frame, lens_mm, use_dof, fstop, target_obj)
        ("Cam_01_FrontApproach",   1,   38.0, False, 4.0, aircraft_root),
        ("Cam_02_OrbitalSide",     121, 42.0, False, 4.0, aircraft_root),
        ("Cam_03_AftStairProfile", 241, 48.0, False, 4.0, aircraft_root),
        ("Cam_04_TheJumpExit",     349, 35.0, False, 2.8, cooper_root),
        ("Cam_05_FreefallTumble",  469, 35.0, True,  1.6, cooper_root),
        ("Cam_06_NightBokeh",      601, 50.0, True,  1.2, cooper_root),
        ("Cam_07_ForestFinale",    721, 75.0, False, 4.0, None),
    ]

    cameras = {}
    scene.timeline_markers.clear()

    for name, f_start, lens, use_dof, fstop, dof_target in cam_specs:
        cam_data = bpy.data.cameras.new(name)
        cam_data.lens = lens
        cam_data.clip_start = 0.1
        cam_data.clip_end = 1000.0
        if use_dof and dof_target:
            cam_data.dof.use_dof = True
            cam_data.dof.focus_object = dof_target
            cam_data.dof.aperture_fstop = fstop

        cam_obj = bpy.data.objects.new(name, cam_data)
        collection.objects.link(cam_obj)
        cameras[name] = cam_obj

        marker = scene.timeline_markers.new(name=name, frame=f_start)
        marker.camera = cam_obj

    scene.camera = cameras["Cam_01_FrontApproach"]

    # تحريك الكاميرا 1: الاقتراب الأمامي السفلي (تطابق اللقطة الخامسة المرجعية عند الإطار 90–120)
    c1 = cameras["Cam_01_FrontApproach"]
    c1.parent = aircraft_root
    keyframe_transform(c1, 1,   loc=(-95.0, 22.0, -14.0), rot_deg=(82.0, 0.0, -76.0))
    keyframe_transform(c1, 85,  loc=(-33.0, 9.5,  -4.8),  rot_deg=(83.0, 0.0, -74.0))
    keyframe_transform(c1, 120, loc=(-29.0, 12.5, -4.2),  rot_deg=(83.5, 0.0, -66.5))

    # تحريك الكاميرا 2: الالتفاف الجانبي حول الجناح والمحركات
    c2 = cameras["Cam_02_OrbitalSide"]
    c2.parent = aircraft_root
    keyframe_transform(c2, 121, loc=(-24.0, 18.0, -3.8), rot_deg=(84.0, 0.0, -52.0))
    keyframe_transform(c2, 240, loc=(4.5,   26.5, -2.5), rot_deg=(85.5, 0.0, -12.0))

    # تحريك الكاميرا 3: كشف السلم الخلفي وشخصية Cooper الحمراء (تطابق اللقطة الرابعة المرجعية)
    c3 = cameras["Cam_03_AftStairProfile"]
    c3.parent = aircraft_root
    keyframe_transform(c3, 241, loc=(8.5,  23.0, -2.2), rot_deg=(86.0, 0.0, -4.0))
    keyframe_transform(c3, 348, loc=(11.2, 19.5, -1.8), rot_deg=(86.0, 0.0, 2.0))

    # تحريك الكاميرا 4: لحظة الوثب والانفصال عن ذيل الطائرة
    c4 = cameras["Cam_04_TheJumpExit"]
    for f in range(349, 470, 4):
        scene.frame_set(f)
        c_pos = cooper_root.matrix_world.translation
        keyframe_transform(c4, f, loc=(c_pos.x + 2.5, c_pos.y + 16.0, c_pos.z + 1.5), rot_deg=(85.0, 0.0, 180.0))

    # تحريك الكاميرا 5: التتبع المركزي أثناء التخبط مع عبور الطائرة خلفه (تطابق اللقطة الثالثة المرجعية)
    c5 = cameras["Cam_05_FreefallTumble"]
    for f in range(469, 602, 4):
        scene.frame_set(f)
        c_pos = cooper_root.matrix_world.translation
        # الكاميرا تنظر من الأسفل/الجانب نحو Cooper بحيث تعبر الطائرة في أعلى الكادر
        keyframe_transform(c5, f, loc=(c_pos.x, c_pos.y + 11.5, c_pos.z - 2.2), rot_deg=(98.0, 0.0, 180.0))

    # تحريك الكاميرا 6: السقوط الحر فوق أضواء المدينة الضبابية Bokeh (تطابق اللقطة الثانية المرجعية)
    c6 = cameras["Cam_06_NightBokeh"]
    for f in range(601, 722, 4):
        scene.frame_set(f)
        c_pos = cooper_root.matrix_world.translation
        # الكاميرا فوق Cooper تنظر للأسفل باتجاه Cooper وعنقود أضواء المدينة في الربع السفلي الأيسر
        keyframe_transform(c6, f, loc=(c_pos.x + 1.2, c_pos.y - 8.2, c_pos.z + 3.8), rot_deg=(65.0, 0.0, 8.0))
        # تحريك عنقود أضواء المدينة لينزلق في الخلفية السفلية اليسرى
        prog = (f - 601) / 120.0
        keyframe_transform(
            bokeh_root, f,
            loc=(c_pos.x - 14.0 + prog * 8.0, c_pos.y + 38.0, c_pos.z - 22.0),
            rot_deg=(-25.0, 0.0, 0.0)
        )

    # تحريك الكاميرا 7: الابتعاد للكشف عن غابة الصنوبر المضاءة وتطاير الطيور (تطابق اللقطة الأولى المرجعية)
    c7 = cameras["Cam_07_ForestFinale"]
    keyframe_transform(c7, 721, loc=(0.0, -72.0, -182.0), rot_deg=(86.5, 0.0, 0.0))
    keyframe_transform(c7, 790, loc=(0.0, -92.0, -206.0), rot_deg=(88.5, 0.0, 0.0))
    keyframe_transform(c7, 864, loc=(0.0, -96.0, -208.5), rot_deg=(89.0, 0.0, 0.0))

    return cameras