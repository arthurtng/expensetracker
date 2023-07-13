from flask import Blueprint, render_template, request, redirect, session
import data
from helpers import *

asset = Blueprint('asset', __name__)

@asset.route("/assets")
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


@asset.route("/add_asset", methods=["GET", "POST"])
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
    
@asset.route("/edit_asset", methods=["GET", "POST"])
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


@asset.route("/delete_asset", methods=["GET", "POST"])
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

@asset.route("/transfer_asset", methods=["GET", "POST"])
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