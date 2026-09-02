"""
alerts.py  —  Heya AI Voice Analytics
Alert engine: metric checking + HTML email delivery.

Reuses recommendations.py for detection logic — same patterns, different output
channel (email instead of UI card).

Cooldown:  24 h per alert type per client (configurable via ALERT_COOLDOWN_HOURS).
Transport: SMTP with STARTTLS — works with Gmail, Outlook, SendGrid, Mailgun, etc.
"""

import os
import smtplib
import ssl
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy import func
from database import get_db, Call, AudioInsight, AlertConfig, AlertLog

# ── Config ────────────────────────────────────────────────────────────────────
SMTP_HOST             = os.getenv("SMTP_HOST",     "smtp.gmail.com")
SMTP_PORT             = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER             = os.getenv("SMTP_USER",     "")
SMTP_PASSWORD         = os.getenv("SMTP_PASSWORD", "")
FROM_EMAIL            = os.getenv("ALERT_FROM_EMAIL", SMTP_USER or "alerts@heya.ai")
DASHBOARD_URL         = os.getenv("DASHBOARD_URL", "http://localhost:5173/dashboard")
ALERT_COOLDOWN_HOURS  = int(os.getenv("ALERT_COOLDOWN_HOURS", "24"))

CLIENT_NAMES = {
    "client_heya_001": "Artel Apartments",
    "client_heya_002": "MVAA Legal",
}

ALERT_LABELS = {
    "high_silence":              "High Silence Ratio",
    "poor_conversation_flow":    "Poor Conversation Flow",
    "low_success_rate":          "Low Call Success Rate",
    "low_engagement":            "Low Engagement Score",
    "deteriorating_trajectory":  "Deteriorating Caller Trajectory",
    "high_interruptions":        "High Interruption Rate",
    "negative_sentiment":        "High Negative Sentiment",
    "weekly_digest":             "Weekly Performance Digest",
}


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL TRANSPORT
# ═══════════════════════════════════════════════════════════════════════════════
def _build_message(to: str, subject: str, html_body: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = f"Heya AI Alerts <{FROM_EMAIL}>"
    msg["To"]      = to
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    return msg


def _send_email_raw(to: str, subject: str, html_body: str) -> None:
    """
    Attempt to send an email. Raises an exception with the real error on failure.
    Tries STARTTLS (port 587) first, then falls back to SSL (port 465).
    Gmail App Passwords may be pasted with spaces — they are stripped automatically.
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        raise ValueError(
            "SMTP_USER or SMTP_PASSWORD is empty in .env — "
            "add your Gmail address and App Password."
        )

    # App Passwords from Google are displayed as 'xxxx xxxx xxxx xxxx' — strip spaces
    password = SMTP_PASSWORD.replace(" ", "")
    msg      = _build_message(to, subject, html_body)
    raw      = msg.as_string()
    errors   = []

    # ── Attempt 1: STARTTLS on configured port (default 587) ─────────────────
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as srv:
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
            srv.login(SMTP_USER, password)
            srv.sendmail(FROM_EMAIL, to, raw)
        return  # success
    except Exception as e:
        errors.append(f"STARTTLS port {SMTP_PORT}: {e}")

    # ── Attempt 2: SSL on port 465 ───────────────────────────────────────────
    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, 465, context=ctx, timeout=15) as srv:
            srv.ehlo()
            srv.login(SMTP_USER, password)
            srv.sendmail(FROM_EMAIL, to, raw)
        return  # success
    except Exception as e:
        errors.append(f"SSL port 465: {e}")

    raise ConnectionError(
        "Both SMTP methods failed:\n" + "\n".join(f"  · {e}" for e in errors)
    )


def _send_email(to: str, subject: str, html_body: str) -> bool:
    """Wrapper — returns True/False. Use _send_email_raw() when you need the error."""
    try:
        _send_email_raw(to, subject, html_body)
        print(f"  ✅ [alert] Sent → {to}: {subject}")
        return True
    except Exception as e:
        print(f"  ✗ [alert] {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# EMAIL TEMPLATES
# ═══════════════════════════════════════════════════════════════════════════════
def _priority_colors(priority: str) -> tuple[str, str]:
    return {
        "critical": ("#f87171", "#f8717118"),
        "warning":  ("#fb923c", "#fb923c18"),
        "info":     ("#818cf8", "#818cf818"),
    }.get(priority, ("#818cf8", "#818cf818"))


def _build_alert_html(
    client_name: str,
    title: str,
    insight: str,
    metric: str,
    action: str,
    priority: str,
) -> tuple[str, str]:
    """Return (subject, html_body) for a threshold alert."""
    text_color, bg_color = _priority_colors(priority)
    subject = f"[Heya AI Alert] {title} — {client_name}"

    html = f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0a0a0f;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0f;padding:40px 20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0"
  style="background:#111118;border:1px solid #ffffff18;border-radius:14px;overflow:hidden;max-width:600px;">

  <!-- Header -->
  <tr><td style="padding:24px 32px;border-bottom:1px solid #ffffff12;">
    <table width="100%"><tr>
      <td>
        <div style="font-size:17px;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;">🎙 Heya AI</div>
        <div style="font-size:10px;color:#64748b;font-family:monospace;letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;">Voice Analytics</div>
      </td>
      <td align="right">
        <span style="background:{bg_color};color:{text_color};border:1px solid {text_color}50;
          border-radius:5px;padding:4px 10px;font-size:10px;font-family:monospace;
          font-weight:700;letter-spacing:0.08em;text-transform:uppercase;">{priority.upper()}</span>
      </td>
    </tr></table>
  </td></tr>

  <!-- Body -->
  <tr><td style="padding:28px 32px 0;">
    <div style="font-size:11px;color:#64748b;font-family:monospace;letter-spacing:0.08em;
      text-transform:uppercase;margin-bottom:6px;">{client_name}</div>
    <div style="font-size:20px;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;
      margin-bottom:18px;line-height:1.3;">{title}</div>
    <div style="font-size:13px;color:#94a3b8;line-height:1.75;font-family:monospace;
      margin-bottom:22px;">{insight}</div>
  </td></tr>

  <!-- Metric -->
  <tr><td style="padding:0 32px 20px;">
    <div style="background:{bg_color};border:1px solid {text_color}40;border-radius:8px;padding:14px 18px;">
      <div style="font-size:10px;color:#64748b;font-family:monospace;
        letter-spacing:0.1em;text-transform:uppercase;margin-bottom:5px;">Key Metric</div>
      <div style="font-size:14px;font-weight:700;color:{text_color};font-family:monospace;">{metric}</div>
    </div>
  </td></tr>

  <!-- Action -->
  <tr><td style="padding:0 32px 24px;">
    <div style="font-size:10px;color:#64748b;font-family:monospace;
      letter-spacing:0.1em;text-transform:uppercase;margin-bottom:8px;">Recommended Action</div>
    <div style="font-size:13px;color:#94a3b8;line-height:1.75;font-family:monospace;">{action}</div>
  </td></tr>

  <!-- CTA -->
  <tr><td style="padding:0 32px 28px;">
    <a href="{DASHBOARD_URL}"
      style="display:inline-block;background:#818cf8;color:#fff;text-decoration:none;
      padding:12px 26px;border-radius:8px;font-size:13px;font-weight:700;
      letter-spacing:-0.01em;">View Dashboard →</a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:18px 32px;border-top:1px solid #ffffff0a;">
    <div style="font-size:11px;color:#475569;font-family:monospace;line-height:1.6;">
      You received this because alerts are enabled for {client_name}.<br>
      Manage alert settings in your dashboard under <strong>Alerts</strong>.
    </div>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""

    return subject, html


def _build_digest_html(
    client_name: str,
    stats: dict,
    top_recs: list[dict],
) -> tuple[str, str]:
    """Return (subject, html_body) for the weekly digest email."""
    subject = f"[Heya AI] Weekly Performance Digest — {client_name}"

    eng   = stats.get("avg_engagement", 0)
    sr    = stats.get("success_rate",   0)
    total = stats.get("total_calls",    0)
    proc  = stats.get("audio_processed", 0)

    eng_color = "#6ee7b7" if eng >= 65 else "#fb923c" if eng >= 45 else "#f87171"
    sr_color  = "#6ee7b7" if sr  >= 80 else "#fb923c" if sr  >= 65 else "#f87171"

    recs_html = ""
    for rec in top_recs[:3]:
        tc, bc = _priority_colors(rec["priority"])
        recs_html += f"""
    <tr><td style="padding:12px 0;border-bottom:1px solid #ffffff0a;">
      <div style="display:flex;align-items:flex-start;gap:10px;">
        <span style="background:{bc};color:{tc};border:1px solid {tc}40;border-radius:4px;
          padding:2px 8px;font-size:9px;font-family:monospace;font-weight:700;
          letter-spacing:0.08em;text-transform:uppercase;flex-shrink:0;margin-top:2px;">
          {rec["priority"].upper()}</span>
        <div>
          <div style="font-size:13px;font-weight:700;color:#f1f5f9;margin-bottom:4px;">{rec["title"]}</div>
          <div style="font-size:12px;color:#64748b;font-family:monospace;">{rec["metric"]}</div>
        </div>
      </div>
    </td></tr>"""

    html = f"""<!DOCTYPE html><html lang="en">
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a0a0f;font-family:'Helvetica Neue',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0f;padding:40px 20px;">
<tr><td align="center">
<table width="600" cellpadding="0" cellspacing="0"
  style="background:#111118;border:1px solid #ffffff18;border-radius:14px;overflow:hidden;max-width:600px;">

  <!-- Header -->
  <tr><td style="padding:24px 32px;border-bottom:1px solid #ffffff12;">
    <table width="100%"><tr>
      <td>
        <div style="font-size:17px;font-weight:800;color:#f1f5f9;letter-spacing:-0.02em;">🎙 Heya AI</div>
        <div style="font-size:10px;color:#64748b;font-family:monospace;letter-spacing:0.1em;text-transform:uppercase;margin-top:2px;">Weekly Performance Digest</div>
      </td>
      <td align="right">
        <span style="font-size:11px;color:#64748b;font-family:monospace;">{client_name}</span>
      </td>
    </tr></table>
  </td></tr>

  <!-- KPI row -->
  <tr><td style="padding:28px 32px 0;">
    <div style="font-size:10px;color:#64748b;font-family:monospace;letter-spacing:0.1em;
      text-transform:uppercase;margin-bottom:14px;">This Week's Numbers</div>
    <table width="100%"><tr>
      <td width="33%" style="padding-right:8px;">
        <div style="background:#1a1a24;border:1px solid #ffffff12;border-radius:10px;padding:16px;">
          <div style="font-size:10px;color:#64748b;font-family:monospace;text-transform:uppercase;margin-bottom:6px;">Total Calls</div>
          <div style="font-size:26px;font-weight:800;color:#818cf8;">{total}</div>
          <div style="font-size:10px;color:#475569;font-family:monospace;margin-top:4px;">{proc} analysed</div>
        </div>
      </td>
      <td width="33%" style="padding-right:8px;">
        <div style="background:#1a1a24;border:1px solid #ffffff12;border-radius:10px;padding:16px;">
          <div style="font-size:10px;color:#64748b;font-family:monospace;text-transform:uppercase;margin-bottom:6px;">Avg Engagement</div>
          <div style="font-size:26px;font-weight:800;color:{eng_color};">{eng:.1f}</div>
          <div style="font-size:10px;color:#475569;font-family:monospace;margin-top:4px;">out of 100</div>
        </div>
      </td>
      <td width="33%">
        <div style="background:#1a1a24;border:1px solid #ffffff12;border-radius:10px;padding:16px;">
          <div style="font-size:10px;color:#64748b;font-family:monospace;text-transform:uppercase;margin-bottom:6px;">Success Rate</div>
          <div style="font-size:26px;font-weight:800;color:{sr_color};">{sr:.1f}%</div>
          <div style="font-size:10px;color:#475569;font-family:monospace;margin-top:4px;">target: 80%+</div>
        </div>
      </td>
    </tr></table>
  </td></tr>

  <!-- Recommendations -->
  <tr><td style="padding:24px 32px 0;">
    <div style="font-size:10px;color:#64748b;font-family:monospace;letter-spacing:0.1em;
      text-transform:uppercase;margin-bottom:4px;">Top Recommendations This Week</div>
    <table width="100%">{recs_html if recs_html else
      "<tr><td style='padding:16px 0;font-size:13px;color:#6ee7b7;font-family:monospace;'>✅ All metrics are healthy this week.</td></tr>"
    }</table>
  </td></tr>

  <!-- CTA -->
  <tr><td style="padding:24px 32px 28px;">
    <a href="{DASHBOARD_URL}"
      style="display:inline-block;background:#818cf8;color:#fff;text-decoration:none;
      padding:12px 26px;border-radius:8px;font-size:13px;font-weight:700;">
      Open Dashboard →</a>
  </td></tr>

  <!-- Footer -->
  <tr><td style="padding:18px 32px;border-top:1px solid #ffffff0a;">
    <div style="font-size:11px;color:#475569;font-family:monospace;line-height:1.6;">
      Weekly digest for {client_name} · Heya AI Voice Analytics<br>
      Manage alert settings in your dashboard under <strong>Alerts</strong>.
    </div>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""

    return subject, html


# ═══════════════════════════════════════════════════════════════════════════════
# CHECK + SEND
# ═══════════════════════════════════════════════════════════════════════════════
def check_and_send_alerts(client_id: str) -> dict:
    """
    Run all enabled alert configs for a client.
    Returns {"sent": N, "skipped": N, "failed": N}
    """
    from recommendations import generate_recommendations

    with get_db() as db:
        cfg_rows = (
            db.query(AlertConfig)
            .filter(AlertConfig.client_id == client_id, AlertConfig.enabled == True)
            .all()
        )
        # Convert to plain dicts before session closes to avoid DetachedInstanceError
        configs = [
            {
                "id":             c.id,
                "alert_type":     c.alert_type,
                "min_priority":   c.min_priority,
                "last_triggered": c.last_triggered,
                "email":          c.email,
            }
            for c in cfg_rows
        ]

    if not configs:
        return {"sent": 0, "skipped": 0, "failed": 0}

    recs    = {r["id"]: r for r in generate_recommendations(client_id)}
    results = {"sent": 0, "skipped": 0, "failed": 0}

    for cfg in configs:
        if cfg["alert_type"] == "weekly_digest":
            continue  # handled separately by send_weekly_digest()

        rec = recs.get(cfg["alert_type"])
        if not rec:
            results["skipped"] += 1
            continue  # metric is healthy — nothing to alert

        # Priority filter
        if cfg["min_priority"] == "critical" and rec["priority"] != "critical":
            results["skipped"] += 1
            continue

        # Cooldown check
        if cfg["last_triggered"]:
            elapsed_h = (datetime.utcnow() - cfg["last_triggered"]).total_seconds() / 3600
            if elapsed_h < ALERT_COOLDOWN_HOURS:
                results["skipped"] += 1
                _log_alert(client_id, cfg["alert_type"],
                           f"[cooldown] {cfg['alert_type']}", "cooldown")
                continue

        client_name = CLIENT_NAMES.get(client_id, client_id)
        subject, html = _build_alert_html(
            client_name = client_name,
            title       = rec["title"],
            insight     = rec["insight"],
            metric      = rec["metric"],
            action      = rec["action"],
            priority    = rec["priority"],
        )

        ok = _send_email(cfg["email"], subject, html)
        _log_alert(client_id, cfg["alert_type"], subject, "sent" if ok else "failed")

        if ok:
            results["sent"] += 1
            with get_db() as db:
                c = db.query(AlertConfig).filter(AlertConfig.id == cfg["id"]).first()
                if c:
                    c.last_triggered = datetime.utcnow()
        else:
            results["failed"] += 1

    return results


def send_weekly_digest(client_id: str) -> bool:
    """
    Build and send the weekly performance digest to all subscribers.
    """
    from recommendations import generate_recommendations

    with get_db() as db:
        _cfg = (
            db.query(AlertConfig)
            .filter(
                AlertConfig.client_id == client_id,
                AlertConfig.alert_type == "weekly_digest",
                AlertConfig.enabled == True,
            )
            .first()
        )
        cfg = {"id": _cfg.id, "email": _cfg.email, "last_triggered": _cfg.last_triggered} if _cfg else None

    if not cfg:
        return False

    # Cooldown — 6 days (don't send twice in one week)
    if cfg["last_triggered"]:
        elapsed_days = (datetime.utcnow() - cfg["last_triggered"]).days
        if elapsed_days < 6:
            return False

    # Gather stats
    with get_db() as db:
        total = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id)
            .scalar() or 0
        )
        successful = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id, Call.call_successful == True)
            .scalar() or 0
        )
        avg_eng = float(
            db.query(func.avg(AudioInsight.engagement_score))
            .join(Call, AudioInsight.call_id == Call.id)
            .filter(Call.client_id == client_id)
            .scalar() or 0
        )
        processed = (
            db.query(func.count(AudioInsight.id))
            .join(Call, AudioInsight.call_id == Call.id)
            .filter(Call.client_id == client_id)
            .scalar() or 0
        )

    stats = {
        "total_calls":    total,
        "success_rate":   round(successful / (total or 1) * 100, 1),
        "avg_engagement": round(avg_eng, 1),
        "audio_processed": processed,
    }

    recs        = generate_recommendations(client_id)
    client_name = CLIENT_NAMES.get(client_id, client_id)
    subject, html = _build_digest_html(client_name, stats, recs)

    ok = _send_email(cfg["email"], subject, html)
    _log_alert(client_id, "weekly_digest", subject, "sent" if ok else "failed")

    if ok:
        with get_db() as db:
            c = db.query(AlertConfig).filter(AlertConfig.id == cfg["id"]).first()
            if c:
                c.last_triggered = datetime.utcnow()

    return ok


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def _log_alert(client_id: str, alert_type: str, subject: str, status: str):
    try:
        with get_db() as db:
            db.add(AlertLog(
                client_id  = client_id,
                alert_type = alert_type,
                subject    = subject,
                status     = status,
                sent_at    = datetime.utcnow(),
            ))
    except Exception as e:
        print(f"  ⚠ [alert] Failed to log alert: {e}")
