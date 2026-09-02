"""
migrate_topics.py — add topic + topic_confidence columns to calls table.
Run once:
    conda activate heya_audio
    python migrate_topics.py
"""
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()

engine = create_engine(os.getenv("DATABASE_URL"))

with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS topic VARCHAR(50)"
    ))
    conn.execute(text(
        "ALTER TABLE calls ADD COLUMN IF NOT EXISTS topic_confidence NUMERIC(5,4)"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS idx_calls_topic ON calls(topic)"
    ))
    conn.commit()

print("Migration complete — topic + topic_confidence added to calls")
