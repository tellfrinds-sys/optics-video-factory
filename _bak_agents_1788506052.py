# -*- coding: utf-8 -*-
"""
agents.py — كاتب الاسكريبت (Gemini) + وكيل المراجعة التحريري (qwen) + التعلّم المستمر.

الذاكرة الحيّة: pipeline/style_guide.md — تُحقَن في تعليمات الاثنين، وتنمو بعد كل مراجعة.
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path("/root/video-factory")
PIPE = ROOT / "pipeline"
STYLE = PIPE / "style_guide.md"
WRITER_PROMPT = PIPE / "prm_writer.txt"
REVIEWER_PROMPT = PIPE / "prm_reviewer.txt"
GEMINI_URL = os.environ.get(
    "GEMINI_URL",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent")
OLLAMA = "http://127.0.0.1:11434/api/generate"
QA_MODEL = os.environ.get("QA_MODEL", "qwen2.5:7b-instruct")

ANATOMY_KEYS = ("eye_whole cornea sclera iris pupil ciliary choroid retina fovea disc nerve "
                "chamber lens zonules vitreous muscle epithelium bowman stroma descemet endothelium tearfilm").split()


def _load_env():
    f = PIPE / ".env"
    if f.exists():
        for ln in f.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def style_guide() -> str:
    return STYLE.read_text(encoding="utf-8") if STYLE.exists() else ""


def bump_style_guide(rule: str, tag: str = ""):
    rule = (rule or "").strip()
    if not rule or len(rule) < 8:
        return
    txt = style_guide()
    stamp = time.strftime("%Y-%m-%d")
    line = f"- [{stamp}]{(' ' + tag) if tag else ''} {rule}"
    if line.split("] ", 1)[-1] in txt:      # لا تكرّر نفس القاعدة
        return
    # ارفع رقم النسخة
    txt = re.sub(r"رقم النسخة: (\d+)", lambda m: "رقم النسخة: %d" % (int(m.group(1)) + 1), txt, count=1)
    txt = txt.rstrip() + "\n" + line + "\n"
    STYLE.write_text(txt, encoding="utf-8")


# ---------------- Gemini: كاتب الاسكريبت ----------------
def _gemini(system: str, user: str) -> dict:
    _load_env()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY غير مضبوط")
    body = json.dumps({
        "system_instruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json",
                             "maxOutputTokens": 45000},
    }).encode("utf-8")
    req = urllib.request.Request(GEMINI_URL, data=body, method="POST",
                                 headers={"x-goog-api-key": key, "Content-Type": "application/json"})
    d = None
    for _try in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                d = json.loads(r.read()); break
        except urllib.error.HTTPError as he:
            if he.code in (429, 503) and _try < 4:
                time.sleep(20 * (_try + 1)); continue
            raise
    if d is None:
        raise RuntimeError("Gemini: تعذّر الاتصال بعد محاولات")
    cand = (d.get("candidates") or [{}])[0]
    txt = ""
    for part in ((cand.get("content") or {}).get("parts") or []):
        txt += part.get("text", "")
    try:
        return json.loads(txt)
    except Exception:
        # إصلاح JSON مبتور: أقفل الأقواس المفتوحة
        t = txt.strip()
        if t.startswith("{"):
            t = t.rstrip(", \n")
            t += "]" * max(0, t.count("[") - t.count("]"))
            t += "}" * max(0, t.count("{") - t.count("}"))
            try:
                return json.loads(t)
            except Exception:
                pass
        raise RuntimeError("Gemini بلا ناتج صالح (finishReason=%s): %s"
                           % (cand.get("finishReason"), txt[:300]))


def write_script(lesson: dict, extra_notes: str = "") -> dict:
    sysmsg = WRITER_PROMPT.read_text(encoding="utf-8").replace("{STYLE_GUIDE}", style_guide())
    user = (
        "lesson_code: %s\nvideo_uid: %d\n"
        "عنوان الدرس الرسمي: %s\n"
        "هدف التعلّم (غطِّ كل نقطة فيه بالاسم): %s\n"
        "المستوى: %s | المدة المستهدفة: %s دقيقة\n"
        "ملاحظة النطاق المهني: %s\n\n"
        "النقاط العلمية المعتمدة:\n%s\n\n"
        "%s\n"
        "اكتب الآن final_script كامل (JSON فقط)."
        % (lesson["lesson_code"], lesson["video_uid"], lesson["title_ar"],
           lesson.get("learning_goal", ""), lesson.get("level", ""),
           lesson.get("duration_minutes", 8), lesson.get("professional_scope_note", ""),
           lesson.get("sources_text") or "(اعتمد على المراجع التشريحية القياسية للعين والقرنية)",
           ("ملاحظات إلزامية من المراجعة السابقة يجب معالجتها:\n" + extra_notes) if extra_notes else "")
    )
    out = _gemini(sysmsg, user)
    fs = out.get("final_script") or {}
    if out.get("status") == "BLOCK" or not fs.get("scenes"):
        raise RuntimeError("Gemini BLOCK / بلا مشاهد: " + json.dumps(out, ensure_ascii=False)[:600])
    fs.setdefault("lesson_code", lesson["lesson_code"])
    fs.setdefault("video_uid", lesson["video_uid"])
    fs["title"] = lesson["title_ar"]                       # فرض العنوان الرسمي
    # فرض الرسم المتخصّص على كل مشاهد الدرس المتخصّص (ما عدا العنوان/الختام)
    gt = (lesson.get("title_ar", "") + " " + lesson.get("learning_goal", ""))
    forced = None
    if ("قرنية" in gt or "القرنية" in gt) and ("طبق" in gt or "شفاف" in gt or "انكسار" in gt):
        forced = "cornea_layers"
    for i, sc in enumerate(fs["scenes"]):
        sc["labels"] = [tuple(x) if isinstance(x, (list, tuple)) else x for x in (sc.get("labels") or [])]
        sc.setdefault("caption", sc.get("narration", ""))
        sc.setdefault("source_codes", lesson["lesson_code"])
        sc.setdefault("diagram", fs.get("diagram_default", "eye"))
        if forced and i not in (0, len(fs["scenes"]) - 1) and sc.get("kind") not in ("title", "outro"):
            sc["diagram"] = forced
    return fs


# ---------------- qwen: وكيل المراجعة ----------------
def _ollama_json(system: str, prompt: str) -> dict:
    body = json.dumps({"model": QA_MODEL, "system": system, "prompt": prompt,
                       "stream": False, "format": "json",
                       "options": {"temperature": 0, "num_ctx": 16384}}).encode()
    req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=900) as resp:
        raw = json.loads(resp.read())["response"]
    try:
        return json.loads(raw)
    except Exception:
        return {"verdict": "fail", "must_fix": ["تعذّر تحليل رد المراجع: " + raw[:200]], "score": 0}


_TASH_RE = re.compile("[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06DC\u06DF-\u06E8\u06EA-\u06ED\u0640]")


# مدقّق لهجة مصرية حتمي (فوري، أدقّ من نموذج صغير في كشف الفصحى)
_MSA = [
    "هذا", "هذه", "هذان", "هؤلاء", "ذلك", "تلك", "الذي", "التي", "الذين", "اللذان",
    "إنَّ", "إنّ", "أنَّ", "لقد", "قد ", "سوف", "سـ", "يتمّ", "يتم ", "يقوم", "تقوم", "نقوم",
    "عندما", "حيثُ", "حيث ", "لذلك", "كذلك", "بينما", "إذ ", "لكنَّ",
    "نستطيع", "يمكننا", "يمكنك", "سنشرح", "سنتحدث", "سنتعرف", "نتحدث", "نستعرض",
    "جدًّا و", "لدى", "لديه", "لديها", "فإنَّ", "فإن ", "حينما", "آنذاك",
    "هو عبارة عن", "عبارة عن", "يُعدّ", "يعدّ", "تُعدّ", "يُعتبر", "لا يزال",
]
_SPLIT = re.compile(r"(?<=[.!؟\n])\s+")


def dialect_lint(scenes: list[dict]) -> dict:
    v = []
    for i, s in enumerate(scenes):
        t = _TASH_RE.sub("", s.get("narration", ""))
        for sent in _SPLIT.split(t):
            for m in _MSA:
                if re.search(r"(^|[\s،؛])" + re.escape(m.strip()) + r"($|[\s،؛.])", " " + sent + " "):
                    v.append({"scene": s.get("scene_no", i + 1), "quote": sent.strip()[:140], "marker": m.strip()})
                    break
    return {"dialect_ok": not v, "violations": v}


def _gemini_review(fs: dict, lesson: dict) -> dict:
    sysmsg = REVIEWER_PROMPT.read_text(encoding="utf-8").replace("{STYLE_GUIDE}", style_guide())
    scenes = fs.get("scenes", [])
    wc = sum(len(s.get("narration", "").split()) for s in scenes)
    body = {
        "عنوان الدرس": lesson["title_ar"],
        "هدف التعلّم": lesson.get("learning_goal", ""),
        "المدة المستهدفة (دقيقة)": lesson.get("duration_minutes", 8),
        "عدد المشاهد": len(scenes), "مجموع كلمات السرد": wc,
        "المشاهد": [{"scene_no": s.get("scene_no"), "heading": s.get("heading"),
                     "diagram": s.get("diagram"), "term_en": s.get("term_en"),
                     "narration": _TASH_RE.sub("", s.get("narration", ""))} for s in scenes],
    }
    return _gemini(sysmsg, "راجع هذا السيناريو وأجب JSON فقط:\n" + json.dumps(body, ensure_ascii=False))


def _qwen_deep_dialect(scenes):
    """تدقيق لهجة بـ qwen2.5:7b — اختياري (بطيء على المعالج)؛ يُفعَّل بـ QA_DEEP=1."""
    if os.environ.get("QA_DEEP") != "1":
        return {"skipped": True}
    text = "\n".join("(%d) %s" % (s.get("scene_no", i + 1), _TASH_RE.sub("", s.get("narration", "")))
                     for i, s in enumerate(scenes))
    body = json.dumps({"model": QA_MODEL,
                       "system": "افحص إن كل جملة عامية مصرية 100%. أجب JSON: "
                                 "{\"dialect_ok\":true|false,\"violations\":[{\"scene\":n,\"quote\":\"\"}]}",
                       "prompt": text, "stream": False, "format": "json",
                       "options": {"temperature": 0, "num_ctx": 8192}}).encode()
    try:
        req = urllib.request.Request(OLLAMA, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1200) as r:
            return json.loads(json.loads(r.read())["response"])
    except Exception as e:
        return {"error": str(e)[:120]}


def review_script(fs: dict, lesson: dict) -> dict:
    scenes = fs.get("scenes", [])
    wc = sum(len(s.get("narration", "").split()) for s in scenes)
    g = _gemini_review(fs, lesson)                 # مراجعة تحريرية شاملة (Gemini)
    q = dialect_lint(scenes)                       # مدقّق لهجة حتمي (فوري)
    qd = _qwen_deep_dialect(scenes)                # اختياري

    dvi = list(g.get("dialect_violations") or []) + list(q.get("violations") or [])
    verdict = "pass"
    if str(g.get("verdict", "")).lower() == "fail" or q.get("dialect_ok") is False or dvi:
        verdict = "fail"
    rv = {
        "verdict": verdict,
        "score": g.get("score", 0),
        "word_count_estimate": g.get("word_count_estimate", wc),
        "coverage_gaps": g.get("coverage_gaps") or [],
        "dialect_violations": dvi,
        "science_flags": g.get("science_flags") or [],
        "structure_issues": g.get("structure_issues") or [],
        "visual_issues": g.get("visual_issues") or [],
        "must_fix": g.get("must_fix") or [],
        "learned_rule": g.get("learned_rule") or "",
        "reviewers": {"gemini": g.get("verdict"), "dialect_lint": q.get("dialect_ok"),
                      "qwen_deep": qd.get("dialect_ok", qd.get("skipped", qd.get("error")))},
    }
    if rv["learned_rule"]:
        bump_style_guide(rv["learned_rule"], tag="(من المراجعة)")
    return rv


_SCENE_MARK = re.compile(r"〔\s*مشهد\s*(\d+)\s*〕(.*?)(?=〔\s*مشهد\s*\d+\s*〕|\Z)", re.S)


def render_script_text(fs: dict) -> str:
    """صيغة نصية قابلة للنسخ والتعديل ثم إعادة الإرسال."""
    out = ["العنوان: " + fs.get("title", ""), ""]
    for i, s in enumerate(fs.get("scenes", []), 1):
        head = s.get("heading", "")
        dia = s.get("diagram", "eye")
        en = s.get("term_en", "")
        out.append("〔مشهد %d〕 %s | رسم: %s | EN: %s" % (s.get("scene_no", i), head, dia, en))
        out.append((s.get("narration", "") or "").strip())
        out.append("")
    obj = fs.get("objectives_ar") or []
    if obj:
        out += ["", "— أهداف الدرس —"] + ["• " + str(o) for o in obj]
    return "\n".join(out).strip()


def parse_script_text(text: str, base: dict | None = None) -> dict:
    """يحوّل النصّ المعدّل من المسؤول إلى final_script جاهز للإنتاج."""
    base = dict(base or {})
    tm = re.search(r"العنوان\s*:\s*(.+)", text)
    if tm:
        base["title"] = tm.group(1).strip()
    scenes = []
    for m in _SCENE_MARK.finditer(text):
        no = int(m.group(1))
        blob = m.group(2).strip()
        first_nl = blob.find("\n")
        header = blob if first_nl < 0 else blob[:first_nl]
        body = "" if first_nl < 0 else blob[first_nl + 1:].strip()
        # أوقف السرد عند أي عنوان قسم لاحق
        body = re.split(r"\n\s*(?:—[^\n]*—|〔)", body)[0].strip()
        parts = [p.strip() for p in header.split("|")]
        heading = parts[0].strip()
        dia = "eye"
        en = ""
        for p in parts[1:]:
            if p.startswith("رسم"):
                dia = p.split(":", 1)[-1].strip() or "eye"
            elif p.upper().startswith("EN"):
                en = p.split(":", 1)[-1].strip()
        cap = _TASH_RE.sub("", body)
        cap = re.sub(r"\bال\s*[A-Za-z][\w' ]*", lambda x: "", cap)  # جرّد المصطلح اللاتيني من الترجمة
        cap = re.sub(r"[A-Za-z][\w' ]*", "", cap)
        cap = re.sub(r"\s+", " ", cap).strip(" ،.")
        scenes.append({"scene_no": no, "heading": heading, "diagram": dia, "term_en": en,
                       "narration": body, "caption": cap or body,
                       "source_codes": base.get("lesson_code", "")})
    if scenes:
        base["scenes"] = scenes
    return base


def learn_from(context: str, human_feedback: str):
    """يُستدعى عند رفض بشري: يقطّر الملاحظة لقاعدة ويضيفها للذاكرة."""
    sysmsg = ("أنت أمين ذاكرة الإنتاج. حوّل ملاحظة المسؤول إلى قاعدة أسلوب واحدة قصيرة "
              "قابلة لإعادة الاستخدام تمنع تكرار الخطأ. أجب JSON: {\"rule\":\"...\"}")
    r = _ollama_json(sysmsg, "السياق: %s\nملاحظة المسؤول: %s" % (context[:1500], human_feedback[:1500]))
    bump_style_guide(r.get("rule", ""), tag="(من ملاحظة المسؤول)")
    return r.get("rule", "")
