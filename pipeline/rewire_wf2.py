# -*- coding: utf-8 -*-
"""تحديث «بناء طلب الإنتاج» ليمرّر مشاهد السكربت من Gemini إلى بوابة الإنتاج،
   وتصحيح تسمية model_used في «تحليل الناتج FINAL»."""
import sqlite3, json, time

WID = "nQFAvcCJ9Hwu26ag"
db = sqlite3.connect("/root/.n8n/database.sqlite")
nodes, conns = db.execute("SELECT nodes, connections FROM workflow_entity WHERE id=?", (WID,)).fetchone()
nodes = json.loads(nodes)

NEW_BUILD = (
    "// يبني طلب بوابة الإنتاج من السكربت النهائي (Gemini) مع fallback لسكربت السيرفر\n"
    "const s = $('تحويل JSON للسكريبت').item.json;\n"
    "const fs = (s && s.final_script) || {};\n"
    "const scenes = Array.isArray(fs.scenes) ? fs.scenes : null;\n"
    "const out = {\n"
    "  video_uid: fs.video_uid || 500128,\n"
    "  lesson_code: fs.lesson_code || 'B01-U01-C01-L01',\n"
    "  title: fs.title || 'رحلة داخل العين البشرية',\n"
    "  sync: true\n"
    "};\n"
    "if (scenes && scenes.length >= 3) { out.scenes = scenes; }\n"
    "return [{ json: out }];\n"
)

done = []
for n in nodes:
    if n["name"] == "بناء طلب الإنتاج":
        n["parameters"]["jsCode"] = NEW_BUILD
        done.append(n["name"])
    if n["name"] == "تحليل الناتج FINAL":
        n["parameters"]["jsCode"] = n["parameters"]["jsCode"].replace(
            "model_used: 'gpt-oss:120b-cloud (Ollama Cloud)'",
            "model_used: 'gemini-3.6-flash'")
        done.append(n["name"])

if not done:
    print("no matching nodes — already updated?")
else:
    db.execute("UPDATE workflow_entity SET nodes=?, updatedAt=? WHERE id=?",
               (json.dumps(nodes, ensure_ascii=False), time.strftime("%Y-%m-%d %H:%M:%S"), WID))
    db.commit()
    print("updated nodes:", done)
