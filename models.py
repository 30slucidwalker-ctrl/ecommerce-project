from extensions import db
import uuid
from datetime import datetime, timezone

class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=True)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)

class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(160), nullable=False)  # Fixed: changed from title to name (Page 1)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)  # Fixed: max length 180 (Page 2)
    sku = db.Column(db.String(64), unique=True, nullable=False, index=True)  # Fixed: max length 64 (Page 2)
    description = db.Column(db.Text, nullable=True)

    price_cents = db.Column(db.Integer, db.CheckConstraint('price_cents >= 0'), nullable=False, index=True)
    currency = db.Column(db.String(3), default='USD', nullable=False)  # Added: ISO currency tracker (Page 2)
    stock_quantity = db.Column(db.Integer, db.CheckConstraint('stock_quantity >= 0'), default=0, nullable=False)

    # Links to the parent category required by the spec hierarchy
    category_id = db.Column(db.String(36), nullable=False, index=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Database relations linking our structural entities
    # category = db.relationship("Category", backref="products", lazy=True)
    images = db.relationship("ProductImage", backref="product", lazy=True, cascade="all, delete-orphan")

class ProductImage(db.Model):
    __tablename__ = "product_images"

    id = db.Column(db.String(36), primary_key=True,default=lambda: str(uuid.uuid4()))
    product_id = db.Column(db.String(36), db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False,
                           index=True)

    url = db.Column(db.String(500), nullable=False)  # Fixed column naming and lengths (Page 3)
    alt_text = db.Column(db.String(200), nullable=True)  # Added column (Page 3)
    position = db.Column(db.SmallInteger, default=0, nullable=False)
    # Fixed: position display sequence (Page 3)