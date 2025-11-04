import json
import os
import psycopg2
import datetime
from decimal import Decimal

def handler(event, context):
    """
    Netlify Python Function: /depositAddress
    Generates or returns a deposit address for an escrow (requires authentication via token)
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

    # Get escrow and generate deposit address
    try:
        # Check if the user is allowed to view this escrow (must be the buyer)
        cur.execute("""
            SELECT e.id, e.amount, e.payment_method, e.status
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

        escrow_id, amount, payment_method, status = escrow_result

        # Generate a mock deposit address (in a real app, this would call a payment processor API)
        if payment_method == 'bank_transfer':
            deposit_address = "BANK-ACC-1234567890"
            deposit_info = {
                "bank_name": "Vanguard Bank",
                "account_number": "1234567890",
                "routing_number": "021000021",
                "reference": f"ESCROW-{escrow_id}"
            }
        elif payment_method == 'crypto':
            deposit_address = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
            deposit_info = {
                "crypto_type": "Bitcoin",
                "network": "BTC Mainnet",
                "memo": f"ESCROW-{escrow_id}"
            }
        else:
            deposit_address = f"PAYMENT-{escrow_id}-{payment_method}"
            deposit_info = {
                "instructions": f"Send payment for escrow {escrow_id}",
                "reference": f"ESCROW-{escrow_id}"
            }

        # Convert Decimal to float for JSON serialization
        if isinstance(amount, Decimal):
            amount = float(amount)

        response_data = {
            "escrow_id": escrow_id,
            "amount": amount,
            "payment_method": payment_method,
            "deposit_address": deposit_address,
            "deposit_info": deposit_info,
            "status": status,
            "instructions": f"Send {amount} via {payment_method} to the address above"
        }

        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps(response_data)
        }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to generate deposit address", "details": str(e)})
        }
