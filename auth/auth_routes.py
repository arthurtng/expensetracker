from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import check_password_hash, generate_password_hash
import data
from helpers import *

auth = Blueprint('auth', __name__)

MINPWDCHARS = 8

@auth.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    if request.method == "POST":

        users = data.query("SELECT username FROM users")

        username = request.form.get("username")

        # Check user input username
        if not username:
            return render_template("error.html", message="Please provide username.")

        # Check if input username already exists
        for user in users:
            if username in user:
                return render_template("error.html", message="username already exists")

        password = request.form.get("password")

        # Check user input a password
        if not password:
            return render_template("error.html", message="must provide password")

        confirmation = request.form.get("confirmation")

        if pwd_checks(password, confirmation):
            return render_template("error.html", message=pwd_checks(password, confirmation))

        # Add user to database
        data.execute("INSERT INTO users (username, hash) VALUES(?, ?)", (username, generate_password_hash(password)))
        return redirect("/")

    else:

        return render_template("register.html")
    
@auth.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return render_template("error.html", message="Please provide username.")

        # Ensure password was submitted
        if not request.form.get("password"):
            return render_template("error.html", message="must provide password")

        # Query database for username
        rows = data.query("SELECT * FROM users WHERE username = ?", (request.form.get("username"),))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]['hash'], request.form.get("password")):
            return render_template("error.html", message="invalid username and/or password")

        # Remember which user has logged in
        session["user_id"] = rows[0]['id']
        session["username"] = request.form.get("username")

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@auth.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

@auth.route("/password", methods=["GET", "POST"])
@login_required
def password():
    """Change User Password"""

    if request.method == "POST":

        # Check user input old password
        if not request.form.get("old_password"):
            return render_template("error.html", message="must provide old password")

        # Check user input new password
        if not request.form.get("new_password"):
            return render_template("error.html", message="must provide new password")

        password = request.form.get("old_password")
        new = request.form.get("new_password")

        user_entry = data.query("SELECT * FROM users WHERE id = ?", (session["user_id"],))[0]

        # Ensure username exists and password is correct
        if not check_password_hash(user_entry['hash'], password):
            return render_template("error.html", message="incorrect password")

        confirmation = request.form.get("confirmation")

        if pwd_checks(new, confirmation):
            return render_template("error.html", message=pwd_checks(password, confirmation))

        # Updates password hash in database
        data.execute("UPDATE users SET hash = ? WHERE id = ?", (generate_password_hash(new), session["user_id"]))

        return render_template("password_changed.html")

    else:

        return render_template("password.html")
    
def pwd_checks(password, confirmation):

    # Check password is at least 8 characters
    if len(password) < MINPWDCHARS:
        return "passwords must be at least 8 characters long"

    # Check password contains at least 1 number, 1 lowercase, 1 uppercase and 1 special character
    digit, upper, special, lower = False, False, False, False
    for char in password:
        if char.isdigit():
            digit = True
        if char.isupper():
            upper = True
        if char in "!@#$%^&*()-+?_=,<>/":
            special = True
        if char.islower():
            lower = True

    if not (digit or upper or special or lower):
        return "Passwords must contain at least 1 number, 1 lowercase letter, 1 uppercase letter and 1 special character !@#$%^&*()-+?_=,<>/"

     # Check user confirmed password correctly
    if password != confirmation:
        return "passwords do not match"