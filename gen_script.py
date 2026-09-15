# -*- coding: utf-8 -*-
"""
gen_script.py — يولّد سكربت درس (مشاهد جاهزة للرندر) عبر Gemini من بيانات الدرس في Supabase.

  gen_script(lesson_uid) -> {"title","lesson_code","video_uid","scenes":[...]}

يُستدعى تلقائيًا من produce_lesson عندما يُمرَّر lesson_uid بلا scenes.
"""
from __future__ import annotations

import json
import os
import re
import urllib.request
from pathlib import Path

ROOT = Path("/root/video-factory")
GEMINI_URL = os.environ.get(
    "GEMINI_URL",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent")
PROMPT_FILE = ROOT / "pipeline" / "prm_script_3.txt"


def _env(k, d=""):
    return os.environ.get(k, d)


def _sb_get(path):
    url = _env("SUPABASE_URL") + path
    key = _env("SUPABASE_SERVICE_KEY")
    req = urllib.request.Request(url, headers={"apikey": key, "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _load_env():
    f = ROOT / "pipeline" / ".env"
    if f.exists():
        for ln in f.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _prompt() -> str:
    if PROMPT_FILE.exists():
        return PROMPT_FILE.read_text(encoding="utf-8")
    rows = _sb_get("/rest/v1/prompts?prompt_code=eq.PRM-SCRIPT-3&version=eq.1.1&select=prompt_text&limit=1")
    return rows[0]["prompt_text"] if rows else ""


def _gemini(system: str, user: str) -> dict:
    key = _env("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY غير مضبوط")
    body = json.dumps({
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json",
                             "maxOutputTokens": 8192},
    }).encode("utf-8")
    req = urllib.request.Request(GEMINI_URL, data=body, method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    try:
        txt = d["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise RuntimeError("Gemini بلا ناتج: " + json.dumps(d)[:400])
    return json.loads(txt)


def _video_uid_for(lesson_uid: int) -> int:
    # 100001 -> 500128 (تاريخيًا)، ثم 500129 لـ 100002 وهكذا
    return 500128 + (lesson_uid - 100001)


def gen_script(lesson_uid: int) -> dict:
    _load_env()
    lrows = _sb_get(
        "/rest/v1/lessons?lesson_uid=eq.%d&select=lesson_code,title_ar,learning_goal,level,duration_minutes,professional_scope_note" % lesson_uid)
    if not lrows:
        raise RuntimeError("الدرس %d غير موجود" % lesson_uid)
    L = lrows[0]
    try:
        srcs = _sb_get(
            "/rest/v1/lesson_sources?lesson_uid=eq.%d&select=citation_note,scientific_point,source_uid" % lesson_uid)
    except Exception:
        srcs = []
    src_txt = "\n".join(
        "- " + str(s.get("scientific_point") or s.get("citation_note") or "").strip()
        for s in srcs if (s.get("scientific_point") or s.get("citation_note")))

    user = (
        "lesson_code: %s\n"
        "العنوان: %s\n"
        "هدف التعلّم: %s\n"
        "المستوى: %s | المدة المستهدفة: %s دقيقة\n"
        "ملاحظة النطاق المهني: %s\n"
        "video_uid: %d\n\n"
        "النقاط العلمية المعتمدة:\n%s\n\n"
        "أنشئ الآن final_script كامل بصيغة JSON حسب التعليمات."
        % (L["lesson_code"], L["title_ar"], L.get("learning_goal", ""), L.get("level", ""),
           L.get("duration_minutes", 8), L.get("professional_scope_note", ""),
           _video_uid_for(lesson_uid), src_txt or "(اعتمد على المعرفة التشريحية القياسية للعين)")
    )
    out = _gemini(_prompt(), user)
    fs = out.get("final_script") or {}
    if out.get("status") == "BLOCK" or not fs.get("scenes"):
        raise RuntimeError("Gemini: BLOCK / بلا مشاهد :: " + json.dumps(out, ensure_ascii=False)[:500])
    fs.setdefault("lesson_code", L["lesson_code"])
    fs.setdefault("video_uid", _video_uid_for(lesson_uid))
    fs.setdefault("title", L["title_ar"])
    # تطبيع labels: قوائم [["اسم","key"]] -> صيغة يفهمها eye_scene2 (tuple-like)
    for sc in fs["scenes"]:
        sc["labels"] = [tuple(x) if isinstance(x, (list, tuple)) else x for x in (sc.get("labels") or [])]
        sc.setdefault("caption", sc.get("narration", ""))
        sc.setdefault("source_codes", L["lesson_code"])
    return fs


if __name__ == "__main__":
    import sys
    print(json.dumps(gen_script(int(sys.argv[1]) if len(sys.argv) > 1 else 100002),
                     ensure_ascii=False, indent=1))
