import os
import json
import asyncio
import urllib.parse
import urllib.request
import subprocess
import edge_tts
import google.generativeai as genai

# 1. إعداد Gemini
genai.configure(api_key=os.environ["GEMINI_API_KEY"])
model = genai.GenerativeModel("gemini-3.1-pro-preview")

# استلام موضوع الفيديو
topic = os.environ.get("VIDEO_TOPIC", "أسرار الحضارات القديمة الغامضة")
print(f"--- بدء إنتاج وثائقي عربي طويل عن: {topic} ---")

# 2. توليد سكربت وثائقي طويل ومفصل باللغة العربية
prompt = f"""
أنت كاتب وثائقيات وسيناريست محترف. اكتب نص فيديو وثائقي طويل ومشوق جداً وموجه لليوتيوب عن موضوع: "{topic}".
قسّم الفيديو إلى 12 إلى 14 مشهداً متسلسلاً ومترابطاً بحيث يكون السرد عميقاً وممتعاً.
يجب أن يكون الرد عبارة عن مصفوفة JSON نقية فقط (بدون أي علامات مقتبسة ``` أو نصوص تمهيدية):
[
  {{
    "narration": "نص السرد الصوتي لهذا المشهد باللغة العربية الفصحى التشكيلية المريحة، فقرة دسمة ومترابطة من 4 إلى 5 جمل تأخذ حوالي 30 ثانية في القراءة الإلقائية الهادئة.",
    "image_prompt": "A detailed 16:9 cinematic shot description in English, photorealistic, documentary style, 8k resolution, dramatic lighting, no text, no watermark, master shot."
  }}
]
"""

response = model.generate_content(prompt, request_options={"timeout": 600.0})
raw_text = response.text.strip()
if raw_text.startswith("```"):
    raw_text = raw_text.split("\n", 1)[1].rsplit("\n", 1)[0].strip()

scenes = json.loads(raw_text)
print(f"تم توليد سيناريو وثائقي يحتوي على {len(scenes)} مشهد.")

# 3. توليد الصوت العربي الفخم عبر Edge-TTS (صوت حامد الوثائقي)
async def generate_arabic_audio(text, output_file):
    # ar-SA-HamedNeural هو أفضل صوت عربي فخم ورصين للوثائقيات
    communicate = edge_tts.Communicate(text, "ar-SA-HamedNeural", rate="-2%", pitch="-1Hz")
    await communicate.save(output_file)

scene_videos = []

for i, scene in enumerate(scenes):
    print(f"\n--- معالجة المشهد رقم {i+1} من {len(scenes)} ---")
    audio_path = f"audio_{i}.mp3"
    image_path = f"image_{i}.jpg"
    video_path = f"scene_{i}.mp4"

    # أ. توليد الصوت العربي
    asyncio.run(generate_arabic_audio(scene["narration"], audio_path))

    # ب. توليد صورة سينمائية بدون لوجو عبر نموذج FLUX
    clean_prompt = f"{scene['image_prompt']}, award winning photography, 8k, cinematic, no borders, clean composition"
    encoded_prompt = urllib.parse.quote(clean_prompt)
    img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1920&height=1080&nologo=true&nofeed=true&model=flux"
    
    # محاولة تنزيل الصورة
    req = urllib.request.Request(img_url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp, open(image_path, 'wb') as out_file:
        out_file.write(resp.read())

    # ج. تحريك الصورة (Ken Burns Zoom Effect) ودمجها مع الصوت
    # هذا الفلتر يمنح الصورة حركة تقريب وزوم سينمائي بطيء يلغي جمود الصور الثابتة تماماً
    filter_complex = "scale=8000:-1,zoompan=z='min(zoom+0.0008,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=25"
    
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-filter_complex", filter_complex,
        "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest", video_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    scene_videos.append(video_path)

# 4. دمج جميع المشاهد في فيلم وثائقي طويل ومترابط
print("\nجاري تجميع كافة المشاهد في الفيديو الوثائقي النهائي...")
with open("concat_list.txt", "w") as f:
    for vid in scene_videos:
        f.write(f"file '{vid}'\n")

final_output = "final_long_video.mp4"
subprocess.run([
    "ffmpeg", "-y",
    "-f", "concat", "-safe", "0",
    "-i", "concat_list.txt",
    "-c", "copy", final_output
], check=True)

print("اكتمل تجهيز الوثائقي الطويل بنجاح تام!")
