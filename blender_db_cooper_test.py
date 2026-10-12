import bpy, math, os, json, urllib.request, urllib.parse
from mathutils import Vector

OUT = os.environ.get('OUTPUT_DIR', os.path.abspath('output'))
TOPIC = os.environ.get('TOPIC', 'D. B. Cooper: the night jump')
SCALE = int(os.environ.get('RESOLUTION_PERCENT', '50'))
os.makedirs(OUT, exist_ok=True)
os.makedirs(os.path.join(OUT, 'frames'), exist_ok=True)

def log(s): print('[DOCU-TEST] ' + str(s), flush=True)

def search_commons(query, limit=4):
    params = {'action':'query','generator':'search','gsrsearch':query,'gsrnamespace':6,'gsrlimit':limit,
              'prop':'imageinfo','iiprop':'url|extmetadata','format':'json'}
    url = 'https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'User-Agent':'BlenderDocumentaryProofOfConcept/1.0 (reference research)'})
    with urllib.request.urlopen(req, timeout=20) as r: data = json.loads(r.read().decode('utf-8'))
    result=[]
    for p in data.get('query',{}).get('pages',{}).values():
        ii=(p.get('imageinfo') or [{}])[0]; md=ii.get('extmetadata') or {}
        result.append({'title':p.get('title',''),'description_page':ii.get('descriptionurl',''),
                       'file_url':ii.get('url',''),'license':(md.get('LicenseShortName') or {}).get('value',''),
                       'artist':(md.get('Artist') or {}).get('value','')})
    return result

def research():
    # Reference search only. Candidate results are not treated as verified historical evidence.
    report={'topic':TOPIC,'warning':'Search candidates only; verify historical relevance and license before publication.','queries':[]}
    for q in ['Boeing 727 aircraft','Boeing 727 rear stairs','D. B. Cooper skyjacking','night clouds aircraft']:
        try:
            rows=search_commons(q)
            report['queries'].append({'query':q,'results':rows})
            log('Commons reference search: %s -> %d candidates' % (q,len(rows)))
        except Exception as e:
            report['queries'].append({'query':q,'error':str(e),'results':[]})
            log('Reference search failed (%s): %s' % (q,e))
    with open(os.path.join(OUT,'research_candidates.json'),'w',encoding='utf-8') as f: json.dump(report,f,ensure_ascii=False,indent=2)
    return report

def material(name, color, metallic=0, rough=0.6, emission=None):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF'); bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Metallic'].default_value=metallic; bs.inputs['Roughness'].default_value=rough
    if emission:
        key='Emission Color' if 'Emission Color' in bs.inputs else ('Emission' if 'Emission' in bs.inputs else None)
        if key: bs.inputs[key].default_value=(*emission,1)
        if 'Emission Strength' in bs.inputs: bs.inputs['Emission Strength'].default_value=0.5
    return m

def applymat(o,m): o.data.materials.append(m); return o

def cube(name, loc, dims, m, bevel=0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc); o=bpy.context.object; o.name=name; o.dimensions=dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        b=o.modifiers.new('Soft edges','BEVEL'); b.width=bevel; b.segments=2
        # Avoid Weighted Normal modifier here: Blender 3.0.x emits an Auto Smooth
        # warning for these procedural meshes. Bevel + flat face normals are enough
        # for this lightweight prototype and work across Blender versions.
    return applymat(o,m)

def sphere(name, loc, scale, m, seg=16, rings=10):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings, location=loc); o=bpy.context.object
    o.name=name; o.scale=scale; bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.shade_smooth(); return applymat(o,m)

def rod(name,a,b,r,m):
    a,b=Vector(a),Vector(b); d=b-a
    bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=r, depth=d.length, location=(a+b)/2)
    o=bpy.context.object; o.name=name; o.rotation_mode='QUATERNION'; o.rotation_quaternion=d.to_track_quat('Z','Y')
    return applymat(o,m)

def aim(o,target): o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()

def add_aircraft(aluminum, wingmat, dark):
    # Stylized 727-like silhouette: a deliberate stand-in, not a scale-accurate aircraft model.
    sphere('Fuselage',(0,0,0),(6.2,.68,.72),aluminum,28,14)
    sphere('Nose',(5.7,0,.02),(.95,.53,.5),aluminum,20,10)
    cube('Main wings',(.1,0,-.04),(2.6,8.2,.14),wingmat,.06)
    cube('Tailplane',(-4.5,0,.24),(1.25,3,.12),wingmat,.04)
    fin=cube('Tail fin',(-4.7,0,.83),(.95,.14,1.65),wingmat,.04); fin.rotation_euler[1]=math.radians(-8)
    for y in (-.4,.4): sphere('Rear engine',(-4.35,y,.05),(.92,.2,.23),dark,14,8)
    sphere('Center engine',(-5,0,.23),(.8,.23,.23),dark,14,8)
    cube('Rear door',(-5.8,0,-.3),(.18,.52,.42),dark,.02)
    for i in range(5): cube('Airstair step',(-5.9-i*.2,0,-.52-i*.12),(.3,.65,.05),aluminum,.01)
    for y in (-.3,.3): rod('Stair rail',(-5.7,y,-.4),(-6.8,y,-1.08),.02,aluminum)
    for i in range(12): sphere('Cabin window',(3.8-i*.64,-.65,.12),(.09,.025,.055),dark,8,6)

def add_person(suit):
    # Low-detail silhouette used to test timing, camera, lighting and animation pipeline.
    sphere('Person head',(-6.35,-.02,-.68),(.17,.15,.19),suit)
    torso=sphere('Person torso',(-6.3,-.02,-1.0),(.21,.15,.31),suit); torso.rotation_euler[1]=math.radians(-20)
    rod('Person left leg',(-6.3,-.1,-1.2),(-6.58,-.13,-1.5),.065,suit)
    rod('Person right leg',(-6.3,.1,-1.2),(-6.08,.12,-1.48),.065,suit)
    rod('Person left arm',(-6.2,-.13,-.9),(-6.48,-.23,-1.1),.05,suit)
    rod('Person right arm',(-6.2,.13,-.9),(-6.48,.23,-1.0),.05,suit)

def add_clouds(cloud):
    for i in range(28):
        x=-15+(i%8)*4; y=(-1 if i%2 else 1)*(5+(i%4)*1.6); z=-3-(i%5)*1.15; s=.7+(i%3)*.3
        sphere('Cloud puff',(x,y,z),(s*1.7,s,s*.6),cloud,10,6)

def add_title(text, loc, size, m):
    c=bpy.data.curves.new('Title type','FONT'); c.body=text; c.size=size; c.extrude=.001
    o=bpy.data.objects.new('Title: '+text,c); bpy.context.collection.objects.link(o); o.location=loc
    o.rotation_euler=(math.radians(90),0,0); c.materials.append(m); return o

def setup():
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene
    try: scene.render.engine='BLENDER_EEVEE_NEXT'
    except: scene.render.engine='BLENDER_EEVEE'
    scene.render.resolution_x=1280; scene.render.resolution_y=720; scene.render.resolution_percentage=SCALE
    scene.render.fps=24; scene.frame_start=1; scene.frame_end=1440
    scene.world.color=(.003,.005,.012)
    # Select a color transform actually supported by the installed Blender build.
    # Ubuntu 22.04 apt repositories may provide Blender 3.0.1 (Film ic, not AgX).
    try:
        prop = scene.view_settings.bl_rna.properties.get('view_transform')
        available = {item.identifier for item in prop.enum_items} if prop else set()
        for candidate in ('AgX', 'Filmic', 'Standard'):
            if candidate in available:
                scene.view_settings.view_transform = candidate
                break
    except Exception as exc:
        log('Color management fallback: %s' % exc)
    aluminum=material('Cold aircraft aluminum',(.3,.34,.4),.65,.32)
    wingmat=material('Dark wing metal',(.09,.12,.17),.5,.42)
    dark=material('Deep shadow',(.008,.012,.02),0,.8)
    suit=material('Dark suit',(.018,.023,.035),0,.9)
    cloud=material('Moonlit cloud',(.12,.16,.23),0,1)
    white=material('Title ivory',(.75,.79,.85),0,.4,(.3,.34,.42))
    amber=material('Muted amber',(.65,.22,.06),.1,.5,(.3,.07,.01))
    add_aircraft(aluminum,wingmat,dark); add_person(suit); add_clouds(cloud)
    bpy.ops.object.light_add(type='AREA', location=(0,-5,6)); key=bpy.context.object; key.name='Moon key'; key.data.energy=1600; key.data.shape='DISK'; key.data.size=8; aim(key,(0,0,0))
    bpy.ops.object.light_add(type='AREA', location=(-7,3,1)); rim=bpy.context.object; rim.name='Blue rim'; rim.data.energy=900; rim.data.color=(.3,.43,1); rim.data.size=5; aim(rim,(-5,0,0))
    bpy.ops.object.camera_add(location=(10,-19,7)); cam=bpy.context.object; scene.camera=cam; cam.data.lens=48
    for fr,loc,target in [(1,(10,-19,7),(-1,0,-.4)),(480,(4,-17,4),(-3,0,-.7)),(960,(-4,-13,2),(-7,-.1,-2)),(1440,(-9,-10,0),(-9,-.1,-5))]:
        cam.location=loc; aim(cam,target); cam.keyframe_insert(data_path='location',frame=fr); cam.keyframe_insert(data_path='rotation_euler',frame=fr)
    # Animate the six person parts as a coherent falling group using a shared parent empty.
    bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0,0,0)); parent=bpy.context.object; parent.name='Falling figure motion'
    for o in list(scene.objects):
        if o.name.startswith('Person ') or o.name=='Person head' or o.name=='Person torso':
            world=o.matrix_world.copy(); o.parent=parent; o.matrix_world=world
    for fr,loc,rot in [(1,(0,0,0),(0,0,0)),(360,(-.2,0,-.4),(math.radians(5),0,math.radians(-4))),(840,(-1.0,0,-2.5),(math.radians(22),0,math.radians(-12))),(1440,(-2.3,0,-5.2),(math.radians(45),0,math.radians(-20)))]:
        parent.location=loc; parent.rotation_euler=rot; parent.keyframe_insert(data_path='location',frame=fr); parent.keyframe_insert(data_path='rotation_euler',frame=fr)
    title=add_title('THE NIGHT JUMP',(-2.3,-6.9,2.2),.42,white)
    for fr,sc in [(1,(.001,)*3),(80,(1,)*3),(260,(1,)*3),(340,(.001,)*3)]: title.scale=sc; title.keyframe_insert(data_path='scale',frame=fr)
    cube('Amber accent line',(-2,-6.8,1.65),(1.2,.025,.025),amber,.005)
    for ob in scene.objects:
        if ob.animation_data and ob.animation_data.action:
            for fc in ob.animation_data.action.fcurves:
                for kp in fc.keyframe_points: kp.interpolation='BEZIER'
    scene.render.image_settings.file_format='PNG'; scene.render.image_settings.color_mode='RGB'
    scene.render.threads_mode='FIXED'; scene.render.threads=max(1,min(4,os.cpu_count() or 2))
    scene.render.filepath=os.path.join(OUT,'frames','frame_')
    try: scene.render.use_motion_blur=True
    except: pass
    return scene

def main():
    log('Topic: '+TOPIC)
    log('Stage 1/4: research/reference candidate search')
    research()
    log('Stage 2/4: generate scene plan and procedural stand-in assets')
    scene=setup()
    plan={'topic':TOPIC,'duration_seconds':60,'fps':24,'frames':1440,
          'asset_strategy':'procedural placeholders in this proof-of-concept; no downloaded 3D model is used yet',
          'planned_assets':['727-like aircraft','human silhouette','night cloud field'],
          'review_gates':['research candidate report saved','frames rendered','MP4 encoded','contact sheet available for human/vision review'],
          'limitations':['Not a historically accurate aircraft model','Search results are candidates, not verified facts','No automatic 3D model provider/OAuth integration in this first smoke test']}
    with open(os.path.join(OUT,'scene_plan.json'),'w',encoding='utf-8') as f: json.dump(plan,f,ensure_ascii=False,indent=2)
    log('Stage 3/4: render 1440 frames at %s%% resolution' % SCALE)
    for frame in range(1,1441):
        scene.frame_set(frame); scene.render.filepath=os.path.join(OUT,'frames','frame_%04d' % frame)
        bpy.ops.render.render(write_still=True)
        if frame%120==0: log('Rendered %d/1440 frames' % frame)
    log('Stage 4/4: render complete; GitHub Actions will encode MP4')

if __name__=='__main__': main()
