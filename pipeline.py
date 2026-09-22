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
model = genai.GenerativeModel("gemini-3.5-flash")

# استلام موضوع الفيديو (إذا لم يتم تحديده نضع موضوعاً افتراضياً)
topic = os.environ.get("VIDEO_TOPIC", "Mysteries of the Deep Sea")
print(f"--- بدء إنتاج فيديو عن: {topic} ---")

# 2. توليد السكربت الطويل مقسماً إلى مشاهد
prompt = f"""
Write an engaging, informative YouTube documentary script about: "{topic}".
Divide the script into 6 to 8 sequential scenes.
You MUST reply with ONLY a raw JSON array of objects (no markdown, no ``` backticks).
Each object must have exactly two fields:
- "narration": Spoken narration for this scene in clear English (2 to 3 sentences).
- "image_prompt": A descriptive visual prompt to generate a 16:9 cinematic illustration for this scene.
"""

response = model.generate_content(prompt)
raw_text = response.text.strip()
if raw_text.startswith("```"):
    raw_text = raw_text.split("\n", 1)[1].rsplit("\n", 1)[0].strip()

scenes = json.loads(raw_text)
print(f"تم إنشاء {len(scenes)} مشاهد بنجاح.")

# 3. توليد الصوت والصور لكل مشهد
async def generate_audio(text, output_file):
    communicate = edge_tts.Communicate(text, "en-US-ChristopherNeural")
    await communicate.save(output_file)

scene_videos = []

for i, scene in enumerate(scenes):
    print(f"\nمعالجة المشهد رقم {i+1}/{len(scenes)}...")
    audio_path = f"audio_{i}.mp3"
    image_path = f"image_{i}.jpg"
    video_path = f"scene_{i}.mp4"

    # أ. توليد الصوت
    asyncio.run(generate_audio(scene["narration"], audio_path))

    # ب. توليد صورة 16:9 عالية الجودة مجاناً
    encoded_prompt = urllib.parse.quote(f"{scene['image_prompt']}, 8k, cinematic, photorealistic, documentary style")
    img_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=1920&height=1080&nologo=true"
    urllib.request.urlretrieve(img_url, image_path)

    # ج. دمج الصوت مع الصورة عبر FFmpeg
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-i", audio_path,
        "-c:v", "libx264", "-tune", "stillimage",
        "-c:a", "aac", "-b:a", "192k",
        "-pix_fmt", "yuv420p",
        "-shortest", video_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    scene_videos.append(video_path)

# 4. دمج جميع المشاهد في فيديو طويل واحد
print("\nجاري تجميع المشاهد معاً...")
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

print("اكتمل إنتاج الفيديو الطويل بنجاح!")

