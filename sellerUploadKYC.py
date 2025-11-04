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
    POST /.netlify/functions/sellerUploadKYC
    Input JSON example:
    {
        "kyc_type": "ID Verification",
        "attachments": [
            {"filename": "id_front.png", "content": "<base64string>"},
            {"filename": "id_back.png", "content": "<base64string>"}
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
        kyc_type = body.get("kyc_type", "General Verification")
        attachments = body.get("attachments", [])
        if not attachments:
            return {"statusCode": 400, "body": json.dumps({"error": "No attachments provided"})}
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

        # Create a KYC submission record
        cur.execute("""
            INSERT INTO kyc_submissions (user_id, kyc_type, status, submitted_at)
            VALUES (%s, %s, 'pending', %s)
            RETURNING id;
        """, (user["id"], kyc_type, datetime.utcnow()))
        kyc_id = cur.fetchone()[0]

        # Save each uploaded file
        for file in attachments:
            filename = file.get("filename")
            content_b64 = file.get("content")
            if not filename or not content_b64:
                continue
            path = f"/tmp/{filename}"
            with open(path, "wb") as f:
                f.write(base64.b64decode(content_b64))

            # Store record in DB
            cur.execute("""
                INSERT INTO escrow_files (escrow_id, file_name, purpose, uploaded_at)
                VALUES (NULL, %s, 'kyc', %s);
            """, (filename, datetime.utcnow()))

        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "KYC documents uploaded successfully",
                "kyc_id": kyc_id,
                "status": "pending"
            })
        }

    except Exception as e:
        print("KYC upload error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database operation failed", "details": str(e)})}
