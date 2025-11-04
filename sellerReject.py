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
    POST /.netlify/functions/sellerReject
    Input: { "escrowId": 123, "reason": "Out of stock or wrong details" }
    Effect: Marks escrow as rejected and records reason
    """
    headers = event.get("headers", {}) or {}
    user = get_session_user(headers)
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "seller":
        return {"statusCode": 403, "body": json.dumps({"error": "Only sellers allowed"})}

    try:
        body = json.loads(event.get("body") or "{}")
        escrow_id = body.get("escrowId")
        reason = body.get("reason", "").strip()
        if not escrow_id:
            return {"statusCode": 400, "body": json.dumps({"error": "escrowId is required"})}
        if not reason:
            reason = "Seller rejected without specified reason"
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

        # Verify the escrow belongs to this seller and is not already confirmed/rejected
        cur.execute("SELECT status FROM escrows WHERE id = %s AND seller_id = %s;", (escrow_id, user["id"]))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return {"statusCode": 404, "body": json.dumps({"error": "Escrow not found for this seller"})}

        current_status = row[0]
        if current_status in ("rejected", "cancelled", "confirmed", "released"):
            cur.close()
            conn.close()
            return {"statusCode": 400, "body": json.dumps({"error": f"Cannot reject escrow in status {current_status}"})}

        # Update escrow record
        cur.execute("""
            UPDATE escrows
            SET status = 'rejected',
                seller_reject_reason = %s,
                updated_at = %s
            WHERE id = %s;
        """, (reason, datetime.utcnow(), escrow_id))

        # Log rejection in transactions
        cur.execute("""
            INSERT INTO transactions (escrow_id, type, description)
            VALUES (%s, 'reject', %s);
        """, (escrow_id, f"Seller rejected escrow: {reason}"))

        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Escrow rejected successfully",
                "escrow_id": escrow_id,
                "status": "rejected"
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
