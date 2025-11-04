import json
import os
import psycopg2
from http import cookies
from datetime import datetime

def get_session_user(headers):
    cookie_header = headers.get("cookie") or headers.get("Cookie") or ""
    cookie_obj = cookies.SimpleCookie()
    cookie_obj.load(cookie_header)
    token = cookie_obj.get("session").value if "session" in cookie_obj else None
    if not token:
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
            SELECT u.id, u.role, u.name, u.email
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = %s;
        """, (token,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "role": row[1], "name": row[2], "email": row[3]}
    except Exception as e:
        print("session error:", e)
        return None


def handler(event, context):
    """
    POST /.netlify/functions/setWithdrawalMethod
    Body JSON:
    {
      "method_code": "USDT_TRC20",
      "details": {
        "address": "T123ExampleAddress",
        "note": "Send only USDT on TRC20"
      }
    }
    """
    headers = event.get("headers", {}) or {}
    user = get_session_user(headers)
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "seller":
        return {"statusCode": 403, "body": json.dumps({"error": "Only sellers allowed"})}

    try:
        body = json.loads(event.get("body") or "{}")
        method_code = body.get("method_code")
        details = body.get("details")
        if not method_code or not details:
            return {"statusCode": 400, "body": json.dumps({"error": "method_code and details are required"})}
    except Exception:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON input"})}

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            sslmode="require"
        )
        cur = conn.cursor()

        # Check if user already has a method set
        cur.execute("SELECT id FROM seller_withdrawal_methods WHERE user_id = %s;", (user["id"],))
        existing = cur.fetchone()

        if existing:
            # Update existing record
            cur.execute("""
                UPDATE seller_withdrawal_methods
                SET method_code = %s,
                    details = %s::jsonb,
                    updated_at = %s
                WHERE user_id = %s;
            """, (method_code, json.dumps(details), datetime.utcnow(), user["id"]))
        else:
            # Insert new record
            cur.execute("""
                INSERT INTO seller_withdrawal_methods (user_id, method_code, details, created_at)
                VALUES (%s, %s, %s::jsonb, %s);
            """, (user["id"], method_code, json.dumps(details), datetime.utcnow()))

        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Withdrawal method saved successfully",
                "method_code": method_code
            })
        }

    except Exception as e:
        print("DB error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database operation failed", "details": str(e)})}
