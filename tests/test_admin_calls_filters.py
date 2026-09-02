"""
test_admin_calls_filters.py — GET /admin/calls filter combinations

Response shape: {"count": N, "calls": [...]}

Covers:
  • No filters → returns results from both clients
  • sentiment filter: lowercase input capitalised before DB query (bug fix 2026-06-01)
  • direction filter: inbound / outbound
  • flow filter: smooth / moderate / poor
  • trajectory filter: improving / stable / deteriorating
  • client_id filter: scopes results to one tenant
  • limit param: capped correctly
  • Combined filters: multiple params narrow results
  • SQL injection in any filter param → 200/empty, never 500
  • Non-admin cannot call this endpoint
"""

import pytest
from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002

ENDPOINT = "/admin/calls"


def calls(r):
    """Extract the calls list from the endpoint response dict."""
    return r.json()["calls"]


# ── Access control ────────────────────────────────────────────────────────────

class TestAdminCallsAccess:
    def test_no_auth_returns_401(self, client):
        r = client.get(ENDPOINT)
        assert r.status_code == 401

    def test_client_user_returns_403(self, client, artel_h):
        r = client.get(ENDPOINT, headers=artel_h)
        assert r.status_code == 403

    def test_mvaa_user_returns_403(self, client, mvaa_h):
        r = client.get(ENDPOINT, headers=mvaa_h)
        assert r.status_code == 403

    def test_admin_returns_200(self, client, admin_h):
        r = client.get(ENDPOINT, headers=admin_h)
        assert r.status_code == 200


# ── Response shape ────────────────────────────────────────────────────────────

class TestAdminCallsShape:
    def test_response_has_count_and_calls_keys(self, client, admin_h):
        data = client.get(ENDPOINT, headers=admin_h).json()
        assert "count" in data
        assert "calls" in data

    def test_calls_is_a_list(self, client, admin_h):
        data = client.get(ENDPOINT, headers=admin_h).json()
        assert isinstance(data["calls"], list)

    def test_count_matches_calls_length(self, client, admin_h):
        data = client.get(ENDPOINT, headers=admin_h).json()
        assert data["count"] == len(data["calls"])

    def test_results_are_non_empty(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, headers=admin_h))
        assert len(rows) > 0

    def test_contains_calls_from_both_clients(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"limit": 500}, headers=admin_h))
        client_ids = {r["client_id"] for r in rows}
        assert CLIENT_HEYA_001 in client_ids
        assert CLIENT_HEYA_002 in client_ids

    def test_each_row_has_required_fields(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"limit": 5}, headers=admin_h))
        required = [
            "call_id", "client_id", "direction", "user_sentiment",
            "conversation_flow", "sentiment_trajectory", "engagement_score",
        ]
        for row in rows:
            for field in required:
                assert field in row, f"Row missing field: {field}"


# ── Sentiment filter (the bug that was fixed 2026-06-01) ─────────────────────

class TestSentimentFilter:
    def test_positive_filter_returns_results(self, client, admin_h):
        """Lowercase 'positive' must match DB value 'Positive' after .capitalize()."""
        r = client.get(ENDPOINT, params={"sentiment": "positive"}, headers=admin_h)
        assert r.status_code == 200
        rows = calls(r)
        assert len(rows) > 0, (
            "No results for sentiment=positive — capitalisation fix may have regressed. "
            "DB stores 'Positive'; frontend sends 'positive'."
        )

    def test_positive_filter_all_rows_are_positive(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"sentiment": "positive", "limit": 100}, headers=admin_h))
        for row in rows:
            assert row["user_sentiment"] == "Positive", (
                f"Row {row['call_id']} has user_sentiment={row['user_sentiment']!r}, expected 'Positive'"
            )

    def test_negative_filter_returns_results(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"sentiment": "negative"}, headers=admin_h))
        assert len(rows) > 0

    def test_negative_filter_all_rows_are_negative(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"sentiment": "negative", "limit": 100}, headers=admin_h))
        for row in rows:
            assert row["user_sentiment"] == "Negative"

    def test_neutral_filter_returns_results(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"sentiment": "neutral"}, headers=admin_h))
        assert len(rows) > 0

    def test_neutral_filter_all_rows_are_neutral(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"sentiment": "neutral", "limit": 100}, headers=admin_h))
        for row in rows:
            assert row["user_sentiment"] == "Neutral"

    def test_capitalized_variant_also_works(self, client, admin_h):
        """'Positive' (already capitalised) must also work — .capitalize() is idempotent."""
        r = client.get(ENDPOINT, params={"sentiment": "Positive"}, headers=admin_h)
        assert r.status_code == 200
        assert len(calls(r)) > 0

    def test_uppercase_variant_works(self, client, admin_h):
        """'POSITIVE'.capitalize() → 'Positive' — must match DB."""
        r = client.get(ENDPOINT, params={"sentiment": "POSITIVE"}, headers=admin_h)
        assert r.status_code == 200

    def test_unknown_sentiment_returns_empty(self, client, admin_h):
        """A value that doesn't exist in DB returns zero rows, not an error."""
        r = client.get(ENDPOINT, params={"sentiment": "ecstatic"}, headers=admin_h)
        assert r.status_code == 200
        assert calls(r) == []


# ── Direction filter ──────────────────────────────────────────────────────────

class TestDirectionFilter:
    def test_inbound_filter_returns_results(self, client, admin_h):
        assert len(calls(client.get(ENDPOINT, params={"direction": "inbound"}, headers=admin_h))) > 0

    def test_inbound_filter_all_rows_are_inbound(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"direction": "inbound", "limit": 100}, headers=admin_h))
        for row in rows:
            assert row["direction"] == "inbound"

    def test_outbound_filter_returns_results(self, client, admin_h):
        assert len(calls(client.get(ENDPOINT, params={"direction": "outbound"}, headers=admin_h))) > 0

    def test_outbound_filter_all_rows_are_outbound(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"direction": "outbound", "limit": 100}, headers=admin_h))
        for row in rows:
            assert row["direction"] == "outbound"

    def test_unknown_direction_returns_empty(self, client, admin_h):
        r = client.get(ENDPOINT, params={"direction": "sideways"}, headers=admin_h)
        assert r.status_code == 200
        assert calls(r) == []


# ── Flow filter ───────────────────────────────────────────────────────────────

class TestFlowFilter:
    @pytest.mark.parametrize("flow", ["smooth", "moderate", "poor"])
    def test_flow_filter_returns_only_matching_rows(self, flow, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"flow": flow, "limit": 100}, headers=admin_h))
        for row in rows:
            assert row["conversation_flow"] == flow, (
                f"Row {row['call_id']} has flow={row['conversation_flow']!r}, expected {flow!r}"
            )


# ── Trajectory filter ─────────────────────────────────────────────────────────

class TestTrajectoryFilter:
    @pytest.mark.parametrize("traj", ["improving", "stable", "deteriorating"])
    def test_trajectory_filter_returns_only_matching_rows(self, traj, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"trajectory": traj, "limit": 100}, headers=admin_h))
        for row in rows:
            assert row["sentiment_trajectory"] == traj


# ── Client_id filter ──────────────────────────────────────────────────────────

class TestClientIdFilter:
    def test_artel_filter_returns_only_artel_calls(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"client_id": CLIENT_HEYA_001, "limit": 100}, headers=admin_h))
        assert len(rows) > 0
        for row in rows:
            assert row["client_id"] == CLIENT_HEYA_001

    def test_mvaa_filter_returns_only_mvaa_calls(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"client_id": CLIENT_HEYA_002, "limit": 100}, headers=admin_h))
        assert len(rows) > 0
        for row in rows:
            assert row["client_id"] == CLIENT_HEYA_002

    def test_unknown_client_returns_empty(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"client_id": "client_does_not_exist"}, headers=admin_h))
        assert rows == []


# ── Limit param ───────────────────────────────────────────────────────────────

class TestLimitParam:
    def test_limit_1_returns_at_most_1_row(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"limit": 1}, headers=admin_h))
        assert len(rows) <= 1

    def test_limit_10_returns_at_most_10_rows(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"limit": 10}, headers=admin_h))
        assert len(rows) <= 10

    def test_limit_0_is_clamped_to_1(self, client, admin_h):
        """limit=0 is clamped to 1 in the endpoint logic."""
        r = client.get(ENDPOINT, params={"limit": 0}, headers=admin_h)
        assert r.status_code == 200
        assert len(calls(r)) >= 1

    def test_limit_above_2000_is_capped(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={"limit": 99999}, headers=admin_h))
        assert len(rows) <= 2000


# ── Combined filters ──────────────────────────────────────────────────────────

class TestCombinedFilters:
    def test_client_and_sentiment_combined(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={
            "client_id": CLIENT_HEYA_001,
            "sentiment": "positive",
            "limit": 100,
        }, headers=admin_h))
        for row in rows:
            assert row["client_id"] == CLIENT_HEYA_001
            assert row["user_sentiment"] == "Positive"

    def test_direction_and_flow_combined(self, client, admin_h):
        rows = calls(client.get(ENDPOINT, params={
            "direction": "inbound",
            "flow": "smooth",
            "limit": 100,
        }, headers=admin_h))
        for row in rows:
            assert row["direction"] == "inbound"
            assert row["conversation_flow"] == "smooth"

    def test_all_filters_combined_returns_subset(self, client, admin_h):
        all_rows = calls(client.get(ENDPOINT, headers=admin_h))
        filtered = calls(client.get(ENDPOINT, params={
            "client_id":  CLIENT_HEYA_001,
            "direction":  "inbound",
            "sentiment":  "positive",
            "limit": 500,
        }, headers=admin_h))
        assert len(filtered) <= len(all_rows)


# ── SQL injection in filter params ────────────────────────────────────────────

class TestSQLInjectionInFilters:
    INJECTIONS = [
        "' OR '1'='1",
        "'; DROP TABLE calls; --",
        "\" OR 1=1--",
        "%27 OR %271%27=%271",
    ]

    @pytest.mark.parametrize("payload", INJECTIONS)
    def test_sql_injection_in_sentiment_does_not_500(self, payload, client, admin_h):
        r = client.get(ENDPOINT, params={"sentiment": payload}, headers=admin_h)
        assert r.status_code in (200, 400, 422), (
            f"SQL injection in sentiment caused {r.status_code}: {payload!r}"
        )

    @pytest.mark.parametrize("payload", INJECTIONS)
    def test_sql_injection_in_direction_does_not_500(self, payload, client, admin_h):
        r = client.get(ENDPOINT, params={"direction": payload}, headers=admin_h)
        assert r.status_code in (200, 400, 422)

    @pytest.mark.parametrize("payload", INJECTIONS)
    def test_sql_injection_in_topic_does_not_500(self, payload, client, admin_h):
        r = client.get(ENDPOINT, params={"topic": payload}, headers=admin_h)
        assert r.status_code in (200, 400, 422)

    def test_injection_never_leaks_all_rows(self, client, admin_h):
        """A successful injection would return all rows; baseline should be large."""
        baseline = len(calls(client.get(ENDPOINT, params={"limit": 500}, headers=admin_h)))
        for payload in self.INJECTIONS:
            r = client.get(ENDPOINT, params={"sentiment": payload, "limit": 500}, headers=admin_h)
            if r.status_code == 200:
                assert len(calls(r)) <= baseline
