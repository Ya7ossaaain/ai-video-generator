import os
import json
import time
import asyncio
import urllib.parse
import urllib.request
import subprocess
from datetime import datetime
import edge_tts
import google.generativeai as genai
from duckduckgo_search import DDGS
import requests

# 1. إعداد النموذج الذكي
genai.configure(api_key=os.environ["GEMINI_API_KEY"])

def get_master_model():
    candidates = ["gemini-3-flash-preview", "gemini-3.5-flash", "gemini-3.1-pro-preview"]
    for model_name in candidates:
        try:
            return genai.GenerativeModel(model_name), model_name
        except Exception:
            continue
    return genai.GenerativeModel("gemini-3-flash-preview"), "gemini-3-flash-preview"

model, active_model_name = get_master_model()
topic = os.environ.get("VIDEO_TOPIC", "حادثة ممر دياتلوف: اللغز الذي حيّر العالم")
print(f"🎬 [المخرج الذكي]: إنتاج وثائقي عن: {topic}")
print(f"🧠 [النموذج النشط]: {active_model_name}")

# حفظ السيناريو في ملف محلي لمنع إعادة توليده إذا توقف السيرفر
script_cache_file = "cached_scenes.json"
scenes = None

if os.path.exists(script_cache_file):
    try:
        with open(script_cache_file, "r", encoding="utf-8") as f:
            scenes = json.load(f)
        print(f"⚡ [استئناف]: تم استرجاع السيناريو المحفوظ مسبقاً ({len(scenes)} مشهداً).")
    except Exception:
        scenes = None

if not scenes:
    director_prompt = f"""
    أنت مخرج وثائقيات جنائية واستقصائية محترف (طراز BBC و Netflix).
    المهمة: كتابة سيناريو وثائقي دسم ومحبوك درامياً عن: "{topic}".
    قسّم العمل إلى 10 إلى 12 مشهداً مترابطاً (مقدمة غامضة -> تشريح الوقائع والقرائن -> الخاتمة والتساؤلات).
    لغة السرد: لغة عربية فصحى أدبية رصينة ومريحة، بدون مقدمات ترحيبية مبتذلة.
    حدد media_type: إما "video" أو "real" أو "ai".
    الرد مصفوفة JSON نقية فقط:
    [
      {{
        "scene_num": 1,
        "narration": "نص السرد الفصيح...",
        "media_type": "video",
        "search_query": "snow covered dark pine forest aerial cinematic 4k",
        "ai_prompt": "Cinematic aerial view of deep snow forest in Siberia, cold lighting, 8k",
        "camera_move": "zoom_in"
      }}
    ]
    """
    for attempt in range(5):
        try:
            print(f"✍️ جاري صياغة السيناريو الإخراجي (محاولة {attempt + 1})...")
            res = model.generate_content(director_prompt, request_options={"timeout": 600.0})
            clean_json = res.text.strip().replace("```json", "").replace("```", "").strip()
            scenes = json.loads(clean_json)
            with open(script_cache_file, "w", encoding="utf-8") as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            print(f"✨ تم اعتماد وحفظ السيناريو بنجاح ({len(scenes)} مشهد).")
            break
        except Exception as e:
            print(f"⏳ ضغط مؤقت ({e}). إعادة المحاولة بعد 15 ثانية...")
            time.sleep(15)

if not scenes:
    raise RuntimeError("تعذر إنشاء أو استعادة السيناريو.")

# 2. قياس مدة ملف الصوت
def get_audio_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    return float(subprocess.check_output(cmd).decode().strip())

# 3. جلب مقاطع الفيديو من Pexels
def fetch_stock_video(query, output_path):
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        return False
    print(f"🎥 [Pexels Video]: بحث عن: '{query}'...")
    try:
        headers = {"Authorization": api_key}
        url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page=6&orientation=landscape"
        r = requests.get(url, headers=headers, timeout=12)
        if r.status_code == 200:
            for v in r.json().get("videos", []):
                files = v.get("video_files", [])
                target_url = None
                for f in files:
                    if f.get("width") == 1920 or f.get("height") == 1080:
                        target_url = f.get("link")
                        break
                if not target_url and files:
                    target_url = files[0].get("link")

                if target_url:
                    stream_r = requests.get(target_url, stream=True, timeout=25)
                    if stream_r.status_code == 200:
                        with open(output_path, "wb") as f_out:
                            for chunk in stream_r.iter_content(chunk_size=1024*1024):
                                f_out.write(chunk)
                        return True
    except Exception as e:
        print(f"تنبيه Pexels: {e}")
    return False

# 4. جلب صور حقيقية من الإنترنت
def fetch_real_photo(query, output_path):
    print(f"🔍 [أرشيف الإنترنت]: بحث عن: '{query}'...")
    try:
        with DDGS() as ddgs:
            results = list(ddgs.images(keywords=query, max_results=6))
            for item in results:
                try:
                    img_url = item.get("image")
                    resp = requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=8)
                    if resp.status_code == 200 and len(resp.content) > 15000:
                        with open(output_path, "wb") as f:
                            f.write(resp.content)
                        return True
                except Exception:
                    continue
    except Exception as e:
        print(f"تنبيه الأرشيف: {e}")
    return False

# 5. توليد الصور مع نظام حماية متعدد الطبقات (ضد أخطاء 500)
def generate_ai_photo(prompt_text, output_path):
    print("🎨 [الذكاء الاصطناعي]: جاري توليد كادر بصري بديل...")
    encoded = urllib.parse.quote(f"{prompt_text}, cinematic documentary shot, photorealistic, 8k, raw texture, no text, no logo")
    
    # محاولة التحميل من سيرفر التوليد مع إعادة المحاولة
    for retry in range(3):
        try:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=1920&height=1120&nologo=true&nofeed=true&model=flux"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=35) as resp:
                data = resp.read()
                if len(data) > 10000:
                    with open(output_path, 'wb') as out:
                        out.write(data)
                    return True
        except Exception as e:
            print(f"⚠️ تعثر مؤقت في سيرفر الصور ({e}). محاولة بعد 5 ثوانٍ...")
            time.sleep(5)

    # خطة إنقاذ تلقائية (Fallback): إذا تعطل السيرفر، يتم البحث عن صورة واقعية للبرومبت
    print("🔄 خطة الطوارئ: الانتقال للبحث عن بديل أرشيفي مناسب...")
    if fetch_real_photo(prompt_text[:80], output_path):
        return True

    # خطة الطوارئ النهائية: إنشاء كادر لوني سينمائي داكن بـ FFmpeg لمنع توقف الرندرة نهائياً
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0d1117:s=1920x1080:d=1",
        "-frames:v", "1", output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

# 6. توليد الصوت
async def generate_narration(text, path):
    comm = edge_tts.Communicate(text, "ar-SA-HamedNeural", rate="-2%", pitch="-1Hz")
    await comm.save(path)

# 7. استوديو المونتاج مع نظام استئناف المشاهد المكتملة
scene_videos = []

for i, scene in enumerate(scenes):
    video_out = f"scene_{i}.mp4"
    audio_norm = f"audio_{i}.mp3"
    audio_raw = f"audio_raw_{i}.mp3"

    # ميزة الاستئناف: إذا كان المشهد مُنتجاً مسبقاً وسليماً، يتم تخطيه فوراً
    if os.path.exists(video_out) and os.path.getsize(video_out) > 50000:
        print(f"⏩ [تخطي]: المشهد {i+1} جاهز ومكتمل مسبقاً، المتابعة إلى التالي...")
        scene_videos.append(video_out)
        continue

    print(f"\n🎞️ ============= معالجة المشهد {i+1}/{len(scenes)} =============")

    # أ. توليد الصوت إذا لم يكن موجوداً
    if not (os.path.exists(audio_norm) and os.path.getsize(audio_norm) > 1000):
        asyncio.run(generate_narration(scene["narration"], audio_raw))
        subprocess.run([
            "ffmpeg", "-y", "-i", audio_raw,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "192k",
            audio_norm
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    duration = get_audio_duration(audio_norm)
    fps = 25
    total_frames = int(duration * fps) + 12

    # ب. محاولة جلب فيديو متحرك
    is_video_ready = False
    temp_clip = f"clip_{i}.mp4"
    if scene.get("media_type") == "video" and scene.get("search_query"):
        if fetch_stock_video(scene["search_query"], temp_clip):
            cmd_v = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", temp_clip,
                "-i", audio_norm,
                "-filter_complex", (
                    "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,"
                    "eq=contrast=1.06:brightness=-0.01:saturation=1.05,vignette=PI/4.5[v]"
                ),
                "-map", "[v]", "-map", "1:a",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-b:v", "6000k", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k",
                "-t", str(duration),
                video_out
            ]
            subprocess.run(cmd_v, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            is_video_ready = True

    # ج. استخدام صورة (أرشيفية أو ذكاء اصطناعي) مع زووم سينمائي
    if not is_video_ready:
        image_path = f"image_{i}.jpg"
        got_img = False
        if scene.get("media_type") == "real" and scene.get("search_query"):
            got_img = fetch_real_photo(scene["search_query"], image_path)
        if not got_img:
            generate_ai_photo(scene.get("ai_prompt", scene.get("search_query", "")), image_path)

        camera_move = scene.get("camera_move", "zoom_in")
        step = 0.22 / total_frames

        if camera_move == "zoom_out":
            zoom_expr = f"max(1.24-{step:.6f}*on,1.0)"
        else:
            zoom_expr = f"min(1.0+{step:.6f}*on,1.24)"
        pan_expr = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

        filter_complex = (
            f"[0:v]scale=w=1920:h=1120:force_original_aspect_ratio=increase,crop=1920:1080:0:0,"
            f"scale=8000:-1,"
            f"zoompan=z='{zoom_expr}':{pan_expr}:d={total_frames}:s=1920x1080:fps={fps},"
            f"eq=contrast=1.07:brightness=-0.01:saturation=1.05,vignette=PI/4.5[v]"
        )

        cmd_i = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_norm,
            "-filter_complex", filter_complex,
            "-map", "[v]", "-map", "1:a",
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-b:v", "6000k", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            "-t", str(duration),
            video_out
        ]
        subprocess.run(cmd_i, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    scene_videos.append(video_out)

# 8. التجميع النهائي
print("\n🪡 [المونتاج النهائي]: جاري دمج كافة فصول الفيلم الوثائقي...")
with open("concat_list.txt", "w") as f:
    for vid in scene_videos:
        f.write(f"file '{vid}'\n")

final_output = "final_documentary.mp4"
subprocess.run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", "concat_list.txt",
    "-c", "copy", final_output
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

# 9. الرفع التلقائي إلى Google Drive
if "DRIVE_UPLOAD_URL" in os.environ and os.environ["DRIVE_UPLOAD_URL"]:
    print("☁️ [الرفع السحابي]: جاري إرسال الفيلم الوثائقي إلى Google Drive...")
    import base64
    url = os.environ["DRIVE_UPLOAD_URL"]
    with open(final_output, "rb") as f:
        encoded_video = base64.b64encode(f.read()).decode("utf-8")
        
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    resp = requests.post(
        url,
        data=encoded_video,
        params={"filename": f"Master_Doc_{stamp}.mp4"},
        timeout=300
    )
    print("🚀 [نتيجة درايف]:", resp.text)

print("\n🏆 اكتمل إنتاج الفيلم بالكامل وبنجاح تام!")
