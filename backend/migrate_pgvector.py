"""
migrate_pgvector.py  —  Heya AI Voice Analytics
Replace ChromaDB with pgvector inside PostgreSQL.

Run once from backend/ with heya_audio env:
    python migrate_pgvector.py

What it does:
  1. Enables the pgvector extension in voice_ai DB
  2. Creates call_embeddings table with vector(1536) column
  3. Adds HNSW index for fast approximate nearest-neighbour search
  4. Adds foreign key to calls table (CASCADE delete keeps vectors in sync)
"""

import os
from dotenv import load_dotenv
load_dotenv()

import psycopg2

DATABASE_URL = os.getenv("DATABASE_URL")


def run():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur  = conn.cursor()

    print("Enabling pgvector extension...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ver = cur.fetchone()[0]
    print(f"  pgvector {ver} ready")

    print("Creating call_embeddings table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS call_embeddings (
            id          BIGSERIAL PRIMARY KEY,
            call_id     TEXT        NOT NULL,
            client_id   TEXT        NOT NULL,
            content     TEXT,
            embedding   vector(1536),
            metadata    JSONB       DEFAULT '{}',
            created_at  TIMESTAMPTZ DEFAULT NOW(),

            CONSTRAINT fk_call
                FOREIGN KEY (call_id)
                REFERENCES calls(id)
                ON DELETE CASCADE
        )
    """)
    print("  Table ready")

    print("Creating indexes...")
    # Fast filter by client before vector search
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ce_client
            ON call_embeddings (client_id)
    """)
    # HNSW index — best balance of speed and recall for production
    # m=16 ef_construction=64 are standard starting values
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ce_hnsw
            ON call_embeddings
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
    """)
    print("  Indexes ready (HNSW + client_id filter)")

    cur.close()
    conn.close()
    print("\nMigration complete. Run python rag.py to embed all calls into PostgreSQL.")


if __name__ == "__main__":
    run()
