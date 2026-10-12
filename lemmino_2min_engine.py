#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LEMMINO INVESTIGATIVE BENCHMARK ENGINE (V28.5 - AGY FIXED WITHOUT --effort)
"""

import os
import sys
import json
import math
import shutil
import subprocess
import zipfile
import base64
import re
from pathlib import Path
import requests

sys.stdout.reconfigure(line_buffering=True)

from google import genai
from google.genai import types

# =============================================================================
# 1. الإعدادات والمسارات
# =============================================================================
BASE_DIR = Path("./output_benchmark").resolve()
SHUTTLE_DIR = (BASE_DIR / "workspace").resolve()
FINAL_VIDEO = (BASE_DIR / "lemmino_2min_benchmark.mp4").resolve()

TARGET_W, TARGET_H, FPS = 1920, 1080, 30

raw_gemini_keys = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY") or ""
GEMINI_KEYS = list(dict.fromkeys([k.strip() for k in re.split(r"[,;\n]+", raw_gemini_keys) if k.strip()]))
GEMINI_KEY = GEMINI_KEYS[0] if GEMINI_KEYS else ""

SKETCHFAB_KEY = os.environ.get("SKETCHFAB_API_KEY", "").strip()
OPENTOPO_KEY = os.environ.get("OPENTOPOGRAPHY_API_KEY", "").strip()

AGY_SCRIPT_MODEL = "gemini-3.1-pro"
TTS_MODEL = "gemini-3.8-flash-tts"
TTS_VOICE = "Charon"

if BASE_DIR.exists():
    shutil.rmtree(BASE_DIR, ignore_errors=True)
SHUTTLE_DIR.mkdir(parents=True, exist_ok=True)

def log_print(msg):
    print(msg, flush=True)

def run_cmd(cmd, desc=""):
    log_print(f"🎬 [تنفيذ]: {desc}...")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        log_print(f"⚠️ تنبيه ({desc}): {res.stderr[-400:]}")
    return res

def extract_json(text):
    if not text: return None
    text = re.sub(r"```json\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"```\s*$", "", text)
    try: return json.loads(text)
    except: pass
    match = re.search(r"\{[\s\S]*\}|\[[\s\S]*\]", text)
    if match:
        try: return json.loads(match.group(0))
        except: pass
    return None

# =============================================================================
# 2. استدعاء أداة AGY الأصلية (تم حذف --effort لتوافق gemini-3.1-pro)
# =============================================================================
def agy_generate_script():
    log_print("🧠 [AGY] استدعاء أداة AGY لصياغة السيناريو الاستقصائي...")
    prompt = """You are an elite investigative documentary director in the exact style of LEMMINO.
Topic: The Mystery of D.B. Cooper.
Generate a broadcast script in Arabic for narration, and specific forensic details for on-screen graphics.

Return ONLY valid JSON:
{
  "narration": "في الرابع والعشرين من نوفمبر عام ألف وتسعمائة وواحد وسبعين، استقل دان كوبر طائرة البوينغ سبعمائة وسبعة وعشرين من بورتلاند. بعد تهديده بوجود قنبلة، طالب بمائتي ألف دولار وأربع مظلات. في سماء واشنطن الممطرة، فُتح الدرج الخلفي وقفز كوبر في ظلام دامس نحو المجهول، تاركاً وراءه اللغز الأكبر في تاريخ الطيران الأمريكي.",
  "scene3_evidence": {
    "title": "EVIDENCE ITEM #01 - PASSENGER MANIFEST",
    "passenger": "DAN COOPER",
    "seat": "18C (AFT SECTION - BOEING 727)",
    "route": "PORTLAND INTL TO SEATTLE-TACOMA",
    "ransom": "$200,000 CASH (10,000 x $20 BILLS)"
  },
  "scene4_suspect": {
    "name": "ROBERT W. RACKSTRAW",
    "tag": "PRIMARY SUSPECT - FBI NORJAK DOSSIER",
    "point1": "Decorated Army Paratrooper & Pilot",
    "point2": "Demolition & Explosives Specialist",
    "point3": "Discharged 5 months prior to hijacking",
    "point4": "Refused to confirm or deny identity"
  }
}"""
    agy_bin = shutil.which("agy") or os.path.expanduser("~/.local/bin/agy")
    
    env_vars = os.environ.copy()
    env_vars["SSH_CONNECTION"] = "127.0.0.1 0 127.0.0.1 22"
    env_vars["AGY_OAUTH_TOKEN"] = os.environ.get("AGY_CREDENTIALS", "")

    # تم حذف --effort لتوافق gemini-3.1-pro بنجاح
    cmd = [agy_bin, "--model", AGY_SCRIPT_MODEL, "--dangerously-skip-permissions", "-p", prompt]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120, env=env_vars)
        data = extract_json(res.stdout)
        if data and "narration" in data:
            log_print("✅ [AGY] تم توليد السيناريو بنجاح عبر Antigravity CLI.")
            return data
        else:
            log_print(f"⚠️ تفاصيل AGY: {res.stderr[:250]}")
    except Exception as e:
        log_print(f"⚠️ خطأ أثناء تشغيل agy ({e})")

    return {
        "narration": "في الرابع والعشرين من نوفمبر عام ألف وتسعمائة وواحد وسبعين، استقل دان كوبر طائرة البوينغ سبعمائة وسبعة وعشرين من بورتلاند. بعد تهديده بوجود قنبلة، طالب بمائتي ألف دولار وأربع مظلات. في سماء واشنطن الممطرة، فُتح الدرج الخلفي وقفز كوبر في ظلام دامس نحو المجهول، تاركاً وراءه اللغز الأكبر في تاريخ الطيران الأمريكي.",
        "scene3_evidence": {
            "title": "EVIDENCE ITEM #01 - PASSENGER MANIFEST",
            "passenger": "DAN COOPER",
            "seat": "18C (AFT SECTION - BOEING 727)",
            "route": "PORTLAND INTL TO SEATTLE-TACOMA",
            "ransom": "$200,000 CASH (10,000 x $20 BILLS)"
        },
        "scene4_suspect": {
            "name": "ROBERT W. RACKSTRAW",
            "tag": "PRIMARY SUSPECT - FBI NORJAK DOSSIER",
            "point1": "Decorated Army Paratrooper & Pilot",
            "point2": "Demolition & Explosives Specialist",
            "point3": "Discharged 5 months prior to hijacking",
            "point4": "Refused to confirm or deny identity"
        }
    }

STORY_DATA = agy_generate_script()

# =============================================================================
# 3. GEMINI 3.8 FLASH TTS ENGINE
# =============================================================================
master_narration_wav = SHUTTLE_DIR / "narration_master.wav"
has_voice = False

if GEMINI_KEY:
    try:
        log_print(f"🎙️ [Gemini TTS] توليد التعليق الصوتي بنموذج {TTS_MODEL} بصوت {TTS_VOICE}...")
        client = genai.Client(api_key=GEMINI_KEY)
        voice_instruction = (
            "[INSTRUCTION: Solemn, emotionally resonant Arabic investigative documentary narrator. "
            "Read naturally without naming chapter titles.]\n\n"
        )
        response = client.models.generate_content(
            model=TTS_MODEL,
            contents=voice_instruction + STORY_DATA["narration"],
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=TTS_VOICE)
                    )
                )
            )
        )
        data = next((p.inline_data.data for p in response.candidates[0].content.parts if getattr(p, "inline_data", None)), None)
        if data:
            raw_audio = base64.b64decode(data) if isinstance(data, str) else bytes(data)
            temp_pcm = SHUTTLE_DIR / "temp.pcm"
            temp_pcm.write_bytes(raw_audio)
            run_cmd(["ffmpeg", "-y", "-f", "s16le", "-ar", "24000", "-ac", "1", "-i", str(temp_pcm),
                     "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(master_narration_wav)], "تحويل الصوت الماستر")
            temp_pcm.unlink(missing_ok=True)
            has_voice = master_narration_wav.exists() and master_narration_wav.stat().st_size > 1024
            if has_voice:
                log_print("✅ [Gemini TTS] تم توليد الصوت الماستر بنجاح.")
    except Exception as e:
        log_print(f"⚠️ خطأ في توليد صوت Gemini ({e})")

# =============================================================================
# 4. تنزيل الأصول (Sketchfab + OpenTopography)
# =============================================================================
def fetch_sketchfab_model(query, output_dir, tag_name):
    if not SKETCHFAB_KEY: return None
    try:
        log_print(f"🔍 [Sketchfab] البحث عن مجسم: '{query}'...")
        headers = {"Authorization": f"Token {SKETCHFAB_KEY}"}
        search_url = f"https://api.sketchfab.com/v3/models?q={query}&downloadable=true&licenses=by,by-nc,cc0&sort_by=-likeCount"
        r = requests.get(search_url, headers=headers, timeout=15)
        results = r.json().get("results", [])
        if not results: return None
        uid = results[0]["uid"]
        d_res = requests.get(f"https://api.sketchfab.com/v3/models/{uid}/download", headers=headers, timeout=15)
        download_link = d_res.json().get("gltf", {}).get("url")
        if not download_link: return None

        zip_path = output_dir / f"{tag_name}.zip"
        with requests.get(download_link, stream=True, timeout=30) as dl:
            with open(zip_path, "wb") as f:
                for chunk in dl.iter_content(chunk_size=1024*256): f.write(chunk)
        extract_dir = output_dir / tag_name
        with zipfile.ZipFile(zip_path, 'r') as zip_ref: zip_ref.extractall(extract_dir)

        for p in extract_dir.rglob("*.gltf"): return str(p.resolve())
        for p in extract_dir.rglob("*.glb"): return str(p.resolve())
    except: pass
    return None

def fetch_opentopography_dem(output_dir):
    tif_path = output_dir / "terrain_washington.tif"
    if not OPENTOPO_KEY: return None
    try:
        log_print("🗺️ [OpenTopography] تنزيل خريطة الارتفاعات الرقمية من ناسا...")
        params = {
            "demtype": "SRTMGL3", "south": "45.85", "north": "46.10",
            "west": "-122.65", "east": "-122.30", "outputFormat": "GTiff",
            "API_Key": OPENTOPO_KEY
        }
        res = requests.get("https://portal.opentopography.org/API/globaldem", params=params, timeout=20)
        if res.status_code == 200 and len(res.content) > 5000:
            tif_path.write_bytes(res.content)
            return str(tif_path.resolve())
    except: pass
    return None

models_dir = SHUTTLE_DIR / "models"
models_dir.mkdir(parents=True, exist_ok=True)
jumper_model = fetch_sketchfab_model("parachute", models_dir, "jumper")
plane_model = fetch_sketchfab_model("boeing 727", models_dir, "plane")
terrain_dem = fetch_opentopography_dem(models_dir)

# =============================================================================
# 5. تصيير بلندر بمحرك التظليل السحابي
# =============================================================================
raw_shot1_prefix = (SHUTTLE_DIR / "shot1_output").resolve()
raw_shot2_prefix = (SHUTTLE_DIR / "shot2_output").resolve()

shot1_py = SHUTTLE_DIR / "shot1.py"
shot1_py.write_text(f"""
import bpy, math

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

scene = bpy.context.scene
scene.render.fps = {FPS}
scene.frame_start, scene.frame_end = 1, {FPS * 30}

mat_red = bpy.data.materials.new("LemminoRed")
mat_red.diffuse_color = (0.85, 0.02, 0.05, 1.0)
mat_red.use_nodes = True
if mat_red.node_tree:
    mat_red.node_tree.nodes.clear()
    emis = mat_red.node_tree.nodes.new('ShaderNodeEmission')
    emis.inputs['Color'].default_value = (0.85, 0.02, 0.05, 1.0)
    out = mat_red.node_tree.nodes.new('ShaderNodeOutputMaterial')
    mat_red.node_tree.links.new(emis.outputs['Emission'], out.inputs['Surface'])

jumper_path = {repr(jumper_model)}
if jumper_path and bpy.path.exists(jumper_path):
    bpy.ops.import_scene.gltf(filepath=jumper_path)
    jumper = bpy.context.selected_objects[0]
    jumper.location = (0, 0, 5)
    max_d = max(jumper.dimensions) if max(jumper.dimensions) > 0 else 1.0
    jumper.scale = [1.8 / max_d] * 3
    jumper.data.materials.clear()
    jumper.data.materials.append(mat_red)
else:
    bpy.ops.mesh.primitive_cylinder_add(radius=0.4, depth=1.6, location=(0, 0, 5))
    jumper = bpy.context.active_object
    jumper.data.materials.append(mat_red)
    bpy.ops.mesh.primitive_cube_add(size=0.6, location=(0, -0.3, 5.2))
    pack = bpy.context.active_object
    pack.data.materials.append(mat_red)
    pack.parent = jumper

jumper.keyframe_insert(data_path="location", frame=1)
jumper.location.z = -18
jumper.keyframe_insert(data_path="location", frame={FPS * 30})

jumper.rotation_euler = (0, 0, 0)
jumper.keyframe_insert(data_path="rotation_euler", frame=1)
jumper.rotation_euler = (math.radians(720), math.radians(240), math.radians(180))
jumper.keyframe_insert(data_path="rotation_euler", frame={FPS * 30})

cam_data = bpy.data.cameras.new("Cam1")
cam_data.lens = 32
cam = bpy.data.objects.new("Camera1", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (0, -5.5, 6.5)
cam.rotation_euler = (math.radians(70), 0, 0)
cam.keyframe_insert(data_path="location", frame=1)
cam.location.z = -16
cam.keyframe_insert(data_path="location", frame={FPS * 30})

scene.render.resolution_x, scene.render.resolution_y = {TARGET_W}, {TARGET_H}
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format, scene.render.ffmpeg.codec = 'MPEG4', 'H264'
scene.render.filepath = {repr(str(raw_shot1_prefix))}
""")

shot2_py = SHUTTLE_DIR / "shot2.py"
shot2_py.write_text(f"""
import bpy, math

for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)

scene = bpy.context.scene
scene.render.fps = {FPS}
scene.frame_start, scene.frame_end = 1, {FPS * 30}

mat_plane = bpy.data.materials.new("PlaneWhite")
mat_plane.diffuse_color = (1.0, 1.0, 1.0, 1.0)

bpy.ops.mesh.primitive_grid_add(x_subdivisions=50, y_subdivisions=50, size=35, location=(0, 0, 0))
terrain = bpy.context.active_object

disp = terrain.modifiers.new(name="Mountains", type='DISPLACE')
dem_file = {repr(terrain_dem)}
if dem_file and bpy.path.exists(dem_file):
    tex = bpy.data.textures.new("DEM_Tex", type='IMAGE')
    img = bpy.data.images.load(dem_file)
    tex.image = img
    disp.texture = tex
    disp.strength = 4.5
else:
    tex = bpy.data.textures.new("Cloud_Tex", type='CLOUDS')
    tex.noise_scale = 1.5
    disp.texture = tex
    disp.strength = 3.5

plane_file = {repr(plane_model)}
if plane_file and bpy.path.exists(plane_file):
    bpy.ops.import_scene.gltf(filepath=plane_file)
    plane = bpy.context.selected_objects[0]
    max_p = max(plane.dimensions) if max(plane.dimensions) > 0 else 1.0
    plane.scale = [2.2 / max_p] * 3
else:
    bpy.ops.mesh.primitive_cone_add(radius1=0.7, depth=2.8, location=(0, -14, 5.5))
    plane = bpy.context.active_object
    plane.rotation_euler = (math.radians(-90), 0, 0)
plane.data.materials.append(mat_plane)

plane.keyframe_insert(data_path="location", frame=1)
plane.location.y = 14
plane.keyframe_insert(data_path="location", frame={FPS * 30})

cam_data = bpy.data.cameras.new("Cam2")
cam_data.lens = 45
cam = bpy.data.objects.new("Camera2", cam_data)
scene.collection.objects.link(cam)
scene.camera = cam
cam.location = (14, -20, 16)
cam.rotation_euler = (math.radians(52), 0, math.radians(35))
cam.keyframe_insert(data_path="location", frame=1)
cam.location.y = -8
cam.keyframe_insert(data_path="location", frame={FPS * 30})

scene.render.resolution_x, scene.render.resolution_y = {TARGET_W}, {TARGET_H}
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format, scene.render.ffmpeg.codec = 'MPEG4', 'H264'
scene.render.filepath = {repr(str(raw_shot2_prefix))}
""")

run_cmd(["blender", "-b", "-P", str(shot1_py), "-a"], "رندرة المشهد 1 عبر بلندر")
run_cmd(["blender", "-b", "-P", str(shot2_py), "-a"], "رندرة المشهد 2 عبر بلندر")

def resolve_blender_video(prefix_name, target_filename):
    target_path = (SHUTTLE_DIR / target_filename).resolve()
    matches = list(SHUTTLE_DIR.glob(f"*{prefix_name}*.mp4"))
    if not matches:
        matches = list(BASE_DIR.glob(f"*{prefix_name}*.mp4")) + list(Path(".").glob(f"*{prefix_name}*.mp4"))
    
    if matches:
        matches.sort(key=lambda p: p.stat().st_size, reverse=True)
        shutil.move(str(matches[0]), str(target_path))
        log_print(f"✅ تم تأكيد ملف بلندر: {target_path.name}")
        return target_path
    
    log_print(f"⚠️ إنشاء بديل فوري لـ {target_filename}...")
    run_cmd([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", f"color=c=0x08080c:s={TARGET_W}x{TARGET_H}:d=30:r={FPS}",
        "-vf", "noise=alls=15:allf=t+u,vignette=PI/4",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(target_path)
    ], f"بديل {target_filename}")
    return target_path

out_shot1 = resolve_blender_video("shot1", "shot1_parachute.mp4")
out_shot2 = resolve_blender_video("shot2", "shot2_radar.mp4")

# =============================================================================
# 6. موشن جرافيك الأدلة والمشتبه به (المشاهد 3 و 4)
# =============================================================================
ev = STORY_DATA["scene3_evidence"]
shot3_mp4 = (SHUTTLE_DIR / "shot3_evidence.mp4").resolve()
vf_shot3 = (
    f"color=c=0x090B0E:s={TARGET_W}x{TARGET_H}:d=30:r={FPS},"
    f"drawbox=x=420:y=160:w=1080:h=760:color=0x13161F:t=fill,"
    f"drawbox=x=420:y=160:w=1080:h=760:color=white@0.15:t=2,"
    f"drawtext=text='{ev['title']}':x=470:y=220:fontsize=28:fontcolor=0xC47A1A,"
    f"drawtext=text='NAME    : {ev['passenger']}':x=470:y=320:fontsize=48:fontcolor=white,"
    f"drawtext=text='SEAT    : {ev['seat']}':x=470:y=410:fontsize=36:fontcolor=0xBBBBBB,"
    f"drawtext=text='ROUTING : {ev['route']}':x=470:y=480:fontsize=36:fontcolor=0xBBBBBB,"
    f"drawtext=text='RANSOM  : {ev['ransom']}':x=470:y=550:fontsize=36:fontcolor=0xBBBBBB,"
    f"drawbox=x=450:y=300:w=1020:h=85:color=0xD90429@0.35:t=3,"
    f"noise=alls=10:allf=t+u,vignette=PI/4"
)
run_cmd(["ffmpeg", "-y", "-f", "lavfi", "-i", vf_shot3, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(shot3_mp4)], "المشهد 3: وثيقة الأدلة")

sp = STORY_DATA["scene4_suspect"]
shot4_mp4 = (SHUTTLE_DIR / "shot4_dossier.mp4").resolve()
vf_shot4 = (
    f"color=c=0x07080B:s={TARGET_W}x{TARGET_H}:d=30:r={FPS},"
    f"drawbox=x=180:y=140:w=480:h=640:color=0x11131A:t=fill,"
    f"drawbox=x=180:y=140:w=480:h=640:color=0xD90429:t=4,"
    f"drawtext=text='SUSPECT: {sp['name']}':x=720:y=190:fontsize=46:fontcolor=white,"
    f"drawtext=text='{sp['tag']}':x=720:y=255:fontsize=24:fontcolor=0xD90429,"
    f"drawtext=text='- {sp['point1']}':x=720:y=340:fontsize=32:fontcolor=0xCCCCCC,"
    f"drawtext=text='- {sp['point2']}':x=720:y=410:fontsize=32:fontcolor=0xCCCCCC,"
    f"drawtext=text='- {sp['point3']}':x=720:y=480:fontsize=32:fontcolor=0xCCCCCC,"
    f"drawtext=text='- {sp['point4']}':x=720:y=550:fontsize=32:fontcolor=0xC47A1A,"
    f"drawbox=x=710:y=620:w=1030:h=2:color=white@0.2:t=fill,"
    f"drawtext=text='THE SEARCH FOR D.B. COOPER':x=720:y=660:fontsize=38:fontcolor=white,"
    f"drawtext=text='CASE CLOSED UNSOLVED - JULY 2016':x=720:y=720:fontsize=26:fontcolor=0x777777,"
    f"noise=alls=12:allf=t+u,vignette=PI/3"
)
run_cmd(["ffmpeg", "-y", "-f", "lavfi", "-i", vf_shot4, "-c:v", "libx264", "-pix_fmt", "yuv420p", str(shot4_mp4)], "المشهد 4: ملف المشتبه به")

# =============================================================================
# 7. الصوت والتجميع النهائي
# =============================================================================
ambient_audio = (SHUTTLE_DIR / "ambient.wav").resolve()
run_cmd([
    "ffmpeg", "-y",
    "-f", "lavfi", "-i", "sine=frequency=52:duration=120,volume=1.2",
    "-f", "lavfi", "-i", "anoisesrc=color=pink:duration=120,lowpass=f=380,volume=0.35",
    "-filter_complex", "[0:a][1:a]amix=inputs=2:duration=longest[aout]",
    "-map", "[aout]", "-c:a", "pcm_s16le", str(ambient_audio)
], "توليد الموسيقى التصويرية")

final_audio = (SHUTTLE_DIR / "final_soundtrack.wav").resolve()
if has_voice and master_narration_wav.exists():
    run_cmd([
        "ffmpeg", "-y", "-i", str(ambient_audio), "-i", str(master_narration_wav),
        "-filter_complex", "[0:a]volume=0.4[bg];[1:a]volume=1.8[voc];[bg][voc]amix=inputs=2:duration=first[aout]",
        "-map", "[aout]", "-c:a", "pcm_s16le", str(final_audio)
    ], "دمج الصوت والتعليق الصوتي")
else:
    final_audio = ambient_audio

concat_file = (SHUTTLE_DIR / "timeline.txt").resolve()
concat_file.write_text(f"""file '{out_shot1.resolve()}'
file '{out_shot2.resolve()}'
file '{shot3_mp4.resolve()}'
file '{shot4_mp4.resolve()}'
""")

run_cmd([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
    "-i", str(final_audio),
    "-vf", "noise=alls=7:allf=t,eq=contrast=1.07:saturation=0.92",
    "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k", "-shortest",
    str(FINAL_VIDEO)
], "التجميع النهائي للفيديو (120 ثانية)")

log_print(f"\n{'='*60}")
log_print(f"🎉 تم الانتهاء بنجاح من إنتاج الفيديو: {FINAL_VIDEO}")
log_print(f"{'='*60}\n")
