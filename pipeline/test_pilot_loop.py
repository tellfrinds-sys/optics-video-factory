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

MAX_ATTEMPTS = 6
notes = ""
fs, review = None, None
history = []

for attempt in range(1, MAX_ATTEMPTS + 1):
    print("=== ATTEMPT %d ===" % attempt, flush=True)
    fs = agents.write_script(L, extra_notes=notes)
    review = agents.review_script(fs, L)
    verdict = review.get("verdict")
    score = review.get("score")
    n_tashkeel = len(review.get("tashkeel_violations") or [])
    n_dialect = len(review.get("dialect_violations") or [])
    print("verdict=%s score=%s tashkeel_issues=%d dialect_issues=%d wc=%s" % (
        verdict, score, n_tashkeel, n_dialect, review.get("word_count_estimate")), flush=True)
    history.append({"attempt": attempt, "verdict": verdict, "score": score,
                     "tashkeel_issues": n_tashkeel, "dialect_issues": n_dialect,
                     "must_fix": review.get("must_fix")})
    if verdict == "pass":
        print("PASSED at attempt", attempt, flush=True)
        break
    notes = "\n".join("• " + x for x in (review.get("must_fix") or []))
    gaps = review.get("coverage_gaps") or []
    if gaps:
        notes += "\nنقاط ناقصة: " + " / ".join(gaps)
    notes += "\nالرسم لازم يكون مخصص لمسارات الأشعة في العدسات المحدبة/المقعرة، مش eye عام."
else:
    print("DID_NOT_PASS after", MAX_ATTEMPTS, "attempts", flush=True)

with open("/root/video-factory/outputs/_status/pilot_100021_loop_history.json", "w", encoding="utf-8") as f:
    json.dump(history, f, ensure_ascii=False, indent=1)
with open("/root/video-factory/outputs/_status/pilot_100021_final.json", "w", encoding="utf-8") as f:
    json.dump({"final_script": fs, "review": review}, f, ensure_ascii=False, indent=1)
print("DONE")
