"""
SENTINEL AI — authentication & roles
------------------------------------
A tiny demo auth layer (JWT-style HMAC tokens, no external deps):

Roles
  * admin          -> sees everything incl. the user database + RAG
  * employee       -> sees operations (payments, phone-verify, learning)
  * customer_care  -> sees support-facing surface (verifications, RAG knowledge)

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

_SECRET = os.environ.get("SENTINEL_AUTH_SECRET", "sentinel-demo-secret-change-me")
_TOKEN_TTL = 12 * 3600  # 12 hours

# ------------------------------------------------------------------ demo users
# In production this would come from a real user store / DB. For the demo we
# ship one account per role so the login page can be tested immediately.
USERS = {
    "admin": {
        "name": "Demo Admin",
        "role": "admin",
        "password": "admin123",
    },
    "employee": {
        "name": "Risk Employee",
        "role": "employee",
        "password": "employee123",
    },
    "care": {
        "name": "Customer Care",
        "role": "customer_care",
        "password": "care123",
    },
}

ROLE_LABELS = {
    "admin": "Administrator",
    "employee": "Employee",
    "customer_care": "Customer Care",
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
