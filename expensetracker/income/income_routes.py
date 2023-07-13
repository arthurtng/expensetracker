from flask import Blueprint, render_template, request, redirect, session
from werkzeug.security import check_password_hash, generate_password_hash
import data
from helpers import *

income_bp = Blueprint('income_bp', __name__)

@income_bp.route("/income", methods=["GET", "POST"])
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

@income_bp.route("/add_income", methods=["GET", "POST"])
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

@income_bp.route("/edit_income", methods=["GET", "POST"])
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


@income_bp.route("/delete_income", methods=["GET", "POST"])
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