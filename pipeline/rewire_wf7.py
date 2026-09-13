# -*- coding: utf-8 -*-
"""rewire_wf7 (v2) — بطاقة السيناريو: n8n ينزّل ملف .txt كامل ويرسله كمرفق ثنائي
   قبل أزرار الاعتماد، عشان المستخدم ينسخه ويعدّله ويعيد لصقه كـ«نسخة معدّلة»."""
import sqlite3, json, uuid, time

DB = "/root/.n8n/database.sqlite"
FACT = "nQFAvcCJ9Hwu26ag"
CRED = {"telegramApi": {"id": "tEzgtrUZruzqjJxd", "name": "Telegram Access Token"}}
db = sqlite3.connect(DB)

n, c = db.execute("SELECT nodes,connections FROM workflow_entity WHERE id=?", (FACT,)).fetchone()
nn, cc = json.loads(n), json.loads(c)
nn = [x for x in nn if x["name"] not in ("إرسال ملف السيناريو", "تنزيل ملف السيناريو")]

hook = "تشغيل عن بعد بطاقة السيناريو"
card = "بطاقة اعتماد السيناريو"
DL = "تنزيل ملف السيناريو"
DOC = "إرسال ملف السيناريو"

cpos = [ -40, 2040 ]
for x in nn:
    if x["name"] == card:
        cpos = x["position"]

nn.append({
    "parameters": {
        "url": "={{ $json.body.script_url }}",
        "options": {"response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}}},
    },
    "id": str(uuid.uuid4()), "name": DL,
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
    "position": [cpos[0] - 520, cpos[1]],
})
nn.append({
    "parameters": {
        "operation": "sendDocument",
        "chatId": "684277004",
        "binaryData": True,
        "binaryPropertyName": "data",
        "additionalFields": {
            "caption": "📄 سيناريو الدرس كامل — افتح الملف، انسخ كل النص، عدّل فيه، ثم ابعته في رد «✏️ نسخة معدّلة». نسختك تصير مصدر إنتاج الفيديو مباشرة.",
            "fileName": "={{ 'script_' + $('" + hook + "').item.json.body.lesson_uid + '.txt' }}",
            "appendAttribution": False,
        },
    },
    "id": str(uuid.uuid4()), "name": DOC,
    "type": "n8n-nodes-base.telegram", "typeVersion": 1.2,
    "position": [cpos[0] - 260, cpos[1]],
    "credentials": CRED,
})

cc[hook] = {"main": [[{"node": DL, "type": "main", "index": 0}]]}
cc[DL] = {"main": [[{"node": DOC, "type": "main", "index": 0}]]}
cc[DOC] = {"main": [[{"node": card, "type": "main", "index": 0}]]}

db.execute("UPDATE workflow_entity SET nodes=?,connections=?,updatedAt=? WHERE id=?",
           (json.dumps(nn, ensure_ascii=False), json.dumps(cc, ensure_ascii=False),
            time.strftime("%Y-%m-%d %H:%M:%S"), FACT))
db.commit()
print("wired: hook ->", DL, "->", DOC, "->", card)
