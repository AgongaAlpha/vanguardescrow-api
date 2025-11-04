import json
import os
import psycopg2
from http import cookies

def get_session_user(headers):
    cookie_header = headers.get("cookie") or headers.get("Cookie") or ""
    cookie_obj = cookies.SimpleCookie()
    cookie_obj.load(cookie_header)
    token = cookie_obj.get("session").value if "session" in cookie_obj else None
    if not token:
        return None
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
            SELECT u.id, u.role, u.name, u.email
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = %s;
        """, (token,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "role": row[1], "name": row[2], "email": row[3]}
    except Exception as e:
        print("session error:", e)
        return None


def handler(event, context):
    """
    GET /.netlify/functions/sellerMyEscrows
    Returns a list of all escrows belonging to the logged-in seller
    Optional query params: ?status=pending&limit=50&offset=0
    """
    headers = event.get("headers", {}) or {}
    user = get_session_user(headers)
    if not user:
        return {"statusCode": 401, "body": json.dumps({"error": "Not authenticated"})}
    if user["role"] != "seller":
        return {"statusCode": 403, "body": json.dumps({"error": "Only sellers allowed"})}

    qs = event.get("queryStringParameters") or {}
    status = qs.get("status")
    limit = int(qs.get("limit", 50))
    offset = int(qs.get("offset", 0))

    try:
        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASS"),
            sslmode="require"
        )
        cur = conn.cursor()

        if status:
            cur.execute("""
                SELECT e.id, e.amount, e.status, e.created_at, e.updated_at,
                       e.buyer_id, u.name AS buyer_name, u.email AS buyer_email
                FROM escrows e
                LEFT JOIN users u ON e.buyer_id = u.id
                WHERE e.seller_id = %s AND e.status = %s
                ORDER BY e.created_at DESC
                LIMIT %s OFFSET %s;
            """, (user["id"], status, limit, offset))
        else:
            cur.execute("""
                SELECT e.id, e.amount, e.status, e.created_at, e.updated_at,
                       e.buyer_id, u.name AS buyer_name, u.email AS buyer_email
                FROM escrows e
                LEFT JOIN users u ON e.buyer_id = u.id
                WHERE e.seller_id = %s
                ORDER BY e.created_at DESC
                LIMIT %s OFFSET %s;
            """, (user["id"], limit, offset))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        escrows = []
        for r in rows:
            escrows.append({
                "id": r[0],
                "amount": float(r[1]) if r[1] else None,
                "status": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
                "updated_at": r[4].isoformat() if r[4] else None,
                "buyer_id": r[5],
                "buyer_name": r[6],
                "buyer_email": r[7]
            })

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"escrows": escrows})
        }

    except Exception as e:
        print("DB error:", e)
        try:
            cur.close()
            conn.close()
        except:
            pass
        return {"statusCode": 500, "body": json.dumps({"error": "Database query failed", "details": str(e)})}
