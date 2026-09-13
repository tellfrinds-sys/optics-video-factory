# -*- coding: utf-8 -*-
"""rewire_wf10 — webhook «video-card»: المصنع يرسل بطاقة الفيديو للمراجعة بنفسه
   (بدل الاعتماد على لوتري «أحدث SCRIPT_FINAL معتمد» في مسار n8n)."""
import sqlite3, json, uuid, time

DB = "/root/.n8n/database.sqlite"
FACT = "nQFAvcCJ9Hwu26ag"
CRED = {"telegramApi": {"id": "tEzgtrUZruzqjJxd", "name": "Telegram Access Token"}}
db = sqlite3.connect(DB)
n, c = db.execute("SELECT nodes,connections FROM workflow_entity WHERE id=?", (FACT,)).fetchone()
nn, cc = json.loads(n), json.loads(c)

if any(x["name"] == "تشغيل عن بعد بطاقة الفيديو" for x in nn):
    print("already present")
else:
    nn.append({"parameters": {"httpMethod": "POST", "path": "video-card", "options": {}},
               "id": str(uuid.uuid4()), "name": "تشغيل عن بعد بطاقة الفيديو",
               "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [-40, 3320],
               "webhookId": "video-card-%d" % int(time.time())})
    txt = ("=🎥 <b>فيديو جاهز للمراجعة</b>\n{{ $json.body.title }}\n<code>{{ $json.body.lesson_code }}</code>\n\n"
           "المدة: {{ Math.round($json.body.seconds) }} ثانية · المراجعة: {{ $json.body.qa_verdict }}"
           "{{ $json.body.auto_healed ? ' · 🔧 أصلحه الوكيل ('+$json.body.heal_attempts+')' : '' }}\n"
           "📁 <a href=\"{{ $json.body.drive_link }}\">تحميل / مشاهدة (Drive)</a>\n"
           "{{ ($json.body.qa_issues && $json.body.qa_issues.length) ? '\\n⚠️ ملاحظات لم تُصلَح آليًا:\\n' + $json.body.qa_issues.map(i=>'• '+(i.type||'')+': '+(i.note||i.quote||'')).join('\\n') : '' }}"
           "{{ ($json.body.heal_log && $json.body.heal_log.length) ? '\\n\\n🛠️ ما نفّذه الوكيل:\\n' + $json.body.heal_log.map(x=>'• '+x).join('\\n') : '' }}")
    nn.append({"parameters": {"chatId": "684277004", "text": txt, "replyMarkup": "inlineKeyboard",
               "inlineKeyboard": {"rows": [{"row": {"buttons": [
                   {"text": "✅ اعتماد والانتقال للتالي", "additionalFields": {"callback_data": "=vok:{{ $json.body.lesson_uid }}"}},
                   {"text": "✏️ ملاحظات وإعادة", "additionalFields": {"callback_data": "=vedit:{{ $json.body.lesson_uid }}"}},
                   {"text": "🔄 إعادة إنتاج", "additionalFields": {"callback_data": "=vredo:{{ $json.body.lesson_uid }}"}},
               ]}}]},
               "additionalFields": {"appendAttribution": False, "parse_mode": "HTML"}},
               "id": str(uuid.uuid4()), "name": "بطاقة الفيديو للمراجعة",
               "type": "n8n-nodes-base.telegram", "typeVersion": 1.2, "position": [230, 3320],
               "credentials": CRED})
    cc["تشغيل عن بعد بطاقة الفيديو"] = {"main": [[{"node": "بطاقة الفيديو للمراجعة", "type": "main", "index": 0}]]}
    print("added video-card webhook + telegram")

db.execute("UPDATE workflow_entity SET nodes=?,connections=?,updatedAt=? WHERE id=?",
           (json.dumps(nn, ensure_ascii=False), json.dumps(cc, ensure_ascii=False),
            time.strftime("%Y-%m-%d %H:%M:%S"), FACT))
db.commit()
print("saved")
