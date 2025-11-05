import json
import os
import psycopg2
import datetime

def handler(event, context):
    """POST /.netlify/functions/depositDone"""

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
            SELECT u.id, u.role
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
        
        user_id, role = user_result
        user = {"id": user_id, "role": role}

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Token validation failed", "details": str(e)})
        }

    # Check if user is buyer
    if user["role"] != "buyer":
        cur.close()
        conn.close()
        return {"statusCode": 403, "body": json.dumps({"error": "Only buyers can confirm deposit"})}

    # Parse request
    try:
        data = json.loads(event.get("body", "{}"))
        escrow_id = data.get("escrowId")
        if not escrow_id:
            cur.close()
            conn.close()
            return {"statusCode": 400, "body": json.dumps({"error": "escrowId is required"})}
    except Exception:
        cur.close()
        conn.close()
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON"})}

    # Update escrow status
    try:
        cur.execute("""
            UPDATE escrows 
            SET status = 'funds_in_escrow', 
                updated_at = %s 
            WHERE id = %s AND buyer_id = %s AND status = 'pending_deposit'
        """, (datetime.datetime.utcnow(), escrow_id, user["id"]))
        
        if cur.rowcount == 0:
            cur.close()
            conn.close()
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Escrow not found or already confirmed"})
            }
        
        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Deposit confirmed successfully"})
        }

    except Exception as e:
        print("DB error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database operation failed", "details": str(e)})}
