# Student Project Funding - Full Stack + AIML MVP

This is a deadline-friendly full-stack Student Project Funding platform.

## Features

### Student
- Registration/login
- Profile
- Submit a new project
- Project description, category, GitHub/demo links
- Required funding amount
- Track pending/approved/rejected projects
- Funding wallet
- Project status history

### Sponsor
- Registration/login
- Sponsor profile
- View pending/approved/rejected projects
- View complete project details
- See student contact details
- Approve/reject pending projects
- Funding is transferred automatically on approval

### AIML
- Extractive NLP project summary using TF-IDF
- Similar-project detection using TF-IDF + cosine similarity
- Full-screen natural-language AI Assistance on the sponsor dashboard
- AI searches all projects in the database using USN/project-name matching, typo-tolerant fuzzy matching and TF-IDF fallback

## Technology

- Python
- Flask
- SQLite
- scikit-learn
- HTML/CSS/JavaScript
- Bootstrap-style custom responsive CSS

## Run in VS Code

1. Install Python 3.11+.
2. Open this folder in VS Code.
3. Open Terminal.
4. Create a virtual environment:

   Windows:
   `python -m venv venv`
   `venv\Scripts\activate`

   Linux/macOS:
   `python3 -m venv venv`
   `source venv/bin/activate`

5. Install packages:

   `pip install -r requirements.txt`

6. Start:

   `python app.py`

7. Open:
   `http://127.0.0.1:5000`

The database `funding.db` is created automatically.

## Demo accounts

Student:
- username: `student1`
- password: `student123`

Sponsor:
- username: `sponsor1`
- password: `sponsor123`

## Suggested demo

1. Login as student.
2. Show dashboard.
3. Submit a new project.
4. Logout.
5. Login as sponsor.
6. Open Pending Projects.
7. Open the project.
8. Open AI Assistance from the sponsor dashboard.
9. Ask natural-language questions using a project name or USN.
10. Approve the project.
11. Logout.
12. Login as student again.
13. Show Approved status and wallet/funded amount.

## Important

This is a college-project MVP, not a production financial application. Real payment gateways, KYC, email verification, and production security should be added for real deployment.

## Add 500 demo projects

The project includes `seed_500_projects.py`. It creates 500 different demo student accounts and projects directly in the same SQLite database used by Flask. Each project includes a USN, student name/contact details, project name, description, category, funding amount, GitHub link, demo link and pending status.

Run from the project folder:

`python seed_500_projects.py`

The script is safe to run repeatedly: generated usernames/USNs that already exist are skipped.

## Sponsor AI Assistance

AI Assistance is available from the Sponsor Dashboard and searches the complete project database. It accepts natural-language questions using a project name or USN, tolerates common spelling mistakes, and can answer project details, student details, category, funding, status, submission date and GitHub/demo references. The chat is full-screen black with white text and can be stopped/restarted.
