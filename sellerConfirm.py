import json
import os
import psycopg2
import datetime

def handler(event, context):
    """
    POST /.netlify/functions/sellerConfirm
    Input: { "escrowId": 123 }
    Effect: Marks escrow as confirmed by seller
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
        if not escrow_id:
            cur.close()
            conn.close()
            return {"statusCode": 400, "body": json.dumps({"error": "escrowId is required"})}
    except Exception:
        cur.close()
        conn.close()
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON input"})}

    # Process seller confirmation
    try:
        # Verify the escrow belongs to this seller
        cur.execute("SELECT status FROM escrows WHERE id = %s AND seller_id = %s;", (escrow_id, user["id"]))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return {"statusCode": 404, "body": json.dumps({"error": "Escrow not found for this seller"})}

        current_status = row[0]
        if current_status not in ("pending", "awaiting_confirmation"):
            cur.close()
            conn.close()
            return {"statusCode": 400, "body": json.dumps({"error": f"Cannot confirm escrow in status {current_status}"})}

        # Update escrow
        cur.execute("""
            UPDATE escrows
            SET status = 'confirmed',
                seller_confirmed_at = %s,
                updated_at = %s
            WHERE id = %s;
        """, (datetime.datetime.utcnow(), datetime.datetime.utcnow(), escrow_id))

        # Log transaction for traceability
        cur.execute("""
            INSERT INTO transactions (escrow_id, type, amount, description)
            SELECT id, 'confirm', amount, 'Seller confirmed escrow'
            FROM escrows WHERE id = %s;
        """, (escrow_id,))

        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"message": "Escrow confirmed successfully", "escrow_id": escrow_id, "status": "confirmed"})
        }

    except Exception as e:
        print("DB error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database operation failed", "details": str(e)})}
