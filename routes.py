from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from extensions import db
from models import User
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

# Initialize the routing blueprint clipboard
api_bp = Blueprint('api', __name__)

# 1. The Signup Route
@api_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or request.form
    email = data.get("email")
    password = data.get("password")

    if not email or not password or password.strip() == "":
        return jsonify({"error": "Email and password are required"}), 400

    user_exists = db.session.scalars(db.select(User).filter_by(email=email)).first()
    if user_exists:
        return jsonify({"error": "Email already registered"}), 400

    # Securely hash the password using scrypt
    hashed_password = generate_password_hash(password, method="scrypt")

    new_user = User(email=email, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()

    # Automatically generate a secure, signed token string
    token = create_access_token(identity=str(new_user.id))

    return jsonify({
        "status": "success",
        "message": "User registered and logged in successfully!",
        "token": token,
    }), 201


# 2. The Login Route (New!)
@api_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or request.form
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400

    # Search for the user in the database
    user = db.session.scalars(db.select(User).filter_by(email=email)).first()

    # If user doesn't exist, or the scrypt blender comparison fails, block them
    if not user or not check_password_hash(user.password, password):
        return jsonify({"error": "Invalid email or password"}), 401

    # If correct, issue a fresh login token
    token = create_access_token(identity=str(user.id))

    return jsonify({
        "status": "success",
        "message": "Logged in successfully!",
        "token": token
    }), 200


# 3. A Protected Dashboard Route (To test the token)
@api_bp.route("/dashboard", methods=["GET"])
@jwt_required()
def dashboard():
    current_user_id = get_jwt_identity()
    return jsonify({
        "status": "success",
        "message": f"Access granted! You are logged in as user {current_user_id}."
    }), 200


@api_bp.route("/auth/google", methods=["POST"])
def google_login():
    data = request.get_json(silent=True)

    if not data:
        return jsonify({"error": "Invalid JSON or missing Content-Type header"}), 400

    token_id = data.get("token")

    if not token_id:
        return jsonify({"error": "Google token is required"}), 400

    # --- 1. EVALUATE ENVIRONMENT AND SET ID_INFO ---
    if current_app.debug and token_id == "google-test-token":
        # Safe testing fallback mode
        id_info = {
            "email": "dev-test-user@gmail.com",
            "iss": "https://accounts.google.com"
        }
    else:
        # Strict Cryptographic Verification Mode
        from google.oauth2 import id_token as google_decoder

        try:
            id_info = None
            for client_id in current_app.config["GOOGLE_CLIENT_IDS"]:
                try:
                    id_info = google_decoder.verify_oauth2_token(
                        token_id,
                        google_requests.Request(),
                        client_id
                    )
                    break  # Success, exit the loop!
                except ValueError:
                    continue  # Keep looking through remaining Client IDs

            if not id_info:
                return jsonify({"error": "Invalid Google token for this application"}), 401

            # Fixed the typo domains here as well!
            if id_info['iss'] not in ['accounts.google.com', 'https://accounts.google.com']:
                return jsonify({"error": "Wrong token issuer"}), 401

        except Exception as e:
            return jsonify({"error": f"Authentication failed: {str(e)}"}), 400

    # --- 2. SYNC ACCOUNT TO SQLITE DATABASE ---
    email = id_info.get("email")
    user = db.session.scalars(db.select(User).filter_by(email=email)).first()

    if not user:
        user = User(email=email, password=None)
        db.session.add(user)
        db.session.commit()
        message = "Cross-platform registration complete!"
    else:
        message = "Cross-platform login successful!"

    # --- 3. ISSUE SIGNED APPLICATION JWT SESSION TOKEN ---
    native_token = create_access_token(identity=str(user.id))

    return jsonify({
        "status": "success",
        "message": message,
        "token": native_token
    }), 200
