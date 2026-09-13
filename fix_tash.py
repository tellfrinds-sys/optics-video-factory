"""يصلح regex التشكيل المعطوب (كان يبتلع كل الحروف العربية) بترميز \\u آمن تمامًا."""
import re

SAFE = "[\\u0610-\\u061A\\u064B-\\u065F\\u0670\\u06D6-\\u06DC\\u06DF-\\u06E8\\u06EA-\\u06ED\\u0640]"

targets = {
    "/root/video-factory/pipeline/agents.py": "_TASH_RE",
    "/root/video-factory/qa_gate.py": "_TASH",
    "/root/video-factory/narrated_render.py": "_TASHKEEL",
    "/root/video-factory/eye_scene2.py": "_TASHKEEL",
}
for path, name in targets.items():
    s = open(path, encoding="utf-8").read()
    repl = '%s = re.compile("%s")' % (name, SAFE)
    s2 = re.sub(re.escape(name) + r' = re\.compile\((?:r?"[^"]*"|r?\'[^\']*\')\)',
                lambda m: repl, s, count=1)
    if s2 != s:
        open(path, "w", encoding="utf-8").write(s2)
        print("fixed", path)
    else:
        print("NO MATCH", path)

import ast
for path in targets:
    ast.parse(open(path).read())
print("syntax ok — test:", re.compile(SAFE.encode().decode("unicode_escape")).sub("", "القَرْنِيَّة"))
