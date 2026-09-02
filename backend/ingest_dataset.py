"""
ingest_dataset.py  —  Heya AI Voice Analytics
Bulk ingestion of 400+ calls from two client datasets.

Folder structure:
    dataset/
    ├── artel_apartments/
    │   └── recordings/
    │       └── call_xxx/
    │           ├── audio.wav
    │           ├── metadata.json
    │           └── transcript.json
    └── mvaa_legal/
        └── recordings/
            └── call_xxx/
                ├── audio.wav
                ├── metadata.json
                └── transcript.json

Phase 1 (FAST — no GPU):
    Reads metadata.json + transcript.json
    Inserts into: clients, agents, calls, call_metadata,
                  tool_calls, transcript_utterances, transcript_words

Phase 2 (SLOW — GPU):
    Runs audio pipeline on audio.wav
    Inserts into: audio_insights

Usage:
    python ingest_dataset.py --phase 1              # all calls, metadata only
    python ingest_dataset.py --phase 1 --limit 5   # test first 5 calls
    python ingest_dataset.py --phase 2              # audio pipeline all calls
    python ingest_dataset.py --phase 2 --limit 5   # test pipeline on 5 calls
    python ingest_dataset.py --summary              # show DB counts only
"""

import os
import sys
import json
import argparse
import traceback
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from database import (
    get_db, create_tables,
    Client, Agent, Call, CallMetadata,
    ToolCall, TranscriptUtterance, TranscriptWord,
    AudioInsight, Recording,
    save_audio_insights,
)
from sqlalchemy import func


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG  —  edit paths and client names here
# ═══════════════════════════════════════════════════════════════════════════════

# Path to your dataset folder — relative to backend/
# If backend/ and dataset/ are siblings under PROJECT/, this is correct
DATASET_ROOT = Path("../dataset")

CLIENTS = {
    "artel_apartments": {
        "client_id":   "client_heya_001",
        "client_name": "Artel Apartments",
        "folder_name": "artel_apartments",
    },
    "mvaa_legal": {
        "client_id":   "client_heya_002",
        "client_name": "MVAA Legal",
        "folder_name": "mvaa_legal",
    },
}

# Each tuple = (path_to_recordings_folder, client_config_dict)
DATASET_FOLDERS = [
    (DATASET_ROOT / "artel_apartments" / "recordings", CLIENTS["artel_apartments"]),
    (DATASET_ROOT / "mvaa_legal"       / "recordings", CLIENTS["mvaa_legal"]),
]


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def safe_float(val, default=None):
    try:
        return float(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def safe_int(val, default=None):
    try:
        return int(val) if val is not None else default
    except (TypeError, ValueError):
        return default


def ts_to_datetime(ts_ms):
    """Convert millisecond Unix timestamp to datetime."""
    try:
        return datetime.fromtimestamp(int(ts_ms) / 1000)
    except (TypeError, ValueError):
        return None


def get_all_call_folders(dataset_folders: list) -> list:
    """
    Scan all dataset folders.
    Returns list of (call_folder_path, client_cfg) tuples.
    Only includes folders containing a metadata.json file.
    """
    results = []

    for base_path, client_cfg in dataset_folders:
        base = Path(base_path)

        if not base.exists():
            print(f"  ⚠ Not found: {base.resolve()}")
            continue

        call_dirs = sorted([
            d for d in base.iterdir()
            if d.is_dir()
            and d.name.startswith("call_")
            and (d / "metadata.json").exists()
        ])

        print(f"  {client_cfg['client_name']:<25} {len(call_dirs)} call(s)")
        results.extend([(d, client_cfg) for d in call_dirs])

    return results


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — INSERT FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════
def ensure_client_exists(client_cfg: dict):
    """Insert client record if it does not already exist."""
    with get_db() as db:
        existing = db.query(Client).filter(
            Client.id == client_cfg["client_id"]
        ).first()
        if not existing:
            db.add(Client(
                id          = client_cfg["client_id"],
                name        = client_cfg["client_name"],
                folder_name = client_cfg["folder_name"],
                created_at  = datetime.utcnow(),
                updated_at  = datetime.utcnow(),
            ))
            print(f"  ✅ Created client: {client_cfg['client_id']} "
                  f"({client_cfg['client_name']})")


def ensure_agent_exists(agent_id: str, agent_name: str,
                         version, client_id: str):
    """Insert agent record if it does not already exist."""
    if not agent_id:
        return
    with get_db() as db:
        if not db.query(Agent).filter(Agent.id == agent_id).first():
            db.add(Agent(
                id         = agent_id,
                client_id  = client_id,
                name       = agent_name or "Heya AI Agent",
                version    = str(version) if version else None,
                created_at = datetime.utcnow(),
                updated_at = datetime.utcnow(),
            ))


def ingest_metadata(call_folder: Path, client_cfg: dict) -> dict | None:
    """
    Read metadata.json → insert into calls, call_metadata, tool_calls.
    Returns call data dict on success, None on failure.
    """
    meta_path = call_folder / "metadata.json"
    client_id = client_cfg["client_id"]

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        print(f"    ✗ Cannot read metadata.json: {e}")
        return None

    # Retell wraps call data under a "call" key
    call_data = raw.get("call", raw)
    call_id   = call_data.get("call_id")

    if not call_id:
        print(f"    ✗ No call_id found in {meta_path}")
        return None

    # Ensure agent FK exists before inserting call
    ensure_agent_exists(
        agent_id   = call_data.get("agent_id"),
        agent_name = call_data.get("agent_name", "Heya AI Agent"),
        version    = call_data.get("agent_version"),
        client_id  = client_id,
    )

    # Parse costs
    call_cost     = call_data.get("call_cost", {})
    product_costs = {
        p["product"]: p.get("cost", 0)
        for p in call_cost.get("product_costs", [])
    }
    total_cost = safe_float(call_cost.get("combined_cost"))
    llm_cost   = safe_float(
        product_costs.get("gemini_3_0_flash") or
        product_costs.get("gpt4") or
        product_costs.get("llm")
    )
    tts_cost   = safe_float(
        product_costs.get("elevenlabs_tts_new") or
        product_costs.get("tts")
    )
    stt_cost   = safe_float(
        product_costs.get("asr") or
        product_costs.get("stt")
    )

    # Parse analysis
    analysis        = call_data.get("call_analysis", {})
    call_summary    = analysis.get("call_summary")
    user_sentiment  = analysis.get("user_sentiment")
    call_successful = analysis.get("call_successful")

    with get_db() as db:

        # ── calls ─────────────────────────────────────────────────────────────
        if not db.query(Call).filter(Call.id == call_id).first():
            db.add(Call(
                id                = call_id,
                client_id         = client_id,
                agent_id          = call_data.get("agent_id"),
                call_type         = call_data.get("call_type"),
                call_status       = call_data.get("call_status"),
                direction         = call_data.get("direction"),
                from_number       = call_data.get("from_number"),
                to_number         = call_data.get("to_number"),
                start_timstamp    = safe_int(call_data.get("start_timestamp")),
                end_timestamp     = safe_int(call_data.get("end_timestamp")),
                duration_ms       = safe_int(call_data.get("duration_ms")),
                transcript        = call_data.get("transcript"),
                call_summary      = call_summary,
                user_sentiment    = user_sentiment,
                call_successful   = call_successful,
                processing_status = "pending",
                total_cost        = total_cost,
                llm_cost          = llm_cost,
                tts_cost          = tts_cost,
                stt_cost          = stt_cost,
                created_at        = (
                    ts_to_datetime(call_data.get("start_timestamp"))
                    or datetime.utcnow()
                ),
            ))

        # ── call_metadata ─────────────────────────────────────────────────────
        if not db.query(CallMetadata).filter(
            CallMetadata.call_id == call_id
        ).first():
            lat     = call_data.get("latency", {})
            llm_lat = lat.get("llm", {})
            e2e_lat = lat.get("e2e", {})
            tok     = call_data.get("llm_token_usage", {})

            db.add(CallMetadata(
                call_id            = call_id,
                disconnectio_rason = call_data.get("disconnection_reason"),
                latency_ms         = safe_float(e2e_lat.get("p50")),
                total_tokens       = safe_int(
                    (tok.get("average") or 0) *
                    (tok.get("num_requests") or 1)
                ),
                prompt_tokens      = None,
                completion_tokens  = None,
                tool_call_count    = len(call_data.get("tool_calls", [])),
                raw_metadata       = {
                    "llm_latency_p50": llm_lat.get("p50"),
                    "llm_latency_p99": llm_lat.get("p99"),
                    "e2e_latency_p50": e2e_lat.get("p50"),
                    "e2e_latency_p99": e2e_lat.get("p99"),
                    "cost_breakdown":  product_costs,
                    "agent_version":   call_data.get("agent_version"),
                    "call_analysis":   analysis,
                },
                imported_at        = datetime.utcnow(),
            ))

        # ── tool_calls ────────────────────────────────────────────────────────
        for tc in call_data.get("tool_calls", []):
            db.add(ToolCall(
                call_id    = call_id,
                tool_name  = tc.get("name"),
                tool_input = None,
                tool_output= None,
                called_at  = None,
            ))

    return call_data


def ingest_transcript(call_id: str, call_folder: Path) -> int:
    """
    Read transcript.json → insert into transcript_utterances + transcript_words.
    Returns number of speech utterances inserted.
    """
    path = call_folder / "transcript.json"
    if not path.exists():
        return 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            utterances = json.load(f)
    except Exception as e:
        print(f"    ✗ Cannot read transcript.json: {e}")
        return 0

    if not isinstance(utterances, list):
        return 0

    count = 0
    with get_db() as db:
        # Remove existing utterances for this call
        db.query(TranscriptUtterance).filter(
            TranscriptUtterance.call_id == call_id
        ).delete()

        for idx, utt in enumerate(utterances):
            role = utt.get("role", "agent")

            # Skip non-speech entries
            if role in ("tool_call_invocation", "tool_call_result"):
                continue

            norm_role = "agent" if role == "agent" else "user"
            content   = utt.get("content", "")

            utt_obj = TranscriptUtterance(
                call_id         = call_id,
                utterness_index = idx,
                role            = norm_role,
                content         = content,
            )
            db.add(utt_obj)
            db.flush()  # get auto-generated id

            for w_idx, wd in enumerate(utt.get("words", [])):
                word_text = wd.get("word", "").strip()
                if not word_text:
                    continue
                db.add(TranscriptWord(
                    utterness_id   = utt_obj.id,
                    word_index     = w_idx,
                    word           = word_text,
                    start_time_sec = safe_float(wd.get("start")),
                    end_time_sec   = safe_float(wd.get("end")),
                ))

            count += 1

    return count


def ingest_recording_path(call_id: str, call_folder: Path):
    """Register file paths in the recordings table."""
    with get_db() as db:
        if db.query(Recording).filter(Recording.call_id == call_id).first():
            return
        audio = call_folder / "audio.wav"
        db.add(Recording(
            call_id               = call_id,
            audio_path            = str(audio.resolve()) if audio.exists() else None,
            transcript_json_path  = str((call_folder / "transcript.json").resolve()),
            metadata_json_path    = str((call_folder / "metadata.json").resolve()),
            imported_at           = datetime.utcnow(),
        ))


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — AUDIO PIPELINE
# ═══════════════════════════════════════════════════════════════════════════════
def run_audio_pipeline_on_call(call_id: str, audio_path: Path,
                                pipeline, sample_rate: int) -> bool:
    """Run v6 pipeline on one audio file and save to audio_insights."""
    if not audio_path.exists():
        print(f"    ✗ audio.wav not found")
        return False

    # Skip only if fully processed (engagement + trajectory both present)
    with get_db() as db:
        existing = db.query(AudioInsight).filter(
            AudioInsight.call_id == call_id
        ).first()
        if (existing
                and existing.engagement_score is not None
                and existing.sentiment_trajectory is not None):
            print(f"    ⏭ Already processed — skipping")
            return True

    try:
        from pipeline import process_call
        turn_df, summary = process_call(str(audio_path), pipeline, sample_rate)

        if summary.get("status") == "failed":
            print(f"    ✗ Failed: {summary.get('reason')}")
            return False

        save_audio_insights(call_id, summary)

        with get_db() as db:
            call = db.query(Call).filter(Call.id == call_id).first()
            if call:
                call.processing_status = "completed"

        print(f"    ✅ engagement: {summary.get('engagement_score')} | "
              f"flow: {summary.get('conversation_flow')} | "
              f"{summary.get('processing_sec')}s")
        return True

    except Exception as e:
        print(f"    ✗ Error: {e}")
        traceback.print_exc()
        return False


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 1 — RUNNER
# ═══════════════════════════════════════════════════════════════════════════════
def run_phase1(call_folders: list, limit: int = None):
    print("\n" + "═" * 60)
    print("PHASE 1 — Metadata & Transcript Ingestion")
    print("═" * 60)

    if limit:
        call_folders = call_folders[:limit]
        print(f"  Test mode: first {limit} calls only")

    print(f"  Processing: {len(call_folders)} call(s)\n")

    # Create all clients upfront
    seen = set()
    for _, cfg in call_folders:
        if cfg["client_id"] not in seen:
            ensure_client_exists(cfg)
            seen.add(cfg["client_id"])
    print()

    success = failed = 0

    for idx, (folder, client_cfg) in enumerate(call_folders, 1):
        print(f"[{idx:>3}/{len(call_folders)}] {folder.name}  "
              f"({client_cfg['client_name']})")
        try:
            call_data = ingest_metadata(folder, client_cfg)
            if call_data is None:
                failed += 1
                continue

            call_id      = call_data.get("call_id")
            n_utt        = ingest_transcript(call_id, folder)
            ingest_recording_path(call_id, folder)

            dur  = (call_data.get("duration_ms") or 0) // 1000
            sent = call_data.get("call_analysis", {}).get("user_sentiment", "?")
            ok   = call_data.get("call_analysis", {}).get("call_successful", "?")

            print(f"    ✅ {n_utt} utterances | {dur}s | "
                  f"sentiment: {sent} | successful: {ok}")
            success += 1

        except Exception as e:
            print(f"    ✗ {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'═'*60}")
    print(f"Phase 1 complete — {success} ✅  {failed} ✗")
    print(f"{'═'*60}")
    return success


# ═══════════════════════════════════════════════════════════════════════════════
# PHASE 2 — RUNNER
# ═══════════════════════════════════════════════════════════════════════════════
def run_phase2(call_folders: list, limit: int = None):
    print("\n" + "═" * 60)
    print("PHASE 2 — Audio Pipeline (GPU)")
    print("═" * 60)

    if limit:
        call_folders = call_folders[:limit]
        print(f"  Test mode: first {limit} calls only")

    print(f"  Processing: {len(call_folders)} call(s)")
    print("\nLoading diarisation pipeline...")

    from pipeline import load_pipeline, SAMPLE_RATE
    pipe = load_pipeline()
    print("Pipeline ready\n")

    success = failed = skipped = 0

    for idx, (folder, client_cfg) in enumerate(call_folders, 1):
        call_id    = folder.name
        audio_path = folder / "audio.wav"

        print(f"[{idx:>3}/{len(call_folders)}] {folder.name}  "
              f"({client_cfg['client_name']})")

        with get_db() as db:
            if not db.query(Call).filter(Call.id == call_id).first():
                print(f"    ⚠ Not in DB — run Phase 1 first")
                skipped += 1
                continue

        ok = run_audio_pipeline_on_call(call_id, audio_path, pipe, SAMPLE_RATE)
        success += ok
        failed  += not ok

    print(f"\n{'═'*60}")
    print(f"Phase 2 complete — {success} ✅  {failed} ✗  {skipped} ⏭")
    print(f"{'═'*60}")
    return success


# ═══════════════════════════════════════════════════════════════════════════════
# DB SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
def print_db_summary():
    print("\n── Database Summary ──────────────────────────────────")
    with get_db() as db:
        tables = [
            ("clients",               Client),
            ("agents",                Agent),
            ("calls",                 Call),
            ("call_metadata",         CallMetadata),
            ("audio_insights",        AudioInsight),
            ("transcript_utterances", TranscriptUtterance),
            ("transcript_words",      TranscriptWord),
            ("tool_calls",            ToolCall),
            ("recordings",            Recording),
        ]
        for name, model in tables:
            n = db.query(func.count(model.id)).scalar()
            print(f"  {name:<30} {n:>6} rows")

        print("\n  ── Per client ──────────────────────────────────────")
        rows = (
            db.query(Call.client_id, func.count(Call.id))
            .group_by(Call.client_id)
            .all()
        )
        for client_id, count in rows:
            print(f"  {client_id:<30} {count:>6} calls")

        n_insights = db.query(func.count(AudioInsight.id)).scalar()
        if n_insights > 0:
            avg_eng = db.query(func.avg(AudioInsight.engagement_score)).scalar()
            if avg_eng:
                print(f"\n  avg engagement score           {float(avg_eng):.1f}")
            flow_rows = (
                db.query(AudioInsight.conversation_flow,
                         func.count(AudioInsight.id))
                .group_by(AudioInsight.conversation_flow)
                .all()
            )
            for flow, count in flow_rows:
                print(f"  flow '{flow}':{' '*(12-len(str(flow)))}{count} calls")


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Ingest Heya AI call dataset into PostgreSQL"
    )
    parser.add_argument(
        "--phase", type=int, choices=[1, 2], default=1,
        help="1 = metadata + transcripts (fast)  |  2 = audio pipeline (GPU)"
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Limit number of calls processed (useful for testing)"
    )
    parser.add_argument(
        "--summary", action="store_true",
        help="Print DB row counts and exit"
    )
    args = parser.parse_args()

    create_tables()

    if args.summary:
        print_db_summary()
        sys.exit(0)

    print(f"\nScanning dataset...")
    print(f"  Root: {DATASET_ROOT.resolve()}")
    call_folders = get_all_call_folders(DATASET_FOLDERS)

    if not call_folders:
        print("\n❌ No call folders found.")
        print(f"   Dataset root resolves to: {DATASET_ROOT.resolve()}")
        print("   Check DATASET_ROOT in the CONFIG section.")
        sys.exit(1)

    print(f"\n  Grand total: {len(call_folders)} call(s)\n")

    if args.phase == 1:
        run_phase1(call_folders, limit=args.limit)
    else:
        run_phase2(call_folders, limit=args.limit)

    print_db_summary()