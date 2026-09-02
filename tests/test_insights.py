"""
test_insights.py — GET /insights/{client_id}

Covers:
  • 200 + correct structure for own client data
  • Each insight record has all required audio fields
  • Admin can access any client
  • Client can only access own data (403 on foreign client_id)
  • Missing auth → 401
  • Nonexistent client_id → returns empty list (not 404)
"""

import pytest
from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002


class TestInsightsHappyPath:
    def test_artel_client_gets_200(self, client, artel_h):
        r = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_response_contains_top_level_fields(self, client, artel_h):
        data = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "client_id"   in data
        assert "total_calls" in data
        assert "insights"    in data
        assert data["client_id"] == CLIENT_HEYA_001

    def test_total_calls_matches_insights_length(self, client, artel_h):
        data = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["total_calls"] == len(data["insights"])

    def test_has_at_least_one_insight(self, client, artel_h):
        data = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert len(data["insights"]) > 0

    def test_mvaa_client_gets_own_data(self, client, mvaa_h):
        data = client.get(f"/insights/{CLIENT_HEYA_002}", headers=mvaa_h).json()
        assert data["client_id"] == CLIENT_HEYA_002

    def test_admin_can_access_any_client(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.get(f"/insights/{cid}", headers=admin_h)
            assert r.status_code == 200


class TestInsightRecordShape:
    """Each insight dict must have every audio analytics field the frontend uses."""

    REQUIRED_FIELDS = [
        "call_id", "engagement_score", "silence_ratio",
        "interruption_count", "hesitation_count",
        "conversation_flow", "sentiment_trajectory",
        "dominant_emotion", "call_successful",
        "agent_talk_time_sec", "customer_talk_time_sec",
        "total_turns", "quality_score", "quality_grade",
    ]

    def test_insight_has_all_required_fields(self, client, artel_h):
        data = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h).json()
        sample = data["insights"][0]
        for field in self.REQUIRED_FIELDS:
            assert field in sample, f"Missing field: {field}"

    def test_engagement_score_is_numeric(self, client, artel_h):
        data = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h).json()
        for r in data["insights"]:
            if r["engagement_score"] is not None:
                assert isinstance(r["engagement_score"], (int, float))

    def test_silence_ratio_between_0_and_1(self, client, artel_h):
        data = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h).json()
        for r in data["insights"]:
            if r["silence_ratio"] is not None:
                assert 0.0 <= r["silence_ratio"] <= 1.0, (
                    f"silence_ratio out of range: {r['silence_ratio']}"
                )

    def test_quality_grade_is_valid(self, client, artel_h):
        data = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h).json()
        valid_grades = {"A", "B", "C", "D", "F", None}
        for r in data["insights"]:
            assert r["quality_grade"] in valid_grades

    def test_engagement_score_not_nan_or_inf(self, client, artel_h):
        import math
        data = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h).json()
        for r in data["insights"]:
            eng = r.get("engagement_score")
            if eng is not None:
                assert not math.isnan(eng) and not math.isinf(eng)

    def test_response_is_json_serialisable(self, client, artel_h):
        import json
        data = client.get(f"/insights/{CLIENT_HEYA_001}", headers=artel_h).json()
        # Must not raise
        json.dumps(data)


class TestInsightsAuthorisation:
    def test_no_auth_returns_401(self, client):
        r = client.get(f"/insights/{CLIENT_HEYA_001}")
        assert r.status_code == 401

    def test_cross_tenant_access_returns_403(self, client, artel_h):
        # Artel user tries to access MVAA data
        r = client.get(f"/insights/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_reverse_cross_tenant_access_returns_403(self, client, mvaa_h):
        r = client.get(f"/insights/{CLIENT_HEYA_001}", headers=mvaa_h)
        assert r.status_code == 403

    def test_nonexistent_client_returns_empty_not_404(self, client, admin_h):
        r = client.get("/insights/client_does_not_exist", headers=admin_h)
        assert r.status_code == 200
        assert r.json()["total_calls"] == 0
