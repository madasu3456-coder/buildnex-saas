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


def get_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(DATABASE_URL)


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
                    status TEXT DEFAULT 'New',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Safe upgrade for existing tables that do not yet have status column
            cur.execute("""
                ALTER TABLE leads
                ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'New'
            """)

        conn.commit()


@app.route("/")
def form():
    return render_template("form.html")


@app.route("/submit", methods=["POST"])
def submit():
    data = request.form

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
                    builder_segment,
                    paint,
                    green,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                data.get("name"),
                data.get("phone"),
                data.get("email"),
                data.get("budget_min"),
                data.get("budget_max"),
                data.get("purpose"),
                data.get("top_area"),
                data.get("priority"),
                data.get("segment"),
                data.get("paint"),
                data.get("green"),
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
        allowed_statuses=ALLOWED_STATUSES
    )


init_db()

if __name__ == "__main__":
    app.run(debug=True)