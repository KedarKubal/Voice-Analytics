"""
export_router.py  —  Heya AI Voice Analytics
Data export: CSV download + printable HTML summary report.

Endpoints:
    GET /export/csv/{client_id}     → calls + insights as .csv download
    GET /export/report/{client_id}  → HTML report (open in browser → Print → Save as PDF)
"""

import csv
import io
from datetime import datetime
from sqlalchemy import func

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse

from auth import CurrentUser, get_current_user
from database import (
    get_db, get_app_db,
    Call, AudioInsight,
    get_audio_insights_by_client,
)

router = APIRouter(prefix="/export", tags=["export"])

CLIENT_NAMES = {
    "client_heya_001": "Artel Apartments",
    "client_heya_002": "MVAA Legal",
}


def _check_access(user: CurrentUser, client_id: str):
    if not user.is_admin and user.client_id != client_id:
        raise HTTPException(403, "Access denied")


# ═══════════════════════════════════════════════════════════════════════════════
# CSV EXPORT
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/csv/{client_id}")
def export_csv(
    client_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Download all calls + audio insights for a client as a CSV file.
    Columns match the dashboard display exactly.
    """
    _check_access(user, client_id)

    insights = get_audio_insights_by_client(client_id)

    output = io.StringIO()
    writer = csv.writer(output)

    # Header row
    writer.writerow([
        "Call ID",
        "Date & Time",
        "Direction",
        "Duration (sec)",
        "Successful",
        "User Sentiment",
        "Conversation Flow",
        "Sentiment Trajectory",
        "Engagement Score",
        "Silence Ratio (%)",
        "Interruptions",
        "Hesitations",
        "Total Turns",
        "Agent Talk Time (sec)",
        "Customer Talk Time (sec)",
        "Avg Pitch (Hz)",
        "Agent Avg Pitch (Hz)",
        "Customer Avg Pitch (Hz)",
        "Avg Energy",
        "Agent Avg Energy",
        "Customer Avg Energy",
    ])

    for r in insights:
        ts = r.get("start_timestamp")
        date_str = (
            datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
            if ts else ""
        )
        writer.writerow([
            r.get("call_id", ""),
            date_str,
            r.get("direction", ""),
            round(r.get("duration_ms", 0) / 1000, 1),
            "Yes" if r.get("call_successful") is True
            else ("No" if r.get("call_successful") is False else ""),
            r.get("user_sentiment", ""),
            r.get("conversation_flow", ""),
            r.get("sentiment_trajectory", ""),
            round(r.get("engagement_score", 0), 1),
            round(r.get("silence_ratio", 0) * 100, 1),
            r.get("interruption_count", 0),
            r.get("hesitation_count", 0),
            r.get("total_turns", 0),
            round(r.get("agent_talk_time_sec", 0), 1),
            round(r.get("customer_talk_time_sec", 0), 1),
            round(r.get("avg_pitch_hz", 0), 1),
            round(r.get("agent_avg_pitch_hz", 0), 1),
            round(r.get("customer_avg_pitch_hz", 0), 1),
            round(r.get("avg_energy", 0), 6),
            round(r.get("agent_avg_energy", 0), 6),
            round(r.get("customer_avg_energy", 0), 6),
        ])

    output.seek(0)
    filename = f"heya_calls_{client_id}_{datetime.utcnow().strftime('%Y%m%d')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ═══════════════════════════════════════════════════════════════════════════════
# HTML REPORT
# ═══════════════════════════════════════════════════════════════════════════════
@router.get("/report/{client_id}", response_class=HTMLResponse)
def export_report(
    client_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Return a print-optimised HTML summary report.
    Open in browser → File → Print → Save as PDF  (Ctrl+P / Cmd+P)
    """
    _check_access(user, client_id)

    client_name = CLIENT_NAMES.get(client_id, client_id)
    generated   = datetime.utcnow().strftime("%d %B %Y at %H:%M UTC")

    # ── Gather stats ──────────────────────────────────────────────────────────
    insights = get_audio_insights_by_client(client_id)
    n        = len(insights)

    with get_db() as db:
        total_calls = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id).scalar() or 0
        )
        successful = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id, Call.call_successful == True).scalar() or 0
        )
        avg_dur = (
            db.query(func.avg(Call.duration_ms))
            .filter(Call.client_id == client_id).scalar() or 0
        )
        sent_counts = dict(
            db.query(Call.user_sentiment, func.count(Call.id))
            .filter(Call.client_id == client_id)
            .group_by(Call.user_sentiment).all()
        )

    success_rate = round(successful / (total_calls or 1) * 100, 1)
    avg_dur_sec  = round(float(avg_dur) / 1000, 1)

    avg_eng  = round(sum(r.get("engagement_score", 0) for r in insights) / (n or 1), 1)
    avg_sil  = round(sum(r.get("silence_ratio",   0) for r in insights) / (n or 1) * 100, 1)

    # Engagement benchmark — 62.0 is the Voice AI industry baseline
    BENCHMARK_SCORE = 62.0
    eng_delta       = round(avg_eng - BENCHMARK_SCORE, 1)
    benchmark_label = f"{abs(eng_delta)} pts above industry baseline" if eng_delta >= 0 else f"{abs(eng_delta)} pts below industry baseline"
    benchmark_color = "#22c55e" if eng_delta >= 0 else "#f97316"

    flow_counts = {"smooth": 0, "moderate": 0, "poor": 0}
    traj_counts = {"improving": 0, "stable": 0, "deteriorating": 0}
    for r in insights:
        f = r.get("conversation_flow")
        t = r.get("sentiment_trajectory")
        if f in flow_counts: flow_counts[f] += 1
        if t in traj_counts: traj_counts[t] += 1

    # ── Recommendations ───────────────────────────────────────────────────────
    from recommendations import generate_recommendations
    recs = generate_recommendations(client_id)[:5]

    # ── Recent calls table ────────────────────────────────────────────────────
    recent = sorted(insights, key=lambda r: r.get("start_timestamp") or 0, reverse=True)[:15]

    # ── HTML helpers ──────────────────────────────────────────────────────────
    def bar(pct: float, color: str, max_w: int = 200) -> str:
        w = round(min(pct / 100, 1) * max_w)
        return (f'<div style="height:8px;border-radius:4px;background:#e2e8f0;width:{max_w}px;display:inline-block;vertical-align:middle;">'
                f'<div style="height:100%;border-radius:4px;background:{color};width:{w}px;"></div></div>')

    def pct_of(n_: int) -> str:
        return f"{round(n_ / (total_calls or 1) * 100, 1)}%"

    def eng_color(v: float) -> str:
        return "#22c55e" if v >= 65 else "#f97316" if v >= 45 else "#ef4444"

    PRIORITY_COLORS = {"critical": "#ef4444", "warning": "#f97316", "info": "#6366f1"}

    rec_rows = ""
    for rec in recs:
        color = PRIORITY_COLORS.get(rec["priority"], "#6366f1")
        rec_rows += f"""
        <tr>
          <td><span style="background:{color}20;color:{color};border:1px solid {color}40;
            border-radius:4px;padding:2px 8px;font-size:10px;font-weight:700;
            letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;">
            {rec['priority'].upper()}</span></td>
          <td style="font-weight:600;">{rec['title']}</td>
          <td style="color:#64748b;font-size:12px;">{rec['metric']}</td>
        </tr>"""

    call_rows = ""
    for r in recent:
        ts       = r.get("start_timestamp")
        date_str = datetime.fromtimestamp(ts / 1000).strftime("%d %b %Y %H:%M") if ts else "—"
        eng      = r.get("engagement_score", 0)
        flow     = r.get("conversation_flow", "—")
        flow_c   = {"smooth": "#22c55e", "moderate": "#f97316", "poor": "#ef4444"}.get(flow, "#64748b")
        ok       = r.get("call_successful")
        ok_s     = ("✓ Yes" if ok is True else ("✗ No" if ok is False else "—"))
        ok_c     = "#22c55e" if ok is True else ("#ef4444" if ok is False else "#64748b")

        call_rows += f"""
        <tr>
          <td style="font-family:monospace;font-size:11px;color:#64748b;">{r['call_id'][:28]}…</td>
          <td style="white-space:nowrap;">{date_str}</td>
          <td style="text-transform:capitalize;">{r.get('direction','—')}</td>
          <td style="color:{flow_c};font-weight:600;text-transform:capitalize;">{flow}</td>
          <td style="color:{eng_color(eng)};font-weight:700;">{eng:.1f}</td>
          <td style="text-transform:capitalize;">{r.get('user_sentiment','—')}</td>
          <td style="color:{ok_c};font-weight:600;">{ok_s}</td>
        </tr>"""

    # ── Build HTML ────────────────────────────────────────────────────────────
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Heya AI Report — {client_name}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: 'Helvetica Neue', Arial, sans-serif;
    background: #f8fafc;
    color: #1e293b;
    font-size: 13px;
    line-height: 1.5;
  }}

  .page {{ max-width: 900px; margin: 0 auto; padding: 40px 32px; }}

  /* ── Header ── */
  .rpt-header {{
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding-bottom: 24px;
    border-bottom: 2px solid #e2e8f0;
    margin-bottom: 32px;
  }}
  .rpt-logo {{ font-size: 20px; font-weight: 800; color: #1e293b; letter-spacing: -0.02em; }}
  .rpt-logo span {{ color: #6366f1; }}
  .rpt-meta {{ font-size: 11px; color: #94a3b8; margin-top: 4px; font-family: monospace; letter-spacing: 0.04em; }}
  .rpt-date {{ text-align: right; font-size: 11px; color: #94a3b8; font-family: monospace; }}

  /* ── Section ── */
  .section {{ margin-bottom: 36px; }}
  .section-title {{
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: #94a3b8;
    margin-bottom: 14px;
    padding-bottom: 6px;
    border-bottom: 1px solid #e2e8f0;
  }}

  /* ── KPI grid ── */
  .kpi-grid {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
  }}
  .kpi-card {{
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 16px 18px;
  }}
  .kpi-label {{ font-size: 10px; color: #94a3b8; font-family: monospace; text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 26px; font-weight: 800; color: #1e293b; letter-spacing: -0.03em; line-height: 1; }}
  .kpi-sub   {{ font-size: 11px; color: #94a3b8; font-family: monospace; margin-top: 4px; }}

  /* ── Breakdown rows ── */
  .breakdown {{ display: flex; flex-direction: column; gap: 10px; }}
  .brow {{ display: flex; align-items: center; gap: 12px; }}
  .brow-label {{ width: 130px; font-size: 12px; font-weight: 600; text-transform: capitalize; flex-shrink: 0; }}
  .brow-count {{ width: 36px; font-family: monospace; font-size: 12px; color: #64748b; flex-shrink: 0; }}
  .brow-pct   {{ width: 44px; font-family: monospace; font-size: 11px; color: #94a3b8; flex-shrink: 0; }}

  /* ── Breakdown grid ── */
  .breakdown-grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }}

  /* ── Tables ── */
  table {{ width: 100%; border-collapse: collapse; }}
  th {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #94a3b8;
    text-align: left;
    padding: 8px 10px;
    border-bottom: 1px solid #e2e8f0;
    background: #f8fafc;
  }}
  td {{
    padding: 9px 10px;
    border-bottom: 1px solid #f1f5f9;
    font-size: 12px;
    color: #475569;
    vertical-align: middle;
  }}
  tr:last-child td {{ border-bottom: none; }}
  tbody tr:hover td {{ background: #f8fafc; }}

  .card {{ background: white; border: 1px solid #e2e8f0; border-radius: 10px; overflow: hidden; }}

  /* ── Footer ── */
  .rpt-footer {{
    margin-top: 48px;
    padding-top: 16px;
    border-top: 1px solid #e2e8f0;
    font-size: 11px;
    color: #94a3b8;
    font-family: monospace;
    display: flex;
    justify-content: space-between;
  }}

  /* ── Print ── */
  @media print {{
    body {{ background: white; }}
    .page {{ padding: 20px 16px; max-width: 100%; }}
    .no-print {{ display: none; }}
    .section {{ break-inside: avoid; }}
    table {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<div class="page">

  <!-- Print button — hidden in print -->
  <div class="no-print" style="text-align:right;margin-bottom:16px;">
    <button onclick="window.print()"
      style="background:#6366f1;color:white;border:none;padding:10px 22px;
      border-radius:8px;font-size:13px;font-weight:700;cursor:pointer;letter-spacing:-0.01em;">
      ⬇ Save as PDF (Ctrl+P)
    </button>
  </div>

  <!-- Header -->
  <div class="rpt-header">
    <div>
      <div class="rpt-logo">🎙 Heya <span>AI</span> — Voice Analytics</div>
      <div class="rpt-meta">{client_name} &nbsp;·&nbsp; {client_id}</div>
    </div>
    <div class="rpt-date">
      Performance Report<br>
      Generated {generated}
    </div>
  </div>

  <!-- KPIs -->
  <div class="section">
    <div class="section-title">Performance Overview</div>
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="kpi-label">Total Calls</div>
        <div class="kpi-value">{total_calls}</div>
        <div class="kpi-sub">{n} with audio insights</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Success Rate</div>
        <div class="kpi-value" style="color:{'#22c55e' if success_rate >= 80 else '#f97316' if success_rate >= 65 else '#ef4444'};">{success_rate}%</div>
        <div class="kpi-sub">target: 80%+</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Avg Engagement</div>
        <div class="kpi-value" style="color:{eng_color(avg_eng)};">{avg_eng}</div>
        <div class="kpi-sub" style="color:{benchmark_color};">{benchmark_label}</div>
        <div class="kpi-sub" style="color:#94a3b8;font-size:9px;">vs. Voice AI industry baseline (62.0)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Avg Call Length</div>
        <div class="kpi-value">{avg_dur_sec}s</div>
        <div class="kpi-sub">{round(avg_dur_sec/60, 1)} minutes</div>
      </div>
    </div>
  </div>

  <!-- Breakdowns -->
  <div class="section">
    <div class="section-title">Call Breakdowns</div>
    <div class="breakdown-grid">

      <!-- Sentiment -->
      <div>
        <div style="font-size:11px;font-weight:700;color:#64748b;margin-bottom:10px;">Caller Sentiment</div>
        <div class="breakdown">
          {"".join(f'''<div class="brow">
            <div class="brow-label" style="color:{'#22c55e' if s=='positive' else '#ef4444' if s=='negative' else '#6366f1'};">{s.capitalize()}</div>
            <div class="brow-count">{c}</div>
            {bar(round(c/(total_calls or 1)*100, 1), '#22c55e' if s=='positive' else '#ef4444' if s=='negative' else '#6366f1', 80)}
            <div class="brow-pct">{pct_of(c)}</div>
          </div>''' for s, c in sent_counts.items() if s)}
        </div>
      </div>

      <!-- Flow -->
      <div>
        <div style="font-size:11px;font-weight:700;color:#64748b;margin-bottom:10px;">Conversation Flow</div>
        <div class="breakdown">
          {"".join(f'''<div class="brow">
            <div class="brow-label" style="color:{'#22c55e' if f=='smooth' else '#f97316' if f=='moderate' else '#ef4444'};">{f.capitalize()}</div>
            <div class="brow-count">{c}</div>
            {bar(round(c/(n or 1)*100, 1), '#22c55e' if f=='smooth' else '#f97316' if f=='moderate' else '#ef4444', 80)}
            <div class="brow-pct">{round(c/(n or 1)*100, 1)}%</div>
          </div>''' for f, c in flow_counts.items())}
        </div>
      </div>

      <!-- Trajectory -->
      <div>
        <div style="font-size:11px;font-weight:700;color:#64748b;margin-bottom:10px;">Sentiment Trajectory</div>
        <div class="breakdown">
          {"".join(f'''<div class="brow">
            <div class="brow-label" style="color:{'#22c55e' if t=='improving' else '#64748b' if t=='stable' else '#ef4444'};">{t.capitalize()}</div>
            <div class="brow-count">{c}</div>
            {bar(round(c/(n or 1)*100, 1), '#22c55e' if t=='improving' else '#94a3b8' if t=='stable' else '#ef4444', 80)}
            <div class="brow-pct">{round(c/(n or 1)*100, 1)}%</div>
          </div>''' for t, c in traj_counts.items())}
        </div>
      </div>

    </div>
  </div>

  <!-- Recommendations -->
  {f'''<div class="section">
    <div class="section-title">Top Recommendations</div>
    <div class="card">
      <table>
        <thead><tr><th>Priority</th><th>Issue</th><th>Metric</th></tr></thead>
        <tbody>{rec_rows}</tbody>
      </table>
    </div>
  </div>''' if recs else ''}

  <!-- Recent Calls -->
  <div class="section">
    <div class="section-title">Recent Calls (last {len(recent)})</div>
    <div class="card">
      <table>
        <thead>
          <tr>
            <th>Call ID</th><th>Date &amp; Time</th><th>Direction</th>
            <th>Flow</th><th>Engagement</th><th>Sentiment</th><th>Outcome</th>
          </tr>
        </thead>
        <tbody>{call_rows}</tbody>
      </table>
    </div>
  </div>

  <!-- Footer -->
  <div class="rpt-footer">
    <div>Heya AI Voice Analytics · {client_name}</div>
    <div>Generated {generated} · {total_calls} calls · {n} analysed</div>
  </div>

</div>
</body>
</html>"""

    return HTMLResponse(content=html)
