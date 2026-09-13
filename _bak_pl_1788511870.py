# -*- coding: utf-8 -*-
"""
produce_lesson.py — منسّق الإنتاج الكامل لفيديو درس واحد.

  السكربت --> رندر (narrated_render) --> بوابة مراجعة (qa_gate)
        --> إن نجح: رفع إلى Google Drive + نسخة احتياطية + حذف نسخ السيرفر المؤقتة
        --> إرجاع النتيجة والروابط لـ n8n (الذي يبلّغ تليجرام)

الاستدعاء عبر HTTP:  POST /api/produce-lesson
  {
    "video_uid": 500128,
    "scenes": [...],            # اختياري؛ إن غاب تُقرأ من corrected_scenes.py
    "lesson_code": "B01-U01-C01-L01",
    "force": false,             # true = صدّر حتى لو رست البوابة على fail
    "skip_export": false
  }
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path("/root/video-factory")
OUT = ROOT / "outputs"
ARCHIVE = ROOT / "archive"
ENV_FILE = ROOT / "pipeline" / ".env"

DRIVE_REMOTE = os.environ.get("DRIVE_REMOTE", "optics_drive:OpticsGate/Videos")
PUBLIC_BASE = os.environ.get("PUBLIC_BASE", "https://n8n.opticsgate.online")

sys.path.insert(0, str(ROOT))


def _load_env():
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def _run(cmd, timeout=1200):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _slug(s: str) -> str:
    s = re.sub(r"[^\w؀-ۿ]+", "_", str(s or "")).strip("_")
    return s or "lesson"


def _drive_upload(src: Path, name: str) -> dict:
    _run(["rclone", "mkdir", DRIVE_REMOTE], timeout=60)
    r = _run(["rclone", "copyto", str(src), f"{DRIVE_REMOTE}/{name}",
              "--drive-chunk-size", "16M"], timeout=900)
    if r.returncode != 0:
        return {"ok": False, "error": r.stderr[-300:]}
    link = _run(["rclone", "link", f"{DRIVE_REMOTE}/{name}"], timeout=60).stdout.strip()
    link = [ln for ln in link.splitlines() if ln.startswith("http")]
    return {"ok": True, "name": name, "link": link[0] if link else ""}


def _supabase_upload(src: Path, name: str) -> dict:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    bucket = os.environ.get("SUPABASE_BUCKET", "lesson-videos")
    if not (url and key):
        return {"ok": False, "skipped": True, "error": "SUPABASE_URL/KEY غير مضبوط"}
    import urllib.parse
    qname = urllib.parse.quote(name)
    data = src.read_bytes()
    req = urllib.request.Request(
        f"{url}/storage/v1/object/{bucket}/{qname}", data=data, method="POST",
        headers={"Authorization": f"Bearer {key}", "apikey": key,
                 "Content-Type": "video/mp4", "x-upsert": "true"})
    try:
        with urllib.request.urlopen(req, timeout=900) as rp:
            rp.read()
        return {"ok": True, "path": f"{bucket}/{name}",
                "link": f"{url}/storage/v1/object/authenticated/{bucket}/{qname}"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:300]}


def _cleanup(d: Path):
    for pat in ("S0*.mp4", "silent.mp4", "body.mp4", "intro_n.mp4", "outro_n.mp4",
                "*.degap.m4a", "clips.txt", "segs.txt"):
        for f in d.glob(pat):
            f.unlink(missing_ok=True)
    # يبقى: final_narrated.mp4 (سيُحذف بعد الأرشفة)، S0X.mp3 (لإعادة المراجعة)، captions.ass


def produce(payload: dict) -> dict:
    _load_env()
    t0 = time.time()
    uid = int(payload.get("video_uid") or 500128)
    force = bool(payload.get("force"))
    skip_export = bool(payload.get("skip_export"))
    code = payload.get("lesson_code") or "B01-U01-C01-L01"

    scenes = payload.get("scenes")
    lesson_uid = payload.get("lesson_uid")
    if not scenes and lesson_uid:
        _status_path(uid).write_text(json.dumps(
            {"status": "running", "stage": "script", "started": t0}, ensure_ascii=False))
        import gen_script
        fs = gen_script.gen_script(int(lesson_uid))
        scenes = fs["scenes"]
        uid = int(fs.get("video_uid") or uid)
        code = fs.get("lesson_code") or code
        payload = {**payload, "title": fs.get("title") or payload.get("title")}
        (STATUS_DIR / f"{uid}_script.json").write_text(
            json.dumps(fs, ensure_ascii=False), encoding="utf-8")
    if not scenes:
        import corrected_scenes as cs
        scenes = cs.SCENES
    title = payload.get("title")
    if not title:
        try:
            import corrected_scenes as cs
            title = getattr(cs, "TITLE", "lesson")
        except Exception:
            title = "lesson"

    import narrated_render
    import qa_gate

    d = OUT / f"narrated_{uid}"

    def _stage(name):
        try:
            _status_path(uid).write_text(json.dumps(
                {"status": "running", "stage": name, "started": t0, "now": time.time()},
                ensure_ascii=False))
        except Exception:
            pass

    # 1) رندر
    _stage("render")
    render = narrated_render.render_narrated({
        "video_uid": uid, "scenes": scenes,
        "bookend_set": payload.get("bookend_set") or "V5",
    })
    video = d / "final_narrated.mp4"
    if not video.exists():
        return {"status": "error", "stage": "render", "detail": render}

    # 2) بوابة المراجعة
    _stage("qa")
    qa = qa_gate.run_qa(uid, scenes)

    lesson_uid = int(payload.get("lesson_uid") or (100001 + (uid - 500128)))
    result = {
        "status": "qa_failed" if (qa["verdict"] == "fail" and not force) else "ok",
        "video_uid": uid, "lesson_uid": lesson_uid, "next_lesson_uid": lesson_uid + 1,
        "lesson_code": code, "title": title,
        "qa_verdict": qa["verdict"],
        "qa_issues": qa.get("issues", []),
        "qa_checks": qa.get("checks", []),
        "server_url": f"{PUBLIC_BASE}/outputs/narrated_{uid}/final_narrated.mp4",
        "seconds": render.get("final_seconds"),
        "elapsed": round(time.time() - t0, 1),
    }

    if result["status"] == "qa_failed" or skip_export:
        return result

    # 3) تصدير
    _stage("export")
    ts = time.strftime("%Y%m%d-%H%M")
    fname = f"{_slug(title)}__{code}__{ts}.mp4"
    ascii_name = f"{code}__{ts}.mp4"                           # اسم ASCII لتخزين Supabase
    ARCHIVE.mkdir(exist_ok=True)
    shutil.copy2(video, ARCHIVE / fname)                       # نسخة سيرفر (أرشيف)
    result["drive"] = _drive_upload(video, fname)              # أساسية: Google Drive
    result["backup"] = _supabase_upload(video, ascii_name)     # احتياطية: Supabase Storage
    result["archive_server"] = str(ARCHIVE / fname)

    # 4) تنظيف نسخ السيرفر المؤقتة + النهائية (النسخ السحابية باقية)
    _cleanup(d)
    video.unlink(missing_ok=True)
    result["cleaned"] = True
    result["elapsed"] = round(time.time() - t0, 1)
    return result


STATUS_DIR = OUT / "_status"


def _status_path(uid: int) -> Path:
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    return STATUS_DIR / f"{uid}.json"


def produce_async(payload: dict) -> dict:
    """يشغّل الإنتاج كعملية منفصلة تمامًا (لا تؤثّر على خادم HTTP) ويعيد فورًا."""
    uid = int(payload.get("video_uid") or 500128)
    sp = _status_path(uid)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps({"status": "running", "started": time.time()}, ensure_ascii=False))
    pl_path = STATUS_DIR / f"{uid}_payload.json"
    pl_path.write_text(json.dumps(payload, ensure_ascii=False))
    logf = open(STATUS_DIR / f"{uid}.log", "wb")
    subprocess.Popen(
        [sys.executable, str(ROOT / "produce_lesson.py"), "--run", str(pl_path)],
        stdout=logf, stderr=subprocess.STDOUT, start_new_session=True, cwd=str(ROOT))
    return {"status": "started", "video_uid": uid,
            "poll": f"{PUBLIC_BASE}/api/produce-status/{uid}"}


def produce_sync(payload: dict, max_wait=2400) -> dict:
    """يبدأ الإنتاج (عملية منفصلة) وينتظر النتيجة حتى max_wait ثانية ثم يعيدها."""
    started = produce_async(payload)
    uid = int(payload.get("video_uid") or 500128)
    sp = _status_path(uid)
    t0 = time.time()
    while time.time() - t0 < max_wait:
        time.sleep(8)
        try:
            st = json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if st.get("status") not in ("running", "started"):
            return st
    return {"status": "timeout", "video_uid": uid, "waited": max_wait, "poll": started["poll"]}


def produce_status(uid: int) -> dict:
    sp = _status_path(uid)
    if not sp.exists():
        return {"status": "unknown", "video_uid": uid}
    try:
        return json.loads(sp.read_text(encoding="utf-8"))
    except Exception as e:
        return {"status": "error", "detail": f"تعذّر قراءة الحالة: {e}"}


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--run":
        # وضع العملية المنفصلة: اقرأ payload، شغّل، اكتب النتيجة في _produce.json
        pl_file = Path(sys.argv[2])
        pl = json.loads(pl_file.read_text(encoding="utf-8"))
        uid = int(pl.get("video_uid") or 500128)
        sp = _status_path(uid)
        try:
            res = produce(pl)
        except Exception as e:
            import traceback
            res = {"status": "error", "detail": str(e), "trace": traceback.format_exc()[-2000:]}
        sp.write_text(json.dumps(res, ensure_ascii=False))
        print(json.dumps(res, ensure_ascii=False, indent=1))
    else:
        pl = {}
        if len(sys.argv) > 1:
            pl = json.loads(sys.argv[1]) if sys.argv[1].startswith("{") else {"video_uid": int(sys.argv[1])}
        print(json.dumps(produce(pl), ensure_ascii=False, indent=1))
