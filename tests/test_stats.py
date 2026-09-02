"""
test_stats.py — GET /stats/{client_id}

Covers:
  • Full response shape validation
  • engagement_benchmark section (62.0 Voice AI baseline)
  • silence_success_correlation section
  • calls_by_hour structure
  • Numeric types and value ranges
  • Admin / client / cross-tenant access
"""

import pytest
from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002


class TestStatsHappyPath:
    def test_artel_stats_returns_200(self, client, artel_h):
        r = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_response_contains_all_top_level_keys(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        required = [
            "client_id", "total_calls", "successful_calls", "success_rate",
            "avg_duration_sec", "audio_processed", "pending_audio",
            "silence_success_correlation", "calls_by_hour",
            "engagement_benchmark",
        ]
        for key in required:
            assert key in data, f"Missing key: {key}"

    def test_client_id_matches_request(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["client_id"] == CLIENT_HEYA_001

    def test_total_calls_is_positive_integer(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert isinstance(data["total_calls"], int)
        assert data["total_calls"] > 0

    def test_success_rate_is_valid_percentage(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        sr = data["success_rate"]
        assert isinstance(sr, (int, float))
        assert 0.0 <= sr <= 100.0

    def test_successful_calls_does_not_exceed_total(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["successful_calls"] <= data["total_calls"]

    def test_avg_duration_is_non_negative(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert data["avg_duration_sec"] >= 0


class TestEngagementBenchmark:
    """engagement_benchmark: client score vs 62.0 Voice AI industry baseline."""

    def test_benchmark_section_present(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "engagement_benchmark" in data

    def test_benchmark_has_required_fields(self, client, artel_h):
        bench = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()["engagement_benchmark"]
        for field in ["client_score", "benchmark_score", "delta", "label", "benchmark_label"]:
            assert field in bench, f"Missing benchmark field: {field}"

    def test_benchmark_score_is_fixed_at_62(self, client, artel_h):
        bench = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()["engagement_benchmark"]
        assert bench["benchmark_score"] == 62.0

    def test_delta_is_client_score_minus_benchmark(self, client, artel_h):
        bench = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()["engagement_benchmark"]
        expected_delta = round(bench["client_score"] - 62.0, 1)
        assert bench["delta"] == pytest.approx(expected_delta, abs=0.2)

    def test_label_says_above_when_delta_positive(self, client, artel_h):
        bench = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()["engagement_benchmark"]
        if bench["delta"] >= 0:
            assert "above" in bench["label"].lower()
        else:
            assert "below" in bench["label"].lower()

    def test_benchmark_label_says_voice_ai(self, client, artel_h):
        bench = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()["engagement_benchmark"]
        assert "Voice AI" in bench["benchmark_label"]

    def test_client_score_is_numeric(self, client, artel_h):
        bench = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()["engagement_benchmark"]
        assert isinstance(bench["client_score"], (int, float))


class TestSilenceSuccessCorrelation:
    """silence_success_correlation: key insight on silence vs call outcomes."""

    def test_section_present(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "silence_success_correlation" in data

    def test_has_required_fields(self, client, artel_h):
        corr = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()["silence_success_correlation"]
        for field in ["high_silence_success_rate", "low_silence_success_rate", "insight"]:
            assert field in corr, f"Missing field: {field}"

    def test_rates_are_valid_percentages(self, client, artel_h):
        corr = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()["silence_success_correlation"]
        for key in ["high_silence_success_rate", "low_silence_success_rate"]:
            rate = corr[key]
            assert 0.0 <= rate <= 100.0, f"{key} out of range: {rate}"

    def test_insight_is_non_empty_string(self, client, artel_h):
        corr = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()["silence_success_correlation"]
        assert isinstance(corr["insight"], str)
        assert len(corr["insight"]) > 5


class TestCallsByHour:
    def test_calls_by_hour_is_a_list(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert isinstance(data["calls_by_hour"], list)

    def test_each_hour_entry_has_required_fields(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        for entry in data["calls_by_hour"]:
            assert "hour"           in entry
            assert "count"          in entry
            assert "avg_engagement" in entry

    def test_hour_values_are_0_to_23(self, client, artel_h):
        data = client.get(f"/stats/{CLIENT_HEYA_001}", headers=artel_h).json()
        for entry in data["calls_by_hour"]:
            assert 0 <= entry["hour"] <= 23


class TestStatsAuthorisation:
    def test_no_auth_returns_401(self, client):
        r = client.get(f"/stats/{CLIENT_HEYA_001}")
        assert r.status_code == 401

    def test_cross_tenant_returns_403(self, client, artel_h):
        r = client.get(f"/stats/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_admin_can_access_any_client_stats(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.get(f"/stats/{cid}", headers=admin_h)
            assert r.status_code == 200
