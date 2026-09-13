# -*- coding: utf-8 -*-
"""rewire_wf6 — «✏️ نسخة معدّلة» على بطاقة السيناريو:
   المستخدم يلصق السيناريو كاملًا -> يُكتشف (〔مشهد) -> webhook apply-script -> إنتاج مباشر."""
import sqlite3, json, uuid, time

DB = "/root/.n8n/database.sqlite"
FACT, BOT = "nQFAvcCJ9Hwu26ag", "LMKFvWfPglBS5BEZ"
SB = "https://ilvgahgnaxxooxvcawyh.supabase.co/rest/v1"
SBKEY = "sb_secret_HcJo0ZQSp66D_Rot-3CrhA_NOfGCcha"
SB_HDR = {"parameters": [{"name": "apikey", "value": SBKEY},
                         {"name": "Authorization", "value": "Bearer " + SBKEY},
                         {"name": "Content-Type", "value": "application/json"}]}
db = sqlite3.connect(DB)


def load(w):
    n, c = db.execute("SELECT nodes,connections FROM workflow_entity WHERE id=?", (w,)).fetchone()
    return json.loads(n), json.loads(c)


def save(w, n, c):
    db.execute("UPDATE workflow_entity SET nodes=?,connections=?,updatedAt=? WHERE id=?",
               (json.dumps(n, ensure_ascii=False), json.dumps(c, ensure_ascii=False),
                time.strftime("%Y-%m-%d %H:%M:%S"), w))


ts = int(time.time())

# ===== المصنع: webhook apply-script =====
fn, fc = load(FACT)
if not any(x["name"] == "تشغيل عن بعد اعتماد سيناريو معدّل" for x in fn):
    fn.append({"parameters": {"httpMethod": "POST", "path": "apply-script", "options": {}},
               "id": str(uuid.uuid4()), "name": "تشغيل عن بعد اعتماد سيناريو معدّل",
               "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [-40, 2560],
               "webhookId": f"apply-script-{ts}"})
    fn.append({"parameters": {"url": "=" + SB + "/content_outputs?output_uid=eq.{{ $json.body.output_uid }}&select=lesson_uid",
                              "sendHeaders": True, "headerParameters": SB_HDR, "options": {}},
               "id": str(uuid.uuid4()), "name": "جلب درس السيناريو المعدّل",
               "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [200, 2560]})
    fn.append({"parameters": {"method": "POST", "url": "http://127.0.0.1:8000/api/apply-script",
                              "sendHeaders": True,
                              "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                              "sendBody": True, "specifyBody": "json",
                              "jsonBody": "={{ JSON.stringify({ lesson_uid: $json[0].lesson_uid, script_text: $('تشغيل عن بعد اعتماد سيناريو معدّل').item.json.body.script_text }) }}",
                              "options": {"timeout": 60000}},
               "id": str(uuid.uuid4()), "name": "استدعاء اعتماد السيناريو المعدّل",
               "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [440, 2560]})
    fc["تشغيل عن بعد اعتماد سيناريو معدّل"] = {"main": [[{"node": "جلب درس السيناريو المعدّل", "type": "main", "index": 0}]]}
    fc["جلب درس السيناريو المعدّل"] = {"main": [[{"node": "استدعاء اعتماد السيناريو المعدّل", "type": "main", "index": 0}]]}
save(FACT, fn, fc)
print("factory: webhook apply-script")

# ===== البوت: كشف السيناريو الكامل في تدفّق الملاحظة =====
bn, bc = load(BOT)
for x in bn:
    if x["name"] == "تحليل رد Gemini":
        js = x["parameters"]["jsCode"]
        if "is_full_script" not in js:
            js = js.replace(
                "return [{ json: { output_uid: prev.output_uid, stage_code: prev.stage_code, edit_instruction } }];",
                "const raw = ($('دمج ومطابقة الترتيب').item.json.note_text || '');\n"
                "const is_full_script = raw.indexOf('\\u3014') !== -1 && /\\u3014\\s*\\u0645\\u0634\\u0647\\u062f/.test(raw);\n"
                "return [{ json: { output_uid: prev.output_uid, stage_code: prev.stage_code, edit_instruction, raw, is_full_script } }];")
            x["parameters"]["jsCode"] = js
            print("bot: تحليل رد Gemini يكتشف السيناريو الكامل")
    if x["name"] == "تحديد رابط المرحلة (ملاحظة)":
        js = x["parameters"]["jsCode"]
        if "apply-script" not in js:
            js = js.replace(
                "const path = WEBHOOK_PATH[prev.stage_code];\nconst webhook_url = path ? ('https://n8n.opticsgate.online/webhook/' + path) : null;\nreturn [{ json: { ...prev, webhook_url } }];",
                "let path = WEBHOOK_PATH[prev.stage_code];\n"
                "if (prev.is_full_script) path = 'apply-script';\n"
                "const webhook_url = path ? ('https://n8n.opticsgate.online/webhook/' + path) : null;\n"
                "return [{ json: { ...prev, webhook_url } }];")
            x["parameters"]["jsCode"] = js
            print("bot: توجيه السيناريو الكامل -> apply-script")
    if x["name"] == "إعادة تشغيل المرحلة بالملاحظة (Webhook)":
        p = x["parameters"]
        p["sendBody"] = True
        p["specifyBody"] = "json"
        p["jsonBody"] = ("={{ JSON.stringify($json.is_full_script"
                         " ? { output_uid: $json.output_uid, script_text: $json.raw }"
                         " : { output_uid: $json.output_uid, edit_instruction: $json.edit_instruction }) }}")
        p.setdefault("sendHeaders", True)
        p.setdefault("headerParameters", {"parameters": [{"name": "Content-Type", "value": "application/json"}]})
        print("bot: webhook الملاحظة يرسل السيناريو أو التعليمة")

for x in bn:
    if x["name"] == "طلب الملاحظة النصية":
        x["parameters"]["text"] = ("=✏️ تمام. الصق الآن السيناريو المعدّل **كامل** بنفس تنسيق الملف "
                                   "(سطر «العنوان: ...» ثم «〔مشهد 1〕 ...» لكل مشهد). "
                                   "نسختك هتصير مصدر إنتاج الفيديو مباشرة بدون إعادة توليد.\n\n"
                                   "أو ابعت ملاحظة قصيرة عادية لو عايز إعادة توليد بالأخذ بيها.")
        print("bot: نص طلب الملاحظة محدّث")

for x in fn:
    if x["name"] == "بطاقة اعتماد السيناريو":
        for b in x["parameters"]["inlineKeyboard"]["rows"][0]["row"]["buttons"]:
            cd = b.get("additionalFields", {}).get("callback_data", "")
            if cd.startswith("=cedit"):
                b["text"] = "✏️ نسخة معدّلة"
            if cd.startswith("=creject"):
                b["text"] = "🔄 إعادة توليد"
save(FACT, fn, fc)
save(BOT, bn, bc)
db.commit()
print("DONE — publish + pm2 restart")
