import sqlite3
<div style="margin-bottom: 15px;">
    <a class="button-link" href="{{ url_for('bulk_followups') }}">
        Send All Follow-ups (Today)
    </a>
</div>
conn = sqlite3.connect("database.db")
c = conn.cursor()

columns_to_add = [
    ("status", "TEXT DEFAULT 'New'"),
    ("last_contact", "TEXT"),
    ("next_followup", "TEXT"),
    ("notes", "TEXT")
]

for column_name, column_type in columns_to_add:
    try:
        c.execute(f"ALTER TABLE leads ADD COLUMN {column_name} {column_type}")
        print(f"Added: {column_name}")
    except sqlite3.OperationalError as e:
        print(f"Skipped {column_name}: {e}")

conn.commit()
conn.close()

print("Done.")