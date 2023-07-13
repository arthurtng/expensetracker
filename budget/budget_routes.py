from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import check_password_hash, generate_password_hash
import data
from helpers import *

budget_bp = Blueprint('budget_bp', __name__)

@budget_bp.route("/budget")
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

@budget_bp.route("/add_budget", methods=["GET", "POST"])
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

@budget_bp.route("/edit_budget", methods=["GET", "POST"])
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

@budget_bp.route("/delete_budget", methods=["GET", "POST"])
@login_required
def delete_budget():

    data.execute("DELETE FROM budgets WHERE id=?", (session["edit_budget"]["id"],))

    return redirect("/budget")

@budget_bp.route("/resolve_budget", methods=["GET", "POST"])
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