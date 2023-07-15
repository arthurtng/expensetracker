from flask import Flask, redirect, session
from flask_session import Session
import datetime
from calendar import monthrange
from functools import wraps

import data

## Saves todays date to a variable
current_date = datetime.datetime.now().date()
MAXCHARS, MAXREMARKS, MINPWDCHARS = 30, 150, 8

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


def validate_asset_entry(desc, asset_type, amount, remarks, id=None):

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