import ast
p = "/root/video-factory/main.py"
s = open(p, encoding="utf-8").read()
old = ('def _produce_lesson(payload: dict) -> dict:\n'
       '    """رندر + بوابة مراجعة + تصدير سحابي (غير متزامن)."""\n'
       '    import produce_lesson\n'
       '    return produce_lesson.produce_async(payload)')
new = ('def _produce_lesson(payload: dict) -> dict:\n'
       '    """رندر + بوابة مراجعة + تصدير سحابي."""\n'
       '    import produce_lesson\n'
       '    if payload.get("sync"):\n'
       '        return produce_lesson.produce_sync(payload)\n'
       '    return produce_lesson.produce_async(payload)')
assert old in s, "anchor not found"
s = s.replace(old, new, 1)
open(p, "w", encoding="utf-8").write(s)
ast.parse(s)
print("main.py: sync mode added")
