from flask import Flask, render_template, request, redirect, session
from flask_session import Session
import datetime
from calendar import monthrange
from werkzeug.security import check_password_hash, generate_password_hash

import data
from helpers import *
from auth import auth_routes
from assets import asset_routes
from income import income_routes
from budget import budget_routes

app = Flask(__name__)
app.register_blueprint(auth_routes.auth)
app.register_blueprint(asset_routes.asset)
app.register_blueprint(income_routes.income_bp)
app.register_blueprint(budget_routes.budget_bp)

app.secret_key = 'secret'

app.config["SESSION_TYPE"] = "filesystem"
Session(app)

## Saves todays date to a variable
current_date = datetime.datetime.now().date()

@app.route("/")
@login_required
def index():
    check_accruals()    
    
    assets = data.query("SELECT * FROM assets WHERE a_or_l='asset' AND user=?", (session["user_id"],))
    liabs = data.query("SELECT * FROM assets WHERE a_or_l='liability' AND user=?", (session["user_id"],))    
    transactions = get_transactions()
    
    balance = get_balance(assets, liabs, transactions)
    coordinates = calculate_coordinates(transactions, balance)
    return render_template("index.html", transactions=transactions, coordinates=coordinates)


def get_transactions():
    income_trans = data.query("SELECT * FROM income WHERE added_account='yes' AND user =? ORDER BY start_date DESC LIMIT 10", (session["user_id"],))
    recurring_trans = data.query("SELECT * FROM recurring WHERE added_account='yes' AND user =? ORDER BY start_date DESC LIMIT 10", (session["user_id"],))
    return sorted(income_trans + recurring_trans, key = lambda i: i['start_date'], reverse=True)[:10]


def get_balance(assets, liabs, transactions):
    balance = 0    
    for asset in assets: balance += asset['amount']
    for liab in liabs: balance -= liab['amount']  
    for i in range(len(transactions)):
        transactions[i]['balance'] = balance
        if transactions[i]['type'] == "income":
            balance = balance - transactions[i]['amount']
        else:
            balance = balance + transactions[i]['amount']
            transactions[i]['amount'] = transactions[i]['amount'] * -1
    return balance


def calculate_coordinates(transactions, balance):
    coordinates = transactions[::-1]
    if not transactions:
        coordinates.append({'balance': balance, 'start_date': current_date.strftime("%Y-%m-%d")})
    return coordinates

