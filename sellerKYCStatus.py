import json
import os
import psycopg2
import datetime

def handler(event, context):
    """
    GET /.netlify/functions/sellerKYCStatus
    Returns seller's most recent KYC submission and status.
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

    # Get KYC status
    try:
        # Get most recent KYC submission for this seller
        cur.execute("""
            SELECT id, kyc_type, status, admin_note, submitted_at, reviewed_at
            FROM kyc_submissions
            WHERE user_id = %s
            ORDER BY submitted_at DESC
            LIMIT 1;
        """, (user["id"],))

        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"message": "No KYC submission found", "kyc": None})
            }

        kyc = {
            "id": row[0],
            "kyc_type": row[1],
            "status": row[2],
            "admin_note": row[3],
            "submitted_at": row[4].isoformat() if row[4] else None,
            "reviewed_at": row[5].isoformat() if row[5] else None
        }

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"kyc": kyc})
        }

    except Exception as e:
        print("DB error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database query failed", "details": str(e)})}
