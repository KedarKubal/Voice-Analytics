# Heya AI — RAG Conversational Interface: Complete Technical Documentation

**Project:** Heya AI Voice Analytics Platform  
**Course:** RMIT COSC2667 / COSC2777 — Semester 4  
**Files:** `backend/rag.py`, `backend/text_to_sql.py`, `backend/main.py`  
**Last Updated:** 2026-06-02

---

## Table of Contents

1. [What Is the RAG System](#1-what-is-the-rag-system)
2. [Full Pipeline Architecture](#2-full-pipeline-architecture)
3. [All Response Routes](#3-all-response-routes)
4. [Component 1 — Text-to-SQL (Primary Path)](#4-component-1--text-to-sql-primary-path)
5. [Component 2 — SQL Fast-Path](#5-component-2--sql-fast-path)
6. [Component 3 — Stats Context Builder](#6-component-3--stats-context-builder)
7. [Component 4 — Semantic Search (pgvector)](#7-component-4--semantic-search-pgvector)
8. [Component 5 — System Prompt](#8-component-5--system-prompt)
9. [Component 6 — LLM Call (Cerebras)](#9-component-6--llm-call-cerebras)
10. [Admin Mode — Cross-Client Platform View](#10-admin-mode--cross-client-platform-view)
11. [Multi-Turn Conversation Memory](#11-multi-turn-conversation-memory)
12. [API Endpoints](#12-api-endpoints)
13. [Security](#13-security)
14. [Database Tables](#14-database-tables)
15. [Vector Store — Building and Rebuilding](#15-vector-store--building-and-rebuilding)
16. [Configuration & Environment Variables](#16-configuration--environment-variables)
17. [Zero-Hallucination Design](#17-zero-hallucination-design)
18. [Known Limitations](#18-known-limitations)

---

## 1. What Is the RAG System

The RAG (Retrieval-Augmented Generation) system is the conversational AI interface for Heya AI. It lets clients ask natural language questions about their call data and receive accurate, data-grounded answers.

**Example questions it can answer:**
- "How many calls did we have in January?"
- "What is our success rate?"
- "Which agent is performing worst?"
- "Show me the most frustrated callers this month"
- "Why did engagement drop in those calls?" *(follow-up)*
- "Compare all agents by engagement score"
- "What topics are callers calling about?"

**What makes it different from a regular chatbot:**
The LLM never invents numbers. Every statistic in the answer comes from a SQL query run against the real database immediately before the LLM generates the response. The LLM's only job is to format and explain — not to recall facts from training data.

---

## 2. Full Pipeline Architecture

Every call to `query()` goes through these decision points in order:

```
User question + client_id + optional history
              │
              ▼
    ┌─────────────────────────────────────────┐
    │  Is it a follow-up?                     │
    │  (_is_followup: "those calls", "that    │
    │   one", "you mentioned", etc.)          │
    └─────────────┬───────────────────────────┘
                  │ Yes → skip Text-to-SQL + SQL fast-path
                  │ No  ↓
                  ▼
    ┌─────────────────────────────────────────┐
    │  Is it a qualitative question?          │
    │  ("why", "explain", "what happened",   │
    │   "describe", "what went wrong", etc.) │
    └─────────────┬───────────────────────────┘
                  │ Yes → skip Text-to-SQL
                  │ No  ↓
                  ▼
    ┌─────────────────────────────────────────┐
    │  Is it an admin query?                  │
    │  (client_id == "heya_admin")            │
    └─────────────┬───────────────────────────┘
                  │ Yes → skip Text-to-SQL + SQL fast-path
                  │ No  ↓
                  ▼
    ╔═════════════════════════════════════════╗
    ║  TEXT-TO-SQL  (text_to_sql.py)          ║  ← Route: "text_to_sql"
    ║  LLM generates SQL → validates →        ║    Confidence: VERIFIED
    ║  executes → LLM formats answer          ║
    ║  Returns on hit / None on miss          ║
    ╚═════════════╤═══════════════════════════╝
                  │ None (no rows / unsafe / no API key)
                  ▼
    ╔═════════════════════════════════════════╗
    ║  SQL FAST-PATH (_direct_sql_answer)     ║  ← Route: "sql_direct"
    ║  Pattern-matched keyword queries        ║    Confidence: VERIFIED
    ║  No LLM — pure SQL aggregates          ║
    ║  Returns string on hit / None on miss  ║
    ╚═════════════╤═══════════════════════════╝
                  │ None (question not in patterns)
                  ▼
    ┌─────────────────────────────────────────┐
    │  BUILD STATS CONTEXT                    │
    │  (build_stats_context)                  │
    │  ~30 SQL queries → verified text block  │
    └─────────────┬───────────────────────────┘
                  ▼
    ┌─────────────────────────────────────────┐
    │  SEMANTIC SEARCH (_secure_semantic_search)│
    │  Ollama embeddings + pgvector cosine    │
    │  Up to 3 query expansions               │
    │  Returns call docs + agent profiles     │
    │  (empty if Ollama not running)          │
    └─────────────┬───────────────────────────┘
                  ▼
    ┌─────────────────────────────────────────┐
    │  Is CEREBRAS_API_KEY set?               │
    └─────────────┬───────────────────────────┘
                  │ No
                  ▼
    ╔═════════════════════════════════════════╗
    ║  NO-LLM FALLBACK                        ║  ← Route: "no_llm"
    ║  Returns raw stats context as text      ║    Confidence: VERIFIED
    ╚═════════════════════════════════════════╝

                  │ Yes (API key set)
                  ▼
    ┌─────────────────────────────────────────┐
    │  BUILD PROMPT                           │
    │  System prompt + history + stats +      │
    │  call records (if semantic hit)         │
    └─────────────┬───────────────────────────┘
                  ▼
    ╔═════════════════════════════════════════╗
    ║  LLM GENERATION (_call_llm)             ║  ← Route: "llm_stats"
    ║  Cerebras gpt-oss-120b                  ║           "llm_stats+semantic"
    ║  temperature=0, max_tokens=1024         ║    Confidence: HIGH or MEDIUM
    ╚═════════════════════════════════════════╝
                  │
                  ▼
         QueryResponse dict
    {question, answer, route,
     confidence, sources}
```

---

## 3. All Response Routes

Every response includes a `route` field that tells you exactly which path was taken.

| Route | How triggered | Confidence | LLM used? |
|---|---|---|---|
| `text_to_sql` | Text-to-SQL succeeded and returned rows | `VERIFIED` | Yes (SQL generation + formatting) |
| `sql_direct` | SQL fast-path keyword matched | `VERIFIED` | No |
| `no_llm` | `CEREBRAS_API_KEY` not set | `VERIFIED` | No |
| `llm_stats` | LLM answered using stats context only | `HIGH` | Yes |
| `llm_stats+semantic` | LLM used stats + vector-retrieved call docs | `MEDIUM` | Yes |
| `admin_platform` | Admin mode, LLM + platform-wide stats | `HIGH` | Yes |
| `admin_platform+semantic` | Admin mode + semantic search results | `MEDIUM` | Yes |
| `followup+llm_stats` | Follow-up question, LLM + stats only | `HIGH` | Yes |
| `followup+llm_stats+semantic` | Follow-up question, LLM + stats + docs | `MEDIUM` | Yes |
| `error` | LLM call threw an exception | `VERIFIED` | Attempted |

**Confidence meanings:**
- `VERIFIED` — answer comes directly from SQL. No LLM invented anything.
- `HIGH` — LLM formatted pre-verified SQL stats. Numbers are authoritative.
- `MEDIUM` — LLM used stats + semantically retrieved call documents. Slight interpretation involved.

---

## 4. Component 1 — Text-to-SQL (Primary Path)

**File:** `backend/text_to_sql.py`  
**Function:** `answer(question, client_id) -> dict | None`

This is the **primary answering path** for all structured/analytical questions. The LLM dynamically generates the SQL rather than matching patterns — this handles any question the system has never seen before.

### 4.1 Flow

```
Question + client_id
       │
       ▼
Step 1: LLM generates SQL
        (schema + enum values + 6 structural examples → prompt)
       │
       ▼
Step 2: Safety validation
        - Must start with SELECT or WITH
        - Forbidden keywords blocked: INSERT, UPDATE, DELETE, DROP,
          TRUNCATE, ALTER, CREATE, GRANT, REVOKE, EXECUTE,
          CALL, COPY, VACUUM, ANALYZE
        - Must contain "client_id" (enforces tenant scoping)
        - If unsafe → return None
       │
       ▼
Step 3: Execute SQL (max 50 rows returned)
        - If SQL error → retry once with the error fed back to LLM
        - If retry fails → return None
        - If 0 rows → return None (fall through to RAG)
       │
       ▼
Step 4: LLM formats rows into natural-language answer
        - "Use ONLY the numbers in the SQL result"
        - Raw table returned as fallback if formatting LLM fails
       │
       ▼
Returns dict: {question, answer, route="text_to_sql",
               confidence="VERIFIED", sources=[], sql}
```

### 4.2 The Schema Prompt

The SQL generation LLM receives a full schema with:

**Tables:**
- `calls` — core table: id, client_id, agent_id, direction, call_successful, user_sentiment, duration_ms, start_timstamp *(one t — DB typo, never fix)*, topic, call_summary
- `audio_insights` — per-call analysis: engagement_score (0–100), silence_ratio (0–1), hesitation_count, interruption_count, conversation_flow, sentiment_trajectory, dominant_emotion, agent_talk_time_sec, customer_talk_time_sec, avg_pitch_hz, speaking_rate, total_turns, avg_pause_sec, sentiment_score
- `agents` — persona_name (Sasha/Justine/Sarah/Julia), agent_role, direction

**Natural language → SQL interpretation guide baked into the prompt:**
- "angry / frustrated / upset" → `user_sentiment='negative'` + `sentiment_trajectory='deteriorating'` + `engagement_score ASC`
- "happy / satisfied" → `user_sentiment='positive'` + `sentiment_trajectory='improving'` + `engagement_score DESC`
- "worst call" → `conversation_flow='poor'` AND `call_successful=FALSE`
- "most silent" → `ORDER BY silence_ratio DESC`
- "most interrupted" → `ORDER BY interruption_count DESC`
- Time queries → `to_timestamp(start_timstamp::float8/1000)` with `EXTRACT()`

**SQL rules enforced in the prompt:**
1. Always `WHERE client_id = '{client_id}'` on calls and agents
2. `audio_insights` has no `client_id` — always JOIN through calls
3. Timestamp column is `start_timstamp` — exactly one `t`
4. Use `ROUND(value::numeric, 1)` for decimals; `NULLIF(denominator, 0)` in divisions
5. Use `LEFT JOIN audio_insights` when listing calls (not all have insights)
6. Exclude test agents: `AND a.agent_role != 'test' AND a.persona_name IS NOT NULL`
7. SELECT only — never mutation
8. `LIMIT 10` for row-level results; no limit for single-value aggregates
9. Always include `call_summary` when showing specific call details

### 4.3 The 6 Few-Shot Examples

Six structural patterns are provided — the LLM learns SQL shape, not specific answers:

| Pattern | Example question |
|---|---|
| Single-table aggregate | "How many calls and success rate?" |
| Two-table aggregate (calls + insights) | "Average engagement, silence, hesitation?" |
| Three-table aggregate grouped by agent | "Compare all agents across every metric" |
| Row-level detail with ordering | "Show me the most frustrated calls" |
| Categorical breakdown with window % | "Breakdown by topic / sentiment / flow" |
| Time-based query | "Peak call hours and busiest days?" |

### 4.4 When Text-to-SQL Is Skipped

- `CEREBRAS_API_KEY` not set → returns `None` immediately
- Question is a follow-up (`_is_followup()` returns True)
- Question is qualitative ("why", "explain", "describe", "what happened", etc.)
- `client_id == "heya_admin"` (admin cross-client queries need different schema)

---

## 5. Component 2 — SQL Fast-Path

**File:** `backend/rag.py`  
**Function:** `_direct_sql_answer(question, client_id) -> str | None`

A keyword-matching fallback that handles very common questions with direct SQL — zero LLM, instant response, always `VERIFIED`.

### 5.1 Date Detection Helpers

Before keyword matching, three pure functions parse temporal context from the question:

| Function | What it detects | Examples |
|---|---|---|
| `_detect_month(q)` | Month name or abbreviation → 1–12 | "january", "jan", "feb", "december" |
| `_detect_day(q)` | Day number with optional ordinal → 1–31 | "15th", "1st", "on the 3rd" |
| `_detect_year(q)` | 4-digit `20xx` year | "2025", "2026" |
| `_month_ts_range(month, year)` | Millisecond epoch range for full month | Used in SQL `WHERE start_timstamp BETWEEN` |
| `_day_ts_range(year, month, day)` | Millisecond epoch range for one day | Day clamped to valid month end |

### 5.2 Keyword Patterns Handled

| Keyword triggers | What SQL runs | Example answer |
|---|---|---|
| Month detected + "how many"/"total"/etc. | `COUNT(*)` filtered by ms timestamp range | "In January 2026: 47 call(s). 32 successful (68.1%), 15 unsuccessful." |
| Day detected + month detected + "how many" | Same but for specific day | "On 15 January 2026: 3 call(s). 2 successful (66.7%), 1 unsuccessful." |
| "trajectory"/"improving"/"deteriorating" | `GROUP BY sentiment_trajectory` | "Improving: 120 (32.4%), Stable: 180 (48.6%), Deteriorating: 71 (19.2%)." |
| "how many calls"/"total calls"/"call count" | `COUNT(*)` + `COUNT(AudioInsight.id)` | "You have 371 total calls. 363 have been fully processed." |
| "success rate"/"successful calls" | `COUNT(CASE WHEN call_successful=TRUE)` | "320 of 371 calls were successful (86.3%). 51 were unsuccessful." |
| "average engagement"/"engagement score" | `AVG`, `MAX`, `MIN` of engagement_score | "Average: 62.4/100. Highest: 98.1. Lowest: 11.3." |
| "average duration"/"how long"/"call length" | `AVG(duration_ms)` | "Average call duration: 187.3 seconds (3.1 minutes)." |
| "conversation flow"/"smooth calls" | `GROUP BY conversation_flow` | "Smooth: 210 (57.8%), Moderate: 98 (27.0%), Poor: 55 (15.2%)." |
| "silence"/"silent"/"silence ratio" | `AVG(silence_ratio)` | "Average silence ratio: 18.4% of call duration." |
| "interruption" | `AVG(interruption_count)` | "Average interruptions per call: 2.1." |
| "customer sentiment"/"sentiment breakdown" | `GROUP BY user_sentiment` | "Positive: 180, Neutral: 120, Negative: 71." |
| "topic"/"calling about"/"why are callers" | `GROUP BY topic ORDER BY count DESC` | "Booking: 95 (25.6%), Enquiry: 88 (23.7%), ..." |
| "peak hour"/"busiest time" | `EXTRACT(hour FROM to_timestamp(...))` | "Busiest hours: 10:00–11:00 (47 calls), 14:00–15:00 (41 calls)." |
| "last call"/"most recent call" | `ORDER BY start_timstamp DESC LIMIT 1` with full JOIN | Full detail: datetime, direction, outcome, agent, all audio insights |

Returns `None` if no pattern matches → falls through to LLM path.

---

## 6. Component 3 — Stats Context Builder

**File:** `backend/rag.py`  
**Function:** `build_stats_context(client_id) -> str`

Builds the authoritative facts block that is injected into every LLM prompt. This is the core anti-hallucination mechanism — the LLM cannot invent numbers because these pre-computed SQL results are what it must use.

### 6.1 What It Queries (~30 SQL queries per call)

| Section | Queries |
|---|---|
| **Header** | Tenant name + client_id boundary declaration |
| **Totals** | `total_calls`, `processed`, `successful`, `unsuccessful`, `success_pct`, `avg_duration` |
| **Engagement** | `avg`, `max`, `min` of `engagement_score` |
| **Conversation flow** | `GROUP BY conversation_flow` (smooth/moderate/poor) with counts + % |
| **Sentiment trajectory** | `GROUP BY sentiment_trajectory` (improving/stable/deteriorating) |
| **Customer sentiment** | `GROUP BY user_sentiment` (Positive/Neutral/Negative) |
| **Direction** | `GROUP BY direction` (inbound/outbound) |
| **Topics** | `GROUP BY topic ORDER BY count DESC` |
| **Call quality** | Avg silence_ratio, interruption_count, hesitation_count, agent_talk_time_sec, customer_talk_time_sec |
| **Peak hours** | `EXTRACT(hour)` top 5 hours by call count |
| **Busiest days** | `EXTRACT(dow)` top 3 days of week |
| **Worst 5 calls** | Bottom 5 by engagement_score with call_id, flow, interruptions, trajectory |
| **Best 5 calls** | Top 5 by engagement_score with call_id, flow, trajectory |
| **Recent 6 calls** | Most recent with sentiment, outcome, and first 250 chars of call_summary |
| **Agent performance** | Per agent: total_calls, success_rate, avg_engagement, avg_hesitations, agent_talk_time, direction breakdown |

### 6.2 Output Format (example excerpt)

```
DATA BOUNDARY: The following data is EXCLUSIVELY for Artel Apartments (client_heya_001).
No data from any other organisation is present.

=== VERIFIED STATISTICS FOR ARTEL APARTMENTS ===
Total calls: 371
Calls with full audio analysis: 363
Successful calls: 320 (86.3% success rate)
Unsuccessful calls: 51
Average call duration: 187.3s (3.1 min)

ENGAGEMENT SCORES (0–100 scale):
  Average engagement: 62.4
  Highest engagement: 98.1
  Lowest engagement:  11.3

CONVERSATION FLOW:
  Smooth: 210 calls (57.8%)
  Moderate: 98 calls (27.0%)
  Poor: 55 calls (15.2%)
...
AGENT PERFORMANCE BREAKDOWN:
  Sasha (Concierge, inbound): 371 calls | 86.3% success | engagement avg 62.4 | hesitations avg 6.2/call

=== END OF VERIFIED DATA FOR ARTEL APARTMENTS ===
```

### 6.3 Admin Mode Variant

When `client_id == "heya_admin"`, `_build_admin_stats_context()` is called instead, which produces a platform-wide view with:
- Platform totals (all clients combined)
- Per-client breakdown (Artel + MVAA side by side)
- All agents across all clients in one table
- Header: `"DATA BOUNDARY: The following data covers ALL clients on the Heya AI platform."`

---

## 7. Component 4 — Semantic Search (pgvector)

**File:** `backend/rag.py`  
**Functions:** `_secure_semantic_search()`, `build_vector_store()`, `build_documents_from_db()`, `build_agent_documents()`

The semantic layer retrieves the most relevant individual call records and agent profiles to supplement the stats context for qualitative/specific questions.

### 7.1 Embeddings

| Setting | Value |
|---|---|
| Model | `nomic-embed-text` via Ollama |
| Dimensions | 768 |
| Service | Local Ollama at `http://localhost:11434` |
| Alternative | OpenAI `text-embedding-3-small` (1536 dims) when billing set up |

Ollama must be running for semantic search. If unreachable, the system falls back silently to stats-only mode (route becomes `llm_stats` instead of `llm_stats+semantic`).

### 7.2 Query Expansion

Before embedding, `_expand_query(question)` generates up to 3 rephrased variants using rule-based rewrites — no LLM needed:

| Trigger | Additional variant added |
|---|---|
| "worst"/"bad"/"poor" | "lowest engagement poor flow" |
| "best"/"good"/"highest" | "highest engagement smooth flow successful" |
| "frustrated"/"angry"/"upset" | "customer angry negative sentiment deteriorating trajectory complaint" |
| "happy"/"satisfied"/"pleased" | "customer positive sentiment improving trajectory successful resolved" |
| "long"/"duration" | "long call high duration many turns" |
| "silent"/"silence" | "high silence ratio dead air pauses" |
| "interrupt" | "interruptions agent talking over customer" |

Each variant is embedded and queried independently. Results are merged (deduplication by call_id), capped at 12 unique documents.

### 7.3 Two Embedding Tables Searched

**`call_embeddings`** — one document per processed call:

Each call document is built as a rich prose narrative from `build_documents_from_db()`:
```
Call call_xyz was a inbound call for client_heya_001 that successfully resolved.
Customer sentiment was positive. The customer was highly engaged and responsive.
Engagement score: 78.4/100. The conversation flowed naturally with good back-and-forth.
Notably, the customer's mood improved as the call progressed. The caller was calling about booking.
There were 1 interruptions and 3 hesitations. Silence accounted for 14.2% of the call.
Average customer pitch was 210Hz (normal pitch). Call summary: Customer called to...
```

Metadata stored per call document: `call_id`, `client_id`, `engagement_score`, `conversation_flow`, `call_successful`, `user_sentiment`, `sentiment_trajectory`, `topic`

**`agent_embeddings`** — one document per agent row (direction variant):

Each agent document is built from `build_agent_documents()` with full performance stats:
```
Agent Profile: Sasha — Artel Apartments Concierge (inbound calls).
Sasha handles guest check-in, booking inquiries, access codes, and emergency escalation.
371 calls, 86.3% success rate (320 successful, 51 unsuccessful).
Average engagement score: 62.4/100. Hesitations per call: 6.2 (moderate).
Interruptions per call: 2.1. Silence: 18.4% of call duration.
Agent speaks avg 94.3s, customer speaks avg 72.1s per call.
```

### 7.4 Tenant Isolation in SQL

Client searches use `WHERE client_id = %s`:
```sql
SELECT call_id, content
FROM   call_embeddings
WHERE  client_id = %s
ORDER  BY embedding <=> %s::vector
LIMIT  8
```

Admin searches omit the `WHERE` clause to search across all clients:
```sql
SELECT call_id, content
FROM   call_embeddings
ORDER  BY embedding <=> %s::vector
LIMIT  8
```

HNSW index (`vector_cosine_ops`) on both tables for fast approximate nearest-neighbour search.

---

## 8. Component 5 — System Prompt

**File:** `backend/rag.py`  
**Functions:** `_build_system_prompt()`, `_build_admin_system_prompt()`

The system prompt is prepended to every LLM prompt. It enforces anti-hallucination rules, sets the data boundary, and controls the LLM's interpretation of everyday language.

### 8.1 Client System Prompt (`_build_system_prompt`)

```
You are a precise call analytics assistant for Artel Apartments with full memory of this conversation.

DATA BOUNDARY: You only have access to data for Artel Apartments (client_heya_001).

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
6. Only say "I don't have enough data" if the metric doesn't exist in the schema.

CONVERSATION MEMORY RULES:
7. [CONVERSATION HISTORY] is your working memory — use it for follow-up questions.
8. Resolve "those calls", "that one", "them", "the worst" from prior context.
9. If a follow-up is ambiguous, state your interpretation before answering.

FORMAT RULES:
- Be concise and professional.
- Use bullet points for lists of more than 3 items.
- Include specific numbers when answering.
- Do NOT repeat the question back.
- Do NOT add disclaimers about being an AI.
```

### 8.2 Admin System Prompt (`_build_admin_system_prompt`)

Identical structure but:
- "You have full visibility across ALL clients: Artel Apartments (client_heya_001), MVAA Legal (client_heya_002)"
- "When comparing clients, always cite specific numbers for each"
- "Use clear labels (e.g., 'Artel Apartments:', 'MVAA Legal:') when comparing clients"

### 8.3 Full Prompt Assembly Order

The final prompt sent to the LLM is assembled in this exact order:
```
1. System prompt
2. [CONVERSATION HISTORY] — last MAX_HISTORY_TURNS*2 messages (if any)
3. [VERIFIED STATISTICS] — the full stats context from build_stats_context()
4. [CALL RECORDS] — semantic search results (if Ollama running + results found)
5. "Current question: {question}"
6. "Answer:"
```

---

## 9. Component 6 — LLM Call (Cerebras)

**File:** `backend/rag.py` and `backend/text_to_sql.py`  
**Function:** `_call_llm(prompt) -> str`

```python
from openai import OpenAI
client = OpenAI(
    api_key  = CEREBRAS_API_KEY,
    base_url = "https://api.cerebras.ai/v1",
)
resp = client.chat.completions.create(
    model       = MODEL_NAME,      # "gpt-oss-120b" (default)
    messages    = [{"role": "user", "content": prompt}],
    temperature = 0,               # deterministic — no randomness
    max_tokens  = 1024,            # answer limit
)
return resp.choices[0].message.content
```

**Key design choices:**
- Uses the **OpenAI SDK** with Cerebras base URL — NOT a LangChain wrapper (avoids version conflicts)
- `temperature = 0` — fully deterministic output; same question gives same answer
- Cerebras is used because it's faster than standard OpenAI for this use case
- No streaming — full response awaited before returning

**Available Cerebras models:**

| Model | ID | Notes |
|---|---|---|
| GPT-OSS 120B | `gpt-oss-120b` | Default production model |
| ZAI GLM 4.7 | `zai-glm-4.7` | Preview model |

Set via `CEREBRAS_MODEL` env var; defaults to `gpt-oss-120b`.

---

## 10. Admin Mode — Cross-Client Platform View

When `client_id == "heya_admin"` is passed to `query()`, a completely different code path runs:

| Behaviour | Client mode | Admin mode |
|---|---|---|
| Stats context | Single client only | All clients + platform totals |
| Semantic search | `WHERE client_id = %s` | No client filter — all embeddings |
| Text-to-SQL | Runs | Skipped (cross-client SQL needs different schema) |
| SQL fast-path | Runs | Skipped |
| Route label | `llm_stats` / `llm_stats+semantic` | `admin_platform` / `admin_platform+semantic` |
| System prompt | Client-scoped | Cross-client with client comparison rules |

**How admin mode is triggered from the frontend:**

In `AdminApp.jsx`, the Intelligence tab chat dropdown has a "Platform Overview (All Clients)" option. When selected, it sends `client_id: "heya_admin"` to `POST /query`. The response includes a `CROSS-CLIENT` badge in the UI.

---

## 11. Multi-Turn Conversation Memory

The `query()` function accepts a `history` parameter:

```python
history: list[dict] = []   # e.g. [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
```

**How history is used:**

1. `_is_followup(question)` checks for referential phrases:
   ```
   "those calls", "those ones", "that call", "that one", "that specific",
   "of those", "of them", "from those", "among those",
   "tell me more", "more about that", "more detail on that",
   "what else about", "elaborate on that", "expand on that",
   "which of those", "which of them",
   "mentioned above", "listed above", "you mentioned"
   ```

2. If follow-up detected → `_build_search_query()` enriches the semantic search query by prepending the last user message from history, so vector search finds the same calls the previous answer referenced.

3. The last `MAX_HISTORY_TURNS * 2` messages (= 12 messages = 6 turns) are injected into the prompt **before** the stats context, under the `[CONVERSATION HISTORY]` label.

4. Follow-up questions **skip** Text-to-SQL and SQL fast-path and go directly to stats context + semantic search + LLM.

**Frontend sends history** from the `AskYourData.jsx` component, which maintains the conversation array in local state and appends each user/assistant pair.

---

## 12. API Endpoints

### 12.1 `POST /query` — Ask a Question

**Auth:** JWT Bearer token required  
**Access:** Client can only query their own `client_id`; admin can query any

**Request body:**
```json
{
  "question":  "How many calls did we have in January?",
  "client_id": "client_heya_001",
  "history":   []
}
```

**Response body (`QueryResponse`):**
```json
{
  "question":   "How many calls did we have in January?",
  "answer":     "In January 2026: 47 call(s). 38 successful (80.9%), 9 unsuccessful.",
  "route":      "sql_direct",
  "sources":    [],
  "confidence": "VERIFIED"
}
```

**Response fields:**

| Field | Type | Description |
|---|---|---|
| `question` | str | The original question echoed back |
| `answer` | str | The answer text (may include markdown) |
| `route` | str | Which path was taken (see §3) |
| `sources` | list[str] | Call IDs or `agent:<id>` strings retrieved by semantic search |
| `confidence` | str | `VERIFIED`, `HIGH`, or `MEDIUM` |

**Error responses:**

| Status | When |
|---|---|
| 400 | Empty/whitespace-only question |
| 401 | No JWT token |
| 403 | Client token used for wrong client_id |
| 422 | Missing `question` or `client_id` field |
| 429 | Rate limit exceeded (25 requests per 60s per user) |
| 500 | RAG internal error |

**Rate limiting:** In-memory sliding window, 25 requests per 60 seconds per `user_id`. Resets on server restart. Implemented via `_check_rate_limit()` with a `defaultdict(list)` and a `threading.Lock`.

**Query history logging:** Every successful query is written to the `rag_query_history` table via the `get_app_db()` session (RLS-enforced). Fields stored: `client_id`, `user_id`, `query`, `response`, `sources`, `query_type` (= route), `response_time_ms`, `created_at`.

### 12.2 `POST /embed/{client_id}` — Build/Rebuild Vector Store

**Auth:** JWT Bearer token required  
**Access:** Client can only embed their own data; admin can embed any

Triggers `build_vector_store(client_id)` which:
1. Checks Ollama is running (raises 500 if not)
2. Builds call documents from DB (`build_documents_from_db`)
3. Builds agent profile documents (`build_agent_documents`)
4. Deletes existing embeddings for the client
5. Embeds all documents with Ollama `nomic-embed-text`
6. Inserts into `call_embeddings` and `agent_embeddings`

**Response:**
```json
{
  "status":    "success",
  "client_id": "client_heya_001",
  "message":   "Vector store built — RAG system is ready for queries"
}
```

This endpoint is **expensive** — do not call it on every query. It is a manual rebuild step run once after new calls are processed or after schema changes.

---

## 13. Security

### 13.1 Tenant Isolation (Three Layers)

**Layer 1 — JWT check at the HTTP endpoint:**
```python
def _require_client_access(user: CurrentUser, client_id: str) -> None:
    if user.is_admin:
        return
    if user.client_id != client_id:
        raise HTTPException(status_code=403, ...)
```
An Artel token cannot send `client_id: "client_heya_002"` — the server returns 403.

**Layer 2 — SQL queries use parameterised `WHERE client_id = :cid`:**
Every SQL query in the stats context builder uses explicit binding — never string interpolation. SQLAlchemy's parameterised queries prevent SQL injection.

**Layer 3 — pgvector search enforces `WHERE client_id = %s`:**
Even if a client somehow bypassed the HTTP check, the SQL in `_secure_semantic_search` has a `WHERE client_id = %s` clause that cannot be removed.

**Post-retrieval guard:** After semantic search, the code checks each returned document's `client_id` metadata to catch any slippage.

### 13.2 SQL Injection Prevention in Text-to-SQL

The `_validate(sql)` function rejects any LLM-generated SQL that:
- Contains `INSERT`, `UPDATE`, `DELETE`, `DROP`, `TRUNCATE`, `ALTER`, `CREATE`, `GRANT`, `REVOKE`, `EXECUTE`, `CALL`, `COPY`, `VACUUM`, `ANALYZE` (word-boundary matched)
- Does not start with `SELECT` or `WITH`
- Does not contain `client_id` (ensures the LLM didn't forget tenant scoping)

Validated with regex word-boundary patterns — `CREATED_AT` does NOT trigger the `CREATE` block.

### 13.3 Rate Limiting

```python
_rate_store: defaultdict[str, list[float]] = defaultdict(list)
_rate_lock  = threading.Lock()

def _check_rate_limit(key: str, limit: int = 25, window: int = 60) -> None:
    now = time.time()
    with _rate_lock:
        timestamps = _rate_store[key]
        _rate_store[key] = [t for t in timestamps if now - t < window]
        if len(_rate_store[key]) >= limit:
            raise HTTPException(status_code=429, ...)
        _rate_store[key].append(now)
```

- Key format: `"query:{user.user_id}"`
- 25 requests per 60 seconds per user
- Sliding window — timestamps older than 60s are dropped on each check
- Thread-safe via `threading.Lock()`
- **Resets on server restart** (in-memory only — not persisted)

---

## 14. Database Tables

### 14.1 `call_embeddings`

Stores embedded call documents for semantic search.

```sql
CREATE TABLE call_embeddings (
    id         BIGSERIAL    PRIMARY KEY,
    call_id    TEXT         REFERENCES calls(id) ON DELETE CASCADE,
    client_id  TEXT         NOT NULL,
    content    TEXT,                    -- prose narrative of the call
    embedding  vector(768),             -- nomic-embed-text embedding
    metadata   JSONB        DEFAULT '{}',
    created_at TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX idx_ce_client ON call_embeddings (client_id);
CREATE INDEX idx_ce_hnsw   ON call_embeddings
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
```

### 14.2 `agent_embeddings`

Stores embedded agent profile documents.

```sql
CREATE TABLE agent_embeddings (
    id         BIGSERIAL    PRIMARY KEY,
    agent_id   TEXT         REFERENCES agents(id) ON DELETE CASCADE,
    client_id  TEXT         NOT NULL,
    content    TEXT,                    -- prose profile of the agent
    embedding  vector(768),
    metadata   JSONB        DEFAULT '{}',
    created_at TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX idx_ae_client ON agent_embeddings (client_id);
CREATE INDEX idx_ae_hnsw   ON agent_embeddings
    USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
```

### 14.3 `rag_query_history`

Logs every query made through `POST /query`.

| Column | Type | Description |
|---|---|---|
| `id` | BIGSERIAL | Primary key |
| `client_id` | TEXT | Tenant |
| `user_id` | TEXT | Who asked |
| `query` | TEXT | The question |
| `response` | TEXT | The answer |
| `sources` | JSONB | List of call_ids/agent_ids cited |
| `query_type` | TEXT | Route label (e.g. `text_to_sql`, `llm_stats`) |
| `response_time_ms` | INT | Latency in milliseconds |
| `created_at` | TIMESTAMPTZ | When it was asked |

---

## 15. Vector Store — Building and Rebuilding

The vector store is **not built automatically**. It is an explicit offline step that must be run:

1. After the pipeline processes new calls for a client
2. After changing the document format in `build_documents_from_db()`
3. After adding new agents

### 15.1 How to Rebuild

```powershell
# 1. Make sure Ollama is running
& "C:\Users\Bhanu\AppData\Local\Programs\Ollama\ollama.exe" serve

# 2. Make sure the backend is running (so POST /embed hits the real app)
#    OR call build_vector_store() directly from Python

# Via HTTP endpoint:
curl -X POST http://localhost:8000/embed/client_heya_001 `
     -H "Authorization: Bearer <artel_token>"

curl -X POST http://localhost:8000/embed/client_heya_002 `
     -H "Authorization: Bearer <mvaa_token>"

# Or directly in Python (from backend/ directory):
$env:PYTHONIOENCODING = "utf-8"
conda activate heya_v2
cd D:\rmit\semester_4\project\backend
python -c "from rag import build_vector_store; build_vector_store('client_heya_001')"
python -c "from rag import build_vector_store; build_vector_store('client_heya_002')"
```

### 15.2 What the Rebuild Does

1. Checks Ollama is reachable (`check_ollama_health()`)
2. Calls `build_documents_from_db(client_id)` → loads all `AudioInsight` + `Call` rows for the client → converts to prose documents
3. Calls `build_agent_documents(client_id)` → loads agent performance stats → converts to prose profiles
4. Ensures `agent_embeddings` table exists (`_ensure_agent_embeddings_table()`)
5. Opens raw `psycopg2` connection with pgvector registered
6. `DELETE FROM call_embeddings WHERE client_id = %s`
7. Embeds all call documents with Ollama `nomic-embed-text`
8. Bulk inserts into `call_embeddings`
9. `DELETE FROM agent_embeddings WHERE client_id = %s`
10. Embeds all agent documents
11. Bulk inserts into `agent_embeddings`
12. Commits and closes connection

**Runtime:** ~2–5 minutes per client (depends on call volume and Ollama speed).  
**Artel:** 371 calls = 371 call docs + 1 agent doc  
**MVAA:** 421 calls = 421 call docs + 3–5 agent docs (Justine, Sarah×2, Julia×2)

---

## 16. Configuration & Environment Variables

All set in `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `CEREBRAS_API_KEY` | `""` (empty) | Cerebras API key. If not set, `USE_LLM = False` and the system falls back to `no_llm` route. |
| `CEREBRAS_MODEL` | `gpt-oss-120b` | Which Cerebras model to use. Current alternatives: `zai-glm-4.7` |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5435/voice_ai` | Superuser DB connection (pipeline + RAG index build) |
| `APP_DATABASE_URL` | Falls back to `DATABASE_URL` | RLS-enforced connection (query history logging) |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL for embeddings |

**Module-level constants in `rag.py`:**
```python
USE_LLM           = bool(CEREBRAS_API_KEY)   # False if key missing
MODEL_NAME        = os.getenv("CEREBRAS_MODEL", "gpt-oss-120b")
MAX_HISTORY_TURNS = 6                         # = 12 messages in prompt
EMBEDDING_DIMS    = 768                       # nomic-embed-text output size
```

---

## 17. Zero-Hallucination Design

This is the most important architectural principle. The LLM is structurally prevented from inventing numbers through four layers:

**Layer 1 — Text-to-SQL executes against real DB:**
The LLM generates SQL → Python validates it → executes it → exact rows returned. The LLM only sees real query results to format into prose. It cannot add numbers that weren't in the result set.

**Layer 2 — Stats context is pre-computed SQL, not LLM knowledge:**
The `[VERIFIED STATISTICS]` block injected into every prompt is built entirely from SQL aggregates run immediately before the LLM call. The LLM's training data plays no role in any statistic.

**Layer 3 — System prompt explicitly forbids invented numbers:**
```
"NEVER write a number not present in the provided data."
"NEVER reference a call ID not listed in [CALL RECORDS]."
"NEVER invent metrics."
```
`temperature = 0` means the model reliably follows these rules.

**Layer 4 — Semantic search scoped at SQL level:**
```sql
WHERE client_id = %s   -- tenant isolation
```
Wrong-client call documents cannot reach the LLM prompt.

**Result — three confidence tiers:**
- `VERIFIED` — no LLM involved in number production (Text-to-SQL or SQL fast-path)
- `HIGH` — LLM formatted pre-verified SQL stats; numbers are authoritative
- `MEDIUM` — LLM used stats + retrieved call documents; slight interpretation involved

---

## 18. Known Limitations

### 18.1 Semantic Search Requires Ollama Running Locally

If Ollama is not running:
- `check_ollama_health()` returns `False`
- `_secure_semantic_search()` returns `("", [])` silently
- System falls back to stats-only mode (`llm_stats` route, no `sources`)
- Call-specific questions ("show me the worst call") still work via Text-to-SQL or SQL fast-path; they just lack vector-retrieved context

To start Ollama:
```powershell
& "C:\Users\Bhanu\AppData\Local\Programs\Ollama\ollama.exe" serve
```

### 18.2 Vector Store Must Be Rebuilt Manually

The `call_embeddings` and `agent_embeddings` tables are not updated automatically when new calls are processed. After running the audio pipeline on new calls, `POST /embed/{client_id}` must be called explicitly. New calls will not appear in semantic search results until then. They will appear in Text-to-SQL and SQL fast-path results immediately.

### 18.3 Rate Limit Resets on Server Restart

The 25 req/min rate limiter is in-memory only (`defaultdict(list)`). Restarting the FastAPI server resets all counters. This is fine for development but not suitable for production under load — a Redis-backed counter would be needed.

### 18.4 Text-to-SQL Requires Cerebras API Key

Without `CEREBRAS_API_KEY`, Text-to-SQL returns `None` immediately. The SQL fast-path still works (no LLM needed), but complex questions that require dynamic SQL generation fall through to the `no_llm` route which returns the raw stats context.

### 18.5 Admin Cross-Client Mode Skips Text-to-SQL

Admin queries always use the stats context + LLM path, never Text-to-SQL. This is because cross-client SQL requires joining across tenant boundaries which the current schema prompt doesn't handle. Admin questions like "which client has better success rate" are answered from `_build_admin_stats_context()` which runs the comparison SQL itself.

### 18.6 The DB Column Typo `start_timstamp`

The `calls` table has a one-t typo: `start_timstamp` (not `start_timestamp`). This is baked into the Text-to-SQL schema prompt:
```
start_timstamp    BIGINT    -- ⚠ ONE 't' (DB typo — never "start_timestamp")
```
**This column must never be renamed** — doing so would break the audio pipeline, all timestamp queries, and require a costly migration. It is deliberately preserved.

---

*This document covers the complete RAG system as implemented on 2026-06-02. Both `rag.py` and `text_to_sql.py` must be read together to understand the full pipeline.*
