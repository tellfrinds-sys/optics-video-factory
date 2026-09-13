# ينشر النسخة الحالية من workflow_entity إلى workflow_history ويضبط activeVersionId
import sqlite3, uuid, time

db = sqlite3.connect("/root/.n8n/database.sqlite")
db.execute("PRAGMA busy_timeout=8000")
for wid in ("nQFAvcCJ9Hwu26ag", "LMKFvWfPglBS5BEZ"):
    row = db.execute("SELECT nodes, connections, name FROM workflow_entity WHERE id=?", (wid,)).fetchone()
    nodes, conns, name = row
    nv = str(uuid.uuid4())
    now = time.strftime("%Y-%m-%d %H:%M:%S.000")
    db.execute(
        "INSERT INTO workflow_history (versionId, workflowId, authors, createdAt, updatedAt, nodes, connections, name, autosaved) "
        "VALUES (?,?,?,?,?,?,?,?,0)",
        (nv, wid, "system:rewire", now, now, nodes, conns, name))
    db.execute("UPDATE workflow_entity SET versionId=?, activeVersionId=?, versionCounter=versionCounter+1, updatedAt=? WHERE id=?",
               (nv, nv, now, wid))
    print(wid, "published ->", nv)
db.commit()
print("OK")
