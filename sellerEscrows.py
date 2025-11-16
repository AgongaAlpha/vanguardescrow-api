import os
import json
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor

def handler(event, context):
    """
    Get all escrows for the authenticated seller
    """
    try:
        # Get authorization header
        headers = event.get('headers', {})
        auth_header = headers.get('authorization') or headers.get('Authorization')
        
        if not auth_header or not auth_header.startswith('Bearer '):
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Unauthorized'})
            }
        
        token = auth_header.replace('Bearer ', '')
        
        # Connect to database
        conn = psycopg2.connect(os.environ['DATABASE_URL'])
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Verify token and get seller_id
        cur.execute("""
            SELECT id, role FROM users 
            WHERE auth_token = %s
        """, (token,))
        
        user = cur.fetchone()
        
        if not user:
            cur.close()
            conn.close()
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Invalid token'})
            }
        
        if user['role'] != 'seller':
            cur.close()
            conn.close()
            return {
                'statusCode': 403,
                'body': json.dumps({'error': 'Access denied. Seller role required.'})
            }
        
        seller_id = user['id']
        
        # Get all escrows for this seller
        cur.execute("""
            SELECT 
                e.id,
                e.amount,
                e.status,
                e.payment_method as wallet,
                e.created_at,
                e.seller_confirmed_at,
                e.paid_at,
                e.released_at,
                u.email as buyer_email
            FROM escrows e
            LEFT JOIN users u ON e.buyer_id = u.id
            WHERE e.seller_id = %s
            ORDER BY e.created_at DESC
        """, (seller_id,))
        
        escrows = cur.fetchall()
        
        # Convert datetime objects to strings
        for escrow in escrows:
            for key, value in escrow.items():
                if isinstance(value, datetime):
                    escrow[key] = value.isoformat()
        
        cur.close()
        conn.close()
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps(escrows)
        }
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error',
                'details': str(e)
            })
        }
