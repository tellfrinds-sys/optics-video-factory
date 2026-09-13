# -*- coding: utf-8 -*-
import json, sys
sys.path.insert(0, "/root/video-factory/pipeline")
import agents

L = {
    "lesson_code": "B02-U01-C02-L02",
    "lesson_uid": 100021,
    "video_uid": 500128 + (100021 - 100001),
    "title_ar": "العدسات المحدبة والمقعرة ومسارات الأشعة",
    "learning_goal": "أن يشرح المتعلم موضوع «العدسات المحدبة والمقعرة ومسارات الأشعة» ويطبقه ضمن نطاق الممارسة وبمعيار السلامة المناسب.",
    "level": "تأسيسي",
    "duration_minutes": 8,
    "professional_scope_note": "يُستخدم المحتوى لفهم القياس والتجهيز البصري، ولا يحل محل التدريب العملي المعتمد.",
    "sources_text": (
        "- ISO 13666:2019 Spectacle lenses — Vocabulary (S010): تعريفات قياسية لأنواع العدسات "
        "(محدّبة/مقعّرة، متجمّعة/مفرّقة) والمصطلحات البصرية المرتبطة بها.\n"
        "- ISO 8624:2020 Spectacle frames — Measuring system and vocabulary (S012): مصطلحات قياس "
        "العدسات والإطارات ذات الصلة."
    ),
}

prev = json.load(open("/root/video-factory/outputs/_status/pilot_100021_script.json", encoding="utf-8"))
review1 = prev["review"]
notes = "\n".join("• " + x for x in (review1.get("must_fix") or []))
notes += "\nنقاط ناقصة: " + " / ".join(review1.get("coverage_gaps") or [])
notes += "\nالرسم لازم يكون مخصص لمسارات الأشعة في العدسات المحدبة/المقعرة، مش eye عام."
print("NOTES_SENT_TO_WRITER:\n" + notes[:800])

fs = agents.write_script(L, extra_notes=notes)
print("SCENES_WRITTEN:", len(fs.get("scenes", [])))

review2 = agents.review_script(fs, L)
print("=== REVIEW RESULT (attempt 2) ===")
print(json.dumps({
    "verdict": review2["verdict"],
    "score": review2["score"],
    "word_count_estimate": review2["word_count_estimate"],
    "dialect_violations": review2["dialect_violations"],
    "tashkeel_violations": review2["tashkeel_violations"],
    "auto_fixed": review2["auto_fixed"],
    "must_fix": review2["must_fix"],
    "reviewers": review2["reviewers"],
}, ensure_ascii=False, indent=1))

with open("/root/video-factory/outputs/_status/pilot_100021_script_attempt2.json", "w", encoding="utf-8") as f:
    json.dump({"final_script": fs, "review": review2}, f, ensure_ascii=False, indent=1)
print("SAVED_ATTEMPT2_OK")
