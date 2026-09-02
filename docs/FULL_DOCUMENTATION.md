# Heya AI — Voice Analytics Platform
# Complete Technical Documentation

**Client:** Heya AI ([heya.au](https://heya.au)) — Australia's Smartest AI Voice Agent  
**Course:** RMIT COSC2667 / COSC2777 — Semester 4  
**API Version:** 2.0.0  
**Project Location:** `D:\rmit\semester_4\project`  
**Last Updated:** 2026-06-02

---

## Table of Contents

1. [About Heya AI — The Real Company](#1-about-heya-ai--the-real-company)
2. [What This Project Is](#2-what-this-project-is)
3. [System Architecture](#3-system-architecture)
4. [Tech Stack Reference](#4-tech-stack-reference)
5. [Repository Structure](#5-repository-structure)
6. [Environment Setup](#6-environment-setup)
7. [Database Schema](#7-database-schema)
8. [Audio Intelligence Pipeline](#8-audio-intelligence-pipeline)
9. [Emotion Processing](#9-emotion-processing)
10. [Topic Classification](#10-topic-classification)
11. [Webhook Ingestion — Live Calls](#11-webhook-ingestion--live-calls)
12. [RAG Conversational Interface](#12-rag-conversational-interface)
13. [ReAct Agent Analysis Engine](#13-react-agent-analysis-engine)
14. [Quality Scoring System](#14-quality-scoring-system)
15. [Recommendations Engine](#15-recommendations-engine)
16. [Alert System](#16-alert-system)
17. [API Reference — Every Endpoint](#17-api-reference--every-endpoint)
18. [Frontend — Pages and Components](#18-frontend--pages-and-components)
19. [Security Model](#19-security-model)
20. [Export and Reports](#20-export-and-reports)
21. [Demo Clients and Accounts](#21-demo-clients-and-accounts)
22. [Running the Application](#22-running-the-application)
23. [Known Gotchas](#23-known-gotchas)
24. [Test Suite](#24-test-suite)
25. [Bugs Found and Fixed](#25-bugs-found-and-fixed)
26. [EC2 Production Deployment](#26-ec2-production-deployment)

---

## 1. About Heya AI — The Real Company

**Heya AI** is a real Australian company at [heya.au](https://heya.au). Their tagline: "Australia's Smartest AI Voice Agent."

They build AI phone agents for small businesses — cafes, medical practices, tradies, legal firms, real estate property managers. Their agents handle inbound and outbound calls 24/7 with a natural Australian voice and accent, integrating with CRM, calendars, and booking systems.

**Heya's technology stack:**
- Their AI voice agents run on **Retell AI** as the underlying voice infrastructure
- Retell uses **Twilio** for telephony and **LiveKit** for real-time audio WebRTC
- This is confirmed by the raw Retell webhook fields found in the actual call data files:

```json
"event": "call_analyzed",
"retell_llm_dynamic_variables": { ... },
"custom_sip_headers": {
  "x-lk-real-ip": "...",                      <- lk = LiveKit (Retell WebRTC layer)
  "x-lk-transport": "udp",
  "x-twilio-callsid": "CA5ad39cca06e40...",    <- Twilio (Retell telephony layer)
  "x-twilio-accountsid": "ACff44c6e755..."
},
"twilio-callsid": "CA5ad39cca06e40cd8ed2d340da1a12929"
```

**Technology chain: Heya -> Retell -> LiveKit (WebRTC) + Twilio (telephony)**

**This project** is Heya's internal analytics platform — the intelligence layer that processes their agents' call recordings and gives Heya's business clients (Artel Apartments, MVAA Legal) visibility into what their AI agents are doing on calls.

---

## 2. What This Project Is

Heya AI Voice Analytics is a **multi-tenant SaaS platform** that:

1. **Ingests** call recordings and metadata from Heya's AI agents (via Retell webhooks or dataset bulk import)
2. **Processes** audio files through a GPU pipeline to extract acoustic intelligence
3. **Stores** everything in PostgreSQL with full tenant isolation
4. **Serves** per-client analytics dashboards to Heya's business clients
5. **Answers** natural language questions about call data via an RAG conversational interface
6. **Gives** the Heya team a God View admin panel across all clients

### Core Capabilities

| Capability | Description |
|---|---|
| **Audio Intelligence Pipeline** | pyannote speaker diarisation + librosa acoustic features → engagement scores, sentiment trajectory, silence ratios, interruption counts, emotion detection from raw .wav files |
| **RAG Conversational Interface** | pgvector embeddings + Cerebras LLM allow users to ask natural language questions with zero hallucination |
| **Text-to-SQL Engine** | LLM dynamically generates and executes SQL from any natural language analytics question |
| **ReAct Agent Analysis** | Multi-step reasoning agent with 4 tools performs deep per-agent performance analysis with transparent reasoning chain |
| **Multi-Tenant Dashboard** | Per-client analytics dashboards with full data isolation via JWT + PostgreSQL Row Level Security |
| **Admin God View** | Cross-client oversight panel for the Heya AI team — portfolio KPIs, cross-client RAG, user management |
| **Live Call Feed** | Webhook-based real-time ingestion with 5-second polling dashboard updates |
| **Full-Text Search** | PostgreSQL GIN index search across all transcript utterances and call summaries |
| **Topic Classification** | Keyword-weighted classifier assigns topic to every call (booking, complaint, payment, etc.) |
| **Light / Dark Theme** | Full dark/light mode toggle persisted per user in localStorage |
| **Export** | UTF-8 BOM CSV download and printable HTML reports per client |
| **Alert System** | Configurable call-level and portfolio-level alerts with email notifications |

---

## 3. System Architecture

```
 +-------------------------------------------------------------------+
 |  Heya's AI Agents (on Retell platform)                            |
 |  Sasha (Artel) * Justine * Sarah * Julia (MVAA)                  |
 +---------------------------+---------------------------------------+
                             | POST /webhook/retell (HMAC-SHA256)
                             | + dataset/ folder (bulk historical data)
                             v
 +-------------------------------------------------------------------+
 |  FastAPI 0.135 (uvicorn)  -- http://localhost:8000               |
 |                                                                   |
 |  main.py          core endpoints + folder watcher                |
 |  admin_router.py  /admin/* (heya_admin only)                     |
 |  agent_router.py  /agent/analyze/{id}                            |
 |  export_router.py /export/csv  /export/report                    |
 |  alert_router.py  /alerts/*                                      |
 |  auth_router.py   POST /auth/login                               |
 +----------------------------+--------------------------------------+
                              | SQLAlchemy 2.x ORM + raw psycopg2 SQL
 +----------------------------v--------------------------------------+
 |  PostgreSQL 15  --  port 5435  --  database: voice_ai            |
 |  pgvector extension (call_embeddings + agent_embeddings)         |
 +-------------------------------------------------------------------+
          ^                        ^                      ^
          |                        |                      |
 +--------+---------+   +----------+------+   +-----------+---------+
 |  Ollama          |   |  Cerebras API    |   |  GPU Pipeline       |
 |  nomic-embed-text|   |  gpt-oss-120b    |   |  heya_pipeline env  |
 |  localhost:11434 |   |  Text-to-SQL     |   |  pyannote + librosa |
 |  768-dim vectors |   |  + RAG answers   |   |  emotion2vec        |
 +------------------+   +-----------------+   +--------------------+
          ^
 +--------+----------------------------------------------------------+
 |  React 19 + Vite 8  --  http://localhost:5173                    |
 |  Client dashboard * Admin God View * Search * Alerts * RAG chat  |
 +-------------------------------------------------------------------+
```

### Full Data Flow

```
1. Call ends
   -> Retell POSTs to POST /webhook/retell (HMAC-SHA256 verified)
      OR: call_xxx/ folder dropped into dataset/

2. Phase 1 -- Fast ingestion (heya_v2 env, no GPU)
   -> webhook_processor.py / ingest_dataset.py
      * metadata.json  -> calls, call_metadata, tool_calls, agents tables
      * transcript.json -> transcript_utterances + transcript_words
      * audio.wav path -> recordings table
      * processing_status = "pending_audio"

3. Phase 2 -- Audio pipeline (heya_pipeline env, GPU)
   -> pipeline.py
      * pyannote diarisation (GPU) -> who spoke when
      * merge turns, assign agent/customer roles
      * librosa acoustic features (CPU) -> energy, pitch per turn
      * compute engagement, flow, trajectory, interruptions, hesitations
      -> save_audio_insights() -> audio_insights table
      * processing_status = "completed"

4. Phase 3 -- Emotion processing (heya_pipeline env, GPU)
   -> emotion_processor.py
      * emotion2vec_plus_large on each utterance audio slice
      * writes emotion + confidence to transcript_utterances
      * dominant_emotion -> audio_insights

5. Phase 4 -- Topic classification (any env, CPU)
   -> topic_classifier.py
      -> keyword scoring -> calls.topic + calls.topic_confidence

6. Dashboard -- client visits their analytics
   -> React fetches /stats + /insights (via useClientData hook)
      * Home: KPI cards, charts, alerts, recent calls
      * Calls: filter table with agent column
      * Audio Insights: 9 analytics sections
      * Ask Your Data: RAG chat + ReAct agent analysis
      * Search: full-text transcript search

7. RAG query -- client asks a question
   -> POST /query -> rag.py
      * text_to_sql.py -> LLM generates SQL -> executes -> formats answer
      * OR _direct_sql_answer() -> keyword-matched SQL (no LLM)
      * OR build_stats_context() + semantic_search() + Cerebras LLM
      -> Returns {answer, route, confidence, sources}
```

---

## 4. Tech Stack Reference

### Backend

| Component | Technology | Version / Notes |
|---|---|---|
| Web framework | FastAPI | 0.135 |
| ASGI server | uvicorn | 0.42 |
| Language | Python | 3.10 (heya_v2 env) |
| ORM | SQLAlchemy | 2.x |
| Database | PostgreSQL | 15, port **5435** (not 5432) |
| Vector search | pgvector | 768-dim, HNSW index |
| Auth | python-jose JWT HS256 | direct bcrypt (no passlib) |
| Password hashing | bcrypt | imported directly -- no passlib |

### AI / ML

| Component | Technology | Notes |
|---|---|---|
| Speaker diarisation | pyannote.audio 3.x | pyannote/speaker-diarization-3.1 from HuggingFace; requires HF_TOKEN |
| Acoustic features | librosa | RMS energy (rms), pitch (pyin), speech rate proxy |
| Emotion detection | FunASR + emotion2vec_plus_large | iic/emotion2vec_plus_large v2.0.5; per-utterance |
| ML framework | PyTorch 2.5.1+cu121 | CUDA-enabled in heya_pipeline env |
| Embeddings | Ollama -- nomic-embed-text | local, free, 768-dim, http://localhost:11434 |
| LLM (RAG + SQL) | Cerebras API -- gpt-oss-120b | via openai SDK, base_url Cerebras, temp=0 |
| LLM (ReAct agent) | Cerebras API -- gpt-oss-120b | same SDK, temp=0.1, fallback to llama3.1-8b on 429 |
| Text-to-SQL | Cerebras + custom schema prompt | 6 few-shot examples, safety validator, retry on error |

### Frontend

| Component | Technology | Version |
|---|---|---|
| UI framework | React | 19 |
| Build tool | Vite | 8 |
| Routing | react-router-dom | v7 |
| Charts | recharts | 3.x |
| Animation | framer-motion | 12.x |
| HTTP client | axios | 1.x |
| Testing | Vitest 4 + React Testing Library | -- |

### Infrastructure

| Component | Details |
|---|---|
| Conda envs | heya_v2 (web server + RAG), heya_pipeline (GPU audio + emotion2vec) |
| OS | Windows 11, miniconda at C:\Users\Bhanu\miniconda3 |
| Ollama path | C:\Users\Bhanu\AppData\Local\Programs\Ollama\ollama.exe |
| Pipeline Python | C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe |
| Web server Python | C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe |

---

## 5. Repository Structure

```
project/
+-- backend/
|   +-- main.py                  FastAPI app, all HTTP endpoints, folder watcher daemon
|   +-- database.py              SQLAlchemy models, session factory (get_db, get_app_db), CRUD
|   +-- auth.py                  JWT create/decode, bcrypt, CurrentUser class, resolve_client_id
|   +-- auth_router.py           POST /auth/login, GET /auth/me, GET /auth/clients
|   +-- admin_router.py          /admin/* -- overview, calls (9 filters), agents, users, feed
|   +-- agent_router.py          POST /agent/analyze/{id}, GET /agent/tools
|   +-- alert_router.py          GET/POST /alerts/config, history, check, digest
|   +-- export_router.py         GET /export/csv/{id}, GET /export/report/{id}
|   +-- rag.py                   Full RAG pipeline -- stats context, semantic search, LLM
|   +-- text_to_sql.py           LLM Text-to-SQL engine with schema prompt + 6 examples
|   +-- agent.py                 ReAct engine -- 4 DB tools, client-scoped system prompt
|   +-- recommendations.py       Pattern detectors -> actionable insights + call-level alerts
|   +-- quality.py               compute_quality_score() + quality_grade() -- 0-100, A-F
|   +-- pipeline.py              pyannote -> librosa acoustic features (heya_pipeline env)
|   +-- emotion_processor.py     emotion2vec per-utterance classification (heya_pipeline env)
|   +-- topic_classifier.py      Keyword-weighted topic classification (CPU, any env)
|   +-- webhook_processor.py     Retell webhook payload -> DB ingestion background task
|   +-- ingest_dataset.py        Bulk dataset ingestion -- Phase 1 (metadata) + Phase 2 (GPU)
|   +-- run_single_pipeline.py   Run audio pipeline on one call by call_id
|   +-- run_pipeline.py          Batch pipeline runner for pending_audio calls
|   +-- patch_pyannote.py        Patches use_auth_token -> token in pyannote source files
|   +-- seed_users.py            Creates the 3 demo user accounts
|   +-- migrate_db.py            Core schema migration
|   +-- migrate_pgvector.py      call_embeddings + agent_embeddings tables
|   +-- migrate_rls.py           PostgreSQL Row Level Security for heya_app role
|   +-- migrate_emotion.py       Adds emotion columns to audio_insights + transcript_utterances
|   +-- migrate_search.py        GIN indexes for full-text search
|   +-- migrate_topics.py        topic + topic_confidence columns on calls
|   +-- alerts.py                Alert logic -- check_and_send_alerts, send_weekly_digest
|   +-- .env                     Secrets -- never committed to git
|
+-- frontend/
|   +-- src/
|       +-- main.jsx             Entry -- all routes, ProtectedRoute, RootRedirect, ThemeProvider
|       +-- App.css              SHARED stylesheet imported by ALL pages (do not delete)
|       +-- index.css            CSS variables for dark/light themes, data-theme on <html>
|       +-- api/
|       |   +-- apiClient.js     Axios instance -- auto Bearer token, base URL :8000
|       +-- context/
|       |   +-- AuthContext.jsx  JWT in localStorage, login(), logout(), ready flag
|       |   +-- FilterContext.jsx Global filter state -- date, flow, dir, topic, traj, agent
|       |   +-- ThemeContext.jsx dark/light toggle, persists as heya_theme in localStorage
|       +-- hooks/
|       |   +-- useClientData.js Fetches /stats + /insights; all client pages use this
|       +-- components/
|       |   +-- Sidebar.jsx      Nav sidebar with theme toggle at bottom
|       |   +-- MotionDrawer.jsx Framer-motion sliding call detail panel
|       |   +-- AudioPlayer.jsx  In-drawer audio playback via GET /audio/{call_id}
|       +-- pages/
|           +-- Login.jsx        Login form, demo credentials, role-based redirect
|           +-- AdminApp.jsx     heya_admin God View -- 4 tabs
|           +-- client/
|               +-- ClientLayout.jsx
|               +-- Home.jsx          KPI cards + 5 charts + alerts + recent calls
|               +-- Calls.jsx         Filter bar + call table + agent column + drawer
|               +-- AudioInsights.jsx 9 analytics sections with charts
|               +-- Trends.jsx        Time-series charts
|               +-- AskYourData.jsx   RAG multi-turn chat + Agent Analysis section
|               +-- Feed.jsx          Live call feed, 5s auto-poll
|               +-- Alerts.jsx        Alert log and configuration
|               +-- Search.jsx        Full-text search with highlighted snippets
|
+-- dataset/
|   +-- artel_apartments/
|   |   +-- recordings/
|   |       +-- call_xxx/
|   |           +-- audio.wav        Raw 16kHz mono call recording
|   |           +-- metadata.json    Retell call metadata (agent, sentiment, costs, etc.)
|   |           +-- transcript.json  Utterances + word-level timestamps
|   +-- mvaa_legal/
|       +-- recordings/              Same structure, 421 calls
|
+-- tests/                           pytest suite -- 647 tests across 16 files
+-- docs/
|   +-- full_documentation.md        This document
|   +-- rag_document.md              Complete RAG system documentation
|   +-- pipeline_document.md         Complete audio pipeline documentation
|   +-- test_document.md             Complete test suite documentation
+-- pytest.ini                       Test config (testpaths, addopts, naming conventions)
+-- CLAUDE.md                        AI assistant instructions for this codebase
+-- requirements.txt                 Python dependencies (heya_v2 env)
```

---

## 6. Environment Setup

### 6.1 Environment Variables (backend/.env)

```env
# PostgreSQL -- non-default port 5435 (NOT 5432)
DATABASE_URL=postgresql://postgres:<password>@localhost:5435/voice_ai

# App-role connection (RLS enforced -- limited heya_app role)
APP_DATABASE_URL=postgresql://heya_app:<password>@localhost:5435/voice_ai

# Cerebras LLM -- for RAG answers, Text-to-SQL, and ReAct agent
CEREBRAS_API_KEY=<your-key>
CEREBRAS_MODEL=gpt-oss-120b

# HuggingFace token -- required for pyannote model download
HF_TOKEN=<your-hf-token>

# JWT signing secret
JWT_SECRET_KEY=heya-ai-voice-analytics-secret-2026-rmit

# Retell webhook HMAC verification (optional -- skipped if not set)
RETELL_API_KEY=<retell-api-key>

# Ollama embedding server
OLLAMA_BASE_URL=http://localhost:11434

# Path to GPU conda env Python
PIPELINE_PYTHON=C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe
```

### 6.2 Conda Environments

**heya_v2** -- web server + RAG (Python 3.10, torch 2.5.1+cu121 merged)

```powershell
$env:PYTHONIOENCODING = "utf-8"
conda activate heya_v2
cd D:\rmit\semester_4\project\backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**heya_pipeline** -- GPU audio pipeline + emotion2vec (torch 2.5.1+cu121, pyannote 3.x, FunASR)

```powershell
# Run pipeline scripts directly from this env
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" ingest_dataset.py --phase 2
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --client client_heya_001
```

> **Why two envs?** heya_pipeline has GPU DLL dependencies (CUDA 12.1) that conflict with web server packages on Windows. They cannot be merged without breaking one or both.

### 6.3 Ollama Setup

```powershell
# Start Ollama server (required for RAG semantic search and vector store build)
& "C:\Users\Bhanu\AppData\Local\Programs\Ollama\ollama.exe" serve

# Pull the embedding model (first time only)
ollama pull nomic-embed-text
```

Ollama is only required for POST /embed/{client_id} and semantic search in POST /query. All other dashboard features work without Ollama.

### 6.4 PostgreSQL Setup

```sql
-- Connect as postgres user
CREATE DATABASE voice_ai;
\c voice_ai
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Run migrations in order:
-- python migrate_db.py
-- python migrate_pgvector.py
-- python migrate_emotion.py
-- python migrate_search.py
-- python migrate_topics.py
-- python migrate_rls.py
-- python seed_users.py
```

---

## 7. Database Schema

**Connection:** PostgreSQL 15, port **5435**, database `voice_ai`

### Critical Notes Before Touching Anything

> `start_timstamp` has **one t** (DB typo from Retell export). Never rename it. SQLAlchemy maps it correctly.

> `user_sentiment` values are **capitalised**: 'Positive', 'Negative', 'Neutral'. Always .toLowerCase() in frontend before comparing to CSS/object keys.

> `call_metadata` has `disconnectio_rason` (another Retell-era typo). Also preserved permanently.

> `utterness_index` not `utterance_index` -- another typo in transcript_utterances. Never rename.

### 7.1 Core Tables

```
clients
  id           TEXT  PK         'client_heya_001', 'client_heya_002'
  name         TEXT              'Artel Apartments', 'MVAA Legal'
  folder_name  TEXT              matches dataset/ subfolder
  created_at   TIMESTAMP
  updated_at   TIMESTAMP

agents
  id           TEXT  PK         Retell agent_id
  client_id    TEXT  FK clients
  name         TEXT              Retell technical name
  persona_name TEXT              Human name: Sasha | Justine | Sarah | Julia
  agent_role   TEXT              concierge | receptionist | at_fault_collector | follow_up_emailer
  direction    TEXT              inbound | outbound
  version      TEXT
  description  TEXT
  created_at   TIMESTAMP
  updated_at   TIMESTAMP

calls
  id                TEXT  PK    Retell call_id (e.g. call_037f9a7f...)
  client_id         TEXT  FK clients
  agent_id          TEXT  FK agents
  call_type         TEXT         'phone_call'
  call_status       TEXT         'ended'
  direction         TEXT         'inbound' | 'outbound'
  from_number       TEXT
  to_number         TEXT
  start_timstamp    BIGINT       ONE 't' -- epoch milliseconds -- never rename
  end_timestamp     BIGINT       epoch milliseconds
  duration_ms       INTEGER
  transcript        TEXT         raw concatenated transcript from Retell
  call_summary      TEXT         AI-generated prose summary (from Retell call_analysis)
  user_sentiment    TEXT         'Positive' | 'Neutral' | 'Negative' (capitalised -- from Retell)
  call_successful   BOOLEAN      from Retell call_analysis.call_successful
  processing_status TEXT         'pending' | 'pending_audio' | 'completed' | 'failed' | 'skipped_empty'
  topic             TEXT         keyword-classified topic (from topic_classifier.py)
  topic_confidence  NUMERIC      0.0-1.0
  total_cost        NUMERIC      from Retell call_cost.combined_cost
  llm_cost          NUMERIC
  tts_cost          NUMERIC
  stt_cost          NUMERIC
  created_at        TIMESTAMP

audio_insights
  id                           SERIAL  PK
  call_id                      TEXT    FK calls (UNIQUE -- one insight per call)
  silence_ratio                NUMERIC(8,4)    0.0-1.0
  speaking_rate                NUMERIC(10,2)   speech rate proxy (1/duration)
  agent_talk_ratio             NUMERIC(8,4)    agent talk / total talk
  user_talk_ratio              NUMERIC(8,4)    customer talk / total talk
  interruption_count           INTEGER         turns starting before previous ends
  average_response_delay_sec   NUMERIC(8,4)   = avg_pause_sec
  sentiment_score              NUMERIC(8,4)   filled by emotion2vec
  engagement_score             NUMERIC(8,2)   0-100 composite acoustic score
  hesitation_count             INTEGER        pauses > 1.0s
  total_turns                  INTEGER
  agent_talk_time_sec          NUMERIC(10,2)
  customer_talk_time_sec       NUMERIC(10,2)
  avg_pause_sec                NUMERIC(8,4)
  avg_energy                   NUMERIC(10,6)
  avg_pitch_hz                 NUMERIC(10,2)
  agent_avg_energy             NUMERIC(10,6)
  customer_avg_energy          NUMERIC(10,6)
  agent_avg_pitch_hz           NUMERIC(10,2)
  customer_avg_pitch_hz        NUMERIC(10,2)
  conversation_flow            VARCHAR(20)    smooth | moderate | poor
  processing_sec               NUMERIC(8,2)   wall-clock pipeline time
  sentiment_trajectory         VARCHAR(20)    improving | stable | deteriorating
  trajectory_start_energy      NUMERIC(10,6)
  trajectory_end_energy        NUMERIC(10,6)
  dominant_emotion             VARCHAR(20)    most common customer emotion
  dominant_emotion_score       NUMERIC(8,4)   avg confidence of dominant emotion
  created_at                   TIMESTAMP
```

### 7.2 Supporting Tables

```
call_metadata
  call_id              TEXT  FK calls
  disconnectio_rason   TEXT     typo -- preserved from Retell schema, never fix
  latency_ms           NUMERIC
  total_tokens         INTEGER
  tool_call_count      INTEGER
  raw_metadata         JSONB    full latency p50/p99, cost breakdown, call_analysis blob
  imported_at          TIMESTAMP

tool_calls
  id          SERIAL  PK
  call_id     TEXT  FK calls
  tool_name   TEXT
  tool_input  JSONB
  tool_output JSONB
  called_at   TIMESTAMP

transcript_utterances
  id               SERIAL  PK
  call_id          TEXT  FK calls
  utterness_index  INTEGER        typo: "utterness" not "utterance" -- preserved
  role             TEXT           'agent' | 'user'
  content          TEXT
  emotion          TEXT           per-utterance emotion from emotion2vec
  emotion_score    NUMERIC(8,4)   confidence from emotion2vec

transcript_words
  id             SERIAL  PK
  utterness_id   INTEGER  FK transcript_utterances
  word_index     INTEGER
  word           TEXT
  start_time_sec NUMERIC   used by emotion processor to slice audio
  end_time_sec   NUMERIC

recordings
  id                    SERIAL  PK
  call_id               TEXT  FK calls
  audio_path            TEXT    absolute path to audio.wav (or Retell recording URL for live calls)
  transcript_json_path  TEXT
  metadata_json_path    TEXT
  imported_at           TIMESTAMP

users
  id              TEXT  PK
  client_id       TEXT  FK clients (NULL for heya_admin)
  email           TEXT  UNIQUE
  hashed_password TEXT  bcrypt $2b$ format
  role            TEXT  'heya_admin' | 'client'
  created_at      TIMESTAMP

rag_query_history
  id               BIGSERIAL  PK
  client_id        TEXT  FK clients
  user_id          TEXT
  query            TEXT
  response         TEXT
  sources          JSONB      list of call_ids cited
  query_type       TEXT       route label (text_to_sql, llm_stats, etc.)
  response_time_ms INTEGER
  created_at       TIMESTAMP

alert_config
  id             BIGSERIAL  PK
  client_id      TEXT  FK clients
  alert_type     TEXT       matches recommendation id slugs
  enabled        BOOLEAN
  email          TEXT       recipient address
  min_priority   TEXT       'warning' | 'critical'
  last_triggered TIMESTAMP  used for cooldown logic

alert_log
  id         BIGSERIAL  PK
  client_id  TEXT
  alert_type TEXT
  subject    TEXT
  status     TEXT       'sent' | 'failed' | 'cooldown'
  created_at TIMESTAMP
```

### 7.3 Vector Tables

```
call_embeddings
  id         BIGSERIAL  PK
  call_id    TEXT  FK calls ON DELETE CASCADE
  client_id  TEXT  NOT NULL
  content    TEXT        prose narrative of the call
  embedding  vector(768) nomic-embed-text 768-dim
  metadata   JSONB
  created_at TIMESTAMP
  -- HNSW index: vector_cosine_ops, m=16, ef_construction=64
  -- Regular index on client_id for tenant filtering

agent_embeddings
  id         BIGSERIAL  PK
  agent_id   TEXT  FK agents ON DELETE CASCADE
  client_id  TEXT  NOT NULL
  content    TEXT        prose agent profile
  embedding  vector(768)
  metadata   JSONB
  created_at TIMESTAMP
  -- HNSW index: vector_cosine_ops, m=16, ef_construction=64
```

### 7.4 Row Level Security

The `heya_app` PostgreSQL role has RLS policies on all client-scoped tables. `APP_DATABASE_URL` must connect as `heya_app`. The `postgres` superuser bypasses RLS and should only be used for migrations and pipeline scripts.

### 7.5 Full-Text Search Indexes

GIN indexes on `transcript_utterances.content` and `calls.call_summary` support `plainto_tsquery('english', :q)`. Created by `migrate_search.py`.

---

## 8. Audio Intelligence Pipeline

**Files:** `backend/pipeline.py`, `backend/ingest_dataset.py`, `backend/run_single_pipeline.py`
**Env:** `heya_pipeline` (torch 2.5.1+cu121, pyannote 3.x, librosa)
**GPU:** Required for pyannote diarisation

### 8.1 All Processing Steps in Order

```
audio.wav
  |
  +-- Step 1: load_audio_for_pyannote()
  |   torchaudio.load() -> mono -> 16kHz resample
  |   Output: {waveform: tensor, sample_rate: 16000}
  |
  +-- Step 2: pipeline(audio_input, num_speakers=2)  [GPU]
  |   Model: pyannote/speaker-diarization-3.1
  |   num_speakers=2 hardcoded (always 2 parties in a business call)
  |   Output: pyannote Annotation object with speaker segments
  |   -> torch.cuda.empty_cache() after (all subsequent steps on CPU)
  |
  +-- Step 3: build_turn_dataframe(diarization)
  |   One row per speaker turn: speaker | start_sec | end_sec | duration_sec
  |   If result is empty -> returns failed status, call is skipped
  |
  +-- Step 4: merge_adjacent_same_speaker(turn_df, gap_threshold=0.3)
  |   Merges turns by same speaker if gap <= 0.3s
  |   Prevents over-segmentation from pyannote
  |
  +-- Step 5: Filter turns < 0.3s
  |   Removes audio artifacts (false detections from background noise)
  |
  +-- Step 6: assign_roles(turn_df)
  |   Most total talk time -> "agent"
  |   Second most -> "customer"
  |   Others -> "other"
  |
  +-- Step 7: add_pause_features(turn_df)
  |   pause_before_sec = max(0, start_sec - prev_end_sec)
  |   First turn: pause = start_sec (silence before first word)
  |
  +-- Step 8: add_acoustic_features(audio_path, turn_df)  [CPU, librosa]
  |   For each turn: slice audio y[start_sample:end_sample]
  |   energy_mean = librosa.feature.rms(y=segment).mean()
  |   pitch_mean_hz = librosa.pyin(seg, fmin=C2, fmax=C7), average voiced frames only
  |
  +-- Step 9: add_speaking_rate(turn_df)
  |   speech_rate_proxy = 1 / (duration_sec + 1e-6)
  |
  +-- Step 10: add_behavior_labels(turn_df)
  |   is_long_turn = duration_sec > 3
  |   is_high_energy = energy_mean > mean(energy_mean) of all turns
  |   is_high_pitch = pitch_mean_hz > mean(pitch_mean_hz) of all turns
  |
  +-- Step 11: build_call_summary(turn_df, audio_path)
      Computes all call-level metrics -> dict -> save_audio_insights()
```

### 8.2 Metrics Computed

| Metric | Formula / Method | Output Range |
|---|---|---|
| engagement_score | 40% energy + 30% rate + 30% inverted pause | 0-100 |
| silence_ratio | total_silence_sec / (total_duration + silence + 1e-6) | 0.0-1.0 |
| conversation_flow | avg_pause > 1.0 -> poor; > 0.6 -> moderate; else smooth | smooth/moderate/poor |
| sentiment_trajectory | last-third vs first-third customer energy; +-15% threshold | improving/stable/deteriorating |
| interruption_count | turns where start_sec < previous end_sec | integer |
| hesitation_count | pause_before_sec > 1.0 | integer |
| agent_talk_time_sec | sum of agent-role turn durations | float |
| customer_talk_time_sec | sum of customer-role turn durations | float |
| avg_energy | mean of energy_mean across all turns | float |
| avg_pitch_hz | mean of pitch_mean_hz across all turns | float |

#### Engagement Score Formula (in pipeline.py)

```python
energy_score = min(avg_energy / 0.05, 1.0)       # 40% -- normalised RMS energy
rate_score   = min(avg_rate   / 0.80, 1.0)       # 30% -- normalised speech rate
pause_score  = 1.0 - min(avg_pause / 2.0, 1.0)  # 30% -- inverted pause ratio
score = round((0.4*energy_score + 0.3*rate_score + 0.3*pause_score) * 100, 2)
```

Score > 70 = healthy for a business call. Below 40 = disengagement or quality issue.

#### Conversation Flow Label (strict greater-than comparisons)

```
avg_pause > 1.0s  ->  "poor"
avg_pause > 0.6s  ->  "moderate"
else              ->  "smooth"

IMPORTANT: exactly 0.6 returns "smooth" (not moderate) -- strict > not >=
IMPORTANT: exactly 1.0 returns "moderate" (not poor)  -- strict > not >=
```

#### Sentiment Trajectory

```python
third = max(len(turn_df) // 3, 1)
e_first = first_third_customer_turns["energy_mean"].mean()
e_last  = last_third_customer_turns["energy_mean"].mean()
change  = (e_last - e_first) / e_first

if change >  0.15: return "improving"
if change < -0.15: return "deteriorating"
return "stable"
# < 3 turns total -> always "stable"
```

### 8.3 Running the Pipeline

```powershell
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project\backend

# Bulk -- all dataset calls
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" ingest_dataset.py --phase 2

# Single call
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" run_single_pipeline.py `
    --call-id call_037f9a7f2d7a7c25fd844ffb16a `
    --audio "D:\rmit\semester_4\project\dataset\artel_apartments\recordings\call_037f9a7f2d7a7c25fd844ffb16a\audio.wav"

# Test run (first 3 calls only)
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" ingest_dataset.py --phase 2 --limit 3

# Check DB state
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" ingest_dataset.py --summary
```

### 8.4 pyannote Authentication

`HF_TOKEN` in `backend/.env`. First run downloads model weights to local cache.

`load_pipeline()` handles the `use_auth_token` -> `token` API change:
```python
try:
    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=token)
except TypeError:
    pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
```

---

## 9. Emotion Processing

**File:** `backend/emotion_processor.py`
**Env:** `heya_pipeline`
**Model:** `iic/emotion2vec_plus_large` v2.0.5 (FunASR / ModelScope)
**GPU:** Yes (CUDA)

### 9.1 What It Does Per Call

```
For each transcript utterance with word-level timing data:
  1. Load full audio file (librosa, 16kHz mono)
  2. Slice audio: y[start_sample : end_sample] using transcript_words timestamps
  3. Skip segments < 1.5 seconds (too short for reliable prediction)
  4. Write to temp .wav file (emotion2vec requires file path)
  5. Run emotion2vec_plus_large -> get ranked (label, score) pairs
  6. Map labels via LABEL_MAP (handles Chinese/English bilingual model output)
  7. Skip "unknown" -> try next-best emotion if score >= 0.05
  8. Write emotion + emotion_score to transcript_utterances row
  9. Delete temp file

After all utterances:
  9. Count emotions from customer utterances only
  10. Most common emotion = dominant_emotion
  11. Update audio_insights.dominant_emotion + dominant_emotion_score
```

### 9.2 Emotion Labels and Dashboard Colors

| Emotion | Color |
|---|---|
| happy | #22c55e (green) |
| neutral | #94a3b8 (gray) |
| sad | #60a5fa (blue) |
| angry | #ef4444 (red) |
| fearful | #fb923c (orange) |
| disgusted | #a3e635 (lime) |
| surprised | #c084fc (purple) |
| unknown | #64748b (dark gray) |

### 9.3 Running the Emotion Processor

```powershell
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project\backend

& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --client client_heya_001
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --client client_heya_002

# Single call
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --call call_xxx
```

Processing time: ~0.5-2 seconds per utterance on GPU. ~1 minute per 10-minute call.

---

## 10. Topic Classification

**File:** `backend/topic_classifier.py`
**Env:** any (CPU only)
**Speed:** ~50ms per call

### 10.1 How It Works

Keyword scoring: for each topic, every keyword present in transcript text adds 1 x weight to its score. Highest-scoring topic wins.

```python
hits = sum(1 for kw in cfg["keywords"] if kw in lowered)
scores[topic] = hits * cfg["weight"]
confidence = round(scores[best] / sum(scores.values()), 4)
```

No keywords match -> ("general", 0.0).

### 10.2 Topics and Weights

| Topic | Weight | Why Higher Weight |
|---|---|---|
| emergency | 1.5 | Very specific keywords, high business importance |
| complaint | 1.4 | Should win over generic enquiry keywords |
| cancellation | 1.3 | Strong intent signal words |
| payment | 1.1 | Specific financial vocabulary |
| technical_support | 1.1 | Technical language |
| booking | 1.0 | Common but specific |
| follow_up | 1.0 | Common but specific |
| enquiry | 0.8 | Generic -- many calls mention these words incidentally |
| general | -- | Fallback when nothing matches |

### 10.3 Running Topic Classifier

```powershell
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" topic_classifier.py --all
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" topic_classifier.py --client client_heya_001
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" topic_classifier.py --all --reclassify
```

---

## 11. Webhook Ingestion -- Live Calls

**File:** `backend/webhook_processor.py`
**Triggered by:** `POST /webhook/retell` in `main.py`

### 11.1 Proof That Heya Uses Retell

The actual metadata.json files in the dataset contain Retell-specific fields not found anywhere else:

- `"event": "call_analyzed"` -- Retell webhook event name
- `"retell_llm_dynamic_variables"` -- Retell's exact LLM context injection field name
- `"collected_dynamic_variables"` -- Retell runtime variable collection
- `"custom_sip_headers"` with `x-lk-*` prefix -- LiveKit (Retell's WebRTC infrastructure)
- `"twilio-callsid": "CA5ad39..."` -- Twilio call (Retell routes calls through Twilio)
- `"twilio-accountsid": "ACff44..."` -- Identifies Retell's Twilio account
- `"agent_version": 48` -- Retell's agent versioning system

### 11.2 Retell Webhook Events

| Event | What Happens |
|---|---|
| call_ended | Triggers ingest_webhook_call() as FastAPI BackgroundTask |
| call_analyzed | Updates existing call row with analysis data |
| anything else | Returns {"status": "ignored"} |

### 11.3 Ingestion Flow Per Live Call

```
POST /webhook/retell
  |
  +-- HMAC-SHA256 verify (if RETELL_API_KEY set in .env)
  |
  +-- BackgroundTask: ingest_webhook_call(call_data)
        1. Extract call_id + agent_id from payload
        2. Look up client_id via agent_id -> agents table
           (if agent unknown -> log warning + return None)
        3. Parse: call_summary, user_sentiment, call_successful, costs
        4. Upsert calls row (insert if new, update if exists)
        5. Insert transcript_utterances + transcript_words
        6. Save recording_url to recordings.audio_path
        7. Set processing_status = "pending_audio"
```

### 11.4 Why Audio Pipeline Does Not Run in the Webhook

Retell expects a 200 response within 3 seconds. pyannote takes 30-120 seconds per call. The webhook only stores data and marks `processing_status = "pending_audio"`. Pipeline must be triggered separately.

`GET /health/queue` (admin only) shows how many calls are pending_audio.

**Production upgrade path:** Celery worker in `heya_pipeline` env that downloads `recording_url`, runs `process_call()`, saves insights, deletes temp file.

### 11.5 Automated Folder Watcher

The web server startup watches two dataset directories. Drop a new call_xxx/ folder containing metadata.json + audio.wav and it automatically runs Phase 1 ingestion + queues GPU pipeline:

```
D:\rmit\semester_4\project\dataset\artel_apartments\recordings\
D:\rmit\semester_4\project\dataset\mvaa_legal\recordings\
```

---

## 12. RAG Conversational Interface

**Files:** `backend/rag.py`, `backend/text_to_sql.py`
**API:** `POST /query`, `POST /embed/{client_id}`

### 12.1 Query Decision Flow

```
User question + client_id + optional history
  |
  +-- Follow-up? (_is_followup: "those calls", "you mentioned", etc.)
  |   Yes -> skip Text-to-SQL and SQL fast-path
  |
  +-- Qualitative? ("why", "explain", "describe", "what happened")
  |   Yes -> skip Text-to-SQL
  |
  +-- Admin? (client_id == "heya_admin")
  |   Yes -> skip Text-to-SQL and SQL fast-path
  |
  v
+---------------------------------------------------------+
|  TEXT-TO-SQL  (text_to_sql.py)                          | route: text_to_sql
|  1. LLM generates SQL (schema + 6 structural examples)  | confidence: VERIFIED
|  2. Safety validate (SELECT only + client_id present)   |
|  3. Execute against DB (max 50 rows)                    |
|  4. On error -> retry once with error message           |
|  5. LLM formats rows into natural-language answer       |
|  Returns dict | None if no rows / unsafe / no key       |
+---------------------------------------------------------+
  | None
  v
+---------------------------------------------------------+
|  SQL FAST-PATH  (_direct_sql_answer)                    | route: sql_direct
|  Keyword-matched queries -- no LLM at all               | confidence: VERIFIED
|  Handles: call counts, success rate, engagement,        |
|  silence, interruptions, sentiment, trajectory,         |
|  topics, peak hours, last call, month/day queries       |
+---------------------------------------------------------+
  | None
  v
Build stats context (build_stats_context) -- ~30 SQL queries
+ Semantic search (_secure_semantic_search) -- pgvector cosine
  |
  +-- No CEREBRAS_API_KEY -> route: no_llm -> return raw stats
  |
  v
+---------------------------------------------------------+
|  LLM GENERATION  (Cerebras gpt-oss-120b)                | route: llm_stats
|  System prompt + history + stats + call records         |        llm_stats+semantic
|  temperature=0, max_tokens=1024                         | confidence: HIGH or MEDIUM
+---------------------------------------------------------+
```

### 12.2 All Response Routes

| Route | Triggered When | Confidence | LLM Used |
|---|---|---|---|
| text_to_sql | Text-to-SQL succeeded with rows | VERIFIED | Yes (SQL gen + formatting) |
| sql_direct | SQL fast-path keyword matched | VERIFIED | No |
| no_llm | CEREBRAS_API_KEY not set | VERIFIED | No |
| llm_stats | LLM with stats context only | HIGH | Yes |
| llm_stats+semantic | LLM with stats + vector docs | MEDIUM | Yes |
| admin_platform | Admin mode, stats only | HIGH | Yes |
| admin_platform+semantic | Admin mode + semantic | MEDIUM | Yes |
| followup+llm_stats | Follow-up question | HIGH | Yes |
| followup+llm_stats+semantic | Follow-up + semantic docs | MEDIUM | Yes |
| error | LLM threw exception | VERIFIED | Attempted |

### 12.3 Text-to-SQL -- Schema and Rules

The LLM receives a full schema with enum values and a natural-language interpretation guide:

```
"angry / frustrated"  ->  user_sentiment='negative' + trajectory='deteriorating' + engagement ASC
"happy / satisfied"   ->  user_sentiment='positive' + trajectory='improving' + engagement DESC
"worst call"          ->  conversation_flow='poor' AND call_successful=FALSE
"most silent"         ->  ORDER BY silence_ratio DESC
"most interrupted"    ->  ORDER BY interruption_count DESC
```

SQL rules enforced in the prompt (LLM must follow):
- Always WHERE client_id = '{client_id}' on calls and agents
- audio_insights has no client_id -- always JOIN through calls
- Timestamp column is start_timstamp -- exactly one t
- SELECT only -- never INSERT/UPDATE/DELETE/DROP etc.
- client_id must appear in the query (prevents cross-tenant data)
- LIMIT 10 for row-level results; no LIMIT for single-value aggregates
- Always include call_summary when showing specific calls

6 few-shot structural examples teach the LLM SQL patterns:
1. Single-table aggregate (total calls, success rate)
2. Two-table aggregate (calls + audio_insights)
3. Three-table agent grouping (agents + calls + audio_insights)
4. Row-level with ordering (worst/best/most X calls)
5. Categorical breakdown with window percentage
6. Time-based query (peak hours, busiest days)

### 12.4 Stats Context Builder

`build_stats_context(client_id)` runs ~30 SQL queries and builds a verified text block injected as [VERIFIED STATISTICS] into every LLM prompt:

```
DATA BOUNDARY: The following data is EXCLUSIVELY for Artel Apartments (client_heya_001).
No data from any other organisation is present.

=== VERIFIED STATISTICS FOR ARTEL APARTMENTS ===
Total calls: 371
Successful calls: 320 (86.3% success rate)
...
AGENT PERFORMANCE:
  Sasha (Concierge, inbound): 371 calls | 86.3% success | engagement avg 62.4
=== END OF VERIFIED DATA FOR ARTEL APARTMENTS ===
```

The system prompt forbids the LLM from using any numbers not in this block.

### 12.5 Zero-Hallucination Design -- Four Layers

1. **Text-to-SQL:** LLM generates SQL -> Python validates and executes -> real rows returned. LLM only formats text.
2. **Stats context:** pre-computed SQL aggregates injected before LLM call. LLM cannot invent statistics.
3. **System prompt:** "NEVER write a number not present in the provided data". temperature=0.
4. **pgvector scoped:** WHERE client_id = %s at SQL level. Wrong-client docs cannot reach the LLM.

### 12.6 Semantic Search Details

- Model: nomic-embed-text via Ollama -- 768-dim vectors
- Tables searched: call_embeddings + agent_embeddings
- Query expansion: up to 3 rephrased variants via rule-based rewrites before embedding
- Result cap: up to 12 unique documents merged across all variants
- Tenant isolation: WHERE client_id = %s for clients; no filter for admin
- Call documents are prose narratives built from all audio insight fields + call summary

### 12.7 Admin Cross-Client Mode

When client_id == "heya_admin":
- _build_admin_stats_context() -- platform-wide totals + per-client breakdown + all agents
- Semantic search has NO WHERE client_id filter -- searches all clients' embeddings
- Text-to-SQL and SQL fast-path are skipped
- Route label becomes admin_platform or admin_platform+semantic

### 12.8 Multi-Turn Conversation

history: list[dict] accepted by POST /query. Each element: {"role": "user"|"assistant", "content": str}.

Follow-up signals: "those calls", "that call", "you mentioned", "tell me more", "which of those", "listed above", etc.

When follow-up detected:
- _build_search_query() prepends last user message to enrich vector search
- History injected under [CONVERSATION HISTORY] label
- Text-to-SQL and SQL fast-path skipped
- Max MAX_HISTORY_TURNS = 6 turns (= 12 messages) in prompt

### 12.9 Building the Vector Store

```powershell
# Start Ollama first
& "C:\Users\Bhanu\AppData\Local\Programs\Ollama\ollama.exe" serve

# Via HTTP (requires admin token)
Invoke-RestMethod -Uri "http://localhost:8000/embed/client_heya_001" -Method POST `
    -Headers @{Authorization="Bearer <admin_token>"}

# Or directly in Python
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" -c `
    "from rag import build_vector_store; build_vector_store('client_heya_001')"
```

Never inline this in the web server -- it takes 2-5 minutes per client and would block all requests.

---

## 13. ReAct Agent Analysis Engine

**File:** `backend/agent.py`
**API:** `POST /agent/analyze/{client_id}`, `GET /agent/tools`

### 13.1 Architecture

```
User question
  |
  v
ReAct Loop (max 3 iterations):
  |
  +-- Iteration N:
  |   1. LLM produces: Thought + Action (JSON tool call)
  |   2. Python executes the tool against the DB
  |   3. Observation (tool result) fed back into prompt
  |   4. LLM reasons again -> another tool OR final Answer
  |
  +-- Returns: answer + tools_used + reasoning chain + confidence + latency_ms
```

### 13.2 Four Tools

| Tool | Input | What It Returns |
|---|---|---|
| sql_analytics(metric) | metric name | Pre-approved SQL queries: overview, trends, topics, sentiment, emotion, flow, trajectory, silence, interruptions, quality |
| agent_performance(persona_name) | agent name | Per-agent metrics: volume, success rate, avg engagement, avg duration, flow breakdown |
| semantic_search(query) | free text | pgvector search over call documents + agent profiles |
| topic_agent_breakdown() | none | Per-agent performance matrix broken down by call topic |

All tools enforce client_id at SQL level.

### 13.3 Critical: Client Isolation in System Prompt

`_client_agent_options(client_id)` queries the agents table for persona_name values belonging only to the requesting client. Only those names are included in the LLM system prompt.

- Artel user sees: "Available agents: Sasha"
- MVAA user sees: "Available agents: Justine, Sarah, Julia"

Hardcoding all agent names would allow an Artel user to ask about MVAA agents -- cross-tenant data leak. The system prompt is dynamically built from DB for every request.

### 13.4 LLM Configuration

- Primary: gpt-oss-120b via Cerebras, temperature=0.1, max_tokens=1500
- Fallback: on RateLimitError -> wait 3s -> retry with llama3.1-8b

### 13.5 Frontend Display

In AskYourData.jsx, answers are rendered with:
- Confidence badge (HIGH / MEDIUM / LOW)
- Tools used chips (e.g. sql_analytics, agent_performance)
- Step count + latency in milliseconds
- Collapsible reasoning chain showing each Thought -> Action -> Observation step

---

## 14. Quality Scoring System

**File:** `backend/quality.py`

Every processed call receives a quality score (0-100) and letter grade (A-F).

### 14.1 Score Formula

```python
eng     = float(engagement_score if engagement_score is not None else 50)
flow    = {"smooth": 100, "moderate": 60, "poor": 20}.get(conversation_flow, 50)
outcome = 100 if call_successful is True else (0 if call_successful is False else 50)
emotion = {"happy":100, "surprised":75, "neutral":60, "fearful":35,
           "sad":30, "disgusted":20, "angry":15}.get(dominant_emotion, 50)
score   = round(eng*0.35 + flow*0.25 + outcome*0.25 + emotion*0.15)
```

| Signal | Weight | Range | Notes |
|---|---|---|---|
| Engagement score (acoustic) | 35% | 0-100 | Most objective signal |
| Conversation flow | 25% | smooth=100, moderate=60, poor=20 | Pause-based |
| Call outcome | 25% | true=100, false=0, null=50 | Business result |
| Customer emotion | 15% | happy=100 to angry=15 | From emotion2vec |

### 14.2 Grade Thresholds

| Grade | Minimum Score |
|---|---|
| A | 80 |
| B | 65 |
| C | 50 |
| D | 35 |
| F | < 35 |

### 14.3 Engagement Benchmark

The Voice AI industry baseline is fixed at **62.0**. The delta appears on Home page KPI cards and exported reports (e.g., "6.4 points below benchmark").

---

## 15. Recommendations Engine

**File:** `backend/recommendations.py`

`generate_recommendations(client_id)` produces actionable insights for the admin drill-down panel.

### 15.1 Benchmark Thresholds

| Metric | Warning Threshold | Critical Threshold |
|---|---|---|
| Silence ratio | >10% of calls exceed 30% silence | >40% of calls OR avg silence > 35% |
| Engagement score | Avg < 65 | Avg < 45 |
| Success rate | < 80% | -- |
| Interruptions (avg) | > 3 per call | -- |
| Poor flow | > 40% of calls | > 65% of calls |
| Deteriorating trajectory | > 35% of calls | -- |
| Negative sentiment | > 25% of callers | -- |

### 15.2 Recommendation Structure

Each recommendation contains:
- `id` -- unique slug (also used as alert_config alert_type)
- `priority` -- critical | warning | info
- `title` -- one-line headline with specific numbers
- `insight` -- why this matters (specific numbers, context)
- `action` -- what to do about it (concrete, specific)
- `metric` -- key number vs benchmark
- `affected_calls` -- how many calls are affected
- `trend` -- worsening | stable | improving

---

## 16. Alert System

**Files:** `backend/alert_router.py`, `backend/alerts.py`

### 16.1 Call-Level Alerts (Home Page)

Generated by `generate_client_alerts()` for individual calls. Shown in the client Home page alerts panel.

| Alert Type | Trigger |
|---|---|
| Early Disconnect | duration_ms < 20,000 (< 20 seconds) |
| Very Poor Engagement | engagement_score < 25 |
| Abusive / Escalatory Language | Transcript contains profanity, "sue", "refund", "cancel", "manager", "unacceptable", etc. |
| Extreme Silence | silence_ratio > 0.65 |
| High Interruptions | interruption_count >= 8 |

### 16.2 Configurable Alert Rules

Via `POST /alerts/config/{client_id}`. Clients configure which alert types fire, at what priority level, and to which email. Cooldown prevents duplicate sends within a time window.

### 16.3 Weekly Digest

`POST /alerts/digest/{client_id}` triggers a weekly performance digest email via `send_weekly_digest()`. Cooldown: 6 days (won't send twice in one week).

---

## 17. API Reference -- Every Endpoint

### 17.1 Authentication

All endpoints except `POST /auth/login` require `Authorization: Bearer <jwt-token>`.

JWT payload: `{ sub: user_id, client_id, role, name, exp }` -- HS256-signed, 24-hour expiry.

```
POST /auth/login
Body:    { "email": "...", "password": "..." }
Returns: { "access_token": "eyJ...", "token_type": "bearer",
           "role": "...", "client_id": "...", "user_id": "...", "name": "..." }
```

### 17.2 Health Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | / | None | Service info, version, endpoint list |
| GET | /health/db | None | PostgreSQL connection check |
| GET | /health/queue | any | Processing queue status per client |

### 17.3 Client Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | /insights/{client_id} | client/admin | All call rows + audio insights + agent_name (persona_name) |
| GET | /stats/{client_id} | client/admin | Aggregate KPIs, benchmark, hourly breakdown, topics, sentiment, flow |
| GET | /call/{call_id} | client/admin | Single call detail + transcript with per-utterance emotions |
| GET | /audio/{call_id} | client/admin | Stream the .wav audio file |
| GET | /feed/{client_id} | client/admin | 30-50 most recent calls (poll every 5s) |
| GET | /search?q=term&limit=20 | client/admin | Full-text transcript + summary search, highlighted snippets |
| GET | /client-alerts/{client_id} | client/admin | Call-level alert flags for Home page |
| GET | /emotions/{client_id} | client/admin | Emotion distribution + weekly trend |
| GET | /topics/{client_id} | client/admin | Topic breakdown with percentages |
| GET | /recommendations/{client_id} | client/admin | Actionable recommendations with priorities |

#### /stats Response Shape

```json
{
  "client_id": "client_heya_001",
  "total_calls": 371,
  "successful_calls": 320,
  "success_rate": 86.3,
  "avg_duration_sec": 187.3,
  "audio_processed": 363,
  "pending_audio": 0,
  "engagement_benchmark": {
    "client_score": 62.4,
    "benchmark_score": 62.0,
    "delta": 0.4,
    "label": "0.4 points above benchmark"
  },
  "silence_success_correlation": { ... },
  "calls_by_hour": [{ "hour": 9, "count": 18 }],
  "sentiment": { "Positive": 210, "Neutral": 91, "Negative": 70 },
  "flow_breakdown": { "smooth": 150, "moderate": 130, "poor": 83 },
  "emotion_breakdown": { "neutral": 200, "happy": 80, "sad": 50 },
  "sentiment_breakdown": { "improving": 120, "stable": 150, "deteriorating": 93 }
}
```

### 17.4 RAG Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /query | client/admin | Natural language question -- {question, client_id, history: []} |
| POST | /embed/{client_id} | client/admin | Build / refresh pgvector store |

Rate limit on /query: 25 requests per 60 seconds per user.

**Query response:**
```json
{
  "question":   "How many calls in January?",
  "answer":     "In January 2026: 47 calls. 38 successful (80.9%), 9 unsuccessful.",
  "route":      "sql_direct",
  "sources":    [],
  "confidence": "VERIFIED"
}
```

### 17.5 Agent Analysis Endpoints

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | /agent/analyze/{client_id} | client/admin | ReAct analysis -- {query, agent_name?} |
| GET | /agent/tools | any | List tool names and descriptions |

**Analysis response:**
```json
{
  "answer":      "Based on analysis...",
  "tools_used":  ["sql_analytics", "agent_performance"],
  "steps":       [{"thought":"...", "action":"...", "observation":"..."}],
  "confidence":  "HIGH",
  "step_count":  3,
  "latency_ms":  4200
}
```

### 17.6 Admin Endpoints (heya_admin only)

| Method | Path | Description |
|---|---|---|
| GET | /admin/clients/overview | All clients -- KPIs, silence, queue depth |
| GET | /admin/feed?limit=50 | Real-time calls across ALL clients (max 100) |
| GET | /admin/calls | All calls with 9-filter support, 22 fields, response: {"count":N, "calls":[...]} |
| GET | /admin/agents?client_id=X | Agents for client (for dropdown population) |
| GET | /admin/users | List all platform users |
| POST | /admin/users | Create user -- {email, password, role, client_id?} |
| DELETE | /admin/users/{user_id} | Delete user (cannot delete own account) |

#### /admin/calls Filter Parameters

| Param | Values | Important Note |
|---|---|---|
| client_id | client_heya_001 / client_heya_002 | -- |
| agent_id | agent UUID | -- |
| date_from | epoch ms | -- |
| date_to | epoch ms | -- |
| direction | inbound / outbound | -- |
| flow | smooth / moderate / poor | -- |
| trajectory | improving / stable / deteriorating | -- |
| sentiment | positive / neutral / negative | Frontend sends lowercase; backend does .capitalize() before SQL comparison |
| topic | booking / complaint / etc. | -- |
| limit | int | Default 500, max 2000, min 1 |

### 17.7 Export Endpoints

| Method | Path | Description |
|---|---|---|
| GET | /export/csv/{client_id} | All calls + insights as UTF-8 BOM CSV (Excel-compatible) |
| GET | /export/report/{client_id} | Printable HTML summary report |

### 17.8 Pipeline / Webhook Endpoints

| Method | Path | Description |
|---|---|---|
| POST | /process-call | Run pipeline on existing DB call |
| POST | /webhook/retell | Retell webhook -- HMAC-SHA256 verified, background-queued |

---

## 18. Frontend -- Pages and Components

### 18.1 State Architecture

Pages never call the API directly. Data flows through three shared mechanisms:

| Mechanism | File | Purpose |
|---|---|---|
| useClientData hook | hooks/useClientData.js | Fetches /stats + /insights once; returns {stats, insights, loading, lastUpdated, refresh} |
| FilterContext | context/FilterContext.jsx | Global filter state: dateFrom, dateTo, filterFlow, filterDir, filterTraj, filterTopic, filterAgent. Persists across navigation. Has clearFilters(), hasActiveFilters, applyTo(). |
| ThemeContext | context/ThemeContext.jsx | dark/light theme. toggleTheme(). Sets data-theme on html. Persists as heya_theme in localStorage. |

### 18.2 Theme System

index.css defines two layers:
- :root -- dark theme (default)
- [data-theme="light"] -- light theme overrides

Key CSS variables: --bg, --surface, --surface2, --text, --border, --muted, --accent, --danger, --tooltip-bg, --track-bg, --hover-bg, --line-faint, --inset-bg.

Never hardcode colour values in component CSS. Always use var(--token).

Toggle buttons:
- Client sidebar: sun/moon icon at bottom of Sidebar.jsx
- Admin: toggle button in AdminApp.jsx header bar

### 18.3 Routing

```
/                  -> RootRedirect -> /login or /dashboard or /admin
/login             -> Login.jsx
/dashboard/*       -> ProtectedRoute (role: client) -> ClientLayout
  /dashboard/home
  /dashboard/calls
  /dashboard/audio-insights
  /dashboard/trends
  /dashboard/ask
  /dashboard/feed
  /dashboard/alerts
  /dashboard/search
/admin             -> ProtectedRoute (role: heya_admin) -> AdminApp.jsx
```

### 18.4 Client Pages

| Page | Route | What It Shows |
|---|---|---|
| Home | /dashboard/home | KPI story cards, 5 charts, call alerts panel, recent calls table |
| Calls | /dashboard/calls | Filter bar (date, flow, direction, topic, agent), call table + agent column, detail drawer with transcript + audio |
| Audio Insights | /dashboard/audio-insights | 9 analytics sections with charts |
| Trends | /dashboard/trends | Time-series charts over selectable date ranges |
| Ask Your Data | /dashboard/ask | RAG multi-turn chat + Agent Analysis section |
| Feed | /dashboard/feed | Live call stream, 5s auto-poll |
| Alerts | /dashboard/alerts | Alert log and configuration |
| Search | /dashboard/search | Full-text search with highlighted snippets + call detail drawer |

#### Audio Insights -- 9 Sections

1. Emotion Detection -- pie/bar of customer emotion distribution; tooltip explains acoustic source
2. Engagement Scoring -- histogram 0-100, mean line, 62.0 benchmark overlay
3. Talk Time Distribution -- agent vs customer % split
4. Conversation Flow -- smooth/moderate/poor breakdown
5. Silence Analysis -- silence ratio distribution + success correlation callout
6. Sentiment Trajectory -- horizontal bars + volume chart + insight line
7. Speaking Rate -- words-per-minute histogram
8. Acoustic Stress -- elevated pitch counts, avg speaking rate, pitch delta (coaching opportunities)
9. Quality Grades -- A-F distribution bar chart

#### Ask Your Data -- Two Sections

Section 1 -- RAG Chat:
- Suggestion pills (pre-built general questions)
- Multi-turn conversation via POST /query
- Answers show: confidence badge (VERIFIED/HIGH/MEDIUM) + source call IDs + route label

Section 2 -- Agent Analysis:
- Client-scoped agent cards: Artel sees only Sasha; MVAA sees Justine, Sarah, Julia
- Preset analysis pills per selected agent
- Answers rendered with: confidence badge, tools_used chips, step count, latency, collapsible reasoning chain
- Calls POST /agent/analyze/{clientId}

### 18.5 Admin App -- 4 Tabs

Accessible only at /admin for role = heya_admin.

| Tab | What It Shows |
|---|---|
| Overview | Client matrix -- all KPIs; click any row to open drill-down with 7 analytics bars, call table, recommendations |
| Feed | Cross-client call feed -- 18 columns, 9 filters (client->agent chain), CSV export, 5s live refresh |
| Intelligence | RAG chat with "Platform Overview (All Clients)" option -> client_id: "heya_admin". CROSS-CLIENT badge on answers. |
| Users | Create / delete platform users, assign to clients |

#### Admin Feed -- 18 Columns

Status, Client, Call ID, Agent, Direction, Date/Time, Duration, Quality grade+score, Engagement mini-bar, Silence %, Interruptions, Flow chip, Trajectory arrow, Sentiment, Emotion, Topic badge, Outcome. CSV export adds 5 more fields (23 total).

#### Admin Feed -- Live Refresh Pattern (stale closure fix)

```jsx
const feedFiltersRef = useRef(feedFilters);
useEffect(() => { feedFiltersRef.current = feedFilters; }, [feedFilters]);

const timer = setInterval(() => {
  fetchFeedData(feedFiltersRef.current);  // always uses latest filters, not stale closure
}, 5000);
```

#### Admin Feed -- Agent Dropdown Chain

Selecting a Client auto-fetches agents via GET /admin/agents?client_id=X and populates the Agent dropdown. Changing client resets agent selection.

### 18.6 Key Components

| Component | File | Purpose |
|---|---|---|
| MotionDrawer | components/MotionDrawer.jsx | Framer-motion sliding panel for call detail |
| AudioPlayer | components/AudioPlayer.jsx | In-drawer audio playback |
| Sidebar | components/Sidebar.jsx | Nav sidebar with theme toggle |
| apiClient | api/apiClient.js | Axios: auto Bearer from localStorage, 401 removes token + redirect /login, 15s timeout |

---

## 19. Security Model

### 19.1 Authentication

- HS256 JWT signed with JWT_SECRET_KEY from .env
- Payload: { sub: user_id, client_id, role, name, exp }
- 24-hour expiry
- Passwords bcrypt-hashed directly -- no passlib (passlib breaks with bcrypt 4.x $2b$ format)
- Expired/malformed tokens cleared on mount in AuthContext.jsx

### 19.2 Multi-Tenant Isolation -- Three Layers

| Layer | Where | Mechanism |
|---|---|---|
| 1. JWT Claims | auth.py | client_id embedded in signed token; cannot be forged |
| 2. App-level check | main.py | _require_client_access(user, client_id) -- plain function called manually at every endpoint |
| 3. PostgreSQL RLS | migrate_rls.py | heya_app role has RLS policies; cross-tenant rows blocked at DB level |

### 19.3 Roles

| Role | Access |
|---|---|
| heya_admin | All clients, admin panel, user management, cross-client feed, cross-client RAG |
| client | Only their own client_id -- enforced in JWT, app check, and RLS |

### 19.4 SQL Injection Prevention

- All SQLAlchemy queries use parameterised bindings
- Text-to-SQL: generated SQL validated before execution (must be SELECT/WITH, no mutating keywords, must contain client_id)
- Raw SQL in admin endpoints uses sql_text() with named parameters (:param)

### 19.5 Cross-Tenant Protections

- call_embeddings queries include WHERE client_id = %s at SQL level
- Post-retrieval filter in _secure_semantic_search() discards documents whose client_id doesn't match
- GET /call/{call_id} returns 404 (not 403) for cross-tenant calls -- hides existence

### 19.6 Rate Limiting

In-memory per-user sliding window (threading.Lock()):
- POST /query: 25 requests per 60 seconds per user
- Resets on server restart (in-memory only -- no Redis)

### 19.7 Webhook Security

POST /webhook/retell verifies HMAC-SHA256 signature against RETELL_API_KEY if set in .env. Invalid signatures return 401. If key not set, verification is skipped (dev mode).

---

## 20. Export and Reports

### 20.1 CSV Export

`GET /export/csv/{client_id}` -- streams a CSV with one row per call.

- UTF-8 BOM encoded (\xef\xbb\xbf) -- opens correctly in Excel on Windows without encoding issues
- Includes: all call metadata + audio insights + quality score + quality grade
- Admin Feed also has a CSV export button for the filtered table (23 columns)

### 20.2 HTML Report

`GET /export/report/{client_id}` -- printable HTML page.

Contains: client name, generation timestamp, KPI cards (total calls, success rate, avg engagement + benchmark delta, avg duration, avg silence), conversation flow breakdown, emotion breakdown.

To export as PDF: open in browser -> File -> Print -> Save as PDF.

---

## 21. Demo Clients and Accounts

### 21.1 Login Credentials

| Email | Password | Role | Access |
|---|---|---|---|
| admin@heya.au | heya_admin_2026 | heya_admin | All clients -- God View |
| admin@artel.com | artel_2026 | client | Artel Apartments only |
| admin@mvaallegal.com | mvaa_2026 | client | MVAA Legal only |

### 21.2 Artel Apartments (client_heya_001)

**Business:** Property management company -- serviced apartments.
**Location:** Brunswick, Melbourne.

**AI Agent: Sasha** (Concierge, inbound only)
- Handles guest check-in (access codes, key safes, parking)
- Booking inquiries and availability (cannot check live -- sends SMS booking link)
- Property FAQs (amenities, check-in/out times, smoking policy)
- Guest identity verification
- Secure SMS forms for sensitive information
- Human escalation for complex issues

**Call Data:** 371 calls, fully processed through all 4 phases. Vector store built for RAG.

### 21.3 MVAA Legal (client_heya_002)

**Business:** Motor vehicle accident law firm.
**Location:** Melbourne.

**AI Agents (3 personas, 5 direction variants):**

| Persona | Direction | Role | What They Do |
|---|---|---|---|
| Justine | Inbound | receptionist | Front desk -- inquiries, case updates, call routing |
| Sarah | Outbound | at_fault_collector | Calls at-fault drivers to collect insurance details |
| Sarah | Inbound | at_fault_collector | Handles return calls from at-fault drivers |
| Julia | Outbound | follow_up_emailer | Follows up with clients to confirm Welcome Pack signing |
| Julia | Inbound | follow_up_emailer | Handles return calls from Welcome Pack clients |

**Call Data:** 421 calls total -- 419 fully processed, 2 skipped (processing_status = "skipped_empty" -- immediate hangups with no audio content).

### 21.4 Agent -> Client Mapping

| persona_name | client_id | direction | agent_role |
|---|---|---|---|
| Sasha | client_heya_001 | inbound | concierge |
| Justine | client_heya_002 | inbound | receptionist |
| Sarah | client_heya_002 | inbound + outbound | at_fault_collector |
| Julia | client_heya_002 | inbound + outbound | follow_up_emailer |

---

## 22. Running the Application

### 22.1 Full Startup

**Terminal 1 -- Backend:**
```powershell
$env:PYTHONIOENCODING = "utf-8"
conda activate heya_v2
cd D:\rmit\semester_4\project\backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

On startup: creates missing DB tables, checks Ollama health (prints warning if down), starts folder watcher daemon.

> After any backend restart: sign out and sign in once to refresh the JWT with the name field.

**Terminal 2 -- Frontend:**
```powershell
cd D:\rmit\semester_4\project\frontend
npm run dev
# -> http://localhost:5173
```

**Terminal 3 -- Ollama (for RAG only):**
```powershell
& "C:\Users\Bhanu\AppData\Local\Programs\Ollama\ollama.exe" serve
```

### 22.2 First-Time Dataset Ingestion

```powershell
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project\backend

# Phase 1 -- metadata + transcripts (~5 min for 800 calls)
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" ingest_dataset.py --phase 1

# Phase 2 -- audio pipeline (~6-8 hours for 800 calls, GPU)
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" ingest_dataset.py --phase 2

# Phase 3 -- emotion processing (~several hours, GPU)
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --client client_heya_001
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --client client_heya_002

# Phase 4 -- topic classification (~1 min, CPU)
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" topic_classifier.py --all

# Build RAG vector store (~5 min per client, requires Ollama running)
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" -c `
    "from rag import build_vector_store; build_vector_store('client_heya_001')"
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" -c `
    "from rag import build_vector_store; build_vector_store('client_heya_002')"
```

### 22.3 Running Tests

```powershell
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project

# All backend integration tests (heya_audio has FastAPI)
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\pytest.exe" -q

# Pipeline unit + acoustic tests (no GPU)
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\pytest.exe" tests/test_pipeline.py -m "not gpu" -q

# Pipeline GPU integration tests (heya_pipeline, --noconftest skips FastAPI conftest)
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\Scripts\pytest.exe" tests/test_pipeline.py -m gpu --noconftest -v

# Frontend tests
cd D:\rmit\semester_4\project\frontend && npm test
```

---

## 23. Known Gotchas

Read before making any changes. Every item here has caused a real bug.

### Database

| Gotcha | Detail |
|---|---|
| **Port is 5435** | Not the default 5432. All connection strings, pgvector calls, and any tooling must use 5435 |
| **start_timstamp has one t** | Typo from Retell export. SQLAlchemy maps it. Text-to-SQL prompt warns the LLM. Never rename the column |
| **user_sentiment is capitalised** | DB stores 'Positive', 'Negative', 'Neutral'. Always .toLowerCase() in frontend. Bug was in admin_router.py (now fixed with .capitalize()) |
| **disconnectio_rason in call_metadata** | Another Retell-era typo. Preserved as-is |
| **utterness_index not utterance_index** | Typo in transcript_utterances. Never rename |
| **RLS uses heya_app role** | APP_DATABASE_URL must connect as heya_app. postgres superuser bypasses RLS -- use only for migrations |

### Backend

| Gotcha | Detail |
|---|---|
| **_require_client_access() is not Depends()** | Plain function -- must be called manually at the top of each endpoint. If you add a new endpoint, call it explicitly |
| **No passlib** | import bcrypt directly. passlib breaks with bcrypt 4.x $2b$ hash format |
| **No LangChain LLM wrappers** | langchain-core 0.3.86 crashes on LLM instantiation. Use the openai SDK with Cerebras base_url directly |
| **safe_json_float() for all numerics** | Pipeline produces NaN/Inf. Always pass numeric fields through this helper before API responses |
| **PYTHONIOENCODING=utf-8 on Windows** | Emoji in database.py causes UnicodeEncodeError with cp1252. Set before uvicorn and any pipeline script |
| **Agent prompt is dynamic** | agent.py builds persona_name options from DB. Never hardcode all agent names -- cross-tenant leak |
| **Rebuild RAG explicitly** | build_vector_store() is an offline step. Never inline in the web server |
| **DetachedInstanceError pattern** | ORM objects accessed after session closes throw DetachedInstanceError. Fix: convert to plain dicts inside the with get_db() block. Fixed in admin_router.py and alerts.py |
| **Groq was replaced by Cerebras** | Any GROQ_API_KEY references in old code are stale |

### Frontend

| Gotcha | Detail |
|---|---|
| **No Redux** | State = AuthContext + useClientData + FilterContext. Pages do not call the API directly |
| **App.jsx was deleted** | Entry point is main.jsx. Do not recreate App.jsx |
| **App.css is shared** | Imported by every page. CSS changes affect the entire application |
| **AgentAnalysis.jsx was deleted** | Standalone /dashboard/agent no longer exists. Agent analysis is embedded in AskYourData.jsx |
| **FilterContext persists across pages** | Filters set on Calls page are active on Home. filterAgent included in clearFilters() and hasActiveFilters |
| **feedFiltersRef in Admin Feed** | Timer callbacks capture filter values via ref to avoid stale closure bugs |
| **Theme via CSS variables only** | Never hardcode colour values in JSX. Always use var(--token) |
| **dashboard.html was deleted** | Old static dashboard fully replaced by React SPA |

### Pipeline

| Gotcha | Detail |
|---|---|
| **heya_pipeline env only for GPU** | Cannot run pyannote from heya_v2 -- speechbrain k2_fsa import fails |
| **num_speakers=2 hardcoded** | Correct for 2-party business calls. Would need changing for conference calls |
| **use_auth_token vs token in pyannote** | Newer huggingface_hub uses token=; older pyannote source uses use_auth_token=. load_pipeline() handles with try/except. patch_pyannote.py can fix source files directly |
| **Emotion needs word-level timestamps** | If Retell doesn't include word timing, utterances are skipped by emotion_processor.py |
| **Minimum 1.5s for emotion2vec** | Utterances shorter than 1.5 seconds are skipped |
| **Audio pipeline cannot run in web server** | heya_pipeline and heya_v2 have conflicting CUDA DLLs on Windows |

---

## 24. Test Suite

**Total:** 647 tests, 0 failures
**Frameworks:** pytest 8 (backend) + Vitest 4 (frontend)

### 24.1 Backend Test Files

| File | Tests | Coverage |
|---|---|---|
| test_auth.py | 32 | Login (all 3 accounts), JWT lifecycle, /auth/me, /auth/clients, bcrypt unit tests |
| test_security.py | 50 | JWT attacks (alg:none, wrong secret, expired, forged), full tenant isolation matrix, rate limiting, SQL injection in auth, webhook security |
| test_admin.py | 33 | /admin/clients/overview, /admin/feed, user management (create/delete), role enforcement |
| test_admin_calls_filters.py | 53 | All 9 filter params on /admin/calls including sentiment capitalisation fix, SQL injection in all string params |
| test_alerts.py | 51 | Alert config, history, triggers, digest, DetachedInstanceError fix verification |
| test_calls.py | 26 | Call detail, transcript shape, roles valid, /feed, /emotions, /topics |
| test_insights.py | 16 | /insights endpoint, all required fields, access control |
| test_stats.py | 24 | /stats all 10 required keys, numeric ranges, benchmark section |
| test_search.py | 20 | Full-text search, scope, edge cases, access control |
| test_export.py | 24 | CSV columns, BOM, HTML report, access control |
| test_recommendations.py | 17 | Recommendation thresholds, priorities |
| test_health.py | 11 | /, /health/db, /health/queue |
| test_quality.py | 40 | Quality score formula (all 4 weights), grade boundaries, banker's rounding |
| test_database_helpers.py | 16 | safe_json_float -- NaN/Inf/None/custom default handling |
| test_rag.py | 85 | Pure unit (date parsing, follow-up, timestamp math), DB (stats context tenant isolation), HTTP (shape, auth, access control, multi-turn) |
| test_pipeline.py | 89 | Pure unit (merge, roles, pauses, engagement formula, flow boundaries, trajectory), Acoustic (real wav), GPU (full process_call end-to-end) |
| **Backend total** | **585** | |

### 24.2 Frontend Test Files

| File | Tests | Coverage |
|---|---|---|
| auth_context.test.jsx | 10 | JWT storage, expiry, hydration, login/logout cycle |
| api_client.test.js | 10 | Axios config, Bearer injection, 401 handling, error propagation |
| login_page.test.jsx | 13 | Form, visibility toggle, routing by role, loading state, error messages |
| search_page.test.jsx | 11 | Debounce, suggestion pills, result cards, empty state, clear button |
| filter_context.test.jsx | 18 | Default state, all setters, clearFilters, hasActiveFilters, applyTo() |
| **Frontend total** | **62** | |

### 24.3 Running Tests (Exact Commands)

```powershell
# Backend (most tests -- heya_audio has FastAPI)
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\pytest.exe" -q --tb=line

# Pipeline unit + acoustic (heya_v2)
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\pytest.exe" tests/test_pipeline.py -m "not gpu" -q

# Pipeline GPU integration (heya_pipeline -- no FastAPI so use --noconftest)
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\Scripts\pytest.exe" tests/test_pipeline.py -m gpu --noconftest -v

# Frontend
cd D:\rmit\semester_4\project\frontend && npm test
```

---

## 25. Bugs Found and Fixed

All bugs below were discovered and fixed during the testing phase on 2026-06-01 to 2026-06-02.

### Bug 1 -- Sentiment Filter Returns Zero Results

**File:** backend/admin_router.py | **Severity:** High

Frontend sends lowercase `positive`/`neutral`/`negative`. DB stores `Positive`/`Neutral`/`Negative`. SQL used case-sensitive `=` with no normalisation.

```python
# BEFORE
params["sentiment"] = sentiment           # "positive" never matches "Positive"

# AFTER
params["sentiment"] = sentiment.capitalize()  # "positive" -> "Positive"
```

### Bug 2 -- engagement_score=0 Treated as Missing

**File:** backend/quality.py | **Severity:** Medium

`engagement_score or 50` treats `0` as falsy in Python, converting genuine zero-engagement to 50.

```python
# BEFORE
eng = float(engagement_score or 50)  # 0 or 50 = 50 (wrong)

# AFTER
eng = float(engagement_score if engagement_score is not None else 50)
```

Same pattern fixed for conversation_flow and dominant_emotion in the same function.

### Bug 3 -- safe_json_float Ignores Custom Default for None

**File:** backend/database.py | **Severity:** Low

`float(val or 0)` -- `None or 0 = 0`, so custom default was never used for None inputs.

```python
# AFTER
def safe_json_float(val, default=0.0):
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default
```

### Bug 4 -- Wrong JWT Library in Security Tests

**File:** tests/test_security.py | **Severity:** Test infrastructure (3 tests never ran)

Tests used `import jwt as pyjwt` (pyjwt package not installed). Only python-jose is installed. Also used wrong env var name `JWT_SECRET` instead of `JWT_SECRET_KEY`.

```python
# BEFORE
import jwt as pyjwt
secret = os.getenv("JWT_SECRET", "heya_secret_key_2026")

# AFTER
from jose import jwt as jose_jwt
secret = os.getenv("JWT_SECRET_KEY", "heya-ai-voice-analytics-secret-2026-rmit")
```

### Bug 5 -- DetachedInstanceError on User Creation

**File:** backend/admin_router.py | **Severity:** High (POST /admin/users crashed in production)

`new_user.id` and `new_user.email` accessed after the `with get_db()` session closed.

```python
# AFTER -- capture inside session before it closes
with get_db() as db:
    db.add(new_user)
    created_id    = new_user.id
    created_email = new_user.email
return {"status": "created", "user_id": created_id, "email": created_email}
```

### Bug 6 -- DetachedInstanceError in Alert Processing

**File:** backend/alerts.py | **Severity:** High (alert check and digest endpoints crashed)

AlertConfig ORM objects loaded in one session, accessed after session closed. Fixed by converting to plain dicts inside the session block before closing.

### Bug 7 -- Banker's Rounding in Quality Test

**File:** tests/test_quality.py | **Severity:** Test precision only

`round(66.5) = 66` in Python (banker's rounding, rounds to even). Test asserted delta = 25 but actual delta was 24. Test corrected to verify individual scores against formula directly.

### Bug 8 -- /admin/calls Response Shape Mismatch in Tests

**File:** tests/test_admin_calls_filters.py | **Severity:** Test infrastructure (22 tests crashed)

Tests assumed /admin/calls returns a plain list. Actual response is `{"count": N, "calls": [...]}`. All tests updated to extract `response["calls"]` via a helper function.

### Bug 9 -- Admin Feed URL Typo

**File:** tests/test_admin.py | **Severity:** Test always wrong

`"\admin\feed"` in Python contains `\a` (ASCII 7, BEL character) and `\f` (ASCII 12, form feed). Fixed to `"/admin/feed"`. Multi-client verification moved to /admin/calls since /admin/feed hard-caps at 100 rows.

### Bug 10 -- pyannote use_auth_token Deprecation

**Files:** heya_v2 pyannote source (model.py, pipeline.py) | **Severity:** Pipeline tests blocked

Newer huggingface_hub renamed `use_auth_token=` to `token=` in hf_hub_download(). Two pyannote source files patched using regex substitution.

### Bug 11 -- Conversation Flow Boundary Condition Wrong in Tests

**File:** tests/test_pipeline.py | **Severity:** Test wrong, production code correct

Tests asserted `_label(0.6) == "moderate"` and `_label(1.0) == "poor"`. The function uses strict `>` comparisons: 0.6 is not > 0.6 (returns "smooth"), 1.0 is not > 1.0 (returns "moderate"). Tests corrected to match strict-inequality behaviour.

---

## 26. EC2 Production Deployment

These are planning notes for when the platform is deployed to Heya's AWS environment.

### 26.1 Instance Recommendations

| Purpose | Instance | Notes |
|---|---|---|
| Web server + RAG | t3.xlarge | 4 vCPU, 16 GB RAM -- Ollama + Cerebras calls |
| Audio pipeline | g4dn.xlarge | NVIDIA T4, 16 GB VRAM -- pyannote requires GPU |
| Single instance (simplest) | g4dn.xlarge | ~$0.53/hr on-demand -- runs everything |
| OS | Ubuntu 22.04 LTS | No Windows CUDA DLL conflicts, no cp1252 encoding |
| Storage | 100 GB+ EBS | WAV files for 700+ calls are large |

### 26.2 Code Changes Required Before Deploying

1. **frontend/src/api/apiClient.js** -- `baseURL` is hardcoded to `http://localhost:8000`. Change to read from `import.meta.env.VITE_API_URL`.

2. **backend/.env** -- all Windows paths must become Linux paths:
   - `PIPELINE_PYTHON=C:\Users\Bhanu\...` -> `/home/ubuntu/miniconda3/envs/heya_pipeline/bin/python`

3. **Hardcoded Windows paths** -- grep backend for `D:\\rmit` or `C:\\Users\\Bhanu` before deploying.

4. **JWT_SECRET_KEY** -- change from dev placeholder to a cryptographically random value.

5. **Rate limiter** -- replace in-memory defaultdict with Redis for persistence across restarts and multiple workers.

### 26.3 Deployment Steps in Order

```
1.  Provision EC2 (Ubuntu 22.04, open ports 22, 80, 443, 8000)
2.  Install: git, nginx, postgresql-15, nodejs, npm, Miniconda, CUDA 11.8
3.  Install Ollama (Linux): curl -fsSL https://ollama.com/install.sh | sh
4.  Clone/upload project
5.  Transfer call data or confirm existing location on EC2
6.  Create conda environments (heya_v2 + heya_pipeline) with identical packages
7.  Create voice_ai database, enable pgvector + pg_trgm extensions
8.  Run migrations in order: migrate_db -> migrate_pgvector -> migrate_emotion -> migrate_search -> migrate_topics -> migrate_rls
9.  Seed users: python seed_users.py
10. Phase 1 ingestion: python ingest_dataset.py --phase 1
11. Phase 2 pipeline: python ingest_dataset.py --phase 2 (heya_pipeline env)
12. Emotion processing per client (heya_pipeline env)
13. Topic classification: python topic_classifier.py --all
14. Build frontend: VITE_API_URL=http://<ec2-ip>:8000 npm run build
15. Configure nginx: serve frontend/dist/ as static files, proxy /api to localhost:8000
16. Start Ollama as systemd service
17. Start FastAPI as systemd service (heya_v2 env, port 8000)
18. Rebuild RAG vector store (both clients)
```

### 26.4 Key Open Question

**Where does live call data live?** If Heya already stores WAV files on EC2 or S3, step 5 is replaced by pointing ingestion scripts at existing paths. If in S3, a sync script is needed before ingestion.

---

*This document covers the complete Heya AI Voice Analytics Platform as of 2026-06-02.*
*RMIT COSC2667 / COSC2777, Semester 4.*
*Built for [Heya AI](https://heya.au) -- Australia's Smartest AI Voice Agent.*
