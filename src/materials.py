import math
import bpy

def create_lemmino_materials(config):
    """إنشاء منظومة الخامات السينمائية المطابقة لأسلوب LEMMiNO والمتوافقة مع Blender 4.0."""
    colors = config["colors"]
    mats = {}

    # 1. خامة بدن الطائرة (رمادي فحمي داكن غير لامع مع تدرج جانبي طفيف جدًا كما في اللقطة 4 و 5)
    mat_aircraft = bpy.data.materials.new(name="LEMMiNO_Aircraft_Body")
    mat_aircraft.use_nodes = True
    nodes = mat_aircraft.node_tree.nodes
    links = mat_aircraft.node_tree.links
    nodes.clear()

    out = nodes.new(type='ShaderNodeOutputMaterial')
    emit = nodes.new(type='ShaderNodeEmission')
    geom = nodes.new(type='ShaderNodeNewGeometry')
    sep = nodes.new(type='ShaderNodeSeparateXYZ')
    map_r = nodes.new(type='ShaderNodeMapRange')
    ramp = nodes.new(type='ShaderNodeValToRGB')

    map_r.inputs[1].default_value = -18.0
    map_r.inputs[2].default_value = 18.0
    map_r.inputs[3].default_value = 0.0
    map_r.inputs[4].default_value = 1.0

    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.032, 0.032, 0.035, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.015, 0.015, 0.018, 1.0)

    emit.inputs[1].default_value = 1.0

    links.new(geom.outputs['Position'], sep.inputs[0])
    links.new(sep.outputs[0], map_r.inputs[0])
    links.new(map_r.outputs[0], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], emit.inputs[0])
    links.new(emit.outputs[0], out.inputs['Surface'])
    mats["aircraft_body"] = mat_aircraft

    # 2. خامة الخطوط البيضاء الحادة
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

    # 3. خامة D.B. Cooper القرمزية المشبعة (Crimson Red Silhouette)
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

    # 4. خامة غابة الصنوبر ذات التدرج الشعاعي المركزي (Radial Spotlight + Vertical Tree Shading)
    mat_forest = bpy.data.materials.new(name="LEMMiNO_Forest_Gradient")
    mat_forest.use_nodes = True
    fnodes = mat_forest.node_tree.nodes
    flinks = mat_forest.node_tree.links
    fnodes.clear()

    f_out = fnodes.new(type='ShaderNodeOutputMaterial')
    f_emit = fnodes.new(type='ShaderNodeEmission')
    f_geom = fnodes.new(type='ShaderNodeNewGeometry')
    f_vec_dist = fnodes.new(type='ShaderNodeVectorMath')
    f_map = fnodes.new(type='ShaderNodeMapRange')
    f_ramp = fnodes.new(type='ShaderNodeValToRGB')

    # مركز البقعة المضيئة في قلب الغابة عند (0.0, -2.0, -219.0)
    f_vec_dist.operation = 'DISTANCE'
    f_vec_dist.inputs[1].default_value = (0.0, -2.0, -219.0)

    f_map.inputs[1].default_value = 0.0
    f_map.inputs[2].default_value = 46.0
    f_map.inputs[3].default_value = 0.0
    f_map.inputs[4].default_value = 1.0
    f_map.clamp = True

    els = f_ramp.color_ramp.elements
    els[0].position = 0.0
    els[0].color = (0.99, 0.99, 1.0, 1.0)    # قلب الغابة أبيض ساطع
    els[1].position = 0.96
    els[1].color = (0.010, 0.010, 0.012, 1.0) # الأطراف والمقدمة داكنة جدًا
    e1 = f_ramp.color_ramp.elements.new(0.22)
    e1.color = (0.85, 0.85, 0.87, 1.0)
    e2 = f_ramp.color_ramp.elements.new(0.48)
    e2.color = (0.38, 0.38, 0.40, 1.0)
    e3 = f_ramp.color_ramp.elements.new(0.74)
    e3.color = (0.08, 0.08, 0.09, 1.0)

    f_emit.inputs[1].default_value = 1.0

    flinks.new(f_geom.outputs['Position'], f_vec_dist.inputs[0])
    flinks.new(f_vec_dist.outputs['Value'], f_map.inputs[0])
    flinks.new(f_map.outputs[0], f_ramp.inputs['Fac'])
    flinks.new(f_ramp.outputs['Color'], f_emit.inputs[0])
    flinks.new(f_emit.outputs[0], f_out.inputs['Surface'])
    mats["forest_gradient"] = mat_forest

    # 5. خامة أضواء المدينة الضبابية الناعمة (Soft Procedural Bokeh Shader بدون حواف حادة)
    mat_bokeh = bpy.data.materials.new(name="LEMMiNO_City_Bokeh")
    mat_bokeh.use_nodes = True
    bnodes = mat_bokeh.node_tree.nodes
    blinks = mat_bokeh.node_tree.links
    bnodes.clear()

    b_out = bnodes.new(type='ShaderNodeOutputMaterial')
    b_emit = bnodes.new(type='ShaderNodeEmission')
    b_coord = bnodes.new(type='ShaderNodeTexCoord')
    b_dist = bnodes.new(type='ShaderNodeVectorMath')
    b_ramp = bnodes.new(type='ShaderNodeValToRGB')

    # حساب المسافة من مركز القرص (0.5, 0.5, 0.0) لتوليد تمويه Bokeh ناعم جدًا
    b_dist.operation = 'DISTANCE'
    b_dist.inputs[1].default_value = (0.5, 0.5, 0.0)

    bels = b_ramp.color_ramp.elements
    bels[0].position = 0.0
    bels[0].color = (0.32, 0.33, 0.35, 1.0)   # رمادي دافئ خافت في قلب النقطة الضبابية
    bels[1].position = 0.48
    bels[1].color = tuple(colors["background_void"])  # يتلاشى تمامًا في لون خلفية الليل
    b_mid = b_ramp.color_ramp.elements.new(0.24)
    b_mid.color = (0.14, 0.14, 0.16, 1.0)

    b_emit.inputs[1].default_value = 1.0

    blinks.new(b_coord.outputs['Generated'], b_dist.inputs[0])
    blinks.new(b_dist.outputs['Value'], b_ramp.inputs['Fac'])
    blinks.new(b_ramp.outputs['Color'], b_emit.inputs[0])
    blinks.new(b_emit.outputs[0], b_out.inputs['Surface'])
    mats["city_bokeh"] = mat_bokeh

    return mats

def add_inverted_hull_outline(obj, white_material, thickness=0.02):
    """تم تعطيل Solidify المقلوب على الطائرة للاعتماد على Freestyle الدقيق والأنابيب الهندسية."""
    return

def setup_freestyle_outlines(scene, thickness=1.8):
    """ضبط Freestyle لرسم الحواف البيضاء الهندسية لطائرة Boeing 727 كما في مرجع LEMMiNO."""
    scene.render.use_freestyle = True
    scene.render.line_thickness = thickness
    for view_layer in scene.view_layers:
        view_layer.use_freestyle = True
        fs = view_layer.freestyle_settings
        fs.crease_angle = math.radians(26.0)
        while fs.linesets:
            fs.linesets.remove(fs.linesets[0])
        lineset = fs.linesets.new(name="LEMMiNO_Tech_Lines")
        lineset.select_silhouette = True
        lineset.select_border = True
        lineset.select_crease = True
        lineset.select_contour = True
        lineset.select_external_contour = True
        lineset.select_edge_mark = True
        linestyle = lineset.linestyle
        linestyle.color = (0.95, 0.95, 0.97)
        linestyle.thickness = thickness