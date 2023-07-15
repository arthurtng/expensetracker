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

    asset_sum = sum(asset['amount'] for asset in assets)
    liab_sum = sum(liab['amount'] for liab in liabs)
    budget_sum = sum(budget['amount'] for budget in budgets)
    net_worth = asset_sum - liab_sum

    return render_template("assets.html", date=current_date, assets=assets, liabs=liabs, budgets=budgets, asset_sum=asset_sum,
            liab_sum=liab_sum, budget_sum=budget_sum, net_worth=net_worth)


@asset.route("/add_asset", methods=["GET", "POST"])
@login_required
def add_asset():
    ## Processes form for adding asset
    if request.method == "POST":
        desc, asset_type, amount, remarks = request.form.get("desc"), request.form.get("type"), request.form.get("amount"), request.form.get("remarks")
                       
        if asset_type in ["savings, checking, cash", "securities", "property"]:
            asset_or_liab = "asset" 
        else:
            asset_or_liab = "liability" 

        validation_result = validate_asset_entry(desc, asset_type, amount, remarks)
        if validation_result: 
            return render_template("error.html", message=validation_result)
        
        data.execute("INSERT INTO assets (user, desc, type, amount, remarks, date, a_or_l) VALUES(?, ?, ?, ?, ?, ?, ?)",
                (session["user_id"], desc, asset_type, amount, remarks, str(datetime.datetime.utcnow()), asset_or_liab))
        return redirect("/assets")

    else:        
        asset_types = ["savings, checking, cash", "securities", "property", "debt"]
        return render_template("add_asset.html", asset_types=asset_types)
    

@asset.route("/edit_asset", methods=["GET", "POST"])
@login_required
def edit_asset():
    if request.form.get("asset_item"):
        session["edit_asset"] = eval(request.form.get("asset_item"))        
        return render_template("edit_asset.html", asset=session['edit_asset'], asset_types=["savings, checking, cash", "securities", "property", "debt"])

    else:
        desc, asset_type, amount, remarks = request.form.get("desc"), request.form.get("type"), request.form.get("amount"), request.form.get("remarks")        
        
        # Checks for invalid inputs
        validation_result = validate_asset_entry(desc, asset_type, amount, remarks, session["edit_asset"]["ID"])
        if validation_result: 
            return render_template("error.html", message=validation_result)
        
        # Implement check amount must not be below income + expenses + budget relating to account     
        income_total = calculate_income_for_account(session["edit_asset"]["desc"])
        if float(amount) < income_total:
            return render_template("error.html", message="Error: amount in account cannot be less than amount of net income input into it.")
        
        data.execute("UPDATE assets SET desc=(?), type=(?), amount=(?), remarks=(?), edit_date=(?) WHERE ID=(?)",
                   (desc, asset_type, amount, remarks, str(datetime.datetime.utcnow()), session["edit_asset"]["ID"]))
        return redirect("/assets")
    

@asset.route("/delete_asset", methods=["GET", "POST"])
@login_required
def delete_asset():
    # Generate delete asset form
    if request.form.get("delete_asset"):
        if session["edit_asset"]['a_or_l'] == "liability":
            accounts = data.query("SELECT desc FROM assets WHERE user=(?) AND desc!=(?) AND type='debt'", 
                              (session["user_id"], session["edit_asset"]['desc']))
        if session["edit_asset"]['a_or_l'] == "asset":
            accounts = data.query("SELECT desc FROM assets WHERE user=(?) AND desc!=(?) AND type='savings, checking, cash'", 
                              (session["user_id"], session["edit_asset"]['desc']))        
        account_options = [account['desc'] for account in accounts]    
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
    old_account = session["edit_asset"]

    transfer_account_balance = data.query("SELECT amount FROM assets WHERE desc=? AND user=(?)", (transfer_account, session["user_id"]))
    transfer_amount, transfer_budget = calculate_old_income_expenses_budgets(old_account)
    
    if not is_transfer_account_above_zero_after_transfer(transfer_account_balance, transfer_amount, transfer_budget):
        return render_template("error.html", message="Cannot transfer to new account as the budget and income items would bring the balance of the new account to below zero.")
    
    old_account_leftover_amount_after_income_items = 0
    if old_account['amount'] > transfer_amount:
        old_account_leftover_amount_after_income_items = old_account['amount'] - transfer_amount

    transfer_asset_in_db(transfer_account, old_account, old_account_leftover_amount_after_income_items)

    return redirect("/assets")


################################################################################


def calculate_old_income_expenses_budgets(old_account):
    # Check if budgets, income, expenses all added up brings transfer account amount to subzero   
    old_account_name = old_account["desc"] 
    transfer_amount = 0
    inc_rows = data.query("SELECT amount FROM income WHERE account=(?) AND type=(?) AND user=(?)", (old_account_name, 'income', session["user_id"]))
    transfer_income = inc_rows + data.query("SELECT amount FROM recurring WHERE account=(?) AND type=(?) AND user=(?)", (old_account_name, 'income', session["user_id"]))
    exp_rows = data.query("SELECT amount FROM income WHERE account=(?) AND type=(?) AND user=(?)", (old_account_name, 'expense', session["user_id"]))
    transfer_expenses = exp_rows + data.query("SELECT amount FROM recurring WHERE account=(?) AND type=(?) AND user=(?)", (old_account_name, 'expense', session["user_id"]))
    transfer_budgets = data.query("SELECT amount FROM budgets WHERE account=? AND user=(?)", (old_account_name, session["user_id"]))
    
    for item in transfer_income: transfer_amount += item['amount']
    for item in transfer_expenses: transfer_amount -= item['amount']
    transfer_budget = 0
    for item in transfer_budgets: transfer_budget -= item['amount']

    return transfer_amount, transfer_budget


def is_transfer_account_above_zero_after_transfer(transfer_account_balance, transfer_amount, transfer_budget):
    return transfer_account_balance[0]['amount'] + transfer_amount + transfer_budget >= 0


def transfer_asset_in_db(transfer_account, old_account, old_account_leftover_amount_after_income_items):
    # Update all budgets, income, expenses to new account and added_account to no
    data.execute("UPDATE income SET account=(?), added_account='no' WHERE account=(?) AND user=(?)", (transfer_account,
                old_account["desc"], session["user_id"]))
    data.execute("UPDATE recurring SET account=(?), added_account='no' WHERE account=(?) AND user=(?)", (transfer_account,
                old_account["desc"], session["user_id"]))
    data.execute("UPDATE budgets SET account=(?) WHERE account=(?) AND user=(?)", (transfer_account, old_account["desc"],
                session["user_id"]))

    new_balance = float(data.query("SELECT amount FROM assets WHERE desc=? AND user=?", (transfer_account, session["user_id"]))[0]['amount'])
    data.execute("UPDATE assets SET amount=? WHERE desc=? AND user=?", (new_balance + old_account_leftover_amount_after_income_items, transfer_account, session["user_id"]))

    # Delete acc from assets
    data.execute("DELETE FROM assets WHERE desc=? AND user=(?)", (old_account["desc"], session["user_id"]))


def calculate_income_for_account(account):
    income_items = data.query("SELECT SUM(amount) AS amount FROM income WHERE account=(?) AND added_account=(?) AND user=(?) AND type=(?)", 
                                  (account, "yes", session["user_id"], "income"))[0]
    expense_items = data.query("SELECT SUM(amount) AS amount FROM income WHERE account=(?) AND added_account=(?) AND user=(?) AND type=(?)", 
                                (account, "yes", session["user_id"], "expense"))[0]        
    return income_items['amount'] - expense_items['amount']