"""
database.py  —  Heya AI Voice Analytics
SQLAlchemy models + session factory + CRUD helpers

Tables covered (matching your SQL schema exactly):
  clients, agents, calls, recordings,
  audio_insights, call_metadata, tool_calls,
  transcript_utterances, transcript_words

Usage:
  from database import get_db, save_audio_insights, save_recording
"""

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, Float, Integer,
    Numeric, String, Text, BIGINT,
    ForeignKey, JSON, create_engine, text,
)
from sqlalchemy import DateTime as Timestamp 
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

import math

def safe_json_float(val, default=0.0):
    """Convert float to JSON-safe value — replaces None/NaN/Inf with default."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default
# ═══════════════════════════════════════════════════════════════════════
# 1.  DATABASE CONNECTION
# ═══════════════════════════════════════════════════════════════════════
# Set this in your .env file or environment:
#   DATABASE_URL=postgresql://user:password@localhost:5432/heya_audio
#
# Never hardcode credentials here.

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5435/voice_ai"
)

# APP_DATABASE_URL uses the limited heya_app role — RLS is enforced on this connection.
# Falls back to DATABASE_URL (superuser) if not set, so local dev keeps working
# before migrate_rls.py has been run.
APP_DATABASE_URL = os.getenv("APP_DATABASE_URL") or DATABASE_URL

# ── Superuser engine (pipeline / ingest / migrations) ────────────────────────
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

# ── App engine (web API — RLS enforced via heya_app role) ────────────────────
app_engine = create_engine(
    APP_DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    echo=False,
)

SessionLocal    = sessionmaker(bind=engine,     autocommit=False, autoflush=False)
AppSessionLocal = sessionmaker(bind=app_engine, autocommit=False, autoflush=False)

# Reset the session variable on every connection checkout so a previous
# request's client context never leaks into the next one.
from sqlalchemy import event as _sa_event

@_sa_event.listens_for(app_engine, "checkout")
def _reset_rls_context(dbapi_conn, _record, _proxy):
    cursor = dbapi_conn.cursor()
    cursor.execute("SET app.client_id = ''")
    cursor.close()


@contextmanager
def get_db():
    """
    Superuser session — bypasses RLS.
    Use for: pipeline, ingest scripts, migrations, seed_users, rag vector build.
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@contextmanager
def get_app_db(client_id: str):
    """
    RLS-enforced session — sets app.client_id before every query.

    The heya_app role policy allows:
      · client_id matching the session variable  → that tenant's rows only
      · 'heya_admin'                             → all rows (admin access)

    Usage:
        with get_app_db(client_id) as db:
            db.query(Call).all()   # only sees that client's calls
    """
    db = AppSessionLocal()
    try:
        db.execute(text("SET LOCAL app.client_id = :cid"), {"cid": client_id})
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ═══════════════════════════════════════════════════════════════════════
# 2.  BASE MODEL
# ═══════════════════════════════════════════════════════════════════════
class Base(DeclarativeBase):
    pass


# ═══════════════════════════════════════════════════════════════════════
# 3.  ORM MODELS  (mirrors your SQL schema exactly)
# ═══════════════════════════════════════════════════════════════════════

class Client(Base):
    """
    Matches: table_clients.sql
    One client = one business using Heya AI (e.g. a dental clinic).
    """
    __tablename__ = "clients"

    id          = Column(String(100), primary_key=True)
    name        = Column(String(255), nullable=False)
    folder_name = Column(String(255), unique=True, nullable=False)
    created_at  = Column(Timestamp)
    updated_at  = Column(Timestamp)

    # relationships (lets you do client.agents, client.calls in Python)
    agents = relationship("Agent", back_populates="client", cascade="all, delete")
    calls  = relationship("Call",  back_populates="client", cascade="all, delete")


class Agent(Base):
    """
    Matches: table_agents.sql
    One agent = one AI voice agent deployed by a client.
    """
    __tablename__ = "agents"

    id           = Column(String(100), primary_key=True)
    client_id    = Column(String(100), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    name         = Column(String(255), nullable=False)
    version      = Column(String(100))
    partner_id   = Column(String(100))
    context_path = Column(Text)
    created_at   = Column(Timestamp)
    updated_at   = Column(Timestamp)

    client = relationship("Client", back_populates="agents")
    calls  = relationship("Call",   back_populates="agent")


class Call(Base):
    """
    Matches: calls.sql
    Central table — one row per phone call.
    NOTE: your SQL has a typo 'start_timstamp' — kept as-is to match your DB.
    """
    __tablename__ = "calls"

    id                = Column(String(100), primary_key=True)
    client_id         = Column(String(100), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    agent_id          = Column(String(100), ForeignKey("agents.id",  ondelete="SET NULL"))
    call_type         = Column(String(100))
    call_status       = Column(String(100))
    direction         = Column(String(100))
    from_number       = Column(String(30))
    to_number         = Column(String(100))
    start_timstamp    = Column(BigInteger)   # typo kept intentionally — matches your SQL
    end_timestamp     = Column(BigInteger)
    duration_ms       = Column(BigInteger)
    transcript        = Column(Text)
    call_summary      = Column(Text)
    user_sentiment    = Column(String(50))
    call_successful   = Column(Boolean)
    processing_status = Column(String(50))
    topic             = Column(String(50))
    topic_confidence  = Column(Numeric(5, 4))
    total_cost        = Column(Numeric(12, 4))
    llm_cost          = Column(Numeric(12, 4))
    stt_cost          = Column(Numeric(12, 4))
    tts_cost          = Column(Numeric(12, 4))
    created_at        = Column(Timestamp, default=datetime.utcnow)

    client      = relationship("Client",  back_populates="calls")
    agent       = relationship("Agent",   back_populates="calls")
    recording   = relationship("Recording",        back_populates="call", uselist=False, cascade="all, delete")
    audio_insight = relationship("AudioInsight",   back_populates="call", uselist=False, cascade="all, delete")
    metadata_rec  = relationship("CallMetadata",   back_populates="call", uselist=False, cascade="all, delete")
    tool_calls    = relationship("ToolCall",        back_populates="call", cascade="all, delete")
    utterances    = relationship("TranscriptUtterance", back_populates="call", cascade="all, delete")


class Recording(Base):
    """
    Matches: recordings.sql
    Stores file paths for audio + transcript + metadata JSON files.
    """
    __tablename__ = "recordings"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    call_id             = Column(String(100), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, unique=True)
    audio_path          = Column(Text)
    transcript_json_path= Column(Text)
    metadata_json_path  = Column(Text)
    imported_at         = Column(Timestamp, default=datetime.utcnow)

    call = relationship("Call", back_populates="recording")


class AudioInsight(Base):
    """
    Matches: audio_insights.sql
    This is where your v6 pipeline output lands.
    Every field maps directly to your call_summary dict.
    """
    __tablename__ = "audio_insights"

    id                        = Column(Integer, primary_key=True, autoincrement=True)
    call_id                   = Column(String(100), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, unique=True)
    silence_ratio             = Column(Numeric(8, 4))
    speaking_rate             = Column(Numeric(10, 2))
    agent_talk_ratio          = Column(Numeric(8, 4))
    user_talk_ratio           = Column(Numeric(8, 4))
    interruption_count        = Column(Integer)
    average_response_delay_sec= Column(Numeric(8, 4))
    sentiment_score           = Column(Numeric(8, 4))
    created_at                = Column(Timestamp, default=datetime.utcnow)

    # ── Extra columns from your pipeline (not in original SQL but needed) ──
    # Add these with ALTER TABLE or in create_tables() below:
    engagement_score          = Column(Numeric(8, 2))
    hesitation_count          = Column(Integer)
    total_turns               = Column(Integer)
    agent_talk_time_sec       = Column(Numeric(10, 2))
    customer_talk_time_sec    = Column(Numeric(10, 2))
    avg_pause_sec             = Column(Numeric(8, 4))
    avg_energy                = Column(Numeric(10, 6))
    avg_pitch_hz              = Column(Numeric(10, 2))
    agent_avg_energy          = Column(Numeric(10, 6))
    customer_avg_energy       = Column(Numeric(10, 6))
    agent_avg_pitch_hz        = Column(Numeric(10, 2))
    customer_avg_pitch_hz     = Column(Numeric(10, 2))
    conversation_flow         = Column(String(20))
    processing_sec            = Column(Numeric(8, 2))
    # ── Sentiment Trajectory (added May 2026) ──────────────────────────────────
    sentiment_trajectory      = Column(String(20))   # improving | stable | deteriorating
    trajectory_start_energy   = Column(Numeric(10, 6))
    trajectory_end_energy     = Column(Numeric(10, 6))
    # ── emotion2vec (added May 2026) ───────────────────────────────────────────
    dominant_emotion          = Column(String(20))   # most common customer emotion in this call
    dominant_emotion_score    = Column(Numeric(8, 4)) # avg confidence of dominant emotion

    call = relationship("Call", back_populates="audio_insight")


class User(Base):
    """
    Platform users — both Heya AI admins and client business users.
    role = 'heya_admin'  → can view all clients (God View)
    role = 'client'      → can view ONLY their own client_id data
    """
    __tablename__ = "users"

    id              = Column(String(100), primary_key=True)
    client_id       = Column(String(100), ForeignKey("clients.id", ondelete="CASCADE"), nullable=True)
    email           = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role            = Column(String(50),  nullable=False)   # 'heya_admin' | 'client'
    created_at      = Column(Timestamp, default=datetime.utcnow)

    client = relationship("Client", foreign_keys=[client_id])


class RAGQueryHistory(Base):
    """
    Every RAG query + response saved per client.
    Lets clients review their past questions and answers.
    """
    __tablename__ = "rag_query_history"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    client_id       = Column(String(100), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    user_id         = Column(String(100), nullable=True)
    query           = Column(Text, nullable=False)
    response        = Column(Text)
    sources         = Column(JSONB)
    query_type      = Column(String(50))    # 'semantic' | 'sql_aggregation'
    response_time_ms= Column(Integer)
    created_at      = Column(Timestamp, default=datetime.utcnow)

    client = relationship("Client")


class CallMetadata(Base):
    """
    Matches: call_metadata.sql
    Raw metadata JSON + token/cost breakdown from Retell.
    NOTE: your SQL has a typo 'disconnectio_rason' — kept as-is.
    """
    __tablename__ = "call_metadata"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    call_id             = Column(String(100), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, unique=True)
    disconnectio_rason  = Column(String(255))   # typo kept to match your SQL
    latency_ms          = Column(Numeric(10, 2))
    total_tokens        = Column(Integer)
    prompt_tokens       = Column(Integer)
    completion_tokens   = Column(Integer)
    tool_call_count     = Column(Integer)
    raw_metadata        = Column(JSONB)
    imported_at         = Column(Timestamp, default=datetime.utcnow)

    call = relationship("Call", back_populates="metadata_rec")


class ToolCall(Base):
    """
    Matches: tool_calls.sql
    Logs every tool the AI agent called during a conversation.
    """
    __tablename__ = "tool_calls"

    id         = Column(BigInteger, primary_key=True, autoincrement=True)
    call_id    = Column(String(100), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    tool_name  = Column(String(255))
    tool_input = Column(JSONB)
    tool_output= Column(JSONB)
    called_at  = Column(Timestamp)

    call = relationship("Call", back_populates="tool_calls")


class TranscriptUtterance(Base):
    """
    Matches: transcript_utterness.sql
    One row per speaker turn in the transcript.
    emotion / emotion_score populated by emotion_processor.py (emotion2vec).
    """
    __tablename__ = "transcript_utterances"

    id              = Column(BigInteger, primary_key=True, autoincrement=True)
    call_id         = Column(String(100), ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    utterness_index = Column(Integer, nullable=False)
    role            = Column(String(20), nullable=False)   # 'agent' or 'user'
    content         = Column(Text)
    emotion         = Column(String(20))      # happy | sad | angry | neutral | fearful | disgusted | surprised
    emotion_score   = Column(Numeric(8, 4))   # confidence 0.0–1.0

    call  = relationship("Call", back_populates="utterances")
    words = relationship("TranscriptWord", back_populates="utterance", cascade="all, delete")


class TranscriptWord(Base):
    """
    Matches: transcripts_words.sql
    One row per word — word-level timing data.
    NOTE: your SQL file has several typos — fixed here for correct Python.
    """
    __tablename__ = "transcript_words"

    id            = Column(BigInteger, primary_key=True, autoincrement=True)
    utterness_id  = Column(BigInteger, ForeignKey("transcript_utterances.id", ondelete="CASCADE"), nullable=False)
    word_index    = Column(Integer, nullable=False)
    word          = Column(Text, nullable=False)
    start_time_sec= Column(Numeric(10, 3))
    end_time_sec  = Column(Numeric(10, 3))

    utterance = relationship("TranscriptUtterance", back_populates="words")


class AlertConfig(Base):
    """
    Per-client alert subscriptions.
    One row per (client_id, alert_type) pair.
    alert_type maps to recommendation IDs from recommendations.py.
    """
    __tablename__ = "alert_configs"

    id             = Column(Integer,     primary_key=True, autoincrement=True)
    client_id      = Column(String(100), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    alert_type     = Column(String(50),  nullable=False)
    enabled        = Column(Boolean,     default=True,  nullable=False)
    email          = Column(String(255), nullable=False)
    min_priority   = Column(String(20),  default="warning")  # "warning" | "critical"
    last_triggered = Column(Timestamp,   nullable=True)
    created_at     = Column(Timestamp,   default=datetime.utcnow)
    updated_at     = Column(Timestamp,   default=datetime.utcnow, onupdate=datetime.utcnow)

    client = relationship("Client")


class AlertLog(Base):
    """
    Immutable record of every alert email attempted.
    """
    __tablename__ = "alert_logs"

    id         = Column(BigInteger,  primary_key=True, autoincrement=True)
    client_id  = Column(String(100), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False)
    alert_type = Column(String(50))
    subject    = Column(String(500))
    status     = Column(String(20))   # "sent" | "failed" | "cooldown"
    sent_at    = Column(Timestamp,   default=datetime.utcnow)

    client = relationship("Client")


# ═══════════════════════════════════════════════════════════════════════
# 4.  CREATE ALL TABLES  (run once to initialise your DB)
# ═══════════════════════════════════════════════════════════════════════
def create_tables():
    """
    Creates all tables if they don't exist.
    Safe to run multiple times — won't drop existing data.

    Run once:
        from database import create_tables
        create_tables()
    """
    Base.metadata.create_all(bind=engine)
    print("✅ All tables created (or already exist)")


# ═══════════════════════════════════════════════════════════════════════
# 5.  CRUD HELPERS
# ═══════════════════════════════════════════════════════════════════════

def save_audio_insights(call_id: str, summary: dict) -> bool:
    """
    Takes the call_summary dict from your v6 pipeline and writes it
    to the audio_insights table.

    Args:
        call_id : the call's primary key in the calls table
        summary : dict returned by build_call_summary() in v6

    Returns:
        True if saved, False if call_id not found or already exists

    Example:
        turn_df, summary = process_call(audio_path, pipeline)
        save_audio_insights("call_abc123", summary)
    """
    with get_db() as db:

        # Check the call exists first
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            print(f"  ⚠ call_id '{call_id}' not found in calls table — skipping")
            return False

        # Check if insight already exists (upsert logic)
        existing = db.query(AudioInsight).filter(
            AudioInsight.call_id == call_id
        ).first()

        # Helper to safely convert to float
        def _f(key, default=None):
            val = summary.get(key, default)
            try:
                return float(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        def _i(key, default=None):
            val = summary.get(key, default)
            try:
                return int(val) if val is not None else None
            except (TypeError, ValueError):
                return None

        # Build the total talk time for ratio calculations
        agent_talk    = _f("agent_talk_time_sec", 0)
        customer_talk = _f("customer_talk_time_sec", 0)
        total_talk    = (agent_talk or 0) + (customer_talk or 0)

        values = dict(
            call_id                    = call_id,
            silence_ratio              = _f("silence_ratio"),
            speaking_rate              = _f("speech_rate_proxy"),       # your proxy field
            agent_talk_ratio           = round(agent_talk / (total_talk + 1e-6), 4) if total_talk else None,
            user_talk_ratio            = round(customer_talk / (total_talk + 1e-6), 4) if total_talk else None,
            interruption_count         = _i("interruption_count"),
            average_response_delay_sec = _f("avg_pause_sec"),
            sentiment_score            = None,                          # filled later by emotion2vec
            engagement_score           = _f("engagement_score"),
            hesitation_count           = _i("hesitation_count"),
            total_turns                = _i("total_turns"),
            agent_talk_time_sec        = _f("agent_talk_time_sec"),
            customer_talk_time_sec     = _f("customer_talk_time_sec"),
            avg_pause_sec              = _f("avg_pause_sec"),
            avg_energy                 = _f("avg_energy"),
            avg_pitch_hz               = _f("avg_pitch_hz"),
            agent_avg_energy           = _f("agent_avg_energy"),
            customer_avg_energy        = _f("customer_avg_energy"),
            agent_avg_pitch_hz         = _f("agent_avg_pitch_hz"),
            customer_avg_pitch_hz      = _f("customer_avg_pitch_hz"),
            conversation_flow          = summary.get("conversation_flow"),
            processing_sec             = _f("processing_sec"),
            sentiment_trajectory       = summary.get("sentiment_trajectory"),
            trajectory_start_energy    = _f("trajectory_start_energy"),
            trajectory_end_energy      = _f("trajectory_end_energy"),
            created_at                 = datetime.utcnow(),
        )

        if existing:
            # Update existing record
            for k, v in values.items():
                if k != "call_id":
                    setattr(existing, k, v)
            print(f"  🔄 Updated audio_insights for call_id: {call_id}")
        else:
            # Insert new record
            db.add(AudioInsight(**values))
            print(f"  ✅ Saved audio_insights for call_id: {call_id}")

        return True


def save_recording(call_id: str,
                   audio_path: str,
                   transcript_json_path: Optional[str] = None,
                   metadata_json_path:   Optional[str] = None) -> bool:
    """
    Saves file paths to the recordings table.

    Example:
        save_recording("call_abc123", "sample_audio/call_abc123.wav")
    """
    with get_db() as db:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            print(f"  ⚠ call_id '{call_id}' not found — skipping recording save")
            return False

        existing = db.query(Recording).filter(Recording.call_id == call_id).first()

        if existing:
            existing.audio_path           = audio_path
            existing.transcript_json_path = transcript_json_path
            existing.metadata_json_path   = metadata_json_path
        else:
            db.add(Recording(
                call_id              = call_id,
                audio_path           = audio_path,
                transcript_json_path = transcript_json_path,
                metadata_json_path   = metadata_json_path,
            ))

        print(f"  ✅ Saved recording path for call_id: {call_id}")
        return True


def save_utterances(call_id: str, turn_df) -> bool:
    """
    Saves turn-level data from your pipeline into transcript_utterances.
    turn_df = the DataFrame returned by process_call()

    Example:
        turn_df, summary = process_call(audio_path, pipeline)
        save_utterances("call_abc123", turn_df)
    """
    if turn_df.empty:
        return False

    with get_db() as db:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            print(f"  ⚠ call_id '{call_id}' not found — skipping utterance save")
            return False

        # Delete existing utterances for this call before re-inserting
        db.query(TranscriptUtterance).filter(
            TranscriptUtterance.call_id == call_id
        ).delete()

        for idx, row in turn_df.iterrows():
            role    = row.get("role", "agent")
            content = (
                f"[{row.get('start_sec', 0):.1f}s–{row.get('end_sec', 0):.1f}s] "
                f"Energy: {row.get('energy_mean', 'N/A'):.4f} | "
                f"Pitch: {row.get('pitch_mean_hz', 'N/A'):.1f}Hz"
            )
            db.add(TranscriptUtterance(
                call_id         = call_id,
                utterness_index = int(idx),
                role            = "agent" if role == "agent" else "user",
                content         = content,
            ))

        print(f"  ✅ Saved {len(turn_df)} utterances for call_id: {call_id}")
        return True


def get_audio_insights_by_client(client_id: str) -> list[dict]:
    """
    Fetch all audio insights for a specific client.
    Used by the RAG system + dashboard.

    Returns list of dicts — one per call.
    """
    with get_db() as db:
        rows = (
            db.query(AudioInsight, Call)
            .join(Call, AudioInsight.call_id == Call.id)
            .filter(Call.client_id == client_id)
            .all()
        )

        # Build agent_id → persona_name lookup (persona_name added via migrate_agent_profiles.sql)
        agent_name_map: dict = {}
        try:
            agent_rows = db.execute(
                text("SELECT id, persona_name FROM agents WHERE client_id = :cid"),
                {"cid": client_id},
            ).fetchall()
            agent_name_map = {r.id: r.persona_name for r in agent_rows}
        except Exception:
            pass  # column may not exist in older DB — degrade gracefully

        from quality import compute_quality_score, quality_grade

        results = []
        for insight, call in rows:
            qs = compute_quality_score(
                safe_json_float(insight.engagement_score),
                insight.conversation_flow,
                call.call_successful,
                insight.dominant_emotion,
            )
            results.append({
                "call_id":                insight.call_id,
                "client_id":              call.client_id,
                "direction":              call.direction,
                "call_status":            call.call_status,
                "duration_ms":            call.duration_ms or 0,
                "start_timestamp":        call.start_timstamp,   # ms since epoch
                "call_successful":        call.call_successful,
                "user_sentiment":         call.user_sentiment,
                "engagement_score":       safe_json_float(insight.engagement_score),
                "silence_ratio":          safe_json_float(insight.silence_ratio),
                "interruption_count":     insight.interruption_count or 0,
                "hesitation_count":       insight.hesitation_count or 0,
                "conversation_flow":      insight.conversation_flow,
                "avg_pause_sec":          safe_json_float(insight.avg_pause_sec),
                "avg_energy":             safe_json_float(insight.avg_energy),
                "avg_pitch_hz":           safe_json_float(insight.avg_pitch_hz),
                "agent_avg_pitch_hz":     safe_json_float(insight.agent_avg_pitch_hz),
                "customer_avg_pitch_hz":  safe_json_float(insight.customer_avg_pitch_hz),
                "agent_avg_energy":       safe_json_float(insight.agent_avg_energy),
                "customer_avg_energy":    safe_json_float(insight.customer_avg_energy),
                "agent_talk_time_sec":    safe_json_float(insight.agent_talk_time_sec),
                "customer_talk_time_sec": safe_json_float(insight.customer_talk_time_sec),
                "total_silence_sec":      safe_json_float(insight.avg_pause_sec),
                "total_turns":              insight.total_turns or 0,
                "sentiment_trajectory":     insight.sentiment_trajectory,
                "trajectory_start_energy":  safe_json_float(insight.trajectory_start_energy),
                "trajectory_end_energy":    safe_json_float(insight.trajectory_end_energy),
                "dominant_emotion":         insight.dominant_emotion,
                "dominant_emotion_score":   safe_json_float(insight.dominant_emotion_score),
                "quality_score":            qs,
                "quality_grade":            quality_grade(qs),
                "topic":                    call.topic,
                "topic_confidence":         safe_json_float(call.topic_confidence),
                "created_at":               str(insight.created_at),
                "agent_id":                 call.agent_id,
                "agent_name":               agent_name_map.get(call.agent_id) if call.agent_id else None,
            })

        return results


def test_connection() -> bool:
    """
    Quick check that the database is reachable.
    Run this first before anything else.
    """
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print(f"✅ Database connected: {DATABASE_URL.split('@')[-1]}")
        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("\nCheck:")
        print("  1. PostgreSQL is running")
        print("  2. DATABASE_URL env var is correct")
        print("  3. Database 'heya_audio' exists")
        return False


# ═══════════════════════════════════════════════════════════════════════
# 6.  QUICK TEST  (run this file directly to verify everything works)
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print("── Testing database.py ──────────────────────────")

    # Step 1: connection
    if not test_connection():
        exit(1)

    # Step 2: create tables
    create_tables()

    # Step 3: simulate saving a pipeline output
    dummy_summary = {
        "file_name":              "test_call.wav",
        "total_turns":            12,
        "total_duration_sec":     245.5,
        "total_silence_sec":      18.3,
        "avg_pause_sec":          0.45,
        "silence_ratio":          0.069,
        "agent_talk_time_sec":    145.2,
        "customer_talk_time_sec": 82.0,
        "interruption_count":     2,
        "hesitation_count":       3,
        "engagement_score":       74.5,
        "conversation_flow":      "smooth",
        "avg_energy":             0.032145,
        "avg_pitch_hz":           187.4,
        "agent_avg_energy":       0.035,
        "customer_avg_energy":    0.028,
        "agent_avg_pitch_hz":     175.2,
        "customer_avg_pitch_hz":  201.8,
        "processing_sec":         38.2,
    }

    print("\nTest save_audio_insights() with a dummy call_id...")
    result = save_audio_insights("test_call_001", dummy_summary)
    print(f"Result: {result}")

    print("\nTest get_audio_insights_by_client()...")
    insights = get_audio_insights_by_client("test_client_001")
    print(f"Found {len(insights)} insight(s)")

    print("\n── All tests done ───────────────────────────────")