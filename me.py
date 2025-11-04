import json
import os
import psycopg2
import datetime

def handler(event, context):
    """
    Netlify Python Function: /me
    Returns information about the currently logged-in user
    based on their session cookie.
    """

    # Get cookies from headers
    headers = event.get("headers", {}) or {}
    cookie_header = headers.get("cookie") or headers.get("Cookie") or ""
    cookies = {}

    for item in cookie_header.split(";"):
        if "=" in item:
            name, value = item.strip().split("=", 1)
            cookies[name] = value

    session_token = cookies.get("session")

    if not session_token:
        return {
            "statusCode": 401,
            "body": json.dumps({"error": "No session token found"})
        }

    # Connect to Neon database
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            sslmode="require"
        )
        cur = conn.cursor()
    except Exception as e:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Database connection failed", "details": str(e)})
        }

    # Verify session token and return user info
    try:
        cur.execute("""
            SELECT u.id, u.name, u.email, u.role, s.expires_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = %s;
        """, (session_token,))
        row = cur.fetchone()

        if not row:
            cur.close()
            conn.close()
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid or expired session"})
            }

        user_id, name, email, role, expires_at = row

        # Check expiration
        if expires_at and expires_at < datetime.datetime.utcnow():
            # Session expired, delete it
            cur.execute("DELETE FROM sessions WHERE session_token = %s;", (session_token,))
            conn.commit()
            cur.close()
            conn.close()
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Session expired"})
            }

        cur.close()
        conn.close()

        # Return user info
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({
                "id": user_id,
                "name": name,
                "email": email,
                "role": role
            })
        }

    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error fetching user info", "details": str(e)})
        }
