from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import check_password_hash, generate_password_hash
import data
from helpers import *
import re

auth = Blueprint('auth', __name__)

MINPWDCHARS = 8

@auth.route("/register", methods=["GET", "POST"])
def register():    
    if request.method == "POST":        
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        check_result = validate_credentials(username, password, confirmation)
        if check_result:
            return render_template("error.html", message=check_result) 

        # Add user to database
        data.execute("INSERT INTO users (username, hash) VALUES(?, ?)", (username, generate_password_hash(password)))
        return redirect("/")

    else:
        return render_template("register.html")
    

@auth.route("/login", methods=["GET", "POST"])
def login():   
    # Forget any user_id
    session.clear()
    
    if request.method == "POST":        
        if not request.form.get("username"): return render_template("error.html", message="Please provide username.")        
        if not request.form.get("password"): return render_template("error.html", message="must provide password")
                
        rows = data.query("SELECT * FROM users WHERE username = ?", (request.form.get("username"),))
        if len(rows) != 1 or not check_password_hash(rows[0]['hash'], request.form.get("password")):
            return render_template("error.html", message="invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]['id']
        session["username"] = request.form.get("username")
        return redirect("/")
    
    else:
        return render_template("login.html")


@auth.route("/logout")
def logout():
    # Forget any user_id
    session.clear()

    return redirect("/")


@auth.route("/password", methods=["GET", "POST"])
@login_required
def change_password():    
    if request.method == "POST":        
        if not request.form.get("old_password"): return render_template("error.html", message="must provide old password")
        if not request.form.get("new_password"): return render_template("error.html", message="must provide new password")
        if not request.form.get("confirmation"): return render_template("error.html", message="must confirm new password")

        old, new, confirmation = request.form.get("old_password"), request.form.get("new_password"), request.form.get("confirmation")
        user_entry = data.query("SELECT * FROM users WHERE id = ?", (session["user_id"],))[0]

        if not check_password_hash(user_entry['hash'], old): return render_template("error.html", message="incorrect password")

        password_check_result = validate_password(new, confirmation)
        if password_check_result: return render_template("error.html", message=password_check_result)

        data.execute("UPDATE users SET hash = ? WHERE id = ?", (generate_password_hash(new), session["user_id"]))
        return render_template("password_changed.html")

    else:
        return render_template("password.html")
    

def validate_password(password, confirmation):
    # Check password is at least 8 characters
    if len(password) < MINPWDCHARS:
        return "passwords must be at least 8 characters long"

    # Check password contains at least 1 number, 1 lowercase, 1 uppercase and 1 special character     
    if not bool(re.search(r'(?=.*\d)(?=.*[a-z])(?=.*[A-Z])(?=.*[!@#$%^&*()-+?_=,<>/])', password)):
        return "Passwords must contain at least 1 number, 1 lowercase letter, 1 uppercase letter and 1 special character !@#$%^&*()-+?_=,<>/"

    if password != confirmation:
        return "passwords do not match"
    
    return None
    

def validate_credentials(username, password, confirmation):
    users = data.query("SELECT username FROM users")    
    
    if not username: return "Please provide username."
    if not password: return "must provide password"

    for user in users:
        if username in user: return "username already exists"     
   
    pwd_check_result = validate_password(password, confirmation)
    if pwd_check_result:
        return pwd_check_result
    
    return None