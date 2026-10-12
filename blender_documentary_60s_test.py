"""Fast, asset-first Blender documentary test.

Searches existing downloadable 3D assets (Sketchfab, Wikimedia Commons,
Poly Haven, NASA 3D), asks agy to rank candidate metadata when available,
then imports the selected assets into Blender. No aircraft/person meshes are
procedurally modeled. The default is a short 12-second low-cost preview.
"""
import bpy, os, sys, json, re, math, time, zipfile, tarfile, shutil, subprocess, urllib.request, urllib.parse, urllib.error
from pathlib import Path
from mathutils import Vector

OUT = Path(os.environ.get('OUTPUT_DIR', str(Path.cwd() / 'output'))).resolve()
ASSET_DIR = OUT / 'assets'
TOPIC = os.environ.get('TOPIC', 'D. B. Cooper: the night jump')
DURATION = max(6, min(60, int(os.environ.get('DURATION_SECONDS', '12'))))
FPS = max(8, min(24, int(os.environ.get('FPS', '12'))))
SCALE = max(20, min(100, int(os.environ.get('RESOLUTION_PERCENT', '35'))))
SKETCHFAB_TOKEN = os.environ.get('SKETCHFAB_API_TOKEN', '').strip()
AGY_MODEL = os.environ.get('AGY_MODEL', 'gemini-3.8-flash')
SUPPORTED = {'.glb', '.gltf', '.blend', '.fbx', '.obj', '.dae', '.stl', '.ply'}
UA = 'DocumentaryAssetResearch/1.0 (automated prototype; license-aware)'

OUT.mkdir(parents=True, exist_ok=True)
ASSET_DIR.mkdir(parents=True, exist_ok=True)
(OUT / 'frames').mkdir(parents=True, exist_ok=True)


def log(message):
    print('[ASSET-DOCU] ' + str(message), flush=True)


def http_json(url, headers=None, timeout=25):
    h = {'User-Agent': UA, 'Accept': 'application/json'}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', errors='replace'))


def safe_name(value):
    value = re.sub(r'[^A-Za-z0-9._-]+', '_', str(value)).strip('._')
    return (value or 'asset')[:100]


def allowed_license(label):
    s = re.sub(r'<[^>]+>', ' ', str(label or '')).lower()
    if any(x in s for x in ('noncommercial', 'non-commercial', 'no derivatives', 'no-derivatives', 'all rights reserved', 'cc by-nc', 'cc-by-nc', 'cc by-nd', 'cc-by-nd')):
        return False
    return any(x in s for x in ('cc0', 'public domain', 'cc by', 'cc attribution', 'creative commons attribution', 'nasa'))


def candidate(role, provider, title, url='', download_url='', license_name='', description='', preview='', provider_id='', file_ext=''):
    lic = re.sub(r'<[^>]+>', ' ', str(license_name or 'Unknown')).strip()[:180]
    return {
        'id': safe_name(provider + '_' + (provider_id or title)),
        'role': role, 'provider': provider, 'title': re.sub(r'<[^>]+>', ' ', str(title or 'Untitled')).strip()[:220],
        'page_url': url, 'download_url': download_url, 'license': lic,
        'license_allowed': allowed_license(lic), 'description': re.sub(r'<[^>]+>', ' ', str(description or '')).strip()[:700],
        'preview_url': preview, 'provider_id': str(provider_id or ''), 'file_ext': file_ext.lower()
    }


def role_queries(role):
    if role == 'aircraft':
        return ['Boeing 727 3D model', 'Boeing 727 aircraft model', 'airliner airplane 3D model', 'passenger jet aircraft 3D']
    return ['skydiver 3D model', 'parachutist human 3D model', 'realistic male human rigged 3D', 'human character 3D model']


def search_sketchfab(role, limit=12):
    if not SKETCHFAB_TOKEN:
        log('Sketchfab skipped: SKETCHFAB_API_TOKEN is not configured.')
        return []
    rows, seen = [], set()
    for q in role_queries(role)[:3]:
        try:
            params = urllib.parse.urlencode({'type':'models', 'q':q, 'downloadable':'true', 'count':8, 'sort_by':'-likeCount'})
            data = http_json('https://api.sketchfab.com/v3/search?' + params,
                             {'Authorization':'Token ' + SKETCHFAB_TOKEN})
            for item in data.get('results', []):
                uid = str(item.get('uid') or '')
                if not uid or uid in seen:
                    continue
                seen.add(uid)
                lic_obj = item.get('license') or {}
                lic = lic_obj.get('label') or lic_obj.get('slug') or 'Unknown'
                thumbs = ((item.get('thumbnails') or {}).get('images') or [])
                thumb = thumbs[-1].get('url','') if thumbs else ''
                c = candidate(role, 'Sketchfab', item.get('name'), item.get('viewerUrl',''), '', lic,
                              item.get('description',''), thumb, uid)
                c['likes'] = item.get('likeCount', 0)
                c['is_downloadable'] = bool(item.get('isDownloadable', True))
                # Monetized documentary use: reject unclear, NC and ND licenses.
                if c['license_allowed'] and c['is_downloadable']:
                    rows.append(c)
                if len(rows) >= limit:
                    break
        except Exception as exc:
            log('Sketchfab search failed for %r: %s' % (q, exc))
    return rows[:limit]


def search_commons(role, limit=12):
    rows, seen = [], set()
    ext_pattern = '|'.join(re.escape(x) for x in sorted(SUPPORTED))
    for q in role_queries(role)[:3]:
        try:
            params = {'action':'query','generator':'search','gsrsearch':q,'gsrnamespace':6,'gsrlimit':30,
                      'prop':'imageinfo','iiprop':'url|extmetadata','format':'json'}
            data = http_json('https://commons.wikimedia.org/w/api.php?' + urllib.parse.urlencode(params),
                             {'User-Agent':UA})
            for p in data.get('query', {}).get('pages', {}).values():
                info = (p.get('imageinfo') or [{}])[0]
                file_url = info.get('url','')
                ext = Path(urllib.parse.urlparse(file_url).path).suffix.lower()
                if ext not in SUPPORTED or file_url in seen:
                    continue
                seen.add(file_url)
                md = info.get('extmetadata') or {}
                lic = (md.get('LicenseShortName') or {}).get('value','Unknown')
                if not allowed_license(lic):
                    continue
                rows.append(candidate(role, 'Wikimedia Commons', p.get('title',''), info.get('descriptionurl',''),
                                      file_url, lic, (md.get('ImageDescription') or {}).get('value',''), '',
                                      p.get('pageid',''), ext))
                if len(rows) >= limit:
                    break
        except Exception as exc:
            log('Wikimedia search failed for %r: %s' % (q, exc))
        if len(rows) >= limit:
            break
    return rows[:limit]


def flatten_file_urls(node, path=''):
    found = []
    if isinstance(node, dict):
        url = node.get('url')
        if isinstance(url, str) and url.startswith('http'):
            context = (path + ' ' + ' '.join(str(k) for k in node.keys())).lower()
            ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
            found.append((url, ext, context))
        for k, v in node.items():
            found.extend(flatten_file_urls(v, path + '/' + str(k)))
    elif isinstance(node, list):
        for item in node:
            found.extend(flatten_file_urls(item, path))
    return found


def search_polyhaven(role, limit=10):
    try:
        data = http_json('https://api.polyhaven.com/assets?t=models')
    except Exception as exc:
        log('Poly Haven catalog failed: %s' % exc)
        return []
    terms = set(re.findall(r'[a-z0-9]+', ' '.join(role_queries(role)).lower()))
    ranked = []
    for aid, meta in data.items():
        tags = meta.get('tags') or []
        name = str(meta.get('name') or aid)
        hay = (str(aid) + ' ' + name + ' ' + ' '.join(map(str, tags))).lower()
        score = sum(1 for t in terms if len(t) > 3 and t in hay)
        # Broad relevant terms matter more than a single shared word.
        if role == 'aircraft' and any(x in hay for x in ('aircraft','airplane','plane','jet')): score += 8
        if role == 'human' and any(x in hay for x in ('human','person','man','character','skydiv')): score += 8
        if score > 0:
            ranked.append((score, aid, meta))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    rows=[]
    for score, aid, meta in ranked[:limit]:
        rows.append(candidate(role, 'Poly Haven', meta.get('name') or aid,
                              'https://polyhaven.com/a/' + aid, '', 'CC0', 'Tags: ' + ', '.join(map(str, meta.get('tags') or [])),
                              '', aid))
        rows[-1]['catalog_score'] = score
    return rows


def search_nasa(role, limit=8):
    """Lightweight discovery of directly linked NASA 3D files; pages that expose no direct model are ignored."""
    rows, seen = [], set()
    queries = role_queries(role)[:2]
    for q in queries:
        try:
            url = 'https://nasa3d.arc.nasa.gov/search?' + urllib.parse.urlencode({'q':q})
            req = urllib.request.Request(url, headers={'User-Agent':UA})
            with urllib.request.urlopen(req, timeout=20) as r: html = r.read().decode('utf-8','replace')
            links = re.findall(r'''href=["']([^"']+)["']''', html, flags=re.I)
            for href in links:
                full = urllib.parse.urljoin(url, href)
                ext = Path(urllib.parse.urlparse(full).path).suffix.lower()
                if ext not in SUPPORTED and ext not in ('.zip', '.7z', '.tar', '.gz'):
                    continue
                if full in seen: continue
                seen.add(full)
                title = Path(urllib.parse.urlparse(full).path).name or q
                rows.append(candidate(role, 'NASA 3D Resources', title, url, full, 'NASA public-domain/usage terms; verify item terms', q, '', full, ext))
                if len(rows) >= limit: break
        except Exception as exc:
            log('NASA 3D search did not return direct model links for %r: %s' % (q, exc))
        if len(rows) >= limit: break
    return rows[:limit]


def gather_candidates():
    all_rows=[]
    providers = [('Sketchfab', search_sketchfab), ('Wikimedia Commons', search_commons),
                 ('Poly Haven', search_polyhaven), ('NASA 3D Resources', search_nasa)]
    report={'topic':TOPIC, 'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'note':'Candidates are search results, not verified historical evidence. License terms must be retained and checked before publication.', 'roles':{}}
    for role in ('aircraft','human'):
        combined=[]
        for name, fn in providers:
            try:
                found=fn(role)
                log('%s / %s: %d usable candidate(s)' % (name, role, len(found)))
                combined.extend(found)
            except Exception as exc:
                log('%s provider error (%s): %s' % (name, role, exc))
        # Stable deduplication and cap the evaluation payload.
        unique=[]; seen=set()
        for c in combined:
            key=(c.get('provider'), c.get('provider_id') or c.get('download_url') or c.get('page_url'))
            if key in seen: continue
            seen.add(key); unique.append(c)
        report['roles'][role]=unique[:30]
        all_rows.extend(unique[:30])
    with open(OUT/'asset_candidates.json','w',encoding='utf-8') as f:
        json.dump(report,f,ensure_ascii=False,indent=2)
    return report


def parse_json_from_text(text):
    if not text: return None
    # Accept fenced output or other prose surrounding the first JSON object.
    m=re.search(r'\{[\s\S]*\}', text)
    if not m: return None
    try: return json.loads(m.group(0))
    except Exception: return None


def agy_rank(report):
    candidates={role: report['roles'].get(role,[]) for role in ('aircraft','human')}
    result={'method':'deterministic_metadata_fallback','selections':{},'evaluations':{},'warning':None}
    # Give agy compact metadata only. Do not claim visual inspection: thumbnails are not attached to this CLI prompt.
    if shutil.which('agy'):
        prompt = (
            'You are the asset research selector for an original minimalist cinematic night-jump documentary. '
            'Select one existing 3D asset for each role: aircraft and human skydiver. Rank ONLY candidates with license_allowed=true. '
            'Prefer relevant real 3D models, downloadable/usable formats, clear permissive license, strong title/description fit, and avoid unrelated assets. '
            'You receive metadata, not image pixels; do not claim visual inspection. Return ONLY valid JSON: '
            '{"selections":{"aircraft":"candidate_id","human":"candidate_id"},"evaluations":{"candidate_id":{"score":0.0,"reason":"short reason"}},"notes":"..."}. '
            'If no suitable candidate exists for a role, use an empty string for its selection. Candidate data: ' +
            json.dumps(candidates, ensure_ascii=False)[:24000]
        )
        try:
            cmd=['agy','--model',AGY_MODEL,'--effort','high','--dangerously-skip-permissions','-p',prompt]
            proc=subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=180)
            (OUT/'agy_asset_evaluation.log').write_text(proc.stdout or '',encoding='utf-8')
            parsed=parse_json_from_text(proc.stdout or '')
            if proc.returncode == 0 and parsed and isinstance(parsed.get('selections'),dict):
                result={'method':'agy_metadata_review','selections':parsed.get('selections',{}),
                        'evaluations':parsed.get('evaluations',{}),'notes':parsed.get('notes','')}
                log('Agy ranked candidate metadata. It was not given image pixels in this workflow.')
            else:
                result['warning']='agy ran but returned no valid selection JSON; using deterministic fallback.'
                log(result['warning'])
        except Exception as exc:
            result['warning']='agy evaluation unavailable: ' + str(exc)
            log(result['warning'])
    else:
        result['warning']='agy executable is not present on this GitHub runner; using deterministic metadata ranking. Add the existing agy setup/authentication to this workflow to enable Agy ranking.'
        log(result['warning'])
    # Validate Agy choices and fill only with license-allowed candidates.
    for role in ('aircraft','human'):
        rows=[c for c in candidates[role] if c.get('license_allowed')]
        selected_id=str(result['selections'].get(role,'') or '')
        selected=next((c for c in rows if c['id']==selected_id),None)
        if selected is None and rows:
            def rank(c):
                text=(c['title']+' '+c['description']).lower()
                role_terms = ('aircraft airplane plane jet boeing 727 airliner' if role=='aircraft' else 'skydiver parachutist human person male character rigged')
                kws=role_terms.split()
                hits=sum(1 for k in kws if k in text)
                provider_bonus={'Sketchfab':3,'Wikimedia Commons':2,'Poly Haven':1,'NASA 3D Resources':2}.get(c['provider'],0)
                format_bonus=2 if c.get('file_ext') in ('.glb','.gltf','.blend','.fbx','.obj') else 0
                return (hits+provider_bonus+format_bonus, c['title'])
            selected=sorted(rows,key=rank,reverse=True)[0]
            result['selections'][role]=selected['id']
        result.setdefault('selected_assets',{})[role]=selected
    with open(OUT/'agy_asset_evaluation.json','w',encoding='utf-8') as f:
        json.dump(result,f,ensure_ascii=False,indent=2)
    return result


def download_url_for(c):
    provider=c['provider']
    if provider=='Sketchfab':
        if not SKETCHFAB_TOKEN: raise RuntimeError('Sketchfab download requires SKETCHFAB_API_TOKEN secret.')
        data=http_json('https://api.sketchfab.com/v3/models/' + urllib.parse.quote(c['provider_id']) + '/download',
                       {'Authorization':'Token '+SKETCHFAB_TOKEN})
        for key in ('glb','gltf'):
            obj=data.get(key)
            if isinstance(obj,dict) and obj.get('url'): return obj['url']
        raise RuntimeError('Sketchfab API did not provide a downloadable GLB/GLTF archive.')
    if provider=='Poly Haven':
        files=http_json('https://api.polyhaven.com/files/' + urllib.parse.quote(c['provider_id']))
        choices=flatten_file_urls(files)
        priorities=('.glb','.gltf','.blend','.fbx','.obj','.dae','.stl','.zip')
        for ext in priorities:
            for url, actual_ext, context in choices:
                if actual_ext==ext or (ext=='.zip' and not actual_ext and 'zip' in context): return url
        raise RuntimeError('No supported downloadable model format found in Poly Haven files API.')
    if c.get('download_url'):
        return c['download_url']
    raise RuntimeError('No direct download URL for this candidate.')


def download_file(url, destination):
    req=urllib.request.Request(url, headers={'User-Agent':UA})
    with urllib.request.urlopen(req, timeout=90) as r:
        data=r.read()
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_bytes(data)
    return destination


def unpack_if_needed(path):
    dest=path.parent/(path.stem+'_unpacked')
    if path.suffix.lower()=='.zip':
        dest.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(path) as z:
            for info in z.infolist():
                target=(dest/info.filename).resolve()
                if dest.resolve() not in target.parents and target != dest.resolve(): continue
                z.extract(info,dest)
        return dest
    if path.suffix.lower() in ('.tar','.gz','.tgz') or path.name.lower().endswith(('.tar.gz','.tgz')):
        dest.mkdir(parents=True,exist_ok=True)
        with tarfile.open(path,'r:*') as t:
            root=dest.resolve()
            for member in t.getmembers():
                target=(dest/member.name).resolve()
                if root not in target.parents and target != root: continue
                t.extract(member,dest)
        return dest
    return path


def find_importable(root):
    if isinstance(root,Path) and root.is_file():
        return root if root.suffix.lower() in SUPPORTED else None
    files=[]
    for p in Path(root).rglob('*'):
        if p.is_file() and p.suffix.lower() in SUPPORTED:
            files.append(p)
    priority={'.glb':0,'.gltf':1,'.blend':2,'.fbx':3,'.obj':4,'.dae':5,'.stl':6,'.ply':7}
    files.sort(key=lambda p:(priority.get(p.suffix.lower(),99), len(p.parts), p.stat().st_size if p.exists() else 0))
    return files[0] if files else None


def download_selected(c):
    if not c: raise RuntimeError('No selected candidate for required role.')
    url=download_url_for(c)
    suffix=Path(urllib.parse.urlparse(url).path).suffix.lower()
    if suffix not in SUPPORTED and suffix not in ('.zip','.gz','.tgz','.tar'):
        # Many model providers deliver an archive through a signed URL with no suffix.
        suffix='.download'
    target=ASSET_DIR/(safe_name(c['role']+'_'+c['provider']+'_'+c['title'])+suffix)
    log('Downloading selected %s: %s' % (c['role'], c['title']))
    download_file(url,target)
    if target.suffix.lower()=='.download':
        # Detect zip payload even when signed URL has no extension.
        try:
            head=target.read_bytes()[:32]
            if zipfile.is_zipfile(target):
                renamed=target.with_suffix('.zip'); target.rename(renamed); target=renamed
            elif head.startswith(b'glTF'):
                renamed=target.with_suffix('.glb'); target.rename(renamed); target=renamed
            elif head.lstrip().startswith(b'{'):
                renamed=target.with_suffix('.gltf'); target.rename(renamed); target=renamed
            elif head.startswith(b'Kaydara FBX Binary') or head.startswith(b'; FBX'):
                renamed=target.with_suffix('.fbx'); target.rename(renamed); target=renamed
        except Exception: pass
    extracted=unpack_if_needed(target)
    model=find_importable(extracted)
    if model is None:
        raise RuntimeError('Downloaded candidate has no supported model file: '+str(target))
    return model


def import_model(path, role):
    before=set(bpy.data.objects.keys())
    ext=path.suffix.lower()
    log('Importing %s model file %s' % (role,path.name))
    if ext in ('.glb','.gltf'):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext=='.fbx':
        bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=True)
    elif ext=='.obj':
        if hasattr(bpy.ops.wm,'obj_import'): bpy.ops.wm.obj_import(filepath=str(path))
        else: bpy.ops.import_scene.obj(filepath=str(path))
    elif ext=='.dae':
        bpy.ops.wm.collada_import(filepath=str(path))
    elif ext=='.stl':
        if hasattr(bpy.ops.wm,'stl_import'): bpy.ops.wm.stl_import(filepath=str(path))
        else: bpy.ops.import_mesh.stl(filepath=str(path))
    elif ext=='.ply':
        if hasattr(bpy.ops.wm,'ply_import'): bpy.ops.wm.ply_import(filepath=str(path))
        else: raise RuntimeError('PLY import is unsupported by this Blender version.')
    elif ext=='.blend':
        with bpy.data.libraries.load(str(path), link=False) as (data_from,data_to):
            data_to.objects=[name for name in data_from.objects if name]
        for obj in data_to.objects:
            if obj: bpy.context.scene.collection.objects.link(obj)
    else:
        raise RuntimeError('Unsupported model format: '+ext)
    imported=[bpy.data.objects[n] for n in (set(bpy.data.objects.keys())-before) if n in bpy.data.objects]
    # Keep only geometry/rig objects from the imported model; ignore provider cameras/lights.
    imported=[o for o in imported if o.type in ('MESH','ARMATURE','EMPTY','CURVE','SURFACE','META','FONT')]
    meshes=[o for o in imported if o.type=='MESH']
    if not meshes:
        raise RuntimeError('Imported asset has no mesh objects; it may be an unsupported scene/rig.')
    return imported, meshes


def bounds(meshes):
    pts=[]
    for o in meshes:
        try: pts.extend([o.matrix_world @ Vector(corner) for corner in o.bound_box])
        except Exception: pass
    if not pts: raise RuntimeError('Could not calculate imported model bounds.')
    mins=Vector((min(p.x for p in pts),min(p.y for p in pts),min(p.z for p in pts)))
    maxs=Vector((max(p.x for p in pts),max(p.y for p in pts),max(p.z for p in pts)))
    return mins,maxs,maxs-mins,(mins+maxs)/2


def normalize_group(imported, meshes, role, target_size):
    mins,maxs,size,center=bounds(meshes)
    if max(size.x,size.y,size.z)<1e-5: raise RuntimeError('Model has zero-sized bounds.')
    root=bpy.data.objects.new(role.title()+' Asset Root',None); bpy.context.scene.collection.objects.link(root)
    root.empty_display_type='PLAIN_AXES'; root.location=center
    for o in imported:
        world=o.matrix_world.copy(); o.parent=root; o.matrix_world=world
    # Scale the overall model based on its longest dimension. Human should stand upright if Z is not dominant.
    if role=='human':
        dims=[size.x,size.y,size.z]
        tall_axis=max(range(3),key=lambda i:dims[i])
        if tall_axis==0: root.rotation_euler[1]=math.radians(90)
        elif tall_axis==1: root.rotation_euler[0]=math.radians(90)
    elif role=='aircraft':
        if size.y>size.x: root.rotation_euler[2]=math.radians(90)
    root.scale=(target_size/max(size),)*3
    return root


def clear_scene():
    bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes,bpy.data.curves,bpy.data.materials,bpy.data.cameras,bpy.data.lights):
        # Leave datablocks to Blender cleanup; deleting aggressively can invalidate linked imported assets.
        pass


def aim(obj, target):
    obj.rotation_euler=(Vector(target)-obj.location).to_track_quat('-Z','Y').to_euler()


def build_scene(plane_root, human_root):
    scene=bpy.context.scene
    scene.render.engine='BLENDER_EEVEE'
    scene.render.resolution_x=1280; scene.render.resolution_y=720; scene.render.resolution_percentage=SCALE
    scene.render.fps=FPS; scene.frame_start=1; scene.frame_end=DURATION*FPS
    scene.world.color=(0.001,0.002,0.008)
    try:
        scene.world.use_nodes=True
        bg=scene.world.node_tree.nodes.get('Background')
        if bg: bg.inputs['Color'].default_value=(0.001,0.003,0.012,1); bg.inputs['Strength'].default_value=0.18
    except Exception: pass
    # Minimal lighting and world: no procedural aircraft/person/cloud geometry.
    bpy.ops.object.light_add(type='AREA', location=(0,-7,7)); key=bpy.context.object
    key.name='Moonlight key'; key.data.energy=1800; key.data.shape='DISK'; key.data.size=9; key.data.color=(0.66,0.76,1.0); aim(key,(0,0,0))
    bpy.ops.object.light_add(type='AREA', location=(-7,4,1)); rim=bpy.context.object
    rim.name='Cold rim light'; rim.data.energy=1100; rim.data.size=6; rim.data.color=(0.24,0.43,1.0); aim(rim,(-4,0,0))
    bpy.ops.object.camera_add(location=(11,-21,7)); cam=bpy.context.object; cam.name='Cinematic camera'; scene.camera=cam; cam.data.lens=48
    end=DURATION*FPS
    keyframes=[(1,(11,-21,7),(-1,0,0)),(int(end*.35),(5,-17,4),(-3,0,-.3)),(int(end*.68),(-2,-13,2),(-6,-.1,-1.5)),(end,(-7,-10,0),(-8,-.1,-3.5))]
    for fr,loc,target in keyframes:
        cam.location=loc; aim(cam,target); cam.keyframe_insert(data_path='location',frame=fr); cam.keyframe_insert(data_path='rotation_euler',frame=fr)
    # Keep imported asset animation if present; animate the roots as an overall cinematic movement.
    for fr,loc in [(1,(0,0,0)),(end,(0,0,0))]:
        plane_root.location=loc; plane_root.keyframe_insert(data_path='location',frame=fr)
    start_fall=max(2,int(end*.38))
    for fr,loc,rot in [(1,(-5.5,0,-.8),(0,0,0)),(start_fall,(-5.5,0,-.8),(0,0,0)),(int(end*.7),(-6.2,0,-2.2),(math.radians(18),0,math.radians(-8))),(end,(-7.2,0,-4.2),(math.radians(38),0,math.radians(-18)))]:
        human_root.location=loc; human_root.rotation_euler=rot
        human_root.keyframe_insert(data_path='location',frame=fr); human_root.keyframe_insert(data_path='rotation_euler',frame=fr)
    for ob in scene.objects:
        if ob.animation_data and ob.animation_data.action:
            try:
                for fc in ob.animation_data.action.fcurves:
                    for kp in fc.keyframe_points: kp.interpolation='BEZIER'
            except Exception: pass
    scene.render.image_settings.file_format='PNG'; scene.render.image_settings.color_mode='RGB'
    scene.render.threads_mode='FIXED'; scene.render.threads=max(1,min(4,os.cpu_count() or 2))
    scene.render.filepath=str(OUT/'frames'/'frame_')
    try: scene.view_settings.view_transform='Standard'
    except Exception: pass
    return scene


def main():
    log('Fast asset-first scene test: %ss at %s fps, %s%% render scale.' % (DURATION,FPS,SCALE))
    log('Stage 1/5: searching multiple model sources; no procedural aircraft/person creation.')
    report=gather_candidates()
    evaluation=agy_rank(report)
    selected=evaluation.get('selected_assets',{})
    with open(OUT/'selected_assets.json','w',encoding='utf-8') as f:
        json.dump(selected,f,ensure_ascii=False,indent=2)
    missing=[role for role in ('aircraft','human') if not selected.get(role)]
    if missing:
        raise RuntimeError('No license-allowed downloadable model found for: '+', '.join(missing)+'. Add SKETCHFAB_API_TOKEN for better coverage, or inspect asset_candidates.json.')
    log('Stage 2/5: downloading selected licensed models.')
    model_paths={}
    for role in ('aircraft','human'):
        try:
            model_paths[role]=download_selected(selected[role])
            selected[role]['local_file']=str(model_paths[role])
        except Exception as exc:
            log('Selected candidate failed to download/import for %s: %s' % (role,exc))
            # Try next licensed candidate in rank order, preserving Agy choice as first attempt.
            alternatives=[c for c in report['roles'].get(role,[]) if c.get('license_allowed') and c.get('id')!=selected[role].get('id')]
            recovered=False
            for alt in alternatives[:5]:
                try:
                    model_paths[role]=download_selected(alt); selected[role]=alt; selected[role]['local_file']=str(model_paths[role]); recovered=True
                    log('Fallback model selected for %s: %s' % (role,alt['title'])); break
                except Exception as alt_exc: log('Candidate fallback failed (%s): %s' % (alt.get('title'),alt_exc))
            if not recovered: raise RuntimeError('Could not obtain a usable '+role+' model after retries.') from exc
    with open(OUT/'selected_assets.json','w',encoding='utf-8') as f: json.dump(selected,f,ensure_ascii=False,indent=2)
    log('Stage 3/5: importing existing 3D models into Blender.')
    clear_scene()
    imported_air, meshes_air=import_model(model_paths['aircraft'],'aircraft')
    plane_root=normalize_group(imported_air,meshes_air,'aircraft',12.0)
    imported_human, meshes_human=import_model(model_paths['human'],'human')
    human_root=normalize_group(imported_human,meshes_human,'human',1.7)
    log('Stage 4/5: preparing minimal night lighting and camera animation.')
    scene=build_scene(plane_root,human_root)
    plan={'topic':TOPIC,'duration_seconds':DURATION,'fps':FPS,'frames':DURATION*FPS,'render_scale_percent':SCALE,
          'asset_strategy':'download and import existing licensed 3D models; no procedural aircraft/person meshes',
          'asset_evaluation_method':evaluation.get('method'),'selected_assets':selected,
          'limitations':['Agy evaluation is metadata-based in this workflow; image-pixel inspection is not claimed.',
                         'Model orientation, rigging and scale vary by provider and may require a targeted correction.',
                         'Search candidates are not historical evidence; verify attribution and exact license before publication.']}
    with open(OUT/'scene_plan.json','w',encoding='utf-8') as f: json.dump(plan,f,ensure_ascii=False,indent=2)
    log('Stage 5/5: rendering %d frames.' % (DURATION*FPS))
    for frame in range(1,DURATION*FPS+1):
        scene.frame_set(frame)
        scene.render.filepath=str(OUT/'frames'/('frame_%04d' % frame))
        bpy.ops.render.render(write_still=True)
        if frame%max(FPS*2,1)==0: log('Rendered %d/%d frames' % (frame,DURATION*FPS))
    log('Render complete; workflow will encode MP4 and upload candidate/evaluation reports.')


if __name__=='__main__':
    try:
        main()
    except Exception as exc:
        log('FATAL: '+str(exc))
        with open(OUT/'asset_pipeline_error.txt','w',encoding='utf-8') as f: f.write(str(exc)+'\n')
        raise
