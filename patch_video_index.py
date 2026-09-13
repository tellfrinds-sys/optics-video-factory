# -*- coding: utf-8 -*-
"""produce_lesson.py:
   - حذف نسخ الفيديو القديمة لنفس الدرس (Drive + Supabase + أرشيف) قبل رفع الجديدة
   - كتابة روابط الفيديو في جدول lessons تلقائيًا (video_url ...) بعد نجاح/فشل الإنتاج
"""
import io, ast

P = "/root/video-factory/produce_lesson.py"
s = io.open(P, encoding="utf-8").read()
if "_purge_old_versions" in s:
    print("already patched"); raise SystemExit

HELPERS = '''

def _patch_lesson(lesson_uid, fields):
    """PATCH صف الدرس في Supabase بروابط/حالة الفيديو."""
    try:
        url = os.environ.get("SUPABASE_URL"); key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not (url and key and lesson_uid):
            return
        req = urllib.request.Request(
            f"{url}/rest/v1/lessons?lesson_uid=eq.{int(lesson_uid)}",
            data=json.dumps(fields, ensure_ascii=False).encode(), method="PATCH",
            headers={"apikey": key, "Authorization": "Bearer " + key,
                     "Content-Type": "application/json", "Prefer": "return=minimal"})
        urllib.request.urlopen(req, timeout=30).read()
    except Exception as e:
        print("patch_lesson failed:", e)


def _purge_old_versions(code, keep_drive=None, keep_ascii=None):
    """يمسح كل فيديوهات نفس رمز الدرس ما عدا النسخة الجديدة."""
    # 1) أرشيف السيرفر
    try:
        for f in ARCHIVE.glob(f"*__{code}__*.mp4"):
            if keep_drive and f.name == keep_drive:
                continue
            f.unlink(missing_ok=True)
    except Exception as e:
        print("purge archive:", e)
    # 2) Google Drive
    try:
        r = _run(["rclone", "lsf", DRIVE_REMOTE], timeout=120)
        for nm in r.stdout.splitlines():
            nm = nm.strip().rstrip("/")
            if f"__{code}__" in nm and nm != (keep_drive or ""):
                _run(["rclone", "deletefile", f"{DRIVE_REMOTE}/{nm}"], timeout=120)
    except Exception as e:
        print("purge drive:", e)
    # 3) Supabase Storage
    try:
        url = os.environ.get("SUPABASE_URL"); key = os.environ.get("SUPABASE_SERVICE_KEY")
        bucket = os.environ.get("SUPABASE_BUCKET", "lesson-videos")
        if url and key:
            lreq = urllib.request.Request(
                f"{url}/storage/v1/object/list/{bucket}",
                data=json.dumps({"prefix": "", "limit": 1000}).encode(), method="POST",
                headers={"apikey": key, "Authorization": "Bearer " + key,
                         "Content-Type": "application/json"})
            items = json.loads(urllib.request.urlopen(lreq, timeout=30).read())
            for it in items:
                nm = it.get("name", "")
                if nm.startswith(f"{code}__") and nm != (keep_ascii or ""):
                    dreq = urllib.request.Request(
                        f"{url}/storage/v1/object/{bucket}/{nm}", method="DELETE",
                        headers={"apikey": key, "Authorization": "Bearer " + key})
                    urllib.request.urlopen(dreq, timeout=30).read()
    except Exception as e:
        print("purge supabase:", e)

'''

s = s.replace("\ndef _drive_upload(src: Path, name: str) -> dict:",
              HELPERS + "\ndef _drive_upload(src: Path, name: str) -> dict:", 1)

# --- qa_failed: سجّل الحالة في الدرس ---
OLD_QF = '''    if result["status"] == "qa_failed" or skip_export:
        return result'''
NEW_QF = '''    if result["status"] == "qa_failed" or skip_export:
        if result["status"] == "qa_failed":
            _patch_lesson(result.get("lesson_uid"), {
                "video_status": "qa_failed", "video_qa_verdict": qa["verdict"],
                "video_duration_seconds": render.get("final_seconds")})
        return result'''
assert OLD_QF in s, "qa_failed anchor missing"
s = s.replace(OLD_QF, NEW_QF, 1)

# --- قبل نسخ الأرشيف: امسح القديم ---
OLD_EX = '''    ARCHIVE.mkdir(exist_ok=True)
    shutil.copy2(video, ARCHIVE / fname)                       # نسخة سيرفر (أرشيف)
    result["drive"] = _drive_upload(video, fname)              # أساسية: Google Drive
    result["backup"] = _supabase_upload(video, ascii_name)     # احتياطية: Supabase Storage
    result["archive_server"] = str(ARCHIVE / fname)'''
NEW_EX = '''    ARCHIVE.mkdir(exist_ok=True)
    _purge_old_versions(code, keep_drive=fname, keep_ascii=ascii_name)   # احذف نسخ الدرس القديمة
    shutil.copy2(video, ARCHIVE / fname)                       # نسخة سيرفر (أرشيف)
    result["drive"] = _drive_upload(video, fname)              # أساسية: Google Drive
    result["backup"] = _supabase_upload(video, ascii_name)     # احتياطية: Supabase Storage
    result["archive_server"] = str(ARCHIVE / fname)
    _patch_lesson(result.get("lesson_uid"), {
        "video_url": (result["drive"] or {}).get("link") or "",
        "video_backup_url": (result["backup"] or {}).get("link") or "",
        "video_duration_seconds": result.get("seconds"),
        "video_qa_verdict": result.get("qa_verdict"),
        "video_published_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
        "video_status": "ready"})'''
assert OLD_EX in s, "export anchor missing"
s = s.replace(OLD_EX, NEW_EX, 1)

ast.parse(s)
io.open(P, "w", encoding="utf-8").write(s)
print("patched produce_lesson.py OK")
