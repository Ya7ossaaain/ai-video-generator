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
print(f"🎬 [المخرج الذكي]: بدء إنتاج الفيلم الوثائقي عن: {topic}")
print(f"🧠 [النموذج النشط]: {active_model_name}")

# نظام الحفظ المؤقت للسيناريو لمنع تكراره عند الاستئناف
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
    أنت مخرج ومؤلف وثائقيات استقصائية وتاريخية حاصل على جوائز عالمية (طراز BBC و Netflix).
    المهمة: هندسة وتأليف سيناريو فيلم وثائقي طويل ومكثف عن: "{topic}".

    البنية الهيكلية للإخراج:
    1. صمم فيلماً من 10 إلى 12 مشهداً مترابطاً بنظام الفصول الثلاثة (مقدمة غامضة -> تحقيق وأدلة ومسرح الجريمة -> ذروة وخاتمة فلسفية).
    2. لغة الإلقاء: لغة عربية فصحى أدبية، جزلة، ذات عمق تحقيقي وتسكين وقفي دقيق ومريح. ممنوع تماماً لغة مخاطبة الجمهور المبتذلة (أهلاً بكم، سنرى، في هذا المقطع).
    3. كل فقرة سردية دسمة تتكون من 3 إلى 4 جمل مركبة وموزونة، تأخذ بين 20 إلى 25 ثانية إلقاء هادئ.
    4. هندسة الانتقاء البصري لكل مشهد:
       - "video": للمشاهد التعبيرية الحية والحركية (بحث B-roll في Pexels). اكتب وصفاً إنجليزياً سينمائياً واضحاً (مثال: "snow blizzard mountain peak dark cinematic 4k").
       - "real": للأدلة والشخصيات ومسارح الجرائم الأصلية (بحث أرشيف ويكيبيديا). اكتب اسم الشخصية أو الحادثة أو مسرح الجريمة بدقة بالإنجليزية (مثال: "Dyatlov Pass incident tent searchers 1959").
       - "ai": للمشاهد التخيلية التاريخية أو التشكيلية الصعبة. اكتب وصفاً درامياً غنياً لـ FLUX مع إضاءة سينمائية.
    5. نوع حركة الكاميرا (camera_move): اختر إما "zoom_in" أو "zoom_out".

    الرد حصراً مصفوفة JSON نقية وصحيحة برمجياً:
    [
      {{
        "scene_num": 1,
        "act": "I",
        "narration": "نص السرد التحقيقي الفصيح هنا...",
        "media_type": "video",
        "search_query": "heavy snow storm mountain night cinematic 4k",
        "ai_prompt": "Cinematic shot of extreme blizzard in dark mountain, 8k documentary style",
        "camera_move": "zoom_in"
      }}
    ]
    """
    for attempt in range(5):
        try:
            print(f"✍️ جاري صياغة السرد الوثائقي وهندسة المشاهد (محاولة {attempt + 1})...")
            res = model.generate_content(director_prompt, request_options={"timeout": 600.0})
            clean_json = res.text.strip().replace("```json", "").replace("```", "").strip()
            scenes = json.loads(clean_json)
            with open(script_cache_file, "w", encoding="utf-8") as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            print(f"✨ تم اعتماد وحفظ السيناريو بنجاح: {len(scenes)} مشهداً.")
            break
        except Exception as e:
            print(f"⏳ ضغط مؤقت ({e}). إعادة المحاولة بعد 15 ثانية...")
            time.sleep(15)

if not scenes:
    raise RuntimeError("تعذر إنشاء السيناريو بعد عدة محاولات.")

# 2. قياس مدة ملف الصوت
def get_audio_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    return float(subprocess.check_output(cmd).decode().strip())

# 3. محرك مقاطع B-Roll الواقعية من Pexels
def fetch_stock_video(query, output_path):
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        return False
    print(f"🎥 [Pexels Video]: بحث عن مقطع حركي لـ: '{query}'...")
    try:
        headers = {"Authorization": api_key}
        url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page=5&orientation=landscape"
        r = requests.get(url, headers=headers, timeout=8)
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
                    stream_r = requests.get(target_url, stream=True, timeout=20)
                    if stream_r.status_code == 200:
                        with open(output_path, "wb") as f_out:
                            for chunk in stream_r.iter_content(chunk_size=1024*1024):
                                f_out.write(chunk)
                        return True
    except Exception as e:
        print(f"تنبيه Pexels Video: {e}")
    return False

# 4. محرك أرشيف ويكيبيديا للصور التاريخية والجنائية الأصلية (بدون حظر نهائياً)
def fetch_real_photo_wiki(query, output_path):
    print(f"🏛️ [أرشيف ويكيبيديا]: استخراج وثيقة/صورة حقيقية لـ: '{query}'...")
    try:
        url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": 4,
            "prop": "pageimages",
            "pithumbsize": 1920,
            "format": "json"
        }
        headers = {"User-Agent": "HistoricalDocBot/1.0 (archive_collector@bot.com)"}
        r = requests.get(url, params=params, headers=headers, timeout=8)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for _, page in pages.items():
                thumb = page.get("thumbnail", {}).get("source")
                if thumb:
                    img_resp = requests.get(thumb, headers=headers, timeout=10)
                    if img_resp.status_code == 200 and len(img_resp.content) > 15000:
                        with open(output_path, "wb") as f:
                            f.write(img_resp.content)
                        return True
    except Exception as e:
        print(f"تنبيه ويكيبيديا: {e}")
    return False

# 5. محرك صور Pexels عالية الدقة (الخطة البديلة للأرشيف)
def fetch_pexels_photo(query, output_path):
    api_key = os.environ.get("PEXELS_API_KEY", "")
    if not api_key:
        return False
    print(f"📷 [Pexels Photo]: جلب صورة واقعية بديلة لـ: '{query}'...")
    try:
        headers = {"Authorization": api_key}
        url = f"https://api.pexels.com/v1/search?query={urllib.parse.quote(query)}&per_page=3&orientation=landscape"
        r = requests.get(url, headers=headers, timeout=8)
        if r.status_code == 200:
            photos = r.json().get("photos", [])
            if photos:
                img_url = photos[0]["src"].get("large2x") or photos[0]["src"].get("original")
                img_data = requests.get(img_url, timeout=10).content
                if len(img_data) > 15000:
                    with open(output_path, "wb") as f:
                        f.write(img_data)
                    return True
    except Exception as e:
        print(f"تنبيه Pexels Photo: {e}")
    return False

# 6. محرك التوليد الفني النقي بدون أي علامات مائية
def generate_ai_photo(prompt_text, output_path):
    print("🎨 [الرسم السينمائي]: توليد بديل فوتوغرافي فائق الدقة (FLUX)...")
    encoded = urllib.parse.quote(f"{prompt_text}, 8k photorealistic documentary shot, raw film grain, Hasselblad, sharp focus, cinematic lighting, masterpiece, no text, no logo")
    for retry in range(2):
        try:
            url = f"https://image.pollinations.ai/prompt/{encoded}?width=1920&height=1120&nologo=true&nofeed=true&model=flux"
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if len(data) > 10000:
                    with open(output_path, 'wb') as out:
                        out.write(data)
                    return True
        except Exception:
            time.sleep(3)

    # خطة الطوارئ النهائية: كادر سينمائي داكن بـ FFmpeg لمنع توقف الرندرة
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0d1117:s=1920x1080:d=1",
        "-frames:v", "1", output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

# 7. الإلقاء الصوتي الفخم
async def generate_narration(text, path):
    comm = edge_tts.Communicate(text, "ar-SA-HamedNeural", rate="-2%", pitch="-1Hz")
    await comm.save(path)

# 8. استوديو المونتاج ومعالجة الكاميرا واللون (FFmpeg Pro Engine)
scene_videos = []

for i, scene in enumerate(scenes):
    video_out = f"scene_{i}.mp4"
    audio_norm = f"audio_{i}.mp3"
    audio_raw = f"audio_raw_{i}.mp3"

    # ميزة الاستئناف: تخطي المشهد إذا تم تصييره مسبقاً
    if os.path.exists(video_out) and os.path.getsize(video_out) > 50000:
        print(f"⏩ [استئناف]: المشهد {i+1} جاهز مسبقاً، المتابعة إلى المشهد التالي...")
        scene_videos.append(video_out)
        continue

    act = scene.get("act", "II")
    print(f"\n🎞️ ============= معالجة المشهد {i+1}/{len(scenes)} [الفصل {act}] =============")

    # أ. توليد الصوت ومعايرته تلفزيونياً (Broadcast Loudnorm)
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

    # ب. هل المشهد فيديو متحرك؟
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

    # ج. إذا لم يكن فيديو: البحث في ويكيبيديا -> ثم صور Pexels -> ثم التوليد الفني (FLUX)
    if not is_video_ready:
        image_path = f"image_{i}.jpg"
        got_img = False

        if scene.get("media_type") == "real" and scene.get("search_query"):
            got_img = fetch_real_photo_wiki(scene["search_query"], image_path)

        if not got_img and scene.get("search_query"):
            got_img = fetch_pexels_photo(scene["search_query"], image_path)

        if not got_img:
            generate_ai_photo(scene.get("ai_prompt", scene.get("search_query", "")), image_path)

        camera_move = scene.get("camera_move", "zoom_in")
        step = 0.22 / total_frames

        if camera_move == "zoom_out":
            zoom_expr = f"max(1.24-{step:.6f}*on,1.0)"
        else:
            zoom_expr = f"min(1.0+{step:.6f}*on,1.24)"
        pan_expr = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

        # اقتصاص العلامة المائية + تحريك الكين بيرنز + التدرج اللوني والتظليل السينمائي
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

# 9. تجميع كافة المشاهد بدقة 1080p
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

# 10. الرفع التلقائي إلى Google Drive
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

print("\n🏆 اكتمل إنتاج الفيلم الوثائقي بالكامل بنجاح وبأعلى معايير الإخراج العالمية!")
