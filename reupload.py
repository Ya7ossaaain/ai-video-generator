import os
import io
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

print("🚀 بدء عملية النقل السريع من Google Drive إلى YouTube...")

client_id = os.environ.get("GOOGLE_CLIENT_ID")
client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
yt_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
drive_token = os.environ.get("DRIVE_REFRESH_TOKEN")
topic = os.environ.get("VIDEO_TOPIC", "تحقيق وثائقي استقصائي")

# 1. الاتصال بـ Google Drive وتنزيل أحدث فيديو
creds_drive = Credentials(
    None, refresh_token=drive_token,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=client_id, client_secret=client_secret
)
drive_service = build("drive", "v3", credentials=creds_drive)

print("🔍 البحث عن أحدث فيلم في مجلد AI_Documentaries...")
q = "mimeType='video/mp4' and trashed=false"
results = drive_service.files().list(q=q, orderBy="createdTime desc", pageSize=1, fields="files(id, name)").execute()
files = results.get("files", [])

if not files:
    raise RuntimeError("لم يتم العثور على أي ملف فيديو في Google Drive!")

file_id = files[0]["id"]
file_name = files[0]["name"]
print(f"📥 جاري سحب الفيلم ({file_name}) إلى السيرفر السحابي...")

request = drive_service.files().get_media(fileId=file_id)
local_filename = "downloaded_doc.mp4"
with open(local_filename, "wb") as f:
    downloader = MediaIoBaseDownload(f, request, chunksize=10*1024*1024)
    done = False
    while not done:
        status, done = downloader.next_chunk()
        if status:
            print(f"تحميل من درايف: {int(status.progress() * 100)}%")

# 2. النشر المباشر على YouTube
print("\n🎬 جاري النشر والرفع المباشر على قناتك في YouTube...")
creds_yt = Credentials(
    None, refresh_token=yt_token,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=client_id, client_secret=client_secret
)
youtube_service = build("youtube", "v3", credentials=creds_yt)

yt_body = {
    "snippet": {
        "title": f"تحقيق استقصائي: {topic}",
        "description": f"تحقيق جنائي وتاريخي موثق بالأدلة والوثائق الأصلية.\n\n#وثائقي #تحقيقات #أدلة_جنائية",
        "tags": ["وثائقي", "تحقيقات", "أدلة جنائية", "غموض", "قضايا تاريخية"],
        "categoryId": "27"
    },
    "status": {
        "privacyStatus": "public",
        "selfDeclaredMadeForKids": False
    }
}

media_yt = MediaFileUpload(local_filename, mimetype="video/mp4", resumable=True, chunksize=10*1024*1024)
yt_req = youtube_service.videos().insert(part="snippet,status", body=yt_body, media_body=media_yt)

resp = None
while resp is None:
    status, resp = yt_req.next_chunk()
    if status:
        print(f"تقدم رفع يوتيوب: {int(status.progress() * 100)}%")

yt_id = resp.get("id")
print("\n=======================================================")
print(f"🎉 تم النشر بنجاح على يوتيوب خلال دقيقة واحدة!")
print(f"🔗 الرابط الجديد: https://youtu.be/{yt_id}")
print("=======================================================\n")
