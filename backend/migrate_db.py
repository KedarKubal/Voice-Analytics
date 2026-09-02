"""
migrate_db.py  —  Heya AI Voice Analytics
One-time database migration: adds new columns to audio_insights.

Run ONCE from heya_audio conda env:
    cd D:\\rmit\\semester_4\\project\\backend
    python migrate_db.py
"""

from dotenv import load_dotenv
load_dotenv()

from database import engine
from sqlalchemy import text

MIGRATIONS = [
    # Sentiment trajectory (improving / stable / deteriorating)
    "ALTER TABLE audio_insights ADD COLUMN IF NOT EXISTS sentiment_trajectory VARCHAR(20)",
    # Energy in first third of turns (call opening)
    "ALTER TABLE audio_insights ADD COLUMN IF NOT EXISTS trajectory_start_energy NUMERIC(10,6)",
    # Energy in last third of turns (call closing)
    "ALTER TABLE audio_insights ADD COLUMN IF NOT EXISTS trajectory_end_energy NUMERIC(10,6)",
]

def run():
    print("Running database migration...")
    with engine.connect() as conn:
        for sql in MIGRATIONS:
            conn.execute(text(sql))
            col = sql.split("ADD COLUMN IF NOT EXISTS")[1].strip().split()[0]
            print(f"  ✅ {col}")
        conn.commit()
    print("\nMigration complete. New columns are ready.")
    print("Next: run  python ingest_dataset.py --phase 2 --limit 50  to populate them.")

if __name__ == "__main__":
    run()
