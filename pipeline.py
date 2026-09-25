import os
import requests
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

print("=" * 60)
print("🔍 بدء الفحص الشامل لبيانات الاعتماد والمفاتيح...")
print("=" * 60)

# 1. فحص مفتاح Gemini API باستخدام نموذج Gemini 3 Flash
print("\n[1/4] 🧠 فحص Gemini API:")
gemini_key = os.environ.get("GEMINI_API_KEY")
if not gemini_key:
    print("❌ خطأ: GEMINI_API_KEY غير موجود في Secrets.")
else:
    try:
        genai.configure(api_key=gemini_key)
        target_models = ["gemini-3-flash-preview", "gemini-3.5-flash", "gemini-2.5-flash"]
        connected = False
        for m_name in target_models:
            try:
                m = genai.GenerativeModel(m_name)
                res = m.generate_content("أكد الاتصال بكلمة واحدة")
                print(f"✅ Gemini متصل ويعمل بنجاح عبر ({m_name})! الرد: '{res.text.strip()}'")
                connected = True
                break
            except Exception:
                continue
        if not connected:
            print("❌ تعذر العثور على النموذج المطلوب، تأكد من تفعيل Gemini API في المشروع.")
    except Exception as e:
        print(f"❌ فشل الاتصال بـ Gemini: {e}")

# 2. فحص مفتاح Pexels API
print("\n[2/4] 🎥 فحص Pexels API:")
pexels_key = os.environ.get("PEXELS_API_KEY")
if not pexels_key:
    print("⚠️ تنبيه: PEXELS_API_KEY غير موجود.")
else:
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search?query=nature&per_page=1",
            headers={"Authorization": pexels_key},
            timeout=5
        )
        if r.status_code == 200:
            print("✅ Pexels API صالح ومتصل بنجاح!")
        else:
            print(f"❌ خطأ في Pexels: كود {r.status_code}")
    except Exception as e:
        print(f"❌ فشل الاتصال بـ Pexels: {e}")

# البيانات المشتركة لـ Google Cloud
client_id = os.environ.get("GOOGLE_CLIENT_ID")
client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
yt_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
drive_token = os.environ.get("DRIVE_REFRESH_TOKEN")

# 3. فحص الاتصال بقناة YouTube
print("\n[3/4] 📺 فحص الاتصال بقناة YouTube:")
if not (client_id and client_secret and yt_token):
    print("❌ نقص في مفاتيح يوتيوب (تأكد من تمريرها داخل env في ملف render.yml).")
else:
    try:
        creds_yt = Credentials(
            None,
            refresh_token=yt_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )
        yt_service = build("youtube", "v3", credentials=creds_yt)
        ch_request = yt_service.channels().list(part="snippet", mine=True)
        ch_response = ch_request.execute()
        items = ch_response.get("items", [])
        if items:
            channel_name = items[0]["snippet"]["title"]
            print(f"✅ تم الاتصال بقناتك بنجاح! اسم القناة: [{channel_name}]")
        else:
            print("⚠️ تم التحقق من الحساب بنجاح، لكن لا توجد قناة يوتيوب منشأة داخل هذا الحساب.")
    except Exception as e:
        print(f"❌ فشل الاتصال بـ YouTube: {e}")

# 4. فحص الاتصال بحساب Google Drive
print("\n[4/4] ☁️ فحص الاتصال بحساب Google Drive:")
if not (client_id and client_secret and drive_token):
    print("❌ نقص في مفاتيح درايف (تأكد من تمريرها داخل env في ملف render.yml).")
else:
    try:
        creds_drive = Credentials(
            None,
            refresh_token=drive_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret
        )
        drive_service = build("drive", "v3", credentials=creds_drive)
        about_request = drive_service.about().get(fields="user(displayName,emailAddress)")
        about_response = about_request.execute()
        user_info = about_response.get("user", {})
        print(f"✅ تم الاتصال بـ Google Drive بنجاح! الحساب: [{user_info.get('displayName')} - {user_info.get('emailAddress')}]")
    except Exception as e:
        print(f"❌ فشل الاتصال بـ Google Drive: {e}")

print("\n" + "=" * 60)
print("🏁 اكتمل الفحص الأمني السريع!")
print("=" * 60)
