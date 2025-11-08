from flask import Flask, request, jsonify
import importlib.util
import sys
import os
import json
from flask_cors import CORS  # ADD THIS LINE

app = Flask(__name__)
CORS(app)  # ADD THIS LINE - enables CORS for all routes

# Your existing code below (keep everything else the same)
# Import all your function files dynamically - THEY ARE IN THE CURRENT DIRECTORY
functions_dir = "."  # ← CHANGED TO CURRENT DIRECTORY

@app.route('/.netlify/functions/<function_name>', methods=['GET', 'POST', 'OPTIONS'])
@app.route('/<function_name>', methods=['GET', 'POST', 'OPTIONS'])
def route_function(function_name):
    try:
        # Find the Python file
        python_file = f"{function_name}.py"  # ← CHANGED - No directory prefix
        
        if not os.path.exists(python_file):
            return jsonify({"error": f"Function {function_name} not found at {python_file}"}), 404
        
        # Dynamically import the module
        spec = importlib.util.spec_from_file_location(function_name, python_file)
        module = importlib.util.module_from_spec(spec)
        sys.modules[function_name] = module
        spec.loader.exec_module(module)
        
        # Create event object from request
        event = {
            "httpMethod": request.method,
            "path": request.path,
            "headers": dict(request.headers),
            "queryStringParameters": dict(request.args),
            "body": request.get_data().decode('utf-8') if request.data else None
        }
        
        # Call the handler function
        context = {}
        result = module.handler(event, context)
        
        # Return the response
        if isinstance(result, dict) and 'body' in result:
            return jsonify(json.loads(result['body'])), result.get('statusCode', 200)
        else:
            return jsonify(result), 200
        
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "traceback": traceback.format_exc()}), 500

# Health check endpoint
@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "message": "Vanguard Escrow API is running"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)

