"""
conftest.py — Heya AI Voice Analytics test fixtures

Session-scoped fixtures so we only hit the login endpoint once per test run.
All tests share the same TestClient, which starts the real FastAPI app
and connects to the live PostgreSQL database on port 5435.

Accounts (from seed_users.py):
  admin@heya.au        / heya_admin_2026  → role=heya_admin
  admin@artel.com      / artel_2026       → role=client, client_id=client_heya_001
  admin@mvaallegal.com / mvaa_2026        → role=client, client_id=client_heya_002
"""

import os
import sys

# Make backend importable without installing it as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient

from main import app

# ── Credentials ──────────────────────────────────────────────────────────────
ADMIN_EMAIL = "admin@heya.au"
ADMIN_PASS  = "heya_admin_2026"
ARTEL_EMAIL = "admin@artel.com"
ARTEL_PASS  = "artel_2026"
MVAA_EMAIL  = "admin@mvaallegal.com"
MVAA_PASS   = "mvaa_2026"

CLIENT_HEYA_001 = "client_heya_001"   # Artel Apartments
CLIENT_HEYA_002 = "client_heya_002"   # MVAA Legal


# ── Client ───────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def client():
    """Synchronous TestClient wrapping the real FastAPI app + real DB."""
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── Login helpers ─────────────────────────────────────────────────────────────
def _do_login(client, email: str, password: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"Login failed for {email}: {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token(client):
    return _do_login(client, ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="session")
def artel_token(client):
    return _do_login(client, ARTEL_EMAIL, ARTEL_PASS)


@pytest.fixture(scope="session")
def mvaa_token(client):
    return _do_login(client, MVAA_EMAIL, MVAA_PASS)


@pytest.fixture(scope="session")
def admin_h(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="session")
def artel_h(artel_token):
    return {"Authorization": f"Bearer {artel_token}"}


@pytest.fixture(scope="session")
def mvaa_h(mvaa_token):
    return {"Authorization": f"Bearer {mvaa_token}"}


# ── First real call ID ────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def artel_call_id(client, artel_h):
    """Return the first processed call_id for Artel so call-detail tests are stable."""
    r = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h)
    assert r.status_code == 200
    insights = r.json().get("insights", [])
    assert len(insights) > 0, "Artel has no processed calls — seed the database first"
    return insights[0]["call_id"]
