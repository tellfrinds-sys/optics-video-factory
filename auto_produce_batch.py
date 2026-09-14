# -*- coding: utf-8 -*-
"""auto_produce_batch.py — ينتج دفعة دروس بلا اعتماد بشري على تليجرام (مؤقتًا، بطلب صريح من المستخدم).

يعيد استخدام نفس منطق الكتابة والمراجعة في prepare_lesson.prepare() (كتابة Gemini + مراجعة
+ فحص التشكيل tashkeel_qa المدمج في agents.review_script، بمحاولتين إضافيتين عند الفشل)،
لكن بدل إرسال بطاقة تليجرام والانتظار: لو المراجعة رجعت "pass" يُعتمد السكريبت تلقائيًا
ويبدأ الإنتاج فورًا. لو ما وصلتش لـ"pass" بعد 3 محاولات، يتوقف ويُعلّم الدرس
"needs_human_review" بدل ما ينشر محتوى لم يجتز بوابة الجودة نفسها.

الاستخدام:  python3 auto_produce_batch.py 100003 100004 100005
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, "/root/video-factory/pipeline")
sys.path.insert(0, "/root/video-factory")


def _env():
    f = "/root/video-factory/pipeline/.env"
    for ln in open(f, encoding="utf-8"):
        if "=" in ln and not ln.strip().startswith("#"):
            k, v = ln.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_env()

import agents
import prepare_lesson
import produce_lesson


def auto_produce_lesson(lesson_uid: int, bookend_set="V5") -> dict:
    L = prepare_lesson._fetch_lesson(lesson_uid)
    print(f"== lesson {lesson_uid} ({L['title_ar']}) ==", flush=True)

    notes, review, fs = "", None, None
    for attempt in (1, 2, 3):
        fs = agents.write_script(L, extra_notes=notes)
        review = agents.review_script(fs, L)
        verdict = str(review.get("verdict", "")).lower()
        print(f"  attempt {attempt}: verdict={verdict} score={review.get('score')}", flush=True)
        if verdict == "pass":
            break
        notes = ("\n".join("• " + x for x in (review.get("must_fix") or [])) +
                 "\nنقاط ناقصة: " + " / ".join(review.get("coverage_gaps") or []))
    fs["_review"] = review
    verdict = str(review.get("verdict", "")).lower()

    out_text = json.dumps({"final_script": fs, "status": "PASS" if verdict == "pass" else "NEEDS_REVIEW",
                            "review": review}, ensure_ascii=False)
    body = {"lesson_uid": lesson_uid, "stage_code": "SCRIPT_FINAL", "prompt_binding_uid": "820006",
            "revision_no": int(time.time()), "output_text": out_text, "output_hash": "",
            "model_used": "gemini-3.6-flash + qwen2.5:7b (auto, no-telegram)",
            "approval_status": "approved" if verdict == "pass" else "changes_requested"}
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(url + "/rest/v1/content_outputs", data=json.dumps(body).encode(),
                                  method="POST", headers={"apikey": key, "Authorization": "Bearer " + key,
                                  "Content-Type": "application/json", "Prefer": "return=representation"})
    urllib.request.urlopen(req, timeout=30).read()

    if verdict != "pass":
        print(f"!! lesson {lesson_uid}: لم يجتز المراجعة بعد 3 محاولات -- توقّف، يحتاج مراجعة بشرية", flush=True)
        return {"status": "needs_human_review", "lesson_uid": lesson_uid, "review": review}

    print(f"-- السكريبت PASS ({review.get('score')}/100) -- اعتماد تلقائي، بدء الإنتاج", flush=True)

    res = produce_lesson.produce({
        "video_uid": L["video_uid"], "lesson_uid": lesson_uid,
        "lesson_code": L["lesson_code"], "scenes": fs["scenes"],
        "title": L["title_ar"], "bookend_set": bookend_set,
    })
    print(json.dumps({k: v for k, v in res.items() if k != "heal_log"}, ensure_ascii=False, indent=1), flush=True)
    return res


if __name__ == "__main__":
    ids = [int(x) for x in sys.argv[1:]] or [100003, 100004, 100005]
    results = []
    for lu in ids:
        try:
            results.append(auto_produce_lesson(lu))
        except Exception as e:
            import traceback
            print("ERROR on", lu, e, flush=True)
            traceback.print_exc()
            results.append({"status": "error", "lesson_uid": lu, "detail": str(e)})
    print("=== SUMMARY ===", flush=True)
    for r in results:
        print(r.get("lesson_uid"), r.get("status"), r.get("qa_verdict"), flush=True)
