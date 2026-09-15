# -*- coding: utf-8 -*-
"""fix_n8n_supabase_key.py -- يستبدل مفتاح Supabase القديم الملغى (sb_secret_...) بالمفتاح
الشغّال الحالي داخل عُقَد n8n المباشرة (نصوص HTTP Request بها الهيدر مكتوب يدويًا، مش
credential منفصل). هذا هو سبب فشل كل بطاقات اعتماد تليجرام منذ 2026-09-14 23:32 (خطأ
"Unregistered API key" / 401 في العقدة "معرفة المرحلة الحالية المنتظرة" وغيرها).

الاستخدام على السيرفر:
    systemctl stop n8n   # أو: pm2 stop n8n
    python3 fix_n8n_supabase_key.py
    pm2 restart n8n

يعمل نسخة احتياطية تلقائية من قاعدة بيانات n8n قبل أي تعديل.
"""
import shutil
import sqlite3
import time

DB = "/root/.n8n/database.sqlite"
OLD_KEY = "sb_secret_HcJo0ZQSp66D_Rot-3CrhA_NOfGCcha"
NEW_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlsdmdhaGduYXh4"
           "b294dmNhd3loIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NjU0OTg0MiwiZXhwIjoyMTAyMTI1"
           "ODQyfQ.hGAQtzYVu4HyehzGOGhtOifpXD_aiaBwMHvYaLvV_pY")

backup = f"{DB}.bak_pre_supabase_key_fix_{int(time.time())}"
shutil.copy2(DB, backup)
print("نسخة احتياطية:", backup)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id, nodes FROM workflow_entity WHERE id IN (?,?)",
            ("LMKFvWfPglBS5BEZ", "nQFAvcCJ9Hwu26ag"))
rows = cur.fetchall()
total = 0
for wf_id, nodes_text in rows:
    count = nodes_text.count(OLD_KEY)
    if count:
        new_text = nodes_text.replace(OLD_KEY, NEW_KEY)
        cur.execute("UPDATE workflow_entity SET nodes = ? WHERE id = ?", (new_text, wf_id))
        print(f"{wf_id}: استُبدل {count} موضع")
        total += count
    else:
        print(f"{wf_id}: لا يوجد المفتاح القديم فيه")
conn.commit()
conn.close()
print("تم -- إجمالي المواضع المُصلَحة:", total)
print("لازم تعيد تشغيل n8n دلوقتي عشان التعديل يفعل فعليًا: pm2 restart n8n")
