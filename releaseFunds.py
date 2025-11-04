import json
import os
import psycopg2
import datetime
from decimal import Decimal

def handler(event, context):
    """
    Netlify Python Function: /releaseFunds
    Releases escrow funds to the seller (requires authentication via token)
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

    # Release funds to seller
    try:
        # Get escrow details and verify user has permission (must be the buyer)
        cur.execute("""
            SELECT e.id, e.amount, e.status, e.seller_id
            FROM escrows e
            WHERE e.id = %s AND e.buyer_id = %s
        """, (escrow_id, user_id))

        escrow_result = cur.fetchone()
        if not escrow_result:
            cur.close()
            conn.close()
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Escrow not found or access denied"})
            }

        escrow_id, amount, status, seller_id = escrow_result
        
        # Check if escrow is in the correct status to release funds
        if status != 'paid':
            cur.close()
            conn.close()
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Escrow must be in 'paid' status to release funds. Current status: {status}"})
            }

        # Update escrow status to 'released'
        cur.execute("""
            UPDATE escrows 
            SET status = 'released', updated_at = %s
            WHERE id = %s
        """, (datetime.datetime.utcnow(), escrow_id))

        # Update seller's balance (add the escrow amount)
        cur.execute("""
            UPDATE users 
            SET balance = balance + %s
            WHERE id = %s
        """, (amount, seller_id))

        # Get the new seller balance for the response
        cur.execute("SELECT balance FROM users WHERE id = %s", (seller_id,))
        new_seller_balance = cur.fetchone()[0]
        
        conn.commit()
        cur.close()
        conn.close()

        # Convert Decimal to float for JSON serialization
        if isinstance(amount, Decimal):
            amount = float(amount)
        if isinstance(new_seller_balance, Decimal):
            new_seller_balance = float(new_seller_balance)

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "message": "Funds released to seller successfully",
                "escrow_id": escrow_id,
                "amount_released": amount,
                "seller_id": seller_id,
                "new_seller_balance": new_seller_balance,
                "previous_status": status,
                "new_status": "released"
            })
        }

    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to release funds", "details": str(e)})
        }
