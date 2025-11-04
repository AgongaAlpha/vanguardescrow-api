from flask import Flask, request, jsonify
import importlib.util
import sys
import os

app = Flask(__name__)

# Import all your function files dynamically
functions_dir = "netlifyfunctions/functions"

@app.route('/.netlify/functions/<function_name>', methods=['GET', 'POST'])
@app.route('/<function_name>', methods=['GET', 'POST'])
def route_function(function_name):
    try:
        # Find the Python file
        python_file = f"{functions_dir}/{function_name}.py"
        
        if not os.path.exists(python_file):
            return jsonify({"error": f"Function {function_name} not found"}), 404
        
        # Dynamically import the module
        spec = importlib.util.spec_from_file_location(function_name, python_file)
        module = importlib.util.module_from_spec(spec)
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
        return jsonify(result.get('body', '')), result.get('statusCode', 200)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Health check endpoint
@app.route('/')
def health_check():
    return jsonify({"status": "healthy", "message": "Vanguard Escrow API is running"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
