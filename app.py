import os
import sqlite3
from datetime import datetime, date
from urllib.parse import quote

from flask import Flask, render_template, request, redirect, session, url_for, flash

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "buildnex-secret-key")

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "buildnex123")

ALLOWED_STATUSES = [
    "New",
    "Contacted",
    "Follow-up",
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


def normalize_date_input(value):
    if not value:
        return None

    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    value = str(value).strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return None


def to_html_date(value):
    return normalize_date_input(value) or ""


app.jinja_env.globals.update(to_html_date=to_html_date)


def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def column_exists(conn, table_name, column_name):
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [row["name"] for row in cur.fetchall()]
    return column_name in columns


def add_column_if_missing(conn, table_name, column_name, column_def):
    if not column_exists(conn, table_name, column_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_def}")


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


def clean_phone_number(phone):
    clean_phone = "".join(ch for ch in (phone or "") if ch.isdigit())

    if clean_phone.startswith("0"):
        clean_phone = clean_phone[1:]

    if len(clean_phone) == 10:
        clean_phone = "91" + clean_phone

    return clean_phone


def generate_whatsapp_message(lead):
    name = lead["name"] or "Customer"
    area = lead["top_area"] or "your preferred area"

    budget_text = ""
    if lead["budget_min"] and lead["budget_max"]:
        budget_text = f" in your budget {lead['budget_min']} - {lead['budget_max']}"

    return (
        f"Hi {name}, based on your requirement in {area}, "
        f"we found high-potential options{budget_text}. "
        f"Want me to share top deals or schedule a quick call?"
    )


def generate_followup_message(lead):
    name = lead["name"] or "Customer"
    area = lead["top_area"] or "your preferred area"

    budget_text = ""
    if lead["budget_min"] and lead["budget_max"]:
        budget_text = f" within your budget {lead['budget_min']} - {lead['budget_max']}"

    return (
        f"Hi {name}, just checking in — we still have some strong options available "
        f"in {area}{budget_text}. Shall I share the best ones or connect you with our team?"
    )


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            phone TEXT UNIQUE,
            email TEXT,
            budget_min TEXT,
            budget_max TEXT,
            purpose TEXT,
            top_area TEXT,
            lead_priority TEXT,
            lead_score INTEGER DEFAULT 0,
            lead_score_category TEXT DEFAULT 'COLD',
            builder_segment TEXT,
            paint TEXT,
            green TEXT,
            status TEXT DEFAULT 'New',
            last_contact TEXT,
            next_followup TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    add_column_if_missing(conn, "leads", "status", "TEXT DEFAULT 'New'")
    add_column_if_missing(conn, "leads", "lead_score", "INTEGER DEFAULT 0")
    add_column_if_missing(conn, "leads", "lead_score_category", "TEXT DEFAULT 'COLD'")
    add_column_if_missing(conn, "leads", "last_contact", "TEXT")
    add_column_if_missing(conn, "leads", "next_followup", "TEXT")
    add_column_if_missing(conn, "leads", "notes", "TEXT")
    add_column_if_missing(conn, "leads", "created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")

    conn.commit()
    conn.close()


def fix_existing_followup_dates():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT id, next_followup
        FROM leads
        WHERE next_followup IS NOT NULL
          AND next_followup <> ''
    """)
    rows = cur.fetchall()

    for row in rows:
        old_value = row["next_followup"]
        new_value = normalize_date_input(old_value)

        if new_value and new_value != old_value:
            cur.execute(
                "UPDATE leads SET next_followup = ? WHERE id = ?",
                (new_value, row["id"])
            )

    conn.commit()
    conn.close()


@app.route("/")
def form():
    return render_template("form.html")


@app.route("/submit", methods=["POST"])
def submit():
    data = request.form
    phone = data.get("phone")

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM leads WHERE phone = %s", (phone,))
            existing = cur.fetchone()

            if existing:
                cur.execute("""
                    UPDATE leads
                    SET name = %s,
                        email = %s,
                        budget_min = %s,
                        budget_max = %s,
                        purpose = %s,
                        top_area = %s,
                        lead_priority = %s,
                        builder_segment = %s,
                        paint = %s,
                        green = %s
                    WHERE phone = %s
                """, (
                    data.get("name"),
                    data.get("email"),
                    data.get("budget_min"),
                    data.get("budget_max"),
                    data.get("purpose"),
                    data.get("top_area"),
                    data.get("priority"),
                    data.get("segment"),
                    data.get("paint"),
                    data.get("green"),
                    phone
                ))
            else:
                cur.execute("""
                    INSERT INTO leads
                    (name, phone, email, budget_min, budget_max, purpose, top_area, lead_priority, builder_segment, paint, green)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    data.get("name"),
                    phone,
                    data.get("email"),
                    data.get("budget_min"),
                    data.get("budget_max"),
                    data.get("purpose"),
                    data.get("top_area"),
                    data.get("priority"),
                    data.get("segment"),
                    data.get("paint"),
                    data.get("green")
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
    next_followup = normalize_date_input(request.form.get("next_followup"))
    new_note = request.form.get("notes", "").strip()
    last_contact = datetime.now().strftime("%Y-%m-%d")

    if new_status not in ALLOWED_STATUSES:
        flash("Invalid status selected.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = cur.fetchone()

    if not lead:
        conn.close()
        flash("Lead not found.", "error")
        return redirect(url_for("dashboard"))

    existing_notes = (lead["notes"] or "").strip()

    if new_note:
        timestamped_note = f"[{last_contact}] {new_note}"
        combined_notes = f"{existing_notes}\n{timestamped_note}".strip() if existing_notes else timestamped_note
    else:
        combined_notes = existing_notes if existing_notes else None

    cur.execute("""
        UPDATE leads
        SET status = ?, last_contact = ?, next_followup = ?, notes = ?
        WHERE id = ?
    """, (
        new_status,
        last_contact,
        next_followup,
        combined_notes,
        lead_id
    ))

    conn.commit()
    conn.close()

    flash("Lead updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/admin/leads/<int:lead_id>/whatsapp")
def whatsapp_redirect(lead_id):
    if not session.get("admin_logged_in"):
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = cur.fetchone()

    if not lead:
        conn.close()
        flash("Lead not found.", "error")
        return redirect(url_for("dashboard"))

    phone = (lead["phone"] or "").strip()
    message = generate_whatsapp_message(lead)
    existing_notes = lead["notes"]
    today = datetime.now().strftime("%Y-%m-%d")

    new_note = f"WhatsApp follow-up sent to {phone}: {message}"
    combined_notes = f"{existing_notes}\n{new_note}" if existing_notes else new_note

    cur.execute("""
        UPDATE leads
        SET status = ?, last_contact = ?, notes = ?
        WHERE id = ?
    """, (
        "Contacted",
        today,
        combined_notes,
        lead_id
    ))

    conn.commit()
    conn.close()

    clean_phone = clean_phone_number(phone)
    wa_url = f"https://wa.me/{clean_phone}?text={quote(message)}"
    return redirect(wa_url)


@app.route("/admin/leads/<int:lead_id>/followup")
def followup_redirect(lead_id):
    if not session.get("admin_logged_in"):
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM leads WHERE id = ?", (lead_id,))
    lead = cur.fetchone()

    if not lead:
        conn.close()
        flash("Lead not found.", "error")
        return redirect(url_for("dashboard"))

    phone = (lead["phone"] or "").strip()
    message = generate_followup_message(lead)
    existing_notes = lead["notes"]
    today = datetime.now().strftime("%Y-%m-%d")

    new_note = f"Manual follow-up sent to {phone}: {message}"
    combined_notes = f"{existing_notes}\n{new_note}" if existing_notes else new_note

    cur.execute("""
        UPDATE leads
        SET status = ?, last_contact = ?, notes = ?
        WHERE id = ?
    """, (
        "Follow-up",
        today,
        combined_notes,
        lead_id
    ))

    conn.commit()
    conn.close()

    clean_phone = clean_phone_number(phone)
    wa_url = f"https://wa.me/{clean_phone}?text={quote(message)}"
    return redirect(wa_url)


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
            id, name, phone, email, budget_min, budget_max, purpose, top_area,
            lead_priority, lead_score, lead_score_category, builder_segment,
            paint, green, status, last_contact, next_followup, notes, created_at
        FROM leads
        WHERE 1=1
    """
    params = []

    if purpose:
        query += " AND purpose = ?"
        params.append(purpose)

    if priority:
        query += " AND lead_priority = ?"
        params.append(priority)

    if segment:
        query += " AND builder_segment = ?"
        params.append(segment)

    if status:
        query += " AND status = ?"
        params.append(status)

    if score_category:
        query += " AND lead_score_category = ?"
        params.append(score_category)

    query += " ORDER BY id DESC"

    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, params)
    leads = cur.fetchall()
    conn.close()

    hot_count = sum(1 for l in leads if l["lead_score_category"] == "HOT")
    warm_count = sum(1 for l in leads if l["lead_score_category"] == "WARM")
    cold_count = sum(1 for l in leads if l["lead_score_category"] == "COLD")

    today = datetime.now().strftime("%Y-%m-%d")
    today_followups_count = sum(1 for l in leads if l["next_followup"] == today)

    return render_template(
        "dashboard.html",
        leads=leads,
        purpose_filter=purpose,
        priority_filter=priority,
        segment_filter=segment,
        status_filter=status,
        score_category_filter=score_category,
        allowed_statuses=ALLOWED_STATUSES,
        allowed_score_categories=ALLOWED_SCORE_CATEGORIES,
        hot_count=hot_count,
        warm_count=warm_count,
        cold_count=cold_count,
        today_followups_count=today_followups_count
    )


@app.route("/admin/today-followups")
def today_followups():
    if not session.get("admin_logged_in"):
        return redirect("/login")

    today = datetime.now().strftime("%Y-%m-%d")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT *
        FROM leads
        WHERE next_followup = ?
        ORDER BY id DESC
    """, (today,))
    leads = cur.fetchall()
    conn.close()

    return render_template("today_followups.html", leads=leads)


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
                    builder_segment TEXT,
                    paint TEXT,
                    green TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cur.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'unique_phone_constraint'
                    ) THEN
                        ALTER TABLE leads
                        ADD CONSTRAINT unique_phone_constraint UNIQUE (phone);
                    END IF;
                END
                $$;
            """)
        conn.commit()