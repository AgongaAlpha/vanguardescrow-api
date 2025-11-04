import json
import os
import psycopg2
import datetime
from decimal import Decimal

def handler(event, context):
    """
    Netlify Python Function: /sellerMyEscrows
    Returns the current seller's escrows (requires authentication via token)
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

        # Check if the user is a seller
        if role != 'seller':
            cur.close()
            conn.close()
            return {
                "statusCode": 403,
                "body": json.dumps({"error": "Only sellers can access this endpoint"})
            }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Token validation failed", "details": str(e)})
        }

    # Get seller's escrows
    try:
        cur.execute("""
            SELECT id, amount, payment_method, status, created_at 
            FROM escrows 
            WHERE seller_id = %s
        """, (user_id,))

        escrows = cur.fetchall()
        escrows_list = []
        for escrow in escrows:
            # Convert Decimal to float for JSON serialization
            amount = escrow[1]
            if isinstance(amount, Decimal):
                amount = float(amount)

            escrows_list.append({
                "id": escrow[0],
                "amount": amount,
                "payment_method": escrow[2],
                "status": escrow[3],
                "created_at": escrow[4].isoformat() if escrow[4] else None,
            })

        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({
                "escrows": escrows_list
            })
        }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to get escrows", "details": str(e)})
        }
