import json
import os
import psycopg2
import datetime
from decimal import Decimal

def handler(event, context):
    """
    Netlify Python Function: /markPaid
    Marks an escrow as paid (requires authentication via token)
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

    # Parse request body
    try:
        data = json.loads(event.get("body", "{}"))
        escrow_id = data.get("escrow_id")
    except Exception as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON body", "details": str(e)})
        }

    if not escrow_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing escrow_id"})
        }

    # Connect to Neon DB using ONLY DATABASE_URL
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

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Token validation failed", "details": str(e)})
        }

    # Mark escrow as paid
    try:
        # Check if the user is allowed to mark this escrow as paid (must be the buyer)
        cur.execute("""
            SELECT id, status 
            FROM escrows 
            WHERE id = %s AND buyer_id = %s
        """, (escrow_id, user_id))

        escrow_result = cur.fetchone()
        if not escrow_result:
            cur.close()
            conn.close()
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Escrow not found or access denied"})
            }

        current_status = escrow_result[1]
        
        # Check if escrow is already paid or completed
        if current_status in ['paid', 'completed', 'released']:
            cur.close()
            conn.close()
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Escrow is already {current_status}"})
            }

        # Update escrow status to 'paid'
        cur.execute("""
            UPDATE escrows 
            SET status = 'paid', updated_at = %s
            WHERE id = %s
        """, (datetime.datetime.utcnow(), escrow_id))
        
        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "message": "Escrow marked as paid successfully",
                "escrow_id": escrow_id,
                "previous_status": current_status,
                "new_status": "paid"
            })
        }

    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to mark escrow as paid", "details": str(e)})
        }
