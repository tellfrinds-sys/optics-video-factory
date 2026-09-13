# -*- coding: utf-8 -*-
"""
rewire_wf4 — يكمل قيادة المشروع من تليجرام:
  المصنع:
   • webhook 'send-script-card' -> بطاقة اعتماد السيناريو (أزرار capprove/cedit/creject)
   • 'جلب SCRIPT_FINAL المعتمد' -> أحدث سيناريو معتمد (بلا قيد lesson_uid)
   • 'إشعار نجاح الإنتاج' -> بطاقة فيديو (أزرار vok/vredo + رابط درايف)
   • webhooks 'prepare-next' / 'prepare-again' -> /api/prepare-lesson
  البوت:
   • 'تحليل المدخل' يفهم vok/vredo
   • 'توجيه نهائي' (switch) +2 مخرج -> فرعا الفيديو
   • 'تحديد رابط المرحلة التالية': SCRIPT_FINAL هو آخر مرحلة -> MEDIA
"""
import sqlite3, json, uuid, time, sys

DB = "/root/.n8n/database.sqlite"
FACT, BOT = "nQFAvcCJ9Hwu26ag", "LMKFvWfPglBS5BEZ"
CHAT = "684277004"
CRED = {"telegramApi": {"id": "tEzgtrUZruzqjJxd", "name": "Telegram Access Token"}}
BASE = "https://n8n.opticsgate.online/webhook"
db = sqlite3.connect(DB)


def load(w):
    n, c = db.execute("SELECT nodes,connections FROM workflow_entity WHERE id=?", (w,)).fetchone()
    return json.loads(n), json.loads(c)


def save(w, n, c):
    db.execute("UPDATE workflow_entity SET nodes=?,connections=?,updatedAt=? WHERE id=?",
               (json.dumps(n, ensure_ascii=False), json.dumps(c, ensure_ascii=False),
                time.strftime("%Y-%m-%d %H:%M:%S"), w))


ts = int(time.time())
for w, tag in ((FACT, "fact"), (BOT, "bot")):
    n, c = load(w)
    open(f"/root/video-factory/_backup_20260902-211514/wf4_{ts}_{tag}.json", "w",
         encoding="utf-8").write(json.dumps({"nodes": n, "connections": c}, ensure_ascii=False))

# ================= المصنع =================
fn, fc = load(FACT)
fb = {x["name"]: x for x in fn}


def add_node(nn):
    if nn["name"] not in fb:
        fn.append(nn); fb[nn["name"]] = nn; return True
    return False


# -- بطاقة اعتماد السيناريو --
if add_node({
    "parameters": {"httpMethod": "POST", "path": "send-script-card", "options": {}},
    "id": str(uuid.uuid4()), "name": "تشغيل عن بعد بطاقة السيناريو",
    "type": "n8n-nodes-base.webhook", "typeVersion": 2,
    "position": [-40, 1980], "webhookId": f"send-script-card-{ts}"}):
    pass
add_node({
    "parameters": {
        "chatId": CHAT, "text": "={{ $json.body.summary }}",
        "replyMarkup": "inlineKeyboard",
        "inlineKeyboard": {"rows": [{"row": {"buttons": [
            {"text": "✅ اعتماد وإنتاج", "additionalFields": {"callback_data": "=capprove:{{ $json.body.output_uid }}"}},
            {"text": "✏️ ملاحظات", "additionalFields": {"callback_data": "=cedit:{{ $json.body.output_uid }}"}},
            {"text": "🔄 إعادة", "additionalFields": {"callback_data": "=creject:{{ $json.body.output_uid }}"}},
        ]}}]},
        "additionalFields": {"appendAttribution": False, "parse_mode": "HTML"}},
    "id": str(uuid.uuid4()), "name": "بطاقة اعتماد السيناريو",
    "type": "n8n-nodes-base.telegram", "typeVersion": 1.2,
    "position": [200, 1980], "webhookId": str(uuid.uuid4()), "credentials": CRED})
fc["تشغيل عن بعد بطاقة السيناريو"] = {"main": [[{"node": "بطاقة اعتماد السيناريو", "type": "main", "index": 0}]]}

# -- جلب SCRIPT_FINAL المعتمد: أحدث معتمد --
for x in fn:
    if x["name"] == "جلب SCRIPT_FINAL المعتمد":
        x["parameters"]["url"] = ("https://ilvgahgnaxxooxvcawyh.supabase.co/rest/v1/content_outputs"
                                  "?stage_code=eq.SCRIPT_FINAL&approval_status=eq.approved"
                                  "&select=output_text,lesson_uid&order=revision_no.desc&limit=1")

# -- webhooks prepare-next / prepare-again --
for path, delta, label in (("prepare-next", 1, "التالي"), ("prepare-again", 0, "نفسه")):
    add_node({
        "parameters": {"httpMethod": "POST", "path": path, "options": {}},
        "id": str(uuid.uuid4()), "name": f"تشغيل عن بعد تجهيز {label}",
        "type": "n8n-nodes-base.webhook", "typeVersion": 2,
        "position": [-40, 2140 + delta * 120], "webhookId": f"{path}-{ts}"})
    add_node({
        "parameters": {"method": "POST", "url": "http://127.0.0.1:8000/api/prepare-lesson",
                       "sendHeaders": True,
                       "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                       "sendBody": True, "specifyBody": "json",
                       "jsonBody": "={{ JSON.stringify({ lesson_uid: Number($json.body.lesson_uid) }) }}",
                       "options": {"timeout": 60000}},
        "id": str(uuid.uuid4()), "name": f"استدعاء تجهيز {label}",
        "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2,
        "position": [200, 2140 + delta * 120]})
    fc[f"تشغيل عن بعد تجهيز {label}"] = {"main": [[{"node": f"استدعاء تجهيز {label}", "type": "main", "index": 0}]]}

# -- إشعار نجاح الإنتاج -> بطاقة فيديو --
for x in fn:
    if x["name"] == "إشعار نجاح الإنتاج":
        x["parameters"] = {
            "chatId": CHAT,
            "text": ("=🎥 <b>فيديو جاهز للاعتماد</b>\n{{ $json.title }}\n<code>{{ $json.lesson_code }}</code>\n\n"
                     "المدة: {{ Math.round($json.seconds) }} ثانية · المراجعة: {{ $json.qa_verdict }}\n"
                     "📁 درايف: {{ $json.drive.link }}\n"
                     "{{ ($json.qa_issues && $json.qa_issues.length) ? '\\n⚠️ ملاحظات:\\n' + $json.qa_issues.map(i=>'• '+(i.type||'')+' '+(i.note||i.quote||'')).join('\\n') : '' }}"),
            "replyMarkup": "inlineKeyboard",
            "inlineKeyboard": {"rows": [{"row": {"buttons": [
                {"text": "✅ اعتماد والانتقال للتالي", "additionalFields": {"callback_data": "=vok:{{ $json.lesson_uid }}"}},
                {"text": "🔄 إعادة إنتاج", "additionalFields": {"callback_data": "=vredo:{{ $json.lesson_uid }}"}},
            ]}}]},
            "additionalFields": {"appendAttribution": False, "parse_mode": "HTML"}}
        x["type"] = "n8n-nodes-base.telegram"

save(FACT, fn, fc)
print("factory: script-card + video-card + prepare webhooks + SCRIPT_FINAL fetch updated")

# ================= البوت =================
bn, bc = load(BOT)
for x in bn:
    if x["name"] == "تحليل المدخل":
        js = x["parameters"]["jsCode"]
        if "vok" not in js:
            js = js.replace(
                "  else if (action === 'cedit') type = 'edit_button';",
                "  else if (action === 'cedit') type = 'edit_button';\n"
                "  else if (action === 'vok') type = 'video_ok';\n"
                "  else if (action === 'vredo') type = 'video_redo';")
            x["parameters"]["jsCode"] = js
            print("bot: تحليل المدخل يفهم vok/vredo")
    if x["name"] == "دمج ومطابقة الترتيب":
        js = x["parameters"]["jsCode"]
        if "video_ok" not in js:
            js = js.replace(
                "else if (['approve','reject','edit_button'].includes(cls.type)) {\n  route = in_sequence ? cls.type : 'out_of_order';\n}",
                "else if (['approve','reject','edit_button'].includes(cls.type)) {\n"
                "  route = in_sequence ? cls.type : 'out_of_order';\n}\n"
                "else if (['video_ok','video_redo'].includes(cls.type)) route = cls.type;")
            x["parameters"]["jsCode"] = js
            print("bot: دمج ومطابقة الترتيب يمرّر video_ok/video_redo")
    if x["name"] == "توجيه نهائي":
        p = x["parameters"]
        p["numberOutputs"] = 8
        p["output"] = ("={{ ({approve:0,reject:1,edit_button:2,text_note:3,out_of_order:4,"
                       "ignore:5,video_ok:6,video_redo:7})[$json.route] ?? 5 }}")
        print("bot: switch -> 8 outputs")
    if x["name"] == "تحديد رابط المرحلة التالية":
        js = x["parameters"]["jsCode"]
        js = js.replace(
            "const STAGE_ORDER = ['CONTENT_DESC','CONTENT_FUNC','CONTENT_SUMMARY','SCRIPT_DRAFT','SCRIPT_REFINE','SCRIPT_FINAL','SCI_REVIEW'];",
            "const STAGE_ORDER = ['CONTENT_DESC','CONTENT_FUNC','CONTENT_SUMMARY','SCRIPT_DRAFT','SCRIPT_REFINE','SCRIPT_FINAL'];")
        x["parameters"]["jsCode"] = js
        print("bot: SCRIPT_FINAL هو آخر مرحلة -> MEDIA")

# فرعا الفيديو: يقرآن route وقيمة lesson_uid من 'دمج ومطابقة الترتيب' (output_uid يحمل الرقم)
def bnode(nn):
    if not any(y["name"] == nn["name"] for y in bn):
        bn.append(nn)


bnode({
    "parameters": {"method": "POST", "url": f"{BASE}/prepare-next", "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                   "sendBody": True, "specifyBody": "json",
                   "jsonBody": "={{ JSON.stringify({ lesson_uid: Number($('تحليل المدخل').item.json.output_uid) + 1 }) }}",
                   "options": {}},
    "id": str(uuid.uuid4()), "name": "تشغيل تجهيز الدرس التالي",
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [900, 1400]})
bnode({
    "parameters": {"chatId": CHAT, "text": "=✅ تم اعتماد الفيديو. بدأ تجهيز الدرس التالي — هتوصلك بطاقة السيناريو قريبًا.",
                   "additionalFields": {"appendAttribution": False}},
    "id": str(uuid.uuid4()), "name": "تأكيد: الانتقال للتالي",
    "type": "n8n-nodes-base.telegram", "typeVersion": 1.2, "position": [1120, 1400],
    "webhookId": str(uuid.uuid4()), "credentials": CRED})
bnode({
    "parameters": {"method": "POST", "url": f"{BASE}/prepare-again", "sendHeaders": True,
                   "headerParameters": {"parameters": [{"name": "Content-Type", "value": "application/json"}]},
                   "sendBody": True, "specifyBody": "json",
                   "jsonBody": "={{ JSON.stringify({ lesson_uid: Number($('تحليل المدخل').item.json.output_uid) }) }}",
                   "options": {}},
    "id": str(uuid.uuid4()), "name": "تشغيل إعادة تجهيز الدرس",
    "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [900, 1560]})
bnode({
    "parameters": {"chatId": CHAT, "text": "=🔄 جاري إعادة تجهيز سيناريو نفس الدرس.",
                   "additionalFields": {"appendAttribution": False}},
    "id": str(uuid.uuid4()), "name": "تأكيد: إعادة التجهيز",
    "type": "n8n-nodes-base.telegram", "typeVersion": 1.2, "position": [1120, 1560],
    "webhookId": str(uuid.uuid4()), "credentials": CRED})

sw = bc.get("توجيه نهائي", {}).get("main", [])
while len(sw) < 8:
    sw.append([])
sw[6] = [{"node": "تشغيل تجهيز الدرس التالي", "type": "main", "index": 0}]
sw[7] = [{"node": "تشغيل إعادة تجهيز الدرس", "type": "main", "index": 0}]
bc["توجيه نهائي"] = {"main": sw}
bc["تشغيل تجهيز الدرس التالي"] = {"main": [[{"node": "تأكيد: الانتقال للتالي", "type": "main", "index": 0}]]}
bc["تشغيل إعادة تجهيز الدرس"] = {"main": [[{"node": "تأكيد: إعادة التجهيز", "type": "main", "index": 0}]]}

save(BOT, bn, bc)
db.commit()
print("DONE — pm2 restart n8n && pm2 save")
