"""
SENTINEL AI — authentication & roles
------------------------------------
A tiny demo auth layer (JWT-style HMAC tokens, no external deps):

Roles
  * admin          -> sees everything incl. the user database + RAG

Endpoints
  POST /api/auth/login   -> { token, role, name }
  GET  /api/auth/me      -> current session info (validates token)

Admin-only endpoints (/api/users*, /api/rag/*) are protected with the
`require_role("admin")` FastAPI dependency below. The shared secret is a demo
value; swap it for a real secret + DB-backed users in production.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from typing import Optional

from fastapi import Depends, Header, HTTPException, status

# ------------------------------------------------------------------ secrets
# The token-signing secret and admin password are injected via environment
# variables / a secret manager (NEVER baked into the image or committed).
#
#   SENTINEL_AUTH_SECRET     -> HMAC token-signing secret (min 32 chars in prod)
#   SENTINEL_ADMIN_PASSWORD  -> admin account password
#
# For local/demo runs we fall back to demo values so the app boots instantly,
# but we refuse to run with the insecure default when SENTINEL_STRICT=1
# (set in production / hardened containers). Always set a real secret in prod.

_DEFAULT_SECRET = "sentinel-demo-secret-change-me"
_DEFAULT_PASSWORD = "admin123"

_SECRET = os.environ.get("SENTINEL_AUTH_SECRET", _DEFAULT_SECRET)
_TOKEN_TTL = int(os.environ.get("SENTINEL_TOKEN_TTL", 12 * 3600))

if _SECRET == _DEFAULT_SECRET and os.environ.get("SENTINEL_STRICT") == "1":
    raise RuntimeError(
        "INVALID CONFIG: SENTINEL_AUTH_SECRET must be set to a real secret when "
        "SENTINEL_STRICT=1. Refusing to start with the insecure demo default."
    )

# ------------------------------------------------------------------ demo users
# In production this would come from a real user store / DB (with hashed
# passwords). For the demo we ship a single admin account; the password can be
# overridden with SENTINEL_ADMIN_PASSWORD so you are not stuck on the default.
USERS = {
    "admin": {
        "name": "Demo Admin",
        "role": "admin",
        "password": os.environ.get("SENTINEL_ADMIN_PASSWORD", _DEFAULT_PASSWORD),
    },
}

ROLE_LABELS = {
    "admin": "Administrator",
}


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: str) -> str:
    return hmac.new(_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_token(username: str) -> str:
    """Issue a signed token: base64(username).base64(expiry).signature"""
    exp = int(time.time()) + _TOKEN_TTL
    body = f"{_b64e(username.encode())}.{_b64e(str(exp).encode())}"
    return f"{body}.{_sign(body)}"


def verify_token(token: str) -> dict:
    """Validate a token and return {username, role, name, exp}. Raises on failure."""
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token")
    body, sig = f"{parts[0]}.{parts[1]}", parts[2]
    if not hmac.compare_digest(_sign(body), sig):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token signature")
    try:
        username = _b64d(parts[0]).decode("utf-8")
        exp = int(_b64d(parts[1]).decode("utf-8"))
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "malformed token")
    if time.time() > exp:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "token expired")
    user = USERS.get(username)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "unknown user")
    return {"username": username, "role": user["role"], "name": user["name"], "exp": exp}


def get_current_user(
    authorization: Optional[str] = Header(None),
) -> dict:
    """FastAPI dependency: parse `Authorization: Bearer <token>` -> session."""
    if not authorization:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "malformed authorization header")
    return verify_token(token)


def require_role(*roles: str):
    """FastAPI dependency factory: allow only the given roles."""
    def deps(user: dict = Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"requires role(s): {', '.join(roles)}")
        return user
    return deps


def list_roles() -> dict:
    """Public login-page helper: which roles/accounts exist + display labels."""
    return {
        "accounts": [
            {"username": u, "role": us["role"], "name": us["name"]}
            for u, us in USERS.items()
        ],
        "role_labels": ROLE_LABELS,
    }
