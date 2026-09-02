"""
test_recommendations.py — GET /recommendations/{client_id} and /client-alerts/{client_id}

Covers:
  • Response shape: id, priority, title, insight, action, metric, affected_calls, trend
  • Priority values are within the valid set
  • Trend values are within the valid set
  • Recommendations are sorted by priority (critical first)
  • Cross-tenant isolation
  • /client-alerts response shape
"""

import pytest
from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002

VALID_PRIORITIES = {"critical", "warning", "info"}
VALID_TRENDS     = {"worsening", "stable", "improving"}


class TestRecommendations:
    def test_returns_200(self, client, artel_h):
        r = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_response_shape(self, client, artel_h):
        data = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "client_id"       in data
        assert "count"           in data
        assert "recommendations" in data
        assert data["client_id"] == CLIENT_HEYA_001

    def test_count_matches_list_length(self, client, artel_h):
        data = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["count"] == len(data["recommendations"])

    def test_each_rec_has_required_fields(self, client, artel_h):
        data = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h).json()
        required = ["id", "priority", "title", "insight", "action", "metric", "affected_calls", "trend"]
        for rec in data["recommendations"]:
            for field in required:
                assert field in rec, f"Missing field '{field}' in recommendation"

    def test_priority_values_are_valid(self, client, artel_h):
        data = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h).json()
        for rec in data["recommendations"]:
            assert rec["priority"] in VALID_PRIORITIES, f"Invalid priority: {rec['priority']}"

    def test_trend_values_are_valid(self, client, artel_h):
        data = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h).json()
        for rec in data["recommendations"]:
            assert rec["trend"] in VALID_TRENDS, f"Invalid trend: {rec['trend']}"

    def test_affected_calls_is_non_negative_int(self, client, artel_h):
        data = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h).json()
        for rec in data["recommendations"]:
            assert isinstance(rec["affected_calls"], int)
            assert rec["affected_calls"] >= 0

    def test_ids_are_unique(self, client, artel_h):
        data = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h).json()
        ids = [r["id"] for r in data["recommendations"]]
        assert len(ids) == len(set(ids)), "Duplicate recommendation IDs"

    def test_critical_recs_appear_before_info(self, client, artel_h):
        recs = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h).json()["recommendations"]
        priority_order = {"critical": 0, "warning": 1, "info": 2}
        priorities = [priority_order[r["priority"]] for r in recs]
        assert priorities == sorted(priorities), "Recommendations not sorted by priority"

    def test_no_auth_returns_401(self, client):
        r = client.get(f"/recommendations/{CLIENT_HEYA_001}")
        assert r.status_code == 401

    def test_cross_tenant_returns_403(self, client, artel_h):
        r = client.get(f"/recommendations/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_admin_can_access_any_client(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.get(f"/recommendations/{cid}", headers=admin_h)
            assert r.status_code == 200

    def test_title_and_insight_are_non_empty(self, client, artel_h):
        data = client.get(f"/recommendations/{CLIENT_HEYA_001}", headers=artel_h).json()
        for rec in data["recommendations"]:
            assert len(rec["title"].strip())   > 0, "Empty title"
            assert len(rec["insight"].strip()) > 0, "Empty insight"
            assert len(rec["action"].strip())  > 0, "Empty action"


class TestClientAlerts:
    def test_returns_200(self, client, artel_h):
        r = client.get(f"/client-alerts/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_response_shape(self, client, artel_h):
        data = client.get(f"/client-alerts/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "client_id" in data
        assert "count"     in data
        assert "alerts"    in data

    def test_count_matches_alerts_length(self, client, artel_h):
        data = client.get(f"/client-alerts/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["count"] == len(data["alerts"])

    def test_cross_tenant_returns_403(self, client, artel_h):
        r = client.get(f"/client-alerts/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403
