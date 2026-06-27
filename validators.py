from flask import request, jsonify

def validate_product_query_params(is_admin=False):
    """
    Unified query parameter validator (Pages 5 & 7).
    Safely enforces rules for public shoppers vs. administrators.
    """
    try:
        # 1. Pagination Parameters (Page 5 mandates 'limit' instead of 'per_page')
        page = int(request.args.get("page", 1))
        limit = int(request.args.get("limit", 20))

        if page < 1:
            return None, (jsonify({"error": "Invalid query parameters. page must be >= 1."}), 400)

        if limit < 1 or limit > 100:
            return None, (jsonify({"error": "Invalid query parameters. limit must be an integer between 1 and 100."}), 400)

        # 2. Text Search Parameter
        search_query = request.args.get("search")
        if search_query:
            search_query = search_query.strip()

        # 3. Category Filter (Allowed for both public and admin - Page 5 & 7)
        category_param = request.args.get("category")
        if category_param:
            category_param = category_param.strip()

        # 4. Price Filters Safely
        min_price_raw = request.args.get("min_price")
        max_price_raw = request.args.get("max_price")

        min_price = int(min_price_raw) if min_price_raw is not None else None
        max_price = int(max_price_raw) if max_price_raw is not None else None

        if min_price is not None and max_price is not None:
            if min_price > max_price:
                return None, (jsonify({"error": "Invalid query parameters. min_price cannot be greater than max_price."}), 400)

        # 5. Sorting Field Whitelist (Page 5)
        sort_param = request.args.get("sort", "newest")  # Default to newest
        valid_sorts = ["price_asc", "price_desc", "newest", "name_asc"]
        if sort_param not in valid_sorts:
            return None, (jsonify({"error": f"Invalid query parameters. Allowed sort fields are: {', '.join(valid_sorts)}"}), 400)



        # 🆕 6. Admin-Only Param Guard (Strictly enforced ONLY if is_admin=True)
        status_param = "all"  # Default fallback state for public users
        if is_admin:
            status_param = request.args.get("status", "all").strip().lower()
            valid_statuses = ["all", "active", "inactive"]
            if status_param not in valid_statuses:
                return None, (jsonify({"error": f"Invalid query parameters. Allowed status values are: {', '.join(valid_statuses)}"}), 400)
        else:
            # 🔒 SECURITY: If a public user attempts to pass a status filter, reject them honestly (Page 6)
            if "status" in request.args:
                return None, (jsonify({"error": "Invalid query parameters. 'status' is an administrative parameter."}), 400)

    except ValueError:
        return None, (jsonify({"error": "Invalid query parameters. Expected numeric values for pagination limits or price filters."}), 400)

    # Return clean parsed data package back to the route layers
    return {
        "page": page,
        "limit": limit,
        "search": search_query,
        "category": category_param,
        "min_price": min_price,
        "max_price": max_price,
        "sort": sort_param,
        "status": status_param  # Public gets "all" safely, Admin gets their filtered choice
    }, None


def validate_product_creation_body():
    """
    Validates request payload for creating a product (Page 8).
    Tracks field-level error messages and returns a structured 422 payload.
    """
    data = request.get_json(silent=True) or request.form
    if not data:
        return None, (jsonify({"error": "Missing or invalid request body."}), 400)

    # Initialize the field-level error details collection (Page 8 Specification)
    validation_errors = []

    # 1. Validate 'name' (Required, 2–160 chars)
    name = data.get("name")
    if not name or not str(name).strip():
        validation_errors.append({"field": "name", "message": "Field is required."})
    elif len(str(name)) < 2 or len(str(name)) > 160:
        validation_errors.append({"field": "name", "message": "Must be between 2 and 160 characters."})

    # 2. Validate 'description' (Optional, max 5000 chars)
    description = data.get("description")
    if description and len(str(description)) > 5000:
        validation_errors.append({"field": "description", "message": "Cannot exceed 5000 characters."})

    # 3. Validate 'sku' (Required, 1–64 chars, no whitespace)
    sku = data.get("sku")
    if not sku or not str(sku).strip():
        validation_errors.append({"field": "sku", "message": "Field is required."})
    elif len(str(sku)) < 1 or len(str(sku)) > 64:
        validation_errors.append({"field": "sku", "message": "Must be between 1 and 64 characters."})
    elif " " in str(sku):
        validation_errors.append({"field": "sku", "message": "Cannot contain whitespace spaces."})

    # 4. Validate 'price_cents' (Required, integer >= 0)
    price_cents_raw = data.get("price_cents")
    price_cents = None

    if price_cents_raw is None or str(price_cents_raw).strip() == "":
        validation_errors.append({"field": "price_cents", "message": "Field is required."})
    else:
        try:
            # Block booleans (True/False shouldn't be treated as numbers)
            if isinstance(price_cents_raw, bool):
                raise ValueError

            # Clean string symbols like spaces or commas if they exist, then convert
            cleaned_price = str(price_cents_raw).replace(",", "").strip()
            price_cents = int(cleaned_price)

            if price_cents < 0:
                validation_errors.append({"field": "price_cents", "message": "Must be an integer >= 0."})
        except (ValueError, TypeError):
            validation_errors.append({"field": "price_cents", "message": "Must be an integer >= 0."})

    # 5. Validate 'stock_quantity' (Optional, integer >= 0, default 0)
    stock_quantity_raw = data.get("stock_quantity")
    stock_quantity = 0

    if stock_quantity_raw is not None and str(stock_quantity_raw).strip() != "":
        try:
            if isinstance(stock_quantity_raw, bool):
                raise ValueError

            stock_quantity = int(str(stock_quantity_raw).strip())
            if stock_quantity < 0:
                validation_errors.append({"field": "stock_quantity", "message": "Must be an integer >= 0."})
        except (ValueError, TypeError):
            validation_errors.append({"field": "stock_quantity", "message": "Must be an integer >= 0."})

    # 6. Validate 'category_id' (Required, must reference existing row)
    category_id = data.get("category_id")
    if not category_id or not str(category_id).strip():
        validation_errors.append({"field": "category_id", "message": "Field is required."})

    # 🆕 7. Explicit Validation for 'is_active' (Optional Boolean)
    is_active_raw = data.get("is_active")
    is_active = True

    if is_active_raw is not None and str(is_active_raw).strip() != "":
        if isinstance(is_active_raw, str):
            clean_str = is_active_raw.strip().lower()
            if clean_str in ["true", "1"]:
                is_active = True
            elif clean_str in ["false", "0"]:
                is_active = False
            else:
                validation_errors.append({"field": "is_active", "message": "Must be a valid boolean choice."})
        elif isinstance(is_active_raw, bool):
            is_active = is_active_raw
        elif isinstance(is_active_raw, int) and is_active_raw in[0, 1]:
            is_active = bool(is_active_raw)
        else:
            validation_errors.append({"field": "is_active", "message": "Must be a valid boolean value."})

    # 🆕 8. Explicit Validation for 'images' Array Payload Structure
    raw_images = data.get("images", [])
    images = []

    # If it's form data, Postman treats custom arrays as strings sometimes, so let's guard it safely
    if isinstance(raw_images, str):
        # Allow empty form fields to pass through without breaking
        if raw_images.strip() != "":
            validation_errors.append({"field": "images", "message": "Must be a valid payload list object."})
    elif not isinstance(raw_images, list):
        validation_errors.append({"field": "images", "message": "Must be a valid list object array."})
    else:
        # Loop over every nested dictionary entry to verify image URLs
        for idx, img_item in enumerate(raw_images):
            if not isinstance(img_item, dict):
                validation_errors.append(
                    {"field": f"images[{idx}]", "message": "Image properties must be an object."})
                continue

            url = img_item.get("url")
            if not url or not str(url).strip():
                validation_errors.append(
                    {"field": f"images[{idx}].url", "message": "Field is required for each image entry."})
            elif len(str(url)) > 500:
                validation_errors.append(
                    {"field": f"images[{idx}].url", "message": "URL cannot exceed 500 characters."})
            else:
                # Save cleaned item to pass back
                images.append({
                    "url": str(url).strip(),
                    "alt_text": str(img_item.get("alt_text", "")).strip() or None,
                    "position": img_item.get("position")
                })

    # 7. Check if errors were captured during audit steps
    if validation_errors:
        # Returns structured dictionary matching Page 8 error format exactly
        error_payload = {
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "One or more fields are invalid.",
                "details": validation_errors
            }
        }
        return None, (jsonify(error_payload), 422)

    # Return clean parsed properties packager
    return {
        "name": str(name).strip(),
        "sku": str(sku).strip().upper(),
        "category_id": str(category_id).strip(),
        "price_cents": price_cents,
        "stock_quantity": stock_quantity,
        "description": str(description).strip() if description else None,
        "currency": str(data.get("currency", "USD")).strip().upper()[:3],
        "is_active": is_active,
        "images": images
    }, None

def validate_product_update_body():
    """
    Validates optional request payload fields for a partial update (PATCH).
    Tracks field-level error messages and returns a structured 422 payload.
    """
    data = request.get_json(silent=True) or request.form
    if not data:
        return None, (jsonify({"error": "Missing or invalid request body."}), 400)

    validation_errors = []
    cleaned_data = {}

    # 1. Partial 'name' Validation
    if "name" in data:
        name = data.get("name")
        if not name or not str(name).strip():
            validation_errors.append({"field": "name", "message": "Field cannot be empty if provided."})
        elif len(str(name)) < 2 or len(str(name)) > 160:
            validation_errors.append({"field": "name", "message": "Must be between 2 and 160 characters."})
        else:
            cleaned_data["name"] = str(name).strip()

    # 2. Partial 'description' Validation
    if "description" in data:
        description = data.get("description")
        if description is not None and len(str(description)) > 5000:
            validation_errors.append({"field": "description", "message": "Cannot exceed 5000 characters."})
        else:
            cleaned_data["description"] = str(description).strip() if description else None

    # 3. Partial 'sku' Validation
    if "sku" in data:
        sku = data.get("sku")
        if not sku or not str(sku).strip():
            validation_errors.append({"field": "sku", "message": "Field cannot be empty if provided."})
        elif len(str(sku)) < 1 or len(str(sku)) > 64:
            validation_errors.append({"field": "sku", "message": "Must be between 1 and 64 characters."})
        elif " " in str(sku):
            validation_errors.append({"field": "sku", "message": "Cannot contain whitespace spaces."})
        else:
            cleaned_data["sku"] = str(sku).strip().upper()

    # 4. Partial 'price_cents' Validation
    if "price_cents" in data:
        price_cents_raw = data.get("price_cents")
        try:
            if isinstance(price_cents_raw, bool):
                raise ValueError
            cleaned_price = str(price_cents_raw).replace(",", "").strip()
            price_cents = int(cleaned_price)
            if price_cents < 0:
                validation_errors.append({"field": "price_cents", "message": "Must be an integer >= 0."})
            else:
                cleaned_data["price_cents"] = price_cents
        except (ValueError, TypeError):
            validation_errors.append({"field": "price_cents", "message": "Must be an integer >= 0."})

    # 5. Partial 'category_id' Validation
    if "category_id" in data:
        category_id = data.get("category_id")
        if not category_id or not str(category_id).strip():
            validation_errors.append({"field": "category_id", "message": "Field cannot be empty if provided."})
        else:
            cleaned_data["category_id"] = str(category_id).strip()

    # 6. Partial 'is_active' Validation
    if "is_active" in data:
        is_active_raw = data.get("is_active")
        if isinstance(is_active_raw, str):
            clean_str = is_active_raw.strip().lower()
            if clean_str in ["true", "1"]:
                cleaned_data["is_active"] = True
            elif clean_str in ["false", "0"]:
                cleaned_data["is_active"] = False
            else:
                validation_errors.append({"field": "is_active", "message": "Must be a valid boolean choice."})
        elif isinstance(is_active_raw, bool):
            cleaned_data["is_active"] = is_active_raw
        elif isinstance(is_active_raw, int) and is_active_raw in[0, 1]:
            cleaned_data["is_active"] = bool(is_active_raw)
        else:
            validation_errors.append({"field": "is_active", "message": "Must be a valid boolean value."})

    # 7. Partial 'images' Validation
    if "images" in data:
        raw_images = data.get("images", [])
        images = []
        if not isinstance(raw_images, list):
            validation_errors.append({"field": "images", "message": "Must be a valid list object array."})
        else:
            for idx, img_item in enumerate(raw_images):
                if not isinstance(img_item, dict):
                    validation_errors.append({"field": f"images[{idx}]", "message": "Image properties must be an object."})
                    continue
                url = img_item.get("url")
                if not url or not str(url).strip():
                    validation_errors.append({"field": f"images[{idx}].url", "message": "Field is required for each image entry."})
                elif len(str(url)) > 500:
                    validation_errors.append({"field": f"images[{idx}].url", "message": "URL cannot exceed 500 characters."})
                else:
                    images.append({
                        "url": str(url).strip(),
                        "alt_text": str(img_item.get("alt_text", "")).strip() or None,
                        "position": img_item.get("position")
                    })
            cleaned_data["images"] = images

    # 8. Check for validation errors
    if validation_errors:
        error_payload = {
            "error": {
                "code": "VALIDATION_FAILED",
                "message": "One or more fields are invalid.",
                "details": validation_errors
            }
        }
        return None, (jsonify(error_payload), 422)

    return cleaned_data, None