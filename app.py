import os
from flask import Flask
from extensions import db, migrate, jwt
from routes import api_bp
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def create_app():
    app = Flask(__name__)

    # --- THE CENTRAL CONFIGURATION VAULT ---
    # We now pull sensitive information from environment variables
    app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "dev-key-if-missing")
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "dev-jwt-key-if-missing")
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("SQLALCHEMY_DATABASE_URI", "sqlite:///users.db")
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Dynamically build the list of allowed Google Client IDs from environment variables
    google_ids = []
    for i in range(1, 4):
        client_id = os.getenv(f"GOOGLE_CLIENT_ID_{i}")
        if client_id:
            google_ids.append(client_id)
    
    app.config["GOOGLE_CLIENT_IDS"] = google_ids

    # --- THE UNIFIED HANDSHAKE ---
    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    # --- MERGE ROUTE BLUEPRINTS ---
    app.register_blueprint(api_bp, url_prefix='/api')

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5001)
