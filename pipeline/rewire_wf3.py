# -*- coding: utf-8 -*-
"""#3: تشغيل إنتاج الفيديو تلقائيًا عند اعتماد SCI_REVIEW من زر تليجرام — بلا تفعيل يدوي.
   - المصنع: يضيف webhook 'start-media-production' يغذّي 'جلب SCRIPT_FINAL المعتمد'.
   - البوت: بعد اعتماد آخر مرحلة (SCI_REVIEW) يستدعي هذا الويبهوك بدل رسالة (شغّل يدويًا).
"""
import sqlite3, json, uuid, time

DB = "/root/.n8n/database.sqlite"
FACT = "nQFAvcCJ9Hwu26ag"
BOT = "LMKFvWfPglBS5BEZ"
MEDIA_HOOK = "start-media-production"
db = sqlite3.connect(DB)


def load(wid):
    n, c = db.execute("SELECT nodes, connections FROM workflow_entity WHERE id=?", (wid,)).fetchone()
    return json.loads(n), json.loads(c)


def save(wid, nodes, conns):
    db.execute("UPDATE workflow_entity SET nodes=?, connections=?, updatedAt=? WHERE id=?",
               (json.dumps(nodes, ensure_ascii=False), json.dumps(conns, ensure_ascii=False),
                time.strftime("%Y-%m-%d %H:%M:%S"), wid))


ts = int(time.time())
open(f"/root/video-factory/_backup_20260902-211514/wf_{ts}_fact.json", "w", encoding="utf-8").write(
    json.dumps(dict(zip(("nodes", "connections"), load(FACT))), ensure_ascii=False))
open(f"/root/video-factory/_backup_20260902-211514/wf_{ts}_bot.json", "w", encoding="utf-8").write(
    json.dumps(dict(zip(("nodes", "connections"), load(BOT))), ensure_ascii=False))

# ---------- المصنع: أضف webhook ----------
fn, fc = load(FACT)
if not any(x["name"] == "تشغيل عن بعد الإنتاج" for x in fn):
    fn.append({
        "parameters": {"httpMethod": "POST", "path": MEDIA_HOOK, "options": {}},
        "id": str(uuid.uuid4()), "name": "تشغيل عن بعد الإنتاج",
        "type": "n8n-nodes-base.webhook", "typeVersion": 2,
        "position": [200, 1760], "webhookId": f"{MEDIA_HOOK}-{ts}",
    })
    fc.setdefault("تشغيل عن بعد الإنتاج", {"main": [[{"node": "جلب SCRIPT_FINAL المعتمد", "type": "main", "index": 0}]]})
    save(FACT, fn, fc)
    print("factory: webhook 'start-media-production' added")
else:
    print("factory: webhook already present")

# ---------- البوت: SCI_REVIEW -> MEDIA ----------
bn, bc = load(BOT)
for x in bn:
    if x["name"] == "تحديد رابط المرحلة التالية":
        js = x["parameters"]["jsCode"]
        old = "} else if (idx === STAGE_ORDER.length - 1) {\n  is_last = true;\n} else {"
        new = ("} else if (idx === STAGE_ORDER.length - 1) {\n"
               "  next_stage = 'MEDIA';\n"
               "  webhook_url = 'https://n8n.opticsgate.online/webhook/" + MEDIA_HOOK + "';\n"
               "} else {")
        if old in js:
            x["parameters"]["jsCode"] = js.replace(old, new, 1)
            print("bot: next-stage logic updated (SCI_REVIEW -> MEDIA)")
        elif "MEDIA" in js:
            print("bot: already updated")
        else:
            print("bot: WARNING anchor not found — no change")
    if x["name"] == "تأكيد للمستخدم: تمت الموافقة":
        x["parameters"]["text"] = ("=✅ تمت الموافقة.\n{{ $('تحديد رابط المرحلة التالية').item.json.next_stage === 'MEDIA'"
                                   " ? 'بدأ إنتاج الفيديو الآن — هيوصلك إشعار بالرابط لما يجهز (حوالي ١٥ دقيقة).'"
                                   " : 'تم تشغيل المرحلة التالية: ' + $('تحديد رابط المرحلة التالية').item.json.next_stage }}")
        print("bot: confirmation message updated")
save(BOT, bn, bc)

db.commit()
print("DONE — restart n8n:  pm2 restart n8n && pm2 save")
