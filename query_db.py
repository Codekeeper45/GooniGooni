import sqlite3
import json
import os

db_path = "/results/gallery.db"
if not os.path.exists(db_path):
    print(json.dumps({"error": f"DB not found at {db_path}"}))
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
try:
    rows = conn.execute("SELECT id, label, workspace, status, last_used FROM modal_accounts").fetchall()
    print(json.dumps([dict(r) for r in rows]))
except Exception as e:
    print(json.dumps({"error": str(e)}))
finally:
    conn.close()
