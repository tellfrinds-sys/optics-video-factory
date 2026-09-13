# -*- coding: utf-8 -*-
import io

P = "/root/video-factory/main.py"
s = io.open(P, encoding="utf-8").read()
old = 'mime = "video/mp4" if file.suffix == ".mp4" else "application/json"'
new = ('mime = {".mp4": "video/mp4", ".txt": "text/plain; charset=utf-8", '
       '".json": "application/json; charset=utf-8"}.get(file.suffix, "application/octet-stream")')
if new in s:
    print("main.py already patched")
else:
    assert old in s, "anchor missing in main.py"
    io.open(P, "w", encoding="utf-8").write(s.replace(old, new, 1))
    print("main.py patched")

P = "/root/video-factory/pipeline/prepare_lesson.py"
s = io.open(P, encoding="utf-8").read()
s2 = s.replace('os.environ.get("PUBLIC_BASE", "https://n8n.opticsgate.online")',
               'os.environ.get("PUBLIC_BASE", "https://opticsgate.online")')
if s2 != s:
    io.open(P, "w", encoding="utf-8").write(s2)
    print("prepare_lesson.py patched")
else:
    print("prepare_lesson.py unchanged (already ok?)")
