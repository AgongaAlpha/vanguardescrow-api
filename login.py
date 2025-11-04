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

    print("=== LOGIN DEBUG START ===")
    
    # Parse incoming JSON
    try:
        data = json.loads(event.get("body", "{}"))
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        print(f"Login attempt for: {email}")
    except Exception as e:
        print(f"JSON parse error: {e}")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON body", "details": str(e)})
        }

    if not email or not password:
        print("Missing email or password")
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Email and password required"})
        }

    # Connect to Neon DB using ONLY DATABASE_URL
    try:
        database_url = os.getenv("DATABASE_URL")
        print(f"DATABASE_URL exists: {bool(database_url)}")
        if not database_url:
            return {
                "statusCode": 500,
                "body": json.dumps({"error": "DATABASE_URL environment variable not set"})
            }
        
        conn = psycopg2.connect(database_url)
        cur = conn.cursor()
        print("Database connection successful")
    except Exception as e:
        print(f"Database connection failed: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Database connection failed", "details": str(e)})
        }

    # Check user credentials
    try:
        # Using auth0_sub column to store password_hash
        cur.execute("SELECT id, auth0_sub, role FROM users WHERE email = %s;", (email,))
        row = cur.fetchone()
        print(f"User query result: {row}")
        
        if not row:
            cur.close()
            conn.close()
            print("User not found")
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid email or password"})
            }

        user_id, stored_hash, role = row
        given_hash = hashlib.sha256(password.encode()).hexdigest()
        print(f"Password match: {stored_hash == given_hash}")

        if stored_hash != given_hash:
            cur.close()
            conn.close()
            print("Password mismatch")
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid email or password"})
            }

        # Create session token
        session_token = secrets.token_hex(32)
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=1)
        print(f"Generated session token: {session_token}")

        # Store session in DB
        try:
            cur.execute("""
                INSERT INTO sessions (user_id, session_token, expires_at)
                VALUES (%s, %s, %s);
            """, (user_id, session_token, expires_at))
            conn.commit()
            print("Session stored in database")
        except Exception as insert_error:
            print(f"Session insert failed: {insert_error}")
            conn.rollback()
            raise insert_error

        cur.close()
        conn.close()

        # Return success with Set-Cookie header
        print("Returning success response with cookie")
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
               "Set-Cookie": f"session={session_token}; Path=/; Max-Age=86400; SameSite=None; Secure"
            },
            "body": json.dumps({
                "message": "Login successful",
                "role": role
            })
        }

    except Exception as e:
        print(f"Login process error: {e}")
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Login failed", "details": str(e)})
        }

