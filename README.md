# V24 Professional Single-Scene GitHub Test

هذا المستودع يختبر **مشهدًا واحدًا فقط** من محرك الوثائقي V24:

1. توليد خطة مشهد واحدة.
2. Gemini TTS بصوت Charon.
3. Groq Whisper word timestamps.
4. جلب وسيط حقيقي تلقائيًا من المصادر المتاحة.
5. FFmpeg Professional Render.
6. منع إعادة تشغيل الفيديو عند انتهاء المصدر؛ يتم تثبيت آخر إطار بدل التكرار.
7. حرق الترجمة العربية داخل الفيديو.
8. رفع MP4 وASS وJSON والـlogs كـ GitHub Artifacts.

## GitHub Secrets

أضف من **Settings → Secrets and variables → Actions**:

- `GEMINI_API_KEY` — مطلوب. يمكن وضع عدة مفاتيح مفصولة بفاصلة.
- `GROQ_API_KEY` — مطلوب للترجمة المتزامنة.
- `PEXELS_API_KEY` — اختياري، لكنه مفيد لجلب فيديو حقيقي.
- `PIXABAY_API_KEY` — اختياري.
- `FREESOUND_API_KEY` — اختياري.

لا تضع المفاتيح داخل الملفات أو الكود.

## التشغيل

Actions → **V24 Professional Single Scene Test** → Run workflow → اكتب موضوع الاختبار → Run.

الافتراضي:

`لغز اختفاء طائرة`

بعد الانتهاء افتح **Artifacts** وحمّل `scene-test-output`.

> في GitHub Actions لا يوجد تسجيل دخول تفاعلي إلى Antigravity. لذلك يستخدم الاختبار `agy` إذا توفر، وإلا يستخدم Gemini API لإنتاج خطة المشهد. بقية مسار TTS → Groq → Media → FFmpeg هو مسار الاختبار الحقيقي.
