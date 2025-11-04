import json

# This function must be named 'handler' to be recognized by Netlify (AWS Lambda)
def handler(event, context):
    """
    This is the entry point for the Netlify function.
    It returns a standard JSON response object.
    
    If this deploys successfully, it proves that:
    1. Netlify is correctly finding and using your netlify.toml.
    2. The Python runtime (3.10) is being correctly invoked.
    3. The path 'netlifyfunctions/functions' is correct.
    """
    
    # We use json.dumps() to serialize the Python dictionary into a JSON string
    response_body = json.dumps({
        "message": "Success! The Python function deployed and executed.",
        "path": event.get("path", "/.netlify/functions/hello")
    })

    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*' # Required for CORS if testing from a different origin
        },
        'body': response_body
    }
