# -*- coding: utf-8 -*-
"""style_guide_curator.py — صيانة دورية آمنة لـ pipeline/style_guide.md (ذاكرة التعلّم الحيّة).

المشكلة اللي بُني هذا السكربت لحلّها (لوحظت فعليًا 2026-09-14): الملف بيتضخّم بقواعد
شبه مكررة من كل مراجعة، وأحيانًا قاعدة جديدة بتتناقض مع قاعدة قديمة (مثال حقيقي: قاعدة
قديمة "لازم 850 كلمة على الأقل" ضد سياسة جديدة "ممنوع تتجاوز 750 كلمة") -- والملف بيُحقَن
كاملًا في كل نداء كتابة/مراجعة، فالتناقض بيربك النموذج ويُبطئ التقارب.

سياسة الأمان الصارمة (بطلب صريح من المسؤول 2026-09-14: "الحفاظ على المكتسبات وعدم الإتلاف"):
  1) الحذف الآلي التلقائي يقتصر على تكرار شبه-حرفي فقط (تشابه نصّي >= 0.85 بعد تطبيع
     المسافات/التشكيل) -- قرار حتمي بالكود، صفر تخمين معنى. يُبقي أقدم نسخة (الأصل).
  2) أي حكم يحتاج "فهم معنى" (تناقض بين قاعدتين، قاعدة عفا عليها الزمن) يُستخلص برأي
     Gemini (الحصة المجانية) لكنه **اقتراح للمراجعة فقط -- لا يُحذف ولا يُعدَّل تلقائيًا
     إطلاقًا**. يُكتب تقرير + تنبيه تليجرام، والقرار النهائي لصاحب المشروع أو جلسة Claude.
  3) نسخة احتياطية كاملة قبل أي كتابة على الملف، دائمًا.
  4) الأقسام الثابتة (1 إلى 7، دليل الأسلوب الأساسي) لا تُلمَس إطلاقًا -- الصيانة تقتصر
     على قسم "دروس مستفادة" المُولَّد آليًا فقط.

التشغيل الدوري: انظر تعليق crontab في نهاية الملف (يوميًا مرة واحدة).
"""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("/root/video-factory")
PIPE = ROOT / "pipeline"
GUIDE = PIPE / "style_guide.md"
BACKUP_DIR = PIPE / "_style_guide_backups"
STATUS_FILE = ROOT / "outputs" / "_status" / "style_guide_curator_last.json"
N8N_BASE = os.environ.get("N8N_BASE", "http://127.0.0.1:5678")

sys.path.insert(0, str(PIPE))


def _env():
    f = PIPE / ".env"
    if f.exists():
        for ln in f.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_env()

_TASHKEEL = re.compile("[ؐ-ًؚ-ٰٟۖ-ۜ۟-۪ۨ-ۭـ]")
_RULE_LINE = re.compile(r"^- \[(\d{4}-\d{2}-\d{2})\]\s*(.*)$")


def _normalize(text: str) -> str:
    """تطبيع للمقارنة فقط (مش للتخزين) -- يشيل التشكيل والمسافات الزائدة."""
    t = _TASHKEEL.sub("", text)
    return re.sub(r"\s+", " ", t).strip()


def _split_guide(text: str) -> tuple[str, list[str]]:
    """يفصل الملف لـ (رأس ثابت + قسم دروس مستفادة, قائمة القواعد فقط).
    كل شيء غير سطر قاعدة (- [YYYY-MM-DD] ...) يُعتبر جزءًا من الرأس الثابت ولا يُلمَس."""
    lines = text.splitlines()
    header_lines, rules = [], []
    for ln in lines:
        if _RULE_LINE.match(ln.strip()):
            rules.append(ln)
        else:
            header_lines.append(ln)
    return "\n".join(header_lines), rules


def _backup() -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    dest = BACKUP_DIR / f"style_guide_{int(time.time())}.md"
    dest.write_text(GUIDE.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


def dedupe_near_identical(rules: list[str], threshold: float = 0.85) -> tuple[list[str], list[tuple[str, str]]]:
    """يحذف فقط تكرارًا شبه-حرفيًا (تشابه نصّي عالي الثقة) -- يُبقي أقدم نسخة (بالترتيب
    الزمني في الملف = ترتيب الظهور). يرجّع (القواعد المحتفَظ بها, أزواج [محذوف, بسبب المحتفَظ به])."""
    kept: list[str] = []
    kept_norm: list[str] = []
    removed: list[tuple[str, str]] = []
    for r in rules:
        m = _RULE_LINE.match(r.strip())
        body = _normalize(m.group(2)) if m else _normalize(r)
        is_dup = False
        for i, kn in enumerate(kept_norm):
            ratio = difflib.SequenceMatcher(None, body, kn).ratio()
            if ratio >= threshold:
                removed.append((r, kept[i]))
                is_dup = True
                break
        if not is_dup:
            kept.append(r)
            kept_norm.append(body)
    return kept, removed


CONTRADICTION_SYSTEM = (
    "انت مراجع أرشيفي لملف \"دليل أسلوب\" مشروع إنتاج فيديوهات تعليمية. هتستلم القسم "
    "الثابت (السياسة الرسمية الحالية) وقائمة \"دروس مستفادة\" مُضافة آليًا من مراجعات "
    "سابقة. مهمتك الوحيدة: تحديد أي قاعدة في القائمة (أ) تتناقض صراحة مع القسم الثابت "
    "أو مع قاعدة أخرى أحدث في القائمة، أو (ب) عفا عليها الزمن (بتشير لسياسة قديمة "
    "معروف إنها اتغيرت). **ممنوع اقتراح حذف أي قاعدة لمجرد إنها تبدو زائدة أو تفصيلية "
    "-- فقط تناقض حقيقي واضح أو قِدَم موثّق.**\n"
    "أعد فقط JSON: {\"flags\": [{\"rule_excerpt\": \"أول 80 حرف من القاعدة\", "
    "\"reason\": \"سبب محدد وواضح\"}]}\n"
    "لو مفيش أي تناقض أو قاعدة عفا عليها الزمن، أعد {\"flags\": []}."
)


def flag_contradictions(header: str, rules: list[str]) -> list[dict]:
    """اقتراح للمراجعة البشرية فقط -- لا حذف ولا تعديل تلقائي إطلاقًا."""
    try:
        import agents
    except Exception as e:
        print("[style_guide_curator] تعذّر استيراد agents:", e, flush=True)
        return []
    payload = "القسم الثابت (لا يُلمَس):\n" + header + "\n\nدروس مستفادة:\n" + "\n".join(rules)
    try:
        out = agents._gemini(CONTRADICTION_SYSTEM, payload)
        return out.get("flags") or []
    except Exception as e:
        print("[style_guide_curator] فحص التناقض فشل، تم التخطي:", e, flush=True)
        return []


def _notify(text: str):
    try:
        req = urllib.request.Request(
            N8N_BASE + "/webhook/notify-user", data=json.dumps({"text": text}, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print("[style_guide_curator] notify failed:", e, flush=True)


def run(min_rules_for_ai_check: int = 15) -> dict:
    if not GUIDE.exists():
        return {"status": "no_guide_file"}

    original = GUIDE.read_text(encoding="utf-8")
    header, rules = _split_guide(original)
    n_before = len(rules)

    kept, removed = dedupe_near_identical(rules)
    n_after = len(kept)

    changed = bool(removed)
    if changed:
        _backup()
        new_text = header.rstrip() + "\n" + "\n".join(kept) + "\n"
        GUIDE.write_text(new_text, encoding="utf-8")
        print(f"[style_guide_curator] حذف {len(removed)} تكرار شبه-حرفي ({n_before} -> {n_after})", flush=True)

    flags = []
    if n_after >= min_rules_for_ai_check:
        flags = flag_contradictions(header, kept)

    result = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "rules_before": n_before, "rules_after": n_after,
        "auto_removed_near_duplicates": len(removed),
        "flagged_for_human_review": flags,
    }
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    if changed or flags:
        lines = []
        if changed:
            lines.append(f"🧹 حذفت {len(removed)} قاعدة مكررة شبه-حرفيًا من style_guide.md "
                         f"({n_before} → {n_after}). أصل كل قاعدة محذوفة باقٍ في نسخة احتياطية.")
        if flags:
            lines.append("⚠️ قواعد محتاجة مراجعتك اليدوية (لم تُحذف، اقتراح فقط):")
            for f in flags[:6]:
                lines.append(f"  • {f.get('rule_excerpt', '')} — {f.get('reason', '')}")
        _notify("📋 صيانة دليل الأسلوب:\n\n" + "\n".join(lines))
        print("\n".join(lines), flush=True)
    else:
        print(f"OK -- {n_after} قاعدة، لا تكرار ولا تناقض مرصود.", flush=True)

    return result


if __name__ == "__main__":
    run()

# --- إعداد التشغيل الدوري (crontab -e) -- يوميًا مرة واحدة، كافٍ لمعدل نمو الملف ---
# 30 5 * * * cd /root/video-factory && /usr/bin/python3 style_guide_curator.py >> outputs/_status/style_guide_curator.log 2>&1
