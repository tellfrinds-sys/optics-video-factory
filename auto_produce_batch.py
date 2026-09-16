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


def _hash(s: str) -> str:
    """نفس دالة prepare_lesson._hash -- output_hash عليه قيد تفرّد عام في الجدول،
    فإرسال '' لأكثر من صف يسبب 409 Conflict من الصف الثاني فصاعدًا (خطأ لوحظ فعليًا)."""
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return "h%x_%d" % (h, len(s))

import agents
import prepare_lesson
import produce_lesson


def _next_pending_lessons(n: int = 5) -> list[int]:
    """نقطة الاستكمال (checkpoint): بيجيب أول N دروس لسه محتاجة إنتاج (video_status مش
    ready) بترتيب lesson_uid -- بيقرأها مباشرة من جدول lessons نفسه، اللي هو أصلًا سجل
    التقدم الحقيقي والدائم (بيتحدّث تلقائيًا مع كل إنتاج ناجح عبر produce_lesson.produce()).
    كده أي تشغيلة جديدة تكمل من حيث ما توقفت آخر تشغيلة، من غير ما حد يفتكر يدويًا آخر رقم
    درس اتنتج، ولا يحتاج يعيد كتابة الدروس اللي خلصت. لو درس اتحاول قبل كده وفشل (زي فشل
    نفاد رصيد Gemini) هيفضل video_status له فاضي (null) بالظبط زي درس لسه ما اتحاولش،
    فهيتحاول تاني تلقائيًا من غير خطوة يدوية منفصلة."""
    url = os.environ["SUPABASE_URL"]; key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(
        url + "/rest/v1/lessons?or=(video_status.is.null,video_status.neq.ready)"
              f"&select=lesson_uid&order=lesson_uid&limit={n}",
        headers={"apikey": key, "Authorization": "Bearer " + key})
    rows = json.loads(urllib.request.urlopen(req, timeout=30).read())
    return [r["lesson_uid"] for r in rows]


# تدوير المقدمة/الخاتمة (bookend) بين النسخ المتاحة فعليًا -- لوحظ إن كل الدروس كانت
# بتستخدم V5 فقط رغم وجود V2/V3/V4 جاهزين على القرص وغير مستخدمين خالص (نفس الملابس/الخلفية
# في كل فيديو متتالي، بتوجيه صريح من المسؤول: يجب التنويع، مفيش فيديوهين متتاليين بنفس المقدمة).
BOOKEND_SETS = ["V2", "V3", "V4", "V5"]


def _bookend_for(lesson_uid: int) -> str:
    return BOOKEND_SETS[lesson_uid % len(BOOKEND_SETS)]


def auto_produce_lesson(lesson_uid: int, bookend_set=None) -> dict:
    if bookend_set is None:
        bookend_set = _bookend_for(lesson_uid)
    L = prepare_lesson._fetch_lesson(lesson_uid)
    print(f"== lesson {lesson_uid} ({L['title_ar']}) ==", flush=True)

    notes, review, fs = "", None, None
    best_fs, best_review, best_score = None, None, -1
    for attempt in (1, 2):  # تقليص 3->2 (2026-09-16, توجيه صريح بعد تفعيل فوترة): اقتصاد صارم في استهلاك Gemini وCartesia -- تراجع جودة الإلقاء 6-10 مرة اتحل فعليًا بالموديل الأرخص للتدقيق الإملائي مش عدد المحاولات نفسه
        # التقارب لكن بيقصّر فرصة تنقية اللهجة/التشكيل، وده اللي سبب تراجع جودة الإلقاء
        # الملحوظ فعليًا في دروس 6-10 -- التكلفة كانت أساسًا اتحلّت بالموديل الأرخص
        # للتدقيق الإملائي وليس بتقليل عدد المحاولات نفسه.
        try:
            fs = agents.write_script(L, extra_notes=notes)
            fs["scenes"] = agents.proofread_scenes(fs["scenes"])  # تدقيق إملائي ضيّق قبل المراجعة الشاملة
            review = agents.review_script(fs, L)
        except Exception as e:
            # فشل عابر في محاولة واحدة (زي قطع JSON بسبب MAX_TOKENS -- لوحظ فعليًا بعد
            # التحويل لـ gemini-3-flash-preview) مايستاهلش يفقدنا الدرس كله؛ نعتبرها محاولة
            # فاشلة بأقل درجة وننتقل للمحاولة التالية بدل ما نكسر auto_produce_lesson بالكامل.
            print(f"  attempt {attempt}: فشل عابر -- {e}", flush=True)
            review = {"verdict": "fail", "score": -1}
            if fs is None:
                continue
        verdict = str(review.get("verdict", "")).lower()
        print(f"  attempt {attempt}: verdict={verdict} score={review.get('score')} "
              f"wc={review.get('word_count_estimate')}", flush=True)
        if verdict == "pass":
            break
        # لا تفقد أفضل محاولة سابقة -- إعادة التوليد الكاملة غير مستقرة (لوحظ فعليًا: محاولة
        # بدرجة 82 تلتها محاولة بدرجة 68 لنفس الدرس)، فنحتفظ بالأعلى درجة كاحتياطي.
        score = review.get("score") or 0
        if score > best_score:
            best_fs, best_review, best_score = json.loads(json.dumps(fs)), review, score
        notes = ("\n".join("• " + x for x in (review.get("must_fix") or [])) +
                 "\nنقاط ناقصة: " + " / ".join(review.get("coverage_gaps") or []))

    if fs is None:
        print(f"!! lesson {lesson_uid}: كل المحاولات فشلت فشلًا عابرًا (أخطاء اتصال/تحليل JSON) -- توقّف", flush=True)
        return {"status": "error", "lesson_uid": lesson_uid, "detail": "all attempts raised exceptions"}

    verdict = str(review.get("verdict", "")).lower()
    if verdict != "pass" and best_score > (review.get("score") or 0):
        print(f"  استخدام أفضل محاولة سابقة (score={best_score}) بدل آخر محاولة "
              f"(score={review.get('score')})", flush=True)
        fs, review = best_fs, best_review
        verdict = str(review.get("verdict", "")).lower()
    # حل أخير حتمي: استبدال/حذف أي كلمة لسه عالقة بدل التوقف الكامل (بتوجيه صريح من
    # المسؤول: تقليل بسيط في عدد الكلمات أو استبدال كلمة عالقة أفضل من توقف الإنتاج).
    # يُكرَّر لأن إعادة المراجعة بعد كل تصحيح قد تُظهر مخالفة جديدة صغيرة لم تكن ظاهرة
    # قبله (لوحظ فعليًا) -- التكرار يضمن التقارب بدل توقّف بعد جولة واحدة فقط.
    for round_no in range(1, 3):  # تقليص 3->2 (2026-09-16) لنفس السبب أعلاه
        hard_tashkeel = [x for x in (review.get("tashkeel_violations") or []) if x.get("type") != "missing_pause"]
        if verdict == "pass" or (not hard_tashkeel and not review.get("dialect_violations")
                                  and not review.get("science_flags")):
            break
        fs["scenes"] = agents.force_resolve_issues(fs["scenes"], review)
        review = agents.review_script(fs, L)
        verdict = str(review.get("verdict", "")).lower()
        print(f"  force-resolve round {round_no}: verdict={verdict} score={review.get('score')} "
              f"wc={review.get('word_count_estimate')}", flush=True)

    fs["_review"] = review

    # قرار الاعتماد النهائي: نقبل لو مفيش تشكيل/لهجة/أخطاء علمية عالقة، حتى لو عدد
    # الكلمات أقل من المستهدف (تصريح صريح من المسؤول: تقليص بسيط في الطول مقبول ولا
    # يوقف الإنتاج -- المهم خلو المحتوى من أخطاء النطق/اللهجة/العلم).
    hard_tashkeel = [x for x in (review.get("tashkeel_violations") or []) if x.get("type") != "missing_pause"]
    clean = not hard_tashkeel and not review.get("dialect_violations") and not review.get("science_flags")
    final_ok = verdict == "pass" or clean

    out_text = json.dumps({"final_script": fs, "status": "PASS" if final_ok else "NEEDS_REVIEW",
                            "review": review}, ensure_ascii=False)
    body = {"lesson_uid": lesson_uid, "stage_code": "SCRIPT_FINAL", "prompt_binding_uid": "820006",
            "revision_no": int(time.time()), "output_text": out_text, "output_hash": _hash(out_text),
            "model_used": "gemini-3.6-flash + proofreader + force-resolve (auto, no-telegram)",
            "approval_status": "approved" if final_ok else "changes_requested"}
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(url + "/rest/v1/content_outputs", data=json.dumps(body).encode(),
                                  method="POST", headers={"apikey": key, "Authorization": "Bearer " + key,
                                  "Content-Type": "application/json", "Prefer": "return=representation"})
    urllib.request.urlopen(req, timeout=30).read()

    if not final_ok:
        print(f"!! lesson {lesson_uid}: لسه فيه مشاكل جوهرية (تشكيل/لهجة/علمية) بعد كل المحاولات -- توقّف، "
              f"يحتاج مراجعة بشرية", flush=True)
        return {"status": "needs_human_review", "lesson_uid": lesson_uid, "review": review}

    print(f"-- السكريبت مقبول (score={review.get('score')}, نظيف من تشكيل/لهجة/علم) "
          f"-- اعتماد تلقائي، بدء الإنتاج", flush=True)

    res = produce_lesson.produce({
        "video_uid": L["video_uid"], "lesson_uid": lesson_uid,
        "lesson_code": L["lesson_code"], "scenes": fs["scenes"],
        "title": L["title_ar"], "bookend_set": bookend_set,
        "objectives_ar": fs.get("objectives_ar"),
        "question_bank_ar": fs.get("question_bank_ar"),
        "scientific_refs_ar": fs.get("scientific_refs_ar"),
    })
    print(json.dumps({k: v for k, v in res.items() if k != "heal_log"}, ensure_ascii=False, indent=1), flush=True)
    return res


if __name__ == "__main__":
    if sys.argv[1:] and sys.argv[1] == "--continue":
        count = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        ids = _next_pending_lessons(count)
        print(f"[checkpoint] استكمال تلقائي -- أول {count} دروس غير مكتملة: {ids}", flush=True)
    else:
        ids = [int(x) for x in sys.argv[1:]] or _next_pending_lessons(5)
    results = []
    for i, lu in enumerate(ids):
        if i > 0:
            # فاصل زمني بين الدروس: الطبقة المجانية لـ Gemini محدودة بعشرين نداء/دقيقة
            # (خطأ RESOURCE_EXHAUSTED لوحظ فعليًا 2026-09-15 مع نص "retry in ~14.5s") --
            # درس واحد ممكن يستهلك عشرات النداءات (كتابة + مراجعة + إصلاح أخير)، فبدء
            # الدرس التالي فورًا كان بيصطدم بالسقف باستمرار. 20 ثانية كفاية لتصفير النافذة.
            print("[توقف 20 ثانية بين الدروس لتفادي حد الطبقة المجانية]", flush=True)
            time.sleep(20)
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
