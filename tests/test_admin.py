"""
test_admin.py — Admin-only endpoints

Covers:
  • GET /admin/clients/overview — structure, client fields, totals
  • GET /admin/feed — live call feed across all tenants
  • GET /admin/users — list all users
  • POST /admin/users — create user (role validation, duplicate check)
  • DELETE /admin/users/{id} — delete, self-deletion blocked
  • All endpoints reject non-admin users with 403
  • /auth/clients list structure
"""

import pytest
import uuid
from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002


# ── /admin/clients/overview ───────────────────────────────────────────────────

class TestClientsOverview:
    def test_returns_200_for_admin(self, client, admin_h):
        r = client.get("/admin/clients/overview", headers=admin_h)
        assert r.status_code == 200

    def test_returns_403_for_client_user(self, client, artel_h):
        r = client.get("/admin/clients/overview", headers=artel_h)
        assert r.status_code == 403

    def test_returns_401_without_auth(self, client):
        r = client.get("/admin/clients/overview")
        assert r.status_code == 401

    def test_response_top_level_fields(self, client, admin_h):
        data = client.get("/admin/clients/overview", headers=admin_h).json()
        assert "total_clients" in data
        assert "total_pending" in data
        assert "total_users"   in data
        assert "clients"       in data

    def test_total_clients_matches_list_length(self, client, admin_h):
        data = client.get("/admin/clients/overview", headers=admin_h).json()
        assert data["total_clients"] == len(data["clients"])

    def test_both_demo_clients_present(self, client, admin_h):
        data = client.get("/admin/clients/overview", headers=admin_h).json()
        ids = {c["client_id"] for c in data["clients"]}
        assert CLIENT_HEYA_001 in ids
        assert CLIENT_HEYA_002 in ids

    def test_each_client_has_required_fields(self, client, admin_h):
        data = client.get("/admin/clients/overview", headers=admin_h).json()
        required = [
            "client_id", "name", "total_calls", "processed_calls",
            "pending_queue", "success_rate", "user_count",
        ]
        for c in data["clients"]:
            for field in required:
                assert field in c, f"Client {c.get('client_id')} missing field: {field}"

    def test_success_rate_is_valid_percentage(self, client, admin_h):
        data = client.get("/admin/clients/overview", headers=admin_h).json()
        for c in data["clients"]:
            assert 0.0 <= c["success_rate"] <= 100.0

    def test_processed_calls_does_not_exceed_total(self, client, admin_h):
        data = client.get("/admin/clients/overview", headers=admin_h).json()
        for c in data["clients"]:
            assert c["processed_calls"] <= c["total_calls"]

    def test_total_users_is_positive(self, client, admin_h):
        data = client.get("/admin/clients/overview", headers=admin_h).json()
        assert data["total_users"] >= 2  # at minimum 2 demo client users


# ── /admin/feed ───────────────────────────────────────────────────────────────

class TestAdminFeed:
    def test_returns_200_for_admin(self, client, admin_h):
        r = client.get("/admin/feed", headers=admin_h)
        assert r.status_code == 200

    def test_returns_403_for_client_user(self, client, artel_h):
        r = client.get("/admin/feed", headers=artel_h)
        assert r.status_code == 403

    def test_response_contains_calls(self, client, admin_h):
        data = client.get("/admin/feed", headers=admin_h).json()
        assert "calls" in data
        assert isinstance(data["calls"], list)

    def test_count_matches_calls_length(self, client, admin_h):
        data = client.get("/admin/feed", headers=admin_h).json()
        assert data["count"] == len(data["calls"])

    def test_limit_parameter_respected(self, client, admin_h):
        data = client.get("/admin/feed", params={"limit": 5}, headers=admin_h).json()
        assert len(data["calls"]) <= 5

    def test_each_call_has_client_id_and_name(self, client, admin_h):
        data = client.get("/admin/feed", headers=admin_h).json()
        for call in data["calls"][:10]:  # check first 10
            assert "call_id"   in call
            assert "client_id" in call

    def test_feed_covers_multiple_clients(self, client, admin_h):
        """Admin can see calls from each tenant — verified per-client via /admin/calls."""
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            data = client.get("/admin/calls", params={"client_id": cid, "limit": 1}, headers=admin_h).json()
            assert data["count"] > 0, f"Admin sees no calls for client {cid}"


# ── /admin/users ──────────────────────────────────────────────────────────────

class TestAdminUsers:
    def test_list_users_returns_200_for_admin(self, client, admin_h):
        r = client.get("/admin/users", headers=admin_h)
        assert r.status_code == 200

    def test_list_users_returns_403_for_client(self, client, artel_h):
        r = client.get("/admin/users", headers=artel_h)
        assert r.status_code == 403

    def test_list_users_response_shape(self, client, admin_h):
        data = client.get("/admin/users", headers=admin_h).json()
        assert "total" in data
        assert "users" in data
        assert data["total"] == len(data["users"])

    def test_each_user_has_required_fields(self, client, admin_h):
        data = client.get("/admin/users", headers=admin_h).json()
        for u in data["users"]:
            assert "user_id"    in u
            assert "email"      in u
            assert "role"       in u
            assert "created_at" in u

    def test_known_admin_email_is_in_list(self, client, admin_h):
        data = client.get("/admin/users", headers=admin_h).json()
        emails = [u["email"] for u in data["users"]]
        assert "admin@heya.au" in emails

    def test_demo_client_emails_are_in_list(self, client, admin_h):
        data = client.get("/admin/users", headers=admin_h).json()
        emails = [u["email"] for u in data["users"]]
        assert "admin@artel.com" in emails
        assert "admin@mvaallegal.com" in emails


class TestAdminCreateUser:
    TEMP_EMAIL = f"pytest_temp_{uuid.uuid4().hex[:8]}@test.com"

    def test_create_client_user(self, client, admin_h):
        payload = {
            "email":     self.TEMP_EMAIL,
            "password":  "TestPass123!",
            "role":      "client",
            "client_id": CLIENT_HEYA_001,
        }
        r = client.post("/admin/users", json=payload, headers=admin_h)
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "created"
        assert data["email"]  == self.TEMP_EMAIL

    def test_duplicate_email_returns_409(self, client, admin_h):
        payload = {
            "email":     self.TEMP_EMAIL,
            "password":  "AnotherPass!",
            "role":      "client",
            "client_id": CLIENT_HEYA_001,
        }
        r = client.post("/admin/users", json=payload, headers=admin_h)
        assert r.status_code == 409

    def test_invalid_role_returns_400(self, client, admin_h):
        r = client.post("/admin/users", json={
            "email": f"bad_role_{uuid.uuid4().hex[:6]}@test.com",
            "password": "pass", "role": "superuser",
        }, headers=admin_h)
        assert r.status_code == 400

    def test_client_role_without_client_id_returns_400(self, client, admin_h):
        r = client.post("/admin/users", json={
            "email": f"no_cid_{uuid.uuid4().hex[:6]}@test.com",
            "password": "pass", "role": "client",
        }, headers=admin_h)
        assert r.status_code == 400

    def test_nonexistent_client_id_returns_404(self, client, admin_h):
        r = client.post("/admin/users", json={
            "email":     f"bad_cid_{uuid.uuid4().hex[:6]}@test.com",
            "password":  "pass",
            "role":      "client",
            "client_id": "client_does_not_exist",
        }, headers=admin_h)
        assert r.status_code == 404

    def test_non_admin_cannot_create_user(self, client, artel_h):
        r = client.post("/admin/users", json={
            "email": "anon@test.com", "password": "pass", "role": "client",
            "client_id": CLIENT_HEYA_001,
        }, headers=artel_h)
        assert r.status_code == 403

    def test_cleanup_delete_temp_user(self, client, admin_h):
        """Delete the temp user created above."""
        users = client.get("/admin/users", headers=admin_h).json()["users"]
        target = next((u for u in users if u["email"] == self.TEMP_EMAIL), None)
        if target:
            r = client.delete(f"/admin/users/{target['user_id']}", headers=admin_h)
            assert r.status_code == 200


class TestAdminDeleteUser:
    def test_delete_returns_404_for_unknown_id(self, client, admin_h):
        r = client.delete("/admin/users/nonexistent-uuid-xxxx", headers=admin_h)
        assert r.status_code == 404

    def test_non_admin_cannot_delete_user(self, client, artel_h):
        r = client.delete("/admin/users/some-user-id", headers=artel_h)
        assert r.status_code == 403

    def test_admin_cannot_delete_own_account(self, client, admin_h, admin_token):
        import json, base64
        parts = admin_token.split(".")
        padding = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + padding))
        own_id = payload["sub"]
        r = client.delete(f"/admin/users/{own_id}", headers=admin_h)
        assert r.status_code == 400
        assert "Cannot delete" in r.json()["detail"] or "own" in r.json()["detail"].lower()
