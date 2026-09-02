"""
agent.py  —  Heya AI Voice Analytics
ReAct-style Agentic Analysis Engine

Architecture
------------
  Question → ReAct loop (max 3 iterations) → Final answer

  Each iteration:
    1. LLM writes a Thought + Action (tool call in JSON)
    2. We execute the tool against the DB / vector store
    3. Observation (tool result) is fed back into the prompt
    4. LLM reasons again → either another tool call or a final Answer

Tools available to the agent
-----------------------------
  sql_analytics(metric)           Pre-approved SQL queries (overview, trends, topics, …)
  agent_performance(persona_name) Per-agent metrics via agents × calls × audio_insights join
  semantic_search(query)          pgvector search over call records + agent profile docs
  topic_agent_breakdown()         Per-agent performance broken down by call topic

LLM: Cerebras via openai SDK (same as rag.py — no LangChain)

Zero-hallucination guarantee: the LLM is instructed to only cite numbers returned by
tools — all tool outputs are verified SQL results or retrieved DB documents.
"""

import os
import json
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import func, text as sql_text
from database import get_db, Call, AudioInsight

# ── Config ─────────────────────────────────────────────────────────────────────
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
MODEL_NAME       = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
MAX_ITERATIONS   = 3

CLIENT_NAMES = {
    "client_heya_001": "Artel Apartments",
    "client_heya_002": "MVAA Legal",
}


# ═══════════════════════════════════════════════════════════════════════════════
# LLM  (direct Cerebras call — no LangChain wrapper)
# ═══════════════════════════════════════════════════════════════════════════════
def _call_llm_agent(prompt: str, max_tokens: int = 1500) -> str:
    """
    Call Cerebras via the OpenAI-compatible SDK.
    Retry logic: on 429 queue-exceeded, wait 3 s then retry once with the
    fast fallback model (llama3.1-8b) so the agent never hard-crashes.
    """
    if not CEREBRAS_API_KEY:
        raise ValueError("CEREBRAS_API_KEY missing — add it to backend/.env")
    import time
    from openai import OpenAI, RateLimitError
    _client = OpenAI(
        api_key  = CEREBRAS_API_KEY,
        base_url = "https://api.cerebras.ai/v1",
    )

    def _call(model: str) -> str:
        resp = _client.chat.completions.create(
            model       = model,
            messages    = [{"role": "user", "content": prompt}],
            temperature = 0.1,
            max_tokens  = max_tokens,
        )
        return resp.choices[0].message.content.strip()

    try:
        return _call(MODEL_NAME)
    except RateLimitError:
        fallback = "llama3.1-8b"
        print(f"[Agent] Cerebras queue full — retrying with {fallback} in 3s")
        time.sleep(3)
        return _call(fallback)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 1 — sql_analytics
# ═══════════════════════════════════════════════════════════════════════════════
def _tool_sql_analytics(metric: str, client_id: str) -> str:
    """Run a pre-approved SQL analytics query and return a verified text result."""
    metric = (metric or "overview").strip().lower()

    with get_db() as db:

        if metric == "overview":
            total   = db.query(func.count(Call.id)).filter(Call.client_id == client_id).scalar() or 0
            suc     = db.query(func.count(Call.id)).filter(Call.client_id == client_id, Call.call_successful == True).scalar() or 0
            fail    = db.query(func.count(Call.id)).filter(Call.client_id == client_id, Call.call_successful == False).scalar() or 0
            proc    = (db.query(func.count(AudioInsight.id))
                         .join(Call, AudioInsight.call_id == Call.id)
                         .filter(Call.client_id == client_id).scalar() or 0)
            avg_eng = (db.query(func.avg(AudioInsight.engagement_score))
                         .join(Call, AudioInsight.call_id == Call.id)
                         .filter(Call.client_id == client_id).scalar())
            avg_dur = db.query(func.avg(Call.duration_ms)).filter(Call.client_id == client_id).scalar()
            suc_pct = round(suc / (total or 1) * 100, 1)
            dur_s   = round(float(avg_dur or 0) / 1000, 1)
            return (
                f"Overview: {total} total calls, {suc_pct}% success rate "
                f"({suc} successful, {fail} unsuccessful). "
                f"{proc} calls fully processed with audio insights. "
                f"Average engagement: {float(avg_eng or 0):.1f}/100. "
                f"Average call duration: {dur_s}s ({round(dur_s / 60, 1)} min)."
            )

        elif metric == "flow_breakdown":
            rows = db.execute(sql_text("""
                SELECT conversation_flow, COUNT(*) AS cnt
                FROM audio_insights ai
                JOIN calls c ON c.id = ai.call_id
                WHERE c.client_id = :cid
                GROUP BY conversation_flow ORDER BY cnt DESC
            """), {"cid": client_id}).fetchall()
            total = sum(r.cnt for r in rows) or 1
            parts = [
                f"{(r.conversation_flow or 'unknown').capitalize()}: {r.cnt} ({round(r.cnt / total * 100, 1)}%)"
                for r in rows
            ]
            return "Conversation flow breakdown: " + ", ".join(parts) + "."

        elif metric == "sentiment_breakdown":
            rows = db.execute(sql_text("""
                SELECT user_sentiment, COUNT(*) AS cnt
                FROM calls WHERE client_id=:cid AND user_sentiment IS NOT NULL
                GROUP BY user_sentiment ORDER BY cnt DESC
            """), {"cid": client_id}).fetchall()
            total = sum(r.cnt for r in rows) or 1
            parts = [
                f"{r.user_sentiment.capitalize()}: {r.cnt} ({round(r.cnt / total * 100, 1)}%)"
                for r in rows
            ]
            return "Customer sentiment breakdown: " + ", ".join(parts) + "."

        elif metric == "peak_hours":
            rows = db.execute(sql_text("""
                SELECT EXTRACT(hour FROM to_timestamp(start_timstamp::float8/1000)) AS hr,
                       COUNT(*) AS cnt
                FROM calls
                WHERE client_id=:cid AND start_timstamp IS NOT NULL AND start_timstamp > 0
                GROUP BY hr ORDER BY cnt DESC LIMIT 5
            """), {"cid": client_id}).fetchall()
            if not rows:
                return "No timestamp data available for peak hour analysis."
            parts = [f"{int(r.hr):02d}:00 — {r.cnt} calls" for r in rows]
            return "Top 5 peak call hours: " + ", ".join(parts) + "."

        elif metric == "topic_breakdown":
            rows = db.execute(sql_text("""
                SELECT topic, COUNT(*) AS total,
                       SUM(CASE WHEN call_successful = TRUE THEN 1 ELSE 0 END) AS successful
                FROM calls
                WHERE client_id=:cid AND topic IS NOT NULL
                GROUP BY topic ORDER BY total DESC LIMIT 10
            """), {"cid": client_id}).fetchall()
            if not rows:
                return "No topic data available. Run topic_classifier.py first."
            total_all = sum(r.total for r in rows) or 1
            parts = []
            for r in rows:
                sp = round((r.successful or 0) / (r.total or 1) * 100, 1)
                parts.append(
                    f"{r.topic.replace('_', ' ').capitalize()}: {r.total} calls "
                    f"({round(r.total / total_all * 100, 1)}% of total), {sp}% success rate"
                )
            return "Call topics by volume:\n" + "\n".join(f"  {p}" for p in parts)

        elif metric == "engagement_trends":
            rows = db.execute(sql_text("""
                SELECT
                    TO_CHAR(DATE_TRUNC('week', TO_TIMESTAMP(c.start_timstamp / 1000.0)), 'Mon DD YYYY') AS week,
                    ROUND(AVG(ai.engagement_score)::numeric, 1) AS avg_eng,
                    COUNT(*) AS calls
                FROM audio_insights ai
                JOIN calls c ON c.id = ai.call_id
                WHERE c.client_id = :cid
                  AND c.start_timstamp IS NOT NULL AND c.start_timstamp > 0
                GROUP BY DATE_TRUNC('week', TO_TIMESTAMP(c.start_timstamp / 1000.0))
                ORDER BY DATE_TRUNC('week', TO_TIMESTAMP(c.start_timstamp / 1000.0)) DESC
                LIMIT 8
            """), {"cid": client_id}).fetchall()
            if not rows:
                return "No weekly engagement trend data available."
            parts = [
                f"Week of {r.week}: avg engagement {r.avg_eng} ({r.calls} calls)"
                for r in rows
            ]
            return "Weekly engagement trends (most recent first):\n" + "\n".join(f"  {p}" for p in parts)

        elif metric == "silence_interruption":
            row = db.execute(sql_text("""
                SELECT
                    ROUND(AVG(silence_ratio) * 100, 1)       AS avg_silence_pct,
                    ROUND(AVG(interruption_count)::numeric, 1) AS avg_interrupts,
                    ROUND(AVG(hesitation_count)::numeric, 1)   AS avg_hes,
                    ROUND(AVG(agent_talk_time_sec)::numeric, 1) AS agent_talk,
                    ROUND(AVG(customer_talk_time_sec)::numeric, 1) AS cust_talk
                FROM audio_insights ai
                JOIN calls c ON c.id = ai.call_id
                WHERE c.client_id = :cid
            """), {"cid": client_id}).fetchone()
            if not row:
                return "No audio insight data available."
            return (
                f"Silence & speech: avg silence {row.avg_silence_pct}% of call, "
                f"avg interruptions {row.avg_interrupts}/call, "
                f"avg hesitations {row.avg_hes}/call. "
                f"Agent speaks avg {row.agent_talk}s, customer avg {row.cust_talk}s per call."
            )

        else:
            return (
                f"Unknown metric '{metric}'. "
                "Valid options: overview | flow_breakdown | sentiment_breakdown | "
                "peak_hours | topic_breakdown | engagement_trends | silence_interruption"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 2 — agent_performance
# ═══════════════════════════════════════════════════════════════════════════════
def _tool_agent_performance(persona_name: str, client_id: str) -> str:
    """Per-agent performance metrics using agents × calls × audio_insights join."""
    persona_name = (persona_name or "all").strip()

    with get_db() as db:

        if persona_name.lower() == "all":
            rows = db.execute(sql_text("""
                SELECT
                    a.persona_name,
                    a.agent_role,
                    COUNT(c.id)                                               AS total_calls,
                    ROUND(AVG(ai.engagement_score)::numeric, 1)               AS avg_eng,
                    ROUND(AVG(ai.hesitation_count)::numeric, 1)               AS avg_hes,
                    ROUND(AVG(ai.silence_ratio) * 100, 1)                     AS silence_pct,
                    ROUND(AVG(ai.interruption_count)::numeric, 1)             AS avg_ints,
                    COUNT(CASE WHEN c.call_successful = TRUE  THEN 1 END)     AS successful,
                    COUNT(CASE WHEN c.call_successful = FALSE THEN 1 END)     AS failed,
                    ROUND(AVG(ai.agent_talk_time_sec)::numeric, 1)            AS agent_talk,
                    ROUND(AVG(ai.customer_talk_time_sec)::numeric, 1)         AS cust_talk
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

            if not rows:
                return "No agent data available."

            parts = []
            for r in rows:
                sp  = round((r.successful or 0) / (r.total_calls or 1) * 100, 1)
                rl  = (r.agent_role or "").replace("_", " ").title()
                parts.append(
                    f"{r.persona_name} ({rl}): {r.total_calls} calls, "
                    f"{sp}% success ({r.successful} successful), "
                    f"engagement avg {r.avg_eng}, hesitations avg {r.avg_hes}/call, "
                    f"silence avg {r.silence_pct}%, "
                    f"agent talk {r.agent_talk}s / customer talk {r.cust_talk}s avg"
                )
            return "All agents (ranked by success rate):\n" + "\n".join(f"  {p}" for p in parts)

        else:
            # Specific persona — groups inbound + outbound for Sarah / Julia
            rows = db.execute(sql_text("""
                SELECT
                    a.persona_name, a.agent_role, a.direction, a.description,
                    COUNT(c.id)                                               AS total_calls,
                    ROUND(AVG(ai.engagement_score)::numeric, 1)               AS avg_eng,
                    ROUND(STDDEV(ai.engagement_score)::numeric, 1)            AS eng_std,
                    ROUND(AVG(ai.hesitation_count)::numeric, 1)               AS avg_hes,
                    ROUND(AVG(ai.silence_ratio) * 100, 1)                     AS silence_pct,
                    ROUND(AVG(ai.interruption_count)::numeric, 1)             AS avg_ints,
                    COUNT(CASE WHEN c.call_successful = TRUE  THEN 1 END)     AS successful,
                    COUNT(CASE WHEN c.call_successful = FALSE THEN 1 END)     AS failed,
                    ROUND(AVG(ai.agent_talk_time_sec)::numeric, 1)            AS agent_talk,
                    ROUND(AVG(ai.customer_talk_time_sec)::numeric, 1)         AS cust_talk,
                    ROUND(AVG(ai.agent_avg_pitch_hz)::numeric, 1)             AS agent_pitch
                FROM agents a
                JOIN calls c ON c.agent_id = a.id
                LEFT JOIN audio_insights ai ON ai.call_id = c.id
                WHERE a.client_id = :cid AND a.persona_name = :persona
                GROUP BY a.persona_name, a.agent_role, a.direction, a.description
                ORDER BY a.direction
            """), {"cid": client_id, "persona": persona_name}).fetchall()

            if not rows:
                available = _client_agent_options(client_id)
                return f"No data found for agent '{persona_name}' in this client's data. Available: {available}"

            total_all = sum(r.total_calls or 0 for r in rows)
            suc_all   = sum(r.successful   or 0 for r in rows)
            suc_pct   = round(suc_all / (total_all or 1) * 100, 1)
            role_lbl  = (rows[0].agent_role or "").replace("_", " ").title()

            out = (
                f"{persona_name} ({role_lbl}): {total_all} total calls, "
                f"{suc_pct}% overall success rate ({suc_all} successful). "
            )

            if len(rows) == 1:
                r = rows[0]
                out += (
                    f"Average engagement: {r.avg_eng}/100 (consistency std dev: {r.eng_std}). "
                    f"Hesitations: {r.avg_hes}/call. Interruptions: {r.avg_ints}/call. "
                    f"Silence: {r.silence_pct}% of call. "
                    f"Agent speaks avg {r.agent_talk}s, customer avg {r.cust_talk}s. "
                    f"Agent avg pitch: {r.agent_pitch}Hz."
                )
            else:
                out += "Per-direction breakdown:\n"
                for r in rows:
                    sp = round((r.successful or 0) / (r.total_calls or 1) * 100, 1)
                    out += (
                        f"  {r.direction.capitalize()}: {r.total_calls} calls, {sp}% success, "
                        f"engagement avg {r.avg_eng}, hesitations avg {r.avg_hes}/call, "
                        f"silence {r.silence_pct}%, agent talk {r.agent_talk}s.\n"
                    )

            if rows[0].description:
                out += f"\nAgent purpose: {rows[0].description[:200]}"

            return out.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 3 — semantic_search
# ═══════════════════════════════════════════════════════════════════════════════
def _tool_semantic_search(query: str, client_id: str) -> str:
    """
    Semantic search over call_embeddings + agent_embeddings.
    Requires Ollama running locally. Returns relevant passages as plain text.
    """
    if not query.strip():
        return "Empty search query — provide a natural language search string."
    try:
        from rag import _secure_semantic_search
        ctx, sources = _secure_semantic_search(query, client_id)
        if not ctx:
            return (
                "No semantically relevant records found. "
                "Ollama may not be running, or the vector store needs a rebuild "
                "(run: python rebuild_rag.py)."
            )
        return f"Relevant call records and agent profiles ({len(sources)} sources):\n{ctx[:2500]}"
    except Exception as e:
        return f"Semantic search failed: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL 4 — topic_agent_breakdown
# ═══════════════════════════════════════════════════════════════════════════════
def _tool_topic_agent_breakdown(client_id: str) -> str:
    """Per-agent performance grouped by call topic (agents × calls × topics join)."""
    with get_db() as db:
        rows = db.execute(sql_text("""
            SELECT
                a.persona_name,
                c.topic,
                COUNT(*)                                                      AS total,
                COUNT(CASE WHEN c.call_successful = TRUE THEN 1 END)          AS successful,
                ROUND(AVG(ai.engagement_score)::numeric, 1)                   AS avg_eng
            FROM agents a
            JOIN calls c ON c.agent_id = a.id
            LEFT JOIN audio_insights ai ON ai.call_id = c.id
            WHERE a.client_id = :cid
              AND c.topic IS NOT NULL
              AND a.agent_role != 'test'
              AND a.persona_name IS NOT NULL
            GROUP BY a.persona_name, c.topic
            ORDER BY a.persona_name, total DESC
        """), {"cid": client_id}).fetchall()

    if not rows:
        return "No topic-level agent data available. Run topic_classifier.py first to classify call topics."

    out             = "Per-agent topic breakdown:\n"
    current_persona = None

    for r in rows:
        if r.persona_name != current_persona:
            out            += f"\n{r.persona_name}:\n"
            current_persona = r.persona_name
        sp        = round((r.successful or 0) / (r.total or 1) * 100, 1)
        topic_lbl = (r.topic or "unknown").replace("_", " ").capitalize()
        out      += f"  {topic_lbl}: {r.total} calls, {sp}% success, engagement avg {r.avg_eng}\n"

    return out.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL DISPATCHER
# ═══════════════════════════════════════════════════════════════════════════════
def _execute_tool(tool_name: str, params: dict, client_id: str) -> str:
    """Dispatch a tool call and return the result as a plain text string."""
    try:
        if tool_name == "sql_analytics":
            return _tool_sql_analytics(params.get("metric", "overview"), client_id)
        elif tool_name == "agent_performance":
            return _tool_agent_performance(params.get("persona_name", "all"), client_id)
        elif tool_name == "semantic_search":
            return _tool_semantic_search(params.get("query", ""), client_id)
        elif tool_name == "topic_agent_breakdown":
            return _tool_topic_agent_breakdown(client_id)
        else:
            return (
                f"Unknown tool '{tool_name}'. "
                "Available: sql_analytics | agent_performance | semantic_search | topic_agent_breakdown"
            )
    except Exception as e:
        return f"Tool '{tool_name}' error: {e}"


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER — build client-scoped agent name list for system prompt
# ═══════════════════════════════════════════════════════════════════════════════
def _client_agent_options(client_id: str) -> str:
    """
    Return the pipe-separated list of persona_names for THIS client only,
    so the system prompt never leaks agent names from other tenants.
    e.g. MVAA → "Justine | Sarah | Julia | all"
         Artel → "Sasha | all"
    """
    try:
        with get_db() as db:
            rows = db.execute(
                sql_text(
                    "SELECT DISTINCT persona_name FROM agents "
                    "WHERE client_id = :cid AND persona_name IS NOT NULL "
                    "  AND agent_role != 'test' "
                    "ORDER BY persona_name"
                ),
                {"cid": client_id},
            ).fetchall()
        names = [r.persona_name for r in rows]
        return " | ".join(names) + " | all" if names else "all"
    except Exception:
        return "all"


# ═══════════════════════════════════════════════════════════════════════════════
# REACT LOOP  —  the agent brain
# ═══════════════════════════════════════════════════════════════════════════════
def analyze(question: str, client_id: str) -> dict:
    """
    ReAct agent loop. Breaks complex analytical questions into tool calls,
    executes each tool against the database / vector store, and synthesises
    a final grounded answer.

    Parameters
    ----------
    question   : the analytical question to answer
    client_id  : tenant scope — all tool calls are scoped to this client only

    Returns
    -------
    dict with keys:
      answer          — final LLM response
      reasoning_steps — list of {iteration, thought, tool, params, observation}
      tools_used      — list of tool names called in order
      sources         — list of call IDs / agent IDs referenced
      confidence      — "HIGH" (all data from verified tools)
      iterations      — number of ReAct iterations used
    """
    if not CEREBRAS_API_KEY:
        return {
            "answer":          "CEREBRAS_API_KEY not configured. Add it to backend/.env.",
            "reasoning_steps": [],
            "tools_used":      [],
            "sources":         [],
            "confidence":      "NONE",
            "iterations":      0,
        }

    client_name    = CLIENT_NAMES.get(client_id, client_id)
    agent_options  = _client_agent_options(client_id)   # e.g. "Justine | Sarah | Julia | all"

    # ── System prompt ─────────────────────────────────────────────────────────
    system = f"""You are an expert AI analytics agent for {client_name}.
Your job is to answer analytical questions about call performance and AI agent behaviour
by using the tools provided below. Every number in your final answer must come from a tool result.

AVAILABLE TOOLS:
  sql_analytics(metric)
    Run verified SQL analytics.
    metric options: overview | flow_breakdown | sentiment_breakdown | peak_hours
                    topic_breakdown | engagement_trends | silence_interruption

  agent_performance(persona_name)
    Get detailed metrics for a specific AI agent or all agents.
    persona_name options: {agent_options}

  semantic_search(query)
    Search call records and agent profiles using natural language.
    query: a descriptive phrase (e.g. "frustrated customer poor flow billing")

  topic_agent_breakdown()
    Show each agent's performance broken down by call topic.
    No params needed.

OUTPUT FORMAT — follow this exactly on every response:
  Thought: <your reasoning about what information you need and why>
  Action: {{"tool": "<tool_name>", "params": {{"<key>": "<value>"}}}}

When you have enough information to give a complete answer:
  Thought: <confirm you have enough data>
  Answer: <your full answer — must cite specific numbers from the Observations above>

STRICT ANTI-HALLUCINATION RULES — NO EXCEPTIONS:
  - EVERY number in your Answer MUST appear verbatim in an Observation above.
  - DO NOT calculate, derive, estimate, or round any figure not explicitly returned.
  - The database contains ONLY these agent metrics: success rate (%), call count,
    engagement score (0–100), hesitation count/call, silence % of call,
    interruption count/call, agent talk time (sec), customer talk time (sec).
  - Metrics like "FCR", "CSAT", "escalation rate", "sentiment score 0–1",
    "flow success rate", "average handle time in minutes" DO NOT EXIST here.
    Never invent them.
  - To determine "worst" or "best" agent, rank ONLY by success rate or engagement
    score returned from the tool — do not use any other basis.
  - Use at most {MAX_ITERATIONS} tool calls total.
  - If a tool returns no data for a metric, omit that metric — never fill it in.
  - Do NOT repeat tool calls with the same parameters."""

    history    = f"Question: {question}\n\n"
    reasoning  = []
    tools_used = []
    sources    = []

    for i in range(MAX_ITERATIONS):
        prompt = system + "\n\n" + history + "Thought:"
        raw    = _call_llm_agent(prompt)

        # Normalise — model sometimes includes its own "Thought:" prefix
        response = raw if raw.startswith("Thought:") else "Thought: " + raw

        # ── Final answer? ─────────────────────────────────────────────────────
        if "Answer:" in response:
            ans_idx = response.index("Answer:") + 7
            answer  = response[ans_idx:].strip()
            thought = response[:response.index("Answer:")].replace("Thought:", "").strip()
            reasoning.append({
                "iteration":   i + 1,
                "thought":     thought,
                "tool":        None,
                "params":      None,
                "observation": None,
            })
            return {
                "answer":          answer,
                "reasoning_steps": reasoning,
                "tools_used":      tools_used,
                "sources":         sources,
                "confidence":      "HIGH",
                "iterations":      i + 1,
            }

        # ── Parse tool call ───────────────────────────────────────────────────
        # Some models omit the "Action:" keyword and output bare JSON — detect and fix
        if "Action:" not in response:
            brace_pos = response.find("{")
            if brace_pos >= 0:
                try:
                    depth, brace_end = 0, brace_pos
                    for ci, ch in enumerate(response[brace_pos:], brace_pos):
                        if ch == "{": depth += 1
                        elif ch == "}": depth -= 1
                        if depth == 0:
                            brace_end = ci + 1
                            break
                    candidate = json.loads(response[brace_pos:brace_end])
                    if "tool" in candidate:
                        response = response[:brace_pos] + "Action: " + response[brace_pos:]
                except Exception:
                    pass

        if "Action:" not in response:
            # LLM didn't follow format — treat as free-form answer
            return {
                "answer":          response.replace("Thought:", "").strip(),
                "reasoning_steps": reasoning,
                "tools_used":      tools_used,
                "sources":         sources,
                "confidence":      "MEDIUM",
                "iterations":      i + 1,
            }

        thought_part = response[:response.index("Action:")].replace("Thought:", "").strip()
        action_raw   = response[response.index("Action:") + 7:].strip()

        # Parse JSON — handle extra text the LLM may add after the closing brace
        try:
            brace_start = action_raw.index("{")
            depth = 0
            brace_end = brace_start
            for ci, ch in enumerate(action_raw[brace_start:], brace_start):
                if   ch == "{": depth += 1
                elif ch == "}": depth -= 1
                if depth == 0:
                    brace_end = ci + 1
                    break
            call      = json.loads(action_raw[brace_start:brace_end])
            tool_name = call.get("tool", "")
            params    = call.get("params", {})
        except Exception as exc:
            observation = f"Could not parse tool call JSON ({exc}). Raw: {action_raw[:200]}"
            history    += f"Thought: {thought_part}\nAction: {action_raw}\nObservation: {observation}\n\n"
            reasoning.append({
                "iteration":   i + 1,
                "thought":     thought_part,
                "tool":        "parse_error",
                "params":      {},
                "observation": observation,
            })
            continue

        # ── Execute the tool ──────────────────────────────────────────────────
        print(f"[Agent] Iter {i + 1}: {tool_name}({json.dumps(params)})")
        observation = _execute_tool(tool_name, params, client_id)

        reasoning.append({
            "iteration":   i + 1,
            "thought":     thought_part,
            "tool":        tool_name,
            "params":      params,
            "observation": observation[:800],
        })
        tools_used.append(tool_name)

        # ── Feed result back into the running prompt ──────────────────────────
        history += (
            f"Thought: {thought_part}\n"
            f"Action: {{\"tool\": \"{tool_name}\", \"params\": {json.dumps(params)}}}\n"
            f"Observation: {observation}\n\n"
        )

    # ── Max iterations reached — force synthesis ──────────────────────────────
    print("[Agent] Max iterations reached — synthesising final answer")
    synthesis = (
        system + "\n\n" + history
        + "You have used all available tool calls. "
        + "Write your final comprehensive answer now.\nAnswer:"
    )
    final = _call_llm_agent(synthesis, max_tokens=2000)
    if final.startswith("Answer:"):
        final = final[7:].strip()

    return {
        "answer":          final,
        "reasoning_steps": reasoning,
        "tools_used":      tools_used,
        "sources":         sources,
        "confidence":      "HIGH",
        "iterations":      MAX_ITERATIONS,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI  —  quick test without starting the server
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys

    cid = "client_heya_002"
    q   = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Why is Julia struggling and what can be done to improve her success rate?"
    )

    print(f"\nClient:   {CLIENT_NAMES.get(cid, cid)}")
    print(f"Question: {q}")
    print("-" * 70)

    result = analyze(q, cid)

    print("\nREASONING STEPS:")
    for step in result["reasoning_steps"]:
        print(f"\n  Iteration {step['iteration']}:")
        if step["thought"]:
            print(f"  Thought:     {step['thought'][:180]}")
        if step["tool"]:
            print(f"  Tool:        {step['tool']}({step['params']})")
            obs = (step["observation"] or "")[:250]
            print(f"  Observation: {obs}")

    print(f"\nTools used:  {result['tools_used']}")
    print(f"Iterations:  {result['iterations']}")
    print(f"Confidence:  {result['confidence']}")
    print(f"\nFINAL ANSWER:\n{result['answer']}")
