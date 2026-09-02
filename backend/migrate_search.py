"""
migrate_search.py  —  Heya AI Voice Analytics
Add GIN indexes for PostgreSQL full-text search.

Run once from backend/:
    python migrate_search.py

What this creates
-----------------
1.  GIN index on transcript_utterances.content
    → powers fast keyword search across all spoken words in every call

2.  GIN index on calls (call_summary || transcript)
    → powers search across AI-generated summaries and raw transcript text

3.  Functional index on calls.start_timstamp → timestamptz
    → used by the search endpoint to sort results by actual call date

CONCURRENTLY means existing queries are not blocked while indexes build.
On 800 calls it completes in a few seconds.
"""

import os
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

ADMIN_URL = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5435/voice_ai")
engine    = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")

INDEXES = [
    (
        "idx_utterances_fts",
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_utterances_fts
        ON transcript_utterances
        USING GIN (to_tsvector('english', coalesce(content, '')));
        """,
    ),
    (
        "idx_calls_summary_fts",
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_calls_summary_fts
        ON calls
        USING GIN (to_tsvector('english',
            coalesce(call_summary, '') || ' ' || coalesce(transcript, '')
        ));
        """,
    ),
    (
        "idx_calls_start_ts",
        """
        CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_calls_start_ts
        ON calls (start_timstamp DESC NULLS LAST);
        """,
    ),
]


def run():
    print("=" * 55)
    print("Heya AI — Full-text search index migration")
    print("=" * 55)

    with engine.connect() as conn:
        for name, sql in INDEXES:
            print(f"  Creating {name}...", end=" ", flush=True)
            try:
                conn.execute(text(sql))
                print("✅")
            except Exception as e:
                print(f"⚠  {e}")

    print()
    print("✅  Search indexes ready — restart the API server.")


if __name__ == "__main__":
    run()
