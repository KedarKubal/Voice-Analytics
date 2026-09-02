"""
auth_router.py  —  Heya AI Voice Analytics
Login + profile endpoints

Endpoints:
    POST /auth/login   — email + password → JWT token
    GET  /auth/me      — decode token, return current user info
    GET  /auth/clients — (admin only) list all clients on platform
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func

from auth import (
    CurrentUser, create_token, get_current_user,
    verify_password,
)
from database import Call, Client, User, AudioInsight, get_db

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Request / Response Models ─────────────────────────────────────────────────

class LoginRequest(BaseModel):
    email:    str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type:   str = "bearer"
    role:         str
    client_id:    Optional[str]
    user_id:      str
    name:         Optional[str] = None   # client business name for greeting


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/login", response_model=TokenResponse)
def login(req: LoginRequest):
    """
    Exchange email + password for a JWT.

    The JWT embeds client_id and role — the frontend stores it and
    attaches it as  Authorization: Bearer <token>  on every request.
    """
    with get_db() as db:
        user = db.query(User).filter(User.email == req.email).first()

        if not user or not verify_password(req.password, user.hashed_password):
            raise HTTPException(status_code=401, detail="Invalid email or password")

        # Fetch client name for the welcome message in the frontend
        client_name = None
        if user.client_id:
            client = db.query(Client).filter(Client.id == user.client_id).first()
            client_name = client.name if client else None

        token = create_token(user.id, user.client_id, user.role, name=client_name)

        return TokenResponse(
            access_token = token,
            role         = user.role,
            client_id    = user.client_id,
            user_id      = user.id,
            name         = client_name,
        )


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    """Return the current user's identity from their JWT."""
    return {
        "user_id":   user.user_id,
        "client_id": user.client_id,
        "role":      user.role,
        "is_admin":  user.is_admin,
    }


@router.get("/clients")
def list_clients(user: CurrentUser = Depends(get_current_user)):
    """
    Admin-only: list all clients with their call counts and audio processing status.
    This powers the Heya AI God View overview page.
    """
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    with get_db() as db:
        clients = db.query(Client).order_by(Client.name).all()

        result = []
        for c in clients:
            total_calls = (
                db.query(func.count(Call.id))
                .filter(Call.client_id == c.id)
                .scalar() or 0
            )
            processed = (
                db.query(func.count(AudioInsight.id))
                .join(Call, AudioInsight.call_id == Call.id)
                .filter(Call.client_id == c.id)
                .scalar() or 0
            )
            successful = (
                db.query(func.count(Call.id))
                .filter(Call.client_id == c.id)
                .filter(Call.call_successful == True)
                .scalar() or 0
            )
            avg_engagement = (
                db.query(func.avg(AudioInsight.engagement_score))
                .join(Call, AudioInsight.call_id == Call.id)
                .filter(Call.client_id == c.id)
                .scalar()
            )

            result.append({
                "client_id":       c.id,
                "name":            c.name,
                "folder_name":     c.folder_name,
                "total_calls":     total_calls,
                "processed_calls": processed,
                "success_rate":    round(successful / (total_calls or 1) * 100, 1),
                "avg_engagement":  round(float(avg_engagement), 1) if avg_engagement else None,
                "created_at":      str(c.created_at),
            })

        return {
            "total_clients": len(result),
            "clients":       result,
        }
