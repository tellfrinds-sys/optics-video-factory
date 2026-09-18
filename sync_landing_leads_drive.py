# -*- coding: utf-8 -*-
"""sync_landing_leads_drive.py -- يصدّر بيانات كل مهتم/مشترك سجّل اهتمامه عبر النافذة
المنبثقة (soft-launch popup) في الصفحة الرئيسية للموقع (جدول landing_leads على
Supabase) إلى ملف Excel على Google Drive -- بنفس نمط sync_subscribers_drive.py
تمامًا (بطلب صريح من المسؤول 2026-09-18)، عشان يبقى جاهز للتواصل الجماعي/الدوري.

يشتغل دوري عبر cron (يوميًا) -- انظر تعليق crontab في آخر الملف.
"""
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font

ROOT = Path("/root/video-factory")
ENV_FILE = ROOT / "pipeline" / ".env"
OUT_FILE = Path("/root/video-factory/outputs/_status/landing_leads_export.xlsx")
DRIVE_REMOTE = os.environ.get("DRIVE_REMOTE", "optics_drive:OpticsGate/Subscribers")
DRIVE_FILENAME = "المهتمين_والمسجلين_مسبقًا.xlsx"


def _load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _fetch_leads() -> list[dict]:
    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(
        url + "/rest/v1/landing_leads"
              "?select=full_name,email,phone,source,created_at"
              "&order=created_at.desc",
        headers={"apikey": key, "Authorization": "Bearer " + key})
    import json
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _build_workbook(rows: list[dict]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "المهتمين"
    ws.sheet_view.rightToLeft = True

    headers = ["الاسم بالكامل", "الإيميل", "رقم الهاتف", "المصدر", "تاريخ التسجيل"]
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for r in rows:
        ws.append([
            r.get("full_name") or "",
            r.get("email") or "",
            r.get("phone") or "",
            r.get("source") or "",
            (r.get("created_at") or "")[:10],
        ])

    for col in ws.columns:
        width = max((len(str(c.value or "")) for c in col), default=10)
        ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 12), 40)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    wb.save(OUT_FILE)


def _upload_to_drive() -> None:
    subprocess.run(["rclone", "mkdir", DRIVE_REMOTE], timeout=60, check=False)
    r = subprocess.run(
        ["rclone", "copyto", str(OUT_FILE), f"{DRIVE_REMOTE}/{DRIVE_FILENAME}"],
        timeout=300, capture_output=True, text=True)
    if r.returncode != 0:
        print("rclone upload failed:", r.stderr[-500:], flush=True)
        sys.exit(1)


def main():
    _load_env()
    rows = _fetch_leads()
    _build_workbook(rows)
    _upload_to_drive()
    print(f"تم تصدير {len(rows)} مهتم/مسجل مسبقًا إلى Drive: {DRIVE_REMOTE}/{DRIVE_FILENAME}", flush=True)


if __name__ == "__main__":
    main()

# جدولة يومية (أضف بـ crontab -e):
# 15 6 * * * cd /root/video-factory && /usr/bin/python3 sync_landing_leads_drive.py >> outputs/_status/landing_leads_sync.log 2>&1
