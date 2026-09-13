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



def _heal_notify(text):
    try:
        import urllib.request, json as _j
        urllib.request.urlopen(urllib.request.Request(
            "https://n8n.opticsgate.online/webhook/notify-user",
            data=_j.dumps({"text": text}).encode(),
            headers={"Content-Type": "application/json"}), timeout=15).read()
    except Exception:
        pass


def _save_healed_script(lesson_uid, code, uid, title, scenes):
    """يكتب نسخة SCRIPT_FINAL معتمدة محدّثة بعد الإصلاح الذاتي."""
    try:
        import urllib.request, json as _j, time as _t
        url = os.environ.get("SUPABASE_URL"); key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not (url and key):
            return
        fs = {"title": title, "lesson_code": code, "video_uid": uid, "scenes": scenes}
        ot = _j.dumps({"final_script": fs, "status": "PASS", "source": "auto_healed"}, ensure_ascii=False)
        urllib.request.urlopen(urllib.request.Request(
            url + "/rest/v1/content_outputs", data=_j.dumps({
                "lesson_uid": int(lesson_uid), "stage_code": "SCRIPT_FINAL",
                "prompt_binding_uid": "820006", "revision_no": int(_t.time()),
                "output_text": ot, "output_hash": "autoheal", "model_used": "auto_healed",
                "approval_status": "approved"}).encode(), method="POST",
            headers={"apikey": key, "Authorization": "Bearer " + key,
                     "Content-Type": "application/json", "Prefer": "return=minimal"}), timeout=30).read()
    except Exception as e:
        print("save healed script skipped:", e)


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

    lesson_uid = int(payload.get("lesson_uid") or (100001 + (uid - 500128)))
    sys.path.insert(0, str(ROOT / "pipeline"))
    import agents as _ag

    MAX_HEAL = int(os.environ.get("MAX_HEAL", "1"))
    heal_log = []
    attempt = 0
    while True:
        _stage("render" if attempt == 0 else "self_heal_%d" % attempt)
        render = narrated_render.render_narrated({
            "video_uid": uid, "scenes": scenes,
            "bookend_set": payload.get("bookend_set") or "V5",
        })
        video = d / "final_narrated.mp4"
        if not video.exists():
            return {"status": "error", "stage": "render", "detail": render}

        _stage("qa")
        qa = qa_gate.run_qa(uid, scenes)

        if qa["verdict"] != "fail" or force or attempt >= MAX_HEAL:
            break

        attempt += 1
        _heal_notify("\U0001f527 بوابة المراجعة رصدت ملاحظات على «%s».\n"
                     "الوكيل المراجع بيحاول الإصلاح تلقائيًا (محاولة %d من %d)…"
                     % (title, attempt, MAX_HEAL))
        try:
            rem = _ag.auto_remediate(qa, {"title": title, "lesson_code": code, "scenes": scenes},
                                     {"lesson_uid": lesson_uid, "title_ar": title})
        except Exception as e:
            heal_log.append("تعذّر استدعاء الوكيل: %s" % e)
            break

        fixes = rem.get("script_fixes") or []
        applied = []
        for fx in fixes:
            try:
                i = int(fx["scene_no"]) - 1
                fld = fx.get("field") or "narration"
                if 0 <= i < len(scenes) and fx.get("new"):
                    cur = str(scenes[i].get(fld, ""))
                    if fx.get("old") and fx["old"] in cur:
                        scenes[i][fld] = cur.replace(fx["old"], fx["new"])
                    else:
                        scenes[i][fld] = fx["new"]
                    if fld == "narration":
                        try:
                            scenes[i]["caption"] = _ag._TASH_RE.sub("", scenes[i]["narration"])
                        except Exception:
                            scenes[i]["caption"] = scenes[i]["narration"]
                    applied.append("مشهد %s" % fx.get("scene_no"))
            except Exception:
                pass
        if rem.get("learned_rule_ar"):
            try:
                _ag.bump_style_guide(rem["learned_rule_ar"], "auto-heal")
            except Exception:
                pass
        heal_log.append(rem.get("diagnosis_ar", ""))
        _heal_notify("\U0001f6e0\ufe0f الوكيل: %s\n%s\nقاعدة اتعلّمها: %s"
                     % (rem.get("diagnosis_ar", "") or "—",
                        ("عدّل: " + "، ".join(applied)) if applied else "قبول كسمة صوتية مصرية (بلا تعديل)",
                        rem.get("learned_rule_ar", "") or "—"))

        if rem.get("action") == "accept" or not applied:
            qa = {"verdict": "pass", "issues": qa.get("issues", []), "checks": qa.get("checks", []),
                  "note": "accepted_by_agent"}
            break
        _save_healed_script(lesson_uid, code, uid, title, scenes)
        # الحلقة تكمّل: إعادة رندر بالسيناريو المصحَّح

    delivered_with_notes = (qa["verdict"] == "fail")
    result = {
        "status": "ok",
        "video_uid": uid, "lesson_uid": lesson_uid, "next_lesson_uid": lesson_uid + 1,
        "lesson_code": code, "title": title,
        "qa_verdict": qa["verdict"],
        "qa_issues": qa.get("issues", []),
        "qa_checks": qa.get("checks", []),
        "auto_healed": attempt > 0,
        "heal_attempts": attempt,
        "heal_log": [x for x in heal_log if x],
        "delivered_with_notes": delivered_with_notes,
        "server_url": f"{PUBLIC_BASE}/outputs/narrated_{uid}/final_narrated.mp4",
        "seconds": render.get("final_seconds"),
        "elapsed": round(time.time() - t0, 1),
    }

    if skip_export:
        return result

    # 3) تصدير
    _stage("export")
    ts = time.strftime("%Y%m%d-%H%M")
    fname = f"{_slug(title)}__{code}__{ts}.mp4"
    ascii_name = f"{code}__{ts}.mp4"                           # اسم ASCII لتخزين Supabase
    ARCHIVE.mkdir(exist_ok=True)
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
        "video_status": "ready"})
    try:
        import build_lessons_page
        build_lessons_page.build()
    except Exception as _e:
        print('lessons page build skipped:', _e)

    # 4) تنظيف نسخ السيرفر المؤقتة + النهائية (النسخ السحابية باقية)
    _cleanup(d)
    video.unlink(missing_ok=True)
    result["cleaned"] = True
    if result.get("delivered_with_notes"):
        _heal_notify("\u2705 الفيديو «%s» اتسلّم للمراجعة، لكن الوكيل ما قدرش يصلّح كل شيء آليًا. "
                     "راجع الملاحظات في البطاقة." % title)
    elif result.get("auto_healed"):
        _heal_notify("\u2705 الوكيل صلّح الملاحظات وأعاد الإنتاج بنجاح — الفيديو «%s» جاهز للمراجعة." % title)
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
