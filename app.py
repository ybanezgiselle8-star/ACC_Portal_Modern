import os, sqlite3, secrets
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash

BASE=os.path.dirname(os.path.abspath(__file__))
DB=os.path.join(BASE,"acc_portal.db"); UPLOAD=os.path.join(BASE,"uploads")
os.makedirs(UPLOAD,exist_ok=True)
app=Flask(__name__); app.secret_key="acc-connect-change-this"; app.config["MAX_CONTENT_LENGTH"]=5*1024*1024

def db():
    c=sqlite3.connect(DB); c.row_factory=sqlite3.Row; return c
def init_db():
    c=db(); c.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY AUTOINCREMENT,full_name TEXT NOT NULL,student_id TEXT UNIQUE NOT NULL,email TEXT UNIQUE NOT NULL,password_hash TEXT NOT NULL,role TEXT DEFAULT 'student',created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS registrations(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,birth_date TEXT,sex TEXT,address TEXT,contact TEXT,course TEXT,year_level TEXT,valid_id TEXT,status TEXT DEFAULT 'Pending',created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS scholarships(id INTEGER PRIMARY KEY AUTOINCREMENT,user_id INTEGER,type TEXT,reason TEXT,status TEXT DEFAULT 'Pending',created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    """)
    if not c.execute("SELECT id FROM users WHERE email='admin@acc.edu.ph'").fetchone():
        c.execute("INSERT INTO users(full_name,student_id,email,password_hash,role) VALUES(?,?,?,?,?)",("ACC Administrator","ADMIN-001","admin@acc.edu.ph",generate_password_hash("admin123"),"admin"))
    c.commit(); c.close()
def required(role="student"):
    def dec(f):
        @wraps(f)
        def w(*a,**k):
            if "user_id" not in session:return redirect(url_for("login"))
            if role=="admin" and session.get("role")!="admin":return redirect(url_for("dashboard"))
            return f(*a,**k)
        return w
    return dec

@app.route("/")
def home(): return render_template("home.html")
@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        n=request.form.get("full_name","").strip(); sid=request.form.get("student_id","").strip(); e=request.form.get("email","").strip().lower(); p=request.form.get("password",""); cp=request.form.get("confirm","")
        if not all([n,sid,e,p,cp]): flash("Complete all required fields.","danger")
        elif p!=cp: flash("Passwords do not match.","danger")
        elif len(p)<6: flash("Password must be at least 6 characters.","danger")
        else:
            c=db()
            try:c.execute("INSERT INTO users(full_name,student_id,email,password_hash) VALUES(?,?,?,?)",(n,sid,e,generate_password_hash(p)));c.commit();c.close();flash("Account created!","success");return redirect(url_for("login"))
            except sqlite3.IntegrityError:c.close();flash("Email or Student ID already exists.","danger")
    return render_template("register.html")
@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        e=request.form.get("email","").strip().lower();p=request.form.get("password","");c=db();u=c.execute("SELECT * FROM users WHERE email=?",(e,)).fetchone();c.close()
        if u and check_password_hash(u["password_hash"],p):session.clear();session.update(user_id=u["id"],full_name=u["full_name"],role=u["role"]);return redirect(url_for("dashboard"))
        flash("Invalid email or password.","danger")
    return render_template("login.html")
@app.route("/logout")
def logout():session.clear();return redirect(url_for("home"))
@app.route("/dashboard")
@required()
def dashboard():
    c=db();u=c.execute("SELECT * FROM users WHERE id=?",(session["user_id"],)).fetchone();r=c.execute("SELECT * FROM registrations WHERE user_id=? ORDER BY id DESC LIMIT 1",(u["id"],)).fetchone();s=c.execute("SELECT * FROM scholarships WHERE user_id=? ORDER BY id DESC",(u["id"],)).fetchall();c.close()
    return render_template("dashboard.html",u=u,r=r,sch=s)
@app.route("/registration",methods=["GET","POST"])
@required()
def registration():
    if request.method=="POST":
        names=["birth_date","sex","address","contact","course","year_level"];v=[request.form.get(x,"").strip() for x in names];f=request.files.get("valid_id")
        if not all(v) or not f or not f.filename:flash("Complete the form and attach a valid ID.","danger")
        elif "." not in f.filename or f.filename.rsplit(".",1)[1].lower() not in {"pdf","jpg","jpeg","png"}:flash("ID must be PDF, JPG, JPEG, or PNG.","danger")
        else:
            ext=f.filename.rsplit(".",1)[1].lower();fn=f"uid_{session['user_id']}_{secrets.token_hex(5)}.{ext}";f.save(os.path.join(UPLOAD,fn));c=db();c.execute("INSERT INTO registrations(user_id,birth_date,sex,address,contact,course,year_level,valid_id) VALUES(?,?,?,?,?,?,?,?)",(session["user_id"],*v,fn));c.commit();c.close();flash("Registration submitted!","success");return redirect(url_for("dashboard"))
    return render_template("registration.html")
@app.route("/scholarship",methods=["GET","POST"])
@required()
def scholarship():
    if request.method=="POST":
        t=request.form.get("type","");r=request.form.get("reason","").strip()
        if not t or not r:flash("Complete the scholarship form.","danger")
        else:c=db();c.execute("INSERT INTO scholarships(user_id,type,reason) VALUES(?,?,?)",(session["user_id"],t,r));c.commit();c.close();flash("Scholarship application submitted!","success");return redirect(url_for("dashboard"))
    return render_template("scholarship.html")
@app.route("/admin")
@required("admin")
def admin():
    c=db();regs=c.execute("SELECT r.*,u.full_name,u.student_id FROM registrations r JOIN users u ON u.id=r.user_id ORDER BY r.id DESC").fetchall();sch=c.execute("SELECT s.*,u.full_name,u.student_id FROM scholarships s JOIN users u ON u.id=s.user_id ORDER BY s.id DESC").fetchall();c.close();return render_template("admin.html",regs=regs,sch=sch)
@app.route("/admin/reg/<int:id>/<status>")
@required("admin")
def reg_status(id,status):
    if status in ("Approved","Rejected","Pending"):c=db();c.execute("UPDATE registrations SET status=? WHERE id=?",(status,id));c.commit();c.close()
    return redirect(url_for("admin"))
@app.route("/admin/sch/<int:id>/<status>")
@required("admin")
def sch_status(id,status):
    if status in ("Approved","Rejected","Pending"):c=db();c.execute("UPDATE scholarships SET status=? WHERE id=?",(status,id));c.commit();c.close()
    return redirect(url_for("admin"))
@app.route("/uploads/<path:name>")
@required("admin")
def uploads(name):return send_from_directory(UPLOAD,name)
init_db()
if __name__=="__main__":app.run(debug=True)
