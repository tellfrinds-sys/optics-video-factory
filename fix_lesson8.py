# -*- coding: utf-8 -*-
"""fix_lesson8.py -- يطبّق نفس دورة force_resolve_issues + إعادة المراجعة المستخدمة في
auto_produce_batch.py على درس 100008 العالق (fail score 42: خطأ مطبعي "المصار البصري"
+ 5 مخالفات لهجة)، بدل انتظار مسار تليجرام "نسخة معدّلة" المعطّل بسبب اعتماد Gemini
Query Key المعطوب في n8n.
"""
import hashlib
import json
import os
import sys
import time

sys.path.insert(0, "/root/video-factory")
sys.path.insert(0, "/root/video-factory/pipeline")

import agents
import produce_lesson

produce_lesson._load_env()

LESSON_UID = 100008
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

with open("/tmp/l8_pending.json", encoding="utf-8") as f:
    d = json.load(f)
ot = json.loads(d[0]["output_text"])
fs = ot["final_script"]
review = ot.get("review") or {}

L = {"title_ar": fs.get("title"), "lesson_code": fs.get("lesson_code")}

for round_no in range(1, 4):
    verdict = str(review.get("verdict", "")).lower()
    hard_tashkeel = [x for x in (review.get("tashkeel_violations") or []) if x.get("type") != "missing_pause"]
    if verdict == "pass" or (not hard_tashkeel and not review.get("dialect_violations") and not review.get("science_flags")):
        print(f"round {round_no}: قبول -- verdict={verdict}", flush=True)
        break
    print(f"round {round_no}: يصلّح {len(review.get('dialect_violations') or [])} لهجة + "
          f"{len(review.get('science_flags') or [])} علمي + {len(hard_tashkeel)} تشكيل", flush=True)
    fs["scenes"] = agents.force_resolve_issues(fs["scenes"], review)
    review = agents.review_script(fs, L)
    print("  -> verdict:", review.get("verdict"), "score:", review.get("score"), flush=True)
else:
    print("لم يُحل بالكامل بعد 3 جولات -- سيُحفَظ بأفضل حالة متاحة", flush=True)

verdict = str(review.get("verdict", "")).lower()
hard_tashkeel = [x for x in (review.get("tashkeel_violations") or []) if x.get("type") != "missing_pause"]
final_ok = verdict == "pass" or (not hard_tashkeel and not review.get("dialect_violations") and not review.get("science_flags"))
print("FINAL_OK:", final_ok, "verdict:", verdict, "score:", review.get("score"), flush=True)

if not final_ok:
    print("توقف -- ما زالت هناك مشاكل حقيقية، لن يُنتَج تلقائيًا:", flush=True)
    print(json.dumps({
        "science_flags": review.get("science_flags"),
        "dialect_violations": review.get("dialect_violations"),
        "tashkeel_violations": hard_tashkeel,
    }, ensure_ascii=False, indent=2), flush=True)
    sys.exit(1)

fs["scenes"] = agents.select_visuals(fs["scenes"], fs.get("title"))
after_visuals = [(s.get("scene_no"), s.get("diagram")) for s in fs["scenes"]]
print("visuals:", after_visuals, flush=True)


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8") + str(time.time()).encode()).hexdigest()[:32]


out_text = json.dumps({"final_script": fs, "status": "PASS", "review": review}, ensure_ascii=False)
row_payload = {
    "lesson_uid": LESSON_UID,
    "stage_code": "SCRIPT_FINAL",
    "prompt_binding_uid": "820006",
    "revision_no": int(time.time()),
    "approval_status": "approved",
    "output_text": out_text,
    "output_hash": _hash(out_text),
    "model_used": "force_resolve_fix",
}
import requests

r = requests.post(
    f"{SUPABASE_URL}/rest/v1/content_outputs",
    headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    },
    json=row_payload,
    timeout=30,
)
print("content_outputs insert:", r.status_code, flush=True)
if r.status_code >= 300:
    print(r.text[:2000], flush=True)
    sys.exit(1)

payload = {
    "video_uid": fs.get("video_uid"),
    "lesson_uid": LESSON_UID,
    "lesson_code": fs.get("lesson_code"),
    "title": fs.get("title"),
    "scenes": fs["scenes"],
    "bookend_set": "V5",
    "objectives_ar": fs.get("objectives_ar"),
    "question_bank_ar": fs.get("question_bank_ar"),
    "scientific_refs_ar": fs.get("scientific_refs_ar"),
    "force": True,
}
with open("/tmp/l8_produce_payload.json", "w", encoding="utf-8") as f:
    json.dump(payload, f, ensure_ascii=False)
print("saved payload to /tmp/l8_produce_payload.json -- سيتم استدعاء /api/produce-lesson بعده", flush=True)
