import os
import json
import psycopg2
import datetime
import base64

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
        escrow_id = body.get("escrowId")
        delivery_terms = body.get("deliveryTerms", "")
        deliverable_content = body.get("deliverableContent", "")
        attachments = body.get("attachments", [])
        if not escrow_id:
            cur.close()
            conn.close()
            return {"statusCode": 400, "body": json.dumps({"error": "escrowId is required"})}
    except Exception:
        cur.close()
        conn.close()
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON input"})}

    # Process delivery submission
    try:
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
        """, (delivery_terms, deliverable_content, datetime.datetime.utcnow(), datetime.datetime.utcnow(), escrow_id))

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
            """, (escrow_id, filename, datetime.datetime.utcnow()))

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
