import ast
p = "/root/video-factory/main.py"
s = open(p, encoding="utf-8").read()

# produce -> async
s = s.replace(
    'def _produce_lesson(payload: dict) -> dict:\n'
    '    """رندر + بوابة مراجعة + تصدير سحابي."""\n'
    '    import produce_lesson\n'
    '    return produce_lesson.produce(payload)',
    'def _produce_lesson(payload: dict) -> dict:\n'
    '    """رندر + بوابة مراجعة + تصدير سحابي (غير متزامن)."""\n'
    '    import produce_lesson\n'
    '    return produce_lesson.produce_async(payload)\n'
    '\n'
    '\n'
    'def _produce_status(uid: int) -> dict:\n'
    '    import produce_lesson\n'
    '    return produce_lesson.produce_status(int(uid))')

# GET route for status  (يُدرج قبل معالجة /outputs/)
s = s.replace(
    '            if path.startswith("/outputs/"):',
    '            if path.startswith("/api/produce-status/"):\n'
    '                return self.send_json(200, _produce_status(path.rsplit("/", 1)[-1]))\n'
    '            if path.startswith("/outputs/"):')

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for probe in ["produce_lesson.produce_async(payload)", "def _produce_status(", '"/api/produce-status/"']:
    assert probe in s, probe
    print("ok", probe)
print("main.py async patch done")
