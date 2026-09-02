# Heya AI — Setup & Run Instructions

Quick-start guide for running the full platform from a single conda environment.

---

## Prerequisites

- [Miniconda](https://docs.conda.io/en/latest/miniconda.html) — Python 3.11
- [Node.js 18+](https://nodejs.org/) — for the frontend
- PostgreSQL 15 running on port **5435**
- [Ollama](https://ollama.com) — for RAG embeddings
- NVIDIA GPU + CUDA 11.8 — for the audio pipeline
- Cerebras API key — [cloud.cerebras.ai](https://cloud.cerebras.ai)
- Hugging Face token — [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens) (must accept pyannote terms)

---

## Step 1 — Create the Single Conda Environment

Install PyTorch first so CUDA version is pinned before everything else resolves against it.

```bash
conda create -n heya_v2 python=3.10
conda activate heya_v2

# PyTorch + CUDA (must be first)
conda install pytorch torchvision torchaudio pytorch-cuda=11.8 -c pytorch -c nvidia

# Audio pipeline packages
pip install pyannote.audio librosa transformers funasr

# Web server + RAG packages
pip install fastapi uvicorn sqlalchemy psycopg2-binary python-jose bcrypt ^
            python-dotenv pydantic langchain-core langchain-community ^
            openai requests pgvector python-multipart

# funasr upgrades torchaudio and numpy — pin them back for pyannote compatibility
pip install "numpy<2" torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu121

# Verify no conflicts
pip check
```

> `pip check` may still report minor warnings about `async-timeout`, `packaging`, and `protobuf` versions — these are safe to ignore. The app runs fine with them.

---

## Step 2 — Install Frontend Dependencies

```bash
cd D:\rmit\semester_4\project\frontend
npm install
```

---

## Step 3 — Configure Environment Variables

Edit `backend/.env` and fill in your values:

```env
DATABASE_URL=postgresql://postgres:<password>@localhost:5435/voice_ai
APP_DATABASE_URL=postgresql://heya_app:<password>@localhost:5435/voice_ai
CEREBRAS_API_KEY=<your-cerebras-key>
HF_TOKEN=<your-huggingface-token>
JWT_SECRET_KEY=heya-ai-voice-analytics-secret-2026-rmit
UPLOADS_DIR=D:\rmit\semester_4\project\uploads
```

> `PIPELINE_PYTHON` is no longer needed — the web server now uses `sys.executable` automatically.

---

## Step 4 — Database Setup (first time only)

```bash
conda activate heya
cd D:\rmit\semester_4\project\backend

python migrate_db.py
python migrate_pgvector.py
python migrate_emotion.py
python migrate_search.py
python migrate_topics.py
python migrate_rls.py
python seed_users.py
```

---

## Step 5 — Ingest Call Data (first time only)

```bash
conda activate heya
cd D:\rmit\semester_4\project\backend

# Phase 1 — metadata + transcripts (fast, no GPU)
python ingest_dataset.py --phase 1

# Phase 2 — audio pipeline (slow, GPU)
python ingest_dataset.py --phase 2

# Emotion labelling
$env:PYTHONIOENCODING = "utf-8"
python emotion_processor.py --client client_heya_001
python emotion_processor.py --client client_heya_002
```

---

## Step 6 — Build RAG Vector Store (first time only)

Ollama must be running before this step.

```bash
ollama pull nomic-embed-text

conda activate heya
cd D:\rmit\semester_4\project\backend
python rebuild_rag.py
```

---

## Running the Application

Open three terminals.

### Terminal 1 — Backend

```powershell
$env:PYTHONIOENCODING = "utf-8"
conda activate heya_v2
cd D:\rmit\semester_4\project\backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### Terminal 2 — Frontend

```powershell
cd D:\rmit\semester_4\project\frontend
npm run dev
```

Open [http://localhost:5173](http://localhost:5173)

### Terminal 3 — Ollama (for Ask Your Data only)

```powershell
ollama serve
```

Only needed when using the RAG chat or rebuilding embeddings. All other features work without it.

---

## Demo Accounts

| Email | Password | Role |
|---|---|---|
| `admin@heya.au` | `heya_admin_2026` | Heya Admin (all clients) |
| `admin@artel.com` | `artel_2026` | Artel Apartments |
| `admin@mvaallegal.com` | `mvaa_2026` | MVAA Legal |

---

## Pipeline Scripts (all use the same `heya_v2` env)

```powershell
conda activate heya_v2
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project\backend

# Batch process all pending calls
python run_pipeline.py

# Process a single call
python run_single_pipeline.py --call-id <call_id> --audio path\to\audio.wav

# Re-run emotion labelling
python emotion_processor.py --client client_heya_001
python emotion_processor.py --client client_heya_002

# Rebuild RAG embeddings
python rebuild_rag.py
```

---

## Notes

- Always set `$env:PYTHONIOENCODING = "utf-8"` before starting the backend or any pipeline script on Windows — emoji in the codebase causes encoding errors with the default cp1252 codec.
- Sign out and sign in once after a backend restart to refresh the JWT with the `name` field.
- PostgreSQL runs on port **5435**, not the default 5432.
- After the first-time setup (Steps 4–6), only the three terminals in "Running the Application" are needed for day-to-day use.

---

*Last updated: 2026-05-31*
