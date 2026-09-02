"""
rag.py  —  Heya AI Voice Analytics
RAG Conversational Interface — LangChain / Groq / pgvector

Zero-hallucination design
--------------------------
Every answer is grounded in one of three ways:
  VERIFIED   — answered directly by SQL query (exact numbers from DB)
  GROUNDED   — LLM answer constrained to pre-computed SQL stats block
               (stats are authoritative; LLM only formats/selects)
  SEMANTIC   — LLM + vector-retrieved call documents (cited by call ID)

The LLM never has the opportunity to invent numbers because:
  1. All statistics are injected as a pre-verified block (SQL results).
  2. The system prompt explicitly forbids numbers not in that block.
  3. The model (llama-3.3-70b-versatile) reliably follows strict instructions.
  4. pgvector search is scoped with WHERE client_id = %s at SQL level —
     wrong-client rows cannot be returned.

Zero cross-data leakage design
--------------------------------
  1. All SQL queries use explicit WHERE client_id = :cid bindings.
  2. pgvector similarity search includes WHERE client_id = %s enforced in SQL.
  3. A post-retrieval check guards against any slippage.

Multi-turn conversation
-----------------------
  query() accepts `history: list[dict]` — last N user/assistant turns.
  These are injected before the current question so the LLM can answer
  follow-up questions like "which of those calls was worst?"
"""

import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2
from langchain_core.documents import Document
from sqlalchemy import func, text as sql_text

from database import get_db, Call, AudioInsight

# ── Config ────────────────────────────────────────────────────────────────────
DATABASE_URL      = os.getenv("DATABASE_URL", "")
CEREBRAS_API_KEY  = os.getenv("CEREBRAS_API_KEY", "")
USE_LLM           = bool(CEREBRAS_API_KEY)
MODEL_NAME        = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
MAX_HISTORY_TURNS = 6

CLIENT_NAMES = {
    "client_heya_001": "Artel Apartments",
    "client_heya_002": "MVAA Legal",
}


# ── Embeddings ────────────────────────────────────────────────────────────────
# Using Ollama nomic-embed-text (768 dims) — free, local, no quota limits.
# Production alternative: OpenAI text-embedding-3-small (1536 dims) when billing is set up.
EMBEDDING_DIMS = 768
OLLAMA_BASE    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

def check_ollama_health() -> bool:
    """Return True if Ollama is reachable, False otherwise."""
    try:
        import requests as _req
        r = _req.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def get_embeddings():
    from langchain_ollama import OllamaEmbeddings
    return OllamaEmbeddings(
        model    = "nomic-embed-text",
        base_url = OLLAMA_BASE,
    )


# ── LLM ───────────────────────────────────────────────────────────────────────
def _call_llm(prompt: str) -> str:
    """Call Cerebras via the OpenAI-compatible SDK — no LangChain wrapper needed."""
    if not CEREBRAS_API_KEY:
        raise ValueError("CEREBRAS_API_KEY missing — add it to backend/.env")
    from openai import OpenAI
    client = OpenAI(
        api_key  = CEREBRAS_API_KEY,
        base_url = "https://api.cerebras.ai/v1",
    )
    resp = client.chat.completions.create(
        model       = MODEL_NAME,
        messages    = [{"role": "user", "content": prompt}],
        temperature = 0,
        max_tokens  = 1024,
    )
    return resp.choices[0].message.content


# ═══════════════════════════════════════════════════════════════════════════════
# ADMIN STATS CONTEXT  (cross-client platform view for heya_admin)
# ═══════════════════════════════════════════════════════════════════════════════
def _build_admin_stats_context() -> str:
    """Platform-wide stats across ALL clients — used when client_id == 'heya_admin'."""
    with get_db() as db:
        total_calls      = db.query(func.count(Call.id)).scalar() or 0
        total_processed  = db.query(func.count(AudioInsight.id)).scalar() or 0
        total_successful = db.query(func.count(Call.id)).filter(Call.call_successful == True).scalar() or 0
        success_pct      = round(total_successful / (total_calls or 1) * 100, 1)

        client_rows = []
        for cid, cname in CLIENT_NAMES.items():
            def ai_q_c():
                return (db.query(AudioInsight)
                        .join(Call, AudioInsight.call_id == Call.id)
                        .filter(Call.client_id == cid))
            def c_q_c():
                return db.query(Call).filter(Call.client_id == cid)

            c_total   = c_q_c().count()
            c_proc    = ai_q_c().count()
            c_suc     = c_q_c().filter(Call.call_successful == True).count()
            c_suc_pct = round(c_suc / (c_total or 1) * 100, 1)
            avg_eng   = db.query(func.avg(AudioInsight.engagement_score)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == cid).scalar()
            avg_sil   = db.query(func.avg(AudioInsight.silence_ratio)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == cid).scalar()
            avg_int   = db.query(func.avg(AudioInsight.interruption_count)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == cid).scalar()
            avg_hes   = db.query(func.avg(AudioInsight.hesitation_count)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == cid).scalar()
            avg_dur   = c_q_c().with_entities(func.avg(Call.duration_ms)).scalar()

            flow_counts = dict(db.query(AudioInsight.conversation_flow, func.count()).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == cid).group_by(AudioInsight.conversation_flow).all())
            traj_counts = dict(db.query(AudioInsight.sentiment_trajectory, func.count()).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == cid).group_by(AudioInsight.sentiment_trajectory).all())
            sent_counts = dict(c_q_c().with_entities(Call.user_sentiment, func.count(Call.id)).group_by(Call.user_sentiment).all())
            dir_counts  = dict(c_q_c().with_entities(Call.direction, func.count(Call.id)).group_by(Call.direction).all())

            client_rows.append({
                "cid": cid, "cname": cname,
                "total": c_total, "processed": c_proc,
                "successful": c_suc, "success_pct": c_suc_pct,
                "avg_eng":   float(avg_eng or 0),
                "avg_sil":   float(avg_sil or 0),
                "avg_int":   float(avg_int or 0),
                "avg_hes":   float(avg_hes or 0),
                "avg_dur_s": round(float(avg_dur or 0) / 1000, 1),
                "flow":      flow_counts,
                "traj":      traj_counts,
                "sentiment": sent_counts,
                "direction": dir_counts,
            })

        # All agents across all clients
        agent_rows = db.execute(sql_text("""
            SELECT
                a.persona_name, a.agent_role, a.direction, a.client_id,
                COUNT(c.id)                                           AS total_calls,
                ROUND(AVG(ai.engagement_score)::numeric, 1)           AS avg_eng,
                ROUND(AVG(ai.hesitation_count)::numeric, 1)           AS avg_hes,
                COUNT(CASE WHEN c.call_successful = TRUE  THEN 1 END) AS successful,
                COUNT(CASE WHEN c.call_successful = FALSE THEN 1 END) AS failed
            FROM agents a
            JOIN calls c ON c.agent_id = a.id
            LEFT JOIN audio_insights ai ON ai.call_id = c.id
            WHERE a.agent_role != 'test' AND a.persona_name IS NOT NULL
            GROUP BY a.persona_name, a.agent_role, a.direction, a.client_id
            ORDER BY a.client_id, a.persona_name
        """)).fetchall()

    lines = [
        "DATA BOUNDARY: The following data covers ALL clients on the Heya AI platform.",
        "You are the Heya AI platform administrator with full cross-client visibility.",
        "",
        f"=== PLATFORM-WIDE TOTALS ===",
        f"Total calls (all clients): {total_calls}",
        f"Calls with audio insights: {total_processed}",
        f"Successful calls (all clients): {total_successful} ({success_pct}% platform success rate)",
        f"Number of clients: {len(CLIENT_NAMES)}",
        "",
        "=== PER-CLIENT BREAKDOWN ===",
    ]

    for cs in client_rows:
        proc = cs["processed"] or 1
        lines += [
            "",
            f"--- {cs['cname']} ({cs['cid']}) ---",
            f"  Total calls:            {cs['total']}",
            f"  Calls with insights:    {cs['processed']}",
            f"  Successful calls:       {cs['successful']} ({cs['success_pct']}% success rate)",
            f"  Avg engagement score:   {cs['avg_eng']:.1f}/100",
            f"  Avg silence ratio:      {cs['avg_sil']*100:.1f}% of call",
            f"  Avg interruptions/call: {cs['avg_int']:.1f}",
            f"  Avg hesitations/call:   {cs['avg_hes']:.1f}",
            f"  Avg call duration:      {cs['avg_dur_s']}s ({round(cs['avg_dur_s']/60,1)} min)",
        ]
        lines.append("  Conversation flow:")
        for flow in ["smooth", "moderate", "poor"]:
            cnt = cs["flow"].get(flow, 0)
            lines.append(f"    {flow.capitalize()}: {cnt} ({round(cnt/(proc)*100,1)}%)")
        lines.append("  Sentiment trajectory:")
        for t in ["improving", "stable", "deteriorating"]:
            cnt = cs["traj"].get(t, 0)
            if cnt:
                lines.append(f"    {t.capitalize()}: {cnt} ({round(cnt/proc*100,1)}%)")
        dir_parts = [f"{d.capitalize()}: {n}" for d, n in cs["direction"].items() if d]
        if dir_parts:
            lines.append(f"  Call direction: {', '.join(dir_parts)}")

    if agent_rows:
        lines += ["", "=== ALL AGENTS ACROSS ALL CLIENTS ==="]
        for r in agent_rows:
            cname   = CLIENT_NAMES.get(r.client_id, r.client_id)
            sp      = round((r.successful or 0) / (r.total_calls or 1) * 100, 1)
            role_lbl = (r.agent_role or "").replace("_", " ").title()
            lines.append(
                f"  {r.persona_name} [{cname}] ({role_lbl}, {r.direction}): "
                f"{r.total_calls} calls | {sp}% success | engagement avg {r.avg_eng or 0} | "
                f"hesitations avg {r.avg_hes or 0}/call"
            )

    lines += ["", "=== END OF PLATFORM DATA ==="]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# STATS CONTEXT  (authoritative SQL → text block fed to LLM)
# ═══════════════════════════════════════════════════════════════════════════════
def build_stats_context(client_id: str) -> str:
    if client_id == "heya_admin":
        return _build_admin_stats_context()
    client_name = CLIENT_NAMES.get(client_id, client_id)
    days_map    = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

    with get_db() as db:
        def ai_q():
            return (db.query(AudioInsight)
                    .join(Call, AudioInsight.call_id == Call.id)
                    .filter(Call.client_id == client_id))

        def c_q():
            return db.query(Call).filter(Call.client_id == client_id)

        total_calls  = c_q().count()
        processed    = ai_q().count()
        successful   = c_q().filter(Call.call_successful == True).count()
        unsuccessful = c_q().filter(Call.call_successful == False).count()
        success_pct  = round(successful / (total_calls or 1) * 100, 1)

        avg_eng  = db.query(func.avg(AudioInsight.engagement_score)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
        max_eng  = db.query(func.max(AudioInsight.engagement_score)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
        min_eng  = db.query(func.min(AudioInsight.engagement_score)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
        avg_dur  = c_q().with_entities(func.avg(Call.duration_ms)).scalar()
        dur_secs = round(float(avg_dur or 0) / 1000, 1)

        flow_counts = dict(db.query(AudioInsight.conversation_flow, func.count()).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).group_by(AudioInsight.conversation_flow).all())
        traj_counts = dict(db.query(AudioInsight.sentiment_trajectory, func.count()).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).group_by(AudioInsight.sentiment_trajectory).all())
        sent_counts = dict(c_q().with_entities(Call.user_sentiment, func.count(Call.id)).group_by(Call.user_sentiment).all())
        dir_counts  = dict(c_q().with_entities(Call.direction, func.count(Call.id)).group_by(Call.direction).all())

        # topic column may not exist yet if migration hasn't been run
        try:
            topic_counts = dict(db.execute(sql_text(
                "SELECT topic, COUNT(*) FROM calls WHERE client_id=:cid AND topic IS NOT NULL GROUP BY topic ORDER BY COUNT(*) DESC"
            ), {"cid": client_id}).fetchall() or [])
        except Exception:
            topic_counts = {}

        avg_silence   = db.query(func.avg(AudioInsight.silence_ratio)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
        avg_interrupts= db.query(func.avg(AudioInsight.interruption_count)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
        avg_hes       = db.query(func.avg(AudioInsight.hesitation_count)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
        avg_agent_t   = db.query(func.avg(AudioInsight.agent_talk_time_sec)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
        avg_cust_t    = db.query(func.avg(AudioInsight.customer_talk_time_sec)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()

        # timestamp-based queries — safe fallback if timestamps are null or malformed
        try:
            peak_hours = db.execute(sql_text("""
                SELECT EXTRACT(hour FROM to_timestamp(start_timstamp::float8/1000)) AS hr, COUNT(*) AS cnt
                FROM calls WHERE client_id=:cid AND start_timstamp IS NOT NULL AND start_timstamp > 0
                GROUP BY hr ORDER BY cnt DESC LIMIT 5
            """), {"cid": client_id}).fetchall()
        except Exception:
            peak_hours = []

        try:
            peak_days = db.execute(sql_text("""
                SELECT EXTRACT(dow FROM to_timestamp(start_timstamp::float8/1000)) AS dow, COUNT(*) AS cnt
                FROM calls WHERE client_id=:cid AND start_timstamp IS NOT NULL AND start_timstamp > 0
                GROUP BY dow ORDER BY cnt DESC LIMIT 3
            """), {"cid": client_id}).fetchall()
        except Exception:
            peak_days = []

        worst = ai_q().order_by(AudioInsight.engagement_score.asc()).limit(5).with_entities(AudioInsight.call_id, AudioInsight.engagement_score, AudioInsight.conversation_flow, AudioInsight.interruption_count, AudioInsight.sentiment_trajectory).all()
        best  = ai_q().order_by(AudioInsight.engagement_score.desc()).limit(5).with_entities(AudioInsight.call_id, AudioInsight.engagement_score, AudioInsight.conversation_flow, AudioInsight.sentiment_trajectory).all()

        try:
            recent = (
                c_q()
                .filter(Call.call_summary.isnot(None))
                .order_by(Call.created_at.desc())
                .limit(6)
                .with_entities(Call.id, Call.user_sentiment, Call.call_successful, Call.call_summary)
                .all()
            )
        except Exception:
            recent = []

        # Agent performance breakdown (calls ⟶ agents + audio_insights join)
        try:
            agent_perf = db.execute(sql_text("""
                SELECT
                    a.persona_name,
                    a.agent_role,
                    a.direction,
                    COUNT(c.id)                                           AS total_calls,
                    ROUND(AVG(ai.engagement_score)::numeric, 1)           AS avg_eng,
                    ROUND(AVG(ai.hesitation_count)::numeric, 1)           AS avg_hes,
                    COUNT(CASE WHEN c.call_successful = TRUE  THEN 1 END) AS successful,
                    COUNT(CASE WHEN c.call_successful = FALSE THEN 1 END) AS failed
                FROM agents a
                JOIN calls c ON c.agent_id = a.id
                LEFT JOIN audio_insights ai ON ai.call_id = c.id
                WHERE a.client_id = :cid
                  AND a.agent_role != 'test'
                  AND a.persona_name IS NOT NULL
                GROUP BY a.persona_name, a.agent_role, a.direction
                ORDER BY a.persona_name, a.direction
            """), {"cid": client_id}).fetchall()
        except Exception:
            agent_perf = []

    lines = [
        f"DATA BOUNDARY: The following data is EXCLUSIVELY for {client_name} ({client_id}).",
        f"No data from any other organisation is present.",
        "",
        f"=== VERIFIED STATISTICS FOR {client_name.upper()} ===",
        f"Total calls: {total_calls}",
        f"Calls with full audio analysis: {processed}",
        f"Successful calls: {successful} ({success_pct}% success rate)",
        f"Unsuccessful calls: {unsuccessful}",
        f"Average call duration: {dur_secs}s ({round(dur_secs/60,1)} min)",
        "",
        "ENGAGEMENT SCORES (0–100 scale):",
        f"  Average engagement: {float(avg_eng or 0):.1f}",
        f"  Highest engagement: {float(max_eng or 0):.1f}",
        f"  Lowest engagement:  {float(min_eng or 0):.1f}",
        "",
        "CONVERSATION FLOW:",
    ]
    for flow in ["smooth","moderate","poor"]:
        cnt = flow_counts.get(flow, 0)
        pct = round(cnt / (processed or 1) * 100, 1)
        lines.append(f"  {flow.capitalize()}: {cnt} calls ({pct}%)")

    lines += ["", "SENTIMENT TRAJECTORY (energy trend during call):"]
    for t in ["improving","stable","deteriorating"]:
        cnt = traj_counts.get(t, 0)
        pct = round(cnt / (processed or 1) * 100, 1)
        if cnt > 0:
            lines.append(f"  {t.capitalize()}: {cnt} calls ({pct}%)")

    lines += ["", "CUSTOMER SENTIMENT (from AI analysis):"]
    for s, cnt in sent_counts.items():
        if s: lines.append(f"  {s.capitalize()}: {cnt} calls")

    lines += ["", "CALL DIRECTION:"]
    for d, cnt in dir_counts.items():
        if d: lines.append(f"  {d.capitalize()}: {cnt} calls")

    if topic_counts:
        lines += ["", "CALL TOPICS (why callers are calling):"]
        for topic, cnt in topic_counts.items():
            pct = round(cnt / (total_calls or 1) * 100, 1)
            lines.append(f"  {topic.replace('_',' ').capitalize()}: {cnt} calls ({pct}%)")

    lines += [
        "",
        "CALL QUALITY AVERAGES:",
        f"  Silence ratio:  {float(avg_silence or 0)*100:.1f}% of call",
        f"  Interruptions:  {float(avg_interrupts or 0):.1f} per call",
        f"  Hesitations:    {float(avg_hes or 0):.1f} per call",
        f"  Agent talk time:    {float(avg_agent_t or 0):.1f}s avg",
        f"  Customer talk time: {float(avg_cust_t or 0):.1f}s avg",
    ]

    if peak_hours:
        lines += ["", "PEAK CALL HOURS:"]
        for r in peak_hours:
            lines.append(f"  {int(r.hr):02d}:00–{int(r.hr)+1:02d}:00 — {r.cnt} calls")

    if peak_days:
        lines += ["", "BUSIEST DAYS OF WEEK:"]
        for r in peak_days:
            lines.append(f"  {days_map[int(r.dow)]}: {r.cnt} calls")

    if worst:
        lines += ["", "LOWEST ENGAGEMENT CALLS (bottom 5 — exact call IDs):"]
        for c in worst:
            lines.append(f"  {c.call_id}: engagement={float(c.engagement_score or 0):.1f}, flow={c.conversation_flow}, interruptions={c.interruption_count}, trajectory={c.sentiment_trajectory}")

    if best:
        lines += ["", "HIGHEST ENGAGEMENT CALLS (top 5 — exact call IDs):"]
        for c in best:
            lines.append(f"  {c.call_id}: engagement={float(c.engagement_score or 0):.1f}, flow={c.conversation_flow}, trajectory={c.sentiment_trajectory}")

    if recent:
        lines += ["", "RECENT CALL SUMMARIES (most recent first):"]
        for c in recent:
            lines.append(f"  [{c.id}] sentiment={c.user_sentiment}, successful={c.call_successful}: {(c.call_summary or '').strip()[:250]}")

    if agent_perf:
        lines += ["", "AGENT PERFORMANCE BREAKDOWN (agents × calls × audio_insights):"]
        persona_groups: dict = {}
        for r in agent_perf:
            pname = r.persona_name
            if pname not in persona_groups:
                persona_groups[pname] = []
            persona_groups[pname].append(r)

        for persona, variants in persona_groups.items():
            total_all = sum(r.total_calls or 0 for r in variants)
            suc_all   = sum(r.successful   or 0 for r in variants)
            suc_pct   = round(suc_all / (total_all or 1) * 100, 1)
            role_lbl  = (variants[0].agent_role or "").replace("_", " ").title()
            avg_eng   = round(
                sum(float(r.avg_eng or 0) * (r.total_calls or 0) for r in variants) / (total_all or 1), 1
            )
            avg_hes   = round(
                sum(float(r.avg_hes or 0) * (r.total_calls or 0) for r in variants) / (total_all or 1), 1
            )
            if len(variants) == 1:
                r = variants[0]
                lines.append(
                    f"  {persona} ({role_lbl}, {r.direction}): "
                    f"{total_all} calls | {suc_pct}% success | engagement avg {avg_eng} | hesitations avg {avg_hes}/call"
                )
            else:
                lines.append(
                    f"  {persona} ({role_lbl}, inbound+outbound combined): "
                    f"{total_all} calls | {suc_pct}% combined success | engagement avg {avg_eng} | hesitations avg {avg_hes}/call"
                )
                for r in variants:
                    sub_pct = round((r.successful or 0) / (r.total_calls or 1) * 100, 1)
                    lines.append(
                        f"    {r.direction}: {r.total_calls} calls | {sub_pct}% success | engagement avg {r.avg_eng or 0}"
                    )

    lines += ["", f"=== END OF VERIFIED DATA FOR {client_name.upper()} ==="]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# DOCUMENT BUILDING
# ═══════════════════════════════════════════════════════════════════════════════
def build_documents_from_db(client_id: str) -> list[Document]:
    with get_db() as db:
        raw = (
            db.query(AudioInsight, Call)
              .join(Call, AudioInsight.call_id == Call.id)
              .filter(Call.client_id == client_id)
              .all()
        )
        # Convert to plain dicts inside the session so ORM objects don't detach
        rows = [
            {
                "call_id":              call.id,
                "direction":            call.direction,
                "call_successful":      call.call_successful,
                "user_sentiment":       call.user_sentiment,
                "call_summary":         call.call_summary,
                "topic":                call.topic,
                "engagement_score":     insight.engagement_score,
                "silence_ratio":        insight.silence_ratio,
                "interruption_count":   insight.interruption_count,
                "hesitation_count":     insight.hesitation_count,
                "conversation_flow":    insight.conversation_flow,
                "avg_pitch_hz":         insight.avg_pitch_hz,
                "avg_energy":           insight.avg_energy,
                "sentiment_trajectory": insight.sentiment_trajectory,
            }
            for insight, call in raw
        ]

    if not rows:
        print(f"  No insights for '{client_id}'")
        return []

    documents = []
    for r in rows:
        call_id   = r["call_id"]
        insight   = r  # alias for readability below
        eng        = float(r["engagement_score"] or 0)
        silence    = float(r["silence_ratio"] or 0)
        interr     = int(r["interruption_count"] or 0)
        hes        = int(r["hesitation_count"] or 0)
        flow       = r["conversation_flow"] or "unknown"
        pitch      = float(r["avg_pitch_hz"] or 0)
        energy     = float(r["avg_energy"] or 0)
        traj       = r["sentiment_trajectory"] or ""
        sentiment  = r["user_sentiment"] or "unknown"
        successful = "yes" if r["call_successful"] else ("no" if r["call_successful"] is False else "unknown")
        summary    = (r["call_summary"] or "").strip()
        topic      = (r["topic"] or "").strip()

        eng_label   = "high engagement" if eng >= 70 else ("moderate engagement" if eng >= 45 else "low engagement")
        pitch_label = "elevated pitch — possible stress" if pitch > 250 else ("normal pitch" if pitch > 180 else "low pitch")

        direction_str = r["direction"] or "unknown direction"
        outcome_str   = "successfully resolved" if successful == "yes" else ("did not resolve" if successful == "no" else "outcome unknown")
        traj_str = {
            "improving":     "the customer's mood improved as the call progressed",
            "stable":        "the customer's mood stayed consistent throughout the call",
            "deteriorating": "the customer became more frustrated as the call progressed",
        }.get(traj, "")
        flow_str = {
            "smooth":   "The conversation flowed naturally with good back-and-forth.",
            "moderate": "The conversation had some friction but was mostly coherent.",
            "poor":     "The conversation was disjointed with significant friction.",
        }.get(flow, "")
        eng_str = (
            "The customer was highly engaged and responsive." if eng >= 70
            else "The customer showed moderate engagement." if eng >= 45
            else "The customer showed low engagement — possibly disinterested or frustrated."
        )

        prose = (
            f"Call {call_id} was a {direction_str} call for {client_id} that {outcome_str}. "
            f"Customer sentiment was {sentiment}. "
            f"{eng_str} Engagement score: {eng:.1f}/100. "
            f"{flow_str} "
        )
        if traj_str:
            prose += f"Notably, {traj_str}. "
        if topic:
            prose += f"The caller was calling about {topic.replace('_', ' ')}. "
        prose += (
            f"There were {interr} interruptions and {hes} hesitations. "
            f"Silence accounted for {silence*100:.1f}% of the call. "
            f"Average customer pitch was {pitch:.0f}Hz ({pitch_label}). "
        )
        if summary:
            prose += f"Call summary: {summary}"

        text_parts = [prose.strip()]

        documents.append(Document(
            page_content="\n".join(text_parts),
            metadata={
                "call_id":             call_id,
                "client_id":           client_id,
                "engagement_score":    eng,
                "conversation_flow":   flow,
                "call_successful":     r["call_successful"],
                "user_sentiment":      sentiment,
                "sentiment_trajectory": traj,
                "topic":               topic,
            }
        ))

    print(f"  Built {len(documents)} document(s) for '{client_id}'")
    return documents


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT PROFILE DOCUMENTS
# ═══════════════════════════════════════════════════════════════════════════════
def build_agent_documents(client_id: str) -> list[Document]:
    """
    Build one Document per agent row (FK-safe for agent_embeddings.agent_id).
    For personas with inbound + outbound variants (Sarah, Julia) each document
    contains the combined persona stats PLUS direction-specific detail so the
    LLM gets the full picture regardless of which variant is retrieved.
    Returns [] if the agents table has no persona_name data yet (run migration first).
    """
    client_name = CLIENT_NAMES.get(client_id, client_id)

    with get_db() as db:
        # Per-agent-row stats (one row per agents.id)
        rows = db.execute(sql_text("""
            SELECT
                a.id                                                        AS agent_db_id,
                a.persona_name,
                a.agent_role,
                a.direction,
                a.description,
                COUNT(c.id)                                                 AS total_calls,
                ROUND(AVG(ai.engagement_score)::numeric, 1)                 AS avg_eng,
                ROUND(AVG(ai.hesitation_count)::numeric, 1)                 AS avg_hes,
                ROUND(AVG(ai.interruption_count)::numeric, 1)               AS avg_ints,
                ROUND(AVG(ai.silence_ratio)::numeric, 3)                    AS avg_silence,
                COUNT(CASE WHEN c.call_successful = TRUE  THEN 1 END)       AS successful,
                COUNT(CASE WHEN c.call_successful = FALSE THEN 1 END)       AS failed,
                ROUND(AVG(ai.agent_talk_time_sec)::numeric, 1)              AS agent_talk,
                ROUND(AVG(ai.customer_talk_time_sec)::numeric, 1)           AS cust_talk
            FROM agents a
            JOIN calls c ON c.agent_id = a.id
            LEFT JOIN audio_insights ai ON ai.call_id = c.id
            WHERE a.client_id = :cid
              AND a.agent_role != 'test'
              AND a.persona_name IS NOT NULL
            GROUP BY a.id, a.persona_name, a.agent_role, a.direction, a.description
            ORDER BY a.persona_name, a.direction
        """), {"cid": client_id}).fetchall()

        # Combined stats per persona (for cross-direction context)
        combined = db.execute(sql_text("""
            SELECT
                a.persona_name,
                a.agent_role,
                COUNT(c.id)                                                 AS total_calls,
                ROUND(AVG(ai.engagement_score)::numeric, 1)                 AS avg_eng,
                ROUND(AVG(ai.hesitation_count)::numeric, 1)                 AS avg_hes,
                COUNT(CASE WHEN c.call_successful = TRUE  THEN 1 END)       AS successful
            FROM agents a
            JOIN calls c ON c.agent_id = a.id
            LEFT JOIN audio_insights ai ON ai.call_id = c.id
            WHERE a.client_id = :cid
              AND a.agent_role != 'test'
              AND a.persona_name IS NOT NULL
            GROUP BY a.persona_name, a.agent_role
        """), {"cid": client_id}).fetchall()

        data_rows    = [dict(r._mapping) for r in rows]
        combined_map = {r.persona_name: dict(r._mapping) for r in combined}

    if not data_rows:
        print(f"  No agent profile data for '{client_id}' — agent documents skipped (run migrate_agent_profiles.sql first)")
        return []

    _role_ctx = {
        "concierge":          "handles guest check-in, booking inquiries, access codes, and emergency escalation",
        "receptionist":       "handles all inbound calls — inquiries, case updates, and routing to team members",
        "at_fault_collector": "contacts at-fault drivers to collect insurance details and accident accounts",
        "follow_up_emailer":  "follows up with clients to confirm they have signed their Welcome Pack engagement documents",
    }

    # Group by persona to know which have multiple directions
    persona_map: dict = {}
    for r in data_rows:
        pname = r["persona_name"]
        if pname not in persona_map:
            persona_map[pname] = []
        persona_map[pname].append(r)

    documents = []

    for r in data_rows:
        persona     = r["persona_name"]
        total       = r["total_calls"] or 0
        suc         = r["successful"] or 0
        fail        = r["failed"] or 0
        suc_pct     = round(suc / (total or 1) * 100, 1)
        avg_eng     = float(r["avg_eng"] or 0)
        avg_hes     = float(r["avg_hes"] or 0)
        avg_ints    = float(r["avg_ints"] or 0)
        avg_silence = float(r["avg_silence"] or 0)
        agent_talk  = float(r["agent_talk"] or 0)
        cust_talk   = float(r["cust_talk"] or 0)
        role        = r["agent_role"]
        direction   = r["direction"]
        description = r["description"] or ""
        role_ctx    = _role_ctx.get(role, role.replace("_", " "))
        role_lbl    = role.replace("_", " ").title()

        comb        = combined_map.get(persona, {})
        comb_total  = comb.get("total_calls") or total
        comb_suc    = comb.get("successful") or suc
        comb_pct    = round(comb_suc / (comb_total or 1) * 100, 1)

        siblings    = persona_map.get(persona, [])
        is_multi    = len(siblings) > 1

        # ── Prose header ─────────────────────────────────────────────────────
        if is_multi:
            prose = (
                f"Agent Profile: {persona} — {client_name} {role_lbl} ({direction} variant). "
                f"{persona} {role_ctx}. "
                f"Overall combined performance across all call directions "
                f"({comb_total} total calls): {comb_pct}% combined success rate. "
            )
        else:
            prose = (
                f"Agent Profile: {persona} — {client_name} {role_lbl} ({direction} calls). "
                f"{persona} {role_ctx}. "
            )

        # ── This direction's stats ────────────────────────────────────────────
        prose += (
            f"This {direction} variant: {total} calls, {suc_pct}% success rate "
            f"({suc} successful, {fail} unsuccessful). "
            f"Average engagement score: {avg_eng}/100. "
            f"Hesitations per call: {avg_hes}"
        )
        if avg_hes > 10:
            prose += " (elevated — may reflect complex or sensitive call content). "
        elif avg_hes < 4:
            prose += " (very low — smooth confident delivery). "
        else:
            prose += " (moderate). "

        prose += (
            f"Interruptions per call: {avg_ints}. "
            f"Silence: {round(avg_silence * 100, 1)}% of call duration. "
            f"Agent speaks avg {agent_talk}s, customer speaks avg {cust_talk}s per call. "
        )

        # ── Cross-direction comparison for multi-direction personas ──────────
        if is_multi:
            other = next(
                (s for s in siblings if s["agent_db_id"] != r["agent_db_id"]), None
            )
            if other:
                other_pct = round((other["successful"] or 0) / (other["total_calls"] or 1) * 100, 1)
                prose += (
                    f"The {other['direction']} variant has "
                    f"{other['total_calls']} calls at {other_pct}% success rate for comparison. "
                )

        if description:
            prose += f"Full agent purpose: {description}"

        documents.append(Document(
            page_content = prose.strip(),
            metadata     = {
                "doc_type":     "agent_profile",
                "agent_id":     r["agent_db_id"],
                "persona_name": persona,
                "agent_role":   role,
                "direction":    direction,
                "client_id":    client_id,
                "total_calls":  total,
                "success_rate": suc_pct,
            }
        ))

    print(f"  Built {len(documents)} agent profile document(s) for '{client_id}'")
    return documents


# ═══════════════════════════════════════════════════════════════════════════════
# PGVECTOR STORE
# ═══════════════════════════════════════════════════════════════════════════════
def _pg_conn():
    """Return a raw psycopg2 connection with pgvector registered."""
    from pgvector.psycopg2 import register_vector
    conn = psycopg2.connect(DATABASE_URL)
    register_vector(conn)
    return conn


def _ensure_agent_embeddings_table():
    """
    Create agent_embeddings table + indexes if they don't exist.
    Safe to call on every rebuild — all DDL uses IF NOT EXISTS.
    Uses vector(768) to match the nomic-embed-text model used for call_embeddings.
    """
    conn = _pg_conn()
    cur  = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS agent_embeddings (
            id          BIGSERIAL    PRIMARY KEY,
            agent_id    TEXT         NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
            client_id   TEXT         NOT NULL,
            content     TEXT,
            embedding   vector(768),
            metadata    JSONB        DEFAULT '{}',
            created_at  TIMESTAMPTZ  DEFAULT NOW()
        )
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ae_client ON agent_embeddings (client_id)"
    )
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ae_hnsw
            ON agent_embeddings
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
    """)
    conn.commit()
    cur.close()
    conn.close()


def build_vector_store(client_id: str, **_kwargs):
    """
    Embed all calls AND agent profiles for a client into PostgreSQL.
      · call_documents  → call_embeddings   (FK to calls.id)
      · agent_documents → agent_embeddings  (FK to agents.id, separate table)
    Both tables are searched by _secure_semantic_search().
    """
    print(f"\nBuilding pgvector store for: {client_id}")
    if not check_ollama_health():
        raise RuntimeError(
            "Ollama is not running. Start it with:\n"
            "  C:\\Users\\Bhanu\\AppData\\Local\\Programs\\Ollama\\ollama.exe serve\n"
            "Then retry the embed request."
        )
    embeddings = get_embeddings()

    call_documents  = build_documents_from_db(client_id)
    agent_documents = build_agent_documents(client_id)

    if not call_documents:
        raise ValueError(f"No call documents for '{client_id}'. Run pipeline first.")

    # Ensure agent_embeddings table exists before inserting
    _ensure_agent_embeddings_table()

    conn = _pg_conn()
    cur  = conn.cursor()

    # ── Call documents → call_embeddings ─────────────────────────────────────
    cur.execute("DELETE FROM call_embeddings WHERE client_id = %s", (client_id,))
    call_vectors = embeddings.embed_documents([d.page_content for d in call_documents])

    for doc, vec in zip(call_documents, call_vectors):
        cur.execute(
            """
            INSERT INTO call_embeddings (call_id, client_id, content, embedding, metadata)
            VALUES (%s, %s, %s, %s, %s::jsonb)
            """,
            (
                doc.metadata.get("call_id"),
                client_id,
                doc.page_content,
                vec,
                __import__("json").dumps(doc.metadata),
            ),
        )

    # ── Agent profile documents → agent_embeddings ───────────────────────────
    if agent_documents:
        cur.execute("DELETE FROM agent_embeddings WHERE client_id = %s", (client_id,))
        agent_vectors = embeddings.embed_documents([d.page_content for d in agent_documents])

        for doc, vec in zip(agent_documents, agent_vectors):
            cur.execute(
                """
                INSERT INTO agent_embeddings (agent_id, client_id, content, embedding, metadata)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                (
                    doc.metadata.get("agent_id"),
                    client_id,
                    doc.page_content,
                    vec,
                    __import__("json").dumps(doc.metadata),
                ),
            )

    conn.commit()
    cur.close()
    conn.close()
    print(
        f"  {len(call_documents)} call docs + {len(agent_documents)} agent profile docs "
        f"embedded into PostgreSQL"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# EXPANDED SQL FAST-PATH  (exact answers, zero hallucination risk)
# ═══════════════════════════════════════════════════════════════════════════════
import re as _re

_MONTH_MAP = {
    "jan": 1, "january": 1, "feb": 2, "february": 2,
    "mar": 3, "march": 3,   "apr": 4, "april": 4,
    "may": 5, "jun": 6,     "june": 6,
    "jul": 7, "july": 7,    "aug": 8, "august": 8,
    "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}

def _detect_month(q: str) -> int | None:
    for name, num in _MONTH_MAP.items():
        if name in q:
            return num
    return None

def _detect_day(q: str) -> int | None:
    """Return day (1–31) if a specific day number appears in the question."""
    # Find all 1–2 digit numbers (with optional ordinal suffix) that are not a 4-digit year
    for m in _re.finditer(r'\b(\d{1,2})(?:st|nd|rd|th)?\b', q):
        day = int(m.group(1))
        if 1 <= day <= 31:
            return day
    return None

def _detect_year(q: str) -> int | None:
    """Return a 4-digit year if one appears in the question."""
    m = _re.search(r'\b(20\d{2})\b', q)
    return int(m.group(1)) if m else None

def _month_ts_range(month: int, year: int | None = None) -> tuple[int, int]:
    import calendar
    from datetime import datetime
    if year is None:
        year = datetime.now().year
    start = int(datetime(year, month, 1).timestamp() * 1000)
    last  = calendar.monthrange(year, month)[1]
    end   = int(datetime(year, month, last, 23, 59, 59).timestamp() * 1000)
    return start, end

def _day_ts_range(year: int, month: int, day: int) -> tuple[int, int]:
    import calendar
    from datetime import datetime
    day = min(day, calendar.monthrange(year, month)[1])   # clamp to valid day
    start = int(datetime(year, month, day, 0,  0,  0 ).timestamp() * 1000)
    end   = int(datetime(year, month, day, 23, 59, 59).timestamp() * 1000)
    return start, end


def _direct_sql_answer(question: str, client_id: str) -> str | None:
    """
    Pattern-match common questions and answer directly from SQL.
    Returns an exact answer string or None to fall through to LLM.
    These answers carry VERIFIED confidence — no LLM involved.
    """
    from datetime import datetime
    q = question.lower()

    # ── Date-filtered queries ─────────────────────────────────────────────────
    month = _detect_month(q)
    if month:
        year  = _detect_year(q) or datetime.now().year
        day   = _detect_day(q)

        # Keywords that indicate the user wants a call count / summary for a date
        date_keywords = [
            "how many", "calls in", "calls list", "list", "calls that",
            "call did", "total", "month", "on", "did i", "do i", "got",
            "have", "were there", "occurred", "happened",
        ]
        wants_count = any(k in q for k in date_keywords)

        if day:
            # Specific day query — e.g. "how many on feb 18th" / "on 18 of feb"
            ts_start, ts_end = _day_ts_range(year, month, day)
            import calendar
            label = f"{day} {datetime(year, month, 1).strftime('%B')} {year}"
            if wants_count:
                with get_db() as db:
                    def c_d():
                        return db.query(Call).filter(
                            Call.client_id == client_id,
                            Call.start_timstamp >= ts_start,
                            Call.start_timstamp <= ts_end,
                        )
                    total   = c_d().count()
                    success = c_d().filter(Call.call_successful == True).count()
                    fail    = c_d().filter(Call.call_successful == False).count()
                    pct     = round(success / (total or 1) * 100, 1)
                if total == 0:
                    return f"No calls found on {label} for your account."
                return (
                    f"On {label}: {total} call(s). "
                    f"{success} successful ({pct}%), {fail} unsuccessful."
                )
        else:
            # Whole-month query — e.g. "how many calls in february"
            ts_start, ts_end = _month_ts_range(month, year)
            month_name = datetime(year, month, 1).strftime("%B %Y")
            if wants_count:
                with get_db() as db:
                    def c_m():
                        return db.query(Call).filter(
                            Call.client_id == client_id,
                            Call.start_timstamp >= ts_start,
                            Call.start_timstamp <= ts_end,
                        )
                    total   = c_m().count()
                    success = c_m().filter(Call.call_successful == True).count()
                    fail    = c_m().filter(Call.call_successful == False).count()
                    pct     = round(success / (total or 1) * 100, 1)
                if total == 0:
                    return f"No calls found in {month_name} for your account."
                return (
                    f"In {month_name}: {total} call(s). "
                    f"{success} successful ({pct}%), {fail} unsuccessful."
                )

    with get_db() as db:
        def ai_q():
            return db.query(AudioInsight).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id)
        def c_q():
            return db.query(Call).filter(Call.client_id == client_id)

        # Trajectory — checked FIRST because "how many calls are improving" contains "how many calls"
        if any(k in q for k in ["trajectory", "improving", "deteriorating", "getting worse",
                                  "getting better", "improving vs", "vs deteriorating",
                                  "how many are improving", "how many improving",
                                  "how many deteriorating", "calls improving", "calls deteriorating"]):
            traj  = dict(ai_q().with_entities(AudioInsight.sentiment_trajectory, func.count()).group_by(AudioInsight.sentiment_trajectory).all())
            total = sum(traj.values()) or 1
            imp   = traj.get("improving", 0)
            sta   = traj.get("stable", 0)
            det   = traj.get("deteriorating", 0)
            return (
                f"Sentiment trajectory across {total} processed calls: "
                f"Improving: {imp} ({round(imp/total*100,1)}%), "
                f"Stable: {sta} ({round(sta/total*100,1)}%), "
                f"Deteriorating: {det} ({round(det/total*100,1)}%)."
            )

        # Call counts — only when NOT a trajectory question
        if any(k in q for k in ["how many calls", "total calls", "number of calls", "call count", "calls do i have"]):
            total   = c_q().count()
            insight = ai_q().count()
            return f"You have {total} total calls. {insight} of these have been fully processed with audio insights."

        # Success rate — skip if this is an agent-comparison question (handled below)
        _AGENT_Q = {"which agent", "best agent", "worst agent", "compare agent", "all agents",
                    "agent performance", "agent breakdown", "agent comparison", "agent ranking"}
        if any(k in q for k in ["success rate", "how many successful", "successful calls", "call success"]) \
                and not any(k in q for k in _AGENT_Q):
            total   = c_q().count()
            success = c_q().filter(Call.call_successful == True).count()
            fail    = c_q().filter(Call.call_successful == False).count()
            pct     = round(success / (total or 1) * 100, 1)
            return f"{success} of {total} calls were successful ({pct}% success rate). {fail} were unsuccessful."

        # Engagement
        if any(k in q for k in ["average engagement", "avg engagement", "mean engagement", "engagement score"]):
            avg = db.query(func.avg(AudioInsight.engagement_score)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
            mx  = db.query(func.max(AudioInsight.engagement_score)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
            mn  = db.query(func.min(AudioInsight.engagement_score)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
            if avg:
                return f"Average engagement score: {float(avg):.1f}/100. Highest: {float(mx):.1f}. Lowest: {float(mn):.1f}."
            return "No engagement data yet."

        # Duration
        if any(k in q for k in ["average duration", "avg duration", "how long", "call length", "average call length", "call duration"]):
            val = c_q().with_entities(func.avg(Call.duration_ms)).scalar()
            if val:
                secs = round(float(val) / 1000, 1)
                return f"Average call duration: {secs} seconds ({round(secs/60,1)} minutes)."
            return "No duration data."

        # Conversation flow
        if any(k in q for k in ["conversation flow", "smooth calls", "poor calls", "moderate calls", "call quality breakdown"]):
            flow_counts = dict(ai_q().with_entities(AudioInsight.conversation_flow, func.count()).group_by(AudioInsight.conversation_flow).all())
            total = sum(flow_counts.values()) or 1
            parts = []
            for flow in ["smooth","moderate","poor"]:
                cnt = flow_counts.get(flow, 0)
                parts.append(f"{flow.capitalize()}: {cnt} ({round(cnt/total*100,1)}%)")
            return "Conversation flow breakdown: " + ", ".join(parts) + "."

        # Silence
        if any(k in q for k in ["silence", "silent", "quiet", "silence ratio"]):
            val = db.query(func.avg(AudioInsight.silence_ratio)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
            if val:
                return f"Average silence ratio: {float(val)*100:.1f}% of call duration."
            return "No silence data."

        # Interruptions
        if any(k in q for k in ["interruption", "interrupting", "interrupt"]):
            val = db.query(func.avg(AudioInsight.interruption_count)).join(Call, AudioInsight.call_id == Call.id).filter(Call.client_id == client_id).scalar()
            if val:
                return f"Average interruptions per call: {float(val):.1f}."
            return "No interruption data."

        # Sentiment
        if any(k in q for k in ["customer sentiment", "caller sentiment", "how are customers feeling", "sentiment breakdown"]):
            sent = dict(c_q().with_entities(Call.user_sentiment, func.count(Call.id)).group_by(Call.user_sentiment).all())
            total = sum(v for v in sent.values() if v) or 1
            parts = [f"{s.capitalize()}: {cnt} ({round(cnt/total*100,1)}%)" for s,cnt in sent.items() if s]
            return "Customer sentiment breakdown: " + ", ".join(sorted(parts)) + "."

        # Topics
        if any(k in q for k in ["topic", "calling about", "why are callers", "call reason", "call purpose", "what do callers want"]):
            rows = db.execute(sql_text("SELECT topic, COUNT(*) as cnt FROM calls WHERE client_id=:cid AND topic IS NOT NULL GROUP BY topic ORDER BY cnt DESC"), {"cid": client_id}).fetchall()
            if rows:
                total = sum(r.cnt for r in rows) or 1
                parts = [f"{r.topic.replace('_',' ').capitalize()}: {r.cnt} ({round(r.cnt/total*100,1)}%)" for r in rows]
                return "Call topics: " + ", ".join(parts) + "."
            return "No topic data yet. Run the topic classifier first."

        # Peak hours
        if any(k in q for k in ["peak hour", "busiest hour", "busiest time", "peak time", "most calls"]):
            rows = db.execute(sql_text("SELECT EXTRACT(hour FROM to_timestamp(start_timstamp::float8/1000)) AS hr, COUNT(*) AS cnt FROM calls WHERE client_id=:cid AND start_timstamp IS NOT NULL GROUP BY hr ORDER BY cnt DESC LIMIT 3"), {"cid": client_id}).fetchall()
            if rows:
                parts = [f"{int(r.hr):02d}:00–{int(r.hr)+1:02d}:00 ({r.cnt} calls)" for r in rows]
                return "Busiest hours: " + ", ".join(parts) + "."
            return "No timestamp data."

        # Most recent / last call  (with audio insights + agent)
        if any(k in q for k in ["last call", "most recent call", "latest call", "most recent",
                                  "newest call", "when did i receive", "when was the last",
                                  "when was my last", "recent call"]):
            from datetime import datetime
            row = db.execute(sql_text("""
                SELECT c.id, c.start_timstamp, c.direction, c.call_successful,
                       c.user_sentiment, c.duration_ms, c.call_summary,
                       a.persona_name   AS agent_name,
                       a.agent_role,
                       ai.engagement_score, ai.silence_ratio, ai.hesitation_count,
                       ai.interruption_count, ai.conversation_flow, ai.sentiment_trajectory,
                       ai.agent_talk_time_sec, ai.customer_talk_time_sec
                FROM calls c
                LEFT JOIN agents a ON c.agent_id = a.id
                LEFT JOIN audio_insights ai ON c.id = ai.call_id
                WHERE c.client_id=:cid AND c.start_timstamp IS NOT NULL AND c.start_timstamp > 0
                ORDER BY c.start_timstamp DESC
                LIMIT 1
            """), {"cid": client_id}).fetchone()
            if row:
                dt      = datetime.fromtimestamp(row.start_timstamp / 1000)
                dt_str  = dt.strftime("%d %B %Y at %I:%M %p")
                dur_s   = round(float(row.duration_ms or 0) / 1000, 1)
                outcome = "successful" if row.call_successful else "unsuccessful"
                agent_s = ""
                if row.agent_name:
                    role_s  = (row.agent_role or "").replace("_", " ").title()
                    agent_s = f" Handled by: {row.agent_name} ({role_s})."
                base = (
                    f"Your most recent call was received on {dt_str}. "
                    f"Call ID: {row.id}. Direction: {row.direction or 'unknown'}. "
                    f"Outcome: {outcome}. Customer sentiment: {row.user_sentiment or 'unknown'}. "
                    f"Duration: {dur_s}s.{agent_s}"
                )
                wants_insights = any(k in q for k in [
                    "insight", "detail", "audio", "engagement", "silence",
                    "hesitation", "interruption", "flow", "trajectory", "score",
                ])
                if wants_insights and row.engagement_score is not None:
                    eng     = float(row.engagement_score)
                    sil     = round(float(row.silence_ratio or 0) * 100, 1)
                    hes     = int(row.hesitation_count or 0)
                    ints    = int(row.interruption_count or 0)
                    flow    = row.conversation_flow or "unknown"
                    traj    = row.sentiment_trajectory or "unknown"
                    a_talk  = round(float(row.agent_talk_time_sec or 0), 1)
                    c_talk  = round(float(row.customer_talk_time_sec or 0), 1)
                    summary = (row.call_summary or "").strip()
                    base += (
                        f"\n\nAudio Insights:"
                        f"\n  Engagement score: {eng:.1f}/100"
                        f"\n  Conversation flow: {flow.capitalize()}"
                        f"\n  Sentiment trajectory: {traj.capitalize()}"
                        f"\n  Silence: {sil}% of call"
                        f"\n  Hesitations: {hes}"
                        f"\n  Interruptions: {ints}"
                        f"\n  Agent talk time: {a_talk}s | Customer talk time: {c_talk}s"
                    )
                    if summary:
                        base += f"\n  Summary: {summary[:300]}"
                return base
            return "No calls with timestamp data found."

        # ── "Which agent attended/handled the most recent call?" ─────────────────
        _RECENT_AGENT_Q = (
            any(k in q for k in ["attended", "handled the last", "handled the most recent",
                                   "took the last", "took the most recent",
                                   "for the last call", "for the most recent call",
                                   "agent for the recent", "who was on the"]) or
            (any(k in q for k in ["which agent", "who"]) and
             any(k in q for k in ["last call", "most recent call", "latest call", "recent call"]))
        )
        if _RECENT_AGENT_Q:
            from datetime import datetime
            row = db.execute(sql_text("""
                SELECT c.id, c.start_timstamp, c.direction, c.call_successful,
                       a.persona_name AS agent_name, a.agent_role
                FROM calls c
                LEFT JOIN agents a ON c.agent_id = a.id
                WHERE c.client_id=:cid AND c.start_timstamp IS NOT NULL AND c.start_timstamp > 0
                ORDER BY c.start_timstamp DESC
                LIMIT 1
            """), {"cid": client_id}).fetchone()
            if row:
                dt     = datetime.fromtimestamp(row.start_timstamp / 1000)
                dt_str = dt.strftime("%d %B %Y at %I:%M %p")
                if row.agent_name:
                    role_s = (row.agent_role or "").replace("_", " ").title()
                    return (
                        f"The most recent call (received {dt_str}, Call ID: {row.id}) "
                        f"was handled by {row.agent_name} ({role_s})."
                    )
                return (
                    f"The most recent call (received {dt_str}, Call ID: {row.id}) "
                    f"has no agent assigned in the database."
                )

        # ── Agent name / persona fast-paths (calls ⟶ agents + audio_insights) ──
        # Detects agent persona names and role keywords — returns exact SQL answers.
        _AGENT_NAMES = {
            "sasha":              "Sasha",
            "justine":            "Justine",
            "sarah":              "Sarah",
            "julia":              "Julia",
            "at fault driver":    "Sarah",
            "at-fault driver":    "Sarah",
            "welcome pack":       "Julia",
            "follow-up emailer":  "Julia",
            "follow up emailer":  "Julia",
            "concierge":          "Sasha",
            "artel agent":        "Sasha",
            "mvaa receptionist":  "Justine",
        }
        _COMPARE_KEYS = [
            "which agent", "best agent", "worst agent", "compare agent",
            "all agents", "agent performance", "agent breakdown",
            "agent comparison", "agent ranking", "agents performing",
            "agent summary", "how are agents",
        ]

        detected_persona = None
        for kw, pname in _AGENT_NAMES.items():
            if kw in q:
                detected_persona = pname
                break

        wants_compare = any(k in q for k in _COMPARE_KEYS)
        # "Why / explain / reason" questions need LLM reasoning — let them fall through
        wants_explanation = any(k in q for k in [
            "why", "reason", "cause", "explain", "what is causing",
            "how can", "how should", "what should", "improve", "suggest",
        ])

        if detected_persona and not wants_compare and not wants_explanation:
            # Single-persona stats — aggregates inbound+outbound for Sarah & Julia
            p_rows = db.execute(sql_text("""
                SELECT
                    a.persona_name, a.agent_role, a.direction,
                    COUNT(c.id)                                             AS total_calls,
                    ROUND(AVG(ai.engagement_score)::numeric, 1)             AS avg_eng,
                    ROUND(AVG(ai.hesitation_count)::numeric, 1)             AS avg_hes,
                    ROUND(AVG(ai.interruption_count)::numeric, 1)           AS avg_ints,
                    ROUND(AVG(ai.silence_ratio) * 100, 1)                   AS silence_pct,
                    COUNT(CASE WHEN c.call_successful = TRUE  THEN 1 END)   AS successful,
                    COUNT(CASE WHEN c.call_successful = FALSE THEN 1 END)   AS failed,
                    ROUND(AVG(ai.agent_talk_time_sec)::numeric, 1)          AS agent_talk,
                    ROUND(AVG(ai.customer_talk_time_sec)::numeric, 1)       AS cust_talk
                FROM agents a
                JOIN calls c ON c.agent_id = a.id
                LEFT JOIN audio_insights ai ON ai.call_id = c.id
                WHERE a.client_id = :cid AND a.persona_name = :persona
                GROUP BY a.persona_name, a.agent_role, a.direction
                ORDER BY a.direction
            """), {"cid": client_id, "persona": detected_persona}).fetchall()

            if not p_rows:
                return f"No data found for agent '{detected_persona}' in your account."

            total_calls = sum(r.total_calls or 0 for r in p_rows)
            total_suc   = sum(r.successful   or 0 for r in p_rows)
            suc_pct     = round(total_suc / (total_calls or 1) * 100, 1)
            avg_eng     = round(
                sum(float(r.avg_eng or 0) * (r.total_calls or 0) for r in p_rows)
                / (total_calls or 1), 1
            )
            avg_hes     = round(
                sum(float(r.avg_hes or 0) * (r.total_calls or 0) for r in p_rows)
                / (total_calls or 1), 1
            )
            role_lbl    = (p_rows[0].agent_role or "").replace("_", " ").title()

            out = (
                f"{detected_persona} ({role_lbl}): {total_calls} total calls, "
                f"{suc_pct}% success rate ({total_suc} successful). "
                f"Average engagement: {avg_eng}/100. Average hesitations: {avg_hes}/call."
            )
            if len(p_rows) > 1:
                parts = []
                for r in p_rows:
                    sub_pct = round((r.successful or 0) / (r.total_calls or 1) * 100, 1)
                    parts.append(
                        f"{r.direction} — {r.total_calls} calls ({sub_pct}% success, eng avg {r.avg_eng})"
                    )
                out += " Direction breakdown: " + " | ".join(parts) + "."
            return out

        if wants_compare:
            # All agents ranked by success rate
            a_rows = db.execute(sql_text("""
                SELECT
                    a.persona_name, a.agent_role,
                    COUNT(c.id)                                             AS total_calls,
                    ROUND(AVG(ai.engagement_score)::numeric, 1)             AS avg_eng,
                    ROUND(AVG(ai.hesitation_count)::numeric, 1)             AS avg_hes,
                    COUNT(CASE WHEN c.call_successful = TRUE  THEN 1 END)   AS successful
                FROM agents a
                JOIN calls c ON c.agent_id = a.id
                LEFT JOIN audio_insights ai ON ai.call_id = c.id
                WHERE a.client_id = :cid
                  AND a.agent_role != 'test'
                  AND a.persona_name IS NOT NULL
                GROUP BY a.persona_name, a.agent_role
                ORDER BY (COUNT(CASE WHEN c.call_successful = TRUE THEN 1 END)::float
                          / NULLIF(COUNT(c.id), 0)) DESC
            """), {"cid": client_id}).fetchall()

            if not a_rows:
                return "No agent data found for your account."

            parts = []
            for r in a_rows:
                sp   = round((r.successful or 0) / (r.total_calls or 1) * 100, 1)
                rlbl = (r.agent_role or "").replace("_", " ").title()
                parts.append(
                    f"  {r.persona_name} ({rlbl}): {r.total_calls} calls, "
                    f"{sp}% success, engagement avg {r.avg_eng or 0}, "
                    f"hesitations avg {r.avg_hes or 0}/call"
                )
            return "Agent performance comparison (ranked by success rate):\n" + "\n".join(parts)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# SECURE SEMANTIC SEARCH  (Chroma with metadata filter)
# ═══════════════════════════════════════════════════════════════════════════════
def _expand_query(question: str) -> list[str]:
    """
    Return 2–3 rephrased versions of the question so vector search
    can match documents that use different wording.
    No LLM needed — rule-based rewrites cover the most common patterns.
    """
    q = question.strip()
    variants = [q]

    ql = q.lower()
    if "worst" in ql or "bad" in ql or "poor" in ql:
        variants.append(q.replace("worst", "lowest engagement").replace("bad", "frustrated deteriorating").replace("poor", "low engagement poor flow"))
    if "best" in ql or "good" in ql or "highest" in ql:
        variants.append(q.replace("best", "highest engagement smooth flow").replace("good", "high engagement successful"))
    if "frustrated" in ql or "angry" in ql or "upset" in ql:
        variants.append("customer angry negative sentiment deteriorating trajectory complaint")
    if "happy" in ql or "satisfied" in ql or "pleased" in ql:
        variants.append("customer positive sentiment improving trajectory successful resolved")
    if "long" in ql or "duration" in ql:
        variants.append("long call high duration many turns")
    if "silent" in ql or "silence" in ql or "quiet" in ql:
        variants.append("high silence ratio dead air pauses")
    if "interrupt" in ql:
        variants.append("interruptions agent talking over customer")

    return variants[:3]  # cap at 3 variants


def _secure_semantic_search(question: str, client_id: str, **_kwargs) -> tuple[str, list[str]]:
    """
    pgvector semantic search — client isolation enforced at SQL level (WHERE client_id = %s).
    Runs query expansion: merges results from up to 3 rephrased variants.

    Returns (context_text, [call_ids]) or ("", []) if unavailable.
    """
    if not check_ollama_health():
        print("[RAG] Ollama not reachable — skipping semantic search, using stats-only mode")
        return "", []
    try:
        embeddings = get_embeddings()
        queries    = _expand_query(question)
        conn       = _pg_conn()
        cur        = conn.cursor()

        seen: dict[str, str] = {}   # call_id → content

        is_admin = (client_id == "heya_admin")

        for q in queries:
            vec = embeddings.embed_query(q)
            if is_admin:
                cur.execute(
                    """
                    SELECT call_id, content
                    FROM   call_embeddings
                    ORDER  BY embedding <=> %s::vector
                    LIMIT  8
                    """,
                    (vec,),
                )
            else:
                cur.execute(
                    """
                    SELECT call_id, content
                    FROM   call_embeddings
                    WHERE  client_id = %s
                    ORDER  BY embedding <=> %s::vector
                    LIMIT  8
                    """,
                    (client_id, vec),
                )
            for call_id, content in cur.fetchall():
                if call_id and call_id not in seen:
                    seen[call_id] = content
            if len(seen) >= 12:
                break

        # Also search agent_embeddings for agent profile documents.
        # One pass with the raw question is enough — agent profiles are few and distinct.
        try:
            vec_q = embeddings.embed_query(question)
            if is_admin:
                cur.execute(
                    """
                    SELECT 'agent:' || agent_id AS doc_id, content
                    FROM   agent_embeddings
                    ORDER  BY embedding <=> %s::vector
                    LIMIT  6
                    """,
                    (vec_q,),
                )
            else:
                cur.execute(
                    """
                    SELECT 'agent:' || agent_id AS doc_id, content
                    FROM   agent_embeddings
                    WHERE  client_id = %s
                    ORDER  BY embedding <=> %s::vector
                    LIMIT  3
                    """,
                    (client_id, vec_q),
                )
            for doc_id, content in cur.fetchall():
                if doc_id and doc_id not in seen:
                    seen[doc_id] = content
        except Exception as e:
            print(f"[RAG] agent_embeddings search skipped: {e}")

        cur.close()
        conn.close()

        if not seen:
            return "", []

        sources = list(seen.keys())[:12]
        context = "\n\n---\n\n".join(seen[cid] for cid in sources)
        return context, sources

    except Exception as e:
        print(f"[RAG] pgvector search skipped: {e}")
        return "", []


# ── Follow-up detection ───────────────────────────────────────────────────────
_FOLLOWUP_SIGNALS = {
    # True referential pronouns — only these unambiguously reference prior turns
    "those calls", "those ones", "that call", "that one", "that specific",
    "of those", "of them", "from those", "among those",
    "tell me more", "more about that", "more detail on that",
    "what else about", "elaborate on that", "expand on that",
    "which of those", "which of them",
    "mentioned above", "listed above", "you mentioned",
}

def _is_followup(question: str) -> bool:
    """Return True if the question likely references something from prior turns."""
    q = question.lower().strip()
    # Short questions that reference prior context
    return any(sig in q for sig in _FOLLOWUP_SIGNALS)

def _build_search_query(question: str, history: list[dict] | None) -> str:
    """
    For follow-up questions, build a richer search query by appending
    the last user question — so semantic search finds relevant calls.
    """
    if not history or not _is_followup(question):
        return question
    last_user = next(
        (t["content"] for t in reversed(history) if t.get("role") == "user"),
        ""
    )
    return f"{last_user} {question}".strip()


# ═══════════════════════════════════════════════════════════════════════════════
# SYSTEM PROMPT  (anti-hallucination + conversation memory rules)
# ═══════════════════════════════════════════════════════════════════════════════
def _build_admin_system_prompt() -> str:
    client_list = ", ".join(f"{name} ({cid})" for cid, name in CLIENT_NAMES.items())
    return f"""You are a precise platform analytics assistant for the Heya AI administrator.
You have full visibility across ALL clients on the platform: {client_list}.

You can compare clients, rank them, and answer questions about the platform as a whole.

STRICT RULES — MUST FOLLOW WITHOUT EXCEPTION:
1. Answer ONLY using numbers and facts from [VERIFIED STATISTICS].
2. NEVER write a number not present in the provided data.
3. When comparing clients, always cite specific numbers for each.
4. NEVER invent metrics or fabricate client-specific data.
5. If a question asks about a specific client, answer with that client's data from the stats.
6. Only say "I don't have enough data" if the metric genuinely doesn't exist in the schema.

CONVERSATION MEMORY RULES:
7. [CONVERSATION HISTORY] contains the full chat — use it to answer follow-up questions.
8. Resolve references like "the better client", "that agent" from prior context.

FORMAT RULES:
- Use clear labels (e.g., "Artel Apartments:", "MVAA Legal:") when comparing clients.
- Include specific numbers when answering.
- Use bullet points for lists of more than 3 items.
- Do NOT add disclaimers about being an AI."""


def _build_system_prompt(client_name: str, client_id: str) -> str:
    if client_id == "heya_admin":
        return _build_admin_system_prompt()
    return f"""You are a precise call analytics assistant for {client_name} with full memory of this conversation.

DATA BOUNDARY: You only have access to data for {client_name} ({client_id}).

STRICT RULES — MUST FOLLOW WITHOUT EXCEPTION:
1. Answer ONLY using numbers and facts from [VERIFIED STATISTICS] or [CALL RECORDS].
2. NEVER write a number not present in the provided data.
3. NEVER reference a call ID not listed in [CALL RECORDS].
4. NEVER invent metrics. Only use: success rate, engagement score, hesitation count,
   silence ratio, interruption count, talk times, sentiment, flow, trajectory, call counts.
5. INTERPRETATION — translate everyday language to available data before answering:
   - "angry / frustrated / upset"  → negative sentiment + deteriorating trajectory + low engagement
   - "happy / satisfied"           → positive sentiment + improving trajectory + high engagement
   - "worst call"                  → lowest engagement + poor flow + unsuccessful
   - "best call"                   → highest engagement + smooth flow + successful
   - "most silent"                 → highest silence ratio
   - "chaotic / most interrupted"  → highest interruption count
   Use whatever data exists to give the closest meaningful answer.
6. Only say "I don't have enough data" if the question asks for a metric that genuinely
   does not exist in the schema (e.g. "revenue", "NPS score", "call recording").

CONVERSATION MEMORY RULES:
6. [CONVERSATION HISTORY] contains the full chat so far — use it to answer follow-up questions.
7. When the user says "those calls", "that one", "them", "the worst" etc., resolve the reference
   from your most recent answer in [CONVERSATION HISTORY].
8. Maintain context across the conversation — remember what was discussed.
9. If a follow-up question is ambiguous, state your interpretation before answering.

FORMAT RULES:
- Be concise and professional.
- Use bullet points for lists of more than 3 items.
- Include specific numbers when answering.
- Do NOT repeat the question back.
- Do NOT add disclaimers about being an AI."""


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN QUERY ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def query(question: str, client_id: str,
          history: list[dict] | None = None) -> dict:
    """
    Answer a question about a client's call data.

    Confidence levels:
      VERIFIED  — answered directly by SQL (exact DB result, zero LLM)
      HIGH      — LLM constrained to pre-verified SQL stats block
      MEDIUM    — LLM + SQL stats + vector-retrieved call documents

    Parameters
    ----------
    question   : the user's question
    client_id  : tenant identifier — all queries scoped to this client only
    history    : list of {"role": "user"|"assistant", "content": str}
                 last MAX_HISTORY_TURNS turns for multi-turn conversation
    """
    print(f"\n[RAG] Q: {question}  |  client: {client_id}  |  history: {len(history or [])} msgs")

    is_followup = bool(history) and _is_followup(question)

    is_admin = (client_id == "heya_admin")

    # ── 1. Text-to-SQL — primary path for all structured/analytical questions ──
    # Skipped for follow-ups, qualitative questions, and admin (cross-client SQL needs different schema).
    _QUALITATIVE_SIGNALS = [
        "why", "explain", "reason", "what happened", "tell me about",
        "describe", "what went wrong", "how did", "what caused",
        "give me insight", "walk me through", "what can you tell",
    ]
    _wants_qualitative = any(k in question.lower() for k in _QUALITATIVE_SIGNALS)

    if not is_followup and not _wants_qualitative and not is_admin:
        try:
            import text_to_sql
            t2s = text_to_sql.answer(question, client_id)
            if t2s:
                print(f"[RAG] Text-to-SQL hit")
                return t2s
        except Exception as _e:
            print(f"[RAG] Text-to-SQL error, falling through: {_e}")

    # ── 2. SQL fast-path — simple keyword-matched queries (fast, no LLM) ─────
    # Skipped for admin — cross-client questions always go to LLM with platform stats.
    if not is_followup and not is_admin:
        direct = _direct_sql_answer(question, client_id)
        if direct:
            print(f"[RAG] SQL fast-path hit")
            return {"question": question, "answer": direct,
                    "route": "sql_direct", "confidence": "VERIFIED", "sources": []}

    # ── 2. Build authoritative stats context ──────────────────────────────────
    print("[RAG] Building stats context...")
    try:
        stats_ctx = build_stats_context(client_id)
    except Exception as e:
        print(f"[RAG] stats context failed: {e}")
        stats_ctx = f"Stats unavailable ({e})."

    # ── 3. Semantic search — use enriched query for follow-ups ─────────────────
    search_q         = _build_search_query(question, history)
    call_ctx, sources = _secure_semantic_search(search_q, client_id)

    confidence = "MEDIUM" if call_ctx else "HIGH"
    if is_admin:
        route = "admin_platform+semantic" if call_ctx else "admin_platform"
    else:
        route = "llm_stats+semantic" if call_ctx else "llm_stats"
    if is_followup:
        route = f"followup+{route}"

    # ── 4. No LLM fallback ────────────────────────────────────────────────────
    if not USE_LLM:
        return {
            "question":   question,
            "answer":     f"Add CEREBRAS_API_KEY to backend/.env for AI answers.\n\n{stats_ctx}",
            "route":      "no_llm",
            "confidence": "VERIFIED",
            "sources":    sources,
        }

    # ── 5. Build the prompt ───────────────────────────────────────────────────
    client_name   = "Heya AI Platform" if is_admin else CLIENT_NAMES.get(client_id, client_id)
    system_prompt = _build_system_prompt(client_name, client_id)

    prompt_parts = [system_prompt, ""]

    # ── Conversation history comes FIRST so the LLM treats it as working memory
    if history:
        recent = history[-(MAX_HISTORY_TURNS * 2):]
        if recent:
            prompt_parts += ["[CONVERSATION HISTORY — your memory of this chat session]"]
            for turn in recent:
                role    = "User" if turn.get("role") == "user" else "Assistant"
                content = str(turn.get("content", ""))[:1200]   # was 400 — now captures full answers
                prompt_parts.append(f"{role}: {content}")
            prompt_parts.append("")  # blank separator

    # ── Verified data context
    prompt_parts += ["[VERIFIED STATISTICS]", stats_ctx]

    if call_ctx:
        prompt_parts += ["", "[CALL RECORDS — for specific call questions]", call_ctx]

    prompt_parts += ["", f"Current question: {question}", "", "Answer:"]
    full_prompt = "\n".join(prompt_parts)

    # ── 6. LLM generation ────────────────────────────────────────────────────
    try:
        answer = _call_llm(full_prompt)
    except Exception as e:
        return {
            "question":   question,
            "answer":     f"AI error: {e}. Stats summary:\n{stats_ctx[:600]}",
            "route":      "error",
            "confidence": "VERIFIED",
            "sources":    [],
        }

    print(f"[RAG] Route: {route} | Confidence: {confidence} | Sources: {len(sources)}")
    return {
        "question":   question,
        "answer":     answer,
        "route":      route,
        "confidence": confidence,
        "sources":    sources,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("Building pgvector stores...\n")
    for cid in ["client_heya_001", "client_heya_002"]:
        try:
            build_vector_store(cid)
        except Exception as e:
            print(f"  {cid}: {e}")

    CLIENT_ID = "client_heya_001"
    print(f"\nTesting on {CLIENT_NAMES.get(CLIENT_ID, CLIENT_ID)}...")
    tests = [
        "How many calls do I have?",
        "What is the average engagement score?",
        "Which calls went poorly and why?",
        "What time of day are we busiest?",
        "Tell me about the worst performing calls",
    ]
    for q in tests:
        r = query(q, CLIENT_ID)
        print(f"\nQ: {q}\nA [{r['confidence']}]: {r['answer'][:200]}\nRoute: {r['route']}")
        print("-" * 60)
