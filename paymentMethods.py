import json
import os
import psycopg2

def handler(event, context):
    """
    Netlify Python Function: /paymentMethods
    Returns available payment methods (may require database connection for dynamic methods)
    """

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

    # Try to get payment methods from database, or return static list if table doesn't exist
    try:
        # Example: Query a table named 'payment_methods' if it exists
        cur.execute("SELECT method_name, description, is_active FROM payment_methods WHERE is_active = true;")
        methods = cur.fetchall()
        payment_methods = []
        for method in methods:
            payment_methods.append({
                "method": method[0],
                "description": method[1],
                "is_active": method[2]
            })

        cur.close()
        conn.close()

        # If no payment methods found in database, return a default list
        if not payment_methods:
            payment_methods = [
                {
                    "method": "bank_transfer",
                    "description": "Bank Transfer",
                    "is_active": True
                },
                {
                    "method": "crypto",
                    "description": "Cryptocurrency",
                    "is_active": True
                }
            ]

        return {
            "statusCode": 200,
            "body": json.dumps({
                "payment_methods": payment_methods
            })
        }

    except Exception as e:
        # If there's an error (like table doesn't exist), return a default list
        try:
            cur.close()
            conn.close()
        except:
            pass

        # Return static payment methods
        payment_methods = [
            {
                "method": "bank_transfer",
                "description": "Bank Transfer",
                "is_active": True
            },
            {
                "method": "crypto",
                "description": "Cryptocurrency",
                "is_active": True
            }
        ]

        return {
            "statusCode": 200,
            "body": json.dumps({
                "payment_methods": payment_methods
            })
        }
