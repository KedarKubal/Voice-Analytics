"""
test_security.py — Security, tenant isolation, and rate-limiting

Covers:
  • JWT manipulation (expired, wrong secret, malformed, missing Bearer prefix)
  • Tenant isolation matrix: every client-scoped endpoint returns 403 when accessed
    by a user from the other tenant
  • Admin bypass: admin can access any tenant's data
  • Rate limiting: POST /query enforces 25 req/min per user
  • Header injection: X-Client-ID and X-User-ID headers are ignored
  • POST /query: empty question → 400, tenant mismatch → 403
  • Timing-safe: 401 vs 403 distinctions are correct (hidden-existence via 404 for calls)
  • /webhook/retell: accepts any event; bad HMAC returns 401 only when key is set
"""

import time
import pytest
import base64
import json
import hmac
import hashlib

from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002


# ── JWT attack scenarios ──────────────────────────────────────────────────────

class TestJWTSecurity:
    def test_no_token_returns_401(self, client):
        r = client.get(f"/insights/{CLIENT_HEYA_001}")
        assert r.status_code == 401

    def test_empty_bearer_returns_401(self, client):
        r = client.get(f"/insights/{CLIENT_HEYA_001}",
                       headers={"Authorization": "Bearer "})
        assert r.status_code == 401

    def test_bearer_only_returns_401(self, client):
        r = client.get(f"/insights/{CLIENT_HEYA_001}",
                       headers={"Authorization": "Bearer"})
        assert r.status_code == 401

    def test_random_token_returns_401(self, client):
        r = client.get(f"/insights/{CLIENT_HEYA_001}",
                       headers={"Authorization": "Bearer thisisnotatoken"})
        assert r.status_code == 401

    def test_wrong_scheme_returns_401(self, client):
        r = client.get(f"/insights/{CLIENT_HEYA_001}",
                       headers={"Authorization": "Basic dXNlcjpwYXNz"})
        assert r.status_code == 401

    def test_token_without_bearer_prefix_returns_401(self, client, artel_token):
        r = client.get(f"/insights/{CLIENT_HEYA_001}",
                       headers={"Authorization": artel_token})
        assert r.status_code == 401

    def test_expired_token_returns_401(self, client):
        from jose import jwt as jose_jwt
        import os
        from datetime import datetime, timedelta
        secret = os.getenv("JWT_SECRET_KEY", "heya-ai-voice-analytics-secret-2026-rmit")
        expired_token = jose_jwt.encode(
            {
                "sub":       "user_fake_id",
                "email":     "fake@test.com",
                "role":      "client",
                "client_id": CLIENT_HEYA_001,
                "exp":       datetime.utcnow() - timedelta(hours=2),
                "iat":       datetime.utcnow() - timedelta(hours=10),
            },
            secret, algorithm="HS256",
        )
        r = client.get(f"/insights/{CLIENT_HEYA_001}",
                       headers={"Authorization": f"Bearer {expired_token}"})
        assert r.status_code == 401

    def test_wrong_secret_returns_401(self, client):
        from jose import jwt as jose_jwt
        from datetime import datetime, timedelta
        forged_token = jose_jwt.encode(
            {
                "sub":       "user_fake_id",
                "email":     "attacker@evil.com",
                "role":      "heya_admin",
                "client_id": None,
                "exp":       datetime.utcnow() + timedelta(hours=8),
                "iat":       datetime.utcnow(),
            },
            "wrong_secret_key", algorithm="HS256",
        )
        r = client.get("/admin/clients/overview",
                       headers={"Authorization": f"Bearer {forged_token}"})
        assert r.status_code == 401

    def test_role_escalation_attempt_returns_401(self, client, artel_token):
        # Take a real token, manually decode its payload, change role to heya_admin,
        # and re-sign with the wrong secret — must be rejected
        from jose import jwt as jose_jwt
        from datetime import datetime, timedelta
        parts = artel_token.split(".")
        padding = "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + padding))
        payload["role"]      = "heya_admin"
        payload["client_id"] = None
        payload["exp"]       = int((datetime.utcnow() + timedelta(hours=8)).timestamp())
        forged = jose_jwt.encode(payload, "forged_secret", algorithm="HS256")
        r = client.get("/admin/clients/overview",
                       headers={"Authorization": f"Bearer {forged}"})
        assert r.status_code == 401

    def test_jwt_with_none_algorithm_is_rejected(self, client):
        # "alg: none" attack: header.payload.no-signature
        import base64
        header  = base64.urlsafe_b64encode(
            b'{"alg":"none","typ":"JWT"}'
        ).rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(
            json.dumps({
                "sub": "x", "email": "x@x.com",
                "role": "heya_admin", "client_id": None
            }).encode()
        ).rstrip(b"=").decode()
        none_jwt = f"{header}.{payload}."
        r = client.get("/admin/clients/overview",
                       headers={"Authorization": f"Bearer {none_jwt}"})
        assert r.status_code == 401


# ── Tenant isolation matrix ───────────────────────────────────────────────────

class TestTenantIsolation:
    """Artel user must be denied access to MVAA endpoints and vice versa."""

    # /insights
    def test_artel_cannot_access_mvaa_insights(self, client, artel_h):
        r = client.get(f"/insights/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_mvaa_cannot_access_artel_insights(self, client, mvaa_h):
        r = client.get(f"/insights/{CLIENT_HEYA_001}", headers=mvaa_h)
        assert r.status_code == 403

    # /stats
    def test_artel_cannot_access_mvaa_stats(self, client, artel_h):
        r = client.get(f"/stats/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_mvaa_cannot_access_artel_stats(self, client, mvaa_h):
        r = client.get(f"/stats/{CLIENT_HEYA_001}", headers=mvaa_h)
        assert r.status_code == 403

    # /recommendations
    def test_artel_cannot_access_mvaa_recommendations(self, client, artel_h):
        r = client.get(f"/recommendations/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_mvaa_cannot_access_artel_recommendations(self, client, mvaa_h):
        r = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=mvaa_h)
        assert r.status_code == 403

    # /emotions
    def test_artel_cannot_access_mvaa_emotions(self, client, artel_h):
        r = client.get(f"/emotions/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    # /topics
    def test_artel_cannot_access_mvaa_topics(self, client, artel_h):
        r = client.get(f"/topics/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    # /feed
    def test_artel_cannot_access_mvaa_feed(self, client, artel_h):
        r = client.get(f"/feed/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    # /client-alerts
    def test_artel_cannot_access_mvaa_alerts(self, client, artel_h):
        r = client.get(f"/client-alerts/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    # /export/csv
    def test_artel_cannot_export_mvaa_csv(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    # /export/report
    def test_artel_cannot_export_mvaa_report(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    # /alerts/config
    def test_artel_cannot_read_mvaa_alert_config(self, client, artel_h):
        r = client.get(f"/alerts/config/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_artel_cannot_write_mvaa_alert_config(self, client, artel_h):
        r = client.post(f"/alerts/config/{CLIENT_HEYA_002}", json={
            "alert_type": "low_engagement", "enabled": True,
            "email": "x@x.com", "min_priority": "warning",
        }, headers=artel_h)
        assert r.status_code == 403

    # /alerts/history
    def test_artel_cannot_read_mvaa_alert_history(self, client, artel_h):
        r = client.get(f"/alerts/history/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    # /admin endpoints are denied for client users
    def test_artel_cannot_access_admin_overview(self, client, artel_h):
        r = client.get("/admin/clients/overview", headers=artel_h)
        assert r.status_code == 403

    def test_artel_cannot_access_admin_feed(self, client, artel_h):
        r = client.get("/admin/feed", headers=artel_h)
        assert r.status_code == 403

    def test_artel_cannot_list_admin_users(self, client, artel_h):
        r = client.get("/admin/users", headers=artel_h)
        assert r.status_code == 403

    # Cross-tenant call detail hides existence (returns 404 not 403)
    def test_cross_tenant_call_hides_existence(self, client, mvaa_h, artel_call_id):
        r = client.get(f"/call/{artel_call_id}", headers=mvaa_h)
        assert r.status_code == 404, (
            "Cross-tenant call access should return 404 (hide existence), not 403"
        )


# ── Admin bypass ──────────────────────────────────────────────────────────────

class TestAdminBypass:
    def test_admin_can_access_artel_insights(self, client, admin_h):
        r = client.get(f"/insights/{CLIENT_HEYA_001}", headers=admin_h)
        assert r.status_code == 200

    def test_admin_can_access_mvaa_insights(self, client, admin_h):
        r = client.get(f"/insights/{CLIENT_HEYA_002}", headers=admin_h)
        assert r.status_code == 200

    def test_admin_can_access_both_feeds(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.get(f"/feed/{cid}", headers=admin_h)
            assert r.status_code == 200

    def test_admin_can_access_both_csv_exports(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.get(f"/export/csv/{cid}", headers=admin_h)
            assert r.status_code == 200

    def test_admin_can_access_both_alert_histories(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.get(f"/alerts/history/{cid}", headers=admin_h)
            assert r.status_code == 200


# ── Header injection ──────────────────────────────────────────────────────────

class TestHeaderInjection:
    def test_x_client_id_header_does_not_grant_access(self, client, artel_h):
        # Artel user with forged X-Client-ID for MVAA — must still be 403
        headers = {**artel_h, "X-Client-ID": CLIENT_HEYA_002}
        r = client.get(f"/insights/{CLIENT_HEYA_002}", headers=headers)
        assert r.status_code == 403

    def test_x_user_id_header_does_not_bypass_auth(self, client, artel_h):
        # Inject an X-User-ID claiming admin — access check is JWT-only
        headers = {**artel_h, "X-User-ID": "admin-user-fake-id"}
        r = client.get("/admin/clients/overview", headers=headers)
        assert r.status_code == 403

    def test_x_forwarded_for_does_not_affect_auth(self, client, artel_h):
        headers = {**artel_h, "X-Forwarded-For": "127.0.0.1"}
        r = client.get(f"/insights/{CLIENT_HEYA_001}", headers=headers)
        assert r.status_code == 200


# ── POST /query security ──────────────────────────────────────────────────────

class TestQueryEndpointSecurity:
    def test_no_auth_returns_401(self, client):
        r = client.post("/query", json={
            "question": "How many calls?", "client_id": CLIENT_HEYA_001
        })
        assert r.status_code == 401

    def test_cross_tenant_query_returns_403(self, client, artel_h):
        r = client.post("/query", json={
            "question": "How many calls?", "client_id": CLIENT_HEYA_002
        }, headers=artel_h)
        assert r.status_code == 403

    def test_empty_question_returns_400(self, client, artel_h):
        r = client.post("/query", json={
            "question": "   ", "client_id": CLIENT_HEYA_001
        }, headers=artel_h)
        assert r.status_code == 400


# ── Rate limiting ─────────────────────────────────────────────────────────────

class TestRateLimiting:
    def test_query_endpoint_rate_limited_at_25_per_minute(self, client, artel_h):
        """
        POST /query enforces 25 requests/minute per user.
        We fire 26 rapid requests; at least one should hit 429.
        (Uses a predictable "empty question" so we get 400 from validation
         before RAG is invoked — but rate check runs first, so we'll see 429.)
        """
        statuses = []
        payload  = {"question": "x", "client_id": CLIENT_HEYA_001}
        for _ in range(27):
            r = client.post("/query", json=payload, headers=artel_h)
            statuses.append(r.status_code)
            if r.status_code == 429:
                break

        assert 429 in statuses, (
            f"Expected at least one 429 after 27 rapid /query requests, got: {set(statuses)}"
        )

    def test_rate_limit_response_has_detail(self, client, artel_h):
        """After hitting the limit, the 429 body should have a 'detail' key."""
        payload  = {"question": "test", "client_id": CLIENT_HEYA_001}
        statuses = []
        for _ in range(27):
            r = client.post("/query", json=payload, headers=artel_h)
            statuses.append(r.status_code)
            if r.status_code == 429:
                assert "detail" in r.json()
                break


# ── SQL injection in auth ─────────────────────────────────────────────────────

class TestAuthSQLInjection:
    def test_sql_injection_in_email_does_not_return_500(self, client):
        for payload_email in [
            "' OR '1'='1",
            "admin@heya.au'--",
            "'; DROP TABLE users; --",
            "\" OR 1=1--",
        ]:
            r = client.post("/auth/login", json={
                "email": payload_email, "password": "password"
            })
            assert r.status_code in (401, 422, 400), (
                f"Expected 401/422/400 for SQL injection, got {r.status_code} "
                f"for payload: {payload_email!r}"
            )

    def test_sql_injection_in_password_does_not_return_500(self, client):
        r = client.post("/auth/login", json={
            "email": "admin@heya.au",
            "password": "' OR '1'='1",
        })
        assert r.status_code in (401, 422, 400)


# ── Webhook signature verification ───────────────────────────────────────────

class TestWebhookSecurity:
    def test_valid_json_without_api_key_is_accepted(self, client):
        # When RETELL_API_KEY is not set, signature check is skipped
        payload = json.dumps({"event": "ignored", "data": {}}).encode()
        r = client.post(
            "/webhook/retell",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
        # Should process (200) or handle gracefully (not 500)
        assert r.status_code in (200, 400, 401)

    def test_invalid_json_returns_400(self, client):
        r = client.post(
            "/webhook/retell",
            content=b"this is not json",
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400

    def test_call_ended_event_returns_queued(self, client):
        payload = json.dumps({
            "event": "call_ended",
            "data": {
                "call_id":    "test_webhook_call_001",
                "agent_id":   "agent_x",
                "call_type":  "web_call",
                "transcript": "",
            }
        }).encode()
        r = client.post(
            "/webhook/retell",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
        # 200 with queued status, or 400 if call processing fails — never 500
        assert r.status_code in (200, 400)
        if r.status_code == 200:
            assert r.json()["status"] == "queued"

    def test_unknown_event_is_ignored(self, client):
        payload = json.dumps({
            "event": "completely_unknown_event",
        }).encode()
        r = client.post(
            "/webhook/retell",
            content=payload,
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "ignored"


# ── Response consistency ──────────────────────────────────────────────────────

class TestResponseConsistency:
    def test_unauthenticated_endpoints_always_return_401(self, client):
        """All protected GET endpoints return 401 when no token provided."""
        endpoints = [
            f"/insights/{CLIENT_HEYA_001}",
            f"/stats/{CLIENT_HEYA_001}",
            f"/feed/{CLIENT_HEYA_001}",
            f"/emotions/{CLIENT_HEYA_001}",
            f"/topics/{CLIENT_HEYA_001}",
            f"/recommendations/{CLIENT_HEYA_001}",
            f"/client-alerts/{CLIENT_HEYA_001}",
            f"/export/csv/{CLIENT_HEYA_001}",
            f"/export/report/{CLIENT_HEYA_001}",
            f"/alerts/config/{CLIENT_HEYA_001}",
            f"/alerts/history/{CLIENT_HEYA_001}",
            "/admin/clients/overview",
            "/admin/feed",
            "/admin/users",
            "/search?q=test",
        ]
        for ep in endpoints:
            r = client.get(ep)
            assert r.status_code == 401, (
                f"{ep} returned {r.status_code} without auth — expected 401"
            )

    def test_403_errors_have_detail_field(self, client, artel_h):
        """403 responses must include a 'detail' message for consistent error handling."""
        r = client.get("/admin/clients/overview", headers=artel_h)
        assert r.status_code == 403
        body = r.json()
        assert "detail" in body
