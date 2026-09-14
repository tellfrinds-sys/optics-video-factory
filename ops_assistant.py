# -*- coding: utf-8 -*-
"""ops_assistant.py — مساعد تشغيلي دوري (الخيار 2): يجمع حالة المشروع من مصادر حتمية
(فحص الاتساق، دروس محتاجة مراجعة بشرية، أخطاء حديثة في اللوجات، مساحة القرص/Drive)،
ويطلب من Gemini (الحصة المجانية -- بلا أي تكلفة) تلخيصها في تقرير عربي مختصر + اقتراحات
مرتبة بالأولوية، ويرسله على تليجرام.

⚠️ لا يتخذ أي إجراء بنفسه إطلاقًا -- قراءة وتلخيص فقط. أي تنفيذ (إنتاج، نشر، تعديل كود)
يفضل قرار المسؤول أو جلسة Claude Code.

استهلاك الحصة المجانية المتوقع: نداء Gemini واحد لكل تشغيلة. مجدول كل 8 ساعات (3 نداءات/يوم)
-- أقل بكثير من حد الحصة المجانية (1500 نداء/يوم، 10 نداءات/دقيقة)، فمجاني بالكامل عمليًا.

يتجاهل Ollama المحلي تمامًا (qwen2.5:7b-instruct) -- تأكدنا عمليًا إنه غير صالح على مواصفات
هذا السيرفر: بطء شديد (~2.5 دقيقة لسؤال بسيطتين) وناتج غير موثوق (خلط لغات).

التشغيل الدوري: انظر تعليق crontab في نهاية الملف.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/root/video-factory")
STATUS_DIR = ROOT / "outputs" / "_status"
ARCHIVE = ROOT / "archive"
N8N_BASE = os.environ.get("N8N_BASE", "http://127.0.0.1:5678")
NOTIFY_HOOK = N8N_BASE + "/webhook/notify-user"
DRIVE_REMOTE = os.environ.get("DRIVE_REMOTE", "optics_drive:OpticsGate/Videos")

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "pipeline"))


def _env():
    f = ROOT / "pipeline" / ".env"
    if f.exists():
        for ln in f.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_env()

import agents          # لإعادة استخدام نفس آلية نداء Gemini (فيها retry/backoff جاهزة)
import consistency_check as cc


def _sb_get(path: str):
    url = os.environ["SUPABASE_URL"] + path
    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(url, headers={"apikey": key, "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _stuck_lessons(hours=48) -> list[dict]:
    """دروس آخر صف SCRIPT_FINAL ليها (بغضّ النظر عن الحالة) بحالة changes_requested/
    rejected/pending خلال آخر N ساعة -- لازم يكون *آخر* صف تحديدًا لا أي صف قديم، وإلا
    درس نجح لاحقًا بعد محاولات فاشلة سيُبلَّغ زورًا كمتعثر (خطأ لوحظ فعليًا في أول تشغيلة)."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - hours * 3600))
    try:
        rows = _sb_get(
            "/rest/v1/content_outputs?stage_code=eq.SCRIPT_FINAL"
            f"&created_at=gte.{cutoff}"
            "&select=lesson_uid,approval_status,created_at,output_text&order=created_at.desc&limit=100"
        )
    except Exception as e:
        print("[ops_assistant] stuck_lessons query failed:", e, flush=True)
        return []
    seen, out = set(), []
    for r in rows:  # أول ظهور لكل lesson_uid هنا = الأحدث فعليًا (النتيجة مرتبة desc)
        lu = r.get("lesson_uid")
        if lu in seen:
            continue
        seen.add(lu)
        if r.get("approval_status") not in ("changes_requested", "rejected", "pending"):
            continue  # آخر حالة فعلية لهذا الدرس ناجحة (approved) -- تجاهله تمامًا
        try:
            review = json.loads(r["output_text"]).get("review") or {}
        except Exception:
            review = {}
        out.append({
            "lesson_uid": lu, "status": r.get("approval_status"), "score": review.get("score"),
            "remaining_dialect": review.get("dialect_violations") or [],
            "remaining_science": review.get("science_flags") or [],
        })
    return out


def _recent_errors(hours=24) -> list[str]:
    """أسطر Traceback/ERROR من ملفات اللوجات المعدَّلة خلال آخر N ساعة تحت outputs/_status."""
    cutoff = time.time() - hours * 3600
    lines = []
    try:
        for f in STATUS_DIR.glob("*.log"):
            if f.stat().st_mtime < cutoff:
                continue
            txt = f.read_text(encoding="utf-8", errors="ignore")
            for m in re.findall(r"^.*(Traceback|ERROR|Error \d{3}).*$", txt, re.M):
                lines.append(f"{f.name}: {m.strip()[:160]}")
    except Exception as e:
        print("[ops_assistant] recent_errors scan failed:", e, flush=True)
    return lines[-20:]


def _disk_and_drive() -> dict:
    info = {}
    try:
        r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=15)
        info["disk"] = r.stdout.strip().splitlines()[-1] if r.stdout else ""
    except Exception:
        info["disk"] = ""
    try:
        r = subprocess.run(["rclone", "about", DRIVE_REMOTE.split(":")[0] + ":"],
                           capture_output=True, text=True, timeout=30)
        info["drive"] = r.stdout.strip()
    except Exception:
        info["drive"] = ""
    return info


OPS_SYSTEM = (
    "انت مساعد تشغيلي (Ops Assistant) لمشروع مصنع فيديوهات تعليمية آلي. هتستلم بيانات حتمية "
    "خام عن حالة المشروع (تعارضات، دروس متعثرة، أخطاء لوجات، مساحة تخزين). مهمتك تلخيص الوضع "
    "في تقرير عربي مختصر جدًا (لا يتجاوز 12 سطر) + قائمة أولويات مرتبة (الأهم أولاً)، موجّه "
    "لصاحب المشروع مباشرة.\n"
    "ممنوع تمامًا: اقتراح تنفيذ أي إجراء تلقائي بنفسك، أو الإيحاء إنك نفّذت أي شيء. أنت بترصد "
    "وتلخّص وتقترح فقط -- التنفيذ الفعلي مسؤولية المالك أو جلسة Claude Code القادمة.\n"
    "لو كل المؤشرات سليمة ومفيش دروس متعثرة ولا أخطاء، اكتب سطرين بس يفيدوا إن كل حاجة تمام.\n"
    "أعد فقط JSON: {\"report_ar\": \"نص التقرير الكامل جاهز للإرسال على تليجرام\"}"
)


def _visual_diversity(hours=48) -> dict:
    """يتحقق دوريًا إن الدروس الحديثة مش كلها بترجع لنفس رسم العين العام -- شبكة أمان
    ضد رجوع مشكلة تكرار نفس الصورة في كل فيديو (لوحظت فعليًا 2026-09-15، حُلّت بوكيل
    agents.select_visuals لكن هذا الفحص يرصد لو المشكلة رجعت مستقبلًا لأي سبب)."""
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - hours * 3600))
    try:
        rows = _sb_get(
            "/rest/v1/content_outputs?stage_code=eq.SCRIPT_FINAL&approval_status=eq.approved"
            f"&created_at=gte.{cutoff}&select=lesson_uid,output_text&order=created_at.desc&limit=20"
        )
    except Exception as e:
        print("[ops_assistant] visual_diversity query failed:", e, flush=True)
        return {}
    seen_lessons, counts = set(), {}
    for r in rows:
        lu = r.get("lesson_uid")
        if lu in seen_lessons:
            continue
        seen_lessons.add(lu)
        try:
            scenes = json.loads(r["output_text"]).get("final_script", {}).get("scenes", [])
        except Exception:
            continue
        for s in scenes:
            d = s.get("diagram") or "eye"
            # eye_scene2.py مايعرفش غير cornea_layers وgemini_custom كأنواع خاصة -- أي قيمة
            # تانية (حتى لو اسم مخترَع مقنع زي visual_pathway) بترجع فعليًا لنفس رسم العين
            # العام -- بنحسبها هنا كده عشان الرقم يعكس الواقع اللي بيشوفه المشاهد فعلًا.
            bucket = d if d in ("cornea_layers", "gemini_custom") else "eye (fallback)"
            counts[bucket] = counts.get(bucket, 0) + 1
    total = sum(counts.values())
    eye_frac = (counts.get("eye (fallback)", 0) / total) if total else 0
    return {"lessons_checked": len(seen_lessons), "diagram_counts": counts,
            "eye_fraction": round(eye_frac, 2), "flag": eye_frac > 0.7 and total >= 6}


def run() -> dict:
    consistency = cc.run()
    stuck = _stuck_lessons()
    errors = _recent_errors()
    infra = _disk_and_drive()

    visuals = _visual_diversity()

    payload = {
        "فحص_الاتساق": {"فيديوهات_غير_مربوطة": consistency.get("orphaned"),
                        "روابط_معطلة": consistency.get("broken_link")},
        "دروس_متعثرة_آخر_48_ساعة": stuck,
        "أخطاء_لوجات_آخر_24_ساعة": errors,
        "تخزين": infra,
        "تنوع_الرسم_البصري_آخر_48_ساعة": visuals,
    }

    try:
        out = agents._gemini(OPS_SYSTEM, json.dumps(payload, ensure_ascii=False))
        report = out.get("report_ar") or "تعذّر توليد التقرير (رد غير متوقع من Gemini)."
    except Exception as e:
        # احتياطي حتمي بلا نموذج -- التقرير الخام لو Gemini غير متاح (لسه مفيد، أقل تنسيقًا)
        print("[ops_assistant] Gemini call failed, falling back to raw report:", e, flush=True)
        parts = ["📋 تقرير تشغيلي (احتياطي بلا تلخيص AI):"]
        if consistency.get("orphaned") or consistency.get("broken_link"):
            parts.append(f"- تعارضات اتساق: {len(consistency.get('orphaned', []))} فيديو غير مربوط، "
                         f"{len(consistency.get('broken_link', []))} رابط معطّل.")
        if stuck:
            parts.append(f"- {len(stuck)} درس متعثر محتاج مراجعة بشرية.")
        if errors:
            parts.append(f"- {len(errors)} خطأ في اللوجات آخر 24 ساعة.")
        if len(parts) == 1:
            parts.append("كل المؤشرات سليمة.")
        report = "\n".join(parts)

    _notify("🧭 " + report)
    print(report, flush=True)
    return {"report": report, "consistency": consistency, "stuck": stuck, "errors": errors}


def _notify(text: str):
    try:
        req = urllib.request.Request(
            NOTIFY_HOOK, data=json.dumps({"text": text}, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print("[ops_assistant] notify failed:", e, flush=True)


if __name__ == "__main__":
    run()

# --- إعداد التشغيل الدوري (crontab -e) -- 3 مرات/يوم، بعيد جدًا عن حد الحصة المجانية ---
# 0 */8 * * * cd /root/video-factory && /usr/bin/python3 ops_assistant.py >> outputs/_status/ops_assistant.log 2>&1
