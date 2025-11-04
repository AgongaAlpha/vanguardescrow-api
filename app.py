from flask import Flask, request, jsonify
import importlib.util
import sys
import os
import json

app = Flask(__name__)

# Enable CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Import all your function files dynamically
functions_dir = "functions"

# Debug endpoint to check file structure
@app.route('/debug')
def debug_files():
    try:
        current_dir = os.getcwd()
        files_in_root = os.listdir('.')
        functions_path = os.path.join(current_dir, functions_dir)
        
        if os.path.exists(functions_path):
            function_files = os.listdir(functions_path)
        else:
            function_files = ["FUNCTIONS DIRECTORY NOT FOUND"]
            
        return jsonify({
            "current_directory": current_dir,
            "files_in_root": files_in_root,
            "functions_directory": functions_path,
            "function_files": function_files,
            "hello.py_exists": os.path.exists(os.path.join(functions_path, "hello.py"))
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/.netlify/functions/<function_name>', methods=['GET', 'POST', 'OPTIONS'])
@app.route('/<function_name>', methods=['GET', 'POST', 'OPTIONS'])
def route_function(function_name):
    try:
        # Find the Python file
        python_file = f"{functions_dir}/{function_name}.py"
        absolute_path = os.path.abspath(python_file)
        
        if not os.path.exists(python_file):
            return jsonify({
                "error": f"Function {function_name} not found",
                "looking_in": python_file,
                "absolute_path": absolute_path,
                "current_directory": os.getcwd()
            }), 404
        
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
