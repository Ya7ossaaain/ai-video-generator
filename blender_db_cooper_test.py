import bpy, math, os
from mathutils import Vector

# Original 40-second, procedural Blender animation test inspired by the general
# visual idea of a nighttime aircraft jump. It is not a frame-for-frame copy.
OUT_DIR = os.environ.get('BLENDER_OUTPUT_DIR', os.path.abspath('output'))
os.makedirs(OUT_DIR, exist_ok=True)
VIDEO_PATH = os.path.join(OUT_DIR, 'db_cooper_test.mp4')

# Clean scene
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
    pass
scene = bpy.context.scene

# Render setup: EEVEE keeps the first CI test practical on CPU runners.
# Blender 4.2+ renamed the real-time renderer to EEVEE Next.
scene.render.engine = 'BLENDER_EEVEE_NEXT' if bpy.app.version >= (4, 2, 0) else 'BLENDER_EEVEE'
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.fps = 24
scene.frame_start = 1
scene.frame_end = 960
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
scene.render.filepath = VIDEO_PATH
scene.render.use_file_extension = True
scene.render.threads_mode = 'FIXED'
scene.render.threads = max(2, min(8, os.cpu_count() or 4))
scene.render.film_transparent = False
scene.view_settings.view_transform = 'Standard'
scene.view_settings.look = 'Medium High Contrast'
scene.view_settings.exposure = -0.2
scene.world.color = (0.002, 0.004, 0.012)

# EEVEE settings vary slightly across Blender versions.
try:
    if bpy.app.version < (4, 2, 0):
        scene.eevee.taa_render_samples = 16
        scene.eevee.use_gtao = True
        scene.eevee.gtao_distance = 3.0
        scene.eevee.gtao_factor = 1.2
except Exception as e:
    print('EEVEE optional settings skipped:', e)

# Helpers
def material(name, color, metallic=0.0, roughness=0.6, emission=None, strength=0.0):
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    bs = m.node_tree.nodes.get('Principled BSDF')
    if bs:
        bs.inputs['Base Color'].default_value = (*color, 1)
        bs.inputs['Metallic'].default_value = metallic
        bs.inputs['Roughness'].default_value = roughness
        if emission:
            key = 'Emission Color' if 'Emission Color' in bs.inputs else 'Emission'
            if key in bs.inputs:
                bs.inputs[key].default_value = (*emission, 1)
            if 'Emission Strength' in bs.inputs:
                bs.inputs['Emission Strength'].default_value = strength
    return m

def apply(obj, mat):
    obj.data.materials.append(mat)
    return obj

def smooth(obj):
    if obj.type == 'MESH':
        for p in obj.data.polygons: p.use_smooth = True
    return obj

def sphere(name, loc, scale, mat, seg=16, rings=10):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, location=loc)
    o = bpy.context.object; o.name = name; o.scale = scale; apply(o, mat); smooth(o)
    return o

def box(name, loc, scale, mat, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object; o.name = name; o.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True); apply(o, mat)
    if bevel:
        mod = o.modifiers.new('Soft edges', 'BEVEL'); mod.width = bevel; mod.segments = 2
        o.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return o

def rod(name, a, b, radius, mat, vertices=12):
    a, b = Vector(a), Vector(b); d = b-a
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=d.length, location=(a+b)/2)
    o = bpy.context.object; o.name = name; o.rotation_mode = 'QUATERNION'; o.rotation_quaternion = d.to_track_quat('Z','Y')
    apply(o, mat); smooth(o); return o

def cone_between(name, a, b, r1, r2, mat, vertices=24):
    a, b = Vector(a), Vector(b); d=b-a
    bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=r1, radius2=r2, depth=d.length, location=(a+b)/2)
    o=bpy.context.object; o.name=name; o.rotation_mode='QUATERNION'; o.rotation_quaternion=d.to_track_quat('Z','Y')
    apply(o, mat); smooth(o); return o

def polygon(name, verts, faces, mat):
    mesh=bpy.data.meshes.new(name+'Mesh'); mesh.from_pydata(verts, [], faces); mesh.materials.append(mat); mesh.update()
    obj=bpy.data.objects.new(name, mesh); scene.collection.objects.link(obj); return obj

def key_location(obj, frame, loc):
    obj.location=loc; obj.keyframe_insert(data_path='location', frame=frame)

def key_rotation(obj, frame, rot):
    obj.rotation_euler=rot; obj.keyframe_insert(data_path='rotation_euler', frame=frame)

def smooth_action(obj):
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points: kp.interpolation='BEZIER'

# Materials
aluminum=material('Aircraft aluminium',(0.26,0.32,0.38),0.65,0.32)
wingmat=material('Wing shadow metal',(0.13,0.18,0.23),0.55,0.4)
dark=material('Deep charcoal',(0.012,0.018,0.027),0.1,0.8)
window=material('Cabin windows',(0.008,0.014,0.025),0.05,0.2)
windowlit=material('A few warm windows',(0.55,0.25,0.08),0.1,0.25,(1.0,0.22,0.045),1.2)
skin=material('Face in low light',(0.16,0.10,0.075),0,0.85)
tie=material('Tie',(0.07,0.015,0.02),0,0.8)
cloud=material('Night clouds',(0.025,0.045,0.075),0,1.0,(0.018,0.03,0.06),0.25)
star=material('Stars',(0.5,0.65,1.0),0,0.3,(0.35,0.48,1.0),1.5)
red=material('Red nav light',(0.5,0.01,0.005),0,0.3,(1.0,0.005,0.002),2.0)
green=material('Green nav light',(0.005,0.3,0.04),0,0.3,(0.005,1.0,0.03),1.5)
moonmat=material('Moon',(0.3,0.38,0.52),0,0.7,(0.25,0.35,0.55),0.8)

# Distant star field
for i in range(115):
    x=((i*73)%211-105)*0.72; y=((i*37)%97)*0.72+22; z=10+((i*29)%67)*0.65
    r=0.018+((i*11)%4)*0.009
    sphere('Distant star',(x,y,z),(r,r,r),star,8,6)
sphere('Moon',(20,38,22),(1.7,1.7,1.7),moonmat,20,12)

# Low stylized clouds, deliberately low-poly/low-cost for CI.
for row in range(3):
    for j in range(13):
        x=-44+j*7.2+(row%2)*2.1; y=8+row*4.5+((j*7)%5); z=-13-row*2.3+((j*3)%4)*0.65
        sphere('Cloud bank',(x,y,z),(3.1+((j*5)%4)*0.55,1.1+((j*3)%3)*0.3,0.75+((j*7)%3)*0.2),cloud,10,7)

# Aircraft root
plane=bpy.data.objects.new('AIRCRAFT_ROOT',None); scene.collection.objects.link(plane)
aircraft=[]
aircraft.append(cone_between('727 style fuselage',(-5.2,0,0),(5.5,0,0),0.68,0.82,aluminum,28))
aircraft.append(sphere('Rounded nose',(5.2,0,0),(0.72,0.67,0.67),aluminum,20,12))
aircraft.append(cone_between('Tail taper',(-6.0,0,0),(-4.7,0,0),0.1,0.68,aluminum,20))
# Swept wings
aircraft.append(polygon('Swept wings',[
    (-1.9,-0.9,-0.08),(1.0,-0.9,-0.08),(0.0,-8.0,-0.34),(-2.3,-7.2,-0.34),
    (-1.9,0.9,-0.08),(1.0,0.9,-0.08),(0.0,8.0,-0.34),(-2.3,7.2,-0.34)],[(0,1,2,3),(4,7,6,5)],wingmat))
aircraft.append(box('Wing fairing',(-0.25,0,-0.2),(3.3,2.0,0.16),wingmat,0.1))
aircraft.append(polygon('Tail fin',[(-5.1,-.1,.2),(-4.2,-.1,.2),(-4.9,-.1,2.1),(-5.7,-.1,1.65),(-5.1,.1,.2),(-4.2,.1,.2),(-4.9,.1,2.1),(-5.7,.1,1.65)],[(0,1,2,3),(4,7,6,5)],wingmat))
aircraft.append(polygon('Tail stabilizers',[(-5.4,-.4,.1),(-4.3,-.4,.1),(-5.0,-2.7,-.05),(-5.7,-2.4,-.05),(-5.4,.4,.1),(-4.3,.4,.1),(-5.0,2.7,-.05),(-5.7,2.4,-.05)],[(0,1,2,3),(4,7,6,5)],wingmat))
for yy in (-0.55,0,0.55):
    aircraft.append(cone_between('Rear engine',(-5.0,yy,0.28),(-3.35,yy,0.28),0.22,0.29,dark,16))
    aircraft.append(sphere('Engine intake',(-5.02,yy,0.28),(0.09,0.22,0.22),dark,12,8))
for side in (-1,1):
    for i in range(17):
        xx=-3.8+i*0.47; yy=side*0.66
        w=sphere('Cabin window',(xx,yy,0.27),(0.095,0.028,0.06),windowlit if (side==-1 and i in (3,10,14)) else window,8,6)
        aircraft.append(w)
# Rear door and stair
aircraft.append(box('Open rear door shadow',(-4.25,-0.70,-0.02),(0.68,0.045,1.02),dark,0.03))
ramp=box('Rear stair ramp',(-4.82,-0.84,-0.57),(1.25,0.08,0.08),wingmat,0.02); ramp.rotation_euler[1]=radians(-19); aircraft.append(ramp)
for i in range(4):
    aircraft.append(box('Stair tread',(-4.35-i*.22,-0.91,-.2-i*.12),(.26,.13,.045),aluminum,.01))
aircraft.append(sphere('Red nav light',(.15,-7.75,-.2),(.09,.09,.09),red,8,6))
aircraft.append(sphere('Green nav light',(.15,7.75,-.2),(.09,.09,.09),green,8,6))
for obj in aircraft: obj.parent=plane

# Suit-clad figure, built as a recognizable but deliberately shadowed silhouette.
person=bpy.data.objects.new('COOPER_FIGURE_ROOT',None); scene.collection.objects.link(person)
parts=[]
parts.append(sphere('Suit torso',(0,0,.43),(.28,.19,.43),dark,14,10))
parts.append(sphere('Head',(0.02,0,1.0),(.16,.15,.18),skin,14,10))
parts.append(sphere('Dark hair',(0.02,0,1.13),(.17,.16,.08),dark,14,8))
parts.append(cone_between('Tie',(.02,-.19,.78),(.02,-.20,.45),.045,.014,tie,8))
parts.append(rod('Left upper arm',(-.18,0,.66),(-.48,-.02,.46),.075,dark))
parts.append(rod('Left forearm',(-.48,-.02,.46),(-.74,-.04,.57),.055,dark))
parts.append(rod('Right upper arm',(.18,0,.66),(.47,.02,.47),.075,dark))
parts.append(rod('Right forearm',(.47,.02,.47),(.72,.04,.67),.055,dark))
parts.append(rod('Left thigh',(-.12,0,.12),(-.28,.02,-.20),.09,dark))
parts.append(rod('Left shin',(-.28,.02,-.20),(-.42,.03,-.43),.065,dark))
parts.append(rod('Right thigh',(.12,0,.12),(.29,-.02,-.15),.09,dark))
parts.append(rod('Right shin',(.29,-.02,-.15),(.42,-.03,-.39),.065,dark))
parts.append(sphere('Left shoe',(-.45,-.02,-.46),(.12,.08,.06),dark,10,6))
parts.append(sphere('Right shoe',(.44,-.02,-.42),(.12,.08,.06),dark,10,6))
parts.append(box('Parachute pack',(0,.17,.49),(.32,.15,.36),wingmat,.04))
for o in parts: o.parent=person

# Initial position at the aircraft stair; fall into the darkness over the sequence.
for fr, loc, rot in [
    (1,(-4.65,-1.10,-.10),(radians(8),0,radians(-8))),
    (250,(-5.15,-1.65,-.85),(radians(18),radians(-8),radians(-15))),
    (420,(-7.0,-1.8,-2.8),(radians(38),radians(-18),radians(-8))),
    (620,(-10.2,-1.0,-6.8),(radians(62),radians(-30),radians(10))),
    (800,(-14.0,.6,-12.0),(radians(78),radians(-42),radians(18))),
    (960,(-18.0,2.0,-18.0),(radians(90),radians(-50),radians(25))),
]:
    key_location(person,fr,loc); key_rotation(person,fr,rot)
for fr, loc in [(1,(0,0,0)),(960,(5.0,0,.6))]: key_location(plane,fr,loc)

# Lights

def area(name, loc, energy, color, size, target):
    data=bpy.data.lights.new(name,'AREA'); data.energy=energy; data.color=color; data.shape='DISK'; data.size=size
    obj=bpy.data.objects.new(name,data); scene.collection.objects.link(obj); obj.location=loc
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler(); return obj
area('Cold moon key',(1,-7,10),1300,(.35,.48,1.0),9,(-2,0,0))
area('Warm cabin bounce',(-4.5,-3.5,1.5),170,(1.0,.42,.18),4,(-4,0,0))
area('Blue rim',(-8,5,5),900,(.12,.25,1.0),7,(-3,0,0))

# Camera choreography: establish aircraft, move to open stair, follow falling figure.
cam_data=bpy.data.cameras.new('Cinematic Camera'); cam=bpy.data.objects.new('Cinematic Camera',cam_data); scene.collection.objects.link(cam); scene.camera=cam
cam_data.lens=52
cam_data.dof.use_dof=True; cam_data.dof.aperture_fstop=5.6
focus=bpy.data.objects.new('Camera Aim',None); scene.collection.objects.link(focus)
track=cam.constraints.new('TRACK_TO'); track.target=focus; track.track_axis='TRACK_NEGATIVE_Z'; track.up_axis='UP_Y'
cam_keys=[
 (1,(11,-25,6),(-1,0,0)),
 (145,(7,-18,3.5),(-2,0,0)),
 (240,(-1.5,-10,1.8),(-4,-.3,-.2)),
 (330,(-7.5,-7,.2),(-5.3,-1.2,-1)),
 (430,(-10.5,-5.5,-2),(-7.2,-1.7,-3)),
 (610,(-13,-7,-4),(-10.2,-1,-6.8)),
 (790,(-16,-8,-7),(-14,.5,-12)),
 (960,(-21,-9,-11),(-18,2,-18)),
]
for fr, loc, aim in cam_keys:
    key_location(cam,fr,loc); key_location(focus,fr,aim)
cam_data.dof.focus_object=person
for obj in (cam,focus,person,plane):
    if obj.animation_data and obj.animation_data.action:
        for fc in obj.animation_data.action.fcurves:
            for kp in fc.keyframe_points: kp.interpolation='BEZIER'

# Soft glow on bright lights
scene.use_nodes=True
nodes=scene.node_tree.nodes; links=scene.node_tree.links; nodes.clear()
rl=nodes.new('CompositorNodeRLayers'); glare=nodes.new('CompositorNodeGlare'); comp=nodes.new('CompositorNodeComposite')
glare.glare_type='FOG_GLOW'; glare.quality='MEDIUM'; glare.threshold=1.4; glare.mix=-0.92
links.new(rl.outputs['Image'],glare.inputs['Image']); links.new(glare.outputs['Image'],comp.inputs['Image'])

# Start frame and render
scene.frame_set(1)
print('BLENDER_SCENE_READY: original 40-second aircraft jump animation')
print('OUTPUT_VIDEO:', VIDEO_PATH)
bpy.ops.render.render(animation=True)
print('BLENDER_RENDER_COMPLETE:', VIDEO_PATH)
