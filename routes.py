from flask import Blueprint, request, jsonify, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from extensions import db
from models import User
from models import Product, ProductImage
from google.auth.transport import requests as google_requests
from decorators import admin_required
from validators import validate_product_query_params, validate_product_creation_body
from utils import generate_unique_slug

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

    new_user = User(email=email, password=hashed_password, is_admin=False)
    db.session.add(new_user)
    db.session.commit()

    # Automatically generate a secure, signed token string
    additional_claims = {"is_admin": getattr(new_user, "is_admin", False)}
    token = create_access_token(identity=str(new_user.id), additional_claims=additional_claims)

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

    is_admin_user = getattr(user, "is_admin", False)

    additional_claims = {"is_admin": is_admin_user}
    token = create_access_token(identity=str(user.id), additional_claims=additional_claims)


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


@api_bp.route("/products", methods=["GET"])
def list_products():
    # Step 1: Validate parameters using our helper function
    params, error_response = validate_product_query_params()
    if error_response:
        return error_response

    # Step 2: Initialize Base Query
    query = db.select(Product).filter_by(is_active=True)

    # Step 3: Apply Text Search Filter (If provided)
    if params["search"]:
        search_term = f"%{params['search']}%"
        query = query.filter(
            (Product.name.ilike(search_term)) |
            (Product.description.ilike(search_term))
        )

    # Step 4: Apply Price Filters (Using our updated parameter keys!)
    if params["min_price"] is not None:
        query = query.filter(Product.price_cents >= params["min_price"])
    if params["max_price"] is not None:
        query = query.filter(Product.price_cents <= params["max_price"])

    # Step 5: Apply Sorting Structures
    if params["sort"] == "price_asc":
        query = query.order_by(Product.price_cents.asc())
    elif params["sort"] == "price_desc":
        query = query.order_by(Product.price_cents.desc())
    elif params["sort"] == "name_asc":
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.created_at.desc())  # Default sorting order

    if params["category"]:
        # Use the already stripped text directly in your SQL filter!
        query = query.filter(Product.category_id.ilike(params["category"]))

    # Step 6: Execute Pagination Safely
    paginated_results = db.paginate(
        query,
        page=params["page"],
        per_page=params["limit"],
        error_out=False
    )

    # Step 7: Serialize Response (Outputs safe array fields only)
    response_payload = {
        "data": [
            {
                "id": str(product.id),
                "name": product.name,
                "slug": product.slug,
                "description": product.description,
                "price_cents": product.price_cents,
                "currency": product.currency,
                "in_stock": product.stock_quantity > 0,
                # Dynamic flat-approach category serialization structure
                "category": {
                    "id": product.category_id,
                    "name": f"Category ID: {product.category_id}",
                    "slug": f"category-{product.category_id}"
                },
                "images": [
                    {
                        "url": img.url,
                        "alt_text": img.alt_text,
                        "position": img.position
                    } for img in sorted(product.images, key=lambda i: i.position)
                ]
            } for product in paginated_results.items
        ],
        "pagination": {
            "page": paginated_results.page,
            "limit": paginated_results.per_page,  # Maps parameter key mapping name
            "total_items": paginated_results.total,
            "total_pages": paginated_results.pages
        }
    }

    return jsonify(response_payload), 200


@api_bp.route("/products/<id_or_slug>", methods=["GET"])
def get_product(id_or_slug):
    """
    Fetches a single product by its UUID id or unique string slug.
    Masks internal business values to return a clean public safe subset (Page 5).
    """
    # 1. Look up the product matching either the id column OR the slug column
    product = db.session.scalars(
        db.select(Product).filter(
            (Product.id == id_or_slug) | (Product.slug == id_or_slug)
        )
    ).first()

    # 2. Strict protection block: if missing or inactive, obscure with a 404
    if not product or not product.is_active:
        return jsonify({"error": "Product not found"}), 404

    # 3. Sort product images by their structural position sequence (Page 3)
    sorted_images = sorted(product.images, key=lambda img: img.position)

    # 4. Compile the single safe response payload, omitting sku and raw stock values
    safe_payload = {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "description": product.description,
        "price_cents": product.price_cents,
        "currency": product.currency,
        "in_stock": product.stock_quantity > 0,
        "category": {
            "id": product.category_id,
        },
        "images": [
            {
                "id": img.id,
                "url": img.url,
                "alt_text": img.alt_text,
                "position": img.position
            } for img in sorted_images
        ]
    }

    return jsonify(safe_payload), 200


@api_bp.route("/admin/products", methods=["POST"])
@admin_required()  # 🔒 Blocks invalid tokens with 401, non-admins with 403
def create_product():
    """
    Admin-only product entry point.
    Handles data structure creation and saves to the database (Page 6).
    """
    # 1. Parse JSON payload body from the incoming request stream
    cleaned_data, error_response = validate_product_creation_body()
    if error_response:
        return error_response

        # 3. Check for SKU duplicate collisions in your database records
    sku_collision = db.session.scalars(db.select(Product).filter_by(sku=cleaned_data["sku"])).first()
    if sku_collision:
        return jsonify({"error": f"Product with SKU '{cleaned_data['sku']}' already exists"}), 409

    # 4. Generate a unique, clean text slug automatically (Page 3 requirement)
    computed_slug = generate_unique_slug(cleaned_data["name"])

    # 5. Initialize base product table object instance
    new_product = Product(
        name=cleaned_data["name"],
        slug=computed_slug,
        sku=cleaned_data["sku"],
        description=cleaned_data["description"],
        price_cents=cleaned_data["price_cents"],
        currency=cleaned_data["currency"],
        stock_quantity=cleaned_data["stock_quantity"],
        category_id=cleaned_data["category_id"],
        is_active=cleaned_data["is_active"]
    )
    db.session.add(new_product)

    # 🌟 6. Process the nested array of images using a structured loop
    for idx, img_item in enumerate(cleaned_data["images"]):
        # Read pre-sanitized properties safely from the validator output
        url = img_item["url"]
        alt_text = img_item["alt_text"] or f"{cleaned_data['name']} image {idx + 1}"

        # Read explicit position or default it cleanly to the loop array index
        position = img_item["position"] if img_item["position"] is not None else idx

        # Build image record tracking
        new_image = ProductImage(
            product=new_product,  # Wire up relationship foreign key assignment
            url=url,
            alt_text=alt_text,
            position=int(position)
        )
        db.session.add(new_image)

    # 7. Commit transaction to your sqlite engine file execution
    db.session.commit()

    # 8. Return full transparency data details object back to admin view dashboard
    return jsonify({
        "status": "success",
        "message": "Product created successfully!",
        "product": {
            # "id": new_product.id,
            "name": new_product.name,
            "slug": new_product.slug,
            "sku": new_product.sku,
            "description": new_product.description,
            "price_cents": new_product.price_cents,
            "currency": new_product.currency,
            "stock_quantity": new_product.stock_quantity,
            "is_active": new_product.is_active,
            "created_at": new_product.created_at.isoformat(),
            "updated_at": new_product.updated_at.isoformat(),
            "category": {
                "id": new_product.category_id
            },
            "images": [
                {
                    # "id": img.id,
                    "url": img.url,
                    "alt_text": img.alt_text,
                    "position": img.position
                } for img in new_product.images
            ]
        }
    }), 201

@api_bp.route("/admin/products", methods=["GET"])
@admin_required()  # 🔒 Ensures valid token exists (401) and user is an admin (403)
def admin_list_products():
    """
    5.1 List products (admin)
    Returns full database schema layout including hidden and inactive draft lines.
    """
    # 1. Run the shared validator passing is_admin=True to unlock admin checks
    params, error_response = validate_product_query_params(is_admin=True)
    if error_response:
        return error_response  # Instantly returns the (jsonify, 400) tuple on failure

    # 2. Initialize SQL Base Query targeting the complete Product table
    query = db.select(Product)

    # 3. Apply Administrative Visibility Filters (Page 7)
    if params["status"] == "active":
        query = query.filter(Product.is_active == True)
    elif params["status"] == "inactive":
        query = query.filter(Product.is_active == False)
    # If 'all', we do not append an is_active constraint, letting both states pass

    # 4. Filter by Category (Matches flat string identifier column)
    if params["category"]:
        query = query.filter(
            (Product.category_id == params['category']) |
            (Product.category_id.ilike(f"%{params['category']}%"))
        )

    # 5. Apply Case-Insensitive Search matching Name OR Warehouse SKU (Page 7)
    if params["search"]:
        search_term = f"%{params['search']}%"
        query = query.filter(
            (Product.name.ilike(search_term)) |
            (Product.sku.ilike(search_term))  # ⭐ Administrative power to look up by SKU
        )

    # 6. Apply Price Range bounds
    if params["min_price"] is not None:
        query = query.filter(Product.price_cents >= params["min_price"])
    if params["max_price"] is not None:
        query = query.filter(Product.price_cents <= params["max_price"])

    # 7. Apply Sorting structures matching page 5/7 rules
    if params["sort"] == "price_asc":
        query = query.order_by(Product.price_cents.asc())
    elif params["sort"] == "price_desc":
        query = query.order_by(Product.price_cents.desc())
    elif params["sort"] == "name_asc":
        query = query.order_by(Product.name.asc())
    else:
        # 'newest' matches the default fallback sort sequence
        query = query.order_by(Product.created_at.desc())

    # 8. Execute database pagination safely using the parsed 'limit' variable
    paginated_results = db.paginate(query, page=params["page"], per_page=params["limit"], error_out=False)

    # 9. Format response to expose the complete, raw administrative shape (Page 4 & 7)
    admin_data = []
    for product in paginated_results.items:
        admin_data.append({
            "id": str(product.id),
            "name": product.name,
            "slug": product.slug,
            "sku": product.sku,                           # ✅ Exposed to Admin
            "description": product.description,
            "price_cents": product.price_cents,
            "currency": product.currency,
            "stock_quantity": product.stock_quantity,     # ✅ Exact integer count exposed
            "is_active": product.is_active,               # ✅ Draft/soft-delete flag exposed
            "created_at": product.created_at.isoformat(), # ✅ Audit log timestamps exposed
            "updated_at": product.updated_at.isoformat(),
            "category": {
                "id": product.category_id,
                "name": f"Category: {product.category_id}",
                "slug": product.category_id.lower().replace(" ", "-")
            },
            "images": [
                {
                    "url": img.url,
                    "alt_text": img.alt_text,
                    "position": img.position
                } for img in sorted(product.images, key=lambda i: i.position)
            ]
        })

    # 10. Wrap in standard pagination metadata envelope block matching Page 5/7 style
    return jsonify({
        "data": admin_data,
        "pagination": {
            "page": paginated_results.page,
            "limit": paginated_results.per_page,
            "total_items": paginated_results.total,
            "total_pages": paginated_results.pages
        }
    }), 200


@api_bp.route("/admin/products/<id>/stock", methods=["PATCH"])
@admin_required()
def adjust_product_stock(id):
    """
    5.5 Adjust stock (dedicated endpoint)
    Handles restocking or sales corrections cleanly while preventing negative values.
    """
    # 1. Read request body using our professional JSON standard
    data = request.get_json(silent=True)
    if not data or "adjustment" not in data:
        return jsonify({"error": "Missing 'adjustment' field in request body."}), 400

    raw_adjustment = data["adjustment"]

    try:
        # 🔒 SECURITY GUARD: Explicitly block booleans from being cast as integers
        if isinstance(raw_adjustment, bool):
            raise ValueError

        adjustment = int(raw_adjustment)
        if adjustment == 0:
            return jsonify({"error": "Adjustment value cannot be zero."}), 400

    except (ValueError, TypeError):
        return jsonify({"error": "Adjustment value must be a valid positive or negative integer."}), 400

    # 2. Find the product inside the database
    product = db.session.scalars(db.select(Product).filter_by(id=id)).first()
    if not product:
        return jsonify({"error": "Product not found."}), 404

    # 3. Calculate target transactional change
    new_stock = product.stock_quantity + adjustment

    # 🔒 STRICT CONSTRAINT CHECK: Reject operations that drain inventory below 0
    if new_stock < 0:
        return jsonify({
            "error": {
                "code": "INSUFFICIENT_STOCK",
                "message": f"Rejected. Current stock is {product.stock_quantity}. Cannot deduct {abs(adjustment)}."
            }
        }), 400

    # 4. Commit the new stock quantity to database records
    product.stock_quantity = new_stock
    db.session.commit()

    return jsonify({
        "status": "success",
        "message": "Inventory adjusted successfully.",
        "id": str(product.id),
        "name": product.name,
        "sku": product.sku,
        "stock_quantity": product.stock_quantity,
        "updated_at": product.updated_at.isoformat()
    }), 200


@api_bp.route("/admin/products/<id>", methods=["DELETE"])
@admin_required()  # 🔒 Only authorized administrators can soft-delete products
def delete_product(id):
    """
    5.3 Delete a product (admin)
    Executes a soft-delete by flipping the is_active flag to False (Page 6).
    """
    # 1. Locate the product by its unique identifier string
    product = db.session.scalars(db.select(Product).filter_by(id=id)).first()
    if not product:
        return jsonify({"error": "Product not found."}), 404

    # 2. Check if the product is already soft-deleted to prevent redundant operations
    if not product.is_active:
        return jsonify({
            "status": "success",
            "message": "Product is already inactive (soft-deleted)."
        }), 200

    # 3. Execute the soft-delete: flip the visibility flag to False (Page 6)
    product.is_active = False

    # 4. Commit the structural state change to your database records
    db.session.commit()

    # 5. Return a clean confirmation message back to the admin dashboard panel
    return jsonify({
        "status": "success",
        "message": f"Product '{product.name}' has been soft-deleted successfully.",
        "id": str(product.id),
        "is_active": product.is_active,
        "updated_at": product.updated_at.isoformat()
    }), 204


@api_bp.route("/admin/products/<id>/restore", methods=["POST"])
@admin_required()  # 🔒 Only authorized administrators can restore inactive records
def restore_product(id):
    """
    Restore a soft-deleted product (admin)
    Flips the is_active flag back to True to make it visible on the storefront.
    """
    # 1. Locate the product inside your database using the URL string identifier
    product = db.session.scalars(db.select(Product).filter_by(id=id)).first()
    if not product:
        return jsonify({"error": "Product not found."}), 404

    # 2. Check if the product is already active to prevent redundant operations
    if product.is_active:
        return jsonify({
            "status": "success",
            "message": "Product is already active and live on the storefront."
        }), 200

    # 3. Execute the restoration: flip the visibility flag back to True
    product.is_active = True

    # 4. Save the structural state change to your database records
    db.session.commit()

    # 5. Return a confirmation layout object back to the management panel
    return jsonify({
        "status": "success",
        "message": f"Product '{product.name}' has been restored and is now live.",
        "id": str(product.id),
        "is_active": product.is_active,
        "updated_at": product.updated_at.isoformat()
    }), 200

@api_bp.route("/admin/products/<id>", methods=["GET"])
@admin_required()  # 🔒 Strict token and role protection boundaries (Page 6)
def admin_get_product(id):
    """
    5.2 Get a single product (admin)
    Returns the full administrative data shape, bypassing public deletion filters.
    """
    # 1. Look up the product directly by its unique identifier string
    product = db.session.scalars(db.select(Product).filter_by(id=id)).first()

    # 2. If missing, return an honest 404 (No draft obscuring required for admins)
    if not product:
        return jsonify({"error": "Product not found."}), 404

    # 3. Shape the response payload to expose the full transparent model schema (Page 4 & 7)
    return jsonify({
        "id": str(product.id),
        "name": product.name,
        "slug": product.slug,
        "sku": product.sku,                           # ✅ Full Admin Attribute (Page 4)
        "description": product.description,
        "price_cents": product.price_cents,
        "currency": product.currency,
        "stock_quantity": product.stock_quantity,     # ✅ Full Admin Attribute (Page 4)
        "is_active": product.is_active,               # ✅ Full Admin Attribute (Page 4)
        "created_at": product.created_at.isoformat(), # ✅ Full Admin Attribute (Page 4)
        "updated_at": product.updated_at.isoformat(),
        "category": {
            "id": product.category_id,
            "name": product.category_id.replace("-", " ").title(),
            "slug": product.category_id.lower()
        },
        "images": [
            {
                "id": str(img.id),
                "url": img.url,
                "alt_text": img.alt_text,
                "position": img.position
            } for img in sorted(product.images, key=lambda i: i.position)
        ]
    }), 200