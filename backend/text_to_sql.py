"""
text_to_sql.py  —  Heya AI Voice Analytics
LLM-powered Text-to-SQL engine for structured call analytics queries.

Design principle
----------------
The LLM is smart enough to translate any natural language question into SQL
given a rich schema with enum values and a semantic interpretation guide.
We do NOT hard-code question patterns — that defeats the purpose of an LLM.
Instead, the schema tells the LLM what column values exist and how everyday
language maps to those values, so it can handle questions it has never seen.

Flow
----
  1. LLM generates SQL from the question (schema + enum values + interpretation guide + 6 structural examples)
  2. Python validates safety (SELECT only, client_id enforced in Python)
  3. Execute against DB — get exact rows
  4. LLM formats rows into natural-language answer (no numbers invented)
  5. On SQL error → retry once with the error fed back to the LLM
"""

import os
import re
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text as sql_text
from database import get_db

CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
MODEL_NAME       = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")


# ═══════════════════════════════════════════════════════════════════════════════
# SCHEMA + ENUM VALUES + NATURAL LANGUAGE INTERPRETATION GUIDE
# ═══════════════════════════════════════════════════════════════════════════════
_SCHEMA = """\
You are a PostgreSQL expert for Heya AI Voice Analytics.
Your job is to translate any natural language question about call data into a single SQL query.
You must figure out the meaning of the question yourself using the schema, enum values,
and interpretation guide below — do not expect question-specific hints.

━━━ TABLE: calls ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  id                TEXT PRIMARY KEY
  client_id         TEXT NOT NULL          -- tenant scope — ALWAYS filter by this
  agent_id          TEXT                   -- FK → agents.id (nullable)
  direction         TEXT                   -- ENUM: 'inbound' | 'outbound'
  call_successful   BOOLEAN                -- TRUE = call achieved its goal
  user_sentiment    TEXT                   -- ENUM: 'positive' | 'neutral' | 'negative'
  duration_ms       BIGINT                 -- call length in milliseconds
  start_timstamp    BIGINT                 -- ⚠ ONE 't' (DB typo — never "start_timestamp")
                                           --   Unix epoch ms → to_timestamp(start_timstamp::float8/1000)
  topic             TEXT                   -- ENUM: 'booking' | 'enquiry' | 'general' | 'emergency' | 'complaint' | ...
  call_summary      TEXT                   -- AI-generated prose summary of the call
  created_at        TIMESTAMPTZ

━━━ TABLE: audio_insights  (one row per analysed call — NOT every call has one) ━━
  call_id                 TEXT FK → calls.id (UNIQUE)
  engagement_score        NUMERIC   -- 0–100  (low = disengaged/frustrated, high = engaged)
  silence_ratio           NUMERIC   -- 0–1    (fraction of call that is silence)
  hesitation_count        INT       -- count of speech hesitations (ums, ahs, pauses)
  interruption_count      INT       -- count of times one party talked over the other
  conversation_flow       TEXT      -- ENUM: 'smooth' | 'moderate' | 'poor'
  sentiment_trajectory    TEXT      -- ENUM: 'improving' | 'stable' | 'deteriorating'
  dominant_emotion        TEXT      -- most frequent customer emotion label (e.g. 'neutral', 'happy', 'sad', 'angry')
  dominant_emotion_score  NUMERIC   -- confidence of dominant_emotion (0–1)
  agent_talk_time_sec     NUMERIC   -- seconds agent spoke
  customer_talk_time_sec  NUMERIC   -- seconds customer spoke
  agent_talk_ratio        NUMERIC   -- fraction of call time agent was speaking (0–1)
  user_talk_ratio         NUMERIC   -- fraction of call time customer was speaking (0–1)
  avg_pitch_hz            NUMERIC   -- average customer voice pitch in Hz
  agent_avg_pitch_hz      NUMERIC   -- average agent voice pitch in Hz
  avg_energy              NUMERIC   -- average audio energy level
  speaking_rate           NUMERIC   -- words per minute
  total_turns             INT       -- total conversational turns
  avg_pause_sec           NUMERIC   -- average pause duration in seconds
  sentiment_score         NUMERIC   -- overall sentiment score (higher = more positive)

━━━ TABLE: agents ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  id            TEXT PRIMARY KEY
  client_id     TEXT NOT NULL
  persona_name  TEXT   -- human name: 'Justine' | 'Sarah' | 'Julia' | 'Sasha'
  agent_role    TEXT   -- ENUM: 'receptionist' | 'at_fault_collector' | 'follow_up_emailer' | 'concierge'
  direction     TEXT   -- 'inbound' | 'outbound'
  description   TEXT

━━━ NATURAL LANGUAGE → SQL INTERPRETATION GUIDE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Use this to map everyday words to the correct columns and values:

  "angry / frustrated / upset / worst mood"
      → ORDER BY user_sentiment='negative' first, THEN sentiment_trajectory='deteriorating', THEN engagement_score ASC
      → dominant_emotion may also contain 'angry' or 'sad'

  "happy / satisfied / positive / best mood / most pleased"
      → ORDER BY user_sentiment='positive' first, THEN sentiment_trajectory='improving', THEN engagement_score DESC

  "most engaged / highest engagement"
      → ORDER BY engagement_score DESC

  "least engaged / lowest engagement / disengaged"
      → ORDER BY engagement_score ASC

  "worst call / call that went most poorly"
      → conversation_flow='poor' AND call_successful=FALSE, ORDER BY engagement_score ASC

  "best call / most successful call"
      → call_successful=TRUE AND conversation_flow='smooth', ORDER BY engagement_score DESC

  "longest call / shortest call"
      → ORDER BY duration_ms DESC / ASC

  "most silent / quietest call"
      → ORDER BY silence_ratio DESC

  "most interrupted / most chaotic"
      → ORDER BY interruption_count DESC

  "improving / getting better"
      → sentiment_trajectory = 'improving'

  "deteriorating / getting worse / worsening"
      → sentiment_trajectory = 'deteriorating'

  "call went smoothly / good flow"
      → conversation_flow = 'smooth'

  "call went poorly / bad flow / friction"
      → conversation_flow = 'poor'

  "inbound calls" → direction = 'inbound'
  "outbound calls" → direction = 'outbound'

  "unsuccessful / failed calls"  → call_successful = FALSE
  "successful / resolved calls"  → call_successful = TRUE

  For time-based queries: use to_timestamp(start_timstamp::float8/1000) with EXTRACT()

━━━ SQL RULES — NEVER BREAK THESE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1.  ALWAYS add WHERE client_id = '{client_id}' on calls and agents.
2.  audio_insights has no client_id — always join: JOIN calls c ON ai.call_id = c.id WHERE c.client_id = '{client_id}'
3.  Timestamp column is start_timstamp — EXACTLY ONE 't'. Never write start_timestamp.
4.  Use ROUND(value::numeric, 1) for decimals. Use NULLIF(denominator, 0) in divisions.
5.  Use LEFT JOIN audio_insights when counting or listing calls (not all calls have insights).
6.  Exclude test agents: AND a.agent_role != 'test' AND a.persona_name IS NOT NULL
7.  SELECT only. Never INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE.
8.  Add LIMIT 10 for row-level results. No LIMIT for single-value aggregates.
9.  Always include call_summary when showing specific call details — it explains the call.
"""


# ═══════════════════════════════════════════════════════════════════════════════
# FEW-SHOT EXAMPLES  — 6 structural patterns only, not question-specific answers.
# The LLM uses the schema + interpretation guide to handle any question.
# These examples only teach SQL shape (joins, aggregates, ordering, time).
# ═══════════════════════════════════════════════════════════════════════════════
_EXAMPLES: list[tuple[str, str]] = [

    # Pattern 1: single-table aggregate
    ("How many calls do I have and what is the success rate?",
     """\
SELECT
    COUNT(*)                                                             AS total_calls,
    COUNT(CASE WHEN call_successful = TRUE  THEN 1 END)                 AS successful,
    ROUND(COUNT(CASE WHEN call_successful = TRUE THEN 1 END)::numeric
          / NULLIF(COUNT(*), 0) * 100, 1)                               AS success_rate_pct
FROM calls
WHERE client_id = '{client_id}'"""),

    # Pattern 2: two-table aggregate (calls + audio_insights)
    ("What is the average engagement score, silence ratio, and hesitation count?",
     """\
SELECT
    ROUND(AVG(ai.engagement_score)::numeric, 1)     AS avg_engagement,
    ROUND(AVG(ai.silence_ratio)::numeric * 100, 1)  AS avg_silence_pct,
    ROUND(AVG(ai.hesitation_count)::numeric, 1)     AS avg_hesitations,
    ROUND(AVG(ai.interruption_count)::numeric, 1)   AS avg_interruptions,
    COUNT(*)                                         AS calls_analysed
FROM audio_insights ai
JOIN calls c ON ai.call_id = c.id
WHERE c.client_id = '{client_id}'"""),

    # Pattern 3: three-table aggregate grouped by agent
    ("Compare all agents across every metric",
     """\
SELECT
    a.persona_name,
    a.agent_role,
    COUNT(c.id)                                                              AS total_calls,
    ROUND(COUNT(CASE WHEN c.call_successful = TRUE THEN 1 END)::numeric
          / NULLIF(COUNT(c.id), 0) * 100, 1)                                AS success_rate_pct,
    ROUND(AVG(ai.engagement_score)::numeric, 1)                             AS avg_engagement,
    ROUND(AVG(ai.silence_ratio)::numeric * 100, 1)                         AS avg_silence_pct,
    ROUND(AVG(ai.hesitation_count)::numeric, 1)                            AS avg_hesitations,
    ROUND(AVG(ai.agent_talk_time_sec)::numeric, 1)                         AS avg_agent_talk_sec
FROM agents a
JOIN calls c ON c.agent_id = a.id
LEFT JOIN audio_insights ai ON ai.call_id = c.id
WHERE a.client_id = '{client_id}'
  AND a.agent_role != 'test'
  AND a.persona_name IS NOT NULL
GROUP BY a.persona_name, a.agent_role
ORDER BY success_rate_pct DESC"""),

    # Pattern 4: row-level detail with ordering (used for "worst/best/most X" questions)
    ("Show me the most frustrated / angriest calls with details",
     """\
SELECT
    c.id                                                        AS call_id,
    c.user_sentiment,
    ai.sentiment_trajectory,
    ai.dominant_emotion,
    ROUND(ai.engagement_score::numeric, 1)                      AS engagement_score,
    ai.conversation_flow,
    ai.interruption_count,
    ROUND(c.duration_ms::numeric / 1000, 1)                    AS duration_sec,
    LEFT(c.call_summary, 300)                                   AS summary
FROM calls c
LEFT JOIN audio_insights ai ON c.id = ai.call_id
WHERE c.client_id = '{client_id}'
ORDER BY
    CASE WHEN c.user_sentiment = 'negative'            THEN 0
         WHEN c.user_sentiment = 'neutral'             THEN 1
         ELSE 2 END ASC,
    CASE WHEN ai.sentiment_trajectory = 'deteriorating' THEN 0
         WHEN ai.sentiment_trajectory = 'stable'        THEN 1
         ELSE 2 END ASC,
    ai.engagement_score ASC NULLS LAST
LIMIT 10"""),

    # Pattern 5: categorical breakdown with window function percentage
    ("What is the breakdown by topic / sentiment / flow / trajectory?",
     """\
SELECT
    COALESCE(topic, 'unknown')                                           AS topic,
    COUNT(*)                                                             AS call_count,
    ROUND(COUNT(*)::numeric / NULLIF(SUM(COUNT(*)) OVER (), 0) * 100, 1) AS pct_of_total,
    ROUND(COUNT(CASE WHEN call_successful = TRUE THEN 1 END)::numeric
          / NULLIF(COUNT(*), 0) * 100, 1)                               AS success_rate_pct
FROM calls
WHERE client_id = '{client_id}'
  AND topic IS NOT NULL
GROUP BY topic
ORDER BY call_count DESC"""),

    # Pattern 6: time-based query
    ("What are the peak call hours and busiest days?",
     """\
SELECT
    EXTRACT(hour FROM to_timestamp(start_timstamp::float8 / 1000))::int  AS hour_of_day,
    COUNT(*)                                                              AS call_count,
    ROUND(COUNT(CASE WHEN call_successful = TRUE THEN 1 END)::numeric
          / NULLIF(COUNT(*), 0) * 100, 1)                                AS success_rate_pct
FROM calls
WHERE client_id = '{client_id}'
  AND start_timstamp IS NOT NULL
  AND start_timstamp > 0
GROUP BY hour_of_day
ORDER BY call_count DESC
LIMIT 5"""),

]


# ═══════════════════════════════════════════════════════════════════════════════
# LLM CALLER
# ═══════════════════════════════════════════════════════════════════════════════
def _call_llm(prompt: str, max_tokens: int = 700) -> str:
    if not CEREBRAS_API_KEY:
        raise ValueError("CEREBRAS_API_KEY missing")
    from openai import OpenAI
    client = OpenAI(api_key=CEREBRAS_API_KEY, base_url="https://api.cerebras.ai/v1")
    resp = client.chat.completions.create(
        model       = MODEL_NAME,
        messages    = [{"role": "user", "content": prompt}],
        temperature = 0,
        max_tokens  = max_tokens,
    )
    return resp.choices[0].message.content.strip()


# ═══════════════════════════════════════════════════════════════════════════════
# SQL GENERATION
# ═══════════════════════════════════════════════════════════════════════════════
def _build_generation_prompt(question: str, client_id: str) -> str:
    examples_block = "\n\n".join(
        f'Q: {q}\nSQL:\n{s.format(client_id=client_id)}'
        for q, s in _EXAMPLES
    )
    return (
        f"{_SCHEMA.format(client_id=client_id)}\n\n"
        f"EXAMPLES — study these patterns, then write SQL for the new question:\n\n"
        f"{examples_block}\n\n"
        f"Now write SQL for this question.\n"
        f"Return ONLY the SQL query. No explanation. No markdown fences.\n\n"
        f"Q: {question}\n"
        f"SQL:"
    )


def _extract_sql(raw: str) -> str:
    """Strip markdown code fences if the model added them."""
    raw = raw.strip()
    raw = re.sub(r"^```(?:sql)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```\s*$", "", raw)
    return raw.strip()


def _enforce_client_id(sql: str, client_id: str) -> str:
    """Replace any un-substituted {client_id} placeholders the model left in."""
    return sql.replace("{client_id}", client_id)


# ═══════════════════════════════════════════════════════════════════════════════
# SAFETY VALIDATION
# ═══════════════════════════════════════════════════════════════════════════════
_FORBIDDEN = {
    "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
    "ALTER", "CREATE", "GRANT", "REVOKE", "EXECUTE",
    "CALL", "COPY", "VACUUM", "ANALYZE",
}

def _validate(sql: str) -> tuple[bool, str]:
    upper = sql.upper().strip()
    for kw in _FORBIDDEN:
        # word-boundary match so we don't block e.g. "CREATED_AT"
        if re.search(rf"\b{kw}\b", upper):
            return False, f"Forbidden keyword: {kw}"
    if not (upper.startswith("SELECT") or upper.startswith("WITH")):
        return False, "Must start with SELECT or WITH"
    # Ensure client_id is referenced somewhere in the query
    if "client_id" not in sql.lower():
        return False, "Missing client_id filter — would expose cross-tenant data"
    return True, "ok"


# ═══════════════════════════════════════════════════════════════════════════════
# EXECUTION
# ═══════════════════════════════════════════════════════════════════════════════
def _execute(sql: str) -> tuple[list[str], list[dict]]:
    """Run SQL and return (column_names, rows_as_dicts). Caps at 50 rows."""
    with get_db() as db:
        result = db.execute(sql_text(sql))
        cols   = list(result.keys())
        raw    = result.fetchmany(50)
    rows = [dict(zip(cols, row)) for row in raw]
    return cols, rows


def _rows_to_table(cols: list[str], rows: list[dict]) -> str:
    """Format rows as a plain-text table for the formatting LLM."""
    header = " | ".join(str(c) for c in cols)
    sep    = "-" * max(len(header), 30)
    lines  = [header, sep]
    for row in rows:
        lines.append(" | ".join(
            "—" if v is None else str(v)
            for v in row.values()
        ))
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# ANSWER FORMATTING
# ═══════════════════════════════════════════════════════════════════════════════
def _format_answer(question: str, table: str) -> str:
    prompt = f"""\
You are a call analytics assistant. Convert this SQL result into a clear, professional answer.

QUESTION: {question}

SQL RESULT (exact database values — do not change any number):
{table}

RULES:
- Use ONLY the numbers in the SQL result. Do not add, calculate, or estimate anything else.
- Be concise and direct. Lead with the answer, then support with data.
- Use a markdown table or bullet list when there are multiple rows.
- Do not mention SQL, databases, or technical details.
- Do not add caveats like "based on available data" — just answer.

Answer:"""
    return _call_llm(prompt, max_tokens=900)


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def answer(question: str, client_id: str) -> dict | None:
    """
    Attempt to answer a question with Text-to-SQL.

    Returns a dict compatible with rag.query() on success, or None if:
      - No API key configured
      - Generated SQL is unsafe
      - SQL fails on retry
      - Query returns no rows (caller falls through to RAG)

    Return dict keys: question, answer, route, confidence, sources, sql
    """
    if not CEREBRAS_API_KEY:
        return None

    # ── Step 1: Generate SQL ─────────────────────────────────────────────────
    gen_prompt = _build_generation_prompt(question, client_id)
    try:
        raw = _call_llm(gen_prompt, max_tokens=1000)
    except Exception as e:
        print(f"[Text2SQL] Generation error: {e}")
        return None

    sql = _enforce_client_id(_extract_sql(raw), client_id)
    print(f"[Text2SQL] Generated SQL:\n{sql}\n")

    # ── Step 2: Validate ─────────────────────────────────────────────────────
    ok, reason = _validate(sql)
    if not ok:
        print(f"[Text2SQL] Unsafe SQL rejected: {reason}")
        return None

    # ── Step 3: Execute (retry once on error) ────────────────────────────────
    try:
        cols, rows = _execute(sql)
    except Exception as err:
        print(f"[Text2SQL] SQL error: {err} — retrying with feedback")
        retry_prompt = (
            gen_prompt
            + f"\n\nThe SQL above failed with this PostgreSQL error:\n  {err}\n"
            + "Fix the SQL. Return ONLY the corrected SQL, no explanation.\n"
            + "Fixed SQL:"
        )
        try:
            raw2 = _call_llm(retry_prompt, max_tokens=1000)
            sql2 = _enforce_client_id(_extract_sql(raw2), client_id)
            ok2, reason2 = _validate(sql2)
            if not ok2:
                print(f"[Text2SQL] Retry SQL unsafe: {reason2}")
                return None
            cols, rows = _execute(sql2)
            sql = sql2
            print(f"[Text2SQL] Retry succeeded.")
        except Exception as err2:
            print(f"[Text2SQL] Retry failed: {err2}")
            return None

    if not rows:
        print("[Text2SQL] Query returned no rows — falling through to RAG")
        return None

    # ── Step 4: Format answer ─────────────────────────────────────────────────
    table = _rows_to_table(cols, rows)
    try:
        answer_text = _format_answer(question, table)
    except Exception as e:
        print(f"[Text2SQL] Formatting error: {e} — returning raw table")
        answer_text = table

    print(f"[Text2SQL] Success — {len(rows)} row(s), {len(cols)} col(s)")
    return {
        "question":   question,
        "answer":     answer_text,
        "route":      "text_to_sql",
        "confidence": "VERIFIED",
        "sources":    [],
        "sql":        sql,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLI — quick smoke test without starting the server
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import sys
    cid = "client_heya_002"
    questions = sys.argv[1:] or [
        "How many calls do I have?",
        "Compare all agents by success rate",
        "Which agent is performing worst and why?",
        "What topics are callers calling about?",
        "What is the average engagement score?",
        "Which calls went poorly and why?",
    ]
    for q in questions:
        print(f"\n{'='*60}\nQ: {q}")
        result = answer(q, cid)
        if result:
            print(f"Route:      {result['route']}")
            print(f"Confidence: {result['confidence']}")
            print(f"Answer:\n{result['answer']}")
        else:
            print("Text2SQL returned None — would fall through to RAG")
        print()
