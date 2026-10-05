"""Password hashing and bearer-token handling.

Passwords are bcrypt-hashed; the plaintext never leaves the request that
carried it. Tokens are short-lived HS256 JWTs holding only the user id, role
and facility - never the password hash and never anything a client could use
to elevate itself, since the role is re-read from the database on every
request that touches data.
"""
import datetime as dt

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .config import JWT_ALGORITHM, JWT_SECRET, JWT_TTL_HOURS

bearer = HTTPBearer(auto_error=False)

# bcrypt hashes at most 72 bytes of input and raises on anything longer, so
# passwords are truncated to that boundary before hashing and before checking.
# Using the bcrypt library directly rather than through passlib: passlib 1.7
# reads bcrypt.__about__, which bcrypt 4.1+ removed, and the shim fails at
# import time on this machine.
_BCRYPT_MAX = 72


def _encode(plain: str) -> bytes:
    return plain.encode("utf-8")[:_BCRYPT_MAX]


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_encode(plain), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_encode(plain), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def make_token(user: dict) -> str:
    payload = {
        "sub": str(user["user_id"]),
        "role": user["role"],
        "facility_id": user.get("facility_id"),
        "name": user["full_name"],
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=JWT_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)) -> dict:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in to continue.")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Your session has expired. Sign in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid session token.")
    return {
        "user_id": int(payload["sub"]),
        "role": payload["role"],
        "facility_id": payload.get("facility_id"),
        "name": payload.get("name"),
    }


def require_staff(user: dict = Depends(current_user)) -> dict:
    """Gate operations and administration are staff-only."""
    if user["role"] not in ("admin", "operator"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action is restricted to staff.")
    return user


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This action is restricted to administrators.")
    return user
