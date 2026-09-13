# -*- coding: utf-8 -*-
"""rewire_wf8:
   - FACT: webhook notify-user -> Telegram sendMessage (إشعارات السيرفر للمستخدم)
   - FACT: إصلاح jsonBody في «استدعاء اعتماد السيناريو المعدّل» ($json.lesson_uid)
   - BOT: أي ملاحظة على مرحلة SCRIPT_FINAL تُعامَل كجزء من لصق السيناريو (لا إعادة توليد)
   - BOT: نص تأكيد الاستلام يفرّق بين لصق السيناريو والملاحظة القصيرة
"""
import sqlite3, json, uuid, time

DB = "/root/.n8n/database.sqlite"
FACT, BOT = "nQFAvcCJ9Hwu26ag", "LMKFvWfPglBS5BEZ"
CRED = {"telegramApi": {"id": "tEzgtrUZruzqjJxd", "name": "Telegram Access Token"}}
db = sqlite3.connect(DB)


def load(w):
    n, c = db.execute("SELECT nodes,connections FROM workflow_entity WHERE id=?", (w,)).fetchone()
    return json.loads(n), json.loads(c)


def save(w, n, c):
    db.execute("UPDATE workflow_entity SET nodes=?,connections=?,updatedAt=? WHERE id=?",
               (json.dumps(n, ensure_ascii=False), json.dumps(c, ensure_ascii=False),
                time.strftime("%Y-%m-%d %H:%M:%S"), w))


# ===================== FACT =====================
fn, fc = load(FACT)

if not any(x["name"] == "تشغيل عن بعد إشعار المستخدم" for x in fn):
    fn.append({"parameters": {"httpMethod": "POST", "path": "notify-user", "options": {}},
               "id": str(uuid.uuid4()), "name": "تشغيل عن بعد إشعار المستخدم",
               "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [-40, 3080],
               "webhookId": "notify-user-%d" % int(time.time())})
    fn.append({"parameters": {"chatId": "684277004", "text": "={{ $json.body.text }}",
                              "additionalFields": {"appendAttribution": False}},
               "id": str(uuid.uuid4()), "name": "إرسال إشعار للمستخدم",
               "type": "n8n-nodes-base.telegram", "typeVersion": 1.2, "position": [220, 3080],
               "credentials": CRED})
    fc["تشغيل عن بعد إشعار المستخدم"] = {"main": [[{"node": "إرسال إشعار للمستخدم", "type": "main", "index": 0}]]}
    print("FACT: webhook notify-user + telegram")
else:
    print("FACT: notify-user already present")

for x in fn:
    if x["name"] == "استدعاء اعتماد السيناريو المعدّل":
        x["parameters"]["jsonBody"] = (
            "={{ JSON.stringify({ lesson_uid: ($json.lesson_uid || ($json[0] && $json[0].lesson_uid)), "
            "script_text: $('تشغيل عن بعد اعتماد سيناريو معدّل').item.json.body.script_text }) }}")
        print("FACT: jsonBody fixed ->", x["parameters"]["jsonBody"][:80])

save(FACT, fn, fc)

# ===================== BOT =====================
bn, bc = load(BOT)
for x in bn:
    if x["name"] == "تحليل رد Gemini":
        js = x["parameters"]["jsCode"]
        old = ("const is_full_script = raw.indexOf('\\u3014') !== -1 && "
               "/\\u3014\\s*\\u0645\\u0634\\u0647\\u062f/.test(raw);")
        new = ("const is_full_script = (prev.stage_code === 'SCRIPT_FINAL') || "
               "(raw.indexOf('\\u3014') !== -1 && /\\u3014\\s*\\u0645\\u0634\\u0647\\u062f/.test(raw));")
        if old in js:
            x["parameters"]["jsCode"] = js.replace(old, new)
            print("BOT: is_full_script -> يشمل SCRIPT_FINAL")
        elif "prev.stage_code === 'SCRIPT_FINAL'" in js:
            print("BOT: is_full_script already patched")
        else:
            print("BOT: !! لم أجد سطر is_full_script")
    if x["name"] == "تأكيد للمستخدم: تم استلام الملاحظة":
        x["parameters"]["text"] = (
            "={{ $('تحديد رابط المرحلة (ملاحظة)').item.json.is_full_script "
            "? '\\uD83D\\uDCE5 استلمت السيناريو المعدّل. لو مقسوم لأجزاء ابعتهم كلهم ورا بعض — "
            "هجمّعهم وأبدأ الإنتاج خلال لحظات وأبعتلك إشعار بالبدء.' "
            ": ('\\uD83D\\uDCDD تم استلام ملاحظتك وتفسيرها: ' "
            "+ $('تحديد رابط المرحلة (ملاحظة)').item.json.edit_instruction "
            "+ '\\n\\nجاري إعادة توليد: ' + $('تحديد رابط المرحلة (ملاحظة)').item.json.stage_code) }}")
        print("BOT: نص تأكيد الاستلام شرطي")

save(BOT, bn, bc)
db.commit()
print("DONE — شغّل publish_wf.py + pm2 restart n8n")
