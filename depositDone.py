import json
import os
import psycopg2
from http import cookies
from datetime import datetime


def get_session_user(headers):
    """Retrieve user info from session cookie."""
    cookie_header = headers.get("cookie") or headers.get("Cookie") or ""
    cookie_obj = cookies.SimpleCookie()
    cookie_obj.load(cookie_header)

    session_token = None
    if "session" in cookie_obj:
        session_token = cookie_obj["session"].value

    if not session_token:
        return None

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            sslmode="require"
        )
        cur = conn.cursor()
        cur.execute("""
            SELECT u.id, u.role
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = %s;
        """, (session_token,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        if not user:
            return None
        return {"id": user[0], "role": user[1]}
    except Exception as e:
        print("Session validation failed:", e)
        return None


def handler(event, context):
    """POST /.netlify/functions/depositDone"""

    # Authenticate
    user = get_session_user(event.get("headers", {}))
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "buyer":
        return {"statusCode": 403, "body": json.dumps({"error": "Only buyers can confirm deposit"})}

    # Parse request
    try:
        data = json.loads(event.get("body", "{}"))
        escrow_id = data.get("escrowId")
    except Exception:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON
