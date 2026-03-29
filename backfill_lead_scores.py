import os
import psycopg2


def calculate_lead_score(budget_min, budget_max, purpose, lead_priority, paint, green):
    score = 0

    try:
        max_budget = int(str(budget_max).strip()) if budget_max else 0
    except (ValueError, TypeError):
        max_budget = 0

    purpose = (purpose or "").strip().lower()
    lead_priority = (lead_priority or "").strip().lower()
    paint = (paint or "").strip().lower()
    green = (green or "").strip().lower()

    if max_budget >= 10000:
        score += 3
    elif max_budget >= 7000:
        score += 2
    else:
        score += 1

    if purpose in ["self", "self-use", "self use"]:
        score += 3
    elif purpose == "investment":
        score += 2
    else:
        score += 1

    if lead_priority == "high":
        score += 3
    elif lead_priority == "medium":
        score += 2
    else:
        score += 1

    if paint == "high":
        score += 2
    elif paint == "medium":
        score += 1

    if green == "high":
        score += 2
    elif green == "medium":
        score += 1

    if score >= 10:
        category = "HOT"
    elif score >= 7:
        category = "WARM"
    else:
        category = "COLD"

    return score, category


database_url = os.environ.get("DATABASE_URL")

if not database_url:
    raise ValueError("DATABASE_URL not found")

conn = psycopg2.connect(database_url)
cur = conn.cursor()

try:
    cur.execute("""
        SELECT id, budget_min, budget_max, purpose, lead_priority, paint, green
        FROM leads
    """)
    leads = cur.fetchall()

    updated_count = 0

    for lead in leads:
        lead_id, budget_min, budget_max, purpose, lead_priority, paint, green = lead
        score, category = calculate_lead_score(
            budget_min, budget_max, purpose, lead_priority, paint, green
        )

        cur.execute("""
            UPDATE leads
            SET lead_score = %s,
                lead_score_category = %s
            WHERE id = %s
        """, (score, category, lead_id))

        updated_count += 1

    conn.commit()
    print(f"Successfully backfilled {updated_count} leads.")

except Exception as e:
    conn.rollback()
    print("Error:", e)

finally:
    cur.close()
    conn.close()