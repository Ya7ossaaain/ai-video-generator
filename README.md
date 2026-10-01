# UNIVERSAL INVESTIGATIVE DOCUMENTARY ENGINE — V24.2 / 7-SCENE PILOT

هذا اختبار مصغر للحلقة الكاملة: **خطة واحدة + Edit Bible واحدة + أول 7 مشاهد مترابطة**.

## ما الذي يختبره؟
- Gemini 3.1 Pro عبر **agy الموجود أصلًا في بيئة GitHub/Antigravity**.
- Episode Edit Bible موحدة للحلقة.
- Scene Directives وBeat Plan.
- Media Scout + Vision Scout.
- Gemini TTS.
- Groq Whisper word timing للترجمة.
- FFmpeg 1080p/30fps/H.264/AAC.
- دمج المشاهد السبعة في Master MP4.
- OpenTimelineIO أو JSON fallback.
- Thumbnail.

## مهم جدًا: agy
الاختبار **لا يثبت agy ولا يحدثه ولا يعيد تهيئته ولا يعدل PATH**.

يفترض أن `agy` متاح أصلًا في بيئة GitHub/Antigravity التي تستخدمها. الـworkflow يكتفي بالتحقق من وجود الأمر ثم يستخدمه كما هو.

الأوامر التي **لا توجد** في هذا الاختبار:
- `npm install agy`
- أي `curl | sh` لتثبيت Antigravity
- أي تحديث تلقائي لـ agy
- أي تعديل لـ PATH
- أي إعادة تسجيل دخول أو إعادة تهيئة لـ agy

## Secrets
أضف في Repository Secrets:
- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `PEXELS_API_KEY`
- `PIXABAY_API_KEY`
- `FREESOUND_API_KEY`

لا تضع المفاتيح داخل الكود.

## التشغيل
1. ارفع محتويات هذا المجلد إلى المستودع.
2. افتح GitHub → Actions.
3. اختر `V24.2 — 7 Scene Pilot Test`.
4. اختر `Run workflow`.
5. اكتب موضوع الاختبار.
6. بعد انتهاء الـworkflow حمّل Artifact باسم `V24.2-7scene-pilot`.

## النتيجة
سيتم تنفيذ أول 7 مشاهد من **خطة واحدة**، وليس 7 prompts منفصلة. الهدف هو تقييم:
- الاستمرارية البصرية
- الإيقاع
- كثافة المعلومات والمرئيات
- الترجمة والتوقيت
- الصوت وFoley
- جودة الـFFmpeg render
- تماسك المخرج بين المشاهد

هذا اختبار إنتاجي مصغر فقط؛ لا يرفع إلى YouTube أو Google Drive.
