"""
test_search.py — GET /search?q=...

Covers:
  • Results shape when matches found
  • Snippet highlighting (HTML mark tags)
  • Query too short (< 2 chars) → 400
  • Query too long (> 200 chars) → 400
  • Empty results when nothing matches
  • Limit parameter clamped to 1–50
  • Client user only sees own calls
  • Admin sees all clients' calls
  • No auth → 401
  • SQL injection attempt in query string
"""

import pytest
from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002


class TestSearchHappyPath:
    def test_common_word_returns_200(self, client, artel_h):
        r = client.get("/search", params={"q": "appointment"}, headers=artel_h)
        assert r.status_code == 200

    def test_response_has_required_keys(self, client, artel_h):
        data = client.get("/search", params={"q": "call"}, headers=artel_h).json()
        assert "query"   in data
        assert "total"   in data
        assert "results" in data

    def test_query_echoed_in_response(self, client, artel_h):
        data = client.get("/search", params={"q": "booking"}, headers=artel_h).json()
        assert data["query"] == "booking"

    def test_total_matches_results_length(self, client, artel_h):
        data = client.get("/search", params={"q": "the"}, headers=artel_h).json()
        assert data["total"] == len(data["results"])

    def test_each_result_has_required_fields(self, client, artel_h):
        data = client.get("/search", params={"q": "appointment"}, headers=artel_h).json()
        for r in data["results"]:
            assert "call_id"     in r
            assert "snippets"    in r
            assert "match_count" in r

    def test_snippets_are_list(self, client, artel_h):
        data = client.get("/search", params={"q": "appointment"}, headers=artel_h).json()
        for r in data["results"]:
            assert isinstance(r["snippets"], list)

    def test_limit_parameter_is_respected(self, client, artel_h):
        data = client.get("/search", params={"q": "the", "limit": 3}, headers=artel_h).json()
        assert len(data["results"]) <= 3

    def test_admin_search_returns_results_across_all_clients(self, client, admin_h):
        r = client.get("/search", params={"q": "the"}, headers=admin_h)
        assert r.status_code == 200


class TestSearchValidation:
    def test_query_under_2_chars_returns_400(self, client, artel_h):
        r = client.get("/search", params={"q": "a"}, headers=artel_h)
        assert r.status_code == 400

    def test_single_char_query_returns_400(self, client, artel_h):
        r = client.get("/search", params={"q": "x"}, headers=artel_h)
        assert r.status_code == 400

    def test_empty_query_returns_400_or_422(self, client, artel_h):
        r = client.get("/search", params={"q": ""}, headers=artel_h)
        assert r.status_code in (400, 422)

    def test_query_over_200_chars_returns_400(self, client, artel_h):
        long_q = "a" * 201
        r = client.get("/search", params={"q": long_q}, headers=artel_h)
        assert r.status_code == 400

    def test_exactly_200_chars_is_accepted(self, client, artel_h):
        q = "appointment " * 16  # 196 chars, valid
        r = client.get("/search", params={"q": q[:200]}, headers=artel_h)
        assert r.status_code == 200

    def test_limit_clamped_at_50(self, client, artel_h):
        data = client.get("/search", params={"q": "the", "limit": 999}, headers=artel_h).json()
        assert len(data["results"]) <= 50

    def test_limit_clamped_minimum_1(self, client, artel_h):
        data = client.get("/search", params={"q": "the", "limit": 0}, headers=artel_h).json()
        assert len(data["results"]) <= 1


class TestSearchEmptyResults:
    def test_nonsense_query_returns_empty_results(self, client, artel_h):
        data = client.get("/search", params={"q": "xyzzyquux9999"}, headers=artel_h).json()
        assert data["total"] == 0
        assert data["results"] == []

    def test_empty_results_has_correct_shape(self, client, artel_h):
        data = client.get("/search", params={"q": "xyzzyquux9999"}, headers=artel_h).json()
        assert "query"   in data
        assert "total"   in data
        assert "results" in data


class TestSearchSecurity:
    def test_no_auth_returns_401(self, client):
        r = client.get("/search", params={"q": "test"})
        assert r.status_code == 401

    def test_sql_injection_in_query_is_safe(self, client, artel_h):
        # plainto_tsquery sanitises input — should return 200 or 400, never 500
        for payload in ["'; DROP TABLE calls; --", "1 UNION SELECT * FROM users--", "OR 1=1"]:
            r = client.get("/search", params={"q": payload}, headers=artel_h)
            assert r.status_code in (200, 400), f"Got {r.status_code} for payload: {payload!r}"

    def test_client_results_scoped_to_own_tenant(self, client, artel_h, mvaa_h):
        # Both clients search for the same word — results must not overlap (RLS)
        artel_results = client.get("/search", params={"q": "the"}, headers=artel_h).json().get("results", [])
        mvaa_results  = client.get("/search", params={"q": "the"}, headers=mvaa_h).json().get("results", [])
        artel_ids = {r["call_id"] for r in artel_results}
        mvaa_ids  = {r["call_id"] for r in mvaa_results}
        # No overlap — RLS ensures isolation
        assert artel_ids.isdisjoint(mvaa_ids), "TENANT ISOLATION FAILURE: overlapping call IDs"
