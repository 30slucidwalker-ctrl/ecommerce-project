from functools import wraps
from flask import jsonify
from flask_jwt_extended import jwt_required, get_jwt

def admin_required():
    """
    Custom decorator to protect admin routes.
    Ensures a valid token exists (401) and the user has the admin claim (403).
    """
    def wrapper(fn):
        @wraps(fn)
        @jwt_required()  # Automatically returns 401 if token is missing or expired
        def decorator(*args, **kwargs):
            claims = get_jwt()
            # If the custom claim isn't True, block them with a 403 Forbidden
            if not claims.get("is_admin", False):
                return jsonify({"error": "Admin role required"}), 403
            return fn(*args, **kwargs)
        return decorator
    return wrapper