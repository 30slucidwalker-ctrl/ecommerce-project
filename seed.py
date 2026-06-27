import sys
from app import create_app  # Adjust this to match your app factory file
from extensions import db
from models import User
from werkzeug.security import generate_password_hash


def seed_admin(email, password):
    app = create_app()

    with app.app_context():
        # Prevent duplicate entries
        existing_user = db.session.scalars(db.select(User).filter_by(email=email)).first()
        if existing_user:
            print(f"Error: User '{email}' already exists.")
            sys.exit(1)

        # Securely hash the admin password using scrypt
        hashed_password = generate_password_hash(password, method="scrypt")

        # Explicitly create as admin
        admin = User(email=email, password=hashed_password, is_admin=True)

        db.session.add(admin)
        db.session.commit()
        print(f"Success: Admin account '{email}' created safely via terminal.")


if __name__ == "__main__":
    # Change these credentials before running!
    ADMIN_EMAIL = "admin@ecommerce.com"
    ADMIN_PASSWORD = "admin12345678"

    seed_admin(ADMIN_EMAIL, ADMIN_PASSWORD)