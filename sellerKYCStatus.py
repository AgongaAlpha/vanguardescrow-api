import json
import os
import psycopg2
from http import cookies

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
    GET /.netlify/functions/sellerKYCStatus
    Returns seller's most recent KYC submission and status.
    """
    headers = event.get("headers", {}) or {}
    user = get_session_user(headers)
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "seller":
        return {"statusCode": 403, "body": json.dumps({"error": "Only sellers allowed"})}

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            sslmode="require"
        )
        cur = conn.cursor()

        # Get most recent KYC submission for this seller
        cur.execute("""
            SELECT id, kyc_type, status, admin_note, submitted_at, reviewed_at
            FROM kyc_submissions
            WHERE user_id = %s
            ORDER BY submitted_at DESC
            LIMIT 1;
        """, (user["id"],))

        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"message": "No KYC submission found", "kyc": None})
            }

        kyc = {
            "id": row[0],
            "kyc_type": row[1],
            "status": row[2],
            "admin_note": row[3],
            "submitted_at": row[4].isoformat() if row[4] else None,
            "reviewed_at": row[5].isoformat() if row[5] else None
        }

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"kyc": kyc})
        }

    except Exception as e:
        print("DB error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database query failed", "details": str(e)})}
