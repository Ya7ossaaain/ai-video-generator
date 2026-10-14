import math
import random
import bpy
from mathutils import Vector, Quaternion

def smoothstep(edge0, edge1, x):
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
    - الإطارات 1..228 (00:00 – 00:09.5): تحلق بثبات.
    - الإطارات 229..335 (00:09.5 – 00:14): تبتعد للأمام واليسار وتخرج من أعلى يسار الشاشة عند 00:11.
    - الإطارات 345..405 (00:14.4 – 00:16.8): تعبر عاليةً وبعيدةً في خلفية الكادر من أعلى اليسار (00:15) إلى أعلى اليمين (00:16).
    """
    if frame <= 228:
        t = (frame - 1) / 24.0
        return Vector((-t * 0.20, 0.0, math.sin(t * 1.3) * 0.08))
    elif frame <= 335:
        dt = (frame - 228) / 24.0
        return Vector((-1.9 - (dt ** 1.30) * 11.5, 0.0, dt * 2.2))
    elif frame <= 410:
        # عبور الطائرة على ارتفاع شاهق خلف Cooper (من أعلى يسار الشاشة في 00:15 إلى أعلى يمينها في 00:16)
        u = (frame - 345) / 55.0
        cp = get_cooper_pos(frame)
        return cp + Vector((-26.0 + u * 54.0, 52.0, 26.0 - u * 4.0))
    else:
        return Vector((0.0, 0.0, 600.0))

def get_cooper_pos(frame):
    """موقع شخصية D.B. Cooper في كل إطار."""
    if frame <= 228:
        ac = get_aircraft_pos(frame)
        # ينزل درجات السلم الخلفي تدريجيًا من الإطار 120 إلى 228 قبل القفز
        walk_u = smoothstep(130, 224, frame)
        sx = 11.2 + walk_u * 1.45
        sz = -1.75 - walk_u * 0.78
        return Vector((ac.x + sx, 0.0, ac.z + sz))
    else:
        ac_jump = get_aircraft_pos(228)
        start_x = ac_jump.x + 12.65
        start_z = ac_jump.z - 2.53
        jt = (frame - 228) / 24.0
        decay = math.exp(-jt * 0.45)
        cx = start_x * decay
        cy = 0.0
        # يصل إلى قمم الأشجار البيضاء (Z = -218.2) عند الإطار 658 (00:27.4 تمامًا مثل LEMMiNO)
        progress = min(1.0, (frame - 228) / (658.0 - 228.0))
        cz = start_z - (progress ** 1.22) * abs(-218.2 - start_z)
        return Vector((cx, cy, cz))

def animate_scene(scene, aircraft_root, stair_pivot, cooper_root, pivots, bokeh_root, birds):
    """تحريك الطائرة، السلم الخلفي، شخصية Cooper، أضواء المدينة، المطر، وسرب الطيور."""
    # 1. تحريك الطائرة
    for f in range(1, 420, 2):
        pos = get_aircraft_pos(f)
        t = (f - 1) / 24.0
        if f <= 335:
            bank_blend = smoothstep(135, 205, f)
            roll = -2.0 * (1.0 - bank_blend) + 15.0 * bank_blend + math.sin(t * 1.2) * 0.6
            pitch = 1.5 - 8.0 * bank_blend
            yaw = 0.0
            s_ac = (1.0, 1.0, 1.0)
        else:
            # زاوية عبور الطائرة الصغيرة في الخلفية العلوية عند 00:15–00:16
            roll = 22.0
            pitch = -12.0
            yaw = -155.0
            s_ac = (0.38, 0.38, 0.38)
        keyframe_transform(aircraft_root, f, loc=pos, rot_deg=(roll, pitch, yaw), scale=s_ac)
    keyframe_transform(aircraft_root, 425, loc=(0, 0, 600), scale=(0.001, 0.001, 0.001))

    # اهتزاز السلم الخلفي لحظة القفز عند الإطار 228 (00:09.5)
    keyframe_transform(stair_pivot, 1,   rot_deg=(0.0, 28.0, 0.0))
    keyframe_transform(stair_pivot, 226, rot_deg=(0.0, 29.5, 0.0))
    keyframe_transform(stair_pivot, 242, rot_deg=(0.0, 15.0, 0.0))
    keyframe_transform(stair_pivot, 262, rot_deg=(0.0, 26.0, 0.0))
    keyframe_transform(stair_pivot, 285, rot_deg=(0.0, 22.0, 0.0))

    # إخفاء خطوط الرياح الافتتاحية بعد الإطار 52، وتحريك المطر القطري في مشهد الغابة (600..864)
    wind_obj = bpy.data.objects.get("Intro_Wind_Streaks")
    if wind_obj:
        keyframe_transform(wind_obj, 1,  loc=(0, 0, 0), scale=(1.0, 1.0, 1.0))
        keyframe_transform(wind_obj, 48, loc=(35, 0, 0), scale=(1.0, 1.0, 1.0))
        keyframe_transform(wind_obj, 52, loc=(0, 0, 500), scale=(0.001, 0.001, 0.001))

    f_rain_obj = bpy.data.objects.get("Forest_Diagonal_Rain")
    if f_rain_obj:
        keyframe_transform(f_rain_obj, 1,   loc=(0, 0, 500), scale=(0.001, 0.001, 0.001))
        keyframe_transform(f_rain_obj, 650, loc=(0, 0, 500), scale=(0.001, 0.001, 0.001))
        for rf in range(654, 865, 4):
            rt = (rf - 654) / 24.0
            # حركة دورية للمطر القطري المتساقط
            cycle = (rt * 18.0) % 14.0
            keyframe_transform(f_rain_obj, rf, loc=(-cycle * 0.40, 0.0, -cycle), scale=(1.0, 1.0, 1.0))

    # 2. تحريك شخصية D.B. Cooper ومفاصله (تطابق وضعيات 00:08, 00:12, 00:13, 00:15, 00:18, 00:19, 00:21)
    for f in range(1, 865, 2):
        c_pos = get_cooper_pos(f)
        if f <= 228:
            # يقف داخل السلم الخلفي وينزل درجاته متأهبًا للقفز (00:06–00:09.5)
            walk_phase = math.sin(f * 0.25) * smoothstep(130, 215, f)
            c_rot = (0.0, 8.0, 180.0)
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, 14, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, 16, 0))
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(0, -32 + walk_phase * 18, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(0, -28 - walk_phase * 18, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, 38, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, 34, 0))
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-12, -25, 0))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(12, -25, 0))
            keyframe_transform(pivots["Elbow_L"], f, rot_deg=(0, -20, 0))
            keyframe_transform(pivots["Elbow_R"], f, rot_deg=(0, -20, 0))
            s_val = (0.72, 0.72, 0.72)  # حجم متناسق مع السلم الخلفي كما في 00:07–00:09
        elif f <= 264:
            # 00:09.5 – 00:11: القفز والاندفاع في الهواء بعيدًا عن السلم
            u = smootherstep(228, 264, f)
            c_rot = (0.0, 8.0 + u * 78.0, 180.0)
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, 14 * (1 - u) - 6 * u, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, 16 * (1 - u) - 12 * u, 0))
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-12 - 35 * u, -25 - 65 * u, 0))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(12 + 35 * u, -25 - 55 * u, 0))
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(-15 * u, -32 * (1 - u) + 12 * u, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(15 * u, -28 * (1 - u) - 8 * u, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, 38 * (1 - u) - 35 * u, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, 34 * (1 - u) - 25 * u, 0))
            s_val = (0.72 + 0.28 * u, 0.72 + 0.28 * u, 0.72 + 0.28 * u)
        else:
            # 00:11 – 00:27.4: السقوط الحر الديناميكي المستمر (ينتقل بسلاسة بين الوضع الجانبي ووضعية X المفتوحة!)
            jt = (f - 264) / 24.0
            # نحسب معامل التقلب الدوري بحيث يظهر Cooper:
            # - عند f=288 (00:12): وضع أفقي جانبي والوجه لليمين (كما في 00:12)
            # - عند f=315 (00:13): وضعية X مفتوحة الذراعين والساقين (كما في 00:13)
            # - عند f=340 (00:14): وضع أفقي جانبي والوجه لليمين (كما في 00:14)
            # - عند f=372 (00:15.5): وضعية X مائلة أثناء عبور الطائرة في الخلفية (كما في 00:15–00:16)
            # - عند f=432 (00:18): وضع أفقي جانبي والوجه لليسار فوق أضواء المدينة (كما في 00:18)
            # - عند f=468 (00:19.5): وضعية X مفتوحة بالكامل فوق أضواء المدينة (كما في 00:19–00:20)
            # - عند f=504..658 (00:21..00:27): وضع أفقي جانبي مستقر أثناء الابتعاد نحو الغابة (كما في 00:21–00:27)
            if f <= 405:
                # دورة التقلب الأولى (00:11 إلى 00:17)
                phase = (f - 288) / 26.0 * math.pi
                x_pose_fac = math.sin(phase) ** 2
                roll_ang = x_pose_fac * 78.0
                pitch_ang = 86.0 + math.sin(jt * 2.2) * 8.0
                yaw_ang = 180.0 + math.sin(phase * 0.5) * 22.0
            elif f <= 504:
                # دورة التقلب الثانية فوق أضواء المدينة (00:17 إلى 00:21): الوجه لليسار في 00:18 ثم X-pose في 00:19.5
                u_b = smootherstep(405, 432, f)
                x_pose_fac = math.sin(smoothstep(432, 500, f) * math.pi) ** 2
                roll_ang = x_pose_fac * 82.0
                pitch_ang = 84.0
                yaw_ang = 180.0 * (1.0 - u_b) + x_pose_fac * 18.0
            else:
                # استقرار السقوط الحر أثناء الابتعاد نحو الغابة (00:21 إلى 00:27.4)
                x_pose_fac = 0.15
                roll_ang = 12.0 + math.sin(jt * 2.0) * 5.0
                pitch_ang = 85.0
                yaw_ang = 180.0

            c_rot = (roll_ang, pitch_ang, yaw_ang)

            # حركة الأطراف المتناغمة بين الوضع الجانبي ووضعية X المفتوحة
            w1 = math.sin(jt * 4.2)
            w2 = math.cos(jt * 3.6)
            keyframe_transform(pivots["Pelvis"], f, rot_deg=(0, -6 + w1 * 4, 0))
            keyframe_transform(pivots["Spine"], f, rot_deg=(0, -14 + w2 * 4, 0))

            # في الوضع الجانبي تمتد الذراعان للأمام/الأسفل، وفي وضعية X تنفردان للجانبين بقوة
            sh_spread = 28.0 + x_pose_fac * 48.0
            keyframe_transform(pivots["Shoulder_L"], f, rot_deg=(-sh_spread + w1 * 8, -75 + w2 * 14, 0))
            keyframe_transform(pivots["Shoulder_R"], f, rot_deg=(sh_spread + w2 * 8, -55 - w1 * 14, 0))
            keyframe_transform(pivots["Elbow_L"], f, rot_deg=(0, -25 + w1 * 10, 0))
            keyframe_transform(pivots["Elbow_R"], f, rot_deg=(0, -20 + w2 * 10, 0))

            leg_spread = 10.0 + x_pose_fac * 26.0
            knee_bend = -52.0 * (1.0 - x_pose_fac * 0.65)
            keyframe_transform(pivots["Hip_L"], f, rot_deg=(-leg_spread, -16 + w1 * 12, 0))
            keyframe_transform(pivots["Hip_R"], f, rot_deg=(leg_spread, 14 + w2 * 12, 0))
            keyframe_transform(pivots["Knee_L"], f, rot_deg=(0, knee_bend + w1 * 10, 0))
            keyframe_transform(pivots["Knee_R"], f, rot_deg=(0, knee_bend * 0.75 + w2 * 10, 0))

            s_val = (1.0, 1.0, 1.0) if f <= 658 else (0.0001, 0.0001, 0.0001)

        keyframe_transform(cooper_root, f, loc=c_pos, rot_deg=c_rot, scale=s_val)

    # 3. تحريك حقل أضواء المدينة الضبابية (يظهر في 00:17.5–00:21 = الإطارات 418–504 ثم ينسحب بسلاسة)
    keyframe_transform(bokeh_root, 1,   loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))
    keyframe_transform(bokeh_root, 415, loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))
    for f in range(418, 512, 2):
        cp = get_cooper_pos(f)
        u = (f - 418) / 94.0
        # ينزلق في الخلفية السفلية اليسرى تحت Cooper ثم يخرج لليسار في 00:21 كما في فيديو LEMMiNO
        slide_out = smoothstep(480, 510, f) * 28.0
        keyframe_transform(
            bokeh_root, f,
            loc=(cp.x - 3.5 - slide_out, cp.y + 18.0, cp.z - 2.2),
            rot_deg=(82.0, 0.0, 0.0),
            scale=(1.0, 1.0, 1.0)
        )
    keyframe_transform(bokeh_root, 514, loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))
    keyframe_transform(bokeh_root, 864, loc=(0, 0, -500), scale=(0.0001, 0.0001, 0.0001))

    # 4. تحريك سرب الطيور البيضاء من قمم الأشجار البيضاء (الإطار 706 إلى 864 = 00:29.4–00:36)
    rng = random.Random(1980)
    for idx, b_obj in enumerate(birds):
        start_x = rng.uniform(-9.5, 9.5)
        start_y = rng.uniform(0.0, 6.0)
        start_z = -218.5 + rng.uniform(-1.2, 0.5)
        vx = rng.uniform(-6.5, 6.5)
        vy = rng.uniform(-2.0, 2.0)
        vz = rng.uniform(4.2, 7.8)

        keyframe_transform(b_obj, 1,   loc=(start_x, start_y, start_z), scale=(0.0001, 0.0001, 0.0001))
        keyframe_transform(b_obj, 704, loc=(start_x, start_y, start_z), scale=(0.0001, 0.0001, 0.0001))
        for bf in range(706, 865, 2):
            bt = (bf - 706) / 24.0
            bx = start_x + vx * bt + math.sin(bt * 4.0 + idx) * 0.5
            by = start_y + vy * bt
            bz = start_z + vz * bt
            flap = math.sin(bt * 24.0 + idx) * 35.0
            keyframe_transform(
                b_obj, bf,
                loc=(bx, by, bz),
                rot_deg=(flap, -12.0, math.degrees(math.atan2(vy, vx))),
                scale=(0.68, 0.68, 0.68)
            )

def setup_cinematic_cameras(scene, collection, aircraft_root, cooper_root, bokeh_root):
    """
    الكاميرا السينمائية الواحدة المتصلة (Master One-Take Camera)
    المعايرة إطارًا بإطار مع فيديو LEMMiNO الأصلي (00:00 إلى 00:36).
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

    for f in range(1, 865):
        ac = get_aircraft_pos(f)
        cp = get_cooper_pos(f)

        # مرحلة الطائرة (الإطارات 1 إلى 228 = 00:00 إلى 00:09.5)
        if f <= 52:
            # 00:00 – 00:02.2: الاقتراب من مسافة بعيدة نحو مقدمة الطائرة دون الاقتراب المفرط
            u = smootherstep(1, 52, f)
            cam_ac = ac + lerp_vec((-145.0, -4.0, -8.0), (-38.0, -7.5, -3.8), u)
            tgt_ac = ac + lerp_vec((0.0, 0.0, 0.6), (-1.5, 0.0, 0.6), u)
            roll = 2.0 * u
            fstop = 8.0
        elif f <= 104:
            # 00:02.2 – 00:04.3: الالتفاف السلس أمام الأنف إلى الجانب الأيسر مع إبقاء الطائرة كاملة في الكادر
            u = smootherstep(52, 104, f)
            angle = math.radians(191.0 + u * 54.0)  # من 191° إلى 245° على مسافة 36 وحدة
            dist = 38.5 - u * 4.5
            cam_ac = ac + Vector((math.cos(angle) * dist, math.sin(angle) * dist, -3.8 + u * 2.2))
            tgt_ac = ac + lerp_vec((-1.5, 0.0, 0.6), (1.0, 0.0, 0.4), u)
            roll = 2.0 * (1.0 - u)
            fstop = 8.0
        elif f <= 168:
            # 00:04.3 – 00:07.0: التحرك بموازاة الجانب الأيسر للكشف عن البدن والجناح والسلم الخلفي
            u = smootherstep(104, 168, f)
            angle = math.radians(245.0 + u * 42.0)  # من 245° إلى 287°
            dist = 34.0 - u * 6.0
            cam_ac = ac + Vector((math.cos(angle) * dist + u * 4.5, math.sin(angle) * dist, -1.6 - u * 1.6))
            tgt_ac = ac + lerp_vec((1.0, 0.0, 0.4), (6.8, 0.0, -0.2), u)
            roll = 0.0
            fstop = 8.0
        else:
            # 00:07.0 – 00:09.5: زاوية السلم الخلفي (خلف وأسفل الجناح الأيسر من مسافة متوسطة مريحة)
            u = smootherstep(168, 228, min(228, f))
            cam_ac = ac + lerp_vec((12.7, -26.8, -3.2), (16.5, -24.0, -3.8), u)
            tgt_ac = ac + lerp_vec((6.8, 0.0, -0.2), (9.2, 0.0, -0.8), u)
            roll = 0.0
            fstop = 6.0

        # مرحلة السقوط الحر والغابة (الإطارات 228 إلى 864)
        if f <= 340:
            # 00:09.5 – 00:14.2: تتبع قفز Cooper وتقلبه الأول في الهواء
            u = smootherstep(228, 340, max(228, f))
            cam_cp = cp + lerp_vec((1.5, -22.0, -1.0), (0.0, -10.5, 0.0), u)
            tgt_cp = cp + Vector((0.0, 0.0, 0.1))
            fstop_cp = 2.4
        elif f <= 410:
            # 00:14.2 – 00:17.1: الكاميرا تنظر خلف Cooper بينما تعبر الطائرة الصغيرة المموهة في أعلى الشاشة (00:15–00:16)
            u = smootherstep(340, 410, f)
            cam_cp = cp + Vector((0.0, -10.5, -1.8 * math.sin(u * math.pi)))
            tgt_cp = cp + Vector((0.0, 0.0, 0.4 * math.sin(u * math.pi)))
            fstop_cp = 0.8  # عزل بؤري قوي لتمويه الطائرة العابرة في الخلفية العلوية
        elif f <= 512:
            # 00:17.1 – 00:21.3: السقوط الحر فوق حقل أضواء المدينة الضبابية (Bokeh — 00:18–00:20)
            u = smootherstep(410, 512, f)
            cam_cp = cp + Vector((0.0, -10.2, 0.6))
            tgt_cp = cp + Vector((0.0, 0.0, 0.05))
            fstop_cp = 1.2
        elif f <= 658:
            # 00:21.3 – 00:27.4: ابتعاد الكاميرا للخلف بينما يصغر Cooper وترتفع الغابة من أسفل الكادر لتشغل 42% من الشاشة!
            u = smootherstep(512, 658, f)
            cam_cp = lerp_vec(cp + Vector((0.0, -10.2, 0.6)), Vector((0.0, -68.0, -212.5)), u)
            # إبقاء Cooper في منتصف الكادر حتى يدخل في قمم الأشجار البيضاء عند الإطار 658 (00:27.4)
            tgt_cp = lerp_vec(cp, Vector((0.0, 0.0, -214.8)), smootherstep(585, 658, f))
            fstop_cp = 1.4 + u * 6.6
        else:
            # 00:27.4 – 00:36.0: استقرار الكاميرا أمام الغابة (النصف السفلي 42% غابة والنصف العلوي 58% سماء سوداء تتطاير فيها الطيور والمطر)
            u = smootherstep(658, 864, f)
            cam_cp = lerp_vec(Vector((0.0, -68.0, -212.5)), Vector((0.0, -70.0, -213.0)), u)
            tgt_cp = lerp_vec(Vector((0.0, 0.0, -214.8)), Vector((0.0, 0.0, -215.2)), u)
            fstop_cp = 8.0

        # دمج سلس حول لحظة القفز (الإطارات 220..264)
        if f < 220:
            final_cam = cam_ac
            final_tgt = tgt_ac
            final_fstop = fstop
        elif f <= 264:
            b = smootherstep(220, 264, f)
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
