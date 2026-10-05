"""Configuration, read from the environment with local-development defaults.

Nothing secret is hard-coded. SMARTPARK_JWT_SECRET must be set in any
deployment that is not a local demo; the default below exists so that
`uvicorn api.main:app` works immediately after a clone.
"""
import os

DATABASE_URL = os.environ.get(
    "SMARTPARK_DATABASE_URL",
    f"postgresql:///{os.environ.get('SMARTPARK_DB', 'smartpark')}",
)

JWT_SECRET = os.environ.get("SMARTPARK_JWT_SECRET", "dev-only-change-me")
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = 12

# Where the static front-end lives, relative to the repository root.
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
