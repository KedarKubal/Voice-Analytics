"""
main.py  —  Heya AI Voice Analytics API
FastAPI backend

Run:
    python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

Endpoints:
    GET  /                         health check
    GET  /health/db                database connection check
    GET  /insights/{client_id}     fetch all audio insights for a client
    GET  /stats/{client_id}        dashboard KPIs from calls table
    GET  /call/{call_id}           call summary + transcript for drawer
    POST /query                    natural language query (RAG)
    POST /embed/{client_id}        build/refresh vector store for a client
    POST /process-call             run pipeline on an audio file
    POST /webhook/retell           Retell webhook — auto-ingest on call end
    GET  /health/queue             processing queue status
"""

import os
import hmac
import hashlib
import json
import time
import threading
import uuid
import subprocess
import sys
import shutil
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Header, Depends, Query, Request, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, text
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

from database import (
    test_connection, create_tables,
    save_audio_insights, save_utterances, save_recording,
    get_audio_insights_by_client,
    get_db, get_app_db, Call, AudioInsight, RAGQueryHistory, TranscriptUtterance, Recording,
)
from auth import CurrentUser, get_current_user
import auth_router

app = FastAPI(
    title       = "Heya AI — Voice Analytics API",
    version     = "2.0.0",
    description = "Audio intelligence pipeline + RAG conversational interface",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router.router)
import alert_router
app.include_router(alert_router.router)
import export_router
app.include_router(export_router.router)
import admin_router
app.include_router(admin_router.router)
import agent_router
app.include_router(agent_router.router)


# ═══════════════════════════════════════════════════════════════════════════════
# FOLDER WATCHER  —  drop a call_xxx/ folder into either dataset directory
#                    to trigger automatic ingestion + pipeline
# ═══════════════════════════════════════════════════════════════════════════════
_DATASET_WATCH = [
    (
        Path(r"D:\rmit\semester_4\project\dataset\artel_apartments\recordings"),
        {"client_id": "client_heya_001", "client_name": "Artel Apartments", "folder_name": "artel_apartments"},
    ),
    (
        Path(r"D:\rmit\semester_4\project\dataset\mvaa_legal\recordings"),
        {"client_id": "client_heya_002", "client_name": "MVAA Legal", "folder_name": "mvaa_legal"},
    ),
]
_seen_call_folders: set = set()


def _seed_seen_folders() -> None:
    """Snapshot all call folders already on disk at startup so they are never re-processed."""
    for base_path, _ in _DATASET_WATCH:
        if not base_path.exists():
            continue
        for d in base_path.iterdir():
            if d.is_dir() and d.name.startswith("call_"):
                _seen_call_folders.add(str(d))


def _process_new_call_folder(folder: Path, client_cfg: dict) -> None:
    from ingest_dataset import ensure_client_exists, ingest_metadata, ingest_transcript, ingest_recording_path

    print(f"[watcher] 🎙  New call folder: {folder.name}  ({client_cfg['client_name']})")

    # Phase 1 — metadata + transcript (pure Python, no GPU)
    ensure_client_exists(client_cfg)
    call_data = ingest_metadata(folder, client_cfg)
    if call_data is None:
        print(f"[watcher] ✗ Phase 1 failed — metadata.json missing or invalid")
        return

    call_id = call_data.get("call_id")
    ingest_transcript(call_id, folder)
    ingest_recording_path(call_id, folder)
    print(f"[watcher] ✅ Phase 1 done — call_id: {call_id}")

    # Phase 2 — audio pipeline (subprocess, non-blocking)
    audio_path = folder / "audio.wav"
    if not audio_path.exists():
        print(f"[watcher] ⚠  No audio.wav found — skipping Phase 2")
        return

    script = Path(__file__).parent / "run_single_pipeline.py"
    subprocess.Popen(
        [
            sys.executable,
            str(script),
            "--call-id", call_id,
            "--audio",   str(audio_path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    print(f"[watcher] ⚙️  Pipeline launched — watch the dashboard for {call_id}")


def _dataset_folder_watcher() -> None:
    _seed_seen_folders()
    print(f"[watcher] 📂 Watching dataset folders for new calls:")
    for base_path, cfg in _DATASET_WATCH:
        print(f"[watcher]    {base_path}  →  {cfg['client_name']}")

    while True:
        try:
            for base_path, client_cfg in _DATASET_WATCH:
                if not base_path.exists():
                    continue
                for d in base_path.iterdir():
                    if not d.is_dir() or not d.name.startswith("call_"):
                        continue
                    if str(d) in _seen_call_folders:
                        continue
                    if not (d / "metadata.json").exists():
                        continue  # folder still being copied — wait for metadata.json
                    _seen_call_folders.add(str(d))
                    try:
                        _process_new_call_folder(d, client_cfg)
                    except Exception as e:
                        print(f"[watcher] ✗ Error on {d.name}: {e}")
        except Exception as e:
            print(f"[watcher] ✗ Poll error: {e}")
        time.sleep(3)


# ═══════════════════════════════════════════════════════════════════════════════
# STARTUP
# ═══════════════════════════════════════════════════════════════════════════════
@app.on_event("startup")
def startup():
    create_tables()
    print("✅ API started — tables ready")
    try:
        from rag import check_ollama_health
        if not check_ollama_health():
            print(
                "WARNING: Ollama not running — RAG embeddings will fail.\n"
                "Start Ollama before using /rag endpoints:\n"
                "  C:\\Users\\Bhanu\\AppData\\Local\\Programs\\Ollama\\ollama.exe serve"
            )
        else:
            print("✅ Ollama reachable — RAG embeddings ready")
    except Exception as e:
        print(f"WARNING: Could not check Ollama health: {e}")

    threading.Thread(target=_dataset_folder_watcher, daemon=True).start()


# ═══════════════════════════════════════════════════════════════════════════════
# RATE LIMITING  (in-memory, per IP — production would use Redis)
# ═══════════════════════════════════════════════════════════════════════════════
_rate_store: dict[str, list[float]] = defaultdict(list)
_rate_lock  = threading.Lock()

def _check_rate_limit(key: str, limit: int, window: int = 60) -> None:
    """Raise 429 if the key has exceeded `limit` requests in `window` seconds."""
    now = time.time()
    with _rate_lock:
        timestamps = _rate_store[key]
        _rate_store[key] = [t for t in timestamps if now - t < window]
        if len(_rate_store[key]) >= limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded — max {limit} requests per {window}s. Try again shortly.",
            )
        _rate_store[key].append(now)


# ═══════════════════════════════════════════════════════════════════════════════
# SECURITY HELPER  (JWT-enforced tenant scoping)
# ═══════════════════════════════════════════════════════════════════════════════
def _require_client_access(user: CurrentUser, client_id: str) -> None:
    """
    Enforce that the authenticated user may access `client_id`.
    - heya_admin: can access any client
    - client role:  can ONLY access their own client_id (from JWT)
    Raises 403 if mismatch.
    """
    if user.is_admin:
        return
    if user.client_id != client_id:
        raise HTTPException(
            status_code=403,
            detail="Access denied — your token does not grant access to this client's data.",
        )


# ═══════════════════════════════════════════════════════════════════════════════
# REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════════════════════
class ProcessCallRequest(BaseModel):
    call_id:    str
    audio_path: str
    client_id:  str


class ProcessCallResponse(BaseModel):
    call_id:           str
    status:            str
    engagement_score:  float | None = None
    silence_ratio:     float | None = None
    total_turns:       int   | None = None
    conversation_flow: str   | None = None
    processing_sec:    float | None = None
    message:           str


class QueryRequest(BaseModel):
    question:  str
    client_id: str
    history:   list[dict] = []   # last N user/assistant turns for multi-turn


class QueryResponse(BaseModel):
    question:   str
    answer:     str
    route:      str
    sources:    list[str]
    confidence: str = "HIGH"


# ═══════════════════════════════════════════════════════════════════════════════
# BACKGROUND EMOTION PROCESSING
# ═══════════════════════════════════════════════════════════════════════════════
def _classify_topic_background(call_id: str) -> None:
    """Classify the topic of a single call. Fast — pure Python, no ML model."""
    try:
        from topic_classifier import classify_call
        classify_call(call_id)
    except Exception as e:
        print(f"[topic] {call_id}: failed — {e}")


def _run_emotion_background(call_id: str) -> None:
    """
    Attempt per-utterance emotion classification for `call_id`.

    Runs in a FastAPI BackgroundTask — safe to fail.
    Skips silently if funasr is not installed (heya_audio env without GPU deps).
    """
    try:
        from emotion_processor import process_call_emotions
        n = process_call_emotions(call_id)
        print(f"[emotion] {call_id}: {n} utterances labelled")
    except ImportError:
        pass  # funasr not installed in this environment — skip
    except Exception as e:
        print(f"[emotion] {call_id}: failed — {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/")
def home():
    return {
        "service":   "Heya AI Voice Analytics",
        "status":    "running",
        "version":   "2.0.0",
        "endpoints": [
            "GET  /insights/{client_id}",
            "GET  /stats/{client_id}",
            "GET  /call/{call_id}",
            "POST /query",
            "POST /agent/analyze/{client_id}",
            "GET  /agent/tools",
            "POST /embed/{client_id}",
            "POST /process-call",
            "POST /webhook/retell",
            "GET  /health/queue",
        ]
    }


@app.get("/health/db")
def health_db():
    ok = test_connection()
    if not ok:
        raise HTTPException(status_code=503, detail="Database unreachable")
    return {"database": "connected"}


# NOTE: _require_client_access() must be called manually — it is not a FastAPI Depends()
# If you add a new endpoint, you must call _require_client_access() explicitly.
@app.get("/insights/{client_id}")
def get_insights(
    client_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    _require_client_access(user, client_id)
    insights = get_audio_insights_by_client(client_id)
    return {
        "client_id":   client_id,
        "total_calls": len(insights),
        "insights":    insights,
    }


# NOTE: _require_client_access() must be called manually — it is not a FastAPI Depends()
# If you add a new endpoint, you must call _require_client_access() explicitly.
@app.get("/stats/{client_id}")
def get_stats(
    client_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    _require_client_access(user, client_id)

    # get_app_db sets app.client_id — RLS policy filters rows at the DB layer
    rls_id = "heya_admin" if user.is_admin else client_id
    with get_app_db(rls_id) as db:
        total_calls = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id)
            .scalar()
        )
        successful = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id, Call.call_successful == True)
            .scalar()
        )
        sentiment_counts = dict(
            db.query(Call.user_sentiment, func.count(Call.id))
            .filter(Call.client_id == client_id)
            .group_by(Call.user_sentiment)
            .all()
        )
        avg_duration = (
            db.query(func.avg(Call.duration_ms))
            .filter(Call.client_id == client_id)
            .scalar()
        )
        audio_processed = (
            db.query(func.count(AudioInsight.id))
            .join(Call, AudioInsight.call_id == Call.id)
            .filter(Call.client_id == client_id)
            .scalar()
        )
        pending_audio = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id, Call.processing_status == "pending_audio")
            .scalar()
        )

        # FEATURE 1 — silence vs success correlation (SQL-computed, not Python loops)
        silence_corr_rows = db.execute(text("""
            SELECT
                ROUND(100.0 * SUM(CASE WHEN ai.silence_ratio > 0.4 AND c.call_successful = true  THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN ai.silence_ratio > 0.4 THEN 1 ELSE 0 END), 0), 1) AS high_silence_success_rate,
                ROUND(100.0 * SUM(CASE WHEN ai.silence_ratio <= 0.4 AND c.call_successful = true THEN 1 ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN ai.silence_ratio <= 0.4 THEN 1 ELSE 0 END), 0), 1) AS low_silence_success_rate,
                SUM(CASE WHEN ai.silence_ratio > 0.4  THEN 1 ELSE 0 END) AS high_count,
                SUM(CASE WHEN ai.silence_ratio <= 0.4 THEN 1 ELSE 0 END) AS low_count
            FROM audio_insights ai
            JOIN calls c ON c.id = ai.call_id
            WHERE c.client_id = :cid
              AND ai.silence_ratio IS NOT NULL
              AND c.call_successful IS NOT NULL
        """), {"cid": client_id}).fetchone()

        high_sr = float(silence_corr_rows.high_silence_success_rate or 0) if silence_corr_rows else 0.0
        low_sr  = float(silence_corr_rows.low_silence_success_rate  or 0) if silence_corr_rows else 0.0
        if high_sr > 0 and low_sr > 0:
            ratio = round(low_sr / high_sr, 2) if high_sr else 0
            if ratio >= 1:
                insight_text = f"Calls with low silence have {ratio}x higher success rates than high-silence calls."
            else:
                ratio = round(high_sr / low_sr, 2) if low_sr else 0
                insight_text = f"Calls with high silence have {ratio}x higher success rates (unusual — may reflect patient listening)."
        else:
            insight_text = "Insufficient data to compute silence-success correlation."

        silence_success_correlation = {
            "high_silence_success_rate": high_sr,
            "low_silence_success_rate":  low_sr,
            "insight": insight_text,
        }

        # FEATURE 2 — time-of-day analysis (uses start_timstamp typo — matches DB column)
        try:
            hour_rows = db.execute(text("""
                SELECT
                    EXTRACT(HOUR FROM to_timestamp(start_timstamp::float8 / 1000)) AS hour,
                    COUNT(*) AS count,
                    ROUND(AVG(ai.engagement_score)::numeric, 1) AS avg_engagement
                FROM calls c
                LEFT JOIN audio_insights ai ON ai.call_id = c.id
                WHERE c.client_id = :cid
                  AND c.start_timstamp IS NOT NULL
                  AND c.start_timstamp > 0
                GROUP BY hour
                ORDER BY hour ASC
            """), {"cid": client_id}).fetchall()
            calls_by_hour = [
                {
                    "hour": int(r.hour),
                    "count": int(r.count),
                    "avg_engagement": float(r.avg_engagement or 0),
                }
                for r in hour_rows
            ]
        except Exception:
            calls_by_hour = []

        # FEATURE 3 — topic breakdown (only if topic data exists)
        try:
            topic_rows = db.execute(text("""
                SELECT topic, COUNT(*) AS count
                FROM calls
                WHERE client_id = :cid AND topic IS NOT NULL
                GROUP BY topic
                ORDER BY count DESC
                LIMIT 10
            """), {"cid": client_id}).fetchall()
            topic_total = sum(r.count for r in topic_rows) or 0
            if topic_total > 0:
                top_topics = [
                    {
                        "topic": r.topic,
                        "count": int(r.count),
                        "pct": round(int(r.count) / topic_total * 100, 1),
                    }
                    for r in topic_rows
                ]
            else:
                # TODO: topic column is empty — run topic_classifier.py first
                top_topics = []
        except Exception:
            top_topics = []

        # FEATURE 4 — engagement benchmark label (62.0 = Voice AI industry baseline)
        avg_eng_row = db.execute(text("""
            SELECT ROUND(AVG(ai.engagement_score)::numeric, 1) AS avg_eng
            FROM audio_insights ai
            JOIN calls c ON c.id = ai.call_id
            WHERE c.client_id = :cid
        """), {"cid": client_id}).scalar()
        client_eng_score = float(avg_eng_row or 0)
        BENCHMARK_SCORE  = 62.0
        eng_delta        = round(client_eng_score - BENCHMARK_SCORE, 1)
        if eng_delta >= 0:
            eng_label = f"{abs(eng_delta)} points above benchmark"
        else:
            eng_label = f"{abs(eng_delta)} points below benchmark"
        engagement_benchmark = {
            "client_score":    client_eng_score,
            "benchmark_score": BENCHMARK_SCORE,
            "benchmark_label": "Voice AI industry baseline",
            "delta":           eng_delta,
            "label":           eng_label,
        }

    return {
        "client_id":                    client_id,
        "total_calls":                  total_calls,
        "successful_calls":             successful,
        "success_rate":                 round(successful / (total_calls or 1) * 100, 1),
        "sentiment":                    sentiment_counts,
        "avg_duration_sec":             round(float(avg_duration or 0) / 1000, 1),
        "audio_processed":              audio_processed,
        "pending_audio":                pending_audio,
        "silence_success_correlation":  silence_success_correlation,
        "calls_by_hour":                calls_by_hour,
        "top_topics":                   top_topics,
        "engagement_benchmark":         engagement_benchmark,
    }


@app.get("/call/{call_id}")
def get_call_detail(
    call_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    rls_id = "heya_admin" if user.is_admin else user.client_id
    with get_app_db(rls_id) as db:
        query = db.query(Call).filter(Call.id == call_id)
        if not user.is_admin:
            query = query.filter(Call.client_id == user.client_id)
        call = query.first()

        if not call:
            raise HTTPException(status_code=404, detail="Call not found")

        utterances = (
            db.query(TranscriptUtterance)
            .filter(TranscriptUtterance.call_id == call_id)
            .order_by(TranscriptUtterance.utterness_index)
            .all()
        )

        return {
            "call_id":      call_id,
            "call_summary": call.call_summary,
            "transcript": [
                {
                    "index":         u.utterness_index,
                    "role":          u.role,
                    "content":       u.content,
                    "emotion":       u.emotion,
                    "emotion_score": float(u.emotion_score) if u.emotion_score else None,
                }
                for u in utterances
            ],
        }


@app.get("/audio/{call_id}")
def get_call_audio(
    call_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Stream the WAV audio file for a specific call."""
    from fastapi.responses import FileResponse
    import os

    with get_db() as db:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
        if not user.is_admin and call.client_id != user.client_id:
            raise HTTPException(status_code=403, detail="Access denied")

        rec = db.query(Recording).filter(Recording.call_id == call_id).first()
        audio_path = rec.audio_path if rec else None

    if not audio_path:
        raise HTTPException(status_code=404, detail="No audio recorded for this call")

    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail="Audio file not found on disk")

    ext        = os.path.splitext(audio_path)[1].lower()
    media_type = "audio/wav" if ext == ".wav" else "audio/mpeg" if ext == ".mp3" else "audio/octet-stream"

    return FileResponse(
        path       = audio_path,
        media_type = media_type,
        filename   = f"{call_id}{ext}",
    )


@app.post("/query", response_model=QueryResponse)
def query_endpoint(
    req: QueryRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    _require_client_access(user, req.client_id)

    # Groq free tier: 30 req/min — enforce per user
    _check_rate_limit(f"query:{user.user_id}", limit=25, window=60)

    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    t0 = time.time()

    try:
        from rag import query
        result = query(req.question, req.client_id, history=req.history)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"RAG error: {e}")

    response_ms = int((time.time() - t0) * 1000)

    try:
        with get_app_db(req.client_id) as db:
            from datetime import datetime
            db.add(RAGQueryHistory(
                client_id        = req.client_id,
                user_id          = user.user_id,
                query            = req.question,
                response         = result["answer"],
                sources          = result["sources"],
                query_type       = result["route"],
                response_time_ms = response_ms,
                created_at       = datetime.utcnow(),
            ))
    except Exception:
        pass

    return QueryResponse(
        question = result["question"],
        answer   = result["answer"],
        route    = result["route"],
        sources  = result["sources"],
        confidence = result.get("confidence", "HIGH"),
    )


@app.post("/embed/{client_id}")
def embed_client_data(
    client_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    _require_client_access(user, client_id)

    try:
        from rag import build_vector_store
        build_vector_store(client_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding error: {e}")

    return {
        "status":    "success",
        "client_id": client_id,
        "message":   "Vector store built — RAG system is ready for queries",
    }


@app.get("/search")
def search_transcripts(
    q:     str,
    limit: int = 20,
    user:  CurrentUser = Depends(get_current_user),
):
    """
    Full-text search across all transcript utterances and call summaries.

    Uses PostgreSQL GIN indexes + plainto_tsquery — handles stemming,
    stop words, and multi-word phrases automatically.

    Returns up to `limit` calls ranked by relevance, each with:
      · match_count  — how many utterances contained the query
      · snippets     — up to 2 excerpts with <mark>…</mark> highlights
      · call metadata (direction, sentiment, engagement, date)

    Example:
        GET /search?q=cancellation
        GET /search?q=appointment+booking&limit=10
    """
    q = q.strip()
    if len(q) < 2:
        raise HTTPException(400, "Query must be at least 2 characters")
    if len(q) > 200:
        raise HTTPException(400, "Query too long")

    limit = max(1, min(limit, 50))
    rls_id = "heya_admin" if user.is_admin else user.client_id

    with get_app_db(rls_id) as db:

        # ── 1. Find matching call IDs from transcript utterances ──────────────
        utterance_hits = db.execute(text("""
            SELECT
                tu.call_id,
                COUNT(*)  AS match_count,
                MAX(ts_rank(
                    to_tsvector('english', coalesce(tu.content, '')),
                    plainto_tsquery('english', :q)
                )) AS rank
            FROM transcript_utterances tu
            JOIN calls c ON c.id = tu.call_id
            WHERE to_tsvector('english', coalesce(tu.content, ''))
                  @@ plainto_tsquery('english', :q)
            GROUP BY tu.call_id
            ORDER BY rank DESC
            LIMIT :lim
        """), {"q": q, "lim": limit}).fetchall()

        # ── 2. Also match on call summaries (lower weight) ───────────────────
        summary_hits = db.execute(text("""
            SELECT id AS call_id, 0.1::float AS rank
            FROM calls
            WHERE to_tsvector('english', coalesce(call_summary, '') || ' ' || coalesce(transcript, ''))
                  @@ plainto_tsquery('english', :q)
            LIMIT :lim
        """), {"q": q, "lim": limit}).fetchall()

        # Merge by call_id, utterance hits take priority
        seen   = {r.call_id: {"match_count": r.match_count, "rank": float(r.rank)}
                  for r in utterance_hits}
        for r in summary_hits:
            if r.call_id not in seen:
                seen[r.call_id] = {"match_count": 0, "rank": float(r.rank)}

        if not seen:
            return {"query": q, "total": 0, "results": []}

        # ── 3. Fetch snippets + metadata for each matching call ──────────────
        results = []
        for call_id, meta in sorted(seen.items(),
                                    key=lambda x: x[1]["rank"], reverse=True):

            # Top 2 highlighted snippets from utterances
            snippets_raw = db.execute(text("""
                SELECT ts_headline(
                    'english', content,
                    plainto_tsquery('english', :q),
                    'MaxWords=15, MinWords=5, MaxFragments=1,
                     StartSel=<mark>, StopSel=</mark>'
                ) AS snippet
                FROM transcript_utterances
                WHERE call_id = :cid
                  AND to_tsvector('english', coalesce(content, ''))
                      @@ plainto_tsquery('english', :q)
                ORDER BY ts_rank(
                    to_tsvector('english', coalesce(content, '')),
                    plainto_tsquery('english', :q)
                ) DESC
                LIMIT 2
            """), {"q": q, "cid": call_id}).fetchall()

            snippets = [r.snippet for r in snippets_raw]

            # If no utterance snippets, highlight the call summary instead
            if not snippets:
                summary_snip = db.execute(text("""
                    SELECT ts_headline(
                        'english', coalesce(call_summary, ''),
                        plainto_tsquery('english', :q),
                        'MaxWords=20, MinWords=6, MaxFragments=1,
                         StartSel=<mark>, StopSel=</mark>'
                    ) AS snippet
                    FROM calls WHERE id = :cid
                """), {"q": q, "cid": call_id}).scalar()
                if summary_snip:
                    snippets = [summary_snip]

            # Call + insight metadata
            call = db.query(Call).filter(Call.id == call_id).first()
            if not call:
                continue

            insight = db.query(AudioInsight).filter(
                AudioInsight.call_id == call_id
            ).first()

            results.append({
                "call_id":         call_id,
                "match_count":     meta["match_count"],
                "rank":            round(meta["rank"], 4),
                "snippets":        snippets,
                "direction":       call.direction,
                "user_sentiment":  call.user_sentiment,
                "call_successful": call.call_successful,
                "start_timestamp": call.start_timstamp,
                "duration_ms":     call.duration_ms,
                "call_summary":    (call.call_summary or "")[:300] if call.call_summary else None,
                "engagement_score": float(insight.engagement_score)
                                    if insight and insight.engagement_score else None,
                "conversation_flow": insight.conversation_flow if insight else None,
            })

    return {"query": q, "total": len(results), "results": results}


@app.get("/feed/{client_id}")
def get_call_feed(
    client_id: str,
    limit:     int = 30,
    user:      CurrentUser = Depends(get_current_user),
):
    """
    Live call feed — most recent calls for a client, newest first.
    Includes processing status, quality score, and emotion.
    Designed to be polled every 5 seconds by the frontend.
    """
    _require_client_access(user, client_id)
    limit  = max(1, min(limit, 50))
    rls_id = "heya_admin" if user.is_admin else client_id

    with get_app_db(rls_id) as db:
        rows = db.execute(text("""
            SELECT
                c.id                  AS call_id,
                c.direction,
                c.start_timstamp      AS start_timestamp,
                c.duration_ms,
                c.processing_status,
                c.call_successful,
                c.user_sentiment,
                c.call_status,
                ai.engagement_score,
                ai.conversation_flow,
                ai.dominant_emotion,
                ai.sentiment_trajectory
            FROM calls c
            LEFT JOIN audio_insights ai ON ai.call_id = c.id
            WHERE c.client_id = :cid
            ORDER BY c.start_timstamp DESC NULLS LAST, c.id DESC
            LIMIT :lim
        """), {"cid": client_id, "lim": limit}).fetchall()

    from quality import compute_quality_score, quality_grade

    result = []
    for r in rows:
        qs = qg = None
        if r.engagement_score is not None:
            qs = compute_quality_score(
                float(r.engagement_score), r.conversation_flow,
                r.call_successful, r.dominant_emotion,
            )
            qg = quality_grade(qs)
        result.append({
            "call_id":            r.call_id,
            "direction":          r.direction,
            "start_timestamp":    r.start_timestamp,
            "duration_ms":        r.duration_ms,
            "processing_status":  r.processing_status,
            "call_successful":    r.call_successful,
            "user_sentiment":     r.user_sentiment,
            "engagement_score":   float(r.engagement_score) if r.engagement_score else None,
            "conversation_flow":  r.conversation_flow,
            "dominant_emotion":   r.dominant_emotion,
            "sentiment_trajectory": r.sentiment_trajectory,
            "quality_score":      qs,
            "quality_grade":      qg,
        })

    return {"client_id": client_id, "count": len(result), "calls": result}


@app.get("/recommendations/{client_id}")
def get_recommendations(
    client_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Aggregate portfolio-level recommendations — used by heya_admin drill-down."""
    _require_client_access(user, client_id)
    from recommendations import generate_recommendations
    recs = generate_recommendations(client_id)
    return {
        "client_id":       client_id,
        "count":           len(recs),
        "recommendations": recs,
    }


@app.get("/client-alerts/{client_id}")
def get_client_alerts(
    client_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """Call-level alert flags — early disconnects, poor engagement, flagged language, etc."""
    _require_client_access(user, client_id)
    from recommendations import generate_client_alerts
    alerts = generate_client_alerts(client_id)
    return {
        "client_id": client_id,
        "count":     len(alerts),
        "alerts":    alerts,
    }


@app.get("/emotions/{client_id}")
def get_emotion_stats(
    client_id: str,
    user: CurrentUser = Depends(get_current_user),
):
    """
    Emotion analytics for a client:
      - utterance_distribution: emotion counts across all customer utterances
      - call_distribution:      how many calls had each dominant emotion
      - weekly_trend:           dominant emotion per call grouped by week (last 8 weeks)
    """
    _require_client_access(user, client_id)
    rls_id = "heya_admin" if user.is_admin else client_id

    with get_app_db(rls_id) as db:
        utt_dist = db.execute(text("""
            SELECT tu.emotion, COUNT(*) AS count
            FROM transcript_utterances tu
            JOIN calls c ON c.id = tu.call_id
            WHERE c.client_id = :cid
              AND tu.role = 'user'
              AND tu.emotion IS NOT NULL
              AND tu.emotion != 'unknown'
            GROUP BY tu.emotion
            ORDER BY count DESC
        """), {"cid": client_id}).fetchall()

        call_dist = db.execute(text("""
            SELECT ai.dominant_emotion AS emotion, COUNT(*) AS count
            FROM audio_insights ai
            JOIN calls c ON c.id = ai.call_id
            WHERE c.client_id = :cid
              AND ai.dominant_emotion IS NOT NULL
              AND ai.dominant_emotion != 'unknown'
            GROUP BY ai.dominant_emotion
            ORDER BY count DESC
        """), {"cid": client_id}).fetchall()

        trend_rows = db.execute(text("""
            SELECT
                TO_CHAR(DATE_TRUNC('week', TO_TIMESTAMP(c.start_timstamp / 1000.0)), 'Mon DD') AS week,
                DATE_TRUNC('week', TO_TIMESTAMP(c.start_timstamp / 1000.0))                    AS week_sort,
                ai.dominant_emotion                                                              AS emotion,
                COUNT(*)                                                                         AS count
            FROM audio_insights ai
            JOIN calls c ON c.id = ai.call_id
            WHERE c.client_id = :cid
              AND ai.dominant_emotion IS NOT NULL
              AND ai.dominant_emotion != 'unknown'
              AND c.start_timstamp IS NOT NULL
              AND TO_TIMESTAMP(c.start_timstamp / 1000.0) >= NOW() - INTERVAL '8 weeks'
            GROUP BY DATE_TRUNC('week', TO_TIMESTAMP(c.start_timstamp / 1000.0)), ai.dominant_emotion
            ORDER BY week_sort ASC
        """), {"cid": client_id}).fetchall()

    trend_map: dict = {}
    for row in trend_rows:
        w = row.week
        if w not in trend_map:
            trend_map[w] = {"week": w}
        trend_map[w][row.emotion] = int(row.count)

    return {
        "client_id":              client_id,
        "utterance_distribution": [{"emotion": r.emotion, "count": int(r.count)} for r in utt_dist],
        "call_distribution":      [{"emotion": r.emotion, "count": int(r.count)} for r in call_dist],
        "weekly_trend":           list(trend_map.values()),
    }


@app.get("/topics/{client_id}")
def get_topic_stats(
    client_id: str,
    user:      CurrentUser = Depends(get_current_user),
):
    """Topic distribution for a client — how many calls per detected topic."""
    _require_client_access(user, client_id)
    rls_id = "heya_admin" if user.is_admin else client_id

    try:
        with get_app_db(rls_id) as db:
            rows = db.execute(text("""
                SELECT topic, COUNT(*) AS count
                FROM calls
                WHERE client_id = :cid
                  AND topic IS NOT NULL
                GROUP BY topic
                ORDER BY count DESC
            """), {"cid": client_id}).fetchall()

            total = db.execute(text("""
                SELECT COUNT(*) FROM calls
                WHERE client_id = :cid AND topic IS NOT NULL
            """), {"cid": client_id}).scalar() or 0

        distribution = [
            {
                "topic": r.topic,
                "count": int(r.count),
                "pct":   round(int(r.count) / total * 100, 1) if total else 0,
            }
            for r in rows
        ]
    except Exception:
        # Column may not exist yet — return empty until migration is run
        distribution = []
        total = 0

    return {
        "client_id":    client_id,
        "total":        total,
        "distribution": distribution,
    }


@app.post("/process-call", response_model=ProcessCallResponse)
def process_call_endpoint(
    req:              ProcessCallRequest,
    background_tasks: BackgroundTasks,
    user:             CurrentUser = Depends(get_current_user),
):
    _require_client_access(user, req.client_id)

    audio_path = Path(req.audio_path)
    if not audio_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {req.audio_path}")

    try:
        from pipeline import process_call, load_pipeline, SAMPLE_RATE
        pipe = load_pipeline()
        turn_df, summary = process_call(str(audio_path), pipe, SAMPLE_RATE)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")

    if summary.get("status") == "failed":
        raise HTTPException(status_code=422, detail=summary.get("reason"))

    save_audio_insights(req.call_id, summary)
    save_utterances(req.call_id, turn_df)
    save_recording(req.call_id, str(audio_path))

    # Kick off emotion + topic classification in the background
    background_tasks.add_task(_run_emotion_background,   req.call_id)
    background_tasks.add_task(_classify_topic_background, req.call_id)

    return ProcessCallResponse(
        call_id           = req.call_id,
        status            = "success",
        engagement_score  = summary.get("engagement_score"),
        silence_ratio     = summary.get("silence_ratio"),
        total_turns       = summary.get("total_turns"),
        conversation_flow = summary.get("conversation_flow"),
        processing_sec    = summary.get("processing_sec"),
        message           = "Pipeline complete — insights saved to database",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# DEMO CALL UPLOAD  —  upload a WAV and push it through the full pipeline
# ═══════════════════════════════════════════════════════════════════════════════
_PIPELINE_PYTHON = sys.executable
_UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", r"D:\rmit\semester_4\project\uploads"))


@app.post("/upload-call")
async def upload_call(
    file:      UploadFile = File(...),
    client_id: str        = Form(...),
    user:      CurrentUser = Depends(get_current_user),
):
    """
    Upload a WAV file and run the full audio pipeline on it.

    The call record is created immediately (status: processing).
    The pipeline runs in the background via heya_pipeline env subprocess.
    Poll GET /feed/{client_id} to track progress — status flips to 'completed'
    when the analytics are ready.
    """
    _require_client_access(user, client_id)

    if not file.filename.lower().endswith((".wav", ".mp3", ".flac", ".m4a")):
        raise HTTPException(status_code=400, detail="Only audio files are accepted (.wav, .mp3, .flac, .m4a)")

    # Generate a unique call_id
    ts       = int(time.time() * 1000)
    short_id = uuid.uuid4().hex[:8]
    call_id  = f"call_demo_{ts}_{short_id}"

    # Save uploaded file
    call_dir   = _UPLOADS_DIR / call_id
    call_dir.mkdir(parents=True, exist_ok=True)
    suffix     = Path(file.filename).suffix.lower()
    audio_path = call_dir / f"audio{suffix}"

    content = await file.read()
    audio_path.write_bytes(content)

    # Rough duration estimate from WAV file size (44-byte header, 16kHz mono 16-bit = 32KB/s)
    duration_ms = max(0, int((len(content) - 44) / 32000 * 1000)) if suffix == ".wav" else 0

    now_ms = int(time.time() * 1000)
    with get_db() as db:
        db.add(Call(
            id                = call_id,
            client_id         = client_id,
            call_type         = "phone_call",
            call_status       = "ended",
            direction         = "inbound",
            start_timstamp    = now_ms,
            end_timestamp     = now_ms + duration_ms,
            duration_ms       = duration_ms or None,
            processing_status = "processing",
            created_at        = datetime.utcnow(),
        ))

    # Fire pipeline in heya_pipeline env — non-blocking
    script = Path(__file__).parent / "run_single_pipeline.py"
    subprocess.Popen(
        [_PIPELINE_PYTHON, str(script), "--call-id", call_id, "--audio", str(audio_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return {
        "call_id":          call_id,
        "client_id":        client_id,
        "status":           "processing",
        "audio_size_bytes": len(content),
        "message":          "Audio uploaded — pipeline is running. Poll /feed/{client_id} to track progress.",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# RETELL WEBHOOK  —  auto-ingest every call the moment it ends
# ═══════════════════════════════════════════════════════════════════════════════
@app.post("/webhook/retell")
async def retell_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
):
    """
    Retell calls this endpoint when a call ends / analysis completes.
    We verify the HMAC signature, then hand off to a background task so
    the HTTP response is immediate (Retell expects 200 within 3 seconds).

    Configure in Retell dashboard:
        Webhook URL: https://your-domain.com/webhook/retell
        Events:      call_analyzed
    """
    body = await request.body()

    # ── Signature verification ────────────────────────────────────────────────
    retell_api_key = os.getenv("RETELL_API_KEY", "")
    if retell_api_key:
        signature = request.headers.get("x-retell-signature", "")
        expected  = hmac.new(
            retell_api_key.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, signature):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event     = payload.get("event", "")
    call_data = payload.get("data", payload)
    call_id   = call_data.get("call_id", "unknown")

    print(f"\n[webhook] Received event='{event}' call_id='{call_id}'")

    # Process on call_ended (fast: metadata + transcript only)
    # or call_analyzed (richer: includes AI summary + sentiment)
    if event in ("call_ended", "call_analyzed"):
        from webhook_processor import ingest_webhook_call
        from alerts import check_and_send_alerts

        async def _ingest_then_check(data: dict):
            ingest_webhook_call(data)

            # Emotion + topic classification
            _run_emotion_background(data.get("call_id", ""))
            _classify_topic_background(data.get("call_id", ""))

            # Alert checks — new call may breach a threshold
            agent_id = data.get("agent_id", "")
            with get_db() as db:
                from database import Agent
                agent = db.query(Agent).filter(Agent.id == agent_id).first()
                if agent:
                    check_and_send_alerts(agent.client_id)

        background_tasks.add_task(_ingest_then_check, call_data)
        return {"status": "queued", "call_id": call_id, "event": event}

    return {"status": "ignored", "event": event}


# ═══════════════════════════════════════════════════════════════════════════════
# PROCESSING QUEUE STATUS
# ═══════════════════════════════════════════════════════════════════════════════
@app.get("/health/queue")
def queue_status(
    user: CurrentUser = Depends(get_current_user),
):
    """
    Returns how many calls are waiting for audio pipeline processing.
    Admins see all clients; client users see only their own.
    """
    rls_id = "heya_admin" if user.is_admin else user.client_id
    with get_app_db(rls_id) as db:
        base = db.query(
            Call.client_id,
            Call.processing_status,
            func.count(Call.id).label("count"),
        )
        if not user.is_admin:
            base = base.filter(Call.client_id == user.client_id)

        rows = (
            base
            .group_by(Call.client_id, Call.processing_status)
            .all()
        )

    result = {}
    for client_id, status, count in rows:
        if client_id not in result:
            result[client_id] = {}
        result[client_id][status or "unknown"] = count

    return {"queue": result}
