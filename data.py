import sqlite3

DB_PATH = "records.db"


# Simplifies querying database and returns list of rows as dicts
def query(sql, parameters=()):
    try:
        con = sqlite3.connect(DB_PATH)
        con.row_factory = sqlite3.Row
        rawResult = con.execute(sql, parameters).fetchall()
        result = [{i: item[i] for i in item.keys()} for item in rawResult]
        return result
    except Exception as e:
        print("Error, failed to execute query " + sql)
        return []
    finally:
        con.close()


# Simplifies execution of SQL
def execute(sql, parameters=()):
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        with con:
            cur.execute(sql, parameters)
    except Exception as e:
        print("Error, failed to execute SQL " + sql)
        return

