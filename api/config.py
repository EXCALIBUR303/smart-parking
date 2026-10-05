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

# A hosted deployment that forgot the secret would sign tokens with a key that
# is printed in this public file, so anyone could forge an admin session.
# Refuse to start rather than run that way.
if os.environ.get("VERCEL") and JWT_SECRET == "dev-only-change-me":
    raise RuntimeError("SMARTPARK_JWT_SECRET must be set in a deployed environment")
JWT_ALGORITHM = "HS256"
JWT_TTL_HOURS = 12

# Where the static front-end lives, relative to the repository root.
WEB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
