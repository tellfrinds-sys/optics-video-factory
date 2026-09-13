# -*- coding: utf-8 -*-
"""rewire_wf5 — زر «ملاحظات وإعادة» على بطاقة الفيديو:
   vedit -> يطلب الملاحظات -> يفسّرها Gemini -> prepare-lesson بالملاحظات -> بطاقة سيناريو جديدة.
   يعيد استخدام آلية awaiting_chat_id الموجودة."""
import sqlite3, json, uuid, time

DB = "/root/.n8n/database.sqlite"
FACT, BOT = "nQFAvcCJ9Hwu26ag", "LMKFvWfPglBS5BEZ"
CHAT = "684277004"
CRED = {"telegramApi": {"id": "tEzgtrUZruzqjJxd", "name": "Telegram Access Token"}}
SB = "https://ilvgahgnaxxooxvcawyh.supabase.co/rest/v1"
SBKEY = "sb_secret_HcJo0ZQSp66D_Rot-3CrhA_NOfGCcha"
db = sqlite3.connect(DB)


def load(w):
    n, c = db.execute("SELECT nodes,connections FROM workflow_entity WHERE id=?", (w,)).fetchone()
    return json.loads(n), json.loads(c)


def save(w, n, c):
    db.execute("UPDATE workflow_entity SET nodes=?,connections=?,updatedAt=? WHERE id=?",
               (json.dumps(n, ensure_ascii=False), json.dumps(c, ensure_ascii=False),
                time.strftime("%Y-%m-%d %H:%M:%S"), w))


ts = int(time.time())
SB_HDR = {"parameters": [{"name": "apikey", "value": SBKEY},
                         {"name": "Authorization", "value": "Bearer " + SBKEY},
                         {"name": "Content-Type", "value": "application/json"},
                         {"name": "Prefer", "value": "return=representation"}]}

# ===== المصنع =====
fn, fc = load(FACT)
fb = {x["name"]: x for x in fn}

# زر vedit على بطاقة الفيديو
for x in fn:
    if x["name"] == "إشعار نجاح الإنتاج":
        btns = x["parameters"]["inlineKeyboard"]["rows"][0]["row"]["buttons"]
        if not any(b.get("additionalFields", {}).get("callback_data", "").startswith("=vedit") for b in btns):
            btns.insert(1, {"text": "✏️ ملاحظات وإعادة",
                            "additionalFields": {"callback_data": "=vedit:{{ $json.lesson_uid }}"}})

# webhook prepare-with-notes -> يجلب lesson_uid ثم يستدعي /api/prepare-lesson
if "تشغيل عن بعد إعادة بملاحظات" not in fb:
    fn.append({"parameters": {"httpMethod": "POST", "path": "prepare-with-notes", "options": {}},
               "id": str(uuid.uuid4()), "name": "تشغيل عن بعد إعادة بملاحظات",
               "type": "n8n-nodes-base.webhook", "typeVersion": 2,
               "position": [-40, 2400], "webhookId": f"prepare-with-notes-{ts}"})
    fn.append({"parameters": {"url": "=" + SB + "/content_outputs?output_uid=eq.{{ $json.body.output_uid }}&select=lesson_uid",
                              "sendHeaders": True, "headerParameters": SB_HDR, "options": {}},
               "id": str(uuid.uuid4()), "name": "جلب درس الملاحظة",
               "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [200, 2400]})
    fn.append({"parameters": {"method": "POST", "url": "http://127.0.0.1:8000/api/prepare-lesson",
                              "sendHeaders": True,
                              "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                              "sendBody": True, "specifyBody": "json",
                              "jsonBody": "={{ JSON.stringify({ lesson_uid: $json[0].lesson_uid, notes: $('تشغيل عن بعد إعادة بملاحظات').item.json.body.edit_instruction }) }}",
                              "options": {"timeout": 60000}},
               "id": str(uuid.uuid4()), "name": "استدعاء تجهيز بالملاحظات",
               "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [440, 2400]})
    fc["تشغيل عن بعد إعادة بملاحظات"] = {"main": [[{"node": "جلب درس الملاحظة", "type": "main", "index": 0}]]}
    fc["جلب درس الملاحظة"] = {"main": [[{"node": "استدعاء تجهيز بالملاحظات", "type": "main", "index": 0}]]}

save(FACT, fn, fc)
print("factory: زر vedit + webhook prepare-with-notes")

# ===== البوت =====
bn, bc = load(BOT)
for x in bn:
    if x["name"] == "تحليل المدخل" and "vedit" not in x["parameters"]["jsCode"]:
        x["parameters"]["jsCode"] = x["parameters"]["jsCode"].replace(
            "  else if (action === 'vredo') type = 'video_redo';",
            "  else if (action === 'vredo') type = 'video_redo';\n"
            "  else if (action === 'vedit') type = 'video_edit';")
        print("bot: تحليل المدخل يفهم vedit")
    if x["name"] == "دمج ومطابقة الترتيب" and "video_edit" not in x["parameters"]["jsCode"]:
        x["parameters"]["jsCode"] = x["parameters"]["jsCode"].replace(
            "else if (['video_ok','video_redo'].includes(cls.type)) route = cls.type;",
            "else if (['video_ok','video_redo','video_edit'].includes(cls.type)) route = cls.type;")
        print("bot: دمج ومطابقة يمرّر video_edit")
    if x["name"] == "توجيه نهائي":
        p = x["parameters"]
        p["numberOutputs"] = 9
        p["output"] = ("={{ ({approve:0,reject:1,edit_button:2,text_note:3,out_of_order:4,ignore:5,"
                       "video_ok:6,video_redo:7,video_edit:8})[$json.route] ?? 5 }}")
        print("bot: switch -> 9 outputs")
    if x["name"] == "تحديد رابط المرحلة (ملاحظة)":
        js = x["parameters"]["jsCode"]
        if "prepare-with-notes" not in js:
            js = js.replace("SCRIPT_FINAL: 'start-script-final',",
                            "SCRIPT_FINAL: 'prepare-with-notes',")
            x["parameters"]["jsCode"] = js
            print("bot: ملاحظة SCRIPT_FINAL -> prepare-with-notes")

# فرع video_edit: علّم صف SCRIPT_FINAL بانتظار ملاحظة + اطلبها
if not any(y["name"] == "تعليم الدرس بانتظار ملاحظة" for y in bn):
    bn.append({"parameters": {
        "method": "PATCH",
        "url": "=" + SB + "/content_outputs?lesson_uid=eq.{{ $('تحليل المدخل').item.json.output_uid }}&stage_code=eq.SCRIPT_FINAL",
        "sendHeaders": True, "headerParameters": SB_HDR, "sendBody": True, "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ approval_status: 'pending', awaiting_chat_id: String($('تحليل المدخل').item.json.chat_id) }) }}",
        "options": {}},
        "id": str(uuid.uuid4()), "name": "تعليم الدرس بانتظار ملاحظة",
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [900, 1720]})
    bn.append({"parameters": {"chatId": CHAT,
               "text": "=✏️ ابعت ملاحظاتك على الفيديو في رسالة نصية واحدة، وهيتم إعادة تجهيز السيناريو بعد الأخذ بيها ثم تظبيط الإنتاج.",
               "additionalFields": {"appendAttribution": False}},
        "id": str(uuid.uuid4()), "name": "طلب ملاحظات الفيديو",
        "type": "n8n-nodes-base.telegram", "typeVersion": 1.2, "position": [1120, 1720],
        "webhookId": str(uuid.uuid4()), "credentials": CRED})

sw = bc.get("توجيه نهائي", {}).get("main", [])
while len(sw) < 9:
    sw.append([])
sw[8] = [{"node": "تعليم الدرس بانتظار ملاحظة", "type": "main", "index": 0}]
bc["توجيه نهائي"] = {"main": sw}
bc["تعليم الدرس بانتظار ملاحظة"] = {"main": [[{"node": "طلب ملاحظات الفيديو", "type": "main", "index": 0}]]}

save(BOT, bn, bc)
db.commit()
print("DONE — publish + pm2 restart n8n")
