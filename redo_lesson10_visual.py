# -*- coding: utf-8 -*-
"""redo_lesson10_visual.py -- يعيد تشغيل agents.select_visuals() على نص درس 100010
المعتمَد مسبقًا (محفوظ في /tmp/l10_approved.json) بعد إصلاح الـ crash في select_visuals،
ثم يحفظ نسخة content_outputs جديدة معتمدة وينتج الفيديو فعليًا عبر produce_lesson.produce().
"""
import json
import os
import sys
import time

sys.path.insert(0, "/root/video-factory")
sys.path.insert(0, "/root/video-factory/pipeline")

import agents
import produce_lesson

produce_lesson._load_env()

LESSON_UID = 100010

with open("/tmp/l10_approved.json", encoding="utf-8") as f:
    d = json.load(f)
row = d[0]
ot = json.loads(row["output_text"]) if isinstance(row["output_text"], str) else row["output_text"]
fs = ot["final_script"]

before = [(s.get("scene_no"), s.get("diagram")) for s in fs["scenes"]]
print("BEFORE:", before, flush=True)

fs["scenes"] = agents.select_visuals(fs["scenes"], fs.get("title"))

after = [(s.get("scene_no"), s.get("diagram")) for s in fs["scenes"]]
print("AFTER:", after, flush=True)

if before == after:
    print("تحذير: لم يتغير أي مشهد -- تحقق يدويًا قبل المتابعة للإنتاج", flush=True)

# حفظ نسخة معتمدة جديدة في content_outputs
import requests

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_KEY"]

import hashlib


def _hash(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8") + str(time.time()).encode()).hexdigest()[:32]


out_text = json.dumps({"final_script": fs, "status": "approved", "review": ot.get("review")}, ensure_ascii=False)
row_payload = {
    "lesson_uid": LESSON_UID,
    "stage_code": "SCRIPT_FINAL",
    "prompt_binding_uid": "820006",
    "revision_no": int(time.time()),
    "approval_status": "approved",
    "output_text": out_text,
    "output_hash": _hash(out_text),
    "model_used": "visual_redo",
}
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

print("بدء الإنتاج الفعلي...", flush=True)
res = produce_lesson.produce({
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
})
print("PRODUCE RESULT:", json.dumps(res, ensure_ascii=False)[:2000], flush=True)
