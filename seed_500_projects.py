"""Insert 500 realistic demo student projects into the existing SQLite database.
Run: python seed_500_projects.py
Safe to run repeatedly: the same generated usernames/USNs are skipped.
"""
from app import db, init_db
from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta
import random

random.seed(42)
init_db()

first_names = ["Aarav","Aditi","Akash","Ananya","Arjun","Bhavana","Chetan","Diya","Gagan","Harsh","Ishita","Karthik","Kavya","Manoj","Meera","Nikhil","Pooja","Pranav","Rahul","Riya","Sanjay","Sneha","Varun","Vidya","Yash"]
last_names = ["Gowda","Patil","Sharma","Reddy","Kulkarni","Joshi","Shetty","Naik","Bhat","Rao","Kumar","Desai","Hegde","Nayak","Prajapati"]
ideas = [
("AI Crop Disease Detection","Artificial Intelligence","An AI system that analyzes crop images and identifies common plant diseases early so farmers can take timely action."),
("Smart Waste Management","Environment","A web and IoT based platform for tracking waste collection, classifying waste and improving recycling operations."),
("Campus Safety Alert","IoT","A campus safety platform that sends emergency alerts and helps authorized users report incidents quickly."),
("Student Skill Tracker","Education","A platform that records student skills, projects and learning progress and presents useful progress reports."),
("Health Appointment Portal","Healthcare","A web application that helps patients find available appointments and manage basic appointment information."),
("Traffic Flow Predictor","Artificial Intelligence","A machine learning project that studies traffic patterns and predicts congestion to support better route planning."),
("Library Management Portal","Web Development","A digital library platform for searching books, tracking borrowing records and managing availability."),
("Water Quality Monitor","IoT","A monitoring system that records water-quality sensor readings and presents alerts through a web dashboard."),
("Secure Feedback System","Web Development","A secure feedback platform that collects structured feedback and provides useful reports to authorized users."),
("Expense Tracking Assistant","Web Development","A personal finance application that categorizes expenses and presents spending summaries."),
]
categories = [x[1] for x in ideas]
conn = db()
inserted = 0
for i in range(1, 501):
    usn = f"1MS22CS{i:03d}"
    username = f"student_demo_{i:03d}"
    if conn.execute("SELECT 1 FROM users WHERE username=? OR EXISTS (SELECT 1 FROM projects WHERE usn=?)", (username, usn)).fetchone():
        continue
    first = first_names[(i-1) % len(first_names)]
    last = last_names[(i*3) % len(last_names)]
    name = f"{first} {last}"
    mobile = f"9{random.randint(100000000,999999999)}"
    email = f"{username}@example.com"
    conn.execute("INSERT INTO users(username,name,mobile,email,password_hash,role,wallet_balance) VALUES(?,?,?,?,?,?,0)",
                 (username,name,mobile,email,generate_password_hash("student123"),"student"))
    student_id = conn.execute("SELECT id FROM users WHERE username=?", (username,)).fetchone()[0]
    title, category, desc = ideas[(i-1) % len(ideas)]
    title = f"{title} {i:03d}"
    amount = random.choice([15000,20000,25000,30000,40000,50000,75000,100000])
    created = datetime.now() - timedelta(days=random.randint(0,180), hours=random.randint(0,23))
    cur = conn.execute("""INSERT INTO projects(student_id,title,description,category,usn,student_name,github_link,demo_link,required_amount,status,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                       (student_id,title,desc,category,usn,name,f"https://github.com/demo/{username}",f"https://demo.example.com/{username}",amount,"pending",created.strftime("%Y-%m-%d %H:%M:%S")))
    conn.execute("INSERT INTO status_history(project_id,old_status,new_status,changed_by,comment,changed_at) VALUES(?,?,?,?,?,?)",
                 (cur.lastrowid,None,"pending",student_id,"Project submitted",created.strftime("%Y-%m-%d %H:%M:%S")))
    inserted += 1
conn.commit(); conn.close()
print(f"Inserted {inserted} demo student projects. Existing records were preserved.")
