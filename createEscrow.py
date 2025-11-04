import json
import os
import psycopg2
import datetime

def handler(event, context):
    """
    Netlify Python Function: /createEscrow
    Creates a new escrow transaction (requires authentication via token)
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
        amount = data.get("amount")
        paymentMethod = data.get("paymentMethod")
        seller_email = data.get("seller_email")
    except Exception as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON body", "details": str(e)})
        }

    # Validate required fields
    if not amount or not paymentMethod or not seller_email:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Missing required fields (amount, paymentMethod, seller_email)"})
        }

    # Connect to Neon DB
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
            SELECT u.id, u.email, u.role 
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
        
        user_id, user_email, user_role = user_result
        
        # Check if user is a buyer
        if user_role != 'buyer':
            cur.close()
            conn.close()
            return {
                "statusCode": 403,
                "body": json.dumps({"error": "Only buyers can create escrows"})
            }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Token validation failed", "details": str(e)})
        }

    # Create escrow
    try:
        # Check if seller exists
        cur.execute("SELECT id FROM users WHERE email = %s AND role = 'seller'", (seller_email,))
        seller_result = cur.fetchone()
        if not seller_result:
            cur.close()
            conn.close()
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Seller not found or not a seller"})
            }
        
        seller_id = seller_result[0]

        # Insert escrow (without currency column)
        cur.execute("""
            INSERT INTO escrows (buyer_id, seller_id, amount, payment_method, status)
            VALUES (%s, %s, %s, %s, 'pending')
            RETURNING id;
        """, (user_id, seller_id, amount, paymentMethod))
        
        escrow_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "message": "Escrow created successfully",
                "escrow_id": escrow_id,
                "buyer_email": user_email,
                "seller_email": seller_email,
                "amount": amount,
                "payment_method": paymentMethod
            })
        }

    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to create escrow", "details": str(e)})
        }
