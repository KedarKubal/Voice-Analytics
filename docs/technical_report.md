# Heya AI — Technical Report
**RMIT COSC2667/2777 | Semester 4 | 2026**

---

## Executive Summary

Heya AI is a multi-tenant Software-as-a-Service (SaaS) platform designed to process AI voice agent call recordings and surface actionable call intelligence to business clients. The platform addresses a gap in the AI voice agent market: businesses deploying conversational AI at scale lack purpose-built tooling to analyse call quality, agent performance, and customer engagement at volume.

The system comprises two primary components: an **Audio Intelligence Pipeline** that processes raw recordings through speaker diarization, acoustic feature extraction, and emotion detection; and a **RAG Conversational Interface** that enables natural-language querying of call data backed by a 120-billion-parameter large language model.

The platform currently serves two demo clients — Artel Apartments (371 calls) and MVAA Legal (421 calls) — with full pipeline processing complete. The frontend is a React 19 single-page application; the backend is a FastAPI service with PostgreSQL 15 and pgvector for semantic search.

---

## 1. Introduction

### 1.1 Background

AI voice agents are increasingly deployed by businesses for inbound customer service, outbound follow-up, and debt collection. These agents generate substantial volumes of call recordings. However, the analytics infrastructure to meaningfully evaluate these calls — at the level of engagement quality, sentiment dynamics, or agent effectiveness — does not exist as a purpose-built product.

Existing call analytics tools were designed for human agents and do not account for the specific dynamics of AI-human conversations: the absence of human hesitation, the predictable turn structure, or the value of acoustic signals as proxies for call quality.

### 1.2 Project Objectives

1. Build an end-to-end pipeline that transforms raw audio recordings into structured analytical data.
2. Store and query that data efficiently at scale using a relational database with vector search capabilities.
3. Expose the data through a multi-tenant API with strong client isolation.
4. Provide a conversational analytics interface using a large language model.
5. Deliver a React frontend that makes the data accessible to non-technical business users.

### 1.3 Scope

The project covers two clients across two industries (property management and legal services), four AI agents across inbound and outbound directions, and approximately 792 calls processed end-to-end through the full pipeline.

---

## 2. System Architecture

### 2.1 High-Level Overview

The system is structured in five layers:

```
Layer 1: Audio Recordings (raw .wav / .mp3 files)
Layer 2: Pipeline (pyannote + librosa + emotion2vec)
Layer 3: PostgreSQL 15 (voice_ai database, pgvector extension)
Layer 4: FastAPI Backend (REST API, auth, RAG, agent engine)
Layer 5: React Frontend (client dashboard + admin dashboard)
```

Data flows strictly downward. The pipeline writes to PostgreSQL; the backend reads from PostgreSQL; the frontend reads from the backend via authenticated HTTP. There are no direct frontend-to-database connections.

### 2.2 Deployment Configuration

| Component | Host | Port |
|---|---|---|
| PostgreSQL 15 | localhost | 5435 (non-default) |
| FastAPI (uvicorn) | 0.0.0.0 | 8000 |
| React (Vite dev server) | localhost | 5173 |

The non-default PostgreSQL port (5435) is an intentional configuration to avoid conflicts with other local PostgreSQL instances.

### 2.3 Environment

All Python components run in a single unified Conda environment: `heya_v2` (Python 3.10, torch 2.5.1+cu121). This consolidates the web server and GPU pipeline into one environment, eliminating activation friction during development and demos.

---

## 3. Database Design

### 3.1 Core Tables

| Table | Purpose |
|---|---|
| `clients` | Tenant registry — client_id, name, industry |
| `users` | Platform users — email, hashed_password, role, client_id |
| `agents` | AI agent definitions — persona_name, direction, role, client_id |
| `call_metadata` | Per-call metadata — client_id, agent_id, direction, topic, duration, `start_timstamp` |
| `audio_insights` | Pipeline output — engagement_score, quality_grade, flow_label, sentiment, silence_ratio, interruptions, dominant_emotion, trajectory |
| `call_embeddings` | pgvector — 1536-dim embeddings per call (for RAG) |
| `agent_embeddings` | pgvector — 1536-dim embeddings per agent interaction |

> Note: The `start_timstamp` column in `call_metadata` contains a deliberate typo (one 't'). This is a known legacy artefact mapped to `start_timestamp` in the Python ORM layer. The column name must not be corrected as it would require a destructive migration.

### 3.2 Multi-Tenancy

Row-Level Security (RLS) is enabled on all key tables. A dedicated database role `heya_app` holds the application credentials, and PostgreSQL policies enforce that queries through `heya_app` only return rows matching the authenticated client's `client_id`. This provides defence-in-depth: even if the API layer's client isolation were bypassed, the database would not return cross-tenant data.

### 3.3 Sentiment Value Encoding

The `user_sentiment` column stores capitalised values: `'Neutral'`, `'Positive'`, `'Negative'`, `'Unknown'`. All frontend comparisons normalise these with `.toLowerCase()` before lookup against CSS class maps or metadata objects.

---

## 4. Audio Intelligence Pipeline

### 4.1 Overview

The pipeline processes each call recording through seven sequential stages, producing a row in `audio_insights` per call.

### 4.2 Stage 1: Speaker Diarization

**Tool:** pyannote.audio 3.x  
**Model:** `pyannote/speaker-diarization-3.1`  
**GPU:** torch 2.5.1, CUDA 12.1

Diarization segments each recording into speaker turns, assigning each turn to either the AI agent (speaker 0) or the customer (speaker 1). This is foundational — all downstream features are computed per speaker or per turn.

### 4.3 Stage 2: Acoustic Feature Extraction

**Tool:** librosa  
Per speaker turn, the pipeline extracts:
- Pitch (F0) mean and variance
- RMS energy
- Speaking rate (syllables per second, estimated via zero-crossing rate)
- Spectral centroid

### 4.4 Stage 3: Engagement Scoring

A composite engagement score (0–100) is computed from:
- Turn balance ratio (agent vs. customer speaking time)
- Energy variance across the call
- Pause frequency and duration
- Turn length distribution

Scores above 70 are considered high-engagement; below 40, low-engagement.

### 4.5 Stage 4: Flow Labeling

Each call is assigned one of four flow labels:
- `smooth` — balanced turns, low interruptions, natural pacing
- `hesitant` — long silences, low customer energy
- `interrupted` — high cross-talk count
- `abandoned` — call ends early without resolution

### 4.6 Stage 5: Sentiment Trajectory

Sentiment is assessed per call segment and an arc is derived:
- `improving` — sentiment moves positive over the call
- `declining` — sentiment degrades
- `stable` — consistent throughout
- `volatile` — high variance with no clear direction

### 4.7 Stage 6: Silence and Interruption Detection

- **Silence ratio**: proportion of call duration with no speaker activity
- **Interruption count**: number of turn overlaps exceeding a 200ms cross-talk threshold

### 4.8 Stage 7: Emotion Detection

**Tool:** emotion2vec (`emotion_processor.py`)  
Assigns a dominant emotion label per call (e.g., `happy`, `neutral`, `angry`, `sad`, `fearful`). Runs as a separate post-processing step.

### 4.9 Pipeline Status

| Client | Total Calls | Processed | Skipped | Reason |
|---|---|---|---|---|
| Artel Apartments | 371 | 371 | 0 | — |
| MVAA Legal | 421 | 419 | 2 | Immediate hangups (< 3s, no diarizable content) |

---

## 5. RAG Conversational Interface

### 5.1 Architecture

The Retrieval-Augmented Generation (RAG) system enables natural-language queries over call data. It combines three information sources:

1. **Real-time SQL statistics** — computed at query time from PostgreSQL (averages, distributions, totals)
2. **Semantic search** — pgvector similarity search over `call_embeddings` and `agent_embeddings`
3. **LLM synthesis** — Cerebras `gpt-oss-120b` generates the final answer

### 5.2 Query Routing

Incoming queries are classified before retrieval:
- **Direct SQL route** — numeric questions with clear aggregation intent bypass the vector store for speed
- **Semantic route** — exploratory or qualitative questions use pgvector similarity search
- **Admin platform route** — cross-client queries skip per-client scoping

### 5.3 Embeddings

Embeddings are generated offline using Ollama (local model). The vector store is rebuilt explicitly via `python rebuild_rag.py` — never inline during API requests. This keeps query latency predictable and avoids blocking the API under load.

### 5.4 LLM: Cerebras

The Cerebras API is accessed via the `openai` SDK with a `base_url` override:

```python
client = openai.OpenAI(
    api_key=CEREBRAS_API_KEY,
    base_url="https://api.cerebras.ai/v1"
)
```

LangChain LLM wrappers are not used for Cerebras — they are incompatible with the Cerebras API's response format. The `gpt-oss-120b` model (120B parameters) is used in production; `zai-glm-4.7` is available as a preview alternative.

### 5.5 Admin Cross-Client Mode

When `client_id == "heya_admin"`, the RAG system switches to platform-wide mode:
- Stats context includes all clients + per-client breakdown
- Semantic search queries all embeddings without client_id filtering
- System prompt allows cross-client comparisons
- Frontend shows a CROSS-CLIENT badge in admin chat responses

---

## 6. Agent Analysis (ReAct Engine)

### 6.1 Overview

Beyond simple RAG queries, the platform includes a ReAct (Reasoning + Acting) agent engine for deeper call intelligence. The engine reasons step-by-step through a query, selecting tools as needed, before synthesising a final answer.

### 6.2 Tools

The agent has access to four tools:
1. **Call statistics tool** — retrieves aggregate stats for a specified agent
2. **Semantic search tool** — searches call embeddings for relevant examples
3. **Trend analysis tool** — computes temporal trends over configurable windows
4. **Agent performance tool** — cross-agent comparison within a client

### 6.3 Client Isolation

Agent names in the system prompt are dynamically built from the database:

```python
def _client_agent_options(client_id: str) -> str:
    # Queries agents table filtered by client_id
    # Returns comma-separated persona_name list
```

This ensures MVAA agents (Justine, Sarah, Julia) are never visible to Artel users (Sasha), and vice versa. Hardcoding agent names in the system prompt was a prior security gap that has been corrected.

### 6.4 Response Format

Agent responses include:
- Final answer text
- Confidence badge (High / Medium / Low)
- Tools used (displayed as chips)
- Step count and execution time (ms)
- Collapsible reasoning chain (full ReAct trace)

---

## 7. Authentication & Authorisation

### 7.1 JWT Authentication

- **Algorithm:** HS256
- **Library:** python-jose
- **Token lifetime:** 30 minutes
- **Payload:** `sub` (email), `client_id`, `role`, `name`

Tokens are stored in `localStorage` on the frontend and attached as `Authorization: Bearer <token>` headers by the axios client.

### 7.2 Password Hashing

bcrypt is used directly (not via passlib). passlib introduced a breaking incompatibility with bcrypt 4.x that caused all password verifications to fail. Direct bcrypt usage resolves this.

### 7.3 Endpoint Protection

`verify_client()` is a plain function (not a FastAPI `Depends()`) that extracts and validates the client_id from the JWT. It is called at the top of every protected endpoint. This is an intentional design choice.

### 7.4 Role Hierarchy

| Role | Access |
|---|---|
| `heya_admin` | All clients, all agents, platform-wide analytics |
| `client` | Own client data only, filtered by client_id |

---

## 8. Frontend

### 8.1 Technology

- **Framework:** React 19 with Vite 8
- **Routing:** react-router-dom v7
- **Charts:** recharts
- **Animation:** framer-motion
- **HTTP:** axios (auto-attaches JWT Bearer token)

### 8.2 State Management

No Redux. State is managed through three contexts and one custom hook:

| Module | Responsibility |
|---|---|
| `AuthContext.jsx` | JWT storage, login/logout, `ready` flag (prevents render before auth resolves) |
| `FilterContext.jsx` | Global filter state (date range, flow, direction, topic, trajectory, sentiment, agent) |
| `ThemeContext.jsx` | Dark/light theme, persisted to localStorage as `heya_theme` |
| `useClientData.js` | Fetches `/stats` and `/insights` together; all pages consume this hook |

Page components do not fetch data directly — they consume the shared hook.

### 8.3 Theming

The theme system uses a CSS variable approach:
- `:root` defines the dark theme palette (8 base colours + tooltip, track, hover, line, inset variables)
- `[data-theme="light"]` overrides all variables with the light palette
- `data-theme` is set on `<html>` by `ThemeContext`
- All hardcoded colour values in JSX have been replaced with CSS variables

### 8.4 Client Dashboard Pages

| Page | Description |
|---|---|
| Overview | KPI cards, recent activity |
| Analytics | 7 metrics sections (engagement, flow, sentiment, silence, interruptions, emotion, topics) |
| Calls | Full call table, 13 columns, 7 filter dimensions, per-call detail |
| Ask Your Data | RAG chat with suggestion pills + Agent Analysis section |

### 8.5 Admin Dashboard Pages

| Page | Description |
|---|---|
| Overview | Platform totals, per-client breakdown |
| Feed | Live 18-column call table, 9 filters, CSV export, 5s auto-refresh |
| Intelligence | Cross-client RAG chat |
| Analytics | Platform-wide aggregated metrics |

---

## 9. API Reference Summary

### Authentication
- `POST /auth/login` — returns JWT

### Client Endpoints (Bearer auth required)
- `GET /stats/{client_id}` — aggregate stats
- `GET /insights/{client_id}` — all calls with audio insights
- `POST /query/{client_id}` — RAG query
- `POST /agent/analyze/{client_id}` — ReAct agent analysis
- `GET /agent/tools` — list available agent tools

### Admin Endpoints (heya_admin role required)
- `GET /admin/overview` — platform summary
- `GET /admin/calls` — all calls, 9 filter params, limit 500
- `GET /admin/agents?client_id=` — agents for a client
- `GET /admin/feed` — live feed
- `GET /admin/query-analytics` — RAG usage stats

---

## 10. Known Issues and Limitations

| Issue | Status | Notes |
|---|---|---|
| Some calls missing `dominant_emotion` | Open | Re-run `emotion_processor.py` for both clients |
| 2 MVAA calls unprocessable | Resolved | Marked `processing_status=skipped_empty` — immediate hangups |
| JWT `name` field missing after backend restart | Workaround | Sign out and sign in once to refresh token |
| Offline RAG rebuild required after new calls | By design | Run `python rebuild_rag.py` — never auto-triggered |
| No real-time pipeline | Out of scope | Pipeline is batch-only; real-time streaming is future work |

---

## 11. Conclusion

Heya AI demonstrates a complete production-oriented stack for AI voice agent analytics. The system processes 792 real-world call recordings through a GPU-accelerated pipeline, stores structured analytical data in a multi-tenant PostgreSQL database, and exposes it through a secure REST API to a polished React frontend.

The RAG conversational interface — combining pgvector semantic search with a 120B-parameter LLM — enables non-technical users to explore their call data without writing SQL. The ReAct agent engine adds reasoning-depth to complex queries. Multi-tenancy is enforced at every layer from JWT to Row-Level Security.

The platform is extensible: real-time streaming, additional clients, and fine-tuned emotion models are clear next steps on a solid architectural foundation.

---

*Report generated: 2026-06-02*
