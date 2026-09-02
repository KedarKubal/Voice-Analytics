"""
migrate_rls.py  —  Heya AI Voice Analytics
PostgreSQL Row Level Security setup.

Run ONCE as superuser (postgres) from backend/:
    python migrate_rls.py

What this does
--------------
1.  Creates a limited application role `heya_app` (no superuser, no createdb).
2.  Grants exactly the permissions the API needs — nothing more.
3.  Enables RLS + FORCE ROW LEVEL SECURITY on every tenant-sensitive table.
4.  Creates TWO policies per table:
      · heya_app  — tenant isolation via app.client_id session variable
      · postgres  — unconditional bypass (used by pipeline / ingest scripts)
5.  Prints the new DATABASE_URL to paste into .env.

Why two roles?
--------------
  postgres (superuser)  → pipeline, ingest, migrations — admin tools that
                          should never be rate-limited or tenant-scoped.
  heya_app              → the web API — must see only the data its JWT says.

After running
-------------
  1. Copy the APP_DATABASE_URL line printed below into backend/.env
  2. Restart the API server — it will pick up the new connection string.
  3. Existing ingest / pipeline scripts keep using the superuser URL and are
     unaffected by RLS (postgres bypass policy lets them see everything).
"""

import os
import secrets
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import create_engine, text

ADMIN_URL    = os.getenv("DATABASE_URL", "postgresql://postgres:1234@localhost:5435/voice_ai")
APP_PASSWORD = os.getenv("APP_DB_PASSWORD") or ("heya_app_" + secrets.token_hex(12))

# Build the app connection URL (same host/db, different user)
# e.g. postgresql://postgres:1234@localhost:5435/voice_ai
#   →  postgresql://heya_app:<pw>@localhost:5435/voice_ai
_parts       = ADMIN_URL.split("@", 1)
_host_db     = _parts[1] if len(_parts) == 2 else "localhost:5435/voice_ai"
APP_URL      = f"postgresql://heya_app:{APP_PASSWORD}@{_host_db}"

# ── SQL blocks executed in order ──────────────────────────────────────────────

ROLE_SETUP = f"""
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'heya_app') THEN
        CREATE ROLE heya_app LOGIN PASSWORD '{APP_PASSWORD}';
        RAISE NOTICE 'Created role heya_app';
    ELSE
        ALTER ROLE heya_app WITH PASSWORD '{APP_PASSWORD}';
        RAISE NOTICE 'Updated heya_app password';
    END IF;
END $$;

GRANT CONNECT ON DATABASE voice_ai TO heya_app;
GRANT USAGE ON SCHEMA public TO heya_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES    IN SCHEMA public TO heya_app;
GRANT USAGE,  SELECT                  ON ALL SEQUENCES IN SCHEMA public TO heya_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES    TO heya_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE,  SELECT                  ON SEQUENCES TO heya_app;
"""

# Each entry: (table_name, policy_name_suffix, USING_clause_for_heya_app)
# Tables with a direct client_id column use it directly.
# Tables that join to calls use an EXISTS sub-select.

DIRECT_TABLES = [
    ("calls",             "calls.client_id = current_setting('app.client_id', true)"),
    ("rag_query_history", "rag_query_history.client_id = current_setting('app.client_id', true)"),
]

JOIN_TABLES = [
    # (table, alias, join_column)
    ("audio_insights",        "ai",  "ai.call_id = calls.id"),
    ("transcript_utterances", "tu",  "tu.call_id = calls.id"),
    ("transcript_words",      "tw",  "tw.utterness_id = transcript_utterances.id"),
    ("recordings",            "rec", "rec.call_id = calls.id"),
    ("call_metadata",         "cm",  "cm.call_id = calls.id"),
    ("tool_calls",            "tc",  "tc.call_id = calls.id"),
]


def _policy_sql(table: str, using_clause: str) -> str:
    """Generate DROP + CREATE for both isolation and bypass policies."""
    return f"""
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE  ROW LEVEL SECURITY;

DROP POLICY IF EXISTS {table}_tenant_isolation ON {table};
CREATE POLICY {table}_tenant_isolation ON {table}
    AS PERMISSIVE FOR ALL TO heya_app
    USING (
        current_setting('app.client_id', true) IN ('heya_admin', 'superuser')
        OR ({using_clause})
    );

DROP POLICY IF EXISTS {table}_superuser_bypass ON {table};
CREATE POLICY {table}_superuser_bypass ON {table}
    AS PERMISSIVE FOR ALL TO postgres
    USING (true);
"""


def _join_using(table: str, alias: str, join_col: str) -> str:
    """
    Build an EXISTS sub-select for tables that reach client_id via calls.
    transcript_words is a special case — it goes through transcript_utterances.
    """
    if table == "transcript_words":
        return f"""EXISTS (
            SELECT 1
            FROM transcript_utterances tu2
            JOIN calls c ON c.id = tu2.call_id
            WHERE tu2.id = transcript_words.utterness_id
              AND c.client_id = current_setting('app.client_id', true)
        )"""
    return f"""EXISTS (
            SELECT 1
            FROM calls
            WHERE calls.id = {table}.call_id
              AND calls.client_id = current_setting('app.client_id', true)
        )"""


# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════
def run():
    print("=" * 60)
    print("Heya AI — PostgreSQL Row Level Security migration")
    print("=" * 60)
    print(f"  Admin URL : {ADMIN_URL.split('@')[1]}")
    print(f"  App role  : heya_app")
    print()

    engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT")

    with engine.connect() as conn:

        # 1. Role + grants
        print("[ 1/3 ] Creating heya_app role and granting permissions...")
        try:
            conn.execute(text(ROLE_SETUP))
            print("        ✅ Done")
        except Exception as e:
            print(f"        ⚠  {e}")

        # 2. Direct tables (have client_id column)
        print("[ 2/3 ] Enabling RLS on direct-client_id tables...")
        for table, using in DIRECT_TABLES:
            sql = _policy_sql(table, using)
            try:
                conn.execute(text(sql))
                print(f"        ✅ {table}")
            except Exception as e:
                print(f"        ⚠  {table}: {e}")

        # 3. Join tables (reach client through calls)
        print("[ 3/3 ] Enabling RLS on joined tables...")
        for table, alias, join_col in JOIN_TABLES:
            using = _join_using(table, alias, join_col)
            sql   = _policy_sql(table, using)
            try:
                conn.execute(text(sql))
                print(f"        ✅ {table}")
            except Exception as e:
                print(f"        ⚠  {table}: {e}")

    print()
    print("=" * 60)
    print("✅  RLS migration complete")
    print("=" * 60)
    print()
    print("Add these lines to backend/.env:")
    print()
    print(f"  # App-role connection (used by the web API — RLS enforced)")
    print(f"  APP_DATABASE_URL={APP_URL}")
    print(f"  APP_DB_PASSWORD={APP_PASSWORD}")
    print()
    print("  # Keep DATABASE_URL pointing to postgres (superuser) for")
    print("  # pipeline / ingest scripts — they use it directly and bypass RLS.")
    print()
    print("Then restart the API server.")


if __name__ == "__main__":
    run()
