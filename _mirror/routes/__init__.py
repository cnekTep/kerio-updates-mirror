from .admin import admin_bp
from .auth import auth_bp
from .kerio import kerio_bp

# Export all Blueprints
__all__ = ["admin_bp", "auth_bp", "kerio_bp"]
