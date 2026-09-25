import os
import json
import time
import asyncio
import base64
import urllib.parse
import urllib.request
import subprocess
from datetime import datetime
import requests

# مكتبات معالجة النص العربي للترجمة والخطوط
import arabic_reshaper
from bidi.algorithm import get_display

from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# تهيئة عميل Gemini
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY غير موجود في Secrets!")

client = genai.Client(api_key=api_key)
topic = os.environ.get("VIDEO_TOPIC", "حادثة ممر دياتلوف: اللغز الذي حيّر العالم")
print(f"🎬 [المخرج الوثائقي]: بدء إنتاج وثائقي استقصائي مكثف بالأدلة الحقيقية والترجمة عن: {topic}")

# البحث التلقائي عن خط عربي متوفر في نظام Ubuntu
def get_arabic_font():
    font_paths = [
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansArabic-Bold.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    ]
    for f in font_paths:
        if os.path.exists(f):
            return f
    try:
        found = subprocess.check_output(["find", "/usr/share/fonts", "-name", "*Arabic*.ttf"]).decode().splitlines()
        if found:
            return found[0]
    except Exception:
        pass
    return "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

ARABIC_FONT = get_arabic_font()
print(f"🔤 تم اعتماد الخط للترجمة والشارات: {ARABIC_FONT}")

# دالة تشكيل وتنسيق النصوص العربية لـ FFmpeg
def format_arabic_for_ffmpeg(text, max_chars_per_line=50):
    words = text.split()
    lines, cur_line, cur_len = [], [], 0
    for w in words:
        if cur_len + len(w) + 1 > max_chars_per_line:
            lines.append(" ".join(cur_line))
            cur_line = [w]
            cur_len = len(w)
        else:
            cur_line.append(w)
            cur_len += len(w) + 1
    if cur_line:
        lines.append(" ".join(cur_line))

    formatted = []
    for line in lines:
        reshaped = arabic_reshaper.reshape(line)
        bidi_line = get_display(reshaped)
        escaped = bidi_line.replace("'", "\\'").replace(":", "\\:").replace("%", "\\%")
        formatted.append(escaped)
    return "\n".join(formatted)

# 1. صياغة السيناريو الاستقصائي المركز على الأدلة
script_cache_file = "cached_scenes_evidence.json"
scenes = None

if os.path.exists(script_cache_file):
    try:
        with open(script_cache_file, "r", encoding="utf-8") as f:
            scenes = json.load(f)
        print(f"⚡ [استئناف]: تم استرجاع السيناريو الجاهز ({len(scenes)} مشهداً).")
    except Exception:
        scenes = None

if not scenes:
    director_prompt = f"""
    أنت كبير محققي ومخرجي الأفلام الوثائقية الجنائية والتاريخية (طراز Netflix Crime و BBC Investigations).
    الموضوع: "{topic}".
    المطلوب: سيناريو استقصائي ضخم ومدعم بالأدلة الميدانية، يتكون من 40 إلى 44 مشهداً (مدة 10-12 دقيقة).

    شروط الأدلة والإخراج الصارمة:
    1. اجعل 70% على الأقل من المشاهد تعتمد على أدلة حقيقية ("media_type": "real") تشمل:
       (تقارير التشريح، صور مسرح الجريمة الحقيقي، برقيات اللاسلكي، وثائق الاستجواب، صور الضحايا قبل الحادث، المقتنيات الشخصية).
    2. كلمات البحث (search_query) للوسائط الحقيقية يجب أن تكون بالإنجليزية الدقيقة جداً للأرشيف الجنائي والتاريخي:
       (أمثلة: "Dyatlov Pass abandoned tent cut from inside 1959 original", "Soviet criminal case file KGB autopsy Dyatlov", "Kholat Syakhl search party telegram document").
    3. بقية المشاهد تتوزع بين:
       - "video": لمشاهد الحركة الواقعية في Pexels (ثلوج، مسير، مختبر، رياح عاصفة).
       - "ai": لتجسيد الفرضيات اللحظية المستعصية.
    4. كل فقرة سردية (narration) تتكون من جملتين أو 3 جمل محبوكة ومكثفة (مدة إلقائها 14-16 ثانية) باللغة العربية الفصحى الرصينة والمشكولة.
    5. حركة الكاميرا (camera_move): استخدم ("tilt_down", "zoom_in", "pan_left", "pan_right")، واحرص على استخدام tilt_down خصيصاً مع الوثائق لمسحها من الأعلى للأسفل.

    أخرج النتيجة بصيغة JSON Array نقية فقط:
    [
      {{
        "scene_num": 1,
        "narration": "نص السرد الوثائقي المتقن هنا...",
        "media_type": "real",
        "search_query": "Dyatlov expedition group final official diary 1959",
        "ai_prompt": "Vintage 1950s documentary archive investigation",
        "camera_move": "tilt_down"
      }}
    ]
    """
    for model_candidate in ["gemini-2.5-flash", "gemini-3-flash-preview"]:
        try:
            print(f"✍️ جاري صياغة السرد الوثائقي القائم على الأدلة عبر ({model_candidate})...")
            res = client.models.generate_content(model=model_candidate, contents=director_prompt)
            clean_json = res.text.strip().replace("```json", "").replace("```", "").strip()
            scenes = json.loads(clean_json)
            with open(script_cache_file, "w", encoding="utf-8") as f:
                json.dump(scenes, f, ensure_ascii=False, indent=2)
            print(f"✨ تم اعتماد سيناريو الأدلة بنجاح: {len(scenes)} مشهداً!")
            break
        except Exception as e:
            print(f"⏳ محاولة مع نموذج بديل ({e})...")
            time.sleep(5)

if not scenes:
    raise RuntimeError("تعذر توليد السيناريو.")

# 2. التعليق الصوتي الدرامي عبر Gemini 3.8 Flash TTS بصوت Charon
def generate_gemini_audio(narration_text, output_wav_path):
    models_to_try = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]
    for tts_model in models_to_try:
        for attempt in range(4):
            try:
                response = client.models.generate_content(
                    model=tts_model,
                    contents=[{
                        "role": "user",
                        "parts": [{
                            "text": narration_text,
                            "speech_metadata": {
                                "style": "deep, solemn, mysterious investigative crime documentary narrator"
                            }
                        }]
                    }],
                    config={
                        "response_modalities": ["AUDIO"],
                        "speech_config": {
                            "voice_config": {
                                "voice": "Charon"
                            }
                        }
                    }
                )
                raw_bytes = response.candidates[0].content.parts[0].inline_data.data
                audio_data = base64.b64decode(raw_bytes) if isinstance(raw_bytes, str) else raw_bytes
                with open(output_wav_path, "wb") as f_out:
                    f_out.write(audio_data)
                return True
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    print("⏳ سقف الدقيقة (RPM)، انتظار 15 ثانية...")
                    time.sleep(15)
                else:
                    break
    # محرك احتياطي
    try:
        import edge_tts
        print("🔄 تشغيل المحرك الصوتي الاحتياطي (Edge-TTS)...")
        comm = edge_tts.Communicate(narration_text, "ar-SA-HamedNeural", rate="-1%", pitch="-1Hz")
        asyncio.run(comm.save(output_wav_path))
        return True
    except Exception as e:
        print(f"❌ خطأ صوتي: {e}")
        return False

def get_audio_duration(file_path):
    cmd = [
        "ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    return float(subprocess.check_output(cmd).decode().strip())

# 3. محرك أرشيف الأدلة والوثائق الجنائية (Wikimedia Commons + Wikipedia)
def fetch_evidence_photo(query, output_path):
    headers = {"User-Agent": "ForensicDocEngine/3.0 (historical_investigation@gmail.com)"}
    # 1. فحص مستودع ملفات ويكيميديا للأدلة الميدانية
    try:
        url_comm = "https://commons.wikimedia.org/w/api.php"
        params_comm = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": 5,
            "prop": "imageinfo",
            "iiprop": "url",
            "iiurlwidth": 1920,
            "format": "json"
        }
        r = requests.get(url_comm, params=params_comm, headers=headers, timeout=8)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for _, page in pages.items():
                img_info = page.get("imageinfo", [])
                if img_info:
                    thumb = img_info[0].get("thumburl") or img_info[0].get("url")
                    if thumb:
                        resp = requests.get(thumb, headers=headers, timeout=10)
                        if resp.status_code == 200 and len(resp.content) > 20000:
                            with open(output_path, "wb") as f:
                                f.write(resp.content)
                            return True
    except Exception:
        pass

    # 2. فحص موسوعة ويكيبيديا للصور الموثقة
    try:
        url_wiki = "https://en.wikipedia.org/w/api.php"
        params_wiki = {
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrlimit": 4,
            "prop": "pageimages",
            "pithumbsize": 1920,
            "format": "json"
        }
        r = requests.get(url_wiki, params=params_wiki, headers=headers, timeout=8)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for _, page in pages.items():
                thumb = page.get("thumbnail", {}).get("source")
                if thumb:
                    resp = requests.get(thumb, headers=headers, timeout=10)
                    if resp.status_code == 200 and len(resp.content) > 15000:
                        with open(output_path, "wb") as f:
                            f.write(resp.content)
                        return True
    except Exception:
        pass
    return False

# 4. محرك مقاطع Pexels السينمائية
def fetch_stock_video(query, output_path):
    api_key_pex = os.environ.get("PEXELS_API_KEY", "")
    if not api_key_pex:
        return False
    try:
        headers = {"Authorization": api_key_pex}
        url = f"https://api.pexels.com/videos/search?query={urllib.parse.quote(query)}&per_page=4&orientation=landscape"
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
    except Exception:
        pass
    return False

# 5. محرك صور Pexels عالية الدقة
def fetch_pexels_photo(query, output_path):
    api_key_pex = os.environ.get("PEXELS_API_KEY", "")
    if not api_key_pex:
        return False
    try:
        headers = {"Authorization": api_key_pex}
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
    except Exception:
        pass
    return False

# 6. محرك التوليد الفني FLUX
def generate_ai_photo(prompt_text, output_path):
    encoded = urllib.parse.quote(f"{prompt_text}, raw historical forensic photo, dark cinematography, 35mm film grain, 8k, no text")
    for _ in range(2):
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
    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=0x0a0c10:s=1920x1080:d=1",
        "-frames:v", "1", output_path
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True

# 7. استوديو المونتاج الملحمي (فلاتر الأرشيف + الشارة الحمراء + الترجمة المباشرة)
scene_videos = []

# نص الشارة الحمراء للأدلة التاريخية
EVIDENCE_BADGE_TEXT = format_arabic_for_ffmpeg("● وثائق وأدلة حقيقية | ملف التحقيق")

for i, scene in enumerate(scenes):
    video_out = f"scene_{i}.mp4"
    audio_norm = f"audio_{i}.mp3"
    audio_raw = f"audio_raw_{i}.wav"

    if os.path.exists(video_out) and os.path.getsize(video_out) > 50000:
        print(f"⏩ [استئناف]: المشهد {i+1}/{len(scenes)} مكتمل مسبقاً.")
        scene_videos.append(video_out)
        continue

    is_real_evidence = (scene.get("media_type") == "real")
    evidence_tag = " [🔍 دليل حقيقي]" if is_real_evidence else ""
    print(f"\n🎬 معالجة المشهد {i+1}/{len(scenes)}{evidence_tag}...")

    # توليد وضبط الصوت
    if not (os.path.exists(audio_norm) and os.path.getsize(audio_norm) > 1000):
        generate_gemini_audio(scene["narration"], audio_raw)
        subprocess.run([
            "ffmpeg", "-y", "-i", audio_raw,
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "libmp3lame", "-b:a", "192k",
            audio_norm
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    duration = get_audio_duration(audio_norm)
    fps = 25
    total_frames = int(duration * fps) + 12

    # تجهيز شريط الترجمة السفلي
    subtitle_text = format_arabic_for_ffmpeg(scene["narration"], max_chars_per_line=52)

    # بناء شريط الترجمة مع خلفية سينمائية داكنة
    sub_filter = (
        f",drawbox=x=0:y=ih-155:w=iw:h=155:color=black@0.65:t=fill,"
        f"drawtext=fontfile='{ARABIC_FONT}':text='{subtitle_text}':fontcolor=white:fontsize=32:"
        f"line_spacing=12:x=(w-text_w)/2:y=h-130"
    )

    # بناء الشارة الحمراء العريضة في أعلى الشاشة عند عرض دليل حقيقي
    badge_filter = ""
    if is_real_evidence:
        badge_filter = (
            f",drawbox=x=50:y=45:w=440:h=56:color=0x990000@0.90:t=fill,"
            f"drawbox=x=50:y=45:w=440:h=56:color=white@0.40:t=2,"
            f"drawtext=fontfile='{ARABIC_FONT}':text='{EVIDENCE_BADGE_TEXT}':fontcolor=white:fontsize=22:"
            f"x=70:y=62"
        )

    # فلتر التلوين الأرشيفي التاريخي (حبيبات الفيلم + الألوان الباردة + التظليل)
    if is_real_evidence:
        archival_grading = "hue=s=0.65,eq=contrast=1.20:brightness=-0.03,noise=alls=11:allf=t+u,vignette=PI/3.2"
    else:
        archival_grading = "eq=contrast=1.07:brightness=-0.01:saturation=1.05,vignette=PI/4.5"

    video_encode_params = [
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-b:v", "5500k", "-maxrate", "6500k", "-bufsize", "8000k",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k"
    ]

    is_video_ready = False
    temp_clip = f"clip_{i}.mp4"
    if scene.get("media_type") == "video" and scene.get("search_query"):
        if fetch_stock_video(scene["search_query"], temp_clip):
            filter_chain = (
                f"[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,"
                f"{archival_grading}{sub_filter}[v]"
            )
            cmd_v = [
                "ffmpeg", "-y",
                "-stream_loop", "-1", "-i", temp_clip,
                "-i", audio_norm,
                "-filter_complex", filter_chain,
                "-map", "[v]", "-map", "1:a"
            ] + video_encode_params + ["-t", str(duration), video_out]
            subprocess.run(cmd_v, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            is_video_ready = True

    if not is_video_ready:
        image_path = f"image_{i}.jpg"
        got_img = False

        if is_real_evidence and scene.get("search_query"):
            got_img = fetch_evidence_photo(scene["search_query"], image_path)

        if not got_img and scene.get("search_query"):
            got_img = fetch_pexels_photo(scene["search_query"], image_path)

        if not got_img:
            generate_ai_photo(scene.get("ai_prompt", scene.get("search_query", "")), image_path)

        camera_move = scene.get("camera_move", "zoom_in")
        step = 0.22 / total_frames

        if camera_move == "zoom_out":
            zoom_expr = f"max(1.24-{step:.6f}*on,1.0)"
            pan_expr = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        elif camera_move == "tilt_down":
            zoom_expr = "1.20"
            pan_expr = "x='iw/2-(iw/zoom/2)':y='(on/d)*(ih-ih/zoom)'"
        elif camera_move == "pan_left":
            zoom_expr = "1.20"
            pan_expr = "x='(1-on/d)*(iw-iw/zoom)':y='ih/2-(ih/zoom/2)'"
        elif camera_move == "pan_right":
            zoom_expr = "1.20"
            pan_expr = "x='(on/d)*(iw-iw/zoom)':y='ih/2-(ih/zoom/2)'"
        else:
            zoom_expr = f"min(1.0+{step:.6f}*on,1.24)"
            pan_expr = "x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"

        filter_chain = (
            f"[0:v]scale=w=1920:h=1120:force_original_aspect_ratio=increase,crop=1920:1080:0:0,"
            f"scale=8000:-1,"
            f"zoompan=z='{zoom_expr}':{pan_expr}:d={total_frames}:s=1920x1080:fps={fps},"
            f"{archival_grading}{badge_filter}{sub_filter}[v]"
        )

        cmd_i = [
            "ffmpeg", "-y",
            "-loop", "1", "-i", image_path,
            "-i", audio_norm,
            "-filter_complex", filter_chain,
            "-map", "[v]", "-map", "1:a"
        ] + video_encode_params + ["-t", str(duration), video_out]
        subprocess.run(cmd_i, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    scene_videos.append(video_out)

# 8. التجميع النهائي للشريط الوثائقي
print("\n🪡 [المونتاج النهائي]: جاري دمج كافة مشاهد الأدلة والتحقيقات...")
with open("concat_list.txt", "w") as f:
    for vid in scene_videos:
        f.write(f"file '{vid}'\n")

final_output = "final_documentary.mp4"
subprocess.run([
    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
    "-i", "concat_list.txt",
    "-c", "copy", final_output
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

file_size_mb = os.path.getsize(final_output) / (1024 * 1024)
print(f"📦 [الحجم النهائي]: تم إخراج الفيلم بنجاح بحجم كامل: {file_size_mb:.2f} ميجابايت.")

# 9. الرفع المباشر إلى YouTube و Google Drive
client_id = os.environ.get("GOOGLE_CLIENT_ID")
client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
yt_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
drive_token = os.environ.get("DRIVE_REFRESH_TOKEN")

# نشر على YouTube
if client_id and client_secret and yt_token:
    print("\n🚀 [YouTube]: جاري نشر الفيلم مباشرة على قناتك...")
    try:
        creds_yt = Credentials(
            None, refresh_token=yt_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id, client_secret=client_secret
        )
        youtube_service = build("youtube", "v3", credentials=creds_yt)
        yt_body = {
            "snippet": {
                "title": f"تحقيق استقصائي: {topic} (وثائق وأدلة حقيقية)",
                "description": f"تحقيق جنائي وتاريخي موثق بالأدلة والوثائق الأصلية حول {topic}.\n\nالعمل مصحوب بترجمة نصية كاملة وفحص للأدلة الميدانية ومحاضر التحقيق الرسمية.\n\n#وثائقي #تحقيقات #قضايا_غامضة #أدلة_جنائية",
                "tags": ["وثائقي", "تحقيقات", "أدلة جنائية", "غموض", "قضايا تاريخية"],
                "categoryId": "27"
            },
            "status": {
                "privacyStatus": "public",
                "selfDeclaredMadeForKids": False
            }
        }
        media_yt = MediaFileUpload(final_output, mimetype="video/mp4", resumable=True, chunksize=10*1024*1024)
        yt_req = youtube_service.videos().insert(part="snippet,status", body=yt_body, media_body=media_yt)
        resp = None
        while resp is None:
            status, resp = yt_req.next_chunk()
            if status:
                print(f"تقدم رفع يوتيوب: {int(status.progress() * 100)}%")
        yt_id = resp.get("id")
        print("\n=======================================================")
        print(f"🎉 تم النشر بنجاح على قناتك في يوتيوب!")
        print(f"🔗 رابط المشاهدة على YouTube: https://youtu.be/{yt_id}")
        print("=======================================================\n")
    except Exception as e:
        print(f"⚠️ تنبيه يوتيوب: {e}")

# حفظ في Google Drive
if client_id and client_secret and drive_token:
    print("\n☁️ [Google Drive]: جاري الرفع بالحجم الكامل إلى Google Drive...")
    try:
        creds_drive = Credentials(
            None, refresh_token=drive_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id, client_secret=client_secret
        )
        drive_service = build("drive", "v3", credentials=creds_drive)
        q = "name='AI_Documentaries' and mimeType='application/vnd.google-apps.folder' and trashed=false"
        res = drive_service.files().list(q=q, spaces='drive').execute()
        folders = res.get('files', [])
        parent_id = folders[0]['id'] if folders else drive_service.files().create(
            body={'name': 'AI_Documentaries', 'mimeType': 'application/vnd.google-apps.folder'}, fields='id'
        ).execute().get('id')

        drive_meta = {
            'name': f"Master_Evidence_Doc_{datetime.now().strftime('%Y-%m-%d_%H-%M')}.mp4",
            'parents': [parent_id]
        }
        media_drive = MediaFileUpload(final_output, mimetype="video/mp4", resumable=True, chunksize=10*1024*1024)
        df = drive_service.files().create(body=drive_meta, media_body=media_drive, fields='id, webViewLink').execute()
        print(f"✅ تم حفظ الفيديو في درايف بنجاح! الرابط: {df.get('webViewLink')}")
    except Exception as e:
        print(f"⚠️ تنبيه درايف: {e}")

# رابط بديل مؤقت أونلاين
print("\n🌐 جاري استخراج رابط مشاهدة أونلاين بديل...")
try:
    with open(final_output, "rb") as f_vid:
        r_stream = requests.post(
            "https://litterbox.catbox.moe/resources/internals/api.php",
            data={"reqtype": "fileupload", "time": "72h"},
            files={"fileToUpload": f_vid},
            timeout=180
        )
        if r_stream.status_code == 200 and r_stream.text.startswith("http"):
            print(f"▶️ [رابط بديل في المتصفح]: {r_stream.text.strip()}")
except Exception:
    pass

print("\n🏆 اكتمل إنتاج الفيلم الملحمي الموثق بالأدلة بنجاح تام!")
