import json
import os
import psycopg2
import hashlib
import secrets
import datetime

def handler(event, context):
    """
    Netlify Python Function: /signup
    Handles user registration for Vanguard Escrow.
    """

    # Parse incoming JSON
    try:
        data = json.loads(event.get("body", "{}"))
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")
        name = data.get("name", "")
        role = data.get("role", "").lower()
    except Exception as e:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid JSON body", "details": str(e)})
        }

    # Validate required fields
    if not email or not password or not name or not role:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "All fields are required"})
        }

    if role not in ["buyer", "seller"]:
        return {
            "statusCode": 400,
            "body": json.dumps({"error": "Invalid role. Must be buyer or seller"})
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

    # Check if user already exists and create new user
    try:
        # Check if email already exists
        cur.execute("SELECT id FROM users WHERE email = %s;", (email,))
        if cur.fetchone():
            cur.close()
            conn.close()
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "User already exists"})
            }

        # Create password hash
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        # Insert new user
        cur.execute("""
            INSERT INTO users (email, password_hash, name, role)
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """, (email, password_hash, name, role))
        
        user_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "message": "User created successfully",
                "user_id": user_id
            })
        }

    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Signup failed", "details": str(e)})
        }
