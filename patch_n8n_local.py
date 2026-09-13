import re

# 1) prepare_lesson.py — استخدم البورت المحلي بدل الدومين العام + سجّل نتيجة إرسال البطاقة
p1 = "pipeline/prepare_lesson.py"
s = open(p1, encoding="utf-8").read()
old1 = 'N8N_BASE = os.environ.get("N8N_BASE", "https://n8n.opticsgate.online")'
new1 = 'N8N_BASE = os.environ.get("N8N_BASE", "http://127.0.0.1:5678")  # اتصال محلي — لا يعتمد على DNS العام'
assert old1 in s, "N8N_BASE pattern not found"
s = s.replace(old1, new1)
old2 = '''    try:
        req = urllib.request.Request(SCRIPT_CARD_HOOK, data=json.dumps(card).encode(),
                                     method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
        sent = True
    except Exception as e:
        sent = False
        card["card_error"] = str(e)[:200]'''
new2 = '''    try:
        req = urllib.request.Request(SCRIPT_CARD_HOOK, data=json.dumps(card).encode(),
                                     method="POST", headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
        sent = True
        print("[prepare_lesson] card sent ok for lesson", lesson_uid, flush=True)
    except Exception as e:
        sent = False
        card["card_error"] = str(e)[:200]
        print("[prepare_lesson] CARD SEND FAILED for lesson", lesson_uid, "->", str(e)[:300], flush=True)'''
assert old2 in s, "card send block not found"
s = s.replace(old2, new2)
open(p1, "w", encoding="utf-8").write(s)
print("patched prepare_lesson.py")

# 2) main.py — نفس الشيء لـ notify_user + تسجيل الفشل بدل ابتلاعه بصمت
p2 = "main.py"
s2 = open(p2, encoding="utf-8").read()
old3 = '''def _notify_user(text, lesson_uid=None):
    import json as _j, urllib.request
    try:
        urllib.request.urlopen(urllib.request.Request(
            "https://n8n.opticsgate.online/webhook/notify-user",
            data=_j.dumps({"text": text, "lesson_uid": lesson_uid}).encode(),
            headers={"Content-Type": "application/json"}), timeout=15).read()
    except Exception:
        pass'''
new3 = '''def _notify_user(text, lesson_uid=None):
    import json as _j, urllib.request
    base = os.environ.get("N8N_BASE", "http://127.0.0.1:5678")
    try:
        urllib.request.urlopen(urllib.request.Request(
            base + "/webhook/notify-user",
            data=_j.dumps({"text": text, "lesson_uid": lesson_uid}).encode(),
            headers={"Content-Type": "application/json"}), timeout=15).read()
    except Exception as e:
        print("[_notify_user] FAILED:", str(e)[:300], flush=True)'''
assert old3 in s2, "notify_user block not found"
s2 = s2.replace(old3, new3)
open(p2, "w", encoding="utf-8").write(s2)
print("patched main.py")
