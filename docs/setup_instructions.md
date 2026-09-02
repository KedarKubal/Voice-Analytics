# Heya AI — Setup & Deployment Instructions
**For developers and system administrators**

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Windows 10/11 | Any | Linux/macOS with path adjustments |
| Miniconda / Anaconda | Latest | For Python environment management |
| Node.js | 18+ | For the React frontend |
| PostgreSQL | 15 | Must run on port **5435** |
| NVIDIA GPU | Any CUDA 12.1 compatible | Required for pyannote pipeline |
| CUDA Toolkit | 12.1 | Paired with torch 2.5.1 |

---

## 1. Database Setup

### 1.1 Start PostgreSQL

Ensure PostgreSQL 15 is running and listening on port **5435** (not the default 5432).

If you need to configure the port, edit `postgresql.conf`:
```
port = 5435
```
Then restart the service.

### 1.2 Create the Database

```sql
CREATE DATABASE voice_ai;
CREATE USER heya_app WITH PASSWORD '<your_password>';
GRANT ALL PRIVILEGES ON DATABASE voice_ai TO heya_app;
```

### 1.3 Enable pgvector Extension

```sql
\c voice_ai
CREATE EXTENSION IF NOT EXISTS vector;
```

### 1.4 Run Migrations

From the backend directory:
```powershell
cd D:\rmit\semester_4\project\backend
conda activate heya_v2
python -c "from database import Base, engine; Base.metadata.create_all(engine)"
```

### 1.5 Seed Demo Data

```powershell
python ingest_dataset.py --phase 1  # metadata + transcripts
```

---

## 2. Python Environment Setup

### 2.1 Create the heya_v2 Environment

```powershell
conda create -n heya_v2 python=3.10 -y
conda activate heya_v2
```

### 2.2 Install PyTorch (CUDA 12.1)

```powershell
pip install torch==2.5.1+cu121 torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
```

### 2.3 Install Backend Dependencies

```powershell
pip install fastapi uvicorn sqlalchemy psycopg2-binary python-jose bcrypt
pip install pyannote.audio librosa
pip install langchain langchain-community pgvector openai
pip install python-multipart python-dotenv
```

### 2.4 Install Ollama (Embeddings)

Download and install Ollama from the official website. Then pull the embedding model:
```powershell
ollama pull nomic-embed-text
```

Ollama must be running before starting the backend if RAG features are needed.

---

## 3. Environment Variables

Create a `.env` file in `D:\rmit\semester_4\project\backend\`:

```env
# Database
DATABASE_URL=postgresql://heya_app:<password>@localhost:5435/voice_ai
APP_DATABASE_URL=postgresql://heya_app:<password>@localhost:5435/voice_ai

# JWT
SECRET_KEY=<your_secret_key_min_32_chars>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Cerebras LLM
CEREBRAS_API_KEY=<your_cerebras_api_key>

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
```

> **Security note:** Never commit `.env` to version control. Add it to `.gitignore`.

---

## 4. Starting the Backend

```powershell
# Set UTF-8 encoding (required on Windows — prevents UnicodeEncodeError)
$env:PYTHONIOENCODING = "utf-8"

conda activate heya_v2
cd D:\rmit\semester_4\project\backend

python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

The API will be available at `http://localhost:8000`.  
Interactive docs: `http://localhost:8000/docs`

> **Important:** The `PYTHONIOENCODING=utf-8` environment variable **must** be set before starting uvicorn. The database contains emoji characters that cause a `UnicodeEncodeError` with Windows' default cp1252 encoding.

---

## 5. Starting the Frontend

```powershell
cd D:\rmit\semester_4\project\frontend
npm install        # first time only
npm run dev
```

The frontend will be available at `http://localhost:5173`.

---

## 6. Running the Audio Pipeline

### 6.1 Prerequisites

The `heya_v2` environment handles both the web server and the pipeline.

Ensure audio files are placed in the expected dataset directory structure:
```
D:\rmit\semester_4\project\dataset\
  └── <client_id>\
        └── <call_id>.wav
```

### 6.2 Run the Pipeline

```powershell
conda activate heya_v2
cd D:\rmit\semester_4\project\backend

# Phase 1: ingest metadata and transcripts
python ingest_dataset.py --phase 1

# Phase 2: run audio pipeline (diarization + acoustic features)
python ingest_dataset.py --phase 2 --client client_heya_001
python ingest_dataset.py --phase 2 --client client_heya_002
```

Pipeline output (diarization cache, feature files) is written to:
```
D:\rmit\semester_4\project\pipeline_output\
```

### 6.3 Run Emotion Detection (Post-Processing)

```powershell
$env:PYTHONIOENCODING = "utf-8"
conda activate heya_v2
cd D:\rmit\semester_4\project\backend

python emotion_processor.py --client client_heya_001
python emotion_processor.py --client client_heya_002
```

---

## 7. Rebuilding the RAG Vector Store

The vector store must be rebuilt explicitly after adding new processed calls. It is never rebuilt automatically.

```powershell
conda activate heya_v2
cd D:\rmit\semester_4\project\backend

python rebuild_rag.py
```

This re-embeds all calls and agents for all clients using Ollama and writes the vectors to `call_embeddings` and `agent_embeddings` in PostgreSQL.

> Ollama must be running before executing this script.

---

## 8. Demo Accounts

After seeding the database, the following accounts are available:

| Email | Password | Role | Client |
|---|---|---|---|
| admin@heya.au | heya_admin_2026 | heya_admin | All clients |
| admin@artel.com | artel_2026 | client | client_heya_001 (Artel Apartments) |
| admin@mvaallegal.com | mvaa_2026 | client | client_heya_002 (MVAA Legal) |

---

## 9. Project Directory Structure

```
D:\rmit\semester_4\project\
├── backend\
│   ├── main.py              # FastAPI app, all endpoints
│   ├── database.py          # SQLAlchemy models
│   ├── auth.py              # JWT utilities
│   ├── auth_router.py       # /auth/login endpoint
│   ├── rag.py               # RAG query engine
│   ├── agent.py             # ReAct agent engine
│   ├── agent_router.py      # /agent/* endpoints
│   ├── admin_router.py      # /admin/* endpoints
│   ├── pipeline.py          # pyannote + librosa pipeline
│   ├── ingest_dataset.py    # Dataset ingestion (phase 1 + 2)
│   ├── emotion_processor.py # emotion2vec post-processing
│   ├── rebuild_rag.py       # Offline RAG vector store rebuild
│   └── .env                 # Environment variables (not in git)
│
├── frontend\
│   ├── src\
│   │   ├── main.jsx         # Entry point, routes, ProtectedRoute
│   │   ├── App.css          # Shared stylesheet (all pages)
│   │   ├── index.css        # CSS variables, dark/light themes
│   │   ├── context\         # Auth, Filter, Theme contexts
│   │   ├── hooks\           # useClientData.js
│   │   ├── api\             # apiClient.js (axios)
│   │   └── pages\           # All page components
│   ├── package.json
│   └── vite.config.js
│
├── dataset\                 # Raw audio recordings
├── pipeline_output\         # Diarization cache and feature files
├── docs\                    # This documentation
└── tests\
```

---

## 10. Common Issues and Fixes

### UnicodeEncodeError on backend startup

**Symptom:** `UnicodeEncodeError: 'charmap' codec can't encode character`  
**Fix:** Set `$env:PYTHONIOENCODING = "utf-8"` before starting uvicorn.

---

### bcrypt password verification fails

**Symptom:** All logins return 401 even with correct credentials.  
**Cause:** passlib incompatibility with bcrypt 4.x.  
**Fix:** Ensure `auth.py` uses `bcrypt` directly, not `passlib.context.CryptContext`.

---

### JWT `name` field is null in frontend

**Symptom:** User display name shows as blank or undefined.  
**Fix:** Sign out and sign back in after a backend restart. The token payload is refreshed on new login.

---

### pgvector extension not found

**Symptom:** `ERROR: type "vector" does not exist`  
**Fix:** `CREATE EXTENSION IF NOT EXISTS vector;` in the `voice_ai` database as a superuser.

---

### Ollama not running — RAG queries fail

**Symptom:** `/query` or `/agent/analyze` returns 500 with a connection error.  
**Fix:** Start Ollama (`ollama serve`) before starting the backend.

---

### Database connection refused on port 5432

**Symptom:** `connection refused` on localhost:5432  
**Fix:** Heya uses port **5435**. Verify `postgresql.conf` and the `DATABASE_URL` in `.env`.

---

## 11. Frequently Used Commands Reference

```powershell
# Start everything (3 terminals)

# Terminal 1 — Backend
$env:PYTHONIOENCODING = "utf-8"
conda activate heya_v2
cd D:\rmit\semester_4\project\backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2 — Frontend
cd D:\rmit\semester_4\project\frontend
npm run dev

# Terminal 3 — Ollama (if running RAG)
ollama serve

# Rebuild RAG vector store
cd D:\rmit\semester_4\project\backend
conda activate heya_v2
python rebuild_rag.py

# Run emotion processor
$env:PYTHONIOENCODING = "utf-8"
conda activate heya_v2
cd D:\rmit\semester_4\project\backend
python emotion_processor.py --client client_heya_001
python emotion_processor.py --client client_heya_002
```

---

*Setup guide version 2026.06 | Heya AI Platform*
