import ast
p = "/root/video-factory/main.py"
s = open(p, encoding="utf-8").read()

if "_apply_script" not in s:
    anchor = "def _prepare_lesson(payload: dict) -> dict:"
    fn = '''def _apply_script(payload: dict) -> dict:
    """يعتمد سيناريو المسؤول المعدّل (نصًّا) ويبدأ الإنتاج مباشرة — بلا إعادة توليد."""
    import sys as _s
    _s.path.insert(0, "/root/video-factory/pipeline")
    import agents, prepare_lesson, produce_lesson, json as _j, urllib.request, os as _o, time as _t
    lu = int(payload.get("lesson_uid") or 100002)
    text = str(payload.get("script_text") or "")
    L = prepare_lesson._fetch_lesson(lu)
    fs = agents.parse_script_text(text, {"lesson_code": L["lesson_code"], "video_uid": L["video_uid"],
                                         "title": L["title_ar"]})
    if not fs.get("scenes"):
        return {"status": "error", "detail": "تعذّر قراءة السيناريو — تأكد من التنسيق 〔مشهد N〕"}
    fs["video_uid"] = L["video_uid"]
    fs["lesson_code"] = L["lesson_code"]
    lint = agents.dialect_lint(fs["scenes"])
    # اكتبه معتمدًا في القاعدة
    ot = _j.dumps({"final_script": fs, "status": "PASS", "source": "human_edited"}, ensure_ascii=False)
    url = _o.environ["SUPABASE_URL"] + "/rest/v1/content_outputs"
    key = _o.environ["SUPABASE_SERVICE_KEY"]
    req = urllib.request.Request(url, data=_j.dumps({
        "lesson_uid": lu, "stage_code": "SCRIPT_FINAL", "prompt_binding_uid": "820006",
        "revision_no": int(_t.time()), "output_text": ot, "output_hash": "human",
        "model_used": "human_edited", "approval_status": "approved",
    }).encode(), method="POST", headers={"apikey": key, "Authorization": "Bearer " + key,
                                         "Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()
    produce_lesson.produce_async({"video_uid": L["video_uid"], "lesson_uid": lu,
                                  "lesson_code": L["lesson_code"], "scenes": fs["scenes"],
                                  "title": L["title_ar"], "bookend_set": payload.get("bookend_set") or "V3"})
    return {"status": "producing", "video_uid": L["video_uid"], "scenes": len(fs["scenes"]),
            "dialect_lint": lint}


'''
    s = s.replace(anchor, fn + anchor, 1)

s = s.replace(
    'elif path == "/api/prepare-lesson":\n                result = _prepare_lesson(payload)',
    'elif path == "/api/prepare-lesson":\n                result = _prepare_lesson(payload)\n'
    '            elif path == "/api/apply-script":\n                result = _apply_script(payload)')

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for pr in ["def _apply_script(", '"/api/apply-script"']:
    assert pr in s, pr
    print("ok", pr)
