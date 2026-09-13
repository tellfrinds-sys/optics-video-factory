# -*- coding: utf-8 -*-
"""يربط فرع «توليد الوسائط» في n8n ببوابة الإنتاج الجديدة (produce-lesson).
   يُبقي العقد القديمة موجودة لكن غير موصولة (قابل للتراجع)."""
import sqlite3, json, uuid, sys, time

WID = "nQFAvcCJ9Hwu26ag"
DB = "/root/.n8n/database.sqlite"
TG_CHAT = "684277004"
TG_CRED = {"telegramApi": {"id": "tEzgtrUZruzqjJxd", "name": "Telegram Access Token"}}

db = sqlite3.connect(DB)
row = db.execute("SELECT nodes, connections FROM workflow_entity WHERE id=?", (WID,)).fetchone()
nodes = json.loads(row[0])
conns = json.loads(row[1])
by_name = {n["name"]: n for n in nodes}

if "بناء طلب الإنتاج" in by_name:
    print("already wired — skipping add")
    sys.exit(0)

# نسخة احتياطية
open(f"/root/video-factory/_backup_20260902-211514/wf_nodes_{int(time.time())}.json", "w",
     encoding="utf-8").write(json.dumps({"nodes": nodes, "connections": conns}, ensure_ascii=False))


def nid():
    return str(uuid.uuid4())


BX, BY = 700, 1568
new_nodes = [
    {
        "parameters": {"jsCode":
            "const s = $('تحويل JSON للسكريبت').item.json;\n"
            "const fs = (s && s.final_script) || {};\n"
            "return [{ json: {\n"
            "  video_uid: 500128,\n"
            "  lesson_code: 'B01-U01-C01-L01',\n"
            "  title: fs.title || 'رحلة داخل العين البشرية',\n"
            "  sync: true\n"
            "} }];"},
        "id": nid(), "name": "بناء طلب الإنتاج", "type": "n8n-nodes-base.code",
        "typeVersion": 2, "position": [BX, BY],
    },
    {
        "parameters": {
            "method": "POST", "url": "http://127.0.0.1:8000/api/produce-lesson",
            "sendHeaders": True,
            "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
            "sendBody": True, "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify($json) }}",
            "options": {"timeout": 2400000},
        },
        "id": nid(), "name": "تشغيل بوابة الإنتاج", "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2, "position": [BX + 220, BY],
    },
    {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "typeValidation": "loose", "version": 2},
                "combinator": "and",
                "conditions": [{
                    "id": nid(),
                    "leftValue": "={{ $json.status }}", "rightValue": "ok",
                    "operator": {"type": "string", "operation": "equals"},
                }],
            },
            "options": {},
        },
        "id": nid(), "name": "فرع نتيجة الإنتاج", "type": "n8n-nodes-base.if",
        "typeVersion": 2.2, "position": [BX + 440, BY],
    },
    {
        "parameters": {
            "chatId": TG_CHAT,
            "text": "=✅ فيديو «{{ $json.title }}» جاهز ومراجَع آليًا.\n\n"
                    "📁 على درايف (opticsgate@gmail.com):\n{{ $json.drive.link }}\n\n"
                    "🔎 المراجعة: {{ $json.qa_verdict }} · المدة: {{ Math.round($json.seconds) }} ثانية"
                    "{{ ($json.backup && $json.backup.ok) ? '\\n💾 نسخة احتياطية: Supabase ✔' : '' }}",
            "additionalFields": {"appendAttribution": False, "parse_mode": "HTML"},
        },
        "id": nid(), "name": "إشعار نجاح الإنتاج", "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2, "position": [BX + 660, BY - 90], "webhookId": nid(),
        "credentials": TG_CRED,
    },
    {
        "parameters": {
            "chatId": TG_CHAT,
            "text": "=⚠️ بوابة المراجعة أوقفت تسليم فيديو «{{ $json.title }}».\n"
                    "الحكم: {{ $json.qa_verdict }}\n\nالملاحظات:\n"
                    "{{ ($json.qa_issues || []).map(i => '• ' + (i.type||'') + ': ' + (i.quote||i.note||'')).join('\\n') }}\n\n"
                    "الفيديو محفوظ مؤقتًا على السيرفر للمراجعة اليدوية:\n{{ $json.server_url }}",
            "additionalFields": {"appendAttribution": False, "parse_mode": "HTML"},
        },
        "id": nid(), "name": "إشعار توقف المراجعة", "type": "n8n-nodes-base.telegram",
        "typeVersion": 1.2, "position": [BX + 660, BY + 90], "webhookId": nid(),
        "credentials": TG_CRED,
    },
]
nodes.extend(new_nodes)

# إعادة التوصيل
conns.pop("تحويل JSON للسكريبت", None)  # كان -> تقسيم المشاهد
conns["تحويل JSON للسكريبت"] = {"main": [[{"node": "بناء طلب الإنتاج", "type": "main", "index": 0}]]}
conns["بناء طلب الإنتاج"] = {"main": [[{"node": "تشغيل بوابة الإنتاج", "type": "main", "index": 0}]]}
conns["تشغيل بوابة الإنتاج"] = {"main": [[{"node": "فرع نتيجة الإنتاج", "type": "main", "index": 0}]]}
conns["فرع نتيجة الإنتاج"] = {"main": [
    [{"node": "إشعار نجاح الإنتاج", "type": "main", "index": 0}],
    [{"node": "إشعار توقف المراجعة", "type": "main", "index": 0}],
]}
# افصل السلسلة القديمة (تبقى العقد لكن غير مُستدعاة)
for dead in ["تقسيم المشاهد", "تجهيز حقول المشهد", "بناء طلب ترجمة الوصف",
             "استدعاء Gemini لترجمة الوصف", "دمج الوصف الإنجليزي", "توليد الوسائط بالتتابع",
             "تجميع كل المشاهد", "بناء طلب الدمج", "إرسال لسيرفر الدمج"]:
    conns.pop(dead, None)

db.execute("UPDATE workflow_entity SET nodes=?, connections=?, updatedAt=? WHERE id=?",
           (json.dumps(nodes, ensure_ascii=False), json.dumps(conns, ensure_ascii=False),
            time.strftime("%Y-%m-%d %H:%M:%S"), WID))
db.commit()
print("rewired OK — %d nodes, %d connection groups" % (len(nodes), len(conns)))
print("new:", [n["name"] for n in new_nodes])
