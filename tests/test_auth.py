"""
test_auth.py — Authentication: login, JWT, /auth/me, /auth/clients, header fallback

Covers:
  • Successful login for all three demo accounts
  • Invalid password → 401
  • Non-existent email → 401
  • Missing credentials → 422 (FastAPI schema validation)
  • Token payload integrity (role, client_id, sub)
  • JWT create / decode cycle (unit)
  • Expired token → 401
  • /auth/me returns correct identity
  • /auth/clients admin-only gate
  • x-client-id dev header fallback still works
  • Tampered token is rejected
  • bcrypt hash / verify (unit)
"""

import time
import pytest
from jose import jwt as jose_jwt

from conftest import (
    ADMIN_EMAIL, ADMIN_PASS,
    ARTEL_EMAIL, ARTEL_PASS,
    MVAA_EMAIL,  MVAA_PASS,
    CLIENT_HEYA_001, CLIENT_HEYA_002,
)


# ── Login: happy paths ────────────────────────────────────────────────────────

class TestLoginHappyPath:
    def test_admin_login_returns_200(self, client):
        r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        assert r.status_code == 200

    def test_admin_login_response_shape(self, client):
        r = client.post("/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS})
        data = r.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["role"] == "heya_admin"
        assert data["client_id"] is None       # admin has no client scope
        assert "user_id" in data

    def test_artel_login_returns_client_scope(self, client):
        r = client.post("/auth/login", json={"email": ARTEL_EMAIL, "password": ARTEL_PASS})
        data = r.json()
        assert r.status_code == 200
        assert data["role"] == "client"
        assert data["client_id"] == CLIENT_HEYA_001
        assert data["name"] == "Artel Apartments"

    def test_mvaa_login_returns_client_scope(self, client):
        r = client.post("/auth/login", json={"email": MVAA_EMAIL, "password": MVAA_PASS})
        data = r.json()
        assert r.status_code == 200
        assert data["client_id"] == CLIENT_HEYA_002

    def test_token_is_valid_jwt(self, client):
        r = client.post("/auth/login", json={"email": ARTEL_EMAIL, "password": ARTEL_PASS})
        token = r.json()["access_token"]
        # JWT has 3 dot-separated segments
        assert len(token.split(".")) == 3

    def test_token_payload_contains_expected_claims(self, client):
        r = client.post("/auth/login", json={"email": ARTEL_EMAIL, "password": ARTEL_PASS})
        token = r.json()["access_token"]
        # Decode without verification to inspect claims
        header, payload_b64, sig = token.split(".")
        import base64, json
        padding = "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + padding))
        assert payload["client_id"] == CLIENT_HEYA_001
        assert payload["role"] == "client"
        assert "sub" in payload
        assert "exp" in payload
        assert payload["exp"] > time.time()


# ── Login: error paths ────────────────────────────────────────────────────────

class TestLoginErrors:
    def test_wrong_password_returns_401(self, client):
        r = client.post("/auth/login", json={"email": ARTEL_EMAIL, "password": "wrong_password"})
        assert r.status_code == 401
        assert "Invalid" in r.json()["detail"]

    def test_unknown_email_returns_401(self, client):
        r = client.post("/auth/login", json={"email": "nobody@example.com", "password": "any"})
        assert r.status_code == 401

    def test_empty_password_returns_401(self, client):
        r = client.post("/auth/login", json={"email": ARTEL_EMAIL, "password": ""})
        assert r.status_code == 401

    def test_missing_email_field_returns_422(self, client):
        r = client.post("/auth/login", json={"password": ARTEL_PASS})
        assert r.status_code == 422

    def test_missing_password_field_returns_422(self, client):
        r = client.post("/auth/login", json={"email": ARTEL_EMAIL})
        assert r.status_code == 422

    def test_completely_empty_body_returns_422(self, client):
        r = client.post("/auth/login", json={})
        assert r.status_code == 422

    def test_sql_injection_in_email_field(self, client):
        r = client.post("/auth/login", json={"email": "' OR 1=1 --", "password": "x"})
        # Should be 401 (not found), not 500 (SQLAlchemy parameterises queries)
        assert r.status_code == 401


# ── /auth/me ──────────────────────────────────────────────────────────────────

class TestAuthMe:
    def test_me_returns_correct_admin_identity(self, client, admin_h):
        r = client.get("/auth/me", headers=admin_h)
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "heya_admin"
        assert data["is_admin"] is True
        assert data["client_id"] is None

    def test_me_returns_correct_client_identity(self, client, artel_h):
        r = client.get("/auth/me", headers=artel_h)
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "client"
        assert data["is_admin"] is False
        assert data["client_id"] == CLIENT_HEYA_001

    def test_me_without_token_returns_401(self, client):
        r = client.get("/auth/me")
        assert r.status_code == 401

    def test_me_with_invalid_token_returns_401(self, client):
        r = client.get("/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
        assert r.status_code == 401

    def test_me_with_tampered_token_returns_401(self, client, artel_token):
        # Flip one character in the signature segment
        parts = artel_token.split(".")
        parts[2] = parts[2][:-1] + ("A" if parts[2][-1] != "A" else "B")
        bad_token = ".".join(parts)
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401


# ── /auth/clients ─────────────────────────────────────────────────────────────

class TestAuthClients:
    def test_admin_can_list_clients(self, client, admin_h):
        r = client.get("/auth/clients", headers=admin_h)
        assert r.status_code == 200
        data = r.json()
        assert "clients" in data
        assert data["total_clients"] >= 2
        ids = [c["client_id"] for c in data["clients"]]
        assert CLIENT_HEYA_001 in ids
        assert CLIENT_HEYA_002 in ids

    def test_client_user_cannot_list_clients(self, client, artel_h):
        r = client.get("/auth/clients", headers=artel_h)
        assert r.status_code == 403

    def test_client_list_contains_required_fields(self, client, admin_h):
        r = client.get("/auth/clients", headers=admin_h)
        for c in r.json()["clients"]:
            assert "client_id" in c
            assert "name" in c
            assert "total_calls" in c
            assert "processed_calls" in c
            assert "success_rate" in c


# ── x-client-id dev header fallback ──────────────────────────────────────────

class TestDevHeaderFallback:
    def test_x_client_id_header_grants_access(self, client):
        r = client.get(
            f"/insights/{CLIENT_HEYA_001}",
            headers={"x-client-id": CLIENT_HEYA_001},
        )
        # Should work — dev fallback grants client-scoped access
        assert r.status_code == 200

    def test_x_client_id_header_sets_client_role(self, client):
        r = client.get("/auth/me", headers={"x-client-id": CLIENT_HEYA_001})
        assert r.status_code == 200
        data = r.json()
        assert data["role"] == "client"

    def test_no_auth_at_all_returns_401(self, client):
        r = client.get(f"/insights/{CLIENT_HEYA_001}")
        assert r.status_code == 401


# ── JWT unit tests ────────────────────────────────────────────────────────────

class TestJWTUnit:
    def test_create_and_decode_token(self):
        from auth import create_token, decode_token
        token = create_token("user-123", CLIENT_HEYA_001, "client")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["client_id"] == CLIENT_HEYA_001
        assert payload["role"] == "client"

    def test_admin_token_has_no_client_id(self):
        from auth import create_token, decode_token
        token = create_token("admin-456", None, "heya_admin")
        payload = decode_token(token)
        assert payload["client_id"] is None
        assert payload["role"] == "heya_admin"

    def test_expired_token_raises_401(self, client):
        from datetime import datetime, timedelta
        from auth import SECRET_KEY, ALGORITHM
        expired_payload = {
            "sub": "u1", "client_id": CLIENT_HEYA_001, "role": "client",
            "exp": datetime.utcnow() - timedelta(hours=1),
        }
        expired_token = jose_jwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert r.status_code == 401

    def test_wrong_secret_token_raises_401(self, client):
        from datetime import datetime, timedelta
        payload = {
            "sub": "u1", "client_id": CLIENT_HEYA_001, "role": "client",
            "exp": datetime.utcnow() + timedelta(hours=1),
        }
        bad_token = jose_jwt.encode(payload, "wrong-secret-key", algorithm="HS256")
        r = client.get("/auth/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401


# ── bcrypt unit tests ─────────────────────────────────────────────────────────

class TestBcryptUnit:
    def test_hash_and_verify_correct_password(self):
        from auth import hash_password, verify_password
        h = hash_password("my_secure_pass")
        assert verify_password("my_secure_pass", h) is True

    def test_wrong_password_does_not_verify(self):
        from auth import hash_password, verify_password
        h = hash_password("correct_horse")
        assert verify_password("wrong_horse", h) is False

    def test_hash_is_not_plaintext(self):
        from auth import hash_password
        h = hash_password("secret")
        assert h != "secret"
        assert h.startswith("$2b$")

    def test_two_hashes_of_same_password_differ(self):
        from auth import hash_password
        h1 = hash_password("password")
        h2 = hash_password("password")
        assert h1 != h2   # bcrypt uses unique salts
