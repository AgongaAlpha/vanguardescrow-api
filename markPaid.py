import json
import os
import psycopg2
from http import cookies
from datetime import datetime

def get_session_user(headers):
    """Validate session cookie and return user id + role"""
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
    """POST /.netlify/functions/markPaid"""

    # Authenticate user
    user = get_session_user(event.get("headers", {}))
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "buyer":
        return {"statusCode": 403, "body": json.dumps({"error": "Only buyers can mark escrow as paid"})}

    # Parse request
    try:
        data = json.loads(event.get("body", "{}"))
        escrow_id = data.get("escrow_id")
        tx_id = data.get("tx_id", "").strip()
        proof_url = data.get("proof_url", "").strip()
        note = data.get("note", "").strip()
    except Exception:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON body"})}

    if not escrow_id:
        return {"statusCode": 400, "body": json.dumps({"error": "Missing escrow_id"})}

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

    try:
        # Verify escrow belongs to buyer
        cur.execute("SELECT id, status FROM escrows WHERE id = %s AND buyer_id = %s;", (escrow_id, user["id"]))
        escrow = cur.fetchone()
        if not escrow:
            cur.close()
            conn.close()
            return {"statusCode": 403, "body": json.dumps({"error": "Escrow not found or not owned by you"})}

        # Update escrow status to payment pending confirmation
        cur.execute("""
            UPDATE escrows
            SET status = %s,
                buyer_tx_id = %s,
                buyer_proof_url = %s,
                buyer_note = %s,
                paid_at = %s
            WHERE id = %s;
        """, (
            "payment_pending_confirmation",
            tx_id or None,
            proof_url or None,
            note or None,
            datetime.utcnow(),
            escrow_id
        ))
        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Escrow marked as paid. Awaiting seller confirmation.",
                "escrow_id": escrow_id,
                "status": "payment_pending_confirmation"
            })
        }

    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to update escrow", "details": str(e)})
        }
