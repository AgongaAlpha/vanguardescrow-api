import json
import os
import psycopg2
import datetime
from decimal import Decimal

def handler(event, context):
    """
    Netlify Python Function: /getEscrow
    Returns detailed information for a specific escrow (requires authentication via token)
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

    # Get escrow_id from query string parameters
    query_params = event.get('queryStringParameters', {})
    escrow_id = query_params.get('escrow_id')

    if not escrow_id:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing escrow_id parameter"})
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

    # Get escrow details
    try:
        # Check if the user is allowed to view this escrow (either buyer or seller)
        cur.execute("""
            SELECT e.id, e.amount, e.payment_method, e.status, e.created_at,
                   u_buyer.email as buyer_email, u_seller.email as seller_email
            FROM escrows e
            JOIN users u_buyer ON e.buyer_id = u_buyer.id
            JOIN users u_seller ON e.seller_id = u_seller.id
            WHERE e.id = %s AND (e.buyer_id = %s OR e.seller_id = %s)
        """, (escrow_id, user_id, user_id))

        escrow_result = cur.fetchone()
        if not escrow_result:
            cur.close()
            conn.close()
            return {
                "statusCode": 404,
                "body": json.dumps({"error": "Escrow not found or access denied"})
            }

        # Convert Decimal to float for JSON serialization
        amount = escrow_result[1]
        if isinstance(amount, Decimal):
            amount = float(amount)

        escrow_details = {
            "id": escrow_result[0],
            "amount": amount,
            "payment_method": escrow_result[2],
            "status": escrow_result[3],
            "created_at": escrow_result[4].isoformat() if escrow_result[4] else None,
            "buyer_email": escrow_result[5],
            "seller_email": escrow_result[6]
        }

        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps(escrow_details)
        }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to get escrow details", "details": str(e)})
        }
