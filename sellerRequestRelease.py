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
    POST /.netlify/functions/sellerRequestRelease
    Input JSON:
    {
        "escrowId": 123,
        "note": "Please release payment, delivery completed successfully"
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
        escrow_id = body.get("escrowId")
        note = body.get("note", "")
        if not escrow_id:
            return {"statusCode": 400, "body": json.dumps({"error": "escrowId is required"})}
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

        # Verify escrow belongs to seller and has been delivered
        cur.execute("SELECT status FROM escrows WHERE id = %s AND seller_id = %s;", (escrow_id, user["id"]))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return {"statusCode": 404, "body": json.dumps({"error": "Escrow not found for this seller"})}

        current_status = row[0]
        if current_status not in ("delivered", "confirmed", "paid"):
            cur.close()
            conn.close()
            return {"statusCode": 400, "body": json.dumps({"error": f"Cannot request release in status {current_status}"})}

        # Update escrow record
        cur.execute("""
            UPDATE escrows
            SET status = 'release_requested',
                seller_request_time = %s,
                updated_at = %s
            WHERE id = %s;
        """, (datetime.utcnow(), datetime.utcnow(), escrow_id))

        # Insert into transactions for traceability
        cur.execute("""
            INSERT INTO transactions (escrow_id, type, description)
            VALUES (%s, 'release_request', %s);
        """, (escrow_id, note or "Seller requested payment release"))

        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Payment release requested successfully",
                "status": "release_requested"
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
