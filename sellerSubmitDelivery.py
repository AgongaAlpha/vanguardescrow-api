import os
import json
import psycopg2
from http import cookies
from datetime import datetime
import base64

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
    POST /.netlify/functions/sellerSubmitDelivery
    Content-Type: application/json
    Body: {
        "escrowId": 123,
        "deliveryTerms": "Work completed as per agreement",
        "deliverableContent": "Summary of delivery",
        "attachments": [
            {"filename": "proof.png", "content": "<base64string>"},
            {"filename": "contract.pdf", "content": "<base64string>"}
        ]
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
        delivery_terms = body.get("deliveryTerms", "")
        deliverable_content = body.get("deliverableContent", "")
        attachments = body.get("attachments", [])
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

        # Verify the escrow belongs to this seller
        cur.execute("SELECT id, status FROM escrows WHERE id = %s AND seller_id = %s;", (escrow_id, user["id"]))
        escrow = cur.fetchone()
        if not escrow:
            cur.close()
            conn.close()
            return {"statusCode": 404, "body": json.dumps({"error": "Escrow not found for this seller"})}

        current_status = escrow[1]
        if current_status not in ("confirmed", "paid", "awaiting_delivery"):
            cur.close()
            conn.close()
            return {"statusCode": 400, "body": json.dumps({"error": f"Cannot submit delivery in status {current_status}"})}

        # Update delivery info
        cur.execute("""
            UPDATE escrows
            SET seller_terms = %s,
                seller_deliverables = %s,
                status = 'delivered',
                delivered_at = %s,
                updated_at = %s
            WHERE id = %s;
        """, (delivery_terms, deliverable_content, datetime.utcnow(), datetime.utcnow(), escrow_id))

        # Insert attachments if any
        for file in attachments:
            filename = file.get("filename")
            content_b64 = file.get("content")
            if not filename or not content_b64:
                continue
            # Save to /tmp temporarily (Netlify runtime)
            path = f"/tmp/{filename}"
            with open(path, "wb") as f:
                f.write(base64.b64decode(content_b64))
            # Record file metadata
            cur.execute("""
                INSERT INTO escrow_files (escrow_id, file_name, purpose, uploaded_at)
                VALUES (%s, %s, 'delivery', %s);
            """, (escrow_id, filename, datetime.utcnow()))

        # Record transaction
        cur.execute("""
            INSERT INTO transactions (escrow_id, type, description)
            VALUES (%s, 'delivery', 'Seller submitted delivery');
        """, (escrow_id,))

        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Delivery submitted successfully", "status": "delivered"})
        }

    except Exception as e:
        print("delivery error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database operation failed", "details": str(e)})}
