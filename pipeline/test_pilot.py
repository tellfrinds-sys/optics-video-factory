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
print("LESSON_READY:", L["title_ar"])

fs = agents.write_script(L)
print("SCENES_WRITTEN:", len(fs.get("scenes", [])))

review = agents.review_script(fs, L)
print("=== REVIEW RESULT ===")
print(json.dumps({
    "verdict": review["verdict"],
    "score": review["score"],
    "word_count_estimate": review["word_count_estimate"],
    "dialect_violations": review["dialect_violations"],
    "tashkeel_violations": review["tashkeel_violations"],
    "auto_fixed": review["auto_fixed"],
    "must_fix": review["must_fix"],
    "reviewers": review["reviewers"],
}, ensure_ascii=False, indent=1))

import os
os.makedirs("/root/video-factory/outputs/_status", exist_ok=True)
with open("/root/video-factory/outputs/_status/pilot_100021_script.json", "w", encoding="utf-8") as f:
    json.dump({"final_script": fs, "review": review}, f, ensure_ascii=False, indent=1)
print("SAVED_SCRIPT_OK")
