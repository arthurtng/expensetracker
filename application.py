from flask import Flask, render_template, request, redirect, session
from flask_session import Session
import datetime
from calendar import monthrange
from functools import wraps
from werkzeug.security import check_password_hash, generate_password_hash

import data

app = Flask(__name__)
app.secret_key = 'secret'

app.config["SESSION_TYPE"] = "filesystem"
Session(app)

## Saves todays date to a variable
current_date = datetime.datetime.now().date()
MAXCHARS, MAXREMARKS, MINPWDCHARS = 30, 150, 8

'''helper functions'''

def login_required(f):
    '''
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/1.1.x/patterns/viewdecorators/
    '''
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

def check_recurring():
    #Checks recurring events and inserts into recurring table if appropriate
    current_month_start = datetime.datetime.now().strftime("%Y-%m") + '-01'

    incomeItems = data.query("SELECT * FROM income WHERE freq='monthly' AND start_date<? AND end_date>=? AND user = ?",
        (current_month_start, current_date.strftime("%Y-%m-%d"), session["user_id"]))

    for item in incomeItems:
        start_date = item['start_date']
        while start_date < current_month_start:
            formatted_start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
            new_start_date = datetime.datetime.strptime(start_date, '%Y-%m-%d').date() + datetime.timedelta(days=monthrange(formatted_start_date.year, formatted_start_date.month)[1])
            start_date = new_start_date.strftime("%Y-%m-%d")
            existing_recurring = data.query("SELECT * FROM recurring WHERE item_id=(?) AND start_date=(?) AND user = (?)", (item['id'], start_date, session["user_id"]))
            if not existing_recurring:
                data.execute("""INSERT INTO recurring (item_id, user, desc, type, amount, account, start_date, freq, remarks, date_of_entry,
                            end_date) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (item['id'], session["user_id"], item['desc'], item['type'],
                            item['amount'], item['account'], start_date, item['freq'], item['remarks'], datetime.datetime.utcnow(),
                            item['end_date']))

def check_accruals():

    #Checks marked expenses for accrual and updates assets
    income_rows = data.query("SELECT * FROM income WHERE start_date<=? AND added_account='no' AND type='income' AND user = ?",
            (current_date.strftime("%Y-%m-%d"), session["user_id"]))
    recurring_rows = data.query("SELECT * FROM recurring WHERE start_date<=? AND added_account='no' AND type='income' AND user = ?",
            (current_date.strftime("%Y-%m-%d"), session["user_id"]))
    accrued_income = income_rows + recurring_rows

    income_rows = data.query("SELECT * FROM income WHERE start_date<=? AND added_account='no' AND type='expense' AND user =?",
            (current_date.strftime("%Y-%m-%d"), session["user_id"]))
    recurring_rows = data.query("SELECT * FROM recurring WHERE start_date<=? AND added_account='no' AND type='expense' AND user =?",
            (current_date.strftime("%Y-%m-%d"), session["user_id"]))
    accrued_expense = income_rows + recurring_rows

    for income in accrued_income:
        data.execute("UPDATE assets SET amount=amount+?, edit_date=? WHERE desc=? AND user=?", (income['amount'],
                    str(datetime.datetime.utcnow()), income['account'], session["user_id"]))

    for expense in accrued_expense:
        data.execute("UPDATE assets SET amount=amount-?, edit_date=? WHERE desc=? AND user=?", (expense['amount'],
                    str(datetime.datetime.utcnow()), expense['account'], session["user_id"]))

    data.execute("UPDATE income SET added_account='yes' WHERE income.start_date<=? AND income.added_account='no' AND user=?",
                (current_date.strftime("%Y-%m-%d"), session["user_id"]))
    data.execute("UPDATE recurring SET added_account='yes' WHERE start_date<=? AND added_account='no' AND user=?",
                (current_date.strftime("%Y-%m-%d"), session["user_id"]))


def asset_checks(desc, asset_type, amount, remarks, id=None):

    # Check desc is 30 characters or less
    if len(desc) > MAXCHARS:
        return "The description must be limited to 30 characters or less."

    # Check asset type is acceptable
    if asset_type not in ["savings, checking, cash", "securities", "property", "debt"]:
        return "Asset type is not acceptable."

    # check for duplicates in desc #
    existing_accounts = data.query("SELECT * FROM assets WHERE user=?", (session["user_id"],))

    if id:
        for item in existing_accounts:
            if item['desc'] == desc and item['ID'] != id:
                return "The description cannot be the same as that of an existing asset or liability item."
    else:
        for item in existing_accounts:
            if item['desc'] == desc:
                return "The description cannot be the same as that of an existing asset or liability item."

    # Check amount is 2dp only
    if len(amount.rsplit('.')) != 1 and len(amount.rsplit('.')[-1]) > 2:
        return "Please enter amount up to 2 decimal places only."

    # Check remarks is 150 characters or less
    if len(remarks) > MAXREMARKS:
        return "The remarks must be limited to 150 characters or less."

    return None

def income_checks(desc, income_or_exp, amount, account, remarks, id=None):

    # Check desc is 30 characters or less
    if len(desc) > MAXCHARS:
        return "The description must be limited to 30 characters or less."

    # Check income type is acceptable
    if income_or_exp not in ["income", "expense"]:
        return "Item type is not acceptable."

    # Check amount is 2dp only
    if len(amount.rsplit('.')) != 1 and len(amount.rsplit('.')[-1]) > 2:
        return "Please enter amount up to 2 decimal places only."

    # Check account is savings accounts only
    account_options = []
    account_descs = data.query("SELECT desc FROM assets WHERE a_or_l='asset' AND type='savings, checking, cash' AND user=?", (session["user_id"],))
    for item in account_descs:
        account_options.append(item['desc'])
    if account not in account_options:
        return "Account must be a savings, checking, cash account."

    # Check remarks is 150 characters or less
    if remarks != None and len(remarks) > MAXREMARKS:
        return "The remarks must be limited to 150 characters or less."

    # check for duplicates in desc #
    existing_accounts = data.query("SELECT * FROM income WHERE user=?", (session["user_id"],))
    if id:
        for item in existing_accounts:
            if item['desc'] == desc and item['id'] != id:
                return "The description cannot be the same as that of an existing income or expense item."
    else:
        for item in existing_accounts:
            if item['desc'] == desc:
                return "The description cannot be the same as that of an existing income or expense item."

    # implement checks for expenses that exceed amount in account minus budgets
    budget_total = 0
    budgets = data.query("SELECT amount FROM budgets WHERE account=? AND user=?", (account, session["user_id"]))
    for budget in budgets:
        budget_total += budget['amount']
    account_balance = data.query("SELECT amount FROM assets WHERE desc=? AND user=?", (account, session["user_id"]))[0]['amount']
    if income_or_exp == "expense" and float(amount) > (account_balance - budget_total):
        return "Expense item may not exceed available balance in designated account."

    return None

def budget_checks(desc, amount, account, remarks, start, end, id=None):

    # Check desc is 30 characters or less
    if len(desc) > MAXCHARS:
        return "The description must be limited to 30 characters or less."

    # check for duplicates in desc #
    existing_budgets = data.query("SELECT * FROM budgets WHERE user=?", (session["user_id"],))

    if id:
        for item in existing_budgets:
            if item['desc'] == desc and item['id'] != id:
                return "The description cannot be the same as that of an existing budget."
    else:
        for item in existing_budgets:
            if item['desc'] == desc:
                return "The description cannot be the same as that of an existing budget."

    # Check amount is 2dp only
    if len(amount.rsplit('.')) != 1 and len(amount.rsplit('.')[-1]) > 2:
        return "Please enter amount up to 2 decimal places only."

    # Check account is savings accounts only
    account_options = []
    assets = data.query("SELECT desc FROM assets WHERE a_or_l='asset' AND type='savings, checking, cash' AND user=?", (session["user_id"],))
    for item in assets:
        account_options.append(item['desc'])
    if account not in account_options:
        return "Account must be a savings, checking, cash account."

    # Check remarks is 150 characters or less
    if len(remarks) > MAXREMARKS:
        return "The remarks must be limited to 150 characters or less."

    # Check account has enough for budget
    budget_total = 0
    budgets = data.query("SELECT amount FROM budgets WHERE account=? AND user=?", (account, session["user_id"]))
    for budget in budgets:
        budget_total += budget['amount']
    account_balance = data.query("SELECT amount FROM assets WHERE desc=? AND user=?", (account, session["user_id"]))[0]['amount']
    if float(amount) > (account_balance - budget_total):
        return "Budget amount may not exceed available balance in designated account."

    # Check end date is today or later
    if datetime.datetime.strptime(end, '%Y-%m-%d').date() < current_date:
        return "End date must be later than today."

    # Check end date is later or equal to start date
    if end < start:
        return "End date must not be earlier than start date."

    return None

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

def retrieve_items(item_list, future_items, item_sum, render_month, render_month_start, render_month_end, item_type):

    for income in data.query("SELECT * FROM income WHERE type=? AND user =?", (item_type, session["user_id"])):

        relevant_date = datetime.datetime.strptime(income['start_date'], '%Y-%m-%d').date()
        end_date = datetime.datetime.strptime(income['end_date'], '%Y-%m-%d').date()

        if relevant_date <= current_date and relevant_date >= render_month_start and relevant_date <= render_month_end:
            item_list.append(income)
            item_sum += income['amount']
        elif relevant_date > current_date and relevant_date <= render_month_end and relevant_date >= render_month_start:
            future_items.append(income)
        elif end_date >= render_month_start and relevant_date < render_month_start:
            start_month = income['start_date'][:-3]
            new_start_date = income['start_date'].replace(start_month, render_month)
            if datetime.datetime.strptime(new_start_date, '%Y-%m-%d').date() > current_date:
                future_items.append(income)
            else:
                item_list.append(income)
                item_sum += income['amount']
    return item_sum


######################################
'''main application'''


@app.route("/register", methods=["GET", "POST"])
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

@app.route("/login", methods=["GET", "POST"])
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

@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")

@app.route("/password", methods=["GET", "POST"])
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

@app.route("/")
@login_required
def index():

    check_accruals()

    income_trans = data.query("SELECT * FROM income WHERE added_account='yes' AND user =? ORDER BY start_date DESC LIMIT 10", (session["user_id"],))
    recurring_trans = data.query("SELECT * FROM recurring WHERE added_account='yes' AND user =? ORDER BY start_date DESC LIMIT 10", (session["user_id"],))
    transactions = sorted(income_trans + recurring_trans, key = lambda i: i['start_date'], reverse=True)[:10]
    assets = data.query("SELECT * FROM assets WHERE a_or_l='asset' AND user=?", (session["user_id"],))
    liabs = data.query("SELECT * FROM assets WHERE a_or_l='liability' AND user=?", (session["user_id"],))

    balance = 0
    for asset in assets:
        balance += asset['amount']
    for liab in liabs:
        balance -= liab['amount']

    for i in range(len(transactions)):
        transactions[i]['balance'] = balance
        if transactions[i]['type'] == "income":
            balance = balance - transactions[i]['amount']
        else:
            balance = balance + transactions[i]['amount']
            transactions[i]['amount'] = transactions[i]['amount'] * -1

    coordinates = transactions[::-1]
    if not transactions:
        coordinates.append({'balance': balance, 'start_date': current_date.strftime("%Y-%m-%d")})

    return render_template("index.html", transactions=transactions, coordinates=coordinates)

@app.route("/assets")
@login_required
def assets():

    ## Check recurring
    check_recurring()

    ## Update assets based on income and expenses accrued
    check_accruals()

    ## Retrieve assets and debts from asset table
    assets = data.query("SELECT * FROM assets WHERE a_or_l='asset' AND user =?", (session["user_id"],))
    liabs = data.query("SELECT * FROM assets WHERE a_or_l='liability' AND user =?", (session["user_id"],))
    budgets = data.query("SELECT * FROM budgets WHERE end_date>=? AND user = (?)", (current_date.strftime("%Y-%m-%d"), session["user_id"]))

    asset_sum = 0
    for asset in assets:
        asset_sum += asset['amount']
    liab_sum = 0
    for liab in liabs:
        liab_sum += liab['amount']
    budget_sum = 0
    for budget in budgets:
        budget_sum += budget['amount']
    nworth = asset_sum - liab_sum

    return render_template("assets.html", date=current_date, assets=assets, liabs=liabs, budgets=budgets, asset_sum=asset_sum,
            liab_sum=liab_sum, budget_sum=budget_sum, nworth=nworth)


@app.route("/add_asset", methods=["GET", "POST"])
@login_required
def add_asset():

    ## Processes form for adding asset
    if request.method == "POST":
        desc = request.form.get("desc")
        asset_or_liab = ""
        asset_type = request.form.get("type")
        amount = request.form.get("amount")
        remarks = request.form.get("remarks")

        if asset_type in ["savings, checking, cash", "securities", "property"]:
            asset_or_liab = "asset"
        else:
            asset_or_liab = "liability"

        # Checks for invalid inputs
        if asset_checks(desc, asset_type, amount, remarks):
            return render_template("error.html", message=asset_checks(desc, asset_type, amount, remarks))

        ## Adds form info into database
        data.execute("INSERT INTO assets (user, desc, type, amount, remarks, date, a_or_l) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (session["user_id"], desc, asset_type, amount, remarks, str(datetime.datetime.utcnow()), asset_or_liab))

        return redirect("/assets")

    else:

        ## Options for adding asset form
        asset_types = ["savings, checking, cash", "securities", "property", "debt"]

        return render_template("add_asset.html", asset_types=asset_types)

@app.route("/income", methods=["GET", "POST"])
@login_required
def income():

    ## Processes form for adding asset
    if request.method == "POST":
        session["request_month"] = request.form.get("month")
        return redirect("/income")

    ## Displays monthly income
    else:
        default_month = datetime.datetime.now().strftime("%Y-%m")

        # Check for requested month of report
        try:
            session["request_month"]
        except:
            render_month_start = datetime.datetime.strptime(default_month + '-01', '%Y-%m-%d').date()
            render_month = default_month
        else:
            render_month_start = datetime.datetime.strptime(session["request_month"] + '-01', '%Y-%m-%d').date()
            render_month = session["request_month"]
        finally:
            render_month_end = render_month_start.replace(day = monthrange(render_month_start.year, render_month_start.month)[1])

        ## Options for adding income form
        income_types = ["income", "expense"]
        account_options = []
        accounts = data.query("SELECT desc FROM assets WHERE a_or_l='asset' AND type='savings, checking, cash' AND user =?", (session["user_id"],))
        for acc in accounts:
            account_options.append(acc['desc'])
        freq_options = ["monthly", "one-off"]

        income_sum = 0
        income_list = []
        future_income = []

        # Retrieve income items and add to income_list
        income_sum = retrieve_items(income_list, future_income, income_sum, render_month, render_month_start, render_month_end, 'income')

        sorted_income = sorted(income_list, key = lambda i: i['start_date'])
        sorted_future_income = sorted(future_income, key = lambda i: i['start_date'])

        expenses = []
        future_expenses = []
        expense_sum = 0

        # Retrieve expense items and add to expense list
        expense_sum = retrieve_items(expenses, future_expenses, expense_sum, render_month, render_month_start, render_month_end, 'expense')

        sorted_expenses = sorted(expenses, key = lambda i: i['start_date'])
        sorted_future_expenses = sorted(future_expenses, key = lambda i: i['start_date'])

        return render_template("income.html", date=current_date, render_month=render_month, income_types=income_types, account_options=account_options, freq_options=freq_options, income_list=sorted_income, future_income=sorted_future_income, income_sum=income_sum, expenses=sorted_expenses,
        expense_sum=expense_sum, future_expenses=sorted_future_expenses, render_month_start=render_month_start, render_month_end=render_month_end)

@app.route("/add_income", methods=["GET", "POST"])
@login_required
def add_income():

    if request.method == "POST":

        desc = request.form.get("desc")
        income_or_exp = request.form.get("type")
        amount = request.form.get("amount")
        account = request.form.get("account")
        start = request.form.get("start")
        freq = request.form.get("frequency")
        remarks = request.form.get("remarks")
        end = request.form.get("end")
        perp = request.form.get("perp")

        # checks for empty fields
        if not desc or not income_or_exp or not amount or not account or not start or not freq:
            return render_template("error.html", message="Please complete all required fields.")
        if freq == "monthly" and not perp:
            return render_template("error.html", message="Please complete all required fields.")
        if perp == "specific" and not end:
            return render_template("error.html", message="Please complete all required fields.")

        # Function for checking certain requirements for income and expense items
        if income_checks(desc, income_or_exp, amount, account, remarks):
            return render_template("error.html", message=income_checks(desc, income_or_exp, amount, account, remarks))

        ## Implement end_date and ensure recurring income and expenses show up in future in income and assets ##
        if perp == "perpetual":
            end = "3000-01-01"
        if freq == "one-off":
            end = start

        # Check end date is later or equal to start date
        if end < start:
            return render_template("error.html", message="End date must not be earlier than start date.")

        ## Adds form info into database
        now = str(datetime.datetime.utcnow())
        data.execute("""INSERT INTO income (user, desc, type, amount, account, start_date, freq, remarks, date_of_entry, end_date)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", (session["user_id"], desc, income_or_exp, amount, account, start, freq, remarks,
                    now, end))

        return redirect("/income")

    else:

        ## Options for adding income form
        income_types = ["income", "expense"]
        account_options = []
        accs = data.query("SELECT desc FROM assets WHERE a_or_l='asset' AND type='savings, checking, cash' AND user=?", (session["user_id"],))

        for acc in accs:
            account_options.append(acc['desc'])
        freq_options = ["monthly", "one-off"]

        return render_template("add_income.html", income_types=income_types, account_options=account_options, freq_options=freq_options, date=current_date)

#@app.route("/budget", methods=["GET", "POST"])
@app.route("/budget")
@login_required
def budget():

    # Check accruals and updates assets
    check_accruals()

    # Options for adding budget form
    account_options = []
    accs = data.query("SELECT desc FROM assets WHERE a_or_l='asset' AND type='savings, checking, cash' AND user=?", (session["user_id"],))
    for acc in accs:
        account_options.append(acc['desc'])

    # Retrieve Total Balance from assets table
    assets = data.query("SELECT * FROM assets WHERE a_or_l='asset' AND user=?", (session["user_id"],))
    liabs = data.query("SELECT * FROM assets WHERE a_or_l='liability' AND user=?", (session["user_id"],))
    asset_sum = 0
    for asset in assets:
        asset_sum += asset['amount']
    liab_sum = 0
    for liab in liabs:
        liab_sum += liab['amount']
    total_bal = asset_sum - liab_sum

    # Retrieve budgets from budgets table
    budgets = data.query("SELECT * FROM budgets WHERE end_date>=? AND user=?", (current_date.strftime("%Y-%m-%d"), session["user_id"]))
    budget_sum = 0
    for budget in budgets:
        budget_sum += budget['amount']

    return render_template("budget.html", date=current_date, total_bal=total_bal, account_options=account_options, budgets=budgets, budget_sum=budget_sum)

@app.route("/add_budget", methods=["GET", "POST"])
@login_required
def add_budget():

    # Processes form for adding asset
    if request.method == "POST":
        desc = request.form.get("desc")
        amount = request.form.get("amount")
        account = request.form.get("account")
        start = request.form.get("start")
        end = request.form.get("end")
        remarks = request.form.get("remarks")

        # checks for empty fields
        if not desc or not amount or not account or not start or not end:
            return render_template("error.html", message="Please complete all required fields.")

        # budget specific checks
        if budget_checks(desc, amount, account, remarks, start, end):
            return render_template("error.html", message=budget_checks(desc, amount, account, remarks, start, end))

        # SQL entry from form
        data.execute("""INSERT INTO budgets (user, desc, amount, account, start_date, end_date, remarks, date_of_entry)
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?)""", (session["user_id"], desc, amount, account, start, end, remarks,
                    str(datetime.datetime.utcnow())))

        return redirect("/budget")

    else:

        # Options for adding budget form
        account_options = []
        accs = data.query("SELECT desc FROM assets WHERE a_or_l='asset' AND type='savings, checking, cash' AND user=?", (session["user_id"],))
        for acc in accs:
            account_options.append(acc['desc'])

        return render_template("add_budget.html", account_options=account_options)

@app.route("/edit_income", methods=["GET", "POST"])
@login_required
def edit_income():

    ## Generate form for editing requested item
    if request.form.get("income_item"):
        session["edit_item"] = eval(request.form.get("income_item"))

        original_item = data.query("SELECT * FROM income WHERE id=?", (session["edit_item"]['id'],))[0]

        ## Options for adding income form
        account_options = []
        accs = data.query("SELECT desc FROM assets WHERE a_or_l='asset' AND type='savings, checking, cash' AND user=?", (session["user_id"],))
        for acc in accs:
            account_options.append(acc['desc'])
        freq_options = ["monthly", "one-off"]

        if session["edit_item"]['end_date'] == "3000-01-01":
            perp = "Perpetual"
        else:
            perp = "Specific End Date"

        return render_template("edit_income.html", income=original_item, account_options=account_options, freq_options=freq_options, perp=perp)

    ## Edit income entry
    else:
        desc = request.form.get("desc")
        amount = request.form.get("amount")
        account = request.form.get("account")
        start = request.form.get("start")
        freq = request.form.get("frequency")
        remarks = request.form.get("remarks")
        end = request.form.get("end")
        perp = request.form.get("perp")

        # checks for empty fields
        if not desc or not amount or not account or not start or not freq:
            return render_template("error.html", message="Please complete all required fields.")
        if freq == "monthly" and not perp:
            return render_template("error.html", message="Please complete all required fields.")
        if perp == "specific" and not end:
            return render_template("error.html", message="Please complete all required fields.")

        # Function for checking certain requirements for income and expense items
        if income_checks(desc, session["edit_item"]['type'], amount, account, remarks, session["edit_item"]['id']):
            return render_template("error.html", message=income_checks(desc, session["edit_item"]['type'], amount,
                    account, remarks, session["edit_item"]['id']))


        ## Implement end_date and ensure recurring income and expenses show up in future in income and assets ##
        if perp == "perpetual":
            end = "3000-01-01"
        if freq == "one-off":
            end = start

        # Check end date is later or equal to start date
        if end < start:
            return render_template("error.html", message="End date must not be earlier than start date.")

        # Updates row in income table
        data.execute("""UPDATE income SET desc=(?), amount=(?), account=(?), start_date=(?), freq=(?), remarks=(?), last_edited=(?),
                    end_date=(?), added_account=(?) WHERE id=(?)""", (desc, amount, account, start, freq, remarks,
                    str(datetime.datetime.utcnow()), end, "no", session["edit_item"]['id']))

        # Removes rows in recurring table
        added = data.query("SELECT * FROM recurring WHERE item_id=(?) AND added_account=(?)", (session["edit_item"]["id"], "yes"))
        removed_amount = 0
        for item in added:
            removed_amount += item['amount']
        data.execute("DELETE FROM recurring WHERE item_id=?", (session['edit_item']['id'],))

        # Resets relevant row in asset table
        if session['edit_item']['added_account'] == "yes":
            if session['edit_item']['type'] == "income":
                removed_amount = (removed_amount + session['edit_item']['amount']) * -1
            else:
                removed_amount = removed_amount + session['edit_item']['amount']
        data.execute("UPDATE assets SET amount=amount+(?) WHERE desc=(?) AND user=(?)", (removed_amount, session['edit_item']['account'],
                    session["user_id"]))

        return redirect("/income")


@app.route("/delete_income", methods=["GET", "POST"])
@login_required
def delete_income():

    # Removes rows in recurring table
    added = data.query("SELECT * FROM recurring WHERE item_id=(?) AND added_account=(?)", (session["edit_item"]["id"], "yes"))
    removed_amount = 0
    for item in added:
        removed_amount += item['amount']

    data.execute("DELETE FROM recurring WHERE item_id=?", (session['edit_item']['id'],))

    # Resets relevant row in asset table
    if session['edit_item']['added_account'] == "yes":
        if session['edit_item']['type'] == "income":
            removed_amount = (removed_amount + session['edit_item']['amount']) * -1
        else:
            removed_amount = removed_amount + session['edit_item']['amount']

    data.execute("UPDATE assets SET amount=amount+(?) WHERE desc=(?) AND user=(?)", (removed_amount, session['edit_item']['account'],
                session["user_id"]))

    # Deletes row in income table
    data.execute("DELETE FROM income WHERE id=?", (session["edit_item"]["id"],))

    return redirect("/income")

@app.route("/edit_asset", methods=["GET", "POST"])
@login_required
def edit_asset():
    if request.form.get("asset_item"):
        session["edit_asset"] = eval(request.form.get("asset_item"))

        asset_types = ["savings, checking, cash", "securities", "property", "debt"]

        return render_template("edit_asset.html", asset=session['edit_asset'], asset_types=asset_types)

    else:
        desc = request.form.get("desc")
        asset_type = request.form.get("type")
        amount = request.form.get("amount")
        remarks = request.form.get("remarks")

        # Checks for invalid inputs
        if asset_checks(desc, asset_type, amount, remarks, session["edit_asset"]["ID"]):
            return render_template("error.html", message=asset_checks(desc, asset_type, amount, remarks, session["edit_asset"]["id"]))

        # Implement check amount must not be below income + expenses + budget relating to account
        income_items = data.query("SELECT * FROM income WHERE account=(?) AND added_account=(?) AND user=(?)", (session["edit_asset"]["desc"], "yes", session["user_id"]))
        income_total = 0
        for item in income_items:
            if item['type'] == "income":
                income_total += item['amount']
            else:
                income_total -= item['amount']

        if float(amount) < income_total:
            return render_template("error.html", message="Error: amount in account cannot be less than amount of net income input into it.")

        ## Adds form info into database
        data.execute("UPDATE assets SET desc=(?), type=(?), amount=(?), remarks=(?), edit_date=(?) WHERE ID=(?)",
                   (desc, asset_type, amount, remarks, str(datetime.datetime.utcnow()), session["edit_asset"]["ID"]))

        return redirect("/assets")


@app.route("/delete_asset", methods=["GET", "POST"])
@login_required
def delete_asset():

    # Generate delete asset form
    if request.form.get("delete_asset"):
        account_options = []
        accs = data.query("SELECT * FROM assets WHERE user=? AND type='savings, checking, cash' OR type='debt'", (session["user_id"],))

        for item in accs:
            if item['desc'] != session["edit_asset"]['desc']:
                if session["edit_asset"]['a_or_l'] == "liability" and item['type'] == "debt":
                    account_options.append(item['desc'])
                elif session["edit_asset"]['a_or_l'] == "asset" and item['type'] == "savings, checking, cash":
                    account_options.append(item['desc'])

        return render_template("delete_asset.html", asset=session["edit_asset"], account_options=account_options)

    else:

        data.execute("DELETE FROM income WHERE account=? AND user=(?)", (session["edit_asset"]['desc'], session["user_id"]))
        data.execute("DELETE FROM recurring WHERE account=? AND user=(?)", (session["edit_asset"]['desc'], session["user_id"]))
        data.execute("DELETE FROM budgets WHERE account=? AND user=(?)", (session["edit_asset"]['desc'], session["user_id"]))
        data.execute("DELETE FROM assets WHERE desc=? AND user=(?)", (session["edit_asset"]['desc'], session["user_id"]))

        return redirect("/assets")

@app.route("/transfer_asset", methods=["GET", "POST"])
@login_required
def transfer_asset():

    transfer_account = request.form.get("transfer_account")

    # Check if budgets, income, expenses all added up brings transfer account amount to subzero
    transfer_account_balance = data.query("SELECT amount FROM assets WHERE desc=? AND user=(?)", (transfer_account, session["user_id"]))
    transfer_amount = 0
    inc_rows = data.query("SELECT amount FROM income WHERE account=(?) AND type=(?) AND user=(?)", (session["edit_asset"]["desc"], 'income', session["user_id"]))
    transfer_income = inc_rows + data.query("SELECT amount FROM recurring WHERE account=(?) AND type=(?) AND user=(?)", (session["edit_asset"]["desc"], 'income', session["user_id"]))
    exp_rows = data.query("SELECT amount FROM income WHERE account=(?) AND type=(?) AND user=(?)", (session["edit_asset"]["desc"], 'expense', session["user_id"]))
    transfer_expenses = exp_rows + data.query("SELECT amount FROM recurring WHERE account=(?) AND type=(?) AND user=(?)", (session["edit_asset"]["desc"], 'expense', session["user_id"]))
    transfer_budgets = data.query("SELECT amount FROM budgets WHERE account=? AND user=(?)", (session["edit_asset"]["desc"], session["user_id"]))

    for item in transfer_income:
        transfer_amount += item['amount']
    for item in transfer_expenses:
        transfer_amount -= item['amount']
    transfer_budget = 0
    for item in transfer_budgets:
        transfer_budget -= item['amount']
    if transfer_account_balance[0]['amount'] + transfer_amount + transfer_budget < 0:
        return render_template("error.html", message="Cannot transfer to new account as the budget and income items would bring the balance of the new account to below zero.")
    adjustment = 0
    if session["edit_asset"]['amount'] > transfer_amount:
        adjustment = session["edit_asset"]['amount'] - transfer_amount

    # Update all budgets, income, expenses to new account and added_account to no
    data.execute("UPDATE income SET account=(?), added_account='no' WHERE account=(?) AND user=(?)", (transfer_account,
                session["edit_asset"]["desc"], session["user_id"]))
    data.execute("UPDATE recurring SET account=(?), added_account='no' WHERE account=(?) AND user=(?)", (transfer_account,
                session["edit_asset"]["desc"], session["user_id"]))
    data.execute("UPDATE budgets SET account=(?) WHERE account=(?) AND user=(?)", (transfer_account, session["edit_asset"]["desc"],
                session["user_id"]))

    new_bal = float(data.query("SELECT amount FROM assets WHERE desc=? AND user=?", (transfer_account, session["user_id"]))[0]['amount'])

    data.execute("UPDATE assets SET amount=? WHERE desc=? AND user=?", (new_bal + adjustment, transfer_account, session["user_id"]))

    # Delete acc from assets
    data.execute("DELETE FROM assets WHERE desc=? AND user=(?)", (session["edit_asset"]["desc"], session["user_id"]))

    return redirect("/assets")

@app.route("/edit_budget", methods=["GET", "POST"])
@login_required
def edit_budget():
    if request.form.get("budget_item"):

        account_options = []
        accs = data.query("SELECT desc FROM assets WHERE a_or_l='asset' AND type='savings, checking, cash' AND user=(?)", (session["user_id"],))
        for item in accs:
            account_options.append(item['desc'])

        session["edit_budget"] = eval(request.form.get("budget_item"))

        return render_template("edit_budget.html", budget=session["edit_budget"], account_options=account_options)

    else:

        desc = request.form.get("desc")
        amount = request.form.get("amount")
        account = request.form.get("account")
        start = request.form.get("start")
        end = request.form.get("end")
        remarks = request.form.get("remarks")

        # implement checks for empty fields
        if not desc or not amount or not account or not start or not end:
            return render_template("error.html", message="Please complete all required fields.")

        # budget specific checks
        adjusted_amount = float(amount) - float(data.query("SELECT amount FROM budgets WHERE id=?", (session["edit_budget"]["id"],))[0]['amount'])
        if budget_checks(desc, str(adjusted_amount), account, remarks, start, end, session["edit_budget"]["id"]):
            return render_template("error.html", message=budget_checks(desc, amount, account, remarks, start, end, session["edit_budget"]["id"]))

        data.execute("UPDATE budgets SET desc=?, amount=?, account=?, start_date=?, end_date=?, remarks=? WHERE id=? AND user=?",
                    (desc, amount, account, start, end, remarks, session["edit_budget"]["id"], session["user_id"]))

        return redirect("/budget")

@app.route("/delete_budget", methods=["GET", "POST"])
@login_required
def delete_budget():

    data.execute("DELETE FROM budgets WHERE id=?", (session["edit_budget"]["id"],))

    return redirect("/budget")

@app.route("/resolve_budget", methods=["GET", "POST"])
@login_required
def resolve_budget():

    if request.form.get("budget_item"):

        session["resolve_budget"] = eval(request.form.get("budget_item"))

        return render_template("resolve_budget.html", budget=session["resolve_budget"])

    else:

        spent_amount = float(request.form.get("newamount"))

        account_balance = data.query("SELECT amount FROM assets WHERE desc=? AND user=?", (session["resolve_budget"]['account'], session["user_id"]))[0]['amount']

        if spent_amount > account_balance:
            return render_template("error.html", message="Amount spent cannot exceed account balance.")

        else:
            new_amount = account_balance - spent_amount

            data.execute("UPDATE assets SET amount=? WHERE desc=? AND user=?", (new_amount, session["resolve_budget"]["account"], session["user_id"]))
            data.execute("INSERT INTO resolved_budgets SELECT * FROM budgets WHERE id=?", (session["resolve_budget"]["id"],))
            data.execute("DELETE FROM budgets WHERE id=?", (session["resolve_budget"]["id"],))

            return redirect("/budget")

