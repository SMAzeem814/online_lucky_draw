
import os
import random
import logging
import smtplib

from datetime import date, datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import Flask, render_template, request, redirect, url_for, session, flash

# local DB helper (your file)
from db_config import get_db_connection

# password helpers (Werkzeug is available with Flask)
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
load_dotenv()



# Flask app
app = Flask(__name__)
# Use an environment variable for secret in real deployments.
app.secret_key = os.getenv("FLASK_SECRET_KEY", "change-this-secret-in-production")

# Logging
logging.basicConfig(level=logging.INFO)

# ---------------- SMTP / Email configuration ----------------
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))

# Sender email address (keep as your address or env variable)
SENDER_EMAIL = os.getenv("SENDER_EMAIL", "syedmazeem814@gmail.com")

SENDER_PASSWORD = os.getenv("EMAIL_PASSWORD")



DISPLAY_FROM_EMAIL = SENDER_EMAIL

# ---------------- Jinja helper ----------------
@app.context_processor
def inject_now():
    # provide datetime.now in templates (for reports)
    return {"now": datetime.now}

# ---------------- Helpers ----------------
def safe_cursor(conn):
    """
    Return a cursor that yields dictionaries for rows.
    Works with mysql-connector-python and PyMySQL style connector wrappers.
    """
    try:
        return conn.cursor(dictionary=True)
    except TypeError:
        # fallback for connectors that accept cursor_class
        return conn.cursor(cursor_class=getattr(conn, "cursor_class", None))

def send_winner_email(user_email: str, user_name: str, draw_title: str, draw_date):
    """
    Send congratulation email using SMTP.
    If EMAIL_PASSWORD is not set, function logs and returns without raising.
    """
    if not SENDER_PASSWORD:
        logging.warning("EMAIL_PASSWORD not set — skipping sending winner email to %s", user_email)
        return

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🎉 Congratulations! You Won: {draw_title}"
        msg["From"] = DISPLAY_FROM_EMAIL
        msg["To"] = user_email

        html_content = f"""
        <html>
        <body>
            <h2>🎉 Congratulations, {user_name}!</h2>
            <p>You have been selected as the <b>winner</b> of:</p>
            <p><b>{draw_title}</b></p>
            <p>Date: {draw_date}</p>
            <hr>
            <p>Thank you for participating.</p>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_content, "html"))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=10)
        server.ehlo()
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, user_email, msg.as_string())
        server.quit()

        logging.info("Winner email sent to %s", user_email)

    except Exception:
        logging.exception("Failed to send winner email")

# ---------------- Routes ----------------

@app.route("/")
def home():
    conn = get_db_connection()
    cur = safe_cursor(conn)
    try:
        cur.execute("""
            SELECT d.*,
                (SELECT COUNT(*) FROM participants p WHERE p.draw_id = d.id) AS participants_count,
                (SELECT COUNT(*) FROM winners w WHERE w.draw_id = d.id) AS winner_selected,
                (d.draw_date < CURDATE()) AS expired
            FROM draws d
            ORDER BY d.draw_date DESC
        """)
        draws = cur.fetchall()
    finally:
        conn.close()

    return render_template("index.html", draws=draws, current_date=date.today())
#-------------register-----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        hashed = generate_password_hash(password)

        conn = get_db_connection()
        cur = safe_cursor(conn)
        try:
            cur.execute(
                "INSERT INTO users (username, email, password, role) VALUES (%s,%s,%s,%s)",
                (username, email, hashed, "user")
            )
            conn.commit()
            flash("Registration successful. Please log in.", "success")
            return redirect(url_for("login"))
        except Exception as e:
            # IntegrityError on duplicate email will be caught here as well
            logging.exception("Register error")
            if hasattr(e, "errno"):  # optional finer handling
                flash("Email already registered.", "warning")
            else:
                flash("Unable to register.", "danger")
        finally:
            conn.close()

    return render_template("register.html")
#-------------login-------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        conn = get_db_connection()
        cur = safe_cursor(conn)
        try:
            cur.execute("SELECT * FROM users WHERE email=%s", (email,))
            user = cur.fetchone()
        finally:
            conn.close()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["user_email"] = user["email"]
            session["is_admin"] = (str(user.get("role", "")).lower() == "admin")
            flash("Logged in 🎉", "success")
            return redirect(url_for("dashboard"))

        flash("Invalid email or password", "danger")

    return render_template("login.html")
#-------------dashboard-------------------
@app.route("/dashboard")
def dashboard():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    name = session["username"]
    is_admin = session["is_admin"]

    conn = get_db_connection()
    cur = safe_cursor(conn)
    try:
        cur.execute("SELECT COUNT(*) AS total FROM participants WHERE user_id=%s", (user_id,))
        total_joined = cur.fetchone()["total"]

        cur.execute("""
            SELECT d.*,
                (SELECT COUNT(*) FROM participants p WHERE p.draw_id = d.id) AS participants_count,
                (SELECT COUNT(*) FROM winners w WHERE w.draw_id = d.id) AS winner_selected,
                (SELECT COUNT(*) FROM participants p WHERE p.draw_id = d.id AND p.user_id=%s) AS already_joined
            FROM draws d
            WHERE d.draw_date >= CURDATE()
              AND d.id NOT IN (SELECT draw_id FROM winners)
            ORDER BY d.draw_date ASC
        """, (user_id,))
        draws = cur.fetchall()
    finally:
        conn.close()

    return render_template("dashboard.html",
                           name=name,
                           total_joined=total_joined,
                           draws=draws,
                           is_admin=is_admin)
#-----------------draw-------------------------
@app.route("/draws")
def list_draws():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = safe_cursor(conn)
    try:
        cur.execute("SELECT * FROM draws ORDER BY draw_date DESC")
        draws = cur.fetchall()
    finally:
        conn.close()
    return render_template("draws.html", draws=draws)
#---------------add-draw---------------------------
@app.route("/add_draw", methods=["GET", "POST"])
def add_draw():
    if not session.get("is_admin"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        title = request.form["title"]
        description = request.form["description"]
        draw_date = request.form["draw_date"]

        conn = get_db_connection()
        cur = safe_cursor(conn)
        try:
            cur.execute("INSERT INTO draws (title, description, draw_date) VALUES (%s,%s,%s)",
                        (title, description, draw_date))
            conn.commit()
            flash("Draw created!", "success")
            return redirect(url_for("dashboard"))
        except Exception:
            logging.exception("Failed to create draw")
            flash("Unable to create draw", "danger")
        finally:
            conn.close()

    return render_template("add_draw.html")
#---------------adit_draw-----------------------
@app.route("/edit_draw/<int:draw_id>", methods=["GET", "POST"])
def edit_draw(draw_id):
    if not session.get("is_admin"):
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = safe_cursor(conn)
    try:
        cur.execute("SELECT * FROM draws WHERE id=%s", (draw_id,))
        draw = cur.fetchone()

        if request.method == "POST":
            title = request.form["title"]
            description = request.form["description"]
            draw_date = request.form["draw_date"]

            cur.execute("""
                UPDATE draws
                SET title=%s, description=%s, draw_date=%s
                WHERE id=%s
            """, (title, description, draw_date, draw_id))
            conn.commit()
            flash("Draw updated!", "success")
            return redirect(url_for("dashboard"))
    finally:
        conn.close()

    return render_template("edit_draw.html", draw=draw)
#-----------------delete_draw------------------
@app.route("/delete_draw/<int:draw_id>", methods=["POST"])
def delete_draw(draw_id):
    if not session.get("is_admin"):
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = safe_cursor(conn)
    try:
        cur.execute("DELETE FROM participants WHERE draw_id=%s", (draw_id,))
        cur.execute("DELETE FROM winners WHERE draw_id=%s", (draw_id,))
        cur.execute("DELETE FROM draws WHERE id=%s", (draw_id,))
        conn.commit()
        flash("Draw deleted!", "info")
    except Exception:
        logging.exception("Failed to delete draw")
        flash("Unable to delete draw", "danger")
    finally:
        conn.close()

    return redirect(url_for("dashboard"))
#==============join-draw---------------------
@app.route("/join_draw/<int:draw_id>", methods=["GET", "POST"])
def join_draw(draw_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    conn = get_db_connection()
    cur = safe_cursor(conn)

    try:
        cur.execute("SELECT * FROM participants WHERE draw_id=%s AND user_id=%s",
                    (draw_id, user_id))
        participant = cur.fetchone()

        if request.method == "POST":
            name = request.form["name"]
            email = request.form["email"].lower()
            phone = request.form["phone"]
            payment_method = request.form["payment_method"]
            bank_name = request.form.get("bank_name")
            amount = request.form.get("amount")

            if participant:
                cur.execute("""
                    UPDATE participants
                    SET name=%s, email=%s, phone=%s, payment_method=%s,
                        bank_name=%s, amount=%s, joined_at=NOW()
                    WHERE draw_id=%s AND user_id=%s
                """, (name, email, phone, payment_method, bank_name, amount, draw_id, user_id))
            else:
                cur.execute("""
                    INSERT INTO participants
                    (user_id, draw_id, name, email, phone, payment_method,
                     bank_name, amount, joined_at)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                """, (user_id, draw_id, name, email, phone, payment_method, bank_name, amount))

            conn.commit()
            flash("Joined successfully!", "success")
            return redirect(url_for("dashboard"))

        cur.execute("SELECT username, email FROM users WHERE id=%s", (user_id,))
        user_info = cur.fetchone()
    finally:
        conn.close()

    return render_template("join_draw.html",
                           draw_id=draw_id,
                           participant=participant,
                           user_info=user_info)
#================manged profile==============
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db_connection()
    cur = safe_cursor(conn)

    try:
        if request.method == "POST":
            username = request.form["username"].strip()
            email = request.form["email"].strip().lower()
            phone = request.form.get("phone")

            cur.execute("""
                UPDATE users
                SET username=%s, email=%s, phone=%s
                WHERE id=%s
            """, (username, email, phone, user_id))

            conn.commit()
            flash("Profile updated successfully ✅", "success")

            # update session name/email if changed
            session["username"] = username
            session["user_email"] = email

            return redirect(url_for("profile"))

        # GET request → load user data
        cur.execute("SELECT username, email, phone FROM users WHERE id=%s", (user_id,))
        user = cur.fetchone()

    finally:
        conn.close()
    return render_template("profile.html", user=user)


#==============past-draw============================
@app.route("/past_draws")
def past_draws():
    if not session.get("is_admin"):
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = safe_cursor(conn)

    cur.execute("""
        SELECT d.*,
            (SELECT COUNT(*) FROM participants WHERE draw_id = d.id) AS participants_count,
            (SELECT COUNT(*) FROM winners WHERE draw_id = d.id) AS winner_selected
        FROM draws d
        WHERE d.draw_date < CURDATE()
           OR d.id IN (SELECT draw_id FROM winners)
        ORDER BY d.draw_date DESC
    """)
    past_draws = cur.fetchall()
    conn.close()

    return render_template("past_draws.html", draws=past_draws)

#================participants==================

@app.route("/participants/<int:draw_id>")
def participants(draw_id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    is_admin = session["is_admin"]

    conn = get_db_connection()
    cur = safe_cursor(conn)
    try:
        cur.execute("SELECT * FROM draws WHERE id=%s", (draw_id,))
        draw = cur.fetchone()

        cur.execute("""
            SELECT p.*, u.username, u.email
            FROM participants p
            JOIN users u ON p.user_id = u.id
            WHERE p.draw_id=%s
            ORDER BY p.joined_at DESC
        """, (draw_id,))
        participants_list = cur.fetchall()

        cur.execute("""
            SELECT w.selected_at, u.username AS name, u.email
            FROM winners w
            JOIN users u ON w.user_id = u.id
            WHERE w.draw_id=%s
        """, (draw_id,))
        winner_data = cur.fetchone()
    finally:
        conn.close()

    return render_template("participants.html",
                           draw=draw,
                           participants=participants_list,
                           draw_id=draw_id,
                           is_admin=is_admin,
                           winner=winner_data)
#================winners===================
@app.route("/winners")
def winners():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    cur = safe_cursor(conn)
    try:
        cur.execute("""
            SELECT w.id, w.selected_at, d.id AS draw_id, d.title, d.draw_date,
                   u.username, u.email
            FROM winners w
            JOIN draws d ON w.draw_id = d.id
            JOIN users u ON w.user_id = u.id
            ORDER BY w.selected_at DESC
        """)
        winners_list = cur.fetchall()
    finally:
        conn.close()

    return render_template("winners.html", winners=winners_list)
#--------------select-winner-----------------------
@app.route("/select_winner/<int:draw_id>", methods=["POST"])
def select_winner(draw_id):
    if not session.get("is_admin"):
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = safe_cursor(conn)
    try:
        cur.execute("SELECT * FROM winners WHERE draw_id=%s", (draw_id,))
        if cur.fetchone():
            flash("Winner already selected!", "warning")
            return redirect(url_for("dashboard"))

        cur.execute("SELECT * FROM participants WHERE draw_id=%s", (draw_id,))
        participants = cur.fetchall()

        if not participants:
            flash("No participants in this draw!", "warning")
            return redirect(url_for("dashboard"))

        winner = random.choice(participants)
        winner_user_id = winner["user_id"]

        cur.execute("INSERT INTO winners (draw_id, user_id) VALUES (%s,%s)",
                    (draw_id, winner_user_id))
        conn.commit()

        cur.execute("SELECT username, email FROM users WHERE id=%s",
                    (winner_user_id,))
        user_data = cur.fetchone()

        cur.execute("SELECT title, draw_date FROM draws WHERE id=%s",
                    (draw_id,))
        draw_data = cur.fetchone()
    finally:
        conn.close()

    # try to send email, but do not block on failure
    try:
        send_winner_email(
            user_data["email"],
            user_data["username"],
            draw_data["title"],
            draw_data["draw_date"]
        )
    except Exception:
        logging.exception("Email send failed (post-insert)")

    return render_template("winner_popup.html",
                           username=user_data["username"],
                           draw_title=draw_data["title"],
                           draw_date=draw_data["draw_date"])
#============generate_report=============================
@app.route("/generate_report/<int:draw_id>")
def generate_report(draw_id):
    if not session.get("is_admin"):
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cur = safe_cursor(conn)
    try:
        cur.execute("SELECT * FROM draws WHERE id=%s", (draw_id,))
        draw = cur.fetchone()

        cur.execute("""
            SELECT p.*, u.username
            FROM participants p
            JOIN users u ON p.user_id = u.id
            WHERE draw_id=%s
        """, (draw_id,))
        participants = cur.fetchall()

        cur.execute("""
            SELECT w.*, u.username, u.email
            FROM winners w
            JOIN users u ON u.id = w.user_id
            WHERE draw_id=%s
        """, (draw_id,))
        winner = cur.fetchone()
    finally:
        conn.close()

    return render_template("report_template.html",
                           draw=draw,
                           participants=participants,
                           winner=winner)
#=================logout=========================
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out", "info")
    return redirect(url_for("home"))

# MAIN
if __name__ == "__main__":
    app.run(debug=True)
