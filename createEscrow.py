import json
import os
import psycopg2
from http import cookies

def get_session_user(headers):
    """Helper to extract logged-in user ID and role from the session cookie."""
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
        print("Session check failed:", e)
        return None


def handler(event, context):
    """POST /.netlify/functions/createEscrow"""

    # Parse request body
    try:
        data = json.loads(event.get("body", "{}"))
    except Exception:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON body"})
        }

    # Required fields
    seller_id = data.get("seller_id")
    amount = data.get("amount")
    payment_method = data.get("paymentMethod", "").strip()
    preferred_wallet = data.get("preferred_wallet", "").strip()
    agreement = data.get("agreement", "").strip()

    # Validate input
    if not amount or not payment_method:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required fields (amount, paymentMethod)"})
        }

    # Get session user
    user = get_session_user(event.get("headers", {}))
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "buyer":
        return {"statusCode": 403, "body": json.dumps({"error": "Only buyers can create escrows"})}

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
        cur.execute(
            """
            INSERT INTO escrows (buyer_id, seller_id, amount, payment_method, payment_details, agreement, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                user["id"],
                seller_id,
                amount,
                payment_method,
                preferred_wallet,
                agreement,
                "pending"
            )
        )
        escrow_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Escrow created successfully",
                "escrow_id": escrow_id
            })
        }

    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to create escrow", "details": str(e)})
        }
