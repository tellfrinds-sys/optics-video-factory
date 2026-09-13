# -*- coding: utf-8 -*-
"""rewire_wf11 — أي ملاحظة على مرحلة SCRIPT_FINAL تروح لوكيل المراجعة (محادثة مباشرة)
   بدل إعادة التوليد. المستخدم يدردش، الوكيل يعدّل، ولما يقول «اعتمد» يبدأ الإنتاج."""
import sqlite3, json, uuid, time

DB = "/root/.n8n/database.sqlite"
FACT, BOT = "nQFAvcCJ9Hwu26ag", "LMKFvWfPglBS5BEZ"
db = sqlite3.connect(DB)


def load(w):
    n, c = db.execute("SELECT nodes,connections FROM workflow_entity WHERE id=?", (w,)).fetchone()
    return json.loads(n), json.loads(c)


def save(w, n, c):
    db.execute("UPDATE workflow_entity SET nodes=?,connections=?,updatedAt=? WHERE id=?",
               (json.dumps(n, ensure_ascii=False), json.dumps(c, ensure_ascii=False),
                time.strftime("%Y-%m-%d %H:%M:%S"), w))


# ===== FACT: webhook agent-chat =====
fn, fc = load(FACT)
if not any(x["name"] == "تشغيل عن بعد محادثة الوكيل" for x in fn):
    fn.append({"parameters": {"httpMethod": "POST", "path": "agent-chat", "options": {}},
               "id": str(uuid.uuid4()), "name": "تشغيل عن بعد محادثة الوكيل",
               "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [-40, 3560],
               "webhookId": "agent-chat-%d" % int(time.time())})
    fn.append({"parameters": {"method": "POST", "url": "http://127.0.0.1:8000/api/agent-chat",
                              "sendHeaders": True,
                              "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                              "sendBody": True, "specifyBody": "json",
                              "jsonBody": "={{ JSON.stringify({ lesson_uid: $json.body.lesson_uid, message: $json.body.message }) }}",
                              "options": {"timeout": 120000}},
               "id": str(uuid.uuid4()), "name": "استدعاء محادثة الوكيل",
               "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [220, 3560]})
    fc["تشغيل عن بعد محادثة الوكيل"] = {"main": [[{"node": "استدعاء محادثة الوكيل", "type": "main", "index": 0}]]}
    print("FACT: webhook agent-chat")
save(FACT, fn, fc)

# ===== BOT: توجيه ملاحظات SCRIPT_FINAL لمحادثة الوكيل =====
bn, bc = load(BOT)
for x in bn:
    if x["name"] == "تحديد رابط المرحلة (ملاحظة)":
        js = x["parameters"]["jsCode"]
        if "agent-chat" not in js:
            js = js.replace(
                "let path = WEBHOOK_PATH[prev.stage_code];\nif (prev.is_full_script) path = 'apply-script';",
                "let path = WEBHOOK_PATH[prev.stage_code];\n"
                "if (prev.is_full_script) path = 'apply-script';\n"
                "if (prev.stage_code === 'SCRIPT_FINAL') path = 'agent-chat';")
            x["parameters"]["jsCode"] = js
            print("BOT: SCRIPT_FINAL -> agent-chat")
    if x["name"] == "تحليل رد Gemini":
        js = x["parameters"]["jsCode"]
        if "lesson_uid" not in js:
            js = js.replace(
                "return [{ json: { output_uid: prev.output_uid, stage_code: prev.stage_code, edit_instruction, raw, is_full_script } }];",
                "const _lu = ($('معرفة المرحلة الحالية المنتظرة').first() || {json:{}}).json.lesson_uid || null;\n"
                "return [{ json: { output_uid: prev.output_uid, stage_code: prev.stage_code, edit_instruction, raw, is_full_script, lesson_uid: _lu } }];")
            x["parameters"]["jsCode"] = js
            print("BOT: تحليل رد Gemini يمرّر lesson_uid")
    if x["name"] == "تحديد رابط المرحلة (ملاحظة)":
        js = x["parameters"]["jsCode"]
        if "lesson_uid: prev.lesson_uid" not in js:
            js = js.replace("return [{ json: { ...prev, webhook_url } }];",
                            "return [{ json: { ...prev, webhook_url, lesson_uid: prev.lesson_uid } }];")
            x["parameters"]["jsCode"] = js
    if x["name"] == "إعادة تشغيل المرحلة بالملاحظة (Webhook)":
        p = x["parameters"]
        p["jsonBody"] = ("={{ JSON.stringify("
                         "$json.webhook_url && $json.webhook_url.indexOf('agent-chat') !== -1"
                         " ? { lesson_uid: $json.lesson_uid, message: $json.raw }"
                         " : ($json.is_full_script"
                         "    ? { output_uid: $json.output_uid, script_text: $json.raw }"
                         "    : { output_uid: $json.output_uid, edit_instruction: $json.edit_instruction })) }}")
        print("BOT: webhook الملاحظة يرسل {lesson_uid,message} للوكيل")
    if x["name"] == "تأكيد للمستخدم: تم استلام الملاحظة":
        x["parameters"]["text"] = ("=💬 وصلت للوكيل المراجع. هو هيراجعها ويرد عليك هنا. "
                                   "كمّل معاه بالتعديلات، ولما تخلص قوله «اعتمد» أو «نفّذ» عشان يبدأ الإنتاج.")
        print("BOT: نص تأكيد الاستلام = محادثة")
    if x["name"] == "طلب الملاحظة النصية":
        x["parameters"]["text"] = ("=✏️ اكتب ملاحظاتك على السيناريو للوكيل المراجع مباشرة "
                                   "(كلمة، جملة، مشهد، نطق، وقفة… أو الصق سيناريو كامل). "
                                   "هو هيرد ويعدّل معاك خطوة خطوة. لما تجهز قول «اعتمد».")
        print("BOT: نص طلب الملاحظة = محادثة الوكيل")
save(BOT, bn, bc)
db.commit()
print("DONE — publish + pm2 restart")
