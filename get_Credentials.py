from http.server import BaseHTTPRequestHandler
import json
import os
import psycopg2
from urllib.parse import urlparse, parse_qs
import jwt
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db_connection():
    """Create and return a database connection"""
    database_url = os.environ.get('DATABASE_URL')
    if not database_url:
        raise ValueError("DATABASE_URL environment variable is not set")
    
    return psycopg2.connect(database_url)

def verify_user_token(token):
    """Verify JWT token and return user data"""
    try:
        jwt_secret = os.environ.get('JWT_SECRET', 'fallback-secret-key-change-in-production')
        decoded = jwt.decode(token, jwt_secret, algorithms=['HS256'])
        return decoded
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")

def get_credentials(escrow_id, user_id):
    """Fetch credentials for a specific escrow ID, verifying user ownership"""
    conn = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # First verify the user owns this escrow (check buyer_id in escrows table)
        cur.execute("""
            SELECT id, buyer_id, seller_email 
            FROM escrows 
            WHERE id = %s AND buyer_id = %s
        """, (escrow_id, user_id))
        
        escrow = cur.fetchone()
        
        if not escrow:
            return None, "Escrow not found or access denied"
        
        # Fetch credentials
        cur.execute("""
            SELECT credentials, provided_by, provided_at 
            FROM escrow_credentials 
            WHERE escrow_id = %s
        """, (escrow_id,))
        
        credentials_data = cur.fetchone()
        
        if credentials_data:
            return {
                'credentials': credentials_data[0],
                'provided_by': credentials_data[1],
                'provided_at': credentials_data[2].isoformat() if credentials_data[2] else None,
                'escrow_id': escrow_id,
                'seller_email': escrow[2]
            }, None
        else:
            return None, "No credentials found for this escrow"
            
    except Exception as e:
        logger.error(f"Database error: {str(e)}")
        return None, f"Database error: {str(e)}"
    finally:
        if conn:
            conn.close()

class handler(BaseHTTPRequestHandler):
    def set_cors_headers(self):
        """Set CORS headers for all responses"""
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Authorization, Content-Type')
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.set_cors_headers()
        self.end_headers()
    
    def do_GET(self):
        try:
            # Parse query parameters
            parsed_path = urlparse(self.path)
            query_params = parse_qs(parsed_path.query)
            escrow_id = query_params.get('escrow_id', [None])[0]
            
            if not escrow_id:
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Missing escrow_id parameter'}).encode())
                return
            
            # Get authorization header
            auth_header = self.headers.get('Authorization')
            if not auth_header or not auth_header.startswith('Bearer '):
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Missing or invalid authorization token'}).encode())
                return
            
            token = auth_header.split(' ')[1]
            
            try:
                # Verify JWT token
                user_data = verify_user_token(token)
                user_id = user_data.get('user_id')
                
                if not user_id:
                    raise ValueError("Invalid token payload")
                    
            except ValueError as e:
                self.send_response(401)
                self.send_header('Content-type', 'application/json')
                self.set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode())
                return
            
            # Get credentials
            credentials, error = get_credentials(escrow_id, user_id)
            
            if error:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps({'error': error}).encode())
            else:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.set_cors_headers()
                self.end_headers()
                self.wfile.write(json.dumps(credentials).encode())
                
        except Exception as e:
            logger.error(f"Server error: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.set_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps({'error': f'Server error: {str(e)}'}).encode())
