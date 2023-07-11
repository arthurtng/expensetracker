from flask import Flask, render_template, request, redirect, session
from flask_session import Session
import datetime
from calendar import monthrange
from werkzeug.security import check_password_hash, generate_password_hash

import data
from helpers import *
from auth import auth_routes
from assets import asset_routes

app = Flask(__name__)
app.register_blueprint(auth_routes.auth)
app.register_blueprint(asset_routes.asset)

app.secret_key = 'secret'

app.config["SESSION_TYPE"] = "filesystem"
Session(app)

## Saves todays date to a variable
current_date = datetime.datetime.now().date()

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

