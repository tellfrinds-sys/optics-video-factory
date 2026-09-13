# -*- coding: utf-8 -*-
"""produce_lesson: يرسل بطاقة الفيديو للمراجعة بنفسه عند انتهاء الإنتاج.
   main._apply_script: ينتج الدرس مباشرة (produce_async) بدل لوتري start-media-production."""
import io, ast

# ---------- produce_lesson.py ----------
P = "/root/video-factory/produce_lesson.py"
s = io.open(P, encoding="utf-8").read()
if "webhook/video-card" not in s:
    OLD = '''    result["elapsed"] = round(time.time() - t0, 1)
    return result


STATUS_DIR = OUT / "_status"'''
    NEW = '''    result["elapsed"] = round(time.time() - t0, 1)
    try:
        import urllib.request as _u, json as _jj
        _u.urlopen(_u.Request(
            "https://n8n.opticsgate.online/webhook/video-card",
            data=_jj.dumps({
                "title": title, "lesson_code": code, "lesson_uid": lesson_uid,
                "seconds": result.get("seconds"), "qa_verdict": result.get("qa_verdict"),
                "drive_link": (result.get("drive") or {}).get("link", ""),
                "auto_healed": bool(result.get("auto_healed")),
                "heal_attempts": result.get("heal_attempts") or 0,
                "heal_log": result.get("heal_log") or [],
                "qa_issues": (result.get("qa_issues") or []) if result.get("delivered_with_notes") else [],
            }).encode(), headers={"Content-Type": "application/json"}), timeout=20).read()
    except Exception as _e:
        print("video-card post skipped:", _e)
    return result


STATUS_DIR = OUT / "_status"'''
    assert OLD in s, "produce return anchor missing"
    s = s.replace(OLD, NEW, 1)
    ast.parse(s)
    io.open(P, "w", encoding="utf-8").write(s)
    print("produce_lesson: video-card hook added")
else:
    print("produce_lesson: already has video-card hook")

# ---------- main.py : _apply_script._settle ----------
P2 = "/root/video-factory/main.py"
m = io.open(P2, encoding="utf-8").read()
OLD2 = '''        try:
            urllib.request.urlopen(urllib.request.Request(
                "https://n8n.opticsgate.online/webhook/start-media-production",
                data=b"{}", headers={"Content-Type": "application/json"}), timeout=30).read()
        except Exception as e:
            _notify_user(_MSG_ERR + str(e)[:120], lu)'''
NEW2 = '''        try:
            import produce_lesson as _pl
            _pl.produce_async({"video_uid": L["video_uid"], "lesson_uid": lu,
                               "lesson_code": L["lesson_code"], "scenes": fs["scenes"],
                               "title": L["title_ar"], "bookend_set": "V3"})
        except Exception as e:
            _notify_user(_MSG_ERR + str(e)[:120], lu)'''
if "import produce_lesson as _pl" in m:
    print("main._apply_script: already direct-produces")
elif OLD2 in m:
    m = io.open(P2, encoding="utf-8").read().replace(OLD2, NEW2, 1)
    ast.parse(m)
    io.open(P2, "w", encoding="utf-8").write(m)
    print("main._apply_script: now calls produce_async directly")
else:
    print("!! main.py anchor not found — check _apply_script")
