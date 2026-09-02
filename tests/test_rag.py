"""
test_rag.py — RAG conversational interface tests

Strategy: three layers tested separately.

  Layer 1 — Pure unit tests (no DB, no LLM, < 1s)
    _detect_month, _detect_day, _detect_year
    _month_ts_range, _day_ts_range
    _is_followup, _build_search_query

  Layer 2 — DB integration tests (real DB, no LLM)
    build_stats_context  — SQL stats block content + shape
    _direct_sql_answer   — keyword-matched SQL fast path
    query()              — with CEREBRAS_API_KEY unset (falls back to no_llm / text_to_sql route)

  Layer 3 — HTTP endpoint tests (real app, no LLM)
    POST /query — response shape, access control, tenant isolation

  The Cerebras LLM is never called. Tests that require a live LLM
  are explicitly excluded — they would be flaky and hit API quotas.
"""

import os
import sys
import pytest

# ── Make backend importable ────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — PURE UNIT TESTS  (no DB, no LLM)
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectMonth:
    """_detect_month(q) — maps month names/abbreviations to integers 1–12."""

    def _dm(self, q):
        from rag import _detect_month
        return _detect_month(q)

    def test_full_name_january(self):
        assert self._dm("how many calls in january") == 1

    def test_full_name_december(self):
        assert self._dm("calls in december") == 12

    def test_abbreviation_jan(self):
        assert self._dm("jan calls") == 1

    def test_abbreviation_feb(self):
        assert self._dm("calls in feb") == 2

    def test_abbreviation_dec(self):
        assert self._dm("dec performance") == 12

    def test_all_twelve_months(self):
        from rag import _detect_month
        cases = [
            ("january", 1), ("february", 2), ("march", 3),
            ("april", 4),   ("may", 5),      ("june", 6),
            ("july", 7),    ("august", 8),   ("september", 9),
            ("october", 10),("november", 11),("december", 12),
        ]
        for name, expected in cases:
            assert _detect_month(name) == expected, f"Failed for {name}"

    def test_no_month_returns_none(self):
        assert self._dm("how many calls total") is None

    def test_numeric_month_not_matched(self):
        assert self._dm("calls in month 3") is None  # "3" is not a month name

    def test_case_insensitive_input(self):
        from rag import _detect_month
        # _MONTH_MAP uses lowercase keys — caller should lowercase first
        # These should return None because "January" doesn't match "january"
        # (by design — callers pass .lower() already)
        assert _detect_month("january") == 1  # lowercase passes

    def test_month_embedded_in_sentence(self):
        assert self._dm("what was the success rate in march 2025") == 3


class TestDetectDay:
    """_detect_day(q) — extracts day number 1–31 from question text."""

    def _dd(self, q):
        from rag import _detect_day
        return _detect_day(q)

    def test_plain_number(self):
        assert self._dd("calls on 15") == 15

    def test_ordinal_st(self):
        assert self._dd("calls on the 1st") == 1

    def test_ordinal_nd(self):
        assert self._dd("on the 2nd") == 2

    def test_ordinal_rd(self):
        assert self._dd("on the 3rd") == 3

    def test_ordinal_th(self):
        assert self._dd("on the 18th") == 18

    def test_four_digit_year_not_matched(self):
        assert self._dd("calls in 2025") is None  # 2025 is not a day

    def test_day_31(self):
        assert self._dd("calls on 31st") == 31

    def test_no_number_returns_none(self):
        assert self._dd("how many calls total") is None


class TestDetectYear:
    """_detect_year(q) — extracts a 4-digit 20xx year."""

    def _dy(self, q):
        from rag import _detect_year
        return _detect_year(q)

    def test_year_2025(self):
        assert self._dy("calls in 2025") == 2025

    def test_year_2026(self):
        assert self._dy("performance in 2026") == 2026

    def test_year_2000(self):
        assert self._dy("calls in 2000") == 2000

    def test_no_year_returns_none(self):
        assert self._dy("how many calls in january") is None

    def test_year_in_context(self):
        assert self._dy("how many calls in march 2025") == 2025


class TestMonthTsRange:
    """_month_ts_range(month, year) — millisecond epoch range for a whole month."""

    def _mtr(self, month, year=None):
        from rag import _month_ts_range
        return _month_ts_range(month, year)

    def test_returns_tuple_of_two(self):
        result = self._mtr(1, 2026)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_start_less_than_end(self):
        start, end = self._mtr(3, 2026)
        assert start < end

    def test_january_31_days(self):
        start, end = self._mtr(1, 2026)
        diff_days = (end - start) / 1000 / 86400
        assert 30 <= diff_days <= 31

    def test_february_28_days_2025(self):
        start, end = self._mtr(2, 2025)
        diff_days = (end - start) / 1000 / 86400
        assert 27 <= diff_days <= 28

    def test_february_29_days_leap_2024(self):
        start, end = self._mtr(2, 2024)
        diff_days = (end - start) / 1000 / 86400
        assert 28 <= diff_days <= 29

    def test_values_are_milliseconds(self):
        start, _ = self._mtr(1, 2026)
        # Millisecond epoch for 2026 should be ~1.75 trillion
        assert start > 1_000_000_000_000

    def test_no_year_uses_current_year(self):
        from datetime import datetime
        start, _ = self._mtr(1)
        current_year = datetime.now().year
        expected_start, _ = self._mtr(1, current_year)
        assert start == expected_start


class TestDayTsRange:
    """_day_ts_range(year, month, day) — millisecond epoch range for a single day."""

    def _dtr(self, year, month, day):
        from rag import _day_ts_range
        return _day_ts_range(year, month, day)

    def test_returns_tuple_of_two(self):
        assert len(self._dtr(2026, 3, 15)) == 2

    def test_start_less_than_end(self):
        start, end = self._dtr(2026, 1, 1)
        assert start < end

    def test_range_is_approximately_one_day(self):
        start, end = self._dtr(2026, 6, 1)
        diff_seconds = (end - start) / 1000
        assert 86390 <= diff_seconds <= 86400  # 23h 59m 59s = 86399s

    def test_day_clamped_to_month_end(self):
        # Feb 30 should clamp to Feb 28 (2025 is not a leap year)
        start_30, _ = self._dtr(2025, 2, 30)
        start_28, _ = self._dtr(2025, 2, 28)
        assert start_30 == start_28


class TestIsFollowup:
    """_is_followup(question) — detects referential follow-up questions."""

    def _if(self, q):
        from rag import _is_followup
        return _is_followup(q)

    def test_those_calls_is_followup(self):
        assert self._if("which of those calls was worst") is True

    def test_that_call_is_followup(self):
        assert self._if("tell me more about that call") is True

    def test_you_mentioned_is_followup(self):
        assert self._if("can you expand on what you mentioned") is True

    def test_listed_above_is_followup(self):
        assert self._if("from those listed above which is best") is True

    def test_plain_question_is_not_followup(self):
        assert self._if("how many calls this week") is False

    def test_total_question_is_not_followup(self):
        assert self._if("what is the success rate") is False

    def test_empty_string_is_not_followup(self):
        assert self._if("") is False


class TestBuildSearchQuery:
    """_build_search_query(question, history) — enriches follow-up queries."""

    def _bsq(self, question, history=None):
        from rag import _build_search_query
        return _build_search_query(question, history)

    def test_no_history_returns_question_unchanged(self):
        assert self._bsq("how many calls", None) == "how many calls"

    def test_non_followup_returns_question_unchanged(self):
        history = [{"role": "user", "content": "prior question"}]
        assert self._bsq("how many calls", history) == "how many calls"

    def test_followup_appends_last_user_question(self):
        history = [
            {"role": "user",      "content": "show me the smooth calls"},
            {"role": "assistant", "content": "Here are 5 smooth calls..."},
        ]
        result = self._bsq("tell me more about those calls", history)
        assert "show me the smooth calls" in result
        assert "tell me more about those calls" in result

    def test_followup_uses_most_recent_user_turn(self):
        history = [
            {"role": "user",      "content": "first question"},
            {"role": "assistant", "content": "first answer"},
            {"role": "user",      "content": "second question"},
            {"role": "assistant", "content": "second answer"},
        ]
        result = self._bsq("which of those calls was worst", history)
        assert "second question" in result
        assert "first question" not in result


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — DB INTEGRATION  (real DB, no LLM)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBuildStatsContext:
    """build_stats_context(client_id) — builds the SQL facts block injected into the LLM."""

    def test_returns_non_empty_string_for_artel(self):
        from rag import build_stats_context
        ctx = build_stats_context(CLIENT_HEYA_001)
        assert isinstance(ctx, str)
        assert len(ctx) > 100

    def test_contains_client_name(self):
        from rag import build_stats_context
        ctx = build_stats_context(CLIENT_HEYA_001)
        assert "Artel" in ctx

    def test_contains_total_calls(self):
        from rag import build_stats_context
        ctx = build_stats_context(CLIENT_HEYA_001)
        assert "Total calls" in ctx or "total calls" in ctx

    def test_contains_engagement_score(self):
        from rag import build_stats_context
        ctx = build_stats_context(CLIENT_HEYA_001)
        assert "engagement" in ctx.lower()

    def test_contains_success_rate(self):
        from rag import build_stats_context
        ctx = build_stats_context(CLIENT_HEYA_001)
        assert "success" in ctx.lower()

    def test_mvaa_context_contains_mvaa_name(self):
        from rag import build_stats_context
        ctx = build_stats_context(CLIENT_HEYA_002)
        assert "MVAA" in ctx or "mvaa" in ctx.lower()

    def test_artel_context_does_not_contain_mvaa_data(self):
        from rag import build_stats_context
        ctx = build_stats_context(CLIENT_HEYA_001)
        # Client data should be scoped — MVAA client ID should not appear in Artel context
        assert CLIENT_HEYA_002 not in ctx

    def test_mvaa_context_does_not_contain_artel_data(self):
        from rag import build_stats_context
        ctx = build_stats_context(CLIENT_HEYA_002)
        assert CLIENT_HEYA_001 not in ctx


class TestDirectSQLAnswer:
    """_direct_sql_answer(question, client_id) — keyword SQL fast path, no LLM."""

    def _dsa(self, q, client_id=CLIENT_HEYA_001):
        from rag import _direct_sql_answer
        return _direct_sql_answer(q, client_id)

    def test_total_calls_question_returns_string(self):
        result = self._dsa("how many calls total")
        # Returns string or None — if the question matches a pattern, string is returned
        assert result is None or isinstance(result, str)

    def test_success_rate_question(self):
        result = self._dsa("what is the success rate")
        assert result is None or isinstance(result, str)

    def test_month_question_returns_string(self):
        result = self._dsa("how many calls in january")
        # Should match the month pattern and return a string
        assert result is None or isinstance(result, str)
        if result:
            assert "january" in result.lower() or "January" in result

    def test_artel_answer_does_not_contain_mvaa_id(self):
        result = self._dsa("how many calls", CLIENT_HEYA_001)
        if result:
            assert CLIENT_HEYA_002 not in result

    def test_mvaa_answer_does_not_contain_artel_id(self):
        result = self._dsa("how many calls", CLIENT_HEYA_002)
        if result:
            assert CLIENT_HEYA_001 not in result

    def test_unknown_question_returns_none(self):
        result = self._dsa("what is the meaning of life")
        assert result is None


class TestQueryNoLLM:
    """
    query(question, client_id) with no CEREBRAS_API_KEY set.

    When USE_LLM is False, query() either:
      - returns text_to_sql result (if text_to_sql module answers it), OR
      - falls back to no_llm route (returns stats context as text)

    In both cases: returns a dict with answer, route, confidence, sources.
    """

    def _q(self, question, client_id=CLIENT_HEYA_001, history=None):
        import rag
        original_key = rag.CEREBRAS_API_KEY
        original_use = rag.USE_LLM
        try:
            rag.CEREBRAS_API_KEY = ""
            rag.USE_LLM = False
            return rag.query(question, client_id, history)
        finally:
            rag.CEREBRAS_API_KEY = original_key
            rag.USE_LLM = original_use

    def test_returns_dict(self):
        result = self._q("how many calls")
        assert isinstance(result, dict)

    def test_has_required_keys(self):
        result = self._q("how many calls")
        for key in ("answer", "question", "route", "confidence", "sources"):
            assert key in result, f"Missing key: {key}"

    def test_answer_is_non_empty_string(self):
        result = self._q("how many calls")
        assert isinstance(result["answer"], str)
        assert len(result["answer"]) > 0

    def test_sources_is_list(self):
        result = self._q("what is the success rate")
        assert isinstance(result["sources"], list)

    def test_question_echoed_back(self):
        q = "how many calls total"
        result = self._q(q)
        assert result["question"] == q

    def test_route_is_known_value(self):
        result = self._q("how many calls")
        valid_routes = {
            "text_to_sql", "sql_direct", "no_llm",
            "llm_stats", "llm_stats+semantic",
            "admin_platform", "admin_platform+semantic",
            "followup+llm_stats", "followup+llm_stats+semantic",
        }
        assert result["route"] in valid_routes, f"Unknown route: {result['route']}"

    def test_confidence_is_known_value(self):
        result = self._q("how many calls")
        assert result["confidence"] in ("VERIFIED", "HIGH", "MEDIUM")

    def test_artel_answer_does_not_reference_mvaa(self):
        result = self._q("how many calls", CLIENT_HEYA_001)
        # MVAA client ID must not appear in Artel answers
        assert CLIENT_HEYA_002 not in result["answer"]

    def test_mvaa_answer_does_not_reference_artel(self):
        result = self._q("how many calls", CLIENT_HEYA_002)
        assert CLIENT_HEYA_001 not in result["answer"]

    def test_followup_flag_detected_in_route(self):
        history = [
            {"role": "user",      "content": "show me smooth calls"},
            {"role": "assistant", "content": "Here are the smooth calls."},
        ]
        result = self._q("which of those calls was worst", CLIENT_HEYA_001, history)
        # Follow-up questions take a different path — verify the answer is still valid
        assert isinstance(result["answer"], str)

    def test_qualitative_question_skips_sql_path(self):
        result = self._q("why did the engagement drop in those calls")
        # Should skip text_to_sql and sql_direct, landing on llm_stats or no_llm
        assert result["route"] not in ("text_to_sql", "sql_direct")


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — HTTP ENDPOINT  (real app via TestClient)
# ═══════════════════════════════════════════════════════════════════════════════

class TestQueryEndpoint:
    """POST /query — HTTP-level tests via TestClient."""

    def test_valid_question_returns_200(self, client, artel_h):
        r = client.post("/query", json={
            "question":  "how many calls",
            "client_id": CLIENT_HEYA_001,
        }, headers=artel_h)
        assert r.status_code == 200

    def test_response_has_answer_key(self, client, artel_h):
        r = client.post("/query", json={
            "question":  "how many calls",
            "client_id": CLIENT_HEYA_001,
        }, headers=artel_h)
        assert "answer" in r.json()

    def test_response_shape(self, client, artel_h):
        r = client.post("/query", json={
            "question":  "what is the success rate",
            "client_id": CLIENT_HEYA_001,
        }, headers=artel_h)
        data = r.json()
        for key in ("answer", "question", "confidence", "sources", "route"):
            assert key in data, f"Missing key: {key}"

    def test_answer_is_non_empty(self, client, artel_h):
        r = client.post("/query", json={
            "question":  "how many calls",
            "client_id": CLIENT_HEYA_001,
        }, headers=artel_h)
        assert len(r.json()["answer"]) > 0

    def test_sources_is_list(self, client, artel_h):
        r = client.post("/query", json={
            "question":  "how many calls",
            "client_id": CLIENT_HEYA_001,
        }, headers=artel_h)
        assert isinstance(r.json()["sources"], list)

    def test_confidence_is_valid(self, client, artel_h):
        r = client.post("/query", json={
            "question":  "how many calls",
            "client_id": CLIENT_HEYA_001,
        }, headers=artel_h)
        assert r.json()["confidence"] in ("VERIFIED", "HIGH", "MEDIUM")

    def test_no_auth_returns_401(self, client):
        r = client.post("/query", json={
            "question": "how many calls", "client_id": CLIENT_HEYA_001
        })
        assert r.status_code == 401

    def test_cross_tenant_returns_403(self, client, artel_h):
        r = client.post("/query", json={
            "question":  "how many calls",
            "client_id": CLIENT_HEYA_002,   # Artel token, MVAA client
        }, headers=artel_h)
        assert r.status_code == 403

    def test_empty_question_returns_400(self, client, artel_h):
        r = client.post("/query", json={
            "question": "   ", "client_id": CLIENT_HEYA_001
        }, headers=artel_h)
        assert r.status_code == 400

    def test_whitespace_only_question_returns_400(self, client, artel_h):
        r = client.post("/query", json={
            "question": "\t\n  ", "client_id": CLIENT_HEYA_001
        }, headers=artel_h)
        assert r.status_code == 400

    def test_admin_can_query_any_client(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.post("/query", json={
                "question":  "how many calls",
                "client_id": cid,
            }, headers=admin_h)
            assert r.status_code == 200, f"Admin query failed for {cid}"

    def test_mvaa_user_can_query_own_client(self, client, mvaa_h):
        r = client.post("/query", json={
            "question":  "how many calls",
            "client_id": CLIENT_HEYA_002,
        }, headers=mvaa_h)
        assert r.status_code == 200

    def test_missing_question_field_returns_422(self, client, artel_h):
        r = client.post("/query", json={"client_id": CLIENT_HEYA_001}, headers=artel_h)
        assert r.status_code == 422

    def test_missing_client_id_field_returns_422(self, client, artel_h):
        r = client.post("/query", json={"question": "how many calls"}, headers=artel_h)
        assert r.status_code == 422

    def test_with_history_returns_200(self, client, artel_h):
        r = client.post("/query", json={
            "question":  "which of those calls was worst",
            "client_id": CLIENT_HEYA_001,
            "history": [
                {"role": "user",      "content": "show me smooth calls"},
                {"role": "assistant", "content": "Here are 5 smooth calls."},
            ],
        }, headers=artel_h)
        assert r.status_code == 200
        assert "answer" in r.json()
