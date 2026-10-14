import bpy
from .compat import set_principled_socket

def create_lemmino_materials(config):
    """إنشاء منظومة الخامات القياسية المستلهمة من مرجع LEMMiNO."""
    colors = config["colors"]
    mats = {}

    # 1. خامة بدن الطائرة (رمادي فحمي مطفي مع حواف Fresnel خفيفة)
    mat_aircraft = bpy.data.materials.new(name="LEMMiNO_Aircraft_Body")
    mat_aircraft.use_nodes = True
    nodes = mat_aircraft.node_tree.nodes
    links = mat_aircraft.node_tree.links
    nodes.clear()

    output = nodes.new(type='ShaderNodeOutputMaterial')
    mix_shader = nodes.new(type='ShaderNodeMixShader')
    diffuse = nodes.new(type='ShaderNodeBsdfDiffuse')
    emission_rim = nodes.new(type='ShaderNodeEmission')
    layer_weight = nodes.new(type='ShaderNodeLayerWeight')
    ramp = nodes.new(type='ShaderNodeValToRGB')

    diffuse.inputs['Color'].default_value = tuple(colors["aircraft_body"])
    diffuse.inputs['Roughness'].default_value = 0.95

    layer_weight.inputs['Blend'].default_value = 0.25
    ramp.color_ramp.elements[0].position = 0.68
    ramp.color_ramp.elements[0].color = (0.02, 0.02, 0.025, 1.0)
    ramp.color_ramp.elements[1].position = 0.96
    ramp.color_ramp.elements[1].color = (0.28, 0.28, 0.30, 1.0)

    emission_rim.inputs['Strength'].default_value = 1.0

    links.new(layer_weight.outputs['Facing'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], emission_rim.inputs['Color'])
    links.new(diffuse.outputs['BSDF'], mix_shader.inputs[1])
    links.new(emission_rim.outputs['Emission'], mix_shader.inputs[2])
    mix_shader.inputs['Fac'].default_value = 0.65
    links.new(mix_shader.outputs['Shader'], output.inputs['Surface'])
    mats["aircraft_body"] = mat_aircraft

    # 2. خامة الخطوط البيضاء الحادة (للحواف الميكانيكية، القضبان، وInverted Hull)
    mat_white = bpy.data.materials.new(name="LEMMiNO_White_Line")
    mat_white.use_nodes = True
    mat_white.use_backface_culling = True
    wnodes = mat_white.node_tree.nodes
    wlinks = mat_white.node_tree.links
    wnodes.clear()
    w_out = wnodes.new(type='ShaderNodeOutputMaterial')
    w_emit = wnodes.new(type='ShaderNodeEmission')
    w_emit.inputs['Color'].default_value = tuple(colors["white_line"])
    w_emit.inputs['Strength'].default_value = 1.15
    wlinks.new(w_emit.outputs['Emission'], w_out.inputs['Surface'])
    mats["white_line"] = mat_white

    # 3. خامة D.B. Cooper القرمزية المشبعة (Crimson Red Silhouette)
    mat_cooper = bpy.data.materials.new(name="LEMMiNO_Cooper_Red")
    mat_cooper.use_nodes = True
    cnodes = mat_cooper.node_tree.nodes
    clinks = mat_cooper.node_tree.links
    cnodes.clear()
    c_out = cnodes.new(type='ShaderNodeOutputMaterial')
    c_emit = cnodes.new(type='ShaderNodeEmission')
    c_lw = cnodes.new(type='ShaderNodeLayerWeight')
    c_mix = cnodes.new(type='ShaderNodeMixRGB')

    c_lw.inputs['Blend'].default_value = 0.3
    c_mix.inputs['Color1'].default_value = tuple(colors["cooper_red"])
    c_mix.inputs['Color2'].default_value = (1.0, 0.18, 0.18, 1.0)
    c_emit.inputs['Strength'].default_value = 1.25

    clinks.new(c_lw.outputs['Fresnel'], c_mix.inputs['Fac'])
    clinks.new(c_mix.outputs['Color'], c_emit.inputs['Color'])
    clinks.new(c_emit.outputs['Emission'], c_out.inputs['Surface'])
    mats["cooper_red"] = mat_cooper

    # 4. خامة غابة الصنوبر ذات التدرج الشعاعي المركزي (Radial Spotlight Forest Shader)
    mat_forest = bpy.data.materials.new(name="LEMMiNO_Forest_Gradient")
    mat_forest.use_nodes = True
    fnodes = mat_forest.node_tree.nodes
    flinks = mat_forest.node_tree.links
    fnodes.clear()

    f_out = fnodes.new(type='ShaderNodeOutputMaterial')
    f_emit = fnodes.new(type='ShaderNodeEmission')
    f_geom = fnodes.new(type='ShaderNodeNewGeometry')
    f_vec_math = fnodes.new(type='ShaderNodeVectorMath')
    f_map = fnodes.new(type='ShaderNodeMapRange')
    f_ramp = fnodes.new(type='ShaderNodeValToRGB')

    # مركز البقعة المضيئة في الغابة عند (0, 0, -220)
    f_vec_math.operation = 'DISTANCE'
    f_vec_math.inputs[1].default_value = (0.0, 0.0, -220.0)

    f_map.inputs['From Min'].default_value = 0.0
    f_map.inputs['From Max'].default_value = 62.0
    f_map.inputs['To Min'].default_value = 0.0
    f_map.inputs['To Max'].default_value = 1.0
    f_map.clamp = True

    # تدرج من الأبيض الساطع في المركز إلى الرمادي المتدرج فالأسود في الأطراف
    els = f_ramp.color_ramp.elements
    els[0].position = 0.0
    els[0].color = (0.98, 0.98, 0.99, 1.0)
    els[1].position = 0.72
    els[1].color = (0.12, 0.12, 0.13, 1.0)
    e_mid = f_ramp.color_ramp.elements.new(0.32)
    e_mid.color = (0.52, 0.52, 0.54, 1.0)
    e_dark = f_ramp.color_ramp.elements.new(0.95)
    e_dark.color = (0.015, 0.015, 0.018, 1.0)

    f_emit.inputs['Strength'].default_value = 1.05

    flinks.new(f_geom.outputs['Position'], f_vec_math.inputs[0])
    flinks.new(f_vec_math.outputs['Value'], f_map.inputs['Value'])
    flinks.new(f_map.outputs['Result'], f_ramp.inputs['Fac'])
    flinks.new(f_ramp.outputs['Color'], f_emit.inputs['Color'])
    flinks.new(f_emit.outputs['Emission'], f_out.inputs['Surface'])
    mats["forest_gradient"] = mat_forest

    # 5. خامة أضواء المدينة الضبابية (Bokeh City Lights)
    mat_bokeh = bpy.data.materials.new(name="LEMMiNO_City_Bokeh")
    mat_bokeh.use_nodes = True
    bnodes = mat_bokeh.node_tree.nodes
    blinks = mat_bokeh.node_tree.links
    bnodes.clear()
    b_out = bnodes.new(type='ShaderNodeOutputMaterial')
    b_emit = bnodes.new(type='ShaderNodeEmission')
    b_emit.inputs['Color'].default_value = tuple(colors["city_bokeh"])
    b_emit.inputs['Strength'].default_value = 3.5
    blinks.new(b_emit.outputs['Emission'], b_out.inputs['Surface'])
    mats["city_bokeh"] = mat_bokeh

    return mats

def add_inverted_hull_outline(obj, white_material, thickness=0.035):
    """إضافة طبقة حواف بيضاء هندسية (Inverted Hull) لضمان ظهور الخطوط البيضاء في كل الظروف."""
    if obj.type != 'MESH' or not obj.data:
        return
    if white_material.name not in [m.name for m in obj.data.materials if m]:
        obj.data.materials.append(white_material)
    mat_idx = len(obj.data.materials) - 1

    solid = obj.modifiers.new(name="LEMMiNO_Outline", type='SOLIDIFY')
    solid.thickness = -abs(thickness)
    solid.offset = 1.0
    solid.use_flip_normals = True
    solid.material_offset = mat_idx
    if hasattr(solid, "use_quality_normals"):
        solid.use_quality_normals = True

def setup_freestyle_outlines(scene, thickness=2.0):
    """تفعيل Freestyle لرسم الخطوط الهندسية البيضاء الدقيقة على طائرة Boeing 727."""
    scene.render.use_freestyle = True
    scene.render.line_thickness = thickness
    for view_layer in scene.view_layers:
        view_layer.use_freestyle = True
        fs = view_layer.freestyle_settings
        fs.crease_angle = 0.58  # ~33 درجة لإظهار خطوط البدن والمحركات والجنيحات
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
        linestyle.color = (0.94, 0.94, 0.96)
        linestyle.thickness = thickness