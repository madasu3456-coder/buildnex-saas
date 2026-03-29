import os
import psycopg2

database_url = os.environ.get("DATABASE_URL")

if not database_url:
    raise ValueError("DATABASE_URL not found")

conn = psycopg2.connect(database_url)
cur = conn.cursor()

try:
    cur.execute("""
        ALTER TABLE leads
        ADD COLUMN IF NOT EXISTS lead_score INTEGER DEFAULT 0;
    """)

    cur.execute("""
        ALTER TABLE leads
        ADD COLUMN IF NOT EXISTS lead_score_category VARCHAR(20) DEFAULT 'COLD';
    """)

    conn.commit()
    print("Lead scoring columns added successfully.")
except Exception as e:
    conn.rollback()
    print("Error:", e)
finally:
    cur.close()
    conn.close()