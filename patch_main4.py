import ast
p = "/root/video-factory/main.py"
s = open(p, encoding="utf-8").read()

if "_prepare_lesson" not in s:
    anchor = "def _produce_lesson(payload: dict) -> dict:"
    helper = '''def _prepare_lesson(payload: dict) -> dict:
    """كتابة السيناريو + مراجعته + بطاقة اعتماد على تليجرام (بلا إنتاج فيديو)."""
    import sys as _s
    _s.path.insert(0, "/root/video-factory/pipeline")
    import prepare_lesson
    import threading
    lu = int(payload.get("lesson_uid") or 100002)

    def _w():
        try:
            prepare_lesson.prepare({"lesson_uid": lu})
        except Exception as e:
            import traceback, json as _j
            (prepare_lesson.STATUS_DIR / ("script_%s.json" % lu)).write_text(
                _j.dumps({"status": "error", "detail": str(e),
                          "trace": traceback.format_exc()[-1500:]}, ensure_ascii=False))
    threading.Thread(target=_w, daemon=True).start()
    return {"status": "preparing", "lesson_uid": lu}


'''
    s = s.replace(anchor, helper + anchor, 1)

s = s.replace(
    'elif path == "/api/produce-lesson":\n                result = _produce_lesson(payload)',
    'elif path == "/api/produce-lesson":\n                result = _produce_lesson(payload)\n'
    '            elif path == "/api/prepare-lesson":\n                result = _prepare_lesson(payload)')

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for probe in ["def _prepare_lesson(", '"/api/prepare-lesson"']:
    assert probe in s, probe
    print("ok", probe)
