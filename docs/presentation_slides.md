# Heya AI — Presentation Slides
**What? So What? Now What? Structure**
**RMIT COSC2667/2777 | Semester 4 | 2026**

---

## ── WHAT ──
*"Here's what we built."*

---

### SLIDE 1 — Title

**Heya AI**
*Voice Agent Intelligence Platform*

> Turning AI voice call recordings into actionable business insight

---

### SLIDE 2 — What Is Heya AI?

**One sentence:**
> Heya AI processes AI voice agent call recordings and surfaces call intelligence to business clients — in real time, in plain English.

**Two components:**

| Component | What it does |
|---|---|
| **Audio Intelligence Pipeline** | Processes raw recordings → engagement scores, sentiment, emotion, flow quality, silence, interruptions |
| **RAG Conversational Interface** | Natural-language querying over all call data — no SQL required |

**Two real clients. 792 real calls.**

---

### SLIDE 3 — The Two Clients

| Client | Industry | Calls | Agents |
|---|---|---|---|
| **Artel Apartments** | Property management | 371 | Sasha (inbound concierge) |
| **MVAA Legal** | Legal services | 421 | Justine, Sarah, Julia |

> Not synthetic data. Not mock data. Real recordings processed end-to-end.

---

### SLIDE 4 — DEMO HANDOFF

**"Let me show you rather than tell you."**

> Share URL with the room: `http://<your-ip>:5173`

**Guide them through — in this order:**

**Step 1 — Client view (Artel)**
- Log in as `admin@artel.com` / `artel_2026`
- Overview page → KPI cards (total calls, engagement, quality, agents)
- Calls page → apply a filter live (e.g. Flow = Interrupted)
- Analytics page → scroll through engagement + sentiment sections

**Step 2 — Ask Your Data**
- Go to Ask Your Data tab
- Type a live RAG question: *"Which calls had the lowest engagement this month?"*
- Show the answer + click a suggestion pill
- Click the Sasha agent card → run an agent analysis

**Step 3 — Admin view**
- Log in as `admin@heya.au` / `heya_admin_2026`
- Feed tab → show live 18-column table, apply client filter, show CSV export
- Intelligence tab → select "Platform Overview (All Clients)" → ask a cross-client question live

> **Let them explore freely for 2-3 minutes after the guided tour.**

---

## ── SO WHAT ──
*"Here's why what you just saw matters."*

---

### SLIDE 5 — The Gap Heya Fills

**The problem no one has solved yet:**

- Businesses are deploying AI voice agents at scale — inbound, outbound, 24/7
- Every call is recorded
- **Nobody is analysing them**

> Existing call analytics tools were built for human agents. They don't account for AI-specific dynamics — turn structure, acoustic signals, engagement patterns.

**Heya fills that gap.**

---

### SLIDE 6 — What You Just Experienced

**What the demo showed — translated into business value:**

| You saw | What it means |
|---|---|
| Engagement scores per call | Know instantly which calls connected and which didn't |
| Flow labels (smooth / hesitant / interrupted) | Identify where the AI agent is losing customers |
| Sentiment trajectory | See if customers warmed up or disengaged over the call |
| RAG query answered in seconds | A non-technical manager can interrogate 792 calls in plain English |
| Cross-client Intelligence (admin) | Platform-wide benchmarking — compare agents across clients |
| Live Feed with auto-refresh | Real-time operational visibility — no manual reporting |

---

### SLIDE 7 — Built for Production, Not Just Demo

**Multi-tenant security at every layer:**

| Layer | Mechanism |
|---|---|
| Authentication | JWT HS256, bcrypt, 30-min tokens |
| API | Client ID verified on every endpoint |
| Database | PostgreSQL Row-Level Security — heya_app role with per-client policies |
| RAG | pgvector semantic search filtered by client_id |
| Agent engine | System prompt built dynamically from DB — agent names never hardcoded |

> MVAA cannot see Artel's data. Artel cannot see MVAA's data. Enforced at the database level — not just the API.

---

### SLIDE 8 — The Numbers

> **792 calls. 4 agents. 2 clients. 7 analytics metrics. 1 unified platform.**

| Metric | Value |
|---|---|
| Total calls processed | 792 |
| Pipeline completion | 100% (Artel) + 99.5% (MVAA — 2 skipped, immediate hangups) |
| LLM powering RAG | Cerebras gpt-oss-120b (120 billion parameters) |
| Embedding search | pgvector — sub-second semantic retrieval |
| Frontend | React 19 + Vite 8 — dark/light theme, fully responsive |
| Auth | JWT + bcrypt + PostgreSQL RLS |

---

### SLIDE 9 — Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, Python 3.11, SQLAlchemy 2.x |
| Database | PostgreSQL 15, pgvector extension |
| Audio AI | pyannote.audio 3.x, librosa, emotion2vec, torch 2.5.1 (CUDA 12.1) |
| RAG | LangChain 0.2+, pgvector, Ollama embeddings |
| LLM | Cerebras API — gpt-oss-120b via openai SDK |
| Frontend | React 19, Vite 8, recharts, framer-motion, axios |

---

## ── NOW WHAT ──
*"Here's where this goes."*

---

### SLIDE 10 — Roadmap

**What's next for Heya AI:**

| Feature | Why |
|---|---|
| **Real-time call streaming** | Pipeline currently runs batch — live analysis during calls is the next frontier |
| **Automated weekly reports** | Email digest of insights delivered to clients without them logging in |
| **More clients onboarded** | Beyond the 2 demo tenants — the platform is multi-tenant ready |
| **Fine-tuned emotion model** | emotion2vec is general-purpose — training on voice-agent data will lift accuracy |
| **Call outcome prediction** | Predict whether a customer will convert before the call ends |

---

### SLIDE 11 — Closing

**Heya AI in one line:**

> *"We built the analytics layer that AI voice agents were missing — and made it accessible to anyone, not just engineers."*

- 792 real calls processed
- Plain-English querying over all of it
- Production-grade security from day one
- Ready to onboard the next client today

**Thank you — questions welcome.**

---

## Speaker Notes

### Timing Guide

| Section | Slides | Time |
|---|---|---|
| WHAT (intro) | 1–3 | 2 min |
| WHAT (demo) | 4 | 8–10 min |
| SO WHAT | 5–9 | 5–6 min |
| NOW WHAT | 10–11 | 2 min |
| **Total** | | **~17–20 min** |

### Demo Day Checklist
- [ ] Backend running: `$env:PYTHONIOENCODING="utf-8"` → `uvicorn main:app --host 0.0.0.0 --port 8000`
- [ ] Frontend running: `npm run dev` (with `host: true` in vite.config.js)
- [ ] Ollama running: `ollama serve`
- [ ] Local IP noted: run `ipconfig`, find WiFi IPv4
- [ ] Everyone on same WiFi
- [ ] URL ready to share: `http://<your-ip>:5173`
- [ ] Demo accounts ready: artel_2026 / mvaa_2026 / heya_admin_2026
- [ ] RAG pre-warmed: run one query before the presentation starts

### Live RAG Questions to Use
- *"Which calls had the lowest engagement this month?"*
- *"What is the most common call topic for inbound calls?"*
- *"Which agent has the best quality scores?"* (admin cross-client)
