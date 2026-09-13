import ast
p = "/root/video-factory/main.py"
s = open(p, encoding="utf-8").read()

# 1) استيراد المحرّك الجديد والمنسّق (كسول: داخل الدالة لتفادي كسر البدء لو نقص اعتماد)
if "def _new_render(" not in s:
    anchor = "def render_narrated(payload: dict[str, Any]) -> dict[str, Any]:"
    helper = '''def _new_render(payload: dict) -> dict:
    """المحرّك السردي الجديد (narrated_render)."""
    import narrated_render
    return narrated_render.render_narrated(payload)


def _produce_lesson(payload: dict) -> dict:
    """رندر + بوابة مراجعة + تصدير سحابي."""
    import produce_lesson
    return produce_lesson.produce(payload)


'''
    s = s.replace(anchor, helper + anchor, 1)

# 2) توجيه /api/render-narrated إلى المحرّك الجديد + مسار /api/produce-lesson
s = s.replace(
    'elif path == "/api/render-narrated":\n                result = render_narrated(payload)',
    'elif path == "/api/render-narrated":\n'
    '                result = _new_render(payload)\n'
    '            elif path == "/api/produce-lesson":\n'
    '                result = _produce_lesson(payload)')

open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
for probe in ["def _new_render(", "def _produce_lesson(", '"/api/produce-lesson"', "result = _new_render(payload)"]:
    assert probe in s, probe
    print("ok", probe)
print("main.py patched")
