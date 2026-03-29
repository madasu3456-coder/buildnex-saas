from flask import Flask, render_template, request, redirect, session
import sqlite3

app = Flask(__name__)
app.secret_key = "buildnex-secret-key"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "buildnex123"

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        green TEXT
    )
    """)
    conn.commit()
    conn.close()

# Run table creation on import so it also works under Gunicorn on Render
init_db()

@app.route("/")
def form():
    return render_template("form.html")

@app.route("/submit", methods=["POST"])
def submit():
    data = request.form

    conn = get_db()
    conn.execute("""
        INSERT INTO leads 
        (name, phone, email, budget_min, budget_max, purpose, top_area, lead_priority, builder_segment, paint, green)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        data.get("green")
    ))
    conn.commit()
    conn.close()

    return redirect("/admin/dashboard")

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        if request.form.get("username") == ADMIN_USERNAME and request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect("/admin/dashboard")
        else:
            error = "Invalid credentials"

    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.pop("admin_logged_in", None)
    return redirect("/login")

@app.route("/admin/dashboard")
def dashboard():
    if not session.get("admin_logged_in"):
        return redirect("/login")

    conn = get_db()

    purpose = request.args.get("purpose")
    priority = request.args.get("priority")
    segment = request.args.get("segment")

    query = "SELECT * FROM leads WHERE 1=1"
    params = []

    if purpose:
        query += " AND purpose=?"
        params.append(purpose)

    if priority:
        query += " AND lead_priority=?"
        params.append(priority)

    if segment:
        query += " AND builder_segment=?"
        params.append(segment)

    leads = conn.execute(query, params).fetchall()
    conn.close()

    return render_template(
        "dashboard.html",
        leads=leads,
        purpose_filter=purpose,
        priority_filter=priority,
        segment_filter=segment
    )

if __name__ == "__main__":
    app.run(debug=True)