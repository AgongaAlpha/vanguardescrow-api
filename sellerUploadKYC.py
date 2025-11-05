import os
import json
import psycopg2
import datetime
import base64

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

    # Get token from Authorization header
    headers = event.get('headers', {})
    auth_header = headers.get('authorization', '') or headers.get('Authorization', '')
    
    if not auth_header or not auth_header.startswith('Bearer '):
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "Missing or invalid authorization header"})
        }
    
    token = auth_header.replace('Bearer ', '').strip()

    # Connect to Neon DB using DATABASE_URL
    try:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "DATABASE_URL environment variable not set"})
            }
        
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Database connection failed", "details": str(e)})
        }

    # Validate token and get user info
    try:
        cur.execute("""
            SELECT u.id, u.role, u.name, u.email
            FROM sessions s 
            JOIN users u ON s.user_id = u.id 
            WHERE s.session_token = %s AND s.expires_at > %s
        """, (token, datetime.datetime.utcnow()))
        
        user_result = cur.fetchone()
        if not user_result:
            cur.close()
            conn.close()
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid or expired token"})
            }
        
        user_id, role, name, email = user_result
        user = {"id": user_id, "role": role, "name": name, "email": email}

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Token validation failed", "details": str(e)})
        }

    # Check if user is seller
    if user["role"] != "seller":
        cur.close()
        conn.close()
        return {"statusCode": 403, "body": json.dumps({"error": "Only sellers allowed"})}

    # Parse request body
    try:
        body = json.loads(event.get("body") or "{}")
        kyc_type = body.get("kyc_type", "General Verification")
        attachments = body.get("attachments", [])
        if not attachments:
            cur.close()
            conn.close()
            return {"statusCode": 400, "body": json.dumps({"error": "No attachments provided"})}
    except Exception:
        cur.close()
        conn.close()
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON input"})}

    # Process KYC upload
    try:
        # Create a KYC submission record
        cur.execute("""
            INSERT INTO kyc_submissions (user_id, kyc_type, status, submitted_at)
            VALUES (%s, %s, 'pending', %s)
            RETURNING id;
        """, (user["id"], kyc_type, datetime.datetime.utcnow()))
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
            """, (filename, datetime.datetime.utcnow()))

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
