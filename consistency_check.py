# -*- coding: utf-8 -*-
"""consistency_check.py — فحص دوري خفيف الوزن (بلا نموذج ذكاء اصطناعي، حتمي بالكامل)
لاكتشاف تعارضات بين حالة قاعدة البيانات (lessons.video_status/video_url) والواقع الفعلي
على السيرفر (archive/) وGoogle Drive -- يلتقط بالضبط نمط مشكلة "الدرس الأول" اللي حصلت
فعليًا (فيديو منتَج ومرفوع على Drive لكن غير مربوط بالموقع لأسابيع بلا أي تنبيه).

قراءة فقط -- لا يعدّل أي شيء في قاعدة البيانات أو الملفات. يرسل تنبيه تليجرام فقط لو لقى
تعارضًا (صمت تام لو كله سليم، لتجنّب إجهاد التنبيهات).

التشغيل: عبر cron كل 6 ساعات (انظر إعداد crontab في نهاية هذا الملف كتعليق).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path("/root/video-factory")
ARCHIVE = ROOT / "archive"
DRIVE_REMOTE = os.environ.get("DRIVE_REMOTE", "optics_drive:OpticsGate/Videos")
N8N_BASE = os.environ.get("N8N_BASE", "http://127.0.0.1:5678")  # اتصال محلي -- لا يعتمد على DNS العام
NOTIFY_HOOK = N8N_BASE + "/webhook/notify-user"
STATUS_FILE = ROOT / "outputs" / "_status" / "consistency_check_last.json"


def _env():
    f = ROOT / "pipeline" / ".env"
    if f.exists():
        for ln in f.read_text().splitlines():
            if "=" in ln and not ln.strip().startswith("#"):
                k, v = ln.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_env()


def _sb_get(path: str):
    url = os.environ["SUPABASE_URL"] + path
    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(url, headers={"apikey": key, "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _drive_files() -> set[str]:
    try:
        r = subprocess.run(["rclone", "lsf", DRIVE_REMOTE], capture_output=True, text=True, timeout=90)
        return {x.strip() for x in r.stdout.splitlines() if x.strip()}
    except Exception as e:
        print("[consistency_check] rclone lsf failed:", e, flush=True)
        return set()


def _archive_files() -> set[str]:
    try:
        return {f.name for f in ARCHIVE.glob("*.mp4")}
    except Exception:
        return set()


def _notify(text: str):
    try:
        req = urllib.request.Request(
            NOTIFY_HOOK, data=json.dumps({"text": text}, ensure_ascii=False).encode(),
            headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print("[consistency_check] notify failed:", e, flush=True)


def run() -> dict:
    lessons = _sb_get(
        "/rest/v1/lessons?select=lesson_uid,lesson_code,title_ar,video_status,video_url"
        "&order=sort_order.asc"
    )
    drive = _drive_files()
    archive = _archive_files()

    orphaned = []     # فيديو منتَج فعليًا (أرشيف أو Drive) لكن lessons.video_status != ready
    broken_link = []  # video_status=ready وvideo_url موجود، لكن مفيش ملف مطابق على Drive حاليًا

    for L in lessons:
        code = L.get("lesson_code") or ""
        if not code:
            continue
        status = L.get("video_status")
        url = L.get("video_url")
        has_drive = any(f"__{code}__" in f for f in drive)
        has_archive = any(f"__{code}__" in f for f in archive)

        if status != "ready" and (has_drive or has_archive):
            orphaned.append({"lesson_code": code, "title_ar": L.get("title_ar"),
                             "on_drive": has_drive, "on_archive": has_archive})

        if status == "ready" and url and not has_drive:
            broken_link.append({"lesson_code": code, "title_ar": L.get("title_ar"), "video_url": url})

    problems = bool(orphaned or broken_link)
    lines = []
    if orphaned:
        lines.append("⚠️ فيديوهات منتَجة فعليًا (على Drive أو أرشيف السيرفر) لكن غير مربوطة بالموقع:")
        for o in orphaned:
            where = "Drive" if o["on_drive"] else "أرشيف السيرفر فقط"
            lines.append(f"  • {o['lesson_code']} — {o['title_ar']} ({where})")
    if broken_link:
        lines.append("⚠️ الموقع بيشاور على فيديو 'متاح' لكن الملف مش موجود على Drive حاليًا:")
        for b in broken_link:
            lines.append(f"  • {b['lesson_code']} — {b['title_ar']}")

    report = "\n".join(lines) if lines else "لا تعارضات."
    result = {"checked_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
              "checked_lessons": len(lessons), "orphaned": orphaned, "broken_link": broken_link}

    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    if problems:
        _notify("🔍 فحص الاتساق الدوري (كل 6 ساعات) رصد تعارضًا يحتاج مراجعتك:\n\n" + report)
        print("PROBLEMS FOUND:\n" + report, flush=True)
    else:
        print(f"OK -- {len(lessons)} lesson(s) checked, no inconsistencies found.", flush=True)

    return result


if __name__ == "__main__":
    run()

# --- إعداد التشغيل الدوري (crontab -e) ---
# 0 */6 * * * cd /root/video-factory && /usr/bin/python3 consistency_check.py >> outputs/_status/consistency_check.log 2>&1
