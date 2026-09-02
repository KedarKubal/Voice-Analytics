"""
migrate_emotion.py  —  Heya AI Voice Analytics
Add emotion columns to transcript_utterances and audio_insights.

Run once from backend/ (heya_audio env is fine):
    python migrate_emotion.py

Columns added
-------------
transcript_utterances:
    emotion         VARCHAR(20)    happy | sad | angry | neutral | fearful |
                                   disgusted | surprised | unknown
    emotion_score   NUMERIC(8,4)   confidence 0.0–1.0

audio_insights:
    dominant_emotion       VARCHAR(20)   most common customer emotion in this call
    dominant_emotion_score NUMERIC(8,4)  avg confidence of dominant emotion
    (sentiment_score was always NULL — now populated with dominant emotion confidence)
"""

import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

ADMIN_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5435/voice_ai")
engine    = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")

MIGRATIONS = [
    (
        "transcript_utterances.emotion",
        "ALTER TABLE transcript_utterances ADD COLUMN IF NOT EXISTS emotion VARCHAR(20);",
    ),
    (
        "transcript_utterances.emotion_score",
        "ALTER TABLE transcript_utterances ADD COLUMN IF NOT EXISTS emotion_score NUMERIC(8,4);",
    ),
    (
        "audio_insights.dominant_emotion",
        "ALTER TABLE audio_insights ADD COLUMN IF NOT EXISTS dominant_emotion VARCHAR(20);",
    ),
    (
        "audio_insights.dominant_emotion_score",
        "ALTER TABLE audio_insights ADD COLUMN IF NOT EXISTS dominant_emotion_score NUMERIC(8,4);",
    ),
    (
        "idx_utterances_emotion",
        "CREATE INDEX IF NOT EXISTS idx_utterances_emotion ON transcript_utterances (call_id, emotion);",
    ),
]


def run():
    print("=" * 55)
    print("Heya AI — emotion2vec schema migration")
    print("=" * 55)

    with engine.connect() as conn:
        for name, sql in MIGRATIONS:
            print(f"  {name}...", end=" ", flush=True)
            try:
                conn.execute(text(sql))
                print("✅")
            except Exception as e:
                print(f"⚠  {e}")

    print()
    print("✅  Migration complete.")
    print()
    print("Next step — install emotion2vec (heya_pipeline env):")
    print("    conda activate heya_pipeline")
    print("    pip install funasr modelscope huggingface_hub soundfile")
    print()
    print("Then run the emotion processor:")
    print("    python emotion_processor.py --client client_heya_001")
    print("    python emotion_processor.py --client client_heya_002")


if __name__ == "__main__":
    run()
