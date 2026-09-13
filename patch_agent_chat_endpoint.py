# -*- coding: utf-8 -*-
"""main.py: نقطة /api/agent-chat — محادثة المستخدم مع وكيل المراجعة عبر تليجرام."""
import io, ast

P = "/root/video-factory/main.py"
s = io.open(P, encoding="utf-8").read()
if "_agent_chat" in s:
    print("already patched"); raise SystemExit

FN = '''

def _agent_chat(payload: dict) -> dict:
    """المستخدم بيدردش مع وكيل المراجعة لضبط السيناريو ثم يقول «اعتمد» فيبدأ الإنتاج."""
    import sys as _s
    _s.path.insert(0, "/root/video-factory/pipeline")
    import agents, prepare_lesson, produce_lesson, json as _j, os as _o, time as _t, pathlib, threading

    lu = int(payload.get("lesson_uid") or 100002)
    msg = str(payload.get("message") or "").strip()
    sd = pathlib.Path("/root/video-factory/outputs/_status")
    sd.mkdir(parents=True, exist_ok=True)
    chat_f = sd / ("chat_%d.json" % lu)
    draft_f = sd / ("draft_%d.json" % lu)

    L = prepare_lesson._fetch_lesson(lu)
    # حمّل المسوّدة الحالية: من ملف مسوّدة سابق، وإلا من آخر SCRIPT_FINAL
    fs = None
    try:
        fs = _j.loads(draft_f.read_text(encoding="utf-8"))
    except Exception:
        pass
    if not fs or not fs.get("scenes"):
        try:
            _k = _o.environ["SUPABASE_SERVICE_KEY"]; _u = _o.environ["SUPABASE_URL"]
            _q = (_u + "/rest/v1/content_outputs?lesson_uid=eq.%d&stage_code=eq.SCRIPT_FINAL"
                  "&order=revision_no.desc&limit=1&select=output_text") % lu
            import urllib.request
            rows = _j.loads(urllib.request.urlopen(urllib.request.Request(
                _q, headers={"apikey": _k, "Authorization": "Bearer " + _k}), timeout=20).read())
            fs = _j.loads(rows[0]["output_text"]).get("final_script") if rows else None
        except Exception:
            fs = None
    if not fs or not fs.get("scenes"):
        _notify_user("مفيش سيناريو محفوظ للدرس ده أراجعه معاك.", lu)
        return {"status": "no_script"}

    try:
        history = _j.loads(chat_f.read_text(encoding="utf-8"))
    except Exception:
        history = []

    res = agents.chat_edit(fs, {"lesson_uid": lu, "title_ar": L["title_ar"]}, msg, history)

    # طبّق التعديلات على المسوّدة
    if res.get("replace_all_scenes"):
        fs["scenes"] = res["replace_all_scenes"]
    for p in (res.get("scene_patches") or []):
        try:
            i = int(p["scene_no"]) - 1
            if 0 <= i < len(fs["scenes"]) and p.get("new"):
                fs["scenes"][i][p.get("field") or "narration"] = p["new"]
        except Exception:
            pass
    fs["video_uid"] = L["video_uid"]; fs["lesson_code"] = L["lesson_code"]; fs["title"] = L["title_ar"]
    draft_f.write_text(_j.dumps(fs, ensure_ascii=False), encoding="utf-8")

    history.append({"role": "user", "text": msg})
    history.append({"role": "agent", "text": res.get("reply_ar", "")})
    chat_f.write_text(_j.dumps(history[-20:], ensure_ascii=False), encoding="utf-8")

    reply = res.get("reply_ar", "تمام.")

    if res.get("ready_to_produce"):
        # اكتب SCRIPT_FINAL معتمد وابدأ الإنتاج
        try:
            _k = _o.environ["SUPABASE_SERVICE_KEY"]; _u = _o.environ["SUPABASE_URL"]
            import urllib.request
            ot = _j.dumps({"final_script": fs, "status": "PASS", "source": "agent_chat"}, ensure_ascii=False)
            urllib.request.urlopen(urllib.request.Request(
                _u + "/rest/v1/content_outputs", data=_j.dumps({
                    "lesson_uid": lu, "stage_code": "SCRIPT_FINAL", "prompt_binding_uid": "820006",
                    "revision_no": int(_t.time()), "output_text": ot, "output_hash": "agentchat",
                    "model_used": "agent_chat", "approval_status": "approved"}).encode(),
                method="POST", headers={"apikey": _k, "Authorization": "Bearer " + _k,
                                        "Content-Type": "application/json", "Prefer": "return=minimal"}),
                timeout=30).read()
        except Exception as e:
            _notify_user("تعذّر حفظ السيناريو: %s" % str(e)[:120], lu)
            return {"status": "save_failed"}
        chat_f.unlink(missing_ok=True); draft_f.unlink(missing_ok=True)
        try:
            produce_lesson.produce_async({"video_uid": L["video_uid"], "lesson_uid": lu,
                                          "lesson_code": L["lesson_code"], "scenes": fs["scenes"],
                                          "title": L["title_ar"], "bookend_set": "V3"})
        except Exception as e:
            _notify_user("تعذّر بدء الإنتاج: %s" % str(e)[:120], lu)
        reply += "\\n\\n\\U0001f3ac تمام — بدأت إنتاج الفيديو. هيوصلك أول ما يخلص."

    _notify_user("\\U0001f4ac " + reply, lu)
    return {"status": "ok", "ready": bool(res.get("ready_to_produce")),
            "patches": len(res.get("scene_patches") or [])}
'''

anchor = "\ndef _prepare_lesson(payload: dict) -> dict:"
assert anchor in s
s = s.replace(anchor, FN + anchor, 1)

route_old = '            elif path == "/api/apply-script":\n                result = _apply_script(payload)'
route_new = ('            elif path == "/api/apply-script":\n                result = _apply_script(payload)\n'
             '            elif path == "/api/agent-chat":\n                result = _agent_chat(payload)')
assert route_old in s
s = s.replace(route_old, route_new, 1)

ast.parse(s)
io.open(P, "w", encoding="utf-8").write(s)
print("added _agent_chat + route")
