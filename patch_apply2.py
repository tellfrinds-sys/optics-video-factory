# -*- coding: utf-8 -*-
"""_apply_script: يجمع أجزاء اللصق + debounce + SCRIPT_FINAL معتمد + بدء إنتاج n8n + إشعار المستخدم."""
import io, ast

P = "/root/video-factory/main.py"
s = io.open(P, encoding="utf-8").read()

if "def _notify_user(" in s:
    print("already patched"); raise SystemExit

a = s.index("def _apply_script(payload: dict) -> dict:")
b = s.index("def _prepare_lesson(payload: dict) -> dict:")

M_BAD = "⚠️ تعذّر قراءة السيناريو المعدّل — تأكد من سطر «العنوان: ...» و«〔مشهد N〕 ...» وابعته تاني."
M_START = "\U0001f3ac استلمت السيناريو المعدّل (%d مشهد) وبدأ إنتاج الفيديو. متوقع خلال ~%d دقيقة، وهيوصلك بطاقة مراجعة أول ما يخلص."
M_ERR = "⚠️ تعذّر بدء الإنتاج تلقائيًا: "

NEW = '''def _notify_user(text, lesson_uid=None):
    import json as _j, urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request(
            "https://n8n.opticsgate.online/webhook/notify-user",
            data=_j.dumps({"text": text, "lesson_uid": lesson_uid}).encode(),
            headers={"Content-Type": "application/json"}), timeout=15).read()
    except Exception:
        pass


_MSG_BAD = %r
_MSG_START = %r
_MSG_ERR = %r


def _apply_script(payload: dict) -> dict:
    """يستقبل السيناريو المعدّل (نصًّا، وربما مقسومًا لأجزاء) ويبدأ الإنتاج بلا إعادة توليد."""
    import sys as _s
    _s.path.insert(0, "/root/video-factory/pipeline")
    import agents, prepare_lesson, json as _j, urllib.request, os as _o, time as _t, threading, pathlib
    lu = int(payload.get("lesson_uid") or 100002)
    text = str(payload.get("script_text") or "")
    sd = pathlib.Path("/root/video-factory/outputs/_status")
    sd.mkdir(parents=True, exist_ok=True)
    buf = sd / ("paste_%%d.txt" %% lu)
    tick = sd / ("paste_%%d.tick" %% lu)
    done = sd / ("paste_%%d.done" %% lu)
    if done.exists() and (_t.time() - done.stat().st_mtime) > 1800:
        done.unlink(missing_ok=True)
    with io.open(buf, "a", encoding="utf-8") as f:
        f.write(text.rstrip() + "\\n")
    marker = "%%.6f" %% _t.time()
    tick.write_text(marker)

    def _settle():
        _t.sleep(16)
        try:
            if tick.read_text().strip() != marker:
                return
        except Exception:
            return
        if done.exists():
            return
        done.write_text(str(_t.time()))
        try:
            full = buf.read_text(encoding="utf-8")
        except Exception:
            done.unlink(missing_ok=True); return
        L = prepare_lesson._fetch_lesson(lu)
        base = {"lesson_code": L["lesson_code"], "video_uid": L["video_uid"], "title": L["title_ar"]}
        try:
            _k = _o.environ["SUPABASE_SERVICE_KEY"]; _u = _o.environ["SUPABASE_URL"]
            _q = (_u + "/rest/v1/content_outputs?lesson_uid=eq.%%d&stage_code=eq.SCRIPT_FINAL"
                  "&order=revision_no.desc&limit=1&select=output_text") %% lu
            _rows = _j.loads(urllib.request.urlopen(urllib.request.Request(
                _q, headers={"apikey": _k, "Authorization": "Bearer " + _k}), timeout=20).read())
            if _rows:
                _prev = _j.loads(_rows[0]["output_text"]).get("final_script") or {}
                if _prev.get("scenes"):
                    base["scenes"] = _prev["scenes"]
        except Exception:
            pass
        fs = agents.parse_script_text(full, base)
        if not fs.get("scenes"):
            _notify_user(_MSG_BAD, lu)
            buf.unlink(missing_ok=True); done.unlink(missing_ok=True); return
        buf.unlink(missing_ok=True)
        fs["video_uid"] = L["video_uid"]; fs["lesson_code"] = L["lesson_code"]
        lint = agents.dialect_lint(fs["scenes"])
        ot = _j.dumps({"final_script": fs, "status": "PASS", "source": "human_edited",
                       "dialect_lint": lint}, ensure_ascii=False)
        _url = _o.environ["SUPABASE_URL"] + "/rest/v1/content_outputs"
        _key = _o.environ["SUPABASE_SERVICE_KEY"]
        urllib.request.urlopen(urllib.request.Request(_url, data=_j.dumps({
            "lesson_uid": lu, "stage_code": "SCRIPT_FINAL", "prompt_binding_uid": "820006",
            "revision_no": int(_t.time()), "output_text": ot, "output_hash": "human",
            "model_used": "human_edited", "approval_status": "approved",
        }).encode(), method="POST", headers={"apikey": _key, "Authorization": "Bearer " + _key,
                                             "Content-Type": "application/json"}), timeout=30).read()
        n = len(fs["scenes"]); eta = max(8, n + 6)
        _notify_user(_MSG_START %% (n, eta), lu)
        try:
            urllib.request.urlopen(urllib.request.Request(
                "https://n8n.opticsgate.online/webhook/start-media-production",
                data=b"{}", headers={"Content-Type": "application/json"}), timeout=30).read()
        except Exception as e:
            _notify_user(_MSG_ERR + str(e)[:120], lu)
        _t.sleep(8)
        done.unlink(missing_ok=True)

    threading.Thread(target=_settle, daemon=True).start()
    return {"status": "buffering", "lesson_uid": lu}


''' % (M_BAD, M_START, M_ERR)

s = s[:a] + NEW + s[b:]
ast.parse(s)
io.open(P, "w", encoding="utf-8").write(s)
print("patched OK")
