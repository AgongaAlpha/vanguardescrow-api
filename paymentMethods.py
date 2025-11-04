import json
import os
import psycopg2

def handler(event, context):
    """
    GET /.netlify/functions/paymentMethods
    Returns all active payment/withdrawal methods from the database.
    """
    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            sslmode="require"
        )
        cur = conn.cursor()

        cur.execute("""
            SELECT code, label, details
            FROM payment_methods
            WHERE active = TRUE
            ORDER BY id ASC;
        """)

        rows = cur.fetchall()
        cur.close()
        conn.close()

        methods = []
        for r in rows:
            methods.append({
                "code": r[0],
                "label": r[1],
                "details": r[2]
            })

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"methods": methods})
        }

    except Exception as e:
        print("DB error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database query failed", "details": str(e)})}
