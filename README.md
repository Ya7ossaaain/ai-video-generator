# V24.2 — 7 Scene Pilot FIXED

هذا الإصدار يعالج مشاكل اختبار الـ7 مشاهد السابقة.

## الإصلاحات الرئيسية

1. **FFmpeg / zoompan**
   - أزيلت تعبيرات `t` الهشة التي سببت:
     `Undefined constant or missing '(' in 't,1.10)'`
   - الحركة الآن تعتمد على متغيرات `zoompan` المدعومة (`zoom` / `on`) مع `d=1`.
   - يوجد fallback ثابت آمن إذا فشل filter لأي سبب، حتى لا يسقط المشهد بالكامل.

2. **الترجمة العربية / ASS**
   - تطبيع Unicode باستخدام NFC.
   - معالجة المسافات غير المرئية وبعض علامات الاقتباس والشرطات والرموز الخاصة.
   - الحفاظ على العربية في ترتيبها المنطقي وترك FriBidi/libass يتوليان RTL والشكل العربي.
   - حماية `{}` و `\\` من التحول إلى ASS override tags.
   - تثبيت Noto Sans Arabic على GitHub runner.

3. **مدة الاختبار**
   - الـSHOWRUNNER مطالب بـ95–125 كلمة عربية تقريباً لكل مشهد.
   - 7 مشاهد مترابطة، وليس 7 prompts منفصلة.
   - الاختبار يستهدف تقريباً 4–6 دقائق، مع حد فشل عند أقل من 4 دقائق.

4. **Gemini TTS**
   - تدوير مفاتيح API.
   - backoff مختلف لـ429 و503.
   - عدم إعادة إرسال الطلبات بسرعة عند RESOURCE_EXHAUSTED / UNAVAILABLE.

5. **الكاش**
   - لا يعاد استخدام manifest قديم بدون `beat_plan` صالح.
   - بصمة المشهد مرتبطة بالنص والاستعلام ونوع الوسيط.

6. **Final verification**
   - الملف النهائي اسمه ثابت:
     `output_build/final_documentary.mp4`
   - GitHub لا يعتبر وجود أي MP4 آخر نجاحاً؛ يجب أن يوجد الملف النهائي نفسه ويكون قابلاً للقراءة بـffprobe.
   - الاختبار يفشل إذا لم يتم رندر المشاهد السبعة كلها.

7. **Thumbnail**
   - معطل افتراضياً في هذا الـpilot حتى لا تستهلك طلبات Gemini في شيء لا نحتاجه للحكم على جودة المونتاج.

## Antigravity / AGY_CREDENTIALS

الـworkflow يستخدم نفس نمط العمل الصحيح:

- تثبيت `agy` داخل GitHub runner المؤقت فقط.
- قراءة `AGY_CREDENTIALS` من GitHub Secrets.
- إنشاء `~/.gemini/antigravity-cli/antigravity-oauth-token` داخل runner.
- لا يتم تعديل `agy` الموجود عند المستخدم في Termux أو Ubuntu.

Secrets المطلوبة:

- `AGY_CREDENTIALS`
- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `PEXELS_API_KEY`
- `PIXABAY_API_KEY`
- `FREESOUND_API_KEY`

## تشغيل الاختبار

شغّل:

`.github/workflows/v24-2-7scene-test.yml`

ثم اختر `topic` وشغّل workflow.
