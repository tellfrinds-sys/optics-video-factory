# -*- coding: utf-8 -*-
"""
tashkeel_qa.py — بوابة تحقق آلية حتمية (كود، مش حكم نموذج على نفسه) على التشكيل والنطق.

السياسة (بتوجيه المسؤول 2026-09-14):
لا تشكيل شامل لكل حرف. التركيز على:
  1) حروف الجر/العطف/الشرط والضمائر الحرجة نطقيًا (من/على/في/أن/إن/لكن/إذا...).
  2) الوقفات والفواصل — جملة طويلة بلا فاصلة داخلية = خطر نطق متلاحق غلط.
  3) الكلمات المصرية الملتبسة + الأسماء/المصطلحات العلمية — تُقاس مقابل قواميس
     pron_surface.json / pron_optics.json المعتمدة فعليًا في المشروع (لا تخمين من موديل).

يُستدعى من agents.review_script() ويُدمَج في verdict/must_fix بشكل حتمي.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

PIPE = Path(__file__).resolve().parent

_TASHKEEL_MARKS = "ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭ"
_HAS_TASHKEEL = re.compile("[" + _TASHKEEL_MARKS + "]")
_WORD_RE = re.compile(r"[؀-ۿ]+")

# حروف الجر/الوصل/الشرط والضمائر الحرجة نطقيًا — لازم تيجي مشكّلة دايمًا لأن
# غيابها بيسيب المحرك يخمّن (فِي/فَي، مِن/مَن، إِن/أَن...)
FUNCTION_WORDS = {
    "من": "مِن", "الى": "إِلَى", "إلى": "إِلَى", "على": "عَلَى", "عن": "عَن",
    "في": "فِي", "أن": "أَن", "ان": "إِن", "إن": "إِن", "لكن": "لَكِن",
    "إذا": "إِذَا", "اذا": "إِذَا", "مع": "مَع", "عند": "عِند", "بعد": "بَعد",
    "قبل": "قَبل", "كل": "كُل", "او": "أَو", "أو": "أَو", "لأن": "لِأَن",
    "عشان": "عَشان", "علشان": "عَلَشان", "ده": "دَه", "دي": "دِي", "دول": "دُول",
}


def _load_json(name: str) -> dict:
    f = PIPE / name
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except Exception:
        return {}


def strip_tashkeel(w: str) -> str:
    return _HAS_TASHKEEL.sub("", w)


def _dicts():
    """يُعاد تحميلها في كل نداء عشان أي تحديث لاحق على القواميس يتفعّل فورًا بلا إعادة تشغيل."""
    surf = _load_json("pron_surface.json")
    optics = _load_json("pron_optics.json")
    surf.pop("_", None); surf.pop("_ملاحظة", None)
    optics.pop("_", None); optics.pop("_ملاحظة", None)
    return surf, optics


def check_scene_words(narration: str, scene_no: int) -> list[dict]:
    issues = []
    surf, optics = _dicts()
    for w in _WORD_RE.findall(narration):
        bare = strip_tashkeel(w)
        # أ) قاموس معتمد (سطحي أو مصطلحات دخيلة) — الكلمة موجودة بصورتها الخام
        #    ولسه ماتحولتش للصورة الصحيحة المعتمدة فعليًا في المشروع.
        for d, label in ((surf, "pron_surface"), (optics, "pron_optics")):
            if bare in d:
                correct = d[bare]
                if w != correct and w == bare:
                    issues.append({"scene": scene_no, "type": "dictionary_fix",
                                   "word": w, "expected": correct, "source": label})
        # ب) حرف جر/وصل/ضمير حرج بلا أي تشكيل إطلاقًا
        if bare in FUNCTION_WORDS and w == bare:
            issues.append({"scene": scene_no, "type": "function_word",
                           "word": w, "expected": FUNCTION_WORDS[bare]})
    return issues


def check_pauses(narration: str, scene_no: int) -> list[dict]:
    issues = []
    sentences = re.split(r"(?<=[.!؟])\s+", (narration or "").strip())
    for sent in sentences:
        wc = len(sent.split())
        if wc >= 22 and "،" not in sent:
            issues.append({"scene": scene_no, "type": "missing_pause",
                           "note": "جملة من %d كلمة بلا أي فاصلة داخلية — خطر نطق متلاحق بلا وقفة" % wc,
                           "quote": sent.strip()[:160]})
    return issues


def check_scenes(scenes: list[dict]) -> dict:
    """نقطة الدخول الوحيدة. تُستدعى من agents.review_script().
    ملاحظة: missing_pause أسلوبي فقط (فاصلة غايبة) وليس خطأ نطق/معنى حقيقي —
    لا يُسقط tashkeel_ok بمفرده (بتوجيه صريح من المسؤول 2026-09-14: تقليص بسيط أو
    ملاحظات أسلوبية بسيطة لا توقف الإنتاج، فقط أخطاء النطق/اللهجة/العلم الحقيقية)."""
    issues = []
    for s in scenes or []:
        n = s.get("scene_no", 0)
        text = s.get("narration", "") or ""
        issues += check_scene_words(text, n)
        issues += check_pauses(text, n)
    hard = [i for i in issues if i.get("type") != "missing_pause"]
    return {"tashkeel_ok": not hard, "issues": issues}


_ATTACHED_PREFIXES = ("بال", "كال", "فال", "وال", "لل", "ولل", "فلل",
                      "و", "ف", "ب", "ل", "ك", "ال")


def apply_dictionary_fixes(scenes: list[dict]) -> tuple[list[dict], list[dict]]:
    """إصلاح آلي مباشر (بلا نموذج) لأي كلمة موجودة حرفيًا في القواميس المعتمدة —
    صفر مجازفة لأنه استبدال حرفي معروف مسبقًا، مش تخمين. يُرجع (السيناريو المصحَّح, سجل التعديلات).
    بيحاول كمان فصل البادئات الملزوقة (و/ف/ب/ل/ك/ال) عن الكلمة قبل المقارنة — خطأ لوحظ
    فعليًا: كلمة قاموسية ملزوقة ببادئة (زي \"وفسيولوجي\") كانت بتفوت المطابقة صامتة."""
    surf, optics = _dicts()
    merged = {**optics, **surf, **FUNCTION_WORDS}
    applied = []
    for s in scenes or []:
        text = s.get("narration", "") or ""
        def _sub(m):
            w = m.group(0)
            bare = strip_tashkeel(w)
            if bare in merged and w == bare:
                applied.append({"scene": s.get("scene_no"), "before": w, "after": merged[bare]})
                return merged[bare]
            if bare == w:
                for pre in _ATTACHED_PREFIXES:
                    if bare.startswith(pre) and bare[len(pre):] in merged:
                        rest = bare[len(pre):]
                        applied.append({"scene": s.get("scene_no"), "before": w,
                                       "after": pre + merged[rest]})
                        return pre + merged[rest]
            return w
        s["narration"] = _WORD_RE.sub(_sub, text)
    return scenes, applied


if __name__ == "__main__":
    import sys
    demo = [{"scene_no": 1, "narration": "سمك القرنية بيتغير من شخص للتاني والدكتور بيحدد ده بجهاز خاص علشان كده لازم نعرف الفرق"}]
    print(json.dumps(check_scenes(demo), ensure_ascii=False, indent=1))
