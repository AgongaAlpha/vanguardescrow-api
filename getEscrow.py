import json
import os
import psycopg2
from http import cookies

def get_session_user(headers):
    """Extracts user ID & role from session cookie."""
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
    """GET /.netlify/functions/getEscrow?id=<escrow_id>"""

    # Authenticate user
    user = get_session_user(event.get("headers", {}))
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "buyer":
        return {"statusCode": 403, "body": json.dumps({"error": "Only buyers can view escrow details"})}

    # Extract escrow ID
    query_params = event.get("queryStringParameters") or {}
    escrow_id = query_params.get("id")

    if not escrow_id:
        return {"statusCode": 400, "body": json.dumps({"error": "Missing escrow ID"})}

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

    try:
        # Fetch escrow info (only if belongs to buyer)
        cur.execute("""
            SELECT e.id, e.amount, e.payment_method, e.payment_details, e.status,
                   e.created_at, e.updated_at,
                   e.seller_id, u.name AS seller_name, u.email AS seller_email
            FROM escrows e
            LEFT JOIN users u ON e.seller_id = u.id
            WHERE e.id = %s AND e.buyer_id = %s;
        """, (escrow_id, user["id"]))
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return {"statusCode": 404, "body": json.dumps({"error": "Escrow not found"})}

        escrow_data = {
            "id": row[0],
            "amount": float(row[1]),
            "payment_method": row[2],
            "payment_details": row[3],
            "status": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "updated_at": row[6].isoformat() if row[6] else None,
            "seller_id": row[7],
            "seller_name": row[8],
            "seller_email": row[9]
        }

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(escrow_data)
        }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to retrieve escrow details", "details": str(e)})
        }
