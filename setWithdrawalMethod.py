import json
import os
import psycopg2
import datetime

def handler(event, context):
    """
    POST /.netlify/functions/setWithdrawalMethod
    Body JSON:
    {
      "method_code": "USDT_TRC20",
      "details": {
        "address": "T123ExampleAddress",
        "note": "Send only USDT on TRC20"
      }
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
        method_code = body.get("method_code")
        details = body.get("details")
        if not method_code or not details:
            return {"statusCode": 400, "body": json.dumps({"error": "method_code and details are required"})}
    except Exception:
        return {"statusCode": 400, "body": json.dumps({"error": "Invalid JSON input"})}

    # Set withdrawal method
    try:
        # Check if user already has a method set
        cur.execute("SELECT id FROM seller_withdrawal_methods WHERE user_id = %s;", (user["id"],))
        existing = cur.fetchone()

        if existing:
            # Update existing record
            cur.execute("""
                UPDATE seller_withdrawal_methods
                SET method_code = %s,
                    details = %s::jsonb,
                    updated_at = %s
                WHERE user_id = %s;
            """, (method_code, json.dumps(details), datetime.datetime.utcnow(), user["id"]))
        else:
            # Insert new record
            cur.execute("""
                INSERT INTO seller_withdrawal_methods (user_id, method_code, details, created_at)
                VALUES (%s, %s, %s::jsonb, %s);
            """, (user["id"], method_code, json.dumps(details), datetime.datetime.utcnow()))

        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "message": "Withdrawal method saved successfully",
                "method_code": method_code
            })
        }

    except Exception as e:
        print("DB error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database operation failed", "details": str(e)})}
