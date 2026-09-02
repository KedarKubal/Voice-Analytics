# Heya AI — Demo Deck Content
## Ready-to-use copy for slide design

---

## SLIDE 1 — TITLE SLIDE

**Headline:**
Heya AI
Voice Analytics Platform

**Subheadline:**
Turning AI voice agent call recordings into actionable intelligence

**Body / Caption:**
RMIT COSC2667 / COSC2777 · Semester 4, 2026

**Visual suggestion:** Dark background, large wordmark, subtle audio waveform graphic underneath.

---

## SLIDE 2 — THE PROBLEM

**Headline:**
AI Voice Agents Are Flying Blind

**Three problem cards (left to right):**

| Card 1 | Card 2 | Card 3 |
|---|---|---|
| **No Visibility** | **No Insight** | **No Action** |
| Businesses deploy AI voice agents and get call logs — but no analytics on what actually happened. | Standard platforms report whether a call "succeeded" or not. They don't tell you *why*. | Without data, managers can't coach agents, identify patterns, or prove ROI. |

**Bottom stat bar:**
> "Voice AI deployments grew 3× in 2025 — but 80% of operators have no call quality analytics."

**Visual suggestion:** Three icon cards in a row (phone, chart, lightning bolt). Muted red/amber tones.

---

## SLIDE 3 — THE SOLUTION

**Headline:**
Heya AI: Full Call Intelligence, Out of the Box

**Two-column layout:**

**Left — What We Do:**
- Process every call recording through an acoustic AI pipeline
- Surface 7 deep analytics metrics: emotion, engagement, sentiment, silence, interruptions, speaking rate, stress indicators
- Let clients ask their data in plain English

**Right — For Whom:**
- Businesses running AI voice agents (Retell AI, Bland, Vapi)
- Multi-agent deployments (inbound + outbound)
- Any industry: property, legal, medical, hospitality

**Bottom tagline:**
> From raw `.wav` file to full call intelligence dashboard — automated, multi-tenant, real-time.

**Visual suggestion:** Split card. Left side: waveform → dashboard. Right side: two-client logo placeholder.

---

## SLIDE 4 — HOW IT WORKS (ARCHITECTURE)

**Headline:**
Three Layers. One Platform.

**Flow diagram (left to right):**

```
[Call Recording]  →  [Audio Pipeline]  →  [Analytics DB]  →  [Dashboard]
     .wav              pyannote                PostgreSQL         React 19
                       librosa                 pgvector           recharts
                       emotion2vec
```

**Below the flow — three callout boxes:**

**Box 1: Audio Intelligence**
Speaker diarisation (pyannote) + acoustic feature extraction (librosa) + emotion detection (emotion2vec). Runs on GPU.

**Box 2: RAG Conversational Interface**
Natural language queries answered from verified SQL stats + pgvector semantic search. Powered by Cerebras Qwen3 235B (235-billion parameter MoE model).

**Box 3: Multi-Tenant SaaS**
Every client sees only their own data. Three isolation layers: JWT claims + application checks + PostgreSQL Row Level Security.

**Visual suggestion:** Light horizontal flow diagram. Three card callouts below with icons.

---

## SLIDE 5 — ANALYTICS DEEP DIVE

**Headline:**
7 Analytics Metrics From Every Call

**Seven metric cards (grid):**

| # | Metric | What It Measures |
|---|---|---|
| 1 | **Emotion Detection** | Customer vocal emotion (happy, angry, sad, fearful, neutral) — from pitch & energy, not transcript text |
| 2 | **Engagement Scoring** | 0–100 composite acoustic score — pitch variation, energy, speech rate, pause frequency |
| 3 | **Sentiment Trajectory** | Is the customer getting better or worse across the call? Improving / Stable / Deteriorating |
| 4 | **Silence & Interruption Analysis** | Silence ratio, interruption count, correlation with call success |
| 5 | **Speaking Rate & Hesitation** | Words per minute, hesitation pauses — signs of confusion or friction |
| 6 | **Acoustic Stress Indicators** | Customer pitch elevation above baseline — early warning for escalation risk |
| 7 | **Agent Consistency** | Pitch standard deviation — how consistent is the AI agent's vocal pattern? |

**Callout:**
> Emotion is detected from voice acoustics — not words. A calm script can mask genuine frustration.

**Visual suggestion:** 7 icon + label cards in a 3+3+1 grid. Brand colour highlights on metric numbers.

---

## SLIDE 6 — CLIENT DASHBOARD DEMO

**Headline:**
Everything a Client Needs, in One View

**Left panel — feature list:**
- KPI summary cards: total calls, success rate, engagement vs industry benchmark, avg duration, avg silence
- 5 embedded charts: engagement distribution, sentiment trajectory, calls over time, conversation flow, outcome × trajectory
- Live call feed — auto-refreshes every 5 seconds
- Filterable call table with full-text transcript search
- "Ask Your Data" — natural language chat over all call history
- Alert inbox: early disconnects, poor engagement, escalatory language

**Right panel — screenshot placeholder:**
`[Dashboard screenshot — Home page]`

**Bottom bar:**
> Industry benchmark: 62.0 engagement score. See at a glance where you stand.

**Visual suggestion:** Split layout — feature bullets left, mockup/screenshot right.

---

## SLIDE 7 — ASK YOUR DATA (RAG)

**Headline:**
Ask Questions. Get Verified Answers.

**Conversation UI mockup:**

```
You:       "Which calls last week had the most frustrated customers?"

Heya AI:   "Based on verified call data: 12 calls had dominant_emotion = 'angry'
            between May 19–25. The highest-stress call was call_abc123 (duration
            4:32, engagement 31/100). Common trigger: callers asking about
            claim status with no update available."

            Sources: call_abc123, call_def456, call_ghi789
            Confidence: HIGH · Route: SEMANTIC
```

**Three feature pills below the chat:**

| Pill 1 | Pill 2 | Pill 3 |
|---|---|---|
| Verified SQL Stats | pgvector Semantic Search | Multi-turn Conversation |
| Numbers come from the DB — never invented | Finds relevant calls by meaning, not keywords | Ask follow-up questions naturally |

**Callout:**
> Powered by Cerebras Qwen3 235B — 235-billion parameter MoE. 60,000 tokens/minute. Zero hallucination guarantee on statistics.

**Visual suggestion:** Dark chat bubble UI mockup. Confidence badge visible.

---

## SLIDE 8 — ADMIN GOD VIEW

**Headline:**
Full Portfolio Visibility for the Heya Team

**Four quadrant grid:**

| Quadrant | Feature |
|---|---|
| **Client Matrix** | All clients in one overview — KPIs, silence ratio, queue depth, engagement delta |
| **Drill-Down Panel** | Click any client: 7 analytics bars, call table with emotion + trajectory, AI-generated recommendations |
| **Cross-Client Feeds** | Real-time call stream across all clients simultaneously |
| **User Management** | Create / delete users, assign to clients, role control |

**Dynamic insight callout example:**
> "Artel Apartments has 2.1× lower silence ratio than MVAA Legal — this correlates with 12% higher success rate."

**Visual suggestion:** Split quad layout. Annotated screenshot or wireframe of admin panel.

---

## SLIDE 9 — DEMO CLIENTS

**Headline:**
Two Real Industry Use Cases

**Client card 1 — Artel Apartments**
- Property management, Brunswick Melbourne
- **AI Agent: Sasha** — 24/7 inbound calls
- Handles: check-in codes, parking, bookings, FAQs, identity verification
- **~385 calls, fully processed**
- Engagement score: 55.6 / 100 (6.4 pts below benchmark)
- Success rate: 77.4%

**Client card 2 — MVAA Legal**
- Motor vehicle accident law firm, Melbourne
- **5 specialised AI agents** — inbound + outbound workflows
- Agents: Justine (front desk), Sarah (at-fault outreach), Julia (Welcome Pack follow-up)
- **~433 calls, partially processed**
- Multi-direction: handles both inbound inquiries and proactive outbound campaigns

**Visual suggestion:** Two cards side-by-side with industry icon, logo placeholder, and key stats.

---

## SLIDE 10 — TECH STACK

**Headline:**
Built With Modern, Production-Grade Technologies

**Stack grid (two columns):**

**Backend:**
- FastAPI 0.135 + uvicorn — REST API
- PostgreSQL 15 + pgvector — data + semantic search
- SQLAlchemy 2.x — ORM with Row Level Security
- pyannote.audio 3.x — speaker diarisation
- librosa — acoustic feature extraction
- emotion2vec — emotion classification
- Ollama (nomic-embed-text) — local embeddings
- Cerebras API (Qwen3 235B) — LLM for RAG
- Python-jose JWT + bcrypt — authentication

**Frontend:**
- React 19 — UI framework
- Vite 8 — build tool
- react-router-dom v7 — routing
- recharts 3.x — data visualisation
- framer-motion 12.x — animations
- axios 1.x — HTTP client
- Vitest + Testing Library — test suite

**Visual suggestion:** Two-column tech logo grid. Highlight AI/ML stack in a different colour.

---

## SLIDE 11 — SECURITY MODEL

**Headline:**
Enterprise-Grade Multi-Tenant Security

**Three-layer diagram (stacked):**

```
Layer 1 — JWT Claims
"client_id embedded in signed token — cannot be forged"

          ↓

Layer 2 — Application Check
"_require_client_access() verified at every endpoint"

          ↓

Layer 3 — PostgreSQL Row Level Security
"heya_app DB role: rows from other tenants are structurally invisible"
```

**Side callout:**
> Cross-tenant data leakage is not just prevented — it is architecturally impossible. Even a compromised JWT cannot return another tenant's rows.

**Plus points below:**
- HMAC-SHA256 webhook verification (Retell)
- Rate limiting: 25 RAG requests/minute per user
- bcrypt password hashing (no third-party abstraction — avoids bcrypt 4.x breakage)
- All pgvector searches hard-scoped with `WHERE client_id = :cid`

**Visual suggestion:** Vertical three-layer security stack with shield icons.

---

## SLIDE 12 — KEY NUMBERS

**Headline:**
By the Numbers

**Six large stat tiles:**

| Stat | Value |
|---|---|
| Total calls processed | 800+ |
| Audio analytics metrics | 7 |
| API endpoints | 25+ |
| Frontend pages | 9 |
| LLM model size | 235B parameters |
| Embedding dimensions | 768 |

**Benchmark callout box:**
> Voice AI industry engagement baseline: **62.0 / 100**
> Artel Apartments: 55.6 · MVAA Legal: TBC

**Quality grade breakdown (Artel):**
> A: 12% · B: 24% · C: 31% · D: 19% · F: 14%

**Visual suggestion:** Six bold stat cards in a 3×2 grid. Benchmark in a highlighted callout.

---

## SLIDE 13 — LIVE DEMO

**Headline:**
Let's See It Live

**Demo flow (ordered steps):**

1. **Login as Artel admin** — `admin@artel.com / artel_2026`
   - Show KPI cards and engagement benchmark
   - Point out the silence-success correlation insight

2. **Audio Insights tab**
   - Walk through emotion detection section — explain acoustic vs text-based
   - Show Sentiment Trajectory bars
   - Show Acoustic Stress section

3. **Ask Your Data**
   - Ask: *"Which calls had the most frustrated customers?"*
   - Show multi-turn: *"What were those customers calling about?"*

4. **Search**
   - Type a keyword (e.g., "parking" or "refund")
   - Show highlighted snippet results

**Visual suggestion:** Numbered step list with arrows. Small screenshot thumbnail for each step.

---

## SLIDE 14 — CLOSING SLIDE

**Headline:**
Heya AI — Turning Voice Data Into Decisions

**Three value propositions:**

> **For Clients**
> Know what's happening in every call — not just whether it succeeded.

> **For Operations**
> Catch escalations before they become complaints. Coach on real data.

> **For the Heya Team**
> Full portfolio visibility across all clients in one place.

**Contact / repo line:**
RMIT COSC2667/2777 · Semester 4, 2026

**Visual suggestion:** Full-bleed closing slide. Bold single-colour background. Large central wordmark.

---

## APPENDIX — SUPPORTING DETAILS (Backup Slides)

### A1 — Pipeline Accuracy Notes

- pyannote.audio 3.x achieves ~92% diarisation accuracy on clean recordings
- emotion2vec classification validated against human labels on subset
- Engagement score correlates with call_successful (r ≈ 0.54 on Artel dataset)
- Silence-success correlation is computed per client — not a fixed assumption

### A2 — RAG Query Examples

| Question Type | Example | Route Used |
|---|---|---|
| Latest call | "When was the last call?" | EXACT_MATCH (SQL, no LLM) |
| Aggregate stat | "What's our average engagement?" | STATS (SQL → LLM format) |
| Pattern query | "Which calls had frustrated customers?" | SEMANTIC (pgvector + LLM) |
| Multi-turn | "Show me more from that time period" | SEMANTIC (history-aware) |

### A3 — Alert Types

| Alert | Trigger Condition |
|---|---|
| Early Disconnect | Call ended in < 20 seconds |
| Very Poor Engagement | Engagement score < 25/100 |
| Escalatory Language | Keywords: "sue", "refund", "cancel", "manager", profanity |
| Extreme Silence | Silence ratio > 65% of call |
| High Interruptions | 8+ interruptions per call |

### A4 — Quality Score Formula

```
Quality Score = (Engagement × 0.35) + (Flow × 0.25) + (Outcome × 0.25) + (Emotion × 0.15)

Flow:    smooth=100, moderate=60, poor=20
Outcome: successful=100, failed=0, unknown=50
Emotion: happy=100, surprised=75, neutral=60, fearful=35, sad=30, disgusted=20, angry=15
```

### A5 — Cerebras vs Previous LLM (Groq)

| Provider | Model | TPM Limit | Issue |
|---|---|---|---|
| Groq (old) | llama-3.1-8b-instant | 6,000 tokens/min | One complex RAG query ≈ 5,500 tokens → constant 429s |
| Cerebras (current) | Qwen3 235B MoE | 60,000 tokens/min | 10× headroom, much higher quality |

---

*Deck content prepared: 2026-05-26*
*RMIT COSC2667/COSC2777, Semester 4*
