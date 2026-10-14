import math
import random
import bpy
from mathutils import Vector, Quaternion

def smoothstep(edge0, edge1, x):
    """دالة تنعيم C1/C2 تمنع أي قفزات مفاجئة في سرعة الكاميرا أو الشخصية."""
    if x <= edge0:
        return 0.0
    if x >= edge1:
        return 1.0
    t = (x - edge0) / (edge1 - edge0)
    return t * t * (3.0 - 2.0 * t)

def smootherstep(edge0, edge1, x):
    if x <= edge0:
        return 0.0
    if x >= edge1:
        return 1.0
    t = (x - edge0) / (edge1 - edge0)
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)

def lerp_vec(v1, v2, t):
    return Vector(v1) * (1.0 - t) + Vector(v2) * t

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
    """
    موقع الطائرة في كل إطار:
    - من الإطار 1 إلى 230 (00:00 – 00:09.6): تحلق بثبات أثناء دوران الكاميرا حولها.
    - من الإطار 231 إلى 340 (00:09.6 – 00:14.1): تبتعد للأمام واليسار بعد قفز Cooper.
    - من الإطار 345 إلى 405 (00:14.4 – 00:16.8): تعبر في الخلفية العلوية خلف Cooper (مطابقة لثانية 00:15–00:16 في مقطع LEMMiNO!).
    """
    if frame <= 230:
        t = (frame - 1) / 24.0
        return Vector((-t * 0.25, 0.0, math.sin(t * 1.4) * 0.10))
    elif frame <= 340:
        dt = (frame - 230) / 24.0
        return Vector((-2.4 - (dt ** 1.35) * 9.5, 0.0, dt * 1.6))
    elif frame <= 415:
        # عبور الطائرة في الخلفية العلوية أثناء نظر الكاميرا للأعلى خلف Cooper (الإطارات 350–400)
        u = (frame - 345) / 60.0
        cp = get_cooper_pos(frame)
        return cp + Vector((-24.0 + u * 52.0, 14.0 - u * 6.0, 28.0))
    else:
        return Vector((0.0, 0.0, 500.0))

def get_cooper_pos(frame):
    """موقع شخصية D.B. Cooper في كل إطار بدقة عالية."""
    if frame <= 228:
        ac = get_aircraft_pos(frame)
        # يقف في أسفل السلم الخلفي تمامًا كما في اللقطة الرابعة المرجعية (00:07–00:09)
        return Vector((ac.x + 13.05, 0.0, ac.z - 2.95))
    else:
        ac_jump = get_aircraft_pos(228)
        start_x = ac_jump.x + 13.05
        start_z = ac_jump.z - 2.95
        jt = (frame - 228) / 24.0
        decay = math.exp(-jt * 0.40)
        cx = start_x * decay + math.sin(jt * 0.9) * 0.18 * decay
        cy = math.sin(jt * 0.7) * 0.15 * decay
        # يسقط من Z = -2.95 إلى قمم الأشجار البيضاء (Z = -218.5) عند الإطار 660 (00:27.5 تمامًا مثل LEMMiNO!)
        progress = min(1.0, (frame - 228) / (660.0 - 228.0))
        cz = start_z - (progress ** 1.25) * abs(-218.5 - start_z)
        return Vector((cx, cy, cz))

def animate_scene(scene, aircraft_root, stair_pivot, cooper_root, pivots, bokeh_root, birds):
    """تحريك الطائرة، السلم الخلفي، شخصية Cooper، أضواء المدينة، وسرب الطيور."""
    # 1. تحريك الطائرة
    for f in range(1, 425, 2):
        pos = get_aircraft_pos(f)
        t = (f - 1) / 24.0
        if f <= 340:
            # ميلان مدروس للطائرة عند الإطار 160–230 ليرتفع الجناح الأيسر ويكشف السلم الخلفي والمحرك تمامًا مثل 00:08
            bank_blend = smoothstep(110, 185, f)
            roll = -3.0 * (1.0 - bank_blend) + 14.5 * bank_blend + math.sin(t * 1.2) * 0.8
            pitch = 2.0 - 7.5 * bank_blend
            yaw = 0.0
            s_ac = (1.0, 1.0, 1.0)
        else:
            # زاوية عبور الطائرة في الخلفية العلوية عند 00:15–00:16
            roll = 18.0
            pitch = -6.0
            yaw = -28.0
            s_ac = (0.65, 0.65, 0.65)
        keyframe_transform(aircraft_root, f, loc=pos, rot_deg=(roll, pitch, yaw), scale=s_ac)
    keyframe_transform(aircraft_root, 430, loc=(0, 0, 500), scale=(0.001, 0.001, 0.001))

    # اهتزاز السلم الخلفي لحظة القفز عند الإطار 228 (00:09.5)
    keyframe_transform(stair_pivot, 1,   rot_deg=(0.0, 33.0, 0.0))
    keyframe_transform(stair_pivot, 226, rot_deg=(0.0, 34.5, 0.0))
    keyframe_transform(stair_pivot, 242, rot_deg=(0.0, 18.0, 0.0))
    keyframe_transform(stair_pivot, 260, rot_deg=(0.0, 30.0, 0.0))
    keyframe_transform(stair_pivot, 285, rot_deg=(0.0, 26.0, 0.0))

    # 2. تحريك شخصية D.B. Cooper ومفاصله بنعومة كاملة
    for f in range(1, 865, 2):
        c_pos = get_cooper_pos(f)
        if f <= 228:
            # وضعية التأهب على السلم الخلفي (00:07–00:09)
            c_rot = (0.0, 18.0, 180.0)
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, 24, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, 18, 0))
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(0, -45, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(0, -35, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, 52, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, 42, 0))
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-18, -32, 0))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(18, -32, 0))
            keyframe_transform(pivots["Elbow_L"], f, rot_deg=(0, -25, 0))
            keyframe_transform(pivots["Elbow_R"], f, rot_deg=(0, -25, 0))
        elif f <= 268:
            # لحظة الوثب والاندفاع من السلم الخلفي في الهواء (00:09.5–00:11)
            u = smootherstep(228, 268, f)
            c_rot = (0.0, 18.0 + u * 68.0, 180.0 - u * 180.0)
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, 24 * (1 - u) - 8 * u, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, 18 * (1 - u) - 15 * u, 0))
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-18 - 45 * u, -32 - 55 * u, 0))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(18 + 45 * u, -32 - 45 * u, 0))
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(-22 * u, -45 * (1 - u) + 12 * u, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(22 * u, -35 * (1 - u) - 10 * u, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, 52 * (1 - u) - 35 * u, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, 42 * (1 - u) - 22 * u, 0))
        else:
            # وضعية السقوط الحر الديناميكية (X-Arch Skydiving Pose — 00:11.5 إلى 00:27.5)
            # الذراعان والساقان مفرودتان في الفضاء ثلاثي الأبعاد مع تموج هوائي طبيعي،
            # بينما دوران الكاميرا حوله يظهره من الجانب (00:12, 00:18) ومن الأسفل/الأعلى (00:13, 00:15, 00:19)!
            jt = (f - 268) / 24.0
            yaw_spin = math.sin(jt * 0.65) * 35.0
            pitch_arch = 84.0 + math.cos(jt * 1.1) * 8.0
            roll_bank = math.sin(jt * 0.85) * 14.0
            c_rot = (roll_bank, pitch_arch, yaw_spin)

            w1 = math.sin(jt * 2.8)
            w2 = math.cos(jt * 2.4)
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, -8 + w1 * 4, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, -16 + w2 * 4, 0))
            # فرد الذراعين للجانبين والأمام (X-Pose)
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-68 + w1 * 10, -72 + w2 * 12, 15))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(68 + w2 * 10, -58 - w1 * 12, -15))
            keyframe_transform(pivots["Elbow_L"], f, rot_deg=(0, -28 + w1 * 10, 0))
            keyframe_transform(pivots["Elbow_R"], f, rot_deg=(0, -24 + w2 * 10, 0))
            # فرد الساقين للجانبين مع انحناء ركبة طبيعي غير متماثل كما في اللقطتين 2 و 3
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(-24 + w1 * 5, -14 + w2 * 10, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(24 - w2 * 5, 10 - w1 * 10, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, -48 + w1 * 12, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, -32 + w2 * 12, 0))

        # يختفي Cooper داخل قمم الأشجار البيضاء عند الإطار 662 (00:27.5 تمامًا كما في فيديو LEMMiNO)
        if f <= 662:
            s_val = (1.0, 1.0, 1.0)
        else:
            s_val = (0.0001, 0.0001, 0.0001)
        keyframe_transform(cooper_root, f, loc=c_pos, rot_deg=c_rot, scale=s_val)

    # 3. تحريك عنقود أضواء المدينة الضبابية ليظهر بوضوح في 00:17.5–00:21.5 (الإطارات 415–525)
    keyframe_transform(bokeh_root, 1,   loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))
    keyframe_transform(bokeh_root, 412, loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))
    for f in range(414, 526, 2):
        cp = get_cooper_pos(f)
        u = (f - 414) / 112.0
        # يوضع أسفل Cooper بمسافة 14 وحدة بحيث تنظر الكاميرا من فوق Cooper إليه مباشرة
        keyframe_transform(
            bokeh_root, f,
            loc=(cp.x - 2.5 + u * 4.5, cp.y + 2.0 - u * 3.0, cp.z - 14.5),
            rot_deg=(0.0, 0.0, -18.0),
            scale=(1.0, 1.0, 1.0)
        )
    keyframe_transform(bokeh_root, 528, loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))
    keyframe_transform(bokeh_root, 864, loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))

    # 4. تحريك سرب الطيور البيضاء من قمم الأشجار البيضاء بعد سقوط Cooper (الإطار 700 إلى 864 = 00:29–00:36)
    rng = random.Random(1980)
    for idx, b_obj in enumerate(birds):
        start_x = rng.uniform(-8.5, 8.5)
        start_y = rng.uniform(-3.0, 5.0)
        start_z = -218.5 + rng.uniform(-1.0, 0.8)
        vx = rng.uniform(-7.5, 7.5)
        vy = rng.uniform(-2.5, 2.5)
        vz = rng.uniform(5.2, 9.8)

        keyframe_transform(b_obj, 1,   loc=(start_x, start_y, start_z), scale=(0.0001, 0.0001, 0.0001))
        keyframe_transform(b_obj, 698, loc=(start_x, start_y, start_z), scale=(0.0001, 0.0001, 0.0001))
        for bf in range(700, 865, 2):
            bt = (bf - 700) / 24.0
            bx = start_x + vx * bt + math.sin(bt * 4.5 + idx) * 0.6
            by = start_y + vy * bt
            bz = start_z + vz * bt
            flap = math.sin(bt * 24.0 + idx) * 35.0
            keyframe_transform(
                b_obj, bf,
                loc=(bx, by, bz),
                rot_deg=(flap, -12.0, math.degrees(math.atan2(vy, vx))),
                scale=(0.75, 0.75, 0.75)
            )

def setup_cinematic_cameras(scene, collection, aircraft_root, cooper_root, bokeh_root):
    """
    بناء الكاميرا السينمائية الواحدة المتصلة (Single Continuous One-Take Camera)
    التي تطابق حركة كاميرا LEMMiNO من الثانية 00:00 إلى 00:36 بدون أي قطع!
    """
    cam_data = bpy.data.cameras.new("LEMMiNO_Master_Camera")
    cam_data.lens = 42.0
    cam_data.clip_start = 0.1
    cam_data.clip_end = 1000.0
    cam_data.dof.use_dof = True
    cam_data.dof.focus_object = cooper_root
    cam_data.dof.aperture_fstop = 8.0

    cam_obj = bpy.data.objects.new("LEMMiNO_Master_Camera", cam_data)
    collection.objects.link(cam_obj)
    scene.camera = cam_obj
    scene.timeline_markers.clear()

    # حساب موقع الكاميرا والهدف في كل إطار (f = 1 .. 864) بانتقالات ناعمة متصلة 100%
    for f in range(1, 865):
        ac = get_aircraft_pos(f)
        cp = get_cooper_pos(f)

        # المواضع المدارية المتصلة حول الطائرة (الإطارات 1 إلى 228 = 00:00 إلى 00:09.5)
        if f <= 48:
            # 00:00 – 00:02: الاندفاع من بعيد عبر خطوط الرياح نحو مقدمة الطائرة (Front-Right Low Angle)
            u = smootherstep(1, 48, f)
            cam_ac = ac + lerp_vec((-115.0, 8.5, -6.5), (-32.0, 5.2, -2.4), u)
            tgt_ac = ac + lerp_vec((0.0, 0.0, 0.5), (-2.0, -0.4, 0.8), u)
            roll = -3.0 * u
            fstop = 8.0
        elif f <= 96:
            # 00:02 – 00:04: العبور من أمام الأنف (00:02 -> 00:03 في المنتصف) إلى الجانب الأمامي الأيسر (00:04)
            u = smootherstep(48, 96, f)
            angle = math.radians(170.0 + u * 52.0)  # يعبر 180° (المقدمة تمامًا عند الإطار 62 = 00:02.6) إلى 222°
            dist = 32.0 - u * 5.0
            cam_ac = ac + Vector((math.cos(angle) * dist, math.sin(angle) * dist, -2.4 + u * 1.2))
            tgt_ac = ac + lerp_vec((-2.0, -0.4, 0.8), (1.5, 0.0, 0.5), u)
            roll = -3.0 * (1.0 - u)
            fstop = 8.0
        elif f <= 168:
            # 00:04 – 00:07: الالتفاف الجانبي الأملس بموازاة البدن والجناح الأيسر
            u = smootherstep(96, 168, f)
            angle = math.radians(222.0 + u * 58.0)  # من 222° إلى 280° (خلف الجناح قليلًا)
            dist = 27.0 - u * 4.5
            cam_ac = ac + Vector((math.cos(angle) * dist + u * 6.5, math.sin(angle) * dist, -1.2 - u * 2.2))
            tgt_ac = ac + lerp_vec((1.5, 0.0, 0.5), (8.2, 0.0, -0.4), u)
            roll = 0.0
            fstop = 8.0
        else:
            # 00:07 – 00:09.5: زاوية السلم الخلفي الأيقونية (خلف وأسفل الجناح الأيسر بحيث يرتفع الجناح للأعلى)
            u = smootherstep(168, 228, min(228, f))
            cam_ac = ac + lerp_vec((10.4, -22.1, -3.4), (15.5, -18.5, -4.2), u)
            tgt_ac = ac + lerp_vec((8.2, 0.0, -0.4), (10.5, 0.0, -1.1), u)
            roll = 0.0
            fstop = 6.0

        # المواضع المدارية المتصلة حول Cooper أثناء السقوط الحر والغابة (الإطارات 228 إلى 864)
        if f <= 312:
            # 00:09.5 – 00:13: الانفصال السلس عن الطائرة والاقتراب من Cooper
            u = smootherstep(228, 312, max(228, f))
            cam_cp = cp + lerp_vec((2.5, -18.5, -1.2), (0.0, -8.8, 1.2), u)
            tgt_cp = cp + Vector((0.0, 0.0, 0.1))
            fstop_cp = 2.8
        elif f <= 412:
            # 00:13 – 00:17.2: الدوران تحت Cooper للنظر للأعلى (حيث تعبر الطائرة المموهة في الخلفية عند 00:15–00:16!)
            u = smootherstep(312, 412, f)
            # الكاميرا تنزل أسفل Cooper (Z = -7.2) ثم تلتف للجانب
            elev_angle = math.radians(10.0 - math.sin(u * math.pi) * 68.0)
            azim_angle = math.radians(-90.0 + u * 55.0)
            dist = 8.8
            cam_cp = cp + Vector((
                dist * math.cos(elev_angle) * math.cos(azim_angle),
                dist * math.cos(elev_angle) * math.sin(azim_angle),
                dist * math.sin(elev_angle)
            ))
            tgt_cp = cp + Vector((0.0, 0.0, 0.1))
            fstop_cp = 1.1  # عزل بؤري قوي لتمويه الطائرة العابرة في الخلفية العلوية
        elif f <= 525:
            # 00:17.2 – 00:21.8: الدوران فوق Cooper للنظر للأسفل نحو أضواء المدينة الضبابية (Bokeh — 00:18–00:20)
            u = smootherstep(412, 525, f)
            elev_angle = math.radians(10.0 + math.sin(u * math.pi) * 52.0)
            azim_angle = math.radians(-35.0 - u * 55.0)
            dist = 8.8 + u * 1.2
            cam_cp = cp + Vector((
                dist * math.cos(elev_angle) * math.cos(azim_angle),
                dist * math.cos(elev_angle) * math.sin(azim_angle),
                dist * math.sin(elev_angle)
            ))
            tgt_cp = cp + Vector((0.0, 0.0, 0.05))
            fstop_cp = 0.9  # تمويه Bokeh قوي لأضواء المدينة في الخلفية
        elif f <= 660:
            # 00:21.8 – 00:27.5: ابتعاد الكاميرا التدريجي للأعلى والخلف بينما ترتفع غابة الصنوبر من أسفل الشاشة!
            u = smootherstep(525, 660, f)
            cam_cp = lerp_vec(cp + Vector((0.0, -10.0, 1.8)), Vector((0.0, -56.0, -206.0)), u)
            # الهدف ينتقل بنعومة من Cooper إلى منتصف الغابة بحيث يدخل Cooper في قمم الأشجار البيضاء عند الإطار 660
            tgt_cp = lerp_vec(cp, Vector((0.0, 0.0, -214.5)), smootherstep(575, 660, f))
            fstop_cp = 1.2 + u * 6.8
        else:
            # 00:27.5 – 00:36.0: استقرار الكاميرا أمام الغابة المضاءة بينما تتطاير الطيور البيضاء للأعلى
            u = smootherstep(660, 864, f)
            cam_cp = lerp_vec(Vector((0.0, -56.0, -206.0)), Vector((0.0, -58.5, -207.2)), u)
            tgt_cp = lerp_vec(Vector((0.0, 0.0, -214.5)), Vector((0.0, 0.0, -215.5)), u)
            fstop_cp = 8.0

        # دمج سلس بين مرحلة الطائرة ومرحلة السقوط الحر حول لحظة القفز (الإطارات 220 إلى 260)
        if f < 220:
            final_cam = cam_ac
            final_tgt = tgt_ac
            final_fstop = fstop
        elif f <= 260:
            b = smootherstep(220, 260, f)
            final_cam = lerp_vec(cam_ac, cam_cp, b)
            final_tgt = lerp_vec(tgt_ac, tgt_cp, b)
            final_fstop = fstop * (1.0 - b) + fstop_cp * b
            roll = 0.0
        else:
            final_cam = cam_cp
            final_tgt = tgt_cp
            final_fstop = fstop_cp
            roll = 0.0

        aim_camera_at(cam_obj, f, final_cam, final_tgt, roll_deg=roll)
        cam_data.dof.aperture_fstop = final_fstop
        cam_data.keyframe_insert(data_path="dof.aperture_fstop", frame=f)

    return {"Master_Camera": cam_obj}
