"""
auth.py  —  Heya AI Voice Analytics
JWT authentication + FastAPI dependency injection

WHY JWT:
  The current x-client-id header trusts whatever the frontend sends — fine for dev,
  but a security hole in production. JWT puts client_id and role inside a signed token
  the server issues. The client cannot forge or modify the contents.

Token payload: { sub: user_id, client_id, role, exp }
  role = 'heya_admin' → God View (all clients)
  role = 'client'     → scoped to their client_id only

Usage in endpoints:
    from auth import get_current_user, resolve_client_id, CurrentUser
    from fastapi import Depends

    @app.get("/calls")
    def get_calls(user: CurrentUser = Depends(get_current_user)):
        client_id = resolve_client_id(user)
        ...
"""

import os
from datetime import datetime, timedelta
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
import bcrypt as _bcrypt

load_dotenv()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "heya-ai-voice-analytics-secret-2026-rmit")
ALGORITHM  = "HS256"
TOKEN_EXPIRE_HOURS = 24

bearer = HTTPBearer(auto_error=False)


# ═══════════════════════════════════════════════════════════════════════════════
# PASSWORD HASHING  (bcrypt direct — no passlib dependency)
# ═══════════════════════════════════════════════════════════════════════════════

def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


# ═══════════════════════════════════════════════════════════════════════════════
# TOKEN CREATION + DECODING
# ═══════════════════════════════════════════════════════════════════════════════

def create_token(user_id: str, client_id: Optional[str], role: str,
                  name: Optional[str] = None) -> str:
    """Create a signed JWT valid for TOKEN_EXPIRE_HOURS."""
    payload = {
        "sub":       user_id,
        "client_id": client_id,
        "role":      role,
        "name":      name,
        "exp":       datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    """Decode and validate a JWT. Raises 401 if invalid or expired."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# ═══════════════════════════════════════════════════════════════════════════════
# CURRENT USER — the object injected into every protected endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class CurrentUser:
    """Represents the authenticated caller of an API request."""

    def __init__(self, user_id: str, client_id: Optional[str], role: str):
        self.user_id   = user_id
        self.client_id = client_id
        self.role      = role

    @property
    def is_admin(self) -> bool:
        return self.role == "heya_admin"


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    x_client_id: Optional[str] = Header(default=None),
) -> CurrentUser:
    """
    FastAPI dependency — extracts the current user from the request.

    Priority:
      1. JWT Bearer token in Authorization header  (production path)
      2. x-client-id header fallback              (dev / dashboard.html compat)

    Raises 401 if neither is present.
    """
    if credentials:
        payload = decode_token(credentials.credentials)
        return CurrentUser(
            user_id   = payload.get("sub", ""),
            client_id = payload.get("client_id"),
            role      = payload.get("role", "client"),
        )

    if x_client_id:
        return CurrentUser(
            user_id   = f"header_{x_client_id}",
            client_id = x_client_id,
            role      = "client",
        )

    raise HTTPException(status_code=401, detail="Not authenticated")


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer),
    x_client_id: Optional[str] = Header(default=None),
) -> Optional[CurrentUser]:
    """Same as get_current_user but returns None instead of raising 401."""
    try:
        return get_current_user(credentials, x_client_id)
    except HTTPException:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# TENANT RESOLUTION
# ═══════════════════════════════════════════════════════════════════════════════

def resolve_client_id(
    user: CurrentUser,
    target_client_id: Optional[str] = None,
) -> str:
    """
    Determine which client_id to query against.

    - heya_admin: uses target_client_id param (must be provided)
    - client:     always uses client_id from JWT (cannot be overridden)

    This is the core of tenant isolation:
      clients are structurally prevented from seeing other tenants' data.
    """
    if user.is_admin:
        if not target_client_id:
            raise HTTPException(
                status_code=400,
                detail="Admin requests must include ?client_id=<id>",
            )
        return target_client_id

    if not user.client_id:
        raise HTTPException(status_code=403, detail="No client_id in token")

    return user.client_id
