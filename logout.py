import json
import os
import psycopg2
from http import cookies
from datetime import datetime, timedelta


def handler(event, context):
    """POST /.netlify/functions/logout — destroy session and clear cookie"""

    cookie_header = event.get("headers", {}).get("cookie") or event.get("headers", {}).get("Cookie") or ""
    cookie_obj = cookies.SimpleCookie()
    cookie_obj.load(cookie_header)

    session_token = None
    if "session" in cookie_obj:
        session_token = cookie_obj["session"].value

    # Connect to DB
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            sslmode="require"
        )
        cur = conn.cursor()
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Database connection failed", "details": str(e)})
        }

    try:
        if session_token:
            cur.execute("DELETE FROM sessions WHERE session_token = %s;", (session_token,))
            conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to destroy session", "details": str(e)})
        }

    # Clear cookie
    expired_cookie = cookies.SimpleCookie()
    expired_cookie["session"] = ""
    expired_cookie["session"]["path"] = "/"
    expired_cookie["session"]["httponly"] = True
    expired_cookie["session"]["expires"] = (datetime.utcnow() - timedelta(days=1)).strftime("%a, %d-%b-%Y %H:%M:%S GMT")

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Set-Cookie": expired_cookie.output(header='', sep=''),
        },
        "body": json.dumps({"message": "Logged out successfully."})
    }
