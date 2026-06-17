# Final Project - Flask API

A Flask-based backend application featuring user authentication and database management.

## Features
- User Registration with hashed passwords.
- SQLite Database integration using SQLAlchemy.
- Database migrations with Flask-Migrate.

## Setup Instructions

1. **Clone the repository:**
   ```bash
   git clone <your-repository-url>
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # macOS/Linux:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Initialize the database:**
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

5. **Run the application:**
   ```bash
   python app.py
   ```
