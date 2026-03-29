from flask import Flask, render_template, request, redirect, session, url_for, flash
import os
import psycopg
from psycopg.rows import dict_row

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "buildnex-secret-key")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "buildnex123")
DATABASE_URL = os.environ.get("DATABASE_URL")

ALLOWED_STATUSES = [
    "New",
    "Contacted",
    "Qualified",
    "Site Visit Scheduled",
    "Closed",
    "Lost",
]

ALLOWED_SCORE_CATEGORIES = [
    "HOT",
    "WARM",
    "COLD",
]


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL)


def calculate_lead_score(budget_min, budget_max, purpose, lead_priority, paint, green):
    score = 0

    try:
        min_budget = int(str(budget_min).strip()) if budget_min else 0
    except (ValueError, TypeError):
        min_budget = 0

    try:
        max_budget = int(str(budget_max).strip()) if budget_max else 0
    except (ValueError, TypeError):
        max_budget = 0

    purpose = (purpose or "").strip().lower()
    lead_priority = (lead_priority or "").strip().lower()
    paint = (paint or "").strip().lower()
    green = (green or "").strip().lower()

    # Budget scoring
    if max_budget >= 10000:
        score += 3
    elif max_budget >= 7000:
        score += 2
    else:
        score += 1

    # Purpose scoring
    if purpose in ["self", "self-use", "self use"]:
        score += 3
    elif purpose == "investment":
        score += 2
    else:
        score += 1

    # Priority scoring
    if lead_priority == "high":
        score += 3
    elif lead_priority == "medium":
        score += 2
    else:
        score += 1

    # Paint interest scoring
    if paint == "high":
        score += 2
    elif paint == "medium":
        score += 1

    # Green interest scoring
    if green == "high":
        score += 2
    elif green == "medium":
        score += 1

    # Final category
    if score >= 10:
        category = "HOT"
    elif score >= 7:
        category = "WARM"
    else:
        category = "COLD"

    return score, category


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    id SERIAL PRIMARY KEY,
                    name TEXT,
                    phone TEXT,
                    email TEXT,
                    budget_min TEXT,
                    budget_max TEXT,
                    purpose TEXT,
                    top_area TEXT,
                    lead_priority TEXT,
                    lead_score INTEGER DEFAULT 0,
                    lead_score_category VARCHAR(20) DEFAULT 'COLD',
                    builder_segment TEXT,
                    paint TEXT,
                    green TEXT,
                    status TEXT DEFAULT 'New',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Safe upgrades for existing tables
            cur.execute("""
                ALTER TABLE leads
                ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'New'
            """)

            cur.execute("""
                ALTER TABLE leads
                ADD COLUMN IF NOT EXISTS lead_score INTEGER DEFAULT 0
            """)

            cur.execute("""
                ALTER TABLE leads
                ADD COLUMN IF NOT EXISTS lead_score_category VARCHAR(20) DEFAULT 'COLD'
            """)

        conn.commit()


@app.route("/")
def form():
    return render_template("form.html")


@app.route("/submit", methods=["POST"])
def submit():
    data = request.form

    name = data.get("name")
    phone = data.get("phone")
    email = data.get("email")
    budget_min = data.get("budget_min")
    budget_max = data.get("budget_max")
    purpose = data.get("purpose")
    top_area = data.get("top_area")
    lead_priority = data.get("priority")
    builder_segment = data.get("segment")
    paint = data.get("paint")
    green = data.get("green")

    lead_score, lead_score_category = calculate_lead_score(
        budget_min,
        budget_max,
        purpose,
        lead_priority,
        paint,
        green
    )

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO leads
                (
                    name,
                    phone,
                    email,
                    budget_min,
                    budget_max,
                    purpose,
                    top_area,
                    lead_priority,
                    lead_score,
                    lead_score_category,
                    builder_segment,
                    paint,
                    green,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                name,
                phone,
                email,
                budget_min,
                budget_max,
                purpose,
                top_area,
                lead_priority,
                lead_score,
                lead_score_category,
                builder_segment,
                paint,
                green,
                "New"
            ))
        conn.commit()

    return redirect("/admin/dashboard")


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        if (
            request.form.get("username") == ADMIN_USERNAME
            and request.form.get("password") == ADMIN_PASSWORD
        ):
            session["admin_logged_in"] = True
            return redirect("/admin/dashboard")
        else:
            error = "Invalid credentials"

    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect("/login")


@app.route("/admin/leads/<int:lead_id>/status", methods=["POST"])
def update_lead_status(lead_id):
    if not session.get("admin_logged_in"):
        return redirect("/login")

    new_status = request.form.get("status", "").strip()

    if new_status not in ALLOWED_STATUSES:
        flash("Invalid status selected.", "error")
        return redirect(url_for("dashboard"))

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE leads SET status = %s WHERE id = %s",
                (new_status, lead_id)
            )
        conn.commit()

    flash("Lead status updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/dashboard")
def dashboard():
    if not session.get("admin_logged_in"):
        return redirect("/login")

    purpose = request.args.get("purpose")
    priority = request.args.get("priority")
    segment = request.args.get("segment")
    status = request.args.get("status")
    score_category = request.args.get("score_category")

    query = """
        SELECT
            id,
            name,
            phone,
            email,
            budget_min,
            budget_max,
            purpose,
            top_area,
            lead_priority,
            lead_score,
            lead_score_category,
            builder_segment,
            paint,
            green,
            status,
            created_at
        FROM leads
        WHERE 1=1
    """
    params = []

    if purpose:
        query += " AND purpose = %s"
        params.append(purpose)

    if priority:
        query += " AND lead_priority = %s"
        params.append(priority)

    if segment:
        query += " AND builder_segment = %s"
        params.append(segment)

    if status:
        query += " AND status = %s"
        params.append(status)

    if score_category:
        query += " AND lead_score_category = %s"
        params.append(score_category)

    query += " ORDER BY id DESC"

    with get_db() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query, params)
            leads = cur.fetchall()

    return render_template(
        "dashboard.html",
        leads=leads,
        purpose_filter=purpose,
        priority_filter=priority,
        segment_filter=segment,
        status_filter=status,
        score_category_filter=score_category,
        allowed_statuses=ALLOWED_STATUSES,
        allowed_score_categories=ALLOWED_SCORE_CATEGORIES
    )


init_db()

if __name__ == "__main__":
    app.run(debug=True)
@app.route("/admin/leads/<int:lead_id>/send-whatsapp", methods=["POST"])
def send_whatsapp(lead_id):
    import requests
    import os
    from datetime import datetime

    access_token = os.getenv("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID")

    if not access_token or not phone_number_id:
        return {"error": "WhatsApp config missing"}, 500

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT name, phone, lead_score_category
                    FROM leads
                    WHERE id = %s
                """, (lead_id,))
                lead = cur.fetchone()

        if not lead:
            return {"error": "Lead not found"}, 404

        name, phone, category = lead

        # Score-based message
        if category == "HOT":
            message = f"Hi {name}, based on your requirement we have high-potential options ready. Want me to share top deals or schedule a call?"
        elif category == "WARM":
            message = f"Hi {name}, I can share matching options based on your budget and area. Want me to send details?"
        else:
            message = f"Hi {name}, whenever you're ready I can help you with suitable options. Just reply here."

        url = f"https://graph.facebook.com/v18.0/{phone_number_id}/messages"

        payload = {
            "messaging_product": "whatsapp",
            "to": f"91{phone}",
            "type": "text",
            "text": {"body": message}
        }

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        response = requests.post(url, json=payload, headers=headers)

        return {"status": "sent", "response": response.json()}

    except Exception as e:
        return {"error": str(e)}, 500
@app.route("/admin/leads/<int:lead_id>/send-whatsapp", methods=["POST"])
def send_whatsapp(lead_id):
    from datetime import datetime

    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                # Get lead
                cur.execute("""
                    SELECT name, phone, lead_score_category
                    FROM leads
                    WHERE id = %s
                """, (lead_id,))
                lead = cur.fetchone()

                if not lead:
                    return {"error": "Lead not found"}, 404

                name, phone, category = lead

                # Simulated message logic
                if category == "HOT":
                    message = f"HOT LEAD → {name}: High intent. Send priority options."
                    stage = "initial_hot"
                elif category == "WARM":
                    message = f"WARM LEAD → {name}: Send curated options."
                    stage = "initial_warm"
                else:
                    message = f"COLD LEAD → {name}: Soft follow-up."
                    stage = "initial_cold"

                # Update lead follow-up tracking
                cur.execute("""
                    UPDATE leads
                    SET last_whatsapp_sent_at = %s,
                        followup_stage = %s,
                        followup_status = 'sent'
                    WHERE id = %s
                """, (datetime.now(), stage, lead_id))

                conn.commit()

        print(f"[SIMULATED WHATSAPP] {message}")

        return {"status": "simulated_sent", "message": message}

    except Exception as e:
        return {"error": str(e)}, 500