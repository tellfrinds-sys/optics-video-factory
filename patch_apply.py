# -*- coding: utf-8 -*-
"""_apply_script: حمّل السيناريو المخزَّن كأساس عشان اللصق الجزئي (مشاهد متغيّرة فقط) يندمج صح."""
import io

P = "/root/video-factory/main.py"
s = io.open(P, encoding="utf-8").read()

OLD = '''    L = prepare_lesson._fetch_lesson(lu)
    fs = agents.parse_script_text(text, {"lesson_code": L["lesson_code"], "video_uid": L["video_uid"],
                                         "title": L["title_ar"]})'''

NEW = '''    L = prepare_lesson._fetch_lesson(lu)
    _base = {"lesson_code": L["lesson_code"], "video_uid": L["video_uid"], "title": L["title_ar"]}
    try:
        _u = (_o.environ["SUPABASE_URL"] + "/rest/v1/content_outputs?lesson_uid=eq.%d"
              "&stage_code=eq.SCRIPT_FINAL&order=revision_no.desc&limit=1&select=output_text") % lu
        _k = _o.environ["SUPABASE_SERVICE_KEY"]
        _rq = urllib.request.Request(_u, headers={"apikey": _k, "Authorization": "Bearer " + _k})
        _rows = _j.loads(urllib.request.urlopen(_rq, timeout=20).read().decode())
        if _rows:
            _prev = _j.loads(_rows[0]["output_text"]).get("final_script") or {}
            if _prev.get("scenes"):
                _base["scenes"] = _prev["scenes"]
    except Exception:
        pass
    fs = agents.parse_script_text(text, _base)'''

if '_base["scenes"] = _prev["scenes"]' in s:
    print("already patched")
else:
    assert OLD in s, "anchor missing"
    io.open(P, "w", encoding="utf-8").write(s.replace(OLD, NEW, 1))
    print("patched _apply_script base-load")
