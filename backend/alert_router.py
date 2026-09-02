"""
alert_router.py  —  Heya AI Voice Analytics
Alert management API.

Endpoints:
    GET  /alerts/config/{client_id}          list all alert configs
    POST /alerts/config/{client_id}          upsert alert config
    DELETE /alerts/config/{client_id}/{type} remove one alert config
    GET  /alerts/history/{client_id}         last 50 alert log entries
    POST /alerts/check/{client_id}           manually run alert checks now
    POST /alerts/digest/{client_id}          send weekly digest now
    POST /alerts/test/{client_id}            send a test email
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr

from auth import CurrentUser, get_current_user
from database import get_db, AlertConfig, AlertLog

router = APIRouter(prefix="/alerts", tags=["alerts"])

VALID_ALERT_TYPES = {
    "high_silence",
    "poor_conversation_flow",
    "low_success_rate",
    "low_engagement",
    "deteriorating_trajectory",
    "high_interruptions",
    "negative_sentiment",
    "weekly_digest",
}


# ── helpers ───────────────────────────────────────────────────────────────────
def _require_access(user: CurrentUser, client_id: str):
    if not user.is_admin and user.client_id != client_id:
        raise HTTPException(403, "Access denied")


# ── Request models ────────────────────────────────────────────────────────────
class AlertConfigIn(BaseModel):
    alert_type:   str
    enabled:      bool   = True
    email:        str
    min_priority: str    = "warning"   # "warning" | "critical"


# ═══════════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/config/{client_id}")
def list_configs(
    client_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Return all alert configs for a client, plus the full list of valid types."""
    _require_access(user, client_id)

    with get_db() as db:
        configs = (
            db.query(AlertConfig)
            .filter(AlertConfig.client_id == client_id)
            .order_by(AlertConfig.alert_type)
            .all()
        )
        return {
            "client_id":   client_id,
            "valid_types": sorted(VALID_ALERT_TYPES),
            "configs": [
                {
                    "id":             c.id,
                    "alert_type":     c.alert_type,
                    "enabled":        c.enabled,
                    "email":          c.email,
                    "min_priority":   c.min_priority,
                    "last_triggered": str(c.last_triggered) if c.last_triggered else None,
                    "created_at":     str(c.created_at),
                }
                for c in configs
            ],
        }


@router.post("/config/{client_id}")
def upsert_config(
    client_id: str,
    body: AlertConfigIn,
    user: CurrentUser = Depends(get_current_user),
):
    """Create or update one alert config (upsert by client_id + alert_type)."""
    _require_access(user, client_id)

    if body.alert_type not in VALID_ALERT_TYPES:
        raise HTTPException(400, f"Unknown alert_type '{body.alert_type}'. "
                                 f"Valid: {sorted(VALID_ALERT_TYPES)}")
    if body.min_priority not in ("warning", "critical"):
        raise HTTPException(400, "min_priority must be 'warning' or 'critical'")

    with get_db() as db:
        existing = (
            db.query(AlertConfig)
            .filter(
                AlertConfig.client_id  == client_id,
                AlertConfig.alert_type == body.alert_type,
            )
            .first()
        )
        if existing:
            existing.enabled      = body.enabled
            existing.email        = body.email
            existing.min_priority = body.min_priority
            existing.updated_at   = datetime.utcnow()
            action = "updated"
        else:
            db.add(AlertConfig(
                client_id    = client_id,
                alert_type   = body.alert_type,
                enabled      = body.enabled,
                email        = body.email,
                min_priority = body.min_priority,
                created_at   = datetime.utcnow(),
                updated_at   = datetime.utcnow(),
            ))
            action = "created"

    return {"status": action, "alert_type": body.alert_type, "client_id": client_id}


@router.delete("/config/{client_id}/{alert_type}")
def delete_config(
    client_id:  str,
    alert_type: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Remove an alert config."""
    _require_access(user, client_id)

    with get_db() as db:
        deleted = (
            db.query(AlertConfig)
            .filter(
                AlertConfig.client_id  == client_id,
                AlertConfig.alert_type == alert_type,
            )
            .delete()
        )
    if not deleted:
        raise HTTPException(404, "Alert config not found")
    return {"status": "deleted", "alert_type": alert_type}


@router.get("/history/{client_id}")
def get_history(
    client_id: str,
    limit: int = 50,
    user: CurrentUser = Depends(get_current_user),
):
    """Return recent alert log entries for a client."""
    _require_access(user, client_id)

    with get_db() as db:
        logs = (
            db.query(AlertLog)
            .filter(AlertLog.client_id == client_id)
            .order_by(AlertLog.sent_at.desc())
            .limit(min(limit, 200))
            .all()
        )
        return {
            "client_id": client_id,
            "logs": [
                {
                    "id":         l.id,
                    "alert_type": l.alert_type,
                    "subject":    l.subject,
                    "status":     l.status,
                    "sent_at":    str(l.sent_at),
                }
                for l in logs
            ],
        }


@router.post("/check/{client_id}")
def run_checks(
    client_id:        str,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Manually trigger alert checks for a client.
    Runs in the background — returns immediately.
    """
    _require_access(user, client_id)

    from alerts import check_and_send_alerts
    background_tasks.add_task(check_and_send_alerts, client_id)
    return {"status": "queued", "message": "Alert checks running in background"}


@router.post("/digest/{client_id}")
def send_digest(
    client_id:        str,
    background_tasks: BackgroundTasks,
    user: CurrentUser = Depends(get_current_user),
):
    """Manually trigger the weekly digest email."""
    _require_access(user, client_id)

    from alerts import send_weekly_digest
    background_tasks.add_task(send_weekly_digest, client_id)
    return {"status": "queued", "message": "Weekly digest sending in background"}


@router.post("/test/{client_id}")
def send_test(
    client_id: str,
    body: AlertConfigIn,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Send a test email immediately to verify SMTP is configured correctly.
    Does NOT respect cooldowns or enabled flags.
    """
    _require_access(user, client_id)

    from alerts import _send_email, CLIENT_NAMES
    client_name = CLIENT_NAMES.get(client_id, client_id)
    subject = f"[Heya AI] Test Alert — {client_name}"
    html = f"""<!DOCTYPE html><html><body style="background:#0a0a0f;padding:40px;
      font-family:monospace;color:#94a3b8;">
      <div style="max-width:500px;margin:0 auto;background:#111118;border:1px solid #ffffff18;
        border-radius:12px;padding:28px;">
        <div style="font-size:18px;font-weight:800;color:#f1f5f9;margin-bottom:16px;">
          🎙 Heya AI — Test Alert
        </div>
        <div style="font-size:13px;line-height:1.7;margin-bottom:20px;">
          This is a test email from Heya AI Voice Analytics.<br>
          SMTP is configured correctly for <strong style="color:#818cf8;">{client_name}</strong>.<br>
          Alert type: <strong>{body.alert_type}</strong>
        </div>
        <div style="font-size:11px;color:#475569;">
          Sent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
        </div>
      </div>
    </body></html>"""

    from alerts import _send_email_raw
    try:
        _send_email_raw(body.email, subject, html)
        return {"status": "sent", "email": body.email, "message": "Test email sent successfully"}
    except Exception as e:
        return {"status": "failed", "email": body.email, "message": str(e)}
