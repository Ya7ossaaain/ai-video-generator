# 🎬 LEMMiNO Hybrid Documentary Engine

محرك إنتاج الأفلام الوثائقية الاستقصائية الآلي الهجين (End-to-End Automated Pipeline) المصمم لمحاكاة الهوية البصرية والإخراجية لقناة **LEMMiNO** (*Noir Minimalist, Cel-Shaded/Wireframe 3D, GIS Vector Maps, Kinetic HUD, Archival Forensics*).

---

## 🏗️ الهيكل المعماري المعياري (Modular Multi-File Architecture)

```text
├── .github/workflows/
│   └── production.yml                 # إعداد البيئة، تحرير المساحة (~30GB)، التوثيق، والتشغيل
├── main.py                            # نقطة الدخول الرئيسية ومنسق المراحل (Orchestrator)
├── engine/
│   ├── __init__.py
│   ├── config.py                      # إعدادات النظام، المسارات، وقراءة المتغيرات البيئية
│   ├── telemetry.py                   # نظام السجلات الاحترافي (Logger) وأدوات فحص ffprobe
│   ├── agy_client.py                  # غلاف استدعاء أداة الطرفية agy مع إدارة الحصة (Strict Quota Law)
│   ├── forensic_harvester.py          # جامع الأدلة والوثائق والصور المسبق (قبل السيناريو)
│   ├── script_writer.py               # كاتب السيناريو المبني على الأدلة المحصودة (8 فصول)
│   ├── audio_studio.py                # تدوير المفاتيح العشرة، توليد TTS (Charon)، ومزامنة Groq Whisper
│   ├── visual_director.py             # المخرج الذكي لتوزيع المشاهد (30% 3D / 60% Remotion / 10% Scanner)
│   ├── blender_runner.py              # مشغل محركات Blender CLI وإدارة الرندر ثلاثي الأبعاد
│   ├── remotion_runner.py             # مشغل قوالب Remotion CLI وتمرير الـ Props
│   ├── compositor.py                  # الدمج الهجين، المؤثرات البصرية، الترجمة ASS، والتجميع النهائي
│   └── cloud_uploader.py              # الرفع التلقائي إلى Google Drive و YouTube
├── blender_scripts/                   # سكربتات بايثون الخاصة بـ Blender Headless
│   ├── normalize_assets.py            # توحيد أبعاد ونقاط ارتكاز المجسمات وبناء الفهرس
│   ├── scene_wireframe_turntable.py   # محرك المجسمات الشبكية والـ Clay مع الإضاءة الحمراء
│   ├── scene_25d_parallax.py          # محرك تحويل الصور الأرشيفية إلى طبقات 2.5D مع الضباب
│   └── scene_terrain_ocean.py         # محرك التضاريس الجغرافية ثلاثية الأبعاد والأمواج
├── remotion-documentary/              # مشروع React/TypeScript الكامل للموشن جرافيك
│   ├── package.json
│   ├── public/maps/                   # ملفات GeoJSON والخطوط
│   └── src/
│       ├── index.ts
│       ├── Root.tsx
│       └── components/
│           ├── VectorMapTracker.tsx   # تتبع المسارات الجغرافية، الرادار، ومناطق البحث
│           ├── ForensicDossier.tsx    # ملفات المشتبه بهم وشبكة استعراض الأدلة (Grid)
│           ├── HudOverlay.tsx         # طبقة البيانات التفاعلية الشفافة لتركيبها فوق فيديو Blender
│           ├── DocumentScanner.tsx    # فحص الوثائق وتمرير شريط التظليل الأحمر (Highlighter)
│           ├── TimelineComparison.tsx # الخطوط الزمنية المتفرعة ومقارنة الصور (Before/After)
│           └── ChapterCard.tsx        # بطاقات الفصول السينمائية وتتر النهاية
└── assets/
    ├── models/                        # حقيبة المجسمات ثلاثية الأبعاد (25 مجسماً .glb) + models_catalog.json
    ├── intro.mp4                      # مقدمة القناة (يتم الحفاظ عليها)
    └── logo.png                       # شعار القناة (يتم الحفاظ عليه)
```
