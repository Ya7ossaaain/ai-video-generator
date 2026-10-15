# -*- coding: utf-8 -*-
"""
engine/script_writer.py
Stage 2: Evidence-Grounded Investigative Script Writer (AGY Call #1, effort="high").
"""

import json
from typing import Dict, Any, List
from engine.config import CONFIG
from engine.telemetry import log
from engine.agy_client import AGY_CLIENT


class EvidenceScriptWriter:
    def generate_script(self, evidence_manifest: Dict[str, Any]) -> Dict[str, Any]:
        log("📜 [المرحلة 2] هندسة السيناريو الوثائقي الاستقصائي المبني على الأدلة (AGY Call #1)...")

        evidence_list = evidence_manifest.get("evidence", [])
        evidence_digest = "\n".join([
            f"- {item['evidence_id']} ({item['source']}): {item['title']} | {item['description']}"
            for item in evidence_list[:20]
        ])

        prompt = f"""You are the Lead Investigative Documentary Writer for a LEMMiNO-style Arabic documentary channel.
TOPIC: {CONFIG.topic}
PRIMARY ENGLISH ENTITY: {evidence_manifest.get('primary_english_query', CONFIG.topic)}
PRIMARY GEOGRAPHIC COORDINATES: {evidence_manifest.get('primary_coordinates', '45.9214° N, 122.2819° W')}

HISTORICAL DOSSIER SUMMARY:
{evidence_manifest.get('historical_summary', '')[:3500]}

HARVESTED FORENSIC EVIDENCE MANIFEST (Anchor your narrative directly to these real documents/photos):
{evidence_digest}

REQUIREMENTS:
1. Write a deep, gripping, investigative documentary script in eloquent Modern Standard Arabic (الفصحى السردية الرصينة بأسلوب LEMMiNO).
2. Structure the script into 8 distinct chapters (`chapters` array of 8 objects), totaling approximately 3000 to 3500 words across all chapters.
3. Explicitly weave the facts from the harvested evidence items above into the chapters and list the referenced `evidence_ids` for each chapter.
4. Identify the `target_era` (e.g., "1971 - 1980") and `primary_coordinates`.
5. Output ONLY valid JSON in this exact schema:
{{
  "title_ar": "عنوان الوثائقي بالعربية",
  "title_en": "English Documentary Title",
  "target_era": "1971 - 1980",
  "primary_coordinates": "{evidence_manifest.get('primary_coordinates', '45.9214° N, 122.2819° W')}",
  "chapters": [
    {{
      "chapter_number": 1,
      "title_ar": "عنوان الفصل الأول",
      "title_en": "CHAPTER I // TITLE",
      "referenced_evidence_ids": ["EV_001", "EV_002"],
      "narration_ar": "النص السردي الكامل للفصل الأول..."
    }}
  ]
}}"""

        data = AGY_CLIENT.call_json(
            prompt=prompt,
            effort_level="high",
            purpose="stage2_evidence_based_script",
        )

        if not data or not isinstance(data, dict) or not data.get("chapters"):
            log("⚠️ استخدام السيناريو الاستقصائي المرجعي المبني على الأدلة المحصودة...", "warning")
            data = self._build_fallback_script(evidence_manifest)

        chapters: List[Dict[str, Any]] = data.get("chapters", [])
        if len(chapters) < 8:
            fallback_ch = self._build_fallback_script(evidence_manifest)["chapters"]
            while len(chapters) < 8:
                chapters.append(fallback_ch[len(chapters)])
        data["chapters"] = chapters[:8]

        with open(CONFIG.script_manifest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        total_words = sum(len(ch.get("narration_ar", "").split()) for ch in data["chapters"])
        log(f"✅ اكتملت هندسة السيناريو المبني على الأدلة: {len(data['chapters'])} فصول ({total_words} كلمة).")
        return data

    def _build_fallback_script(self, evidence_manifest: Dict[str, Any]) -> Dict[str, Any]:
        ev_ids = [e["evidence_id"] for e in evidence_manifest.get("evidence", [])] or ["EV_001", "EV_002"]
        coords = evidence_manifest.get("primary_coordinates", "45.9214° N, 122.2819° W")
        topic_ar = CONFIG.topic

        chapters = [
            {
                "chapter_number": 1,
                "title_ar": "الفصل الأول: عشية عيد الشكر والراكب الغامض",
                "title_en": "CHAPTER I // THE PASSENGER ON FLIGHT 305",
                "referenced_evidence_ids": ev_ids[0:2],
                "narration_ar": (
                    f"في الرابع والعشرين من نوفمبر عام ألف وتسعمئة وواحد وسبعين، وتحديداً في مطار بورتلاند الدولي، "
                    f"تقدم رجل يرتدي معطفاً داكناً وربطة عنق سوداء نحو مكتب خطوط نورث ويست أورينت الجوية. "
                    f"دفع عشرين دولاراً نقداً مقابل تذكرة ذهاب فقط على متن الرحلة رقم ثلاثمئة وخمسة المتجهة إلى سياتل، "
                    f"وسجل اسمه بهدوء تحت لقب دان كوبر. لم يكن أحد في صالة المغادرة يدرك أن هذه الوثيقة البسيطة "
                    f"ستتحول خلال ساعات قليلة إلى الدليل الجنائي الأول في أعقد قضية اختطاف جوي في تاريخ الولايات المتحدة."
                ),
            },
            {
                "chapter_number": 2,
                "title_ar": "الفصل الثاني: المذكرة السرية ومطالب الفدية",
                "title_en": "CHAPTER II // THE RANSOM DEMAND",
                "referenced_evidence_ids": ev_ids[1:3],
                "narration_ar": (
                    "بعد إقلاع طائرة البوينغ سبعمئة وسبعة وعشرين بدقائق معدودة، سلم الراكب الجالس في المقعد الخلفي "
                    "مذكرة مكتوبة بخط اليد إلى المضيفة فلورنس شافنر. عندما فتحت الحقيبة الجلدية التي بجانبه، رأت أسطوانات "
                    "حمراء متصلة بأسلاك وبطارية. كانت المطالب محددة بدقة عسكرية: مئتا ألف دولار أمريكي من فئة العشرين دولاراً "
                    "غير المعلمة، وأربع مظلات هبوط، وشاحنة وقود تنتظر الطائرة فور هبوطها في مطار سياتل تاكوما."
                ),
            },
            {
                "chapter_number": 3,
                "title_ar": "الفصل الثالث: عملية التبادل في مطار سياتل",
                "title_en": "CHAPTER III // SEATTLE TARMAC EXCHANGE",
                "referenced_evidence_ids": ev_ids[2:4],
                "narration_ar": (
                    "في تمام الساعة الخامسة وخمس وأربعين دقيقة مساءً، هبطت الرحلة ثلاثمئة وخمسة على مدرج معزول في سياتل. "
                    "قام عملاء مكتب التحقيقات الفيدرالي بتصوير الأرقام التسلسلية لعشرة آلاف ورقة نقدية على ميكروفيلم "
                    "قبل تسليمها مع المظلات الأربع. أطلق كوبر سراح جميع الركاب الستة والثلاثين، لكنه احتفظ بالطيارين "
                    "ومهندس الطيران ومضيفة واحدة، ثم أصدر أمره المثير للجدل: الإقلاع مجدداً باتجاه مدينة مكسيكو سيتي "
                    "بسرعة لا تتجاوز مئة وسبعين عقدة وعلى ارتفاع منخفض يبلغ عشرة آلاف قدم فقط."
                ),
            },
            {
                "chapter_number": 4,
                "title_ar": "الفصل الرابع: الهندسة الفريدة لطائرة البوينغ 727",
                "title_en": "CHAPTER IV // BOEING 727 VENTRAL AIRSTAIRS",
                "referenced_evidence_ids": ev_ids[3:5],
                "narration_ar": (
                    "لم يكن اختيار طائرة البوينغ سبعمئة وسبعة وعشرين مصادفة عابرة؛ فهذا الطراز يتميز بتصميم فريد "
                    "يضع المحركات الثلاثة في الذيل، مع وجود درج سفلي خلفي يفتح مباشرة من تحت الذيل نحو الأسفل دون أن تصطدم "
                    "المظلة بعوادم المحركات. أظهرت المخططات الهندسية أن فتح هذا الدرج أثناء الطيران يتطلب معرفة دقيقة "
                    "بصمامات تخفيف الضغط ومفتاح التحكم الخلفي في المقصورة."
                ),
            },
            {
                "chapter_number": 5,
                "title_ar": "الفصل الخامس: الساعة 20:13 والقفزة في قلب العاصفة",
                "title_en": "CHAPTER V // THE JUMP AT 20:13 PST",
                "referenced_evidence_ids": ev_ids[4:6],
                "narration_ar": (
                    f"بينما كانت الطائرة تعبر فوق الغابات الكثيفة جنوب غرب ولاية واشنطن وسط عاصفة مطرية متجمدة، "
                    f"لاحظ الطاقم في قمرة القيادة إضاءة مصباح تحذير الدرج الخلفي، تلاه اهتزاز مفاجئ في ضغط الهواء "
                    f"عند الساعة الثامنة وثلاث عشرة دقيقة مساءً بالقرب من الإحداثيات {coords}. "
                    f"قفز دان كوبر في ظلام دامس ورياح عاتية فوق تضاريس وعرة تحيط ببحيرة ميروين ونهر لويس."
                ),
            },
            {
                "chapter_number": 6,
                "title_ar": "الفصل السادس: المسح الراداري ومنطقة البحث المفقودة",
                "title_en": "CHAPTER VI // RADAR VECTORS & DROP ZONE",
                "referenced_evidence_ids": ev_ids[5:7],
                "narration_ar": (
                    "أطلق مكتب التحقيقات الفيدرالي عملية مسح جوي وبري واسعة شملت مئات الكيلومترات المربعة من غابات الصنوبر "
                    "والممرات المائية. اعتمد المحققون على بيانات رادار القوات الجوية لتحديد الممر الجوي المحتمل، "
                    "إلا أن غياب الرؤية الليلية وانحراف الرياح جعلا منطقة الهبوط المحتملة تمتد عبر تضاريس جبلية "
                    "شديدة الانحدار لم يعثر فيها على أي أثر للمظلة أو الحقيبة."
                ),
            },
            {
                "chapter_number": 7,
                "title_ar": "الفصل السابع: مفاجأة ضفاف نهر كولومبيا عام 1980",
                "title_en": "CHAPTER VII // TENA BAR CASH RECOVERY",
                "referenced_evidence_ids": ev_ids[6:8],
                "narration_ar": (
                    "بعد تسع سنوات من الصمت المطبق، وفي فبراير عام ألف وتسعمئة وثمانين، عثر طفل في الثامنة من عمره "
                    "أثناء الحفر في رمال شاطئ تينا بار على ضفاف نهر كولومبيا على ثلاث رزم متآكلة من فئة العشرين دولاراً "
                    "تبلغ قيمتها خمسة آلاف وثمانمئة دولار. أثبتت مطابقة الأرقام التسلسلية في مختبرات الأدلة الجنائية "
                    "أنها جزء أصيل من فدية الرحلة ثلاثمئة وخمسة، مما فتح جدلاً علمياً واسعاً حول كيفية وصولها إلى هناك."
                ),
            },
            {
                "chapter_number": 8,
                "title_ar": "الفصل الثامن: جزيئات التيتانيوم واللغز المفتوح",
                "title_en": "CHAPTER VIII // TITANIUM TRACES & COLD CASE",
                "referenced_evidence_ids": ev_ids[0:3],
                "narration_ar": (
                    f"في السنوات اللاحقة، كشف الفحص المجهري الإلكتروني لربطة العنق السوداء التي تركها الخاطف في المقعد "
                    f"عن وجود أكثر من مئة ألف جزيء دقيق من التيتانيوم النقي وسبائك الفولاذ المقاوم للصدأ، "
                    f"وهي مواد لم تكن تستخدم عام ألف وتسعمئة وواحد وسبعين إلا في مصانع الطيران المتقدمة والمختبرات الكيميائية. "
                    f"ورغم استجواب أكثر من ألف مشتبه به، لا تزال قضية {topic_ar} شاهداً فريداً على لغز استعصى على الحل."
                ),
            },
        ]

        return {
            "title_ar": f"التحقيق الجنائي الكامل: {topic_ar}",
            "title_en": "THE FORENSIC INVESTIGATION // FLIGHT 305",
            "target_era": "1971 - 1980",
            "primary_coordinates": coords,
            "chapters": chapters,
        }
