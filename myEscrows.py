import json
import os
import psycopg2
from http import cookies

def get_session_user(headers):
    """Extracts and validates the session cookie."""
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
    """GET /.netlify/functions/myEscrows — returns all escrows for the logged-in buyer."""

    # Authenticate session
    user = get_session_user(event.get("headers", {}))
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "buyer":
        return {"statusCode": 403, "body": json.dumps({"error": "Only buyers can view their escrows"})}

    # Parse query params (optional filters)
    query_params = event.get("queryStringParameters") or {}
    status_filter = query_params.get("status")
    limit = int(query_params.get("limit", 50))
    offset = int(query_params.get("offset", 0))

    # Connect to Neon DB
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

    # Build query
    try:
        if status_filter:
            cur.execute("""
                SELECT e.id, e.amount, e.payment_method, e.status, e.created_at,
                       e.seller_id, u.name AS seller_name
                FROM escrows e
                LEFT JOIN users u ON e.seller_id = u.id
                WHERE e.buyer_id = %s AND e.status = %s
                ORDER BY e.created_at DESC
                LIMIT %s OFFSET %s;
            """, (user["id"], status_filter, limit, offset))
        else:
            cur.execute("""
                SELECT e.id, e.amount, e.payment_method, e.status, e.created_at,
                       e.seller_id, u.name AS seller_name
                FROM escrows e
                LEFT JOIN users u ON e.seller_id = u.id
                WHERE e.buyer_id = %s
                ORDER BY e.created_at DESC
                LIMIT %s OFFSET %s;
            """, (user["id"], limit, offset))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        escrows = []
        for r in rows:
            escrows.append({
                "id": r[0],
                "amount": float(r[1]),
                "payment_method": r[2],
                "status": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
                "seller_id": r[5],
                "seller_name": r[6]
            })

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"escrows": escrows})
        }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to fetch escrows", "details": str(e)})
        }
