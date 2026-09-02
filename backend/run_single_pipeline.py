"""
run_single_pipeline.py  —  Heya AI Voice Analytics
Run the audio pipeline on one call. Must use the heya_pipeline conda env.

Usage:
    C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe run_single_pipeline.py \
        --call-id call_demo_xxx \
        --audio "D:\path\to\audio.wav"
"""

import argparse
import sys
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from pipeline import load_pipeline, process_call, SAMPLE_RATE
from database import get_db, save_audio_insights, Call


def main():
    parser = argparse.ArgumentParser(description="Run heya audio pipeline on one call")
    parser.add_argument("--call-id", required=True, help="call_id already in the DB")
    parser.add_argument("--audio",   required=True, help="Path to the .wav file")
    args = parser.parse_args()

    call_id    = args.call_id
    audio_path = Path(args.audio)

    if not audio_path.exists():
        print(f"✗ Audio file not found: {audio_path}")
        sys.exit(1)

    with get_db() as db:
        if not db.query(Call).filter(Call.id == call_id).first():
            print(f"✗ call_id '{call_id}' not in DB — aborting")
            sys.exit(1)

    print(f"Loading diarisation pipeline...")
    pipe = load_pipeline()

    print(f"Processing {audio_path.name} ...")
    turn_df, summary = process_call(str(audio_path), pipe, SAMPLE_RATE)

    if summary.get("status") == "failed":
        print(f"✗ Pipeline failed: {summary.get('reason', 'unknown')}")
        with get_db() as db:
            call = db.query(Call).filter(Call.id == call_id).first()
            if call:
                call.processing_status = "failed"
        sys.exit(1)

    save_audio_insights(call_id, summary)

    with get_db() as db:
        call = db.query(Call).filter(Call.id == call_id).first()
        if call:
            call.processing_status = "completed"

    print(
        f"✅ Done — engagement: {summary.get('engagement_score')} | "
        f"flow: {summary.get('conversation_flow')} | "
        f"trajectory: {summary.get('sentiment_trajectory')} | "
        f"{summary.get('processing_sec')}s"
    )


if __name__ == "__main__":
    main()
