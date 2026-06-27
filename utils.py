import re
from extensions import db
from models import Product


def generate_unique_slug(name, exclude_product_id=None):
    """
    Generates a unique, URL-friendly slug from a product name.
    Handles naming collisions by appending a counter suffix (Page 3).
    """
    # 1. Clean the string: lowercase, replace spaces/special chars with hyphens
    slug_base = name.strip().lower()
    slug_base = re.sub(re.compile(r'[^a-z0-9\s-]'), '', slug_base)
    slug_base = re.sub(re.compile(r'[\s-]+'), '-', slug_base)
    slug_base = slug_base.strip('-')

    # Fallback if the name consisted entirely of special characters
    if not slug_base:
        slug_base = "product"

    # Truncate to ensure the final slug string fits within the 180-char database limit
    slug_base = slug_base[:170]

    slug = slug_base
    counter = 1

    # 2. Loop to detect database collisions and increment if a match is found
    while True:
        # Build query to check if slug exists
        query = db.select(Product).filter_by(slug=slug)

        # If we are updating an existing product, ignore its own current slug
        if exclude_product_id:
            query = query.filter(Product.id != exclude_product_id)

        existing_product = db.session.scalars(query).first()

        # If no collision exists, the slug is safe to use!
        if not existing_product:
            break

        # Collision found! Append counter suffix (e.g., "red-mug-1")
        slug = f"{slug_base}-{counter}"
        counter += 1

    return slug