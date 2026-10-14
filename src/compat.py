import bpy

def get_blender_version():
    return bpy.app.version

def configure_render_engine(scene, samples=32, use_motion_blur=False):
    """ضبط محرك التصيير EEVEE ليعمل بكفاءة على CPU عبر Blender 3.x و 4.x."""
    version = get_blender_version()
    available_engines = [
        e.identifier for e in scene.render.bl_rna.properties['engine'].enum_items
    ]
    if 'BLENDER_EEVEE_NEXT' in available_engines:
        scene.render.engine = 'BLENDER_EEVEE_NEXT'
    elif 'BLENDER_EEVEE' in available_engines:
        scene.render.engine = 'BLENDER_EEVEE'
    else:
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = max(16, samples // 2)

    if hasattr(scene, "eevee"):
        if hasattr(scene.eevee, "taa_render_samples"):
            scene.eevee.taa_render_samples = samples
        if hasattr(scene.eevee, "use_bloom"):
            scene.eevee.use_bloom = True
            scene.eevee.bloom_intensity = 0.04
            scene.eevee.bloom_threshold = 0.9
        if hasattr(scene.eevee, "use_gtao"):
            scene.eevee.use_gtao = True

    scene.render.use_motion_blur = use_motion_blur
    if use_motion_blur and hasattr(scene.render, "motion_blur_shutter"):
        scene.render.motion_blur_shutter = 0.45

    # تفعيل إدارة الألوان القياسية لضمان التباين الحاد بين الأسود والأحمر والأبيض
    try:
        scene.view_settings.view_transform = 'Standard'
        scene.view_settings.look = 'High Contrast' if 'High Contrast' in [
            i.identifier for i in scene.view_settings.bl_rna.properties['look'].enum_items
        ] else 'None'
    except Exception:
        pass

def set_principled_socket(bsdf_node, socket_names, value):
    """ضبط مدخلات عقدة Principled BSDF بأمان عبر مختلف إصدارات Blender."""
    if isinstance(socket_names, str):
        socket_names = [socket_names]
    for name in socket_names:
        if name in bsdf_node.inputs:
            bsdf_node.inputs[name].default_value = value
            return True
    return False

def set_smooth_shading(obj, auto_smooth_angle_deg=35.0):
    """تطبيق التنعيم مع الحفاظ على الحواف الحادة."""
    if obj.type != 'MESH' or not obj.data:
        return
    for poly in obj.data.polygons:
        poly.use_smooth = True
    if hasattr(obj.data, "use_auto_smooth"):
        obj.data.use_auto_smooth = True
        import math
        obj.data.auto_smooth_angle = math.radians(auto_smooth_angle_deg)