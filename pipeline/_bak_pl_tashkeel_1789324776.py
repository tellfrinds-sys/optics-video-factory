# -*- coding: utf-8 -*-
"""
prepare_lesson.py — يجهّز درسًا للإنتاج: يكتب Gemini السيناريو، يراجعه وكيل المراجعة،
يعيد التوليد مرة إن رست المراجعة على fail، ثم يحفظه في Supabase (SCRIPT_FINAL / pending)
ويرسل بطاقة اعتماد على تليجرام. لا إنتاج فيديو قبل اعتماد المسؤول.

  POST /api/prepare-lesson  {"lesson_uid": 100002}
  -> {"status":"awaiting_script_approval", "output_uid":..., "review":{...}}
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from pathlib import Path

import agents

ROOT = Path("/root/video-factory")
PIPE = ROOT / "pipeline"
STATUS_DIR = ROOT / "outputs" / "_status"
N8N_BASE = os.environ.get("N8N_BASE", "http://127.0.0.1:5678")  # اتصال محلي — لا يعتمد على DNS العام
SCRIPT_CARD_HOOK = N8N_BASE + "/webhook/send-script-card"
PROMPT_BINDING_UID = "820006"


def _load_env():
    f = PIPE / ".env"
    if f.exists():
        for ln in f.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _sb(method, path, body=None):
    _load_env()
    url = os.environ["SUPABASE_URL"] + path
    key = os.environ["SUPABASE_SERVICE_KEY"]
    h = {"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json",
         "Prefer": "return=representation"}
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=40) as r:
        t = r.read()
        return json.loads(t) if t else []


def _video_uid_for(lesson_uid: int) -> int:
    return 500128 + (lesson_uid - 100001)


def _fetch_lesson(lesson_uid: int) -> dict:
    rows = _sb("GET", "/rest/v1/lessons?lesson_uid=eq.%d&select=lesson_code,title_ar,learning_goal,level,duration_minutes,professional_scope_note" % lesson_uid)
    if not rows:
        raise RuntimeError("الدرس %d غير موجود" % lesson_uid)
    L = rows[0]
    L["video_uid"] = _video_uid_for(lesson_uid)
    L["lesson_uid"] = lesson_uid
    try:
        srcs = _sb("GET", "/rest/v1/lesson_sources?lesson_uid=eq.%d&select=citation_note,scientific_point" % lesson_uid)
        L["sources_text"] = "\n".join("- " + str(s.get("scientific_point") or s.get("citation_note") or "").strip()
                                      for s in srcs if (s.get("scientific_point") or s.get("citation_note")))
    except Exception:
        L["sources_text"] = ""
    return L


def _hash(s: str) -> str:
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return "h%x_%d" % (h, len(s))


def prepare(payload: dict) -> dict:
    lesson_uid = int(payload["lesson_uid"])
    L = _fetch_lesson(lesson_uid)
    human_notes = str(payload.get("notes") or "").strip()
    if human_notes:
        try:
            agents.learn_from("درس %s" % L["lesson_code"], human_notes)
        except Exception:
            pass

    # 1) كتابة + مراجعة (محاولتان). ملاحظات المسؤول تُدمج مع ملاحظات المراجعة.
    notes, review, fs = human_notes, None, None
    for attempt in (1, 2):
        fs = agents.write_script(L, extra_notes=notes)
        review = agents.review_script(fs, L)
        if str(review.get("verdict", "")).lower() == "pass":
            break
        notes = "\n".join("• " + x for x in (review.get("must_fix") or [])) + \
                "\nنقاط ناقصة: " + " / ".join(review.get("coverage_gaps") or [])
    fs["_review"] = review

    # 2) حفظ في Supabase كـ SCRIPT_FINAL / pending
    out_text = json.dumps({"final_script": fs, "status": "PASS",
                           "review": review}, ensure_ascii=False)
    row = _sb("POST", "/rest/v1/content_outputs", {
        "lesson_uid": lesson_uid,
        "stage_code": "SCRIPT_FINAL",
        "prompt_binding_uid": PROMPT_BINDING_UID,
        "revision_no": int(time.time()),
        "output_text": out_text,
        "output_hash": _hash(out_text),
        "model_used": "gemini-3.6-flash + qwen2.5:7b (مراجعة)",
        "approval_status": "pending",
    })
    output_uid = (row[0] if isinstance(row, list) and row else row).get("output_uid")

    # 2b) أهداف الدرس + بنك الأسئلة + المصادر -> أعمدة جدول lessons
    try:
        patch = {}
        if fs.get("objectives_ar"):
            patch["objectives_ar"] = fs["objectives_ar"]
        if fs.get("question_bank_ar"):
            patch["question_bank_ar"] = fs["question_bank_ar"]
        if fs.get("scientific_refs_ar"):
            patch["scientific_refs_ar"] = fs["scientific_refs_ar"]
        if patch:
            _sb("PATCH", "/rest/v1/lessons?lesson_uid=eq.%d" % lesson_uid, patch)
    except Exception:
        pass

    # 3) ملخص + بطاقة تليجرام
    wc = review.get("word_count_estimate", 0)
    summary = (
        "🎬 <b>سيناريو جاهز للاعتماد</b>\n"
        "الدرس: %s\n<code>%s</code>\n\n"
        "المشاهد: %d | كلمات السرد: ~%d | تقدير المدة: ~%d دقيقة\n"
        "تقييم المراجع الآلي: %s (%s/100)\n"
        % (L["title_ar"], L["lesson_code"], len(fs["scenes"]), wc, round(wc / 150),
           review.get("verdict", "?"), review.get("score", "?"))
    )
    gaps = review.get("coverage_gaps") or []
    mf = review.get("must_fix") or []
    if gaps:
        summary += "\n⚠️ نقاط قد تكون ناقصة:\n" + "\n".join("• " + g for g in gaps[:4])
    if mf:
        summary += "\n\n📝 ملاحظات المراجع:\n" + "\n".join("• " + m for m in mf[:4])
    summary += "\n\nالعناوين:\n" + "\n".join("%d. %s" % (s["scene_no"], s["heading"]) for s in fs["scenes"])

    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    (STATUS_DIR / ("script_%s.json" % lesson_uid)).write_text(out_text, encoding="utf-8")
    script_txt = agents.render_script_text(fs)
    (STATUS_DIR / ("script_%s.txt" % lesson_uid)).write_text(script_txt, encoding="utf-8")
    txt_url = "%s/outputs/_status/script_%s.txt" % (
        os.environ.get("PUBLIC_BASE", "https://opticsgate.online"), lesson_uid)
    summary += ("\n\n📄 السيناريو الكامل للمراجعة والتعديل:\n" + txt_url +
                "\n\nللاعتماد كما هو: «✅ اعتماد وإنتاج».\n"
                "للتعديل: «✏️ نسخة معدّلة» ثم الصق السيناريو كاملًا بنفس التنسيق — نسختك تصير مصدر الإنتاج مباشرة.")

    card = {"output_uid": output_uid, "lesson_uid": lesson_uid,
            "lesson_code": L["lesson_code"], "title": L["title_ar"], "summary": summary,
            "script_url": txt_url}
    try:
        req = urllib.request.Request(SCRIPT_CARD_HOOK, data=json.dumps(card).encode(),
                                     method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
        sent = True
        print("[prepare_lesson] card sent ok for lesson", lesson_uid, flush=True)
    except Exception as e:
        sent = False
        card["card_error"] = str(e)[:200]
        print("[prepare_lesson] CARD SEND FAILED for lesson", lesson_uid, "->", str(e)[:300], flush=True)

    return {"status": "awaiting_script_approval", "output_uid": output_uid,
            "lesson_uid": lesson_uid, "video_uid": L["video_uid"],
            "review": review, "card_sent": sent, "scenes": len(fs["scenes"]),
            "word_count": wc}


if __name__ == "__main__":
    import sys
    print(json.dumps(prepare({"lesson_uid": int(sys.argv[1]) if len(sys.argv) > 1 else 100002}),
                     ensure_ascii=False, indent=1))
