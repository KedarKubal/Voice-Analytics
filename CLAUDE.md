# Heya AI — Voice Analytics Platform

## What This Is

A multi-tenant SaaS platform that processes AI voice agent call recordings and surfaces call intelligence dashboards to clients. Built for RMIT COSC2667/2777, Semester 4.

Two core capabilities:
1. **Audio Intelligence Pipeline** — pyannote speaker diarization + librosa acoustic features → engagement scores, sentiment trajectory, silence ratios, interruption counts, emotion detection.
2. **RAG Conversational Interface** — pgvector embeddings + Cerebras LLM (Qwen3 235B) for natural language queries over call data ("what were the top complaints last week?").

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI + uvicorn, Python 3.11 |
| Database | PostgreSQL 15, port **5435** (NOT 5432), DB name `voice_ai` |
| ORM | SQLAlchemy 2.x — `get_db()` context manager |
| Audio pipeline | pyannote.audio 3.x, librosa, torch |
| RAG / embeddings | pgvector (`call_embeddings` table), Ollama for embeddings |
| LLM | Cerebras API — `qwen-3-235b-a22b-instruct-2507` (called via openai SDK, NOT LangChain) |
| Auth | python-jose JWT HS256 + bcrypt direct (NO passlib — breaks bcrypt 4.x) |
| Frontend | React 19 + Vite 8, react-router-dom v7, recharts, framer-motion, axios |

---

## Project Structure

```
project/
├── backend/
│   ├── main.py              # FastAPI app — all HTTP endpoints
│   ├── database.py          # SQLAlchemy models + session factory + CRUD helpers
│   ├── auth.py              # JWT encode/decode, bcrypt hashing
│   ├── auth_router.py       # /login endpoint
│   ├── admin_router.py      # /admin/* endpoints (heya_admin only)
│   ├── alert_router.py      # /alerts/* endpoints
│   ├── export_router.py     # /export/csv and /export/report
│   ├── rag.py               # RAG query handler — SQL stats + pgvector semantic search + LLM
│   ├── recommendations.py   # generate_recommendations() + generate_client_alerts()
│   ├── quality.py           # quality score computation
│   ├── pipeline.py          # pyannote → acoustic features (run in heya_pipeline env)
│   ├── topic_classifier.py  # call topic classification
│   ├── emotion_processor.py # emotion2vec inference (run in heya_pipeline env)
│   ├── ingest_dataset.py    # phase 1: metadata+transcript, phase 2: audio pipeline
│   └── .env                 # DATABASE_URL, APP_DATABASE_URL, CEREBRAS_API_KEY, JWT_SECRET
│
├── frontend/src/
│   ├── main.jsx             # entry point — all routes, ProtectedRoute, RootRedirect
│   ├── App.css              # SHARED stylesheet — imported by ALL pages, do not delete
│   ├── api/apiClient.js     # axios — base URL localhost:8000, auto Bearer token header
│   ├── context/
│   │   ├── AuthContext.jsx  # JWT in localStorage, login(), logout(), ready flag
│   │   └── FilterContext.jsx # global filter state (date range, flow, direction, topic)
│   ├── hooks/
│   │   └── useClientData.js # fetches /stats + /insights — used by every client page
│   ├── components/
│   │   ├── Sidebar.jsx      # nav: Home, Calls, Audio Insights, Trends, Ask Your Data, Search
│   │   ├── MotionDrawer.jsx # sliding detail panel (framer-motion)
│   │   └── AudioPlayer.jsx  # in-drawer audio playback
│   └── pages/
│       ├── Login.jsx
│       ├── AdminApp.jsx     # heya_admin god view — tabs: Overview, Feed, Users, Alerts
│       └── client/
│           ├── Home.jsx         # KPI cards + 5 charts + Call Alerts + Recent Calls
│           ├── Calls.jsx        # filter bar + call table + Analytics|Live toggle
│           ├── AudioInsights.jsx # 9 analytics sections (emotion, engagement, sentiment, etc.)
│           ├── Trends.jsx       # trend charts over time
│           ├── AskYourData.jsx  # RAG chat interface
│           └── Search.jsx       # full-text call search
│
└── dataset/
    ├── artel_apartments/    # calls.csv, agents.csv, client_info.json
    └── mvaa_legal/          # calls.csv, agents.csv
```

---

## Database Schema (key tables)

```sql
clients          — id (PK), name, created_at
agents           — id (PK), client_id (FK), name, ...
calls            — call_id (PK), client_id, agent_id, direction, start_timstamp*,
                   duration_ms, processing_status, call_successful, topic
audio_insights   — call_id (PK/FK), engagement_score, silence_ratio, interruption_count,
                   hesitation_count, conversation_flow, sentiment_trajectory, quality_score,
                   quality_grade, user_sentiment, dominant_emotion, agent_talk_time_sec,
                   customer_talk_time_sec, total_silence_sec, avg_pitch_hz,
                   agent_avg_pitch_hz, customer_avg_pitch_hz, avg_energy
transcript_utterances — id, call_id (FK), role (agent|user), content, emotion, emotion_score
call_embeddings  — call_id, client_id, embedding (vector), summary
```

> **Critical:** The DB column is `start_timstamp` (one 't' — a typo). It is mapped to `start_timestamp` in Python models. **Never fix the column name.**

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/login` | Returns JWT |
| GET | `/stats/{client_id}` | Aggregate KPIs for client |
| GET | `/insights/{client_id}` | All call rows (joined audio_insights) |
| GET | `/call/{call_id}` | Single call detail + transcript |
| GET | `/feed/{client_id}` | 50 most recent calls (live feed) |
| GET | `/recommendations/{client_id}` | Portfolio-level recs (admin drill-down) |
| GET | `/client-alerts/{client_id}` | Call-level alerts (client Home view) |
| POST | `/rag/{client_id}` | RAG natural language query |
| GET | `/export/csv/{client_id}` | Download call data as CSV |
| GET | `/export/report/{client_id}` | Generate HTML/PDF report |
| GET | `/admin/overview` | All clients summary (heya_admin only) |
| GET | `/search/{client_id}` | Full-text search across transcripts |

Auth: all endpoints (except `/login`) require `Authorization: Bearer <token>` header.  
`_require_client_access(user, client_id)` in main.py — heya_admin can access any client.

---

## Demo Accounts

| Email | Password | Role | Client |
|---|---|---|---|
| admin@heya.au | heya_admin_2026 | heya_admin | all clients |
| admin@artel.com | artel_2026 | client | Artel Apartments (client_heya_001) |
| admin@mvaallegal.com | mvaa_2026 | client | MVAA Legal (client_heya_002) |

**Clients:**
- `client_heya_001` — Artel Apartments — ~370 calls, fully processed
- `client_heya_002` — MVAA Legal — ~421 calls, partially processed

---

## How to Run

```bash
# Terminal 1 — Backend (activate heya_audio conda env first)
cd D:\rmit\semester_4\project\backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd D:\rmit\semester_4\project\frontend
npm run dev
# → http://localhost:5173
```

**Two separate conda environments — cannot be merged (DLL conflicts):**
- `heya_audio` — web server, RAG, FastAPI
- `heya_pipeline` — torch, pyannote, librosa (GPU pipeline only)

---

## Frontend Pages

### Client View (sidebar nav)
| Page | Route | What it shows |
|---|---|---|
| Home | `/dashboard/home` | KPI story cards, 5 charts (engagement dist, sentiment, calls over time, call flow, trajectory & outcome), call-level alerts, recent calls |
| Calls | `/dashboard/calls` | Filter bar + call table; toggle: Analytics \| Live (auto-polls every 5s) |
| Audio Insights | `/dashboard/audio-insights` | 9 sections: emotion, engagement, talk time, flow, silence, sentiment trajectory, speaking rate, acoustic stress |
| Trends | `/dashboard/trends` | Time-series trend charts |
| Ask Your Data | `/dashboard/ask` | RAG chat — type questions in natural language |
| Search | `/dashboard/search` | Full-text transcript search |

### Admin View (heya_admin only)
| Tab | What it shows |
|---|---|
| Overview | Client matrix — all clients, KPIs, click to drill down into any client |
| Feed | Real-time call feed across all clients |
| Users | User management |
| Alerts | Alert configuration per client — toggle alert types, view alert history |

Drill-down panel (click a client row in Overview): 7 analytics metrics bar, call table with trajectory + emotion columns, portfolio-level recommendations.

---

## Key Conventions & Gotchas

- **PostgreSQL is on port 5435** — not the default 5432.
- **DB typo `start_timstamp`** — never fix the column, always use the Python alias `start_timestamp`.
- **No Redux** — state is AuthContext + `useClientData` hook only. Pages do not fetch data directly.
- **`verify_client()` is a plain function**, not FastAPI `Depends()` — intentional.
- **`App.jsx` and `dashboard.html` were deleted** — do not recreate.
- **LangChain LLM wrappers crash** in `heya_audio` env (`langchain-core 0.3.86` bug). Use `openai` SDK directly with Cerebras base URL. The `_call_llm(prompt)` function in `rag.py` handles this.
- **RAG vector store rebuild** is an explicit offline step: `python rebuild_rag.py` (or `POST /embed/{client_id}`). Ollama must be running for embeddings.
- **Groq was replaced by Cerebras** — do not reference Groq. `CEREBRAS_API_KEY` is in `.env`.
- **heya_app PostgreSQL role** — RLS policies are active. `APP_DATABASE_URL` in `.env` uses this limited role.
- FilterContext is shared across all client pages — filters on the Calls page persist when navigating to Home and vice versa.

---

## Call Alert Detectors (client Home view)

Implemented in `recommendations.py → generate_client_alerts()`:

| Alert | Condition |
|---|---|
| Early Disconnects | `duration_ms < 20,000` (call ended in < 20s) |
| Very Poor Engagement | `engagement_score < 25` |
| Abusive / Escalatory Language | transcript utterances contain flagged words (profanity, "sue", "refund", "cancel", etc.) |
| Extreme Silence | `silence_ratio > 0.65` |
| High Interruptions | `interruption_count >= 8` |

---

## Portfolio Recommendations (admin drill-down)

Implemented in `recommendations.py → generate_recommendations()` — appears in the AdminApp drill-down panel when clicking a client, not visible to client users.

---

## Cerebras LLM Config

- **Primary model:** `qwen-3-235b-a22b-instruct-2507`
- **Fallback:** `llama3.1-8b` (set `CEREBRAS_MODEL=llama3.1-8b` in `.env` if primary has a queue)
- Called via `openai` SDK: `base_url="https://api.cerebras.ai/v1"`
- Rate limit: 60,000 TPM (vs Groq's 6,000 TPM — old provider)

---

## AI Agent-Based Analysis (Sprint 4 — Added on Supervisor Request)

### Motivation

Supervisor asked specifically about agent-based analysis during demo review. The RAG endpoint
(`/query`) couldn't answer deep per-agent questions like "Why is Sarah's success rate low?" or
"Compare all agents by engagement score." Added a full ReAct agentic engine alongside RAG.

### Architecture

```
Frontend: AgentAnalysis.jsx  (/dashboard/agent)
       │
       ▼  POST /agent/analyze/{client_id}
agent_router.py   (FastAPI router, prefix=/agent)
       │
       ▼  from agent import analyze
agent.py          (ReAct Reason+Act loop, max 3 iterations)
       │
       ├── Tool: sql_analytics        → 7 SQL metrics over calls/audio_insights
       ├── Tool: agent_performance    → agents × calls × audio_insights 3-table join
       ├── Tool: semantic_search      → _secure_semantic_search() from rag.py
       └── Tool: topic_agent_breakdown → per-agent topic performance breakdown
```

### ReAct Loop (agent.py)

- Thought/Action/Observation cycle, max 3 iterations
- Format: `"Thought: ...\nAction: {"tool":"...","params":{...}}"` or `"Answer: ..."`
- Primary model: qwen-3-235b-a22b-instruct-2507, temperature=0.1
- Fallback on 429: sleeps 3s, retries with llama3.1-8b
- Returns: `{answer, reasoning_steps, tools_used, sources, confidence:"HIGH", iterations}`

### Files Created / Modified for Agent Feature

| File | Status | What changed |
|------|--------|-------------|
| `backend/migrate_agent_profiles.sql` | CREATED + APPLIED | ALTER TABLE agents + UPDATE for all 7 agent rows |
| `backend/rag.py` | MODIFIED | build_stats_context (agent perf section), build_agent_documents, _ensure_agent_embeddings_table, build_vector_store (dual tables), _secure_semantic_search (searches agent_embeddings too), _direct_sql_answer (agent fast-paths + wants_explanation guard) |
| `backend/agent.py` | CREATED | Full ReAct engine, 4 tools, 300+ lines |
| `backend/agent_router.py` | CREATED | POST /agent/analyze/{client_id}, GET /agent/tools |
| `backend/main.py` | MODIFIED | `import agent_router; app.include_router(agent_router.router)` |
| `frontend/src/pages/client/AgentAnalysis.jsx` | CREATED | Agent selector cards, preset questions, answer + reasoning UI |
| `frontend/src/components/Sidebar.jsx` | MODIFIED | Added `{ to: '/dashboard/agent', label: 'Agent Analysis' }` |
| `frontend/src/main.jsx` | MODIFIED | import AgentAnalysis, `<Route path="agent" element={<AgentAnalysis />} />` |

### Agent Persona → DB Mapping

| persona_name | direction | agent_role | Retell ID |
|-------------|-----------|------------|-----------|
| Sasha | inbound | concierge | agent_28ebdecbf16cbb5dfc96589d32 |
| Justine | inbound | receptionist | agent_fa08e43585c6579d3ef76fe6ba |
| Sarah | outbound | at_fault_collector | agent_8fb2cb8871f7bf640534f0607a |
| Sarah | inbound | at_fault_collector | agent_da956ae9f9a5e5b1ffd122f44d |
| Julia | outbound | follow_up_emailer | agent_96d980070eca5838e58a5b505f |
| Julia | inbound | follow_up_emailer | agent_68e9c67435f72930e32b668b6a |

Sarah and Julia each have TWO DB rows (inbound + outbound) sharing persona_name.

### Additional Tables

```sql
-- agent_embeddings: separate from call_embeddings because call_embeddings FK → calls.id NOT NULL
agent_embeddings (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id    VARCHAR REFERENCES agents(id) ON DELETE CASCADE,
    embedding   vector(768),
    content     TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);
-- HNSW index: CREATE INDEX ON agent_embeddings USING hnsw (embedding vector_cosine_ops)
```

### Windows Startup Fix

```powershell
# REQUIRED on Windows — emoji in database.py causes UnicodeEncodeError with cp1252
$env:PYTHONIOENCODING = "utf-8"
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Rebuilding Agent Embeddings

```powershell
# Run after any changes to rag.py build_agent_documents()
# Ollama must be running (ollama serve)
Invoke-WebRequest -Uri "http://localhost:8000/embed/client_heya_001" `
  -Method POST -Headers @{Authorization="Bearer <token>"}
Invoke-WebRequest -Uri "http://localhost:8000/embed/client_heya_002" `
  -Method POST -Headers @{Authorization="Bearer <token>"}
```

### API Reference — Agent Endpoints

**POST /agent/analyze/{client_id}**
```json
// Request body
{ "question": "How is Sarah performing?", "mode": "auto" }

// Response
{
  "question": "How is Sarah performing?",
  "answer": "Sarah (at-fault collector) makes 53 calls total...",
  "reasoning_steps": [
    { "iteration": 1, "thought": "...", "tool": "agent_performance",
      "params": {"persona_name": "Sarah"}, "observation": "..." }
  ],
  "tools_used": ["agent_performance"],
  "sources": [],
  "confidence": "HIGH",
  "iterations": 1,
  "response_ms": 4200
}
```

**GET /agent/tools** — Returns descriptions of all 4 tools.
