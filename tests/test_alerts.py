"""
test_alerts.py — Alert configuration and notification system

Covers:
  • GET  /alerts/config/{client_id}      — list configs, valid_types, field shapes
  • POST /alerts/config/{client_id}      — upsert: created / updated, invalid types → 400
  • DELETE /alerts/config/{client_id}/{type} — delete existing, 404 for missing
  • GET  /alerts/history/{client_id}     — log shape, limit respected
  • POST /alerts/check/{client_id}       — queued response
  • POST /alerts/digest/{client_id}      — queued response
  • POST /alerts/test/{client_id}        — sent/failed response (SMTP may not be configured)
  • Cross-tenant isolation (403)
  • No auth → 401
  • VALID_ALERT_TYPES completeness
"""

import pytest
from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002

VALID_ALERT_TYPES = {
    "high_silence",
    "poor_conversation_flow",
    "low_success_rate",
    "low_engagement",
    "deteriorating_trajectory",
    "high_interruptions",
    "negative_sentiment",
    "weekly_digest",
}

TEST_ALERT_TYPE = "low_engagement"
TEST_EMAIL      = "pytest_alerts@test.com"


# ── GET /alerts/config/{client_id} ────────────────────────────────────────────

class TestListAlertConfigs:
    def test_returns_200_for_client_user(self, client, artel_h):
        r = client.get(f"/alerts/config/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_returns_200_for_admin(self, client, admin_h):
        r = client.get(f"/alerts/config/{CLIENT_HEYA_001}", headers=admin_h)
        assert r.status_code == 200

    def test_returns_403_for_wrong_tenant(self, client, artel_h):
        r = client.get(f"/alerts/config/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_returns_401_without_auth(self, client):
        r = client.get(f"/alerts/config/{CLIENT_HEYA_001}")
        assert r.status_code == 401

    def test_response_shape(self, client, artel_h):
        data = client.get(f"/alerts/config/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "client_id"   in data
        assert "valid_types" in data
        assert "configs"     in data

    def test_client_id_matches_request(self, client, artel_h):
        data = client.get(f"/alerts/config/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["client_id"] == CLIENT_HEYA_001

    def test_valid_types_contains_all_known_types(self, client, artel_h):
        data  = client.get(f"/alerts/config/{CLIENT_HEYA_001}", headers=artel_h).json()
        returned = set(data["valid_types"])
        assert VALID_ALERT_TYPES.issubset(returned), (
            f"Missing types in valid_types: {VALID_ALERT_TYPES - returned}"
        )

    def test_configs_is_list(self, client, artel_h):
        data = client.get(f"/alerts/config/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert isinstance(data["configs"], list)

    def test_each_config_has_required_fields(self, client, artel_h):
        data = client.get(f"/alerts/config/{CLIENT_HEYA_001}", headers=artel_h).json()
        for cfg in data["configs"]:
            assert "id"             in cfg
            assert "alert_type"     in cfg
            assert "enabled"        in cfg
            assert "email"          in cfg
            assert "min_priority"   in cfg
            assert "created_at"     in cfg

    def test_each_config_alert_type_is_valid(self, client, artel_h):
        data = client.get(f"/alerts/config/{CLIENT_HEYA_001}", headers=artel_h).json()
        for cfg in data["configs"]:
            assert cfg["alert_type"] in VALID_ALERT_TYPES, (
                f"Unexpected alert_type: {cfg['alert_type']}"
            )

    def test_each_config_min_priority_is_valid(self, client, artel_h):
        data = client.get(f"/alerts/config/{CLIENT_HEYA_001}", headers=artel_h).json()
        valid_priorities = {"warning", "critical"}
        for cfg in data["configs"]:
            assert cfg["min_priority"] in valid_priorities, (
                f"Invalid min_priority: {cfg['min_priority']}"
            )


# ── POST /alerts/config/{client_id} ──────────────────────────────────────────

class TestUpsertAlertConfig:
    def test_create_config_returns_201_or_200(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        r = client.post(f"/alerts/config/{CLIENT_HEYA_001}", json=payload, headers=artel_h)
        assert r.status_code in (200, 201)

    def test_create_returns_status_created_or_updated(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        data = client.post(
            f"/alerts/config/{CLIENT_HEYA_001}", json=payload, headers=artel_h
        ).json()
        assert data["status"] in ("created", "updated")

    def test_create_echoes_alert_type(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        data = client.post(
            f"/alerts/config/{CLIENT_HEYA_001}", json=payload, headers=artel_h
        ).json()
        assert data["alert_type"] == TEST_ALERT_TYPE
        assert data["client_id"]  == CLIENT_HEYA_001

    def test_upsert_updates_existing(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      False,
            "email":        "updated@test.com",
            "min_priority": "critical",
        }
        data = client.post(
            f"/alerts/config/{CLIENT_HEYA_001}", json=payload, headers=artel_h
        ).json()
        assert data["status"] == "updated"

    def test_invalid_alert_type_returns_400(self, client, artel_h):
        payload = {
            "alert_type":   "nonexistent_metric",
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        r = client.post(f"/alerts/config/{CLIENT_HEYA_001}", json=payload, headers=artel_h)
        assert r.status_code == 400

    def test_invalid_min_priority_returns_400(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "low",
        }
        r = client.post(f"/alerts/config/{CLIENT_HEYA_001}", json=payload, headers=artel_h)
        assert r.status_code == 400

    def test_cross_tenant_create_returns_403(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        r = client.post(f"/alerts/config/{CLIENT_HEYA_002}", json=payload, headers=artel_h)
        assert r.status_code == 403

    def test_no_auth_returns_401(self, client):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        r = client.post(f"/alerts/config/{CLIENT_HEYA_001}", json=payload)
        assert r.status_code == 401

    def test_all_valid_alert_types_can_be_created(self, client, artel_h):
        for alert_type in VALID_ALERT_TYPES:
            payload = {
                "alert_type":   alert_type,
                "enabled":      True,
                "email":        TEST_EMAIL,
                "min_priority": "warning",
            }
            r = client.post(
                f"/alerts/config/{CLIENT_HEYA_001}", json=payload, headers=artel_h
            )
            assert r.status_code in (200, 201), (
                f"Type '{alert_type}' unexpectedly returned {r.status_code}"
            )

    def test_weekly_digest_can_be_configured(self, client, artel_h):
        payload = {
            "alert_type":   "weekly_digest",
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        r = client.post(f"/alerts/config/{CLIENT_HEYA_001}", json=payload, headers=artel_h)
        assert r.status_code in (200, 201)


# ── DELETE /alerts/config/{client_id}/{type} ─────────────────────────────────

class TestDeleteAlertConfig:
    def test_delete_existing_config_returns_200(self, client, artel_h):
        # Ensure it exists first
        client.post(f"/alerts/config/{CLIENT_HEYA_001}", json={
            "alert_type": TEST_ALERT_TYPE, "enabled": True,
            "email": TEST_EMAIL, "min_priority": "warning",
        }, headers=artel_h)

        r = client.delete(
            f"/alerts/config/{CLIENT_HEYA_001}/{TEST_ALERT_TYPE}", headers=artel_h
        )
        assert r.status_code == 200

    def test_delete_response_has_status_and_type(self, client, artel_h):
        # Re-create so delete has something to work with
        client.post(f"/alerts/config/{CLIENT_HEYA_001}", json={
            "alert_type": "high_silence", "enabled": True,
            "email": TEST_EMAIL, "min_priority": "warning",
        }, headers=artel_h)

        data = client.delete(
            f"/alerts/config/{CLIENT_HEYA_001}/high_silence", headers=artel_h
        ).json()
        assert data["status"]     == "deleted"
        assert data["alert_type"] == "high_silence"

    def test_delete_nonexistent_returns_404(self, client, artel_h):
        r = client.delete(
            f"/alerts/config/{CLIENT_HEYA_001}/type_does_not_exist", headers=artel_h
        )
        assert r.status_code == 404

    def test_delete_cross_tenant_returns_403(self, client, artel_h):
        r = client.delete(
            f"/alerts/config/{CLIENT_HEYA_002}/{TEST_ALERT_TYPE}", headers=artel_h
        )
        assert r.status_code == 403

    def test_delete_no_auth_returns_401(self, client):
        r = client.delete(
            f"/alerts/config/{CLIENT_HEYA_001}/{TEST_ALERT_TYPE}"
        )
        assert r.status_code == 401


# ── GET /alerts/history/{client_id} ──────────────────────────────────────────

class TestAlertHistory:
    def test_returns_200(self, client, artel_h):
        r = client.get(f"/alerts/history/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_returns_403_for_wrong_tenant(self, client, artel_h):
        r = client.get(f"/alerts/history/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_returns_401_without_auth(self, client):
        r = client.get(f"/alerts/history/{CLIENT_HEYA_001}")
        assert r.status_code == 401

    def test_response_shape(self, client, artel_h):
        data = client.get(f"/alerts/history/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "client_id" in data
        assert "logs"      in data
        assert isinstance(data["logs"], list)

    def test_client_id_matches_request(self, client, artel_h):
        data = client.get(f"/alerts/history/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["client_id"] == CLIENT_HEYA_001

    def test_each_log_has_required_fields(self, client, artel_h):
        data = client.get(f"/alerts/history/{CLIENT_HEYA_001}", headers=artel_h).json()
        for log in data["logs"]:
            assert "id"         in log
            assert "alert_type" in log
            assert "subject"    in log
            assert "status"     in log
            assert "sent_at"    in log

    def test_limit_parameter_is_respected(self, client, artel_h):
        data = client.get(
            f"/alerts/history/{CLIENT_HEYA_001}", params={"limit": 5}, headers=artel_h
        ).json()
        assert len(data["logs"]) <= 5

    def test_limit_capped_at_200(self, client, artel_h):
        data = client.get(
            f"/alerts/history/{CLIENT_HEYA_001}", params={"limit": 999}, headers=artel_h
        ).json()
        assert len(data["logs"]) <= 200

    def test_admin_can_access_any_client_history(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.get(f"/alerts/history/{cid}", headers=admin_h)
            assert r.status_code == 200


# ── POST /alerts/check/{client_id} ───────────────────────────────────────────

class TestRunAlertChecks:
    def test_returns_200_for_authorized_user(self, client, artel_h):
        r = client.post(f"/alerts/check/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_response_has_queued_status(self, client, artel_h):
        data = client.post(f"/alerts/check/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["status"] == "queued"

    def test_response_has_message(self, client, artel_h):
        data = client.post(f"/alerts/check/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "message" in data
        assert len(data["message"]) > 0

    def test_cross_tenant_returns_403(self, client, artel_h):
        r = client.post(f"/alerts/check/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_no_auth_returns_401(self, client):
        r = client.post(f"/alerts/check/{CLIENT_HEYA_001}")
        assert r.status_code == 401


# ── POST /alerts/digest/{client_id} ──────────────────────────────────────────

class TestSendDigest:
    def test_returns_200_for_authorized_user(self, client, artel_h):
        r = client.post(f"/alerts/digest/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_response_has_queued_status(self, client, artel_h):
        data = client.post(f"/alerts/digest/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["status"] == "queued"

    def test_cross_tenant_returns_403(self, client, artel_h):
        r = client.post(f"/alerts/digest/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_no_auth_returns_401(self, client):
        r = client.post(f"/alerts/digest/{CLIENT_HEYA_001}")
        assert r.status_code == 401

    def test_admin_can_trigger_digest_for_any_client(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.post(f"/alerts/digest/{cid}", headers=admin_h)
            assert r.status_code == 200


# ── POST /alerts/test/{client_id} ────────────────────────────────────────────

class TestSendTestEmail:
    def test_returns_200_with_sent_or_failed(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        r = client.post(f"/alerts/test/{CLIENT_HEYA_001}", json=payload, headers=artel_h)
        assert r.status_code == 200

    def test_response_has_status_field(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        data = client.post(
            f"/alerts/test/{CLIENT_HEYA_001}", json=payload, headers=artel_h
        ).json()
        assert data["status"] in ("sent", "failed")

    def test_response_has_email_field(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        data = client.post(
            f"/alerts/test/{CLIENT_HEYA_001}", json=payload, headers=artel_h
        ).json()
        assert data["email"] == TEST_EMAIL

    def test_response_has_message_field(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        data = client.post(
            f"/alerts/test/{CLIENT_HEYA_001}", json=payload, headers=artel_h
        ).json()
        assert "message" in data

    def test_cross_tenant_returns_403(self, client, artel_h):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        r = client.post(f"/alerts/test/{CLIENT_HEYA_002}", json=payload, headers=artel_h)
        assert r.status_code == 403

    def test_no_auth_returns_401(self, client):
        payload = {
            "alert_type":   TEST_ALERT_TYPE,
            "enabled":      True,
            "email":        TEST_EMAIL,
            "min_priority": "warning",
        }
        r = client.post(f"/alerts/test/{CLIENT_HEYA_001}", json=payload)
        assert r.status_code == 401
