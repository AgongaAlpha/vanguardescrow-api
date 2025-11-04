import json
import os
import psycopg2
import hashlib
import re

def handler(event, context):
    """
    Netlify Python Function: /signup
    Handles new user registration for Vanguard Escrow.
    """

    # Parse request body
    try:
        data = json.loads(event.get("body", "{}"))
        name = data.get("name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        role = data.get("role", "").strip().lower()
    except Exception as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON body", "details": str(e)})
        }

    # Simple validation
    if not name or not email or not password or not role:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "All fields are required"})
        }

    if role not in ["buyer", "seller"]:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid role. Must be buyer or seller"})
        }

    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid email format"})
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

    # Check if email already exists
    try:
        cur.execute("SELECT id FROM users WHERE email = %s;", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return {
                "statusCode": 409,
                "body": json.dumps({"error": "Email already registered"})
            }
    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Error checking user existence", "details": str(e)})
        }

    # Hash password (SHA256)
    password_hash = hashlib.sha256(password.encode()).hexdigest()

    # Insert new user
    try:
        cur.execute(
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
            """,
            (name, email, password_hash, role)
        )
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Database insert failed", "details": str(e)})
        }

    # Success response
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "message": "Signup successful",
            "user_id": user_id,
            "role": role
        })
    }
