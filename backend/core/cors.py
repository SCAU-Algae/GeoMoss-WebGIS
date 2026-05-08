"""
CORS configuration for the FastAPI application.

The current permissive regex is preserved for deployment compatibility. Move it
behind environment-specific settings before exposing stricter production modes.
"""


ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://154.201.94.222:5173",
    "http://154.201.94.222",
    "https://geomoss.app",
    "https://www.geomoss.app",
]


def build_cors_options() -> dict:
    """Return keyword arguments for CORSMiddleware."""
    return {
        "allow_origins": ALLOWED_ORIGINS,
        "allow_origin_regex": "https?://.*",
        "allow_credentials": True,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }
