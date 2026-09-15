# -*- coding: utf-8 -*-
"""fix_n8n_history_key.py -- الجزء الثاني من الإصلاح: n8n بيشغّل النسخة المنشورة في
workflow_history (حسب activeVersionId) مش الصف الحي في workflow_entity مباشرة -- نفس
النمط المعروف من قبل (publish_wf.py). عدّلنا workflow_entity.nodes فعلاً، لكن نسخة
workflow_history لسه فيها المفتاح القديم، فلازم نصلحها هي كمان عشان التفعيل الفعلي يشتغل.
"""
import shutil
import sqlite3
import time

DB = "/root/.n8n/database.sqlite"
OLD_KEY = "sb_secret_HcJo0ZQSp66D_Rot-3CrhA_NOfGCcha"
NEW_KEY = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlsdmdhaGduYXh4"
           "b294dmNhd3loIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc4NjU0OTg0MiwiZXhwIjoyMTAyMTI1"
           "ODQyfQ.hGAQtzYVu4HyehzGOGhtOifpXD_aiaBwMHvYaLvV_pY")

backup = f"{DB}.bak_pre_history_key_fix_{int(time.time())}"
shutil.copy2(DB, backup)
print("نسخة احتياطية:", backup)

conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT versionId, workflowId, nodes FROM workflow_history WHERE workflowId IN (?,?)",
            ("LMKFvWfPglBS5BEZ", "nQFAvcCJ9Hwu26ag"))
rows = cur.fetchall()
total = 0
for version_id, wf_id, nodes_text in rows:
    count = nodes_text.count(OLD_KEY)
    if count:
        new_text = nodes_text.replace(OLD_KEY, NEW_KEY)
        cur.execute("UPDATE workflow_history SET nodes = ? WHERE versionId = ?", (new_text, version_id))
        print(f"{wf_id} (history {version_id}): استُبدل {count} موضع")
        total += count
    else:
        print(f"{wf_id} (history {version_id}): لا يوجد المفتاح القديم فيه")
conn.commit()
conn.close()
print("تم -- إجمالي المواضع المُصلَحة في workflow_history:", total)
