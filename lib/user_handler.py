import logging

from flask import session
from werkzeug.security import check_password_hash

module_logger = logging.getLogger('icad_cap_alerts.users')


def authenticate_user(db, username, password):
    query = f"SELECT password FROM users WHERE username = ?"
    params = (username,)
    user_result = db.execute_query(query, params, fetch_mode='one')

    if not user_result.get("success") or not user_result.get("result"):
        return {"success": False, "message": "Invalid Username or Password"}

    if not check_password_hash(user_result["result"]["password"], password):
        return {"success": False, "message": "Invalid Username or Password"}

    session['logged_in'] = True
    session['user'] = username

    return {"success": True, "message": "Authenticated"}
