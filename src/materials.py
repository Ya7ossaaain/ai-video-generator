import math
import bpy

def create_lemmino_materials(config):
    """إنشاء منظومة الخامات السينمائية المطابقة تمامًا لمقطع LEMMiNO الأصلي."""
    colors = config["colors"]
    mats = {}

    # 1. خامة بدن الطائرة (رمادي فحمي داكن مع تدرج خفيف جدًا من المقدمة للذيل)
    mat_aircraft = bpy.data.materials.new(name="LEMMiNO_Aircraft_Body")
    mat_aircraft.use_nodes = True
    nodes = mat_aircraft.node_tree.nodes
    links = mat_aircraft.node_tree.links
    nodes.clear()

    out = nodes.new(type='ShaderNodeOutputMaterial')
    emit = nodes.new(type='ShaderNodeEmission')
    coord = nodes.new(type='ShaderNodeTexCoord')
    sep = nodes.new(type='ShaderNodeSeparateXYZ')
    map_r = nodes.new(type='ShaderNodeMapRange')
    ramp = nodes.new(type='ShaderNodeValToRGB')

    map_r.inputs[1].default_value = -19.0
    map_r.inputs[2].default_value = 18.0
    map_r.inputs[3].default_value = 0.0
    map_r.inputs[4].default_value = 1.0

    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.032, 0.032, 0.035, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.015, 0.015, 0.017, 1.0)

    emit.inputs[1].default_value = 1.0
    links.new(coord.outputs['Object'], sep.inputs[0])
    links.new(sep.outputs[0], map_r.inputs[0])
    links.new(map_r.outputs[0], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], emit.inputs[0])
    links.new(emit.outputs[0], out.inputs['Surface'])
    mats["aircraft_body"] = mat_aircraft

    # 2. خامة الخطوط البيضاء الحادة والطيور
    mat_white = bpy.data.materials.new(name="LEMMiNO_White_Line")
    mat_white.use_nodes = True
    wnodes = mat_white.node_tree.nodes
    wlinks = mat_white.node_tree.links
    wnodes.clear()
    w_out = wnodes.new(type='ShaderNodeOutputMaterial')
    w_emit = wnodes.new(type='ShaderNodeEmission')
    w_emit.inputs[0].default_value = tuple(colors["white_line"])
    w_emit.inputs[1].default_value = 1.05
    wlinks.new(w_emit.outputs[0], w_out.inputs['Surface'])
    mats["white_line"] = mat_white

    # 3. خامة خطوط الرياح والمطر الرمادية الخافتة جدًا (Subtle Atmospheric Rain/Wind Streaks)
    mat_streak = bpy.data.materials.new(name="LEMMiNO_Rain_Streak")
    mat_streak.use_nodes = True
    snodes = mat_streak.node_tree.nodes
    slinks = mat_streak.node_tree.links
    snodes.clear()
    s_out = snodes.new(type='ShaderNodeOutputMaterial')
    s_emit = snodes.new(type='ShaderNodeEmission')
    s_emit.inputs[0].default_value = (0.065, 0.065, 0.070, 1.0)
    s_emit.inputs[1].default_value = 1.0
    slinks.new(s_emit.outputs[0], s_out.inputs['Surface'])
    mats["rain_streak"] = mat_streak

    # 4. خامة D.B. Cooper القرمزية المشبعة (Crimson Red Silhouette)
    mat_cooper = bpy.data.materials.new(name="LEMMiNO_Cooper_Red")
    mat_cooper.use_nodes = True
    cnodes = mat_cooper.node_tree.nodes
    clinks = mat_cooper.node_tree.links
    cnodes.clear()
    c_out = cnodes.new(type='ShaderNodeOutputMaterial')
    c_emit = cnodes.new(type='ShaderNodeEmission')
    c_emit.inputs[0].default_value = tuple(colors["cooper_red"])
    c_emit.inputs[1].default_value = 1.15
    clinks.new(c_emit.outputs[0], c_out.inputs['Surface'])
    mats["cooper_red"] = mat_cooper

    # 5. خامة غابة الصنوبر الاحترافية (لون موحد لكل شجرة + بقعة إضاءة مركزية وتعتيم في المقدمة والأطراف)
    mat_forest = bpy.data.materials.new(name="LEMMiNO_Forest_Gradient")
    mat_forest.use_nodes = True
    fnodes = mat_forest.node_tree.nodes
    flinks = mat_forest.node_tree.links
    fnodes.clear()

    f_out = fnodes.new(type='ShaderNodeOutputMaterial')
    f_emit = fnodes.new(type='ShaderNodeEmission')
    f_obj_info = fnodes.new(type='ShaderNodeObjectInfo')
    f_geom = fnodes.new(type='ShaderNodeNewGeometry')
    f_mix_pos = fnodes.new(type='ShaderNodeMix')
    f_mix_pos.data_type = 'VECTOR'
    f_mix_pos.inputs[0].default_value = 0.22  # 78% لون موحد للشجرة و 22% تدرج ناعم

    f_vec_dist = fnodes.new(type='ShaderNodeVectorMath')
    f_map = fnodes.new(type='ShaderNodeMapRange')
    f_ramp = fnodes.new(type='ShaderNodeValToRGB')

    # مركز البقعة المضيئة في قلب الغابة عند (0.0, 4.0, -225.0)
    f_vec_dist.operation = 'DISTANCE'
    f_vec_dist.inputs[1].default_value = (0.0, 4.0, -225.0)

    f_map.inputs[1].default_value = 0.0
    f_map.inputs[2].default_value = 34.0
    f_map.inputs[3].default_value = 0.0
    f_map.inputs[4].default_value = 1.0
    f_map.clamp = True

    els = f_ramp.color_ramp.elements
    els[0].position = 0.0
    els[0].color = (1.0, 1.0, 1.0, 1.0)         # قلب الغابة أبيض ساطع
    els[1].position = 0.92
    els[1].color = (0.009, 0.009, 0.010, 1.0)   # الأطراف الجانبية والمقدمة سوداء/داكنة جدًا
    e1 = f_ramp.color_ramp.elements.new(0.18)
    e1.color = (0.94, 0.94, 0.95, 1.0)
    e2 = f_ramp.color_ramp.elements.new(0.40)
    e2.color = (0.46, 0.46, 0.48, 1.0)
    e3 = f_ramp.color_ramp.elements.new(0.64)
    e3.color = (0.15, 0.15, 0.16, 1.0)
    e4 = f_ramp.color_ramp.elements.new(0.80)
    e4.color = (0.04, 0.04, 0.045, 1.0)

    f_emit.inputs[1].default_value = 1.0

    flinks.new(f_obj_info.outputs['Location'], f_mix_pos.inputs[4])
    flinks.new(f_geom.outputs['Position'], f_mix_pos.inputs[5])
    flinks.new(f_mix_pos.outputs[1], f_vec_dist.inputs[0])
    flinks.new(f_vec_dist.outputs['Value'], f_map.inputs[0])
    flinks.new(f_map.outputs[0], f_ramp.inputs['Fac'])
    flinks.new(f_ramp.outputs['Color'], f_emit.inputs[0])
    flinks.new(f_emit.outputs[0], f_out.inputs['Surface'])
    mats["forest_gradient"] = mat_forest

    # 6. خامة أضواء المدينة الضبابية الحقيقية (True Radial Gaussian Bokeh Shader عبر Object Coords)
    mat_bokeh = bpy.data.materials.new(name="LEMMiNO_City_Bokeh")
    mat_bokeh.use_nodes = True
    bnodes = mat_bokeh.node_tree.nodes
    blinks = mat_bokeh.node_tree.links
    bnodes.clear()

    b_out = bnodes.new(type='ShaderNodeOutputMaterial')
    b_emit = bnodes.new(type='ShaderNodeEmission')
    b_coord = bnodes.new(type='ShaderNodeTexCoord')
    b_len = bnodes.new(type='ShaderNodeVectorMath')
    b_ramp = bnodes.new(type='ShaderNodeValToRGB')

    # Object coordinates على دائرة نصف قطرها 1 تعطي المسافة الشعاعية الدقيقة من 0 في المركز إلى 1 عند الحافة!
    b_len.operation = 'LENGTH'

    bels = b_ramp.color_ramp.elements
    bels[0].position = 0.0
    bels[0].color = (0.25, 0.26, 0.28, 1.0)          # مركز النقطة الضوئية رمادي دافئ ناعم
    bels[1].position = 0.88
    bels[1].color = tuple(colors["background_void"]) # يتلاشى كليًا في لون الخلفية الأسود قبل الحافة
    b1 = b_ramp.color_ramp.elements.new(0.32)
    b1.color = (0.14, 0.14, 0.15, 1.0)
    b2 = b_ramp.color_ramp.elements.new(0.62)
    b2.color = (0.035, 0.035, 0.038, 1.0)

    b_emit.inputs[1].default_value = 1.0
    blinks.new(b_coord.outputs['Object'], b_len.inputs[0])
    blinks.new(b_len.outputs['Value'], b_ramp.inputs['Fac'])
    blinks.new(b_ramp.outputs['Color'], b_emit.inputs[0])
    blinks.new(b_emit.outputs[0], b_out.inputs['Surface'])
    mats["city_bokeh"] = mat_bokeh

    return mats

def add_inverted_hull_outline(obj, white_material, thickness=0.02):
    return

def setup_freestyle_outlines(scene, thickness=1.5):
    """
    ضبط Freestyle لرسم الحواف الخارجية والخطوط المعلمة فقط (بدون select_crease)
    وهو ما يمنع ظهور أي خطوط مثلثية مشوهة تحت جناح الطائرة!
    """
    scene.render.use_freestyle = True
    scene.render.line_thickness = thickness
    for view_layer in scene.view_layers:
        view_layer.use_freestyle = True
        fs = view_layer.freestyle_settings
        fs.crease_angle = math.radians(15.0)
        while fs.linesets:
            fs.linesets.remove(fs.linesets[0])
        lineset = fs.linesets.new(name="LEMMiNO_Tech_Lines")
        lineset.select_silhouette = True
        lineset.select_border = True
        lineset.select_crease = False  # تعطيل Crease التلقائي لمنع خربشات الجناح
        lineset.select_contour = True
        lineset.select_external_contour = True
        lineset.select_edge_mark = True
        linestyle = lineset.linestyle
        linestyle.color = (0.94, 0.94, 0.96)
        linestyle.thickness = thickness
