# -*- coding: utf-8 -*-
"""
agents.py — كاتب الاسكريبت (Gemini) + وكيل المراجعة التحريري (qwen) + التعلّم المستمر.

الذاكرة الحيّة: pipeline/style_guide.md — تُحقَن في تعليمات الاثنين، وتنمو بعد كل مراجعة.
"""
from __future__ import annotations

import json
import json as _json
import os
import re
import time
import urllib.request
import urllib.parse
import urllib.error
from pathlib import Path

import tashkeel_qa

ROOT = Path("/root/video-factory")
PIPE = ROOT / "pipeline"
STYLE = PIPE / "style_guide.md"
WRITER_PROMPT = PIPE / "prm_writer.txt"
REVIEWER_PROMPT = PIPE / "prm_reviewer.txt"
GEMINI_URL = os.environ.get(
    "GEMINI_URL",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent")
# موديل أرخص (gemini-3.5-flash-lite، ~60% أرخص للتوكن) للمهام الضيّقة فقط (تدقيق إملائي) --
# اقتصاد فعلي بطلب صريح من المسؤول 2026-09-15، بدون المساس بجودة الكتابة/المراجعة الأساسية.
GEMINI_LITE_URL = os.environ.get(
    "GEMINI_LITE_URL",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent")
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
def _gemini(system: str, user: str, url: str = None) -> dict:
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
    req = urllib.request.Request(url or GEMINI_URL, data=body, method="POST",
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


# روابط محقَّقة يدويًا (بحث فعلي، لا تخمين) لمراجع شائعة الاستخدام في سيناريوهات الدروس --
# تُفضَّل على رابط البحث العام لو اسم المرجع يحتوي أحد هذه المفاتيح.
_KNOWN_REF_LINKS = [
    ("adler", "https://shop.elsevier.com/books/adlers-physiology-of-the-eye/levin/978-0-323-05714-1"),
    ("elkington", "https://www.wiley.com/en-us/Clinical+Optics%2C+3rd+Edition-p-9780632049899"),
    ("clinical optics", "https://www.wiley.com/en-us/Clinical+Optics%2C+3rd+Edition-p-9780632049899"),
    ("snell", "https://onlinelibrary.wiley.com/doi/book/10.1002/9781118690987"),
    ("khurana", "https://archive.org/details/anatomyphysiolog0000khur"),
    ("bcsc", "https://store.aao.org/basic-and-clinical-science-course-section-02-fundamentals-and-principles-of-ophthalmology.html"),
    ("aao", "https://www.aao.org/education"),
]


def _ref_url(name: str) -> str:
    """رابط حقيقي محقَّق لو المرجع معروف (مطابقة بالاسم)، وإلا رابط بحث Google Scholar
    حتمي بالكود (بلا أي تخمين من نموذج) -- يضمن رابطًا صحيحًا شغّالًا دايمًا، ولا يحاول
    توليد رابط دقيق مخترَع لمرجع غير معروف (خطر هلوسة روابط لو تُرك للنموذج)."""
    low = (name or "").lower()
    for key, url in _KNOWN_REF_LINKS:
        if key in low:
            return url
    return "https://scholar.google.com/scholar?q=" + urllib.parse.quote(name or "")


def enrich_refs(refs) -> list[dict]:
    """يحوّل قائمة مراجع (نصوص أو dict) لقائمة {name,url} موحّدة -- من الآن فصاعدًا
    (بتوجيه صريح من المسؤول 2026-09-14): لا مرجع بلا رابط."""
    out = []
    for r in (refs or []):
        if isinstance(r, dict) and r.get("url"):
            out.append({"name": r.get("name") or r["url"], "url": r["url"]})
        else:
            name = r.get("name") if isinstance(r, dict) else str(r)
            out.append({"name": name, "url": _ref_url(name)})
    return out


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
        # شبكة أمان حتمية: Gemini بيهمل حقل visual_focus كتير رغم تعليمات البرومبت —
        # نملأه آليًا من heading/term_en بدل ما نرفض السيناريو كامل ونعيد توليده من الصفر.
        if not sc.get("visual_focus"):
            sc["visual_focus"] = sc.get("term_en") or sc.get("heading") or "eye anatomy overview"
    fs["scientific_refs_ar"] = enrich_refs(fs.get("scientific_refs_ar"))
    return fs


# ---------------- تدقيق إملائي ضيّق النطاق (وكيل مخصّص لمشكلة محددة) ----------------
# قاعدة عامة للمشروع (بتوجيه صريح من المسؤول 2026-09-14): أي مشكلة متكررة محددة في
# التدفق تُحل بخطوة/وكيل ضيّق النطاق مخصّص لها، بدل الاعتماد على إعادة توليد شاملة
# قد تصلح شيئًا وتكسر شيئًا آخر في نفس الوقت (كما لوحظ فعليًا: كل إعادة توليد كاملة
# كانت تصلح خطأ إملائيًا وتُدخل خطأ جديدًا مكانه).
PROOFREAD_SYSTEM = (
    "انت مدقق إملائي فقط، مش كاتب أو محرر. هتستلم عدة مشاهد (scene_no + narration). مهمتك "
    "الوحيدة لكل مشهد: تصحيح الأخطاء الإملائية/الطباعية الحرفية (حروف ناقصة أو زايدة أو "
    "مبدّلة تحوّل الكلمة لكلمة تانية أو كلمة مش موجودة) في نص السرد بالعامية المصرية.\n"
    "ممنوع تمامًا: إعادة الصياغة، تغيير المعنى، تحويل اللهجة لفصحى، حذف أو إضافة جمل، تغيير "
    "طول النص، أو تغيير أي كلمة سليمة إملائيًا حتى لو تقدر تصوغها بشكل أحسن.\n"
    "أعد فقط JSON: {\"scenes\":[{\"scene_no\":N,\"narration\":\"النص كاملًا بعد التصحيح\"}]}\n"
    "-- بنفس عدد المشاهد المُرسلة بالضبط. لو مفيش أي خطأ إملائي في مشهد، أعد نفس نصّه حرفيًا."
)


def proofread_scenes(scenes: list[dict], batch_size: int = 3) -> list[dict]:
    """تدقيق إملائي ضيّق النطاق فقط (خطوة منفصلة عن الكتابة والمراجعة الشاملة) — يصحح
    الأخطاء الطباعية الحرفية فقط بدون إعادة صياغة، حفاظًا على المعنى واللهجة والطول.
    اقتصاد فعلي (2026-09-15، بطلب صريح من المسؤول لتقليل استهلاك الرصيد): دفعات من 3
    مشاهد لكل نداء (بدل مشهد واحد) + موديل أرخص (GEMINI_LITE_URL) -- دفعة صغيرة كفاية
    لتفادي كسر JSON اللي كان بيحصل مع كل المشاهد (9-10) دفعة واحدة، لكن أوفر بكتير من
    نداء منفصل لكل مشهد."""
    idx = [i for i, s in enumerate(scenes) if (s.get("narration") or "").strip()]
    for start in range(0, len(idx), batch_size):
        group = [scenes[i] for i in idx[start:start + batch_size]]
        payload = {"scenes": [{"scene_no": s.get("scene_no"), "narration": s["narration"]} for s in group]}
        try:
            out = _gemini(PROOFREAD_SYSTEM, _json.dumps(payload, ensure_ascii=False), url=GEMINI_LITE_URL)
        except Exception as e:
            nums = [s.get("scene_no") for s in group]
            print(f"[proofread_scenes] مشاهد {nums}: فشل، تم التخطي: {e}", flush=True)
            continue
        fixed = {}
        for x in (out.get("scenes") or []):
            try:
                fixed[int(x["scene_no"])] = x.get("narration", "")
            except Exception:
                continue
        for s in group:
            new = fixed.get(s.get("scene_no"), "")
            old = s.get("narration", "")
            if not new or not new.strip():
                continue
            old_wc, new_wc = len(old.split()), len(new.split())
            # أمان: ارفض أي "تصحيح" غيّر عدد الكلمات بأكثر من 12% -- على الأغلب إعادة صياغة لا تدقيق
            if old_wc and abs(new_wc - old_wc) / old_wc > 0.12:
                print(f"[proofread_scenes] مشهد {s.get('scene_no')}: رُفض (فرق كلمات كبير)", flush=True)
                continue
            s["narration"] = new
            s["caption"] = _TASH_RE.sub("", new)
    return scenes


# ---------------- حل أخير حتمي: استبدال/حذف كلمات عالقة بدل توقف الإنتاج ----------------
# بتوجيه صريح من المسؤول 2026-09-14: لو لسه فيه كلمة فصحى أو تشكيل عالق بعد كل محاولات
# الكتابة والتدقيق، الأفضل استبدالها بمرادف عامي آمن أو حذفها، وقبول تقليص بسيط في عدد
# الكلمات/مدة الفيديو، بدل ما يتوقف الإنتاج بالكامل بانتظار مراجعة بشرية.
_MSA_FIX = {
    "هذا": "ده", "هذه": "دي", "هذان": "دول", "هؤلاء": "دول", "ذلك": "ده", "تلك": "دي",
    "الذي": "اللي", "التي": "اللي", "الذين": "اللي", "اللذان": "اللي",
    "لكنَّ": "بس", "لكن": "بس", "سوف": "", "سـ": "هـ",
    "يتمّ": "بيتم", "يتم ": "بيتم ", "يقوم": "بيعمل", "تقوم": "بتعمل", "نقوم": "بنعمل",
    "عندما": "لما", "حيثُ": "وبما", "حيث ": "وبما ", "لذلك": "عشان كده", "كذلك": "كمان",
    "بينما": "وقت ما", "نستطيع": "نقدر", "يمكننا": "نقدر", "يمكنك": "تقدر",
    "سنشرح": "هنشرح", "سنتحدث": "هنتكلم", "سنتعرف": "هنتعرف", "نتحدث": "بنتكلم", "نستعرض": "بنستعرض",
    "لدى": "عند", "لديه": "عنده", "لديها": "عندها", "فإنَّ": "يبقى", "فإن ": "يبقى ",
    "حينما": "لما", "آنذاك": "وقتها", "هو عبارة عن": "هو", "عبارة عن": "",
    "يُعدّ": "بيتعتبر", "يعدّ": "بيعتبر", "تُعدّ": "بتعتبر", "يُعتبر": "بيعتبر", "لا يزال": "لسه",
}


def _diacritic_tolerant_pattern(bare_word: str) -> str:
    """يبني نمط بحث يطابق الكلمة حتى لو جات في النص محمّلة بتشكيل بين حروفها —
    المشكلة اللي لوحظت فعليًا: marker/word بيوصل بلا تشكيل من المراجعة، لكن نص
    narration المخزّن دايمًا مُشكَّل بالكامل، فمطابقة حرفية (bare) كانت بتفشل صامتة."""
    tash = "[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭـ]*"
    return tash.join(re.escape(ch) for ch in bare_word)


_PARENS = re.compile(r"[（(].*?[）)]")


def _clean_fix_text(fix: str) -> str:
    """احيانا Gemini بيحط شرحا توضيحيا بين قوسين جوه fix -- استبداله حرفيا كان
    بيدخل النص الشارح ده جوه narration فعليا (خطأ لوحظ فعليا). نشيل اي قوسين."""
    return re.sub(r"\s{2,}", " ", _PARENS.sub("", fix)).strip()


def force_resolve_issues(scenes: list[dict], review: dict) -> list[dict]:
    """حل أخير حتمي (بلا نموذج): يستبدل/يحذف أي كلمة فصحى أو تشكيل لسه عالق بعد كل
    محاولات الكتابة والتدقيق والتصحيح الإملائي، بدل ما يوقف الإنتاج بالكامل."""
    by_scene = {s.get("scene_no"): s for s in scenes}

    for v in (review.get("dialect_violations") or []):
        sc = by_scene.get(v.get("scene"))
        if not sc:
            continue
        marker = (v.get("marker") or "").strip()
        if marker:
            # مصدر: dialect_lint الحتمي -- مرادف معروف مسبقًا من _MSA_FIX
            repl = _MSA_FIX.get(marker, "")
            pat = r"(?<![\wء-ي])" + _diacritic_tolerant_pattern(marker) + r"(?![\wء-ي])"
            sc["narration"] = re.sub(pat, repl, sc["narration"])
            sc["narration"] = re.sub(r"\s{2,}", " ", sc["narration"]).strip()
        else:
            # مصدر: مراجعة Gemini نفسها -- بتوفّر quote/fix جاهزين مباشرة
            quote = (v.get("quote") or "").strip()
            fix = _clean_fix_text(v.get("fix") or "")
            if quote and fix:
                pat = _diacritic_tolerant_pattern(quote)
                sc["narration"], n = re.subn(pat, fix, sc["narration"])
                if not n:
                    # النص المقتبس مش مطابق حرفيًا (اختلاف تشكيل/ترقيم) -- استبدال حرفي مباشر كحل بديل
                    sc["narration"] = sc["narration"].replace(quote, fix)

    for i in (review.get("tashkeel_violations") or []):
        sc = by_scene.get(i.get("scene"))
        w, exp = i.get("word"), i.get("expected")
        if sc and w and exp and i.get("type") in ("function_word", "dictionary_fix"):
            pat = r"(?<![\wء-ي])" + _diacritic_tolerant_pattern(w) + r"(?![\wء-ي])"
            sc["narration"] = re.sub(pat, exp, sc["narration"])

    # محاولة حل أفضل جهد لأخطاء علمية بصيغة معتادة من المراجع: "كُتب 'X' ... الصحيح 'Y'"
    # -- استبدال حرفي مباشر لو النمط واضح، وإلا تُترك (خطأ علمي غير قابل للحل الحتمي
    # يبقى عائقًا حقيقيًا يستحق مراجعة، بعكس التشكيل/اللهجة).
    quoted = re.compile(r"['’«»\"]([^'’«»\"]{2,40})['’«»\"]")
    for flag in (review.get("science_flags") or []):
        m = quoted.findall(str(flag))
        if len(m) >= 2:
            wrong, correct = m[0].strip(), m[-1].strip()
            for s in scenes:
                if wrong in s.get("narration", ""):
                    s["narration"] = s["narration"].replace(wrong, correct)

    for s in scenes:
        s["caption"] = _TASH_RE.sub("", s.get("narration", ""))
    return scenes


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
                     "visual_focus": s.get("visual_focus"),
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
    # 0) تصحيح تلقائي حتمي (بلا نموذج) لأي كلمة معروفة حرفيًا في قواميس النطق المعتمدة —
    #    صفر مجازفة لأنه استبدال حرفي مسبق التحقق، مش تخمين.
    fixed_scenes, auto_fixed = tashkeel_qa.apply_dictionary_fixes(scenes)
    fs["scenes"] = fixed_scenes
    scenes = fixed_scenes
    wc = sum(len(s.get("narration", "").split()) for s in scenes)
    g = _gemini_review(fs, lesson)                 # مراجعة تحريرية شاملة (Gemini)
    q = dialect_lint(scenes)                       # مدقّق لهجة حتمي (فوري)
    t = tashkeel_qa.check_scenes(scenes)           # بوابة تشكيل/نطق حتمية (فورية، كود لا نموذج)
    qd = _qwen_deep_dialect(scenes)                # اختياري

    dvi = list(g.get("dialect_violations") or []) + list(q.get("violations") or [])
    tvi = list(t.get("issues") or [])
    must_fix = list(g.get("must_fix") or [])
    if tvi:
        must_fix = must_fix + [
            "تشكيل/نطق: \"%s\" ← \"%s\" (مشهد %s)" % (
                i.get("word", i.get("quote", "")), i.get("expected", i.get("note", "")), i.get("scene"))
            for i in tvi[:8]]
    verdict = "pass"
    if (str(g.get("verdict", "")).lower() == "fail" or q.get("dialect_ok") is False
            or dvi or not t.get("tashkeel_ok", True)):
        verdict = "fail"
    rv = {
        "verdict": verdict,
        "score": g.get("score", 0),
        "word_count_estimate": g.get("word_count_estimate", wc),
        "coverage_gaps": g.get("coverage_gaps") or [],
        "dialect_violations": dvi,
        "tashkeel_violations": tvi,
        "auto_fixed": auto_fixed,
        "science_flags": g.get("science_flags") or [],
        "structure_issues": g.get("structure_issues") or [],
        "visual_issues": g.get("visual_issues") or [],
        "must_fix": must_fix,
        "learned_rule": g.get("learned_rule") or "",
        "reviewers": {"gemini": g.get("verdict"), "dialect_lint": q.get("dialect_ok"),
                      "tashkeel_qa": t.get("tashkeel_ok"),
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
        base_scenes = list(base.get("scenes") or [])
        if base_scenes:
            by_no = {}
            for i, s in enumerate(base_scenes):
                by_no[int(s.get("scene_no") or (i + 1))] = dict(s)
            for s in scenes:
                old = by_no.get(s["scene_no"], {})
                merged = dict(old)
                merged.update({k: v for k, v in s.items() if v not in (None, "", [])})
                if s.get("diagram") in ("", "eye") and old.get("diagram"):
                    merged["diagram"] = old["diagram"]
                if not s.get("term_en") and old.get("term_en"):
                    merged["term_en"] = old["term_en"]
                if old.get("labels"):
                    merged.setdefault("labels", old["labels"])
                if old.get("visual_focus"):
                    merged.setdefault("visual_focus", old["visual_focus"])
                by_no[s["scene_no"]] = merged
            base["scenes"] = [by_no[k] for k in sorted(by_no)]
        else:
            base["scenes"] = scenes
    return base



def auto_remediate(qa: dict, fs: dict, lesson: dict) -> dict:
    """وكيل الإصلاح الذاتي: يحلّل فشل بوابة المراجعة، يصلح ما يُصلَح في السيناريو،
    يقبل ما هو قيد صوتي بحت، ويستخلص قاعدة تعلُّم. يعيد JSON."""
    scenes = fs.get("scenes") or []
    issues = qa.get("issues") or []
    checks = qa.get("checks") or []
    script_txt = "\n".join("(%d) %s" % (s0.get("scene_no", i + 1), s0.get("narration", ""))
                            for i, s0 in enumerate(scenes))
    iss_txt = "\n".join("- [%s] %s" % (it.get("type", ""), it.get("note") or it.get("quote") or "")
                         for it in issues)
    system = (
        "أنت «الوكيل المراجع المُصلِح» في أكاديمية بوابة البصريات. بوابة المراجعة رصدت ملاحظات على "
        "الفيديو بعد إنتاجه. مهمتك: (1) صنّف كل ملاحظة: قابلة للإصلاح في نصّ السيناريو (كلمة خاطئة، "
        "رقم غلط، تعبير علمي غير دقيق، تسرّب فصحى) أم قيد صوتي بحت لا يُصلَح بالنص (مثل نطق القاف همزةً "
        "في اللهجة المصرية — هذا مقبول ولا يُصلَح). (2) للإصلاحات النصّية: أعطِ التعديل الدقيق "
        "(المشهد + النص القديم + النص الجديد) بالعامية المصرية فقط ومع الحفاظ على المعنى والطول. "
        "(3) استخلص قاعدة واحدة مختصرة تُضاف لدليل الأسلوب لمنع تكرار الخطأ. (4) قرّر action: "
        "\"refix\" لو فيه إصلاحات نصّية تستحق إعادة إنتاج، \"accept\" لو كل الملاحظات قيود صوتية "
        "مقبولة أو تافهة، \"escalate\" لو الخطأ جوهري ويحتاج تدخل بشري. "
        "أعد JSON فقط: {\"diagnosis_ar\":\"جملة\",\"script_fixes\":[{\"scene_no\":n,\"field\":\"narration\","
        "\"old\":\"...\",\"new\":\"...\"}],\"accept_as_voice_limitation\":[\"...\"],"
        "\"learned_rule_ar\":\"...\",\"action\":\"refix|accept|escalate\"}\n\n"
        + style_guide()[:3500])
    user = ("الدرس: %s\nحكم البوابة: %s (score %s)\n\nالملاحظات:\n%s\n\nالسيناريو الحالي:\n%s" % (
        lesson.get("title_ar", ""), qa.get("verdict"),
        next((c.get("detail", "") for c in checks if "Gemini" in c.get("check", "")), ""),
        iss_txt, script_txt))
    try:
        out = _gemini(system, user)
    except Exception as e:
        return {"action": "escalate", "diagnosis_ar": "تعذّر استدعاء الوكيل: %s" % e,
                "script_fixes": [], "accept_as_voice_limitation": [], "learned_rule_ar": ""}
    if not isinstance(out, dict):
        return {"action": "escalate", "diagnosis_ar": "رد غير صالح من الوكيل",
                "script_fixes": [], "accept_as_voice_limitation": [], "learned_rule_ar": ""}
    out.setdefault("script_fixes", [])
    out.setdefault("accept_as_voice_limitation", [])
    out.setdefault("action", "escalate")
    out.setdefault("diagnosis_ar", "")
    out.setdefault("learned_rule_ar", "")
    return out


def chat_edit(fs: dict, lesson: dict, user_msg: str, history: list | None = None) -> dict:
    """محادثة تفاعلية: المستخدم يمرّر ملاحظاته للوكيل، والوكيل يرد ويعدّل السيناريو
    حتى يقول المستخدم «اعتمد/نفّذ». يعيد:
      {reply_ar, scene_patches:[{scene_no,field,new}], replace_all_scenes:[...]|None, ready_to_produce}
    """
    history = history or []
    scenes = fs.get("scenes") or []
    script_txt = "\n".join("(%d) [%s] %s" % (s0.get("scene_no", i + 1),
                                              s0.get("heading", ""), s0.get("narration", ""))
                            for i, s0 in enumerate(scenes))
    hist_txt = "\n".join("%s: %s" % ("المستخدم" if h.get("role") == "user" else "الوكيل",
                                      h.get("text", "")) for h in history[-8:])
    system = (
        "أنت «وكيل المراجعة» في أكاديمية بوابة البصريات، بتتكلم مع المسؤول مباشرة على تليجرام "
        "عشان تظبطوا سيناريو الدرس سوا. اللهجة مصرية عامية 100%. كن مختصرًا ومحترفًا.\n"
        "قواعد:\n"
        "- لو المستخدم طلب تعديل واضح (كلمة، جملة، مشهد، نطق، وقفة) — طبّقه فورًا وارجع scene_patches.\n"
        "- لو لصق سيناريو كامل (فيه «〔مشهد») — رجّعه كامل في replace_all_scenes بنفس بنية المشاهد.\n"
        "- لو المستخدم قال «اعتمد» أو «نفّذ» أو «يلا» أو «تمام ابدأ» — اضبط ready_to_produce=true.\n"
        "- لو محتاج توضيح — اسأل سؤال واحد قصير في reply_ar وسيب ready_to_produce=false.\n"
        "- طبّق دليل الأسلوب بصرامة (نطق القاف في المصطلحات العلمية، سُمك بالضم، تعطيش الجيم، لهجة مصرية).\n"
        "أعد JSON فقط: {\"reply_ar\":\"...\",\"scene_patches\":[{\"scene_no\":n,\"field\":\"narration|heading|caption\",\"new\":\"...\"}],"
        "\"replace_all_scenes\":null,\"ready_to_produce\":false}\n\n" + style_guide()[:3000])
    user = ("السيناريو الحالي:\n%s\n\nالمحادثة السابقة:\n%s\n\nرسالة المستخدم الآن:\n%s"
            % (script_txt, hist_txt or "(بداية)", user_msg))
    try:
        out = _gemini(system, user)
    except Exception as e:
        return {"reply_ar": "حصل خطأ عند الوكيل: %s. جرّب تاني." % e,
                "scene_patches": [], "replace_all_scenes": None, "ready_to_produce": False}
    if not isinstance(out, dict):
        return {"reply_ar": "ماقدرتش أفهم — ممكن توضّح؟", "scene_patches": [],
                "replace_all_scenes": None, "ready_to_produce": False}
    out.setdefault("reply_ar", "تمام.")
    out.setdefault("scene_patches", [])
    out.setdefault("replace_all_scenes", None)
    out.setdefault("ready_to_produce", False)
    return out

def learn_from(context: str, human_feedback: str):
    """يُستدعى عند رفض بشري: يقطّر الملاحظة لقاعدة ويضيفها للذاكرة."""
    sysmsg = ("أنت أمين ذاكرة الإنتاج. حوّل ملاحظة المسؤول إلى قاعدة أسلوب واحدة قصيرة "
              "قابلة لإعادة الاستخدام تمنع تكرار الخطأ. أجب JSON: {\"rule\":\"...\"}")
    r = _ollama_json(sysmsg, "السياق: %s\nملاحظة المسؤول: %s" % (context[:1500], human_feedback[:1500]))
    bump_style_guide(r.get("rule", ""), tag="(من ملاحظة المسؤول)")
    return r.get("rule", "")
