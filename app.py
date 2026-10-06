from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from pathlib import Path
import re
from difflib import SequenceMatcher
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "funding.db"

app = Flask(__name__)
app.secret_key = "student-funding-demo-secret-change-me"


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        mobile TEXT,
        email TEXT,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('student','sponsor')),
        wallet_balance REAL NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        category TEXT NOT NULL,
        usn TEXT NOT NULL,
        student_name TEXT NOT NULL,
        github_link TEXT,
        demo_link TEXT,
        required_amount REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending'
            CHECK(status IN ('pending','approved','rejected')),
        sponsor_id INTEGER,
        sponsor_comment TEXT,
        funded_amount REAL NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(student_id) REFERENCES users(id),
        FOREIGN KEY(sponsor_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS status_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id INTEGER NOT NULL,
        old_status TEXT,
        new_status TEXT NOT NULL,
        changed_by INTEGER,
        comment TEXT,
        changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(project_id) REFERENCES projects(id),
        FOREIGN KEY(changed_by) REFERENCES users(id)
    );
    """)
    # Migrate older versions: add USN and permanently remove the old
    # advantages/disadvantages columns if they exist.
    cols = [row[1] for row in conn.execute("PRAGMA table_info(projects)").fetchall()]
    if "usn" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN usn TEXT NOT NULL DEFAULT 'UNKNOWN'")
        cols.append("usn")
    if "student_name" not in cols:
        conn.execute("ALTER TABLE projects ADD COLUMN student_name TEXT NOT NULL DEFAULT ''")
        conn.execute("UPDATE projects SET student_name=(SELECT name FROM users WHERE users.id=projects.student_id) WHERE student_name='' OR student_name IS NULL")
        cols.append("student_name")
    if "advantages" in cols or "disadvantages" in cols:
        conn.execute("PRAGMA foreign_keys=OFF")
        conn.execute("""CREATE TABLE projects_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            usn TEXT NOT NULL,
            student_name TEXT NOT NULL,
            github_link TEXT,
            demo_link TEXT,
            required_amount REAL NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','approved','rejected')),
            sponsor_id INTEGER,
            sponsor_comment TEXT,
            funded_amount REAL NOT NULL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(student_id) REFERENCES users(id),
            FOREIGN KEY(sponsor_id) REFERENCES users(id)
        )""")
        conn.execute("""INSERT INTO projects_new
            (id,student_id,title,description,category,usn,student_name,github_link,demo_link,required_amount,status,sponsor_id,sponsor_comment,funded_amount,created_at)
            SELECT id,student_id,title,description,category,COALESCE(usn,'UNKNOWN'),COALESCE(student_name,(SELECT name FROM users WHERE users.id=projects.student_id),''),github_link,demo_link,required_amount,status,sponsor_id,sponsor_comment,funded_amount,created_at
            FROM projects""")
        conn.execute("DROP TABLE projects")
        conn.execute("ALTER TABLE projects_new RENAME TO projects")
        conn.execute("PRAGMA foreign_keys=ON")

    # Demo accounts for easy presentation.
    users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
    if users == 0:
        conn.execute(
            "INSERT INTO users(username,name,mobile,email,password_hash,role,wallet_balance) VALUES(?,?,?,?,?,?,?)",
            ("student1", "Demo Student", "9876543210", "student@example.com",
             generate_password_hash("student123"), "student", 0)
        )
        conn.execute(
            "INSERT INTO users(username,name,mobile,email,password_hash,role,wallet_balance) VALUES(?,?,?,?,?,?,?)",
            ("sponsor1", "Demo Sponsor", "9123456780", "sponsor@example.com",
             generate_password_hash("sponsor123"), "sponsor", 100000)
        )
        # No demo project is inserted. Students create their own projects.
    conn.commit()
    conn.close()


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return user


@app.context_processor
def inject_user():
    return {"current_user": current_user()}


def login_required(role=None):
    user = current_user()
    if not user:
        return redirect(url_for("login"))
    if role and user["role"] != role:
        return redirect(url_for("dashboard"))
    return None


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip()
        name = request.form["name"].strip()
        mobile = request.form.get("mobile", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form["password"]
        confirm = request.form["confirm_password"]
        role = request.form["role"]
        if password != confirm:
            flash("Passwords do not match.", "error")
            return render_template("register.html")
        if role not in ("student", "sponsor"):
            flash("Invalid role.", "error")
            return render_template("register.html")
        try:
            conn = db()
            balance = 100000 if role == "sponsor" else 0
            conn.execute(
                "INSERT INTO users(username,name,mobile,email,password_hash,role,wallet_balance) VALUES(?,?,?,?,?,?,?)",
                (username, name, mobile, email, generate_password_hash(password), role, balance)
            )
            conn.commit()
            conn.close()
            flash("Registration successful. Please login.", "success")
            return redirect(url_for("login"))
        except sqlite3.IntegrityError:
            flash("Username already exists.", "error")
    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    guard = login_required()
    if guard:
        return guard
    return redirect(url_for("student_dashboard" if current_user()["role"] == "student" else "sponsor_dashboard"))


@app.route("/student")
def student_dashboard():
    guard = login_required("student")
    if guard:
        return guard
    user = current_user()
    conn = db()
    projects = conn.execute("""
        SELECT p.*, u.name AS sponsor_name
        FROM projects p LEFT JOIN users u ON p.sponsor_id=u.id
        WHERE p.student_id=? ORDER BY p.created_at DESC
    """, (user["id"],)).fetchall()
    counts = {
        "pending": sum(1 for p in projects if p["status"] == "pending"),
        "approved": sum(1 for p in projects if p["status"] == "approved"),
        "rejected": sum(1 for p in projects if p["status"] == "rejected"),
    }
    conn.close()
    return render_template("student_dashboard.html", projects=projects, counts=counts)


@app.route("/student/project/new", methods=["GET", "POST"])
def new_project():
    guard = login_required("student")
    if guard:
        return guard
    if request.method == "POST":
        title = request.form["title"].strip()
        usn = request.form["usn"].strip().upper()
        student_name = request.form["student_name"].strip()
        description = request.form["description"].strip()
        category = request.form["category"].strip()
        amount = float(request.form.get("required_amount") or 0)
        if not usn:
            flash("USN is required.", "error")
            return render_template("project_form.html")
        if not student_name:
            flash("Student name is required.", "error")
            return render_template("project_form.html")
        conn = db()
        cur = conn.execute("""
            INSERT INTO projects
            (student_id,title,description,category,usn,student_name,github_link,demo_link,required_amount)
            VALUES(?,?,?,?,?,?,?,?,?)
        """, (
            current_user()["id"], title, description, category, usn, student_name,
            request.form.get("github_link","").strip(),
            request.form.get("demo_link","").strip(),
            amount
        ))
        project_id = cur.lastrowid
        conn.execute(
            "INSERT INTO status_history(project_id,old_status,new_status,changed_by,comment) VALUES(?,?,?,?,?)",
            (project_id, None, "pending", current_user()["id"], "Project submitted")
        )
        conn.commit()
        conn.close()
        flash("Project submitted successfully.", "success")
        return redirect(url_for("student_dashboard"))
    return render_template("project_form.html")


@app.route("/project/<int:project_id>")
def project_detail(project_id):
    guard = login_required()
    if guard:
        return guard
    conn = db()
    project = conn.execute("""
        SELECT p.*, COALESCE(NULLIF(p.student_name,''),s.name) AS student_name, s.mobile AS student_mobile, s.email AS student_email,
               sp.name AS sponsor_name
        FROM projects p
        JOIN users s ON p.student_id=s.id
        LEFT JOIN users sp ON p.sponsor_id=sp.id
        WHERE p.id=?
    """, (project_id,)).fetchone()
    history = conn.execute("""
        SELECT h.*, u.name AS changer
        FROM status_history h LEFT JOIN users u ON h.changed_by=u.id
        WHERE h.project_id=? ORDER BY h.changed_at DESC
    """, (project_id,)).fetchall()
    conn.close()
    if not project:
        flash("Project not found.", "error")
        return redirect(url_for("dashboard"))
    user = current_user()
    if user["role"] == "student" and project["student_id"] != user["id"]:
        flash("You cannot access this project.", "error")
        return redirect(url_for("student_dashboard"))
    return render_template("project_detail.html", project=project, history=history)


@app.route("/sponsor")
def sponsor_dashboard():
    guard = login_required("sponsor")
    if guard:
        return guard
    conn = db()
    projects = conn.execute("""
        SELECT p.*, COALESCE(NULLIF(p.student_name,''),u.name) AS student_name, u.mobile AS student_mobile, u.email AS student_email
        FROM projects p JOIN users u ON p.student_id=u.id
        ORDER BY p.created_at DESC
    """).fetchall()
    conn.close()
    return render_template("sponsor_dashboard.html", projects=projects)


@app.route("/sponsor/project/<int:project_id>")
def sponsor_project(project_id):
    guard = login_required("sponsor")
    if guard:
        return guard
    conn = db()
    project = conn.execute("""
        SELECT p.*,
               COALESCE(NULLIF(p.student_name,''),s.name) AS student_name, s.username AS student_username,
               s.mobile AS student_mobile, s.email AS student_email,
               sp.name AS sponsor_name
        FROM projects p
        JOIN users s ON p.student_id=s.id
        LEFT JOIN users sp ON p.sponsor_id=sp.id
        WHERE p.id=?
    """, (project_id,)).fetchone()
    conn.close()
    if not project:
        flash("Project not found.", "error")
        return redirect(url_for("sponsor_dashboard"))
    return render_template("sponsor_project.html", project=project)


@app.route("/sponsor/project/<int:project_id>/decision", methods=["POST"])
def sponsor_decision(project_id):
    guard = login_required("sponsor")
    if guard:
        return guard
    action = request.form["action"]
    if action not in ("approved", "rejected"):
        flash("Invalid action.", "error")
        return redirect(url_for("sponsor_dashboard"))
    conn = db()
    project = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not project:
        conn.close()
        flash("Project not found.", "error")
        return redirect(url_for("sponsor_dashboard"))
    sponsor = current_user()
    old = project["status"]
    if old != "pending":
        conn.close()
        flash("Only pending projects can be reviewed.", "error")
        return redirect(url_for("sponsor_project", project_id=project_id))
    funded = project["required_amount"] if action == "approved" else 0
    comment = request.form.get("comment", "").strip()
    conn.execute("""
        UPDATE projects SET status=?, sponsor_id=?, sponsor_comment=?, funded_amount=?
        WHERE id=?
    """, (
        action, sponsor["id"], comment, funded, project_id
    ))
    if action == "approved":
        conn.execute(
            "UPDATE users SET wallet_balance = wallet_balance + ? WHERE id = ? AND role = 'student'",
            (funded, project["student_id"])
        )
    conn.execute(
        "INSERT INTO status_history(project_id,old_status,new_status,changed_by,comment) VALUES(?,?,?,?,?)",
        (project_id, old, action, sponsor["id"], comment)
    )
    conn.commit()
    conn.close()
    flash(f"Project {action}.", "success")
    return redirect(url_for("sponsor_dashboard"))


def make_summary(description):
    sentences = re.split(r'(?<=[.!?])\s+', description.strip())
    sentences = [s for s in sentences if s]
    if not sentences:
        return "No description available."
    # Lightweight NLP extractive summary: score sentences by TF-IDF relevance.
    if len(sentences) <= 2:
        return " ".join(sentences)
    vectorizer = TfidfVectorizer(stop_words="english")
    matrix = vectorizer.fit_transform(sentences)
    scores = matrix.sum(axis=1).A1
    best = sorted(range(len(sentences)), key=lambda i: scores[i], reverse=True)[:2]
    best.sort()
    return " ".join(sentences[i] for i in best)


@app.route("/sponsor/ai")
def ai_assistant_page():
    guard = login_required("sponsor")
    if guard:
        return guard
    return render_template("ai_assistant.html")


def _norm(text):
    text = (text or "").lower()
    text = text.replace("₹", " rupees ")
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _ratio(a, b):
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _project_rows(conn):
    return conn.execute("""SELECT p.*, COALESCE(NULLIF(p.student_name,''),s.name) AS student_name,
        s.username AS student_username, s.mobile AS student_mobile, s.email AS student_email,
        sp.name AS sponsor_name
        FROM projects p JOIN users s ON p.student_id=s.id
        LEFT JOIN users sp ON p.sponsor_id=sp.id ORDER BY p.created_at DESC""").fetchall()


def _project_context(conn, project_id):
    if not project_id:
        return None
    return conn.execute("""SELECT p.*, COALESCE(NULLIF(p.student_name,''),s.name) AS student_name,
        s.username AS student_username, s.mobile AS student_mobile, s.email AS student_email,
        sp.name AS sponsor_name
        FROM projects p JOIN users s ON p.student_id=s.id
        LEFT JOIN users sp ON p.sponsor_id=sp.id WHERE p.id=?""", (project_id,)).fetchone()


def _clean_query(q):
    words = _norm(q).split()
    stop = {
        "the","a","an","of","for","on","in","to","me","my","is","are","was","were",
        "this","that","please","give","show","tell","what","who","which","can","you","about",
        "details","detail","project","projects","student","students","name","link","get","find",
        "display","all","information","info","from","by","with","do","does","did","and","or",
        "could","would","should","i","want","need","know","tellme","provide","provide me"
    }
    return " ".join(w for w in words if w not in stop)


def _ratio(a, b):
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


def _token_similarity(a, b):
    a=set(_norm(a).split()); b=set(_norm(b).split())
    if not a or not b: return 0.0
    return len(a & b) / len(a | b)


def _match_score(query, value):
    q=_norm(query); v=_norm(value)
    if not q or not v: return 0.0
    if q == v: return 1.0
    if q in v or v in q: return 0.94
    return max(_ratio(q,v), _token_similarity(q,v))


def _project_rows(conn):
    return conn.execute("""SELECT p.*, COALESCE(NULLIF(p.student_name,''),s.name) AS student_name,
        s.username AS student_username, s.mobile AS student_mobile, s.email AS student_email,
        sp.name AS sponsor_name
        FROM projects p JOIN users s ON p.student_id=s.id
        LEFT JOIN users sp ON p.sponsor_id=sp.id ORDER BY p.created_at DESC""").fetchall()


def _project_context(conn, project_id):
    if not project_id: return None
    return conn.execute("""SELECT p.*, COALESCE(NULLIF(p.student_name,''),s.name) AS student_name,
        s.username AS student_username, s.mobile AS student_mobile, s.email AS student_email,
        sp.name AS sponsor_name
        FROM projects p JOIN users s ON p.student_id=s.id
        LEFT JOIN users sp ON p.sponsor_id=sp.id WHERE p.id=?""", (project_id,)).fetchone()


def _find_projects(conn, question):
    projects=list(_project_rows(conn)); q=_norm(question)
    if not projects: return []
    # Strong identifiers first: USN, exact project title, exact student name/username.
    exact=[]
    for p in projects:
        vals=[p["usn"],p["title"],p["student_name"],p["student_username"]]
        if any(v and _norm(v) in q for v in vals): exact.append(p)
    if exact: return exact
    core=_clean_query(q) or q
    scored=[]
    for p in projects:
        vals=[p["title"],p["usn"],p["student_name"],p["student_username"],p["category"]]
        score=max((_match_score(core,v) for v in vals if v),default=0)
        scored.append((score,p))
    scored.sort(key=lambda x:x[0], reverse=True)
    return [p for score,p in scored[:5] if score >= 0.38]


def _find_projects_by_person(conn, question):
    projects=list(_project_rows(conn)); q=_norm(question)
    # Prefer exact USN/name/username anywhere in the sentence.
    exact=[]
    for p in projects:
        if p["usn"] and _norm(p["usn"]) in q: exact.append(p)
        elif p["student_name"] and _norm(p["student_name"]) in q: exact.append(p)
        elif p["student_username"] and _norm(p["student_username"]) in q: exact.append(p)
    if exact: return exact
    core=_clean_query(q)
    scored=[]
    for p in projects:
        score=max(_match_score(core,p["usn"]),_match_score(core,p["student_name"]),_match_score(core,p["student_username"]))
        scored.append((score,p))
    scored.sort(key=lambda x:x[0],reverse=True)
    if not scored or scored[0][0] < .45: return []
    best=scored[0][0]
    return [p for score,p in scored if score >= max(.45,best-.08)]


def _full_project_text(p):
    amount=float(p["required_amount"] or 0); funded=float(p["funded_amount"] or 0)
    return (f"Project name: {p['title']}\nUSN: {p['usn']}\nStudent name: {p['student_name']}\n"
            f"Mobile: {p['student_mobile'] or 'Not provided'}\nEmail: {p['student_email'] or 'Not provided'}\n"
            f"Category: {p['category']}\nRequired funding: ₹{amount:,.2f}\nApproved/funded amount: ₹{funded:,.2f}\n"
            f"Status: {p['status'].capitalize()}\nGitHub: {p['github_link'] or 'Not provided'}\n"
            f"Demo: {p['demo_link'] or 'Not provided'}\nSubmitted on: {p['created_at']}\n\nDescription:\n{p['description'] or 'No description provided.'}")


def _has(q, *terms):
    return any(t in q for t in terms)


def _is_projects_list_request(q):
    return _has(q,
        "projects of","projects for","projects by","projects from","all projects of","all projects for",
        "project list of","project list for","project list by","projects submitted by","projects submitted from",
        "what projects","which projects","list projects","show projects","display projects")


def _is_name_request(q):
    return _has(q,
        "what is name","what is the name","name of","student name","name of student","who is the student",
        "who submitted","student who submitted","whose project")


def _is_usn_request(q):
    return _has(q,"what is usn","what is the usn","student usn","usn of","university seat number","registration number")


def _answer_for_project(project, question):
    q=_norm(question); amount=float(project["required_amount"] or 0); funded=float(project["funded_amount"] or 0)
    # Field-specific questions are intentionally checked BEFORE generic "details" handling.
    if _is_name_request(q):
        return "Student Name", project["student_name"] or "The student's name was not provided."
    if _is_usn_request(q):
        return "USN", project["usn"] or "The USN was not provided."
    if _has(q,"mobile","phone","phone number","contact number","telephone","mobile number"):
        return "Student Mobile", project["student_mobile"] or "The student's mobile number was not provided."
    if _has(q,"email","email id","mail id","student mail","student email"):
        return "Student Email", project["student_email"] or "The student's email was not provided."
    if _has(q,"github","git hub","githublink","git link","repository","repo","source code"):
        return "GitHub", project["github_link"] or "No GitHub link was provided."
    if _has(q,"demo","live link","live demo","demo link","website link","deployed link","deployment"):
        return "Demo", project["demo_link"] or "No demo link was provided."
    if _has(q,"category","domain","field","type of project","area","project type"):
        return "Category", project["category"] or "The category was not provided."
    if _has(q,"required amount","required funding","funding needed","fund needed","fund required","how much funding","how much money","money needed","budget","cost","amount needed","funding amount"):
        return "Required Funding", f"The project requires ₹{amount:,.2f}."
    if _has(q,"approved amount","funded amount","amount approved","money approved","approved funding"):
        return "Approved Funding", f"The approved/funded amount is ₹{funded:,.2f}."
    if _has(q,"status","state","pending or approved","approved or rejected","current status"):
        return "Project Status", project["status"].capitalize()
    if _has(q,"submitted date","submission date","when submitted","submitted on","date submitted"):
        return "Submission Date", project["created_at"]
    if _has(q,"sponsor name","reviewed by","approved by","who approved","sponsor"):
        return "Sponsor", project["sponsor_name"] or "No sponsor has been assigned yet."
    if _has(q,"summary","summarize","summarise","brief","overview","short description","in short"):
        return "Project Summary", f"{project['title']} — {make_summary(project['description'] or 'No description available.')}"
    if _has(q,"description","what does","what is this project","explain project","how does this project","what is it about","about the project","project about"):
        return "Project Description", project["description"] or "No description was provided."
    # Explicit complete-detail requests only return the full record.
    if _has(q,"full details","all details","all information","everything about","complete details","complete information") or q.startswith("details of") or q.startswith("detail of") or "project details of" in q:
        return "Complete Project Details", _full_project_text(project)
    return "Project Details", _full_project_text(project)


def _list_projects_text(rows):
    return "\n".join(f"• {p['title']} — USN: {p['usn']} — Student: {p['student_name']} — {p['status'].capitalize()}" for p in rows)


@app.route("/api/ai/global", methods=["POST"])
def ai_global():
    guard=login_required("sponsor")
    if guard: return jsonify({"error":"login required"}),401
    payload=request.get_json(silent=True) or {}; question=(payload.get("question") or "").strip(); context_id=payload.get("context_project_id")
    if not question: return jsonify({"error":"Please type a question."}),400
    if _norm(question) in {"stop","stop chat","end chat","exit","quit","stop the chat","end"}:
        return jsonify({"message":"AI assistance stopped. Click Restart AI Assistance when you want to continue.","stopped":True})
    conn=db(); q=_norm(question)

    # More than 30 natural-language patterns are supported here; matching is semantic/typo tolerant,
    # not a single exact command. The database remains the source of truth.
    list_patterns={
        "pending":["pending projects","show pending","list pending","projects pending","which are pending","waiting projects"],
        "approved":["approved projects","show approved","list approved","projects approved","which are approved"],
        "rejected":["rejected projects","show rejected","list rejected","projects rejected","which are rejected"],
    }
    for status,patterns in list_patterns.items():
        if any(x in q for x in patterns):
            rows=conn.execute("SELECT p.*, COALESCE(NULLIF(p.student_name,''),u.name) AS student_name FROM projects p JOIN users u ON p.student_id=u.id WHERE p.status=? ORDER BY p.created_at DESC",(status,)).fetchall(); conn.close()
            return jsonify({"heading":f"{status.capitalize()} Projects","message":_list_projects_text(rows) if rows else f"There are no {status} projects.","stopped":False})

    # "projects of/for/by <person>" ALWAYS returns a list, never full project details.
    if _is_projects_list_request(q):
        rows=_find_projects_by_person(conn,question)
        if rows:
            seen={r["id"]:r for r in rows}; rows=list(seen.values())
            conn.close(); return jsonify({"heading":"Projects Found","message":_list_projects_text(rows),"stopped":False})
        conn.close(); return jsonify({"heading":"No Projects Found","message":"I couldn't find projects for that USN or student name. Try the exact USN or student name.","stopped":False})

    # A direct USN/name field question should resolve to one field, not the whole project.
    rows=_find_projects(conn,question)
    context=_project_context(conn,context_id)
    if not rows and context and _has(q,"this project","this","it","that project","the project"):
        rows=[context]
    if not rows:
        conn.close(); return jsonify({"heading":"Project Not Found","message":"I couldn't confidently identify a project or student from that question. Try the project name, USN, or student name.","stopped":False})

    # If a student name/USN is requested, return ONLY that field from the best matching record.
    if _is_name_request(q) or _is_usn_request(q):
        heading,answer=_answer_for_project(rows[0],question)
    else:
        # Specific fields always beat generic details, summaries, links, etc.
        heading,answer=_answer_for_project(rows[0],question)
    conn.close(); return jsonify({"heading":heading,"message":answer,"stopped":False,"project_id":rows[0]["id"],"project_name":rows[0]["title"],"usn":rows[0]["usn"]})


init_db()

if __name__ == "__main__":
    app.run(debug=True)
