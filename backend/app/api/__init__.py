"""Blueprint registration."""
from .admin import bp as admin_bp
from .auth import bp as auth_bp
from .exceedances import bp as exceedances_bp
from .measurements import bp as measurements_bp
from .meta import bp as meta_bp
from .query import bp as query_bp
from .stations import bp as stations_bp

BLUEPRINTS = (
    (meta_bp, "/api/meta"),
    (auth_bp, "/api/auth"),
    (admin_bp, "/api/admin"),
    (stations_bp, "/api/stations"),
    (measurements_bp, "/api/measurements"),
    (exceedances_bp, "/api/exceedances"),
    (query_bp, "/api/query"),
)


def register_blueprints(app):
    for blueprint, url_prefix in BLUEPRINTS:
        app.register_blueprint(blueprint, url_prefix=url_prefix)
