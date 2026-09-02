"""
webhook_processor.py  —  Heya AI Voice Analytics
Background task triggered by POST /webhook/retell.

Flow:
    1. Verify the call belongs to a known client (via agent_id → client_id)
    2. Upsert the call row (metadata, summary, sentiment)
    3. Ingest transcript utterances
    4. Save recording URL
    5. Mark call as pending_audio so the pipeline can pick it up

The audio pipeline itself (pyannote diarisation) is NOT run here because:
  - It requires the heya_pipeline conda env (GPU, torchaudio)
  - It takes 30–120 seconds per call
  - Retell expects a 200 response within 3 seconds

Production upgrade path:
  Replace the background task with a Celery worker that:
    1. Downloads the recording_url to a temp file
    2. Runs process_call() in the heya_pipeline env
    3. Saves results to audio_insights
    4. Deletes the temp file
"""

from datetime import datetime
from database import (
    get_db,
    Agent, Call, CallMetadata, TranscriptUtterance, TranscriptWord,
    Recording, AudioInsight,
)


# ── helpers ───────────────────────────────────────────────────────────────────
def _f(val, default=None):
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def _i(val, default=None):
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN BACKGROUND TASK
# ═══════════════════════════════════════════════════════════════════════════════
def ingest_webhook_call(call_data: dict) -> str | None:
    """
    Ingest one call received from a Retell webhook into PostgreSQL.
    Designed to run as a FastAPI BackgroundTask — never raises, always returns.
    """
    call_id  = call_data.get("call_id")
    agent_id = call_data.get("agent_id")

    if not call_id:
        print("  ⚠ [webhook] Payload missing call_id — skipped")
        return None

    print(f"\n[webhook] Processing call_id={call_id}  agent_id={agent_id}")

    # ── 1. Resolve client_id from agent ──────────────────────────────────────
    client_id = None
    with get_db() as db:
        if agent_id:
            agent = db.query(Agent).filter(Agent.id == agent_id).first()
            if agent:
                client_id = agent.client_id

    if not client_id:
        print(f"  ⚠ [webhook] No client found for agent '{agent_id}' — skipped")
        return None

    # ── 2. Parse Retell payload ───────────────────────────────────────────────
    analysis        = call_data.get("call_analysis", {})
    call_summary    = analysis.get("call_summary")
    user_sentiment  = analysis.get("user_sentiment")
    call_successful = analysis.get("call_successful")

    call_cost      = call_data.get("call_cost", {})
    product_costs  = {p["product"]: p.get("cost", 0) for p in call_cost.get("product_costs", [])}
    total_cost     = _f(call_cost.get("combined_cost"))
    llm_cost       = _f(product_costs.get("llm") or product_costs.get("gemini_3_0_flash"))
    tts_cost       = _f(product_costs.get("tts") or product_costs.get("elevenlabs_tts_new"))
    stt_cost       = _f(product_costs.get("stt") or product_costs.get("asr"))

    # ── 3. Upsert call row ────────────────────────────────────────────────────
    try:
        with get_db() as db:
            existing = db.query(Call).filter(Call.id == call_id).first()

            if not existing:
                db.add(Call(
                    id                = call_id,
                    client_id         = client_id,
                    agent_id          = agent_id,
                    call_type         = call_data.get("call_type"),
                    call_status       = call_data.get("call_status"),
                    direction         = call_data.get("direction"),
                    from_number       = call_data.get("from_number"),
                    to_number         = call_data.get("to_number"),
                    start_timstamp    = _i(call_data.get("start_timestamp")),
                    end_timestamp     = _i(call_data.get("end_timestamp")),
                    duration_ms       = _i(call_data.get("duration_ms")),
                    transcript        = call_data.get("transcript"),
                    call_summary      = call_summary,
                    user_sentiment    = user_sentiment,
                    call_successful   = call_successful,
                    processing_status = "webhook_received",
                    total_cost        = total_cost,
                    llm_cost          = llm_cost,
                    tts_cost          = tts_cost,
                    stt_cost          = stt_cost,
                    created_at        = datetime.utcnow(),
                ))
                print(f"  ✅ [webhook] Call row inserted")
            else:
                # Enrich with analysis data if now available (call_analyzed event)
                if call_summary:    existing.call_summary    = call_summary
                if user_sentiment:  existing.user_sentiment  = user_sentiment
                if call_successful is not None:
                    existing.call_successful = call_successful
                existing.processing_status = "webhook_received"
                print(f"  🔄 [webhook] Call row updated")
    except Exception as e:
        print(f"  ✗ [webhook] Failed to upsert call: {e}")
        return None

    # ── 4. Ingest transcript utterances ───────────────────────────────────────
    transcript_obj = call_data.get("transcript_object", [])
    if isinstance(transcript_obj, list) and transcript_obj:
        try:
            with get_db() as db:
                db.query(TranscriptUtterance).filter(
                    TranscriptUtterance.call_id == call_id
                ).delete()

                count = 0
                for idx, utt in enumerate(transcript_obj):
                    role = utt.get("role", "agent")
                    if role in ("tool_call_invocation", "tool_call_result"):
                        continue

                    utt_obj = TranscriptUtterance(
                        call_id         = call_id,
                        utterness_index = idx,
                        role            = "agent" if role == "agent" else "user",
                        content         = utt.get("content", ""),
                    )
                    db.add(utt_obj)
                    db.flush()

                    for w_idx, wd in enumerate(utt.get("words", [])):
                        word_text = wd.get("word", "").strip()
                        if not word_text:
                            continue
                        db.add(TranscriptWord(
                            utterness_id   = utt_obj.id,
                            word_index     = w_idx,
                            word           = word_text,
                            start_time_sec = _f(wd.get("start")),
                            end_time_sec   = _f(wd.get("end")),
                        ))
                    count += 1

            print(f"  ✅ [webhook] {count} utterances inserted")
        except Exception as e:
            print(f"  ✗ [webhook] Failed to insert transcript: {e}")

    # ── 5. Save recording URL ─────────────────────────────────────────────────
    recording_url = call_data.get("recording_url")
    if recording_url:
        try:
            with get_db() as db:
                rec = db.query(Recording).filter(Recording.call_id == call_id).first()
                if not rec:
                    db.add(Recording(call_id=call_id, audio_path=recording_url))
                else:
                    rec.audio_path = recording_url
        except Exception as e:
            print(f"  ✗ [webhook] Failed to save recording URL: {e}")

    # ── 6. Mark as pending audio pipeline ────────────────────────────────────
    # The audio pipeline (pyannote + librosa) must run separately in heya_pipeline env.
    # This status flag lets the /health/queue endpoint surface it to admins.
    try:
        with get_db() as db:
            call = db.query(Call).filter(Call.id == call_id).first()
            if call and not db.query(AudioInsight).filter(
                AudioInsight.call_id == call_id
            ).first():
                call.processing_status = "pending_audio"
    except Exception as e:
        print(f"  ✗ [webhook] Failed to set pending_audio status: {e}")

    print(f"  ✅ [webhook] Done — {call_id} ready for audio pipeline")
    return call_id
