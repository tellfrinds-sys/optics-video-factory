# -*- coding: utf-8 -*-
"""rewire_wf9 — أزرار على رسالة «بوابة المراجعة أوقفت التسليم» عشان المستخدم
   يقدر يعدّل السيناريو أو يعيد الإنتاج من تليجرام مباشرة (مش رسالة ميتة)."""
import sqlite3, json, time

DB = "/root/.n8n/database.sqlite"
FACT = "nQFAvcCJ9Hwu26ag"
db = sqlite3.connect(DB)
n, c = db.execute("SELECT nodes,connections FROM workflow_entity WHERE id=?", (FACT,)).fetchone()
nn = json.loads(n)

for x in nn:
    if x["name"] == "إشعار توقف المراجعة":
        p = x["parameters"]
        p["replyMarkup"] = "inlineKeyboard"
        p["inlineKeyboard"] = {"rows": [{"row": {"buttons": [
            {"text": "✏️ تعديل السيناريو", "additionalFields": {"callback_data": "=vedit:{{ $json.lesson_uid }}"}},
            {"text": "🔄 إعادة الإنتاج", "additionalFields": {"callback_data": "=vredo:{{ $json.lesson_uid }}"}},
        ]}}]}
        p.setdefault("additionalFields", {})["appendAttribution"] = False
        print("patched إشعار توقف المراجعة with buttons")

db.execute("UPDATE workflow_entity SET nodes=?,updatedAt=? WHERE id=?",
           (json.dumps(nn, ensure_ascii=False), time.strftime("%Y-%m-%d %H:%M:%S"), FACT))
db.commit()
print("saved")
