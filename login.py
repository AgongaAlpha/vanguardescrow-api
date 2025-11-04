import json
import os
import psycopg2
import hashlib
import secrets
import datetime

def handler(event, context):
    """
    Netlify Python Function: /login
    Handles secure user login for Vanguard Escrow.
    """

    # Parse incoming JSON
    try:
        data = json.loads(event.get("body", "{}"))
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
    except Exception as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON body", "details": str(e)})
        }

    if not email or not password:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Email and password required"})
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

    # Check user credentials
    try:
        # Using auth0_sub column to store password_hash
        cur.execute("SELECT id, auth0_sub, role FROM users WHERE email = %s;", (email,))
        row = cur.fetchone()
        if not row:
            cur.close()
            conn.close()
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid email or password"})
            }

        user_id, stored_hash, role = row
        given_hash = hashlib.sha256(password.encode()).hexdigest()

        if stored_hash != given_hash:
            cur.close()
            conn.close()
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid email or password"})
            }

        # Create session token
        session_token = secrets.token_hex(32)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=1)

        # Store session in DB
        cur.execute("""
            INSERT INTO sessions (user_id, session_token, expires_at)
            VALUES (%s, %s, %s);
        """, (user_id, session_token, expires_at))
        conn.commit()
        cur.close()
        conn.close()

        # Return success with token in response body
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json"
            },
            "body": json.dumps({
                "message": "Login successful",
                "role": role,
                "token": session_token  # ← Token in response body
            })
        }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Login failed", "details": str(e)})
        }
