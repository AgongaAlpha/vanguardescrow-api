import json
import os
import psycopg2
from http import cookies
from datetime import datetime, timedelta

def get_session_user(headers):
    """Get logged-in user via session cookie."""
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
    """POST /.netlify/functions/depositAddress"""

    # Authenticate user
    user = get_session_user(event.get("headers", {}))
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "buyer":
        return {"statusCode": 403, "body": json.dumps({"error": "Only buyers can view deposit details"})}

    # Parse request body
    try:
        data = json.loads(event.get("body", "{}"))
        escrow_id = data.get("escrow_id")
        payment_method = data.get("method", "").strip()
    except Exception:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON body"})}

    if not escrow_id or not payment_method:
        return {"statusCode": 400, "body": json.dumps({"error": "Missing escrow_id or method"})}

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
        return {"statusCode": 500, "body": json.dumps({"error": "DB connection failed", "details": str(e)})}

    # Validate escrow ownership
    try:
        cur.execute("SELECT id FROM escrows WHERE id = %s AND buyer_id = %s;", (escrow_id, user["id"]))
        escrow = cur.fetchone()
        if not escrow:
            cur.close()
            conn.close()
            return {"statusCode": 403, "body": json.dumps({"error": "Escrow not found or not owned by you"})}
    except Exception as e:
        cur.close()
        conn.close()
        return {"statusCode": 500, "body": json.dumps({"error": "Error validating escrow", "details": str(e)})}

    # Fetch deposit info
    try:
        cur.execute("SELECT label, details FROM payment_methods WHERE code = %s AND active = TRUE;", (payment_method,))
        pm = cur.fetchone()
        if pm:
            label = pm[0]
            details = pm[1]
        else:
            # fallback (for testing)
            label = payment_method
            details = {"address": "TExampleWalletAddress12345", "note": "Send only USDT TRC20"}

        # Assign expiry (optional, 1 hour)
        expires_at = (datetime.utcnow() + timedelta(hours=1)).isoformat() + "Z"

        # Update escrow record
        cur.execute("""
            UPDATE escrows
            SET deposit_address = %s, payment_details = %s, status = %s
            WHERE id = %s;
        """, (details.get("address") if isinstance(details, dict) else None,
              json.dumps(details),
              "awaiting_deposit",
              escrow_id))
        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "escrow_id": escrow_id,
                "payment_method": label,
                "address": details.get("address") if isinstance(details, dict) else None,
                "note": details.get("note") if isinstance(details, dict) else None,
                "expires_at_
