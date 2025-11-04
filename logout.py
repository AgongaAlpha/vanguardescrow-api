import json
import os
import psycopg2

def handler(event, context):
    """
    Netlify Python Function: /logout
    Handles user logout by invalidating the session token.
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

    # Delete the session
    try:
        cur.execute("DELETE FROM sessions WHERE session_token = %s;", (token,))
        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "message": "Logout successful"
            })
        }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Logout failed", "details": str(e)})
        }
