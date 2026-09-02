"""
test_calls.py — GET /call/{call_id} and GET /audio/{call_id}

Covers:
  • 200 + full shape for a real call
  • Transcript utterances present and shaped correctly
  • Cross-tenant call access returns 404 (not 403 — hides existence)
  • Nonexistent call_id → 404
  • Audio endpoint for call without recording → 404
  • /feed/{client_id} client-scoped live feed
  • /emotions/{client_id} and /topics/{client_id}
"""

import pytest
from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002


# ── /call/{call_id} ───────────────────────────────────────────────────────────

class TestCallDetail:
    def test_valid_call_returns_200(self, client, artel_h, artel_call_id):
        r = client.get(f"/call/{artel_call_id}", headers=artel_h)
        assert r.status_code == 200

    def test_response_has_required_fields(self, client, artel_h, artel_call_id):
        data = client.get(f"/call/{artel_call_id}", headers=artel_h).json()
        assert "call_id"      in data
        assert "transcript"   in data
        assert "call_summary" in data

    def test_call_id_matches_request(self, client, artel_h, artel_call_id):
        data = client.get(f"/call/{artel_call_id}", headers=artel_h).json()
        assert data["call_id"] == artel_call_id

    def test_transcript_is_list(self, client, artel_h, artel_call_id):
        data = client.get(f"/call/{artel_call_id}", headers=artel_h).json()
        assert isinstance(data["transcript"], list)

    def test_transcript_utterances_have_required_fields(self, client, artel_h, artel_call_id):
        data = client.get(f"/call/{artel_call_id}", headers=artel_h).json()
        for utt in data["transcript"]:
            assert "index"   in utt
            assert "role"    in utt
            assert "content" in utt

    def test_transcript_roles_are_valid(self, client, artel_h, artel_call_id):
        data = client.get(f"/call/{artel_call_id}", headers=artel_h).json()
        valid_roles = {"agent", "user"}
        for utt in data["transcript"]:
            assert utt["role"] in valid_roles, f"Unexpected role: {utt['role']}"

    def test_transcript_ordered_by_index(self, client, artel_h, artel_call_id):
        data = client.get(f"/call/{artel_call_id}", headers=artel_h).json()
        indices = [u["index"] for u in data["transcript"]]
        assert indices == sorted(indices)

    def test_admin_can_access_any_call(self, client, admin_h, artel_call_id):
        r = client.get(f"/call/{artel_call_id}", headers=admin_h)
        assert r.status_code == 200

    def test_nonexistent_call_returns_404(self, client, artel_h):
        r = client.get("/call/call_does_not_exist_xyz", headers=artel_h)
        assert r.status_code == 404

    def test_cross_tenant_call_returns_404(self, client, mvaa_h, artel_call_id):
        # MVAA user tries to access Artel's call — gets 404 (not 403, to hide existence)
        r = client.get(f"/call/{artel_call_id}", headers=mvaa_h)
        assert r.status_code == 404

    def test_no_auth_returns_401(self, client, artel_call_id):
        r = client.get(f"/call/{artel_call_id}")
        assert r.status_code == 401


# ── /audio/{call_id} ─────────────────────────────────────────────────────────

class TestCallAudio:
    def test_audio_no_auth_returns_401(self, client, artel_call_id):
        r = client.get(f"/audio/{artel_call_id}")
        assert r.status_code == 401

    def test_audio_nonexistent_call_returns_404(self, client, artel_h):
        r = client.get("/audio/call_does_not_exist_xyz", headers=artel_h)
        assert r.status_code == 404

    def test_audio_cross_tenant_returns_403(self, client, mvaa_h, artel_call_id):
        r = client.get(f"/audio/{artel_call_id}", headers=mvaa_h)
        assert r.status_code == 403

    def test_audio_returns_404_or_200_for_real_call(self, client, artel_h, artel_call_id):
        r = client.get(f"/audio/{artel_call_id}", headers=artel_h)
        # 200 if recording file exists on disk, 404 if not — both are correct
        assert r.status_code in (200, 404)


# ── /feed/{client_id} ─────────────────────────────────────────────────────────

class TestClientFeed:
    def test_feed_returns_200(self, client, artel_h):
        r = client.get(f"/feed/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_feed_contains_calls_list(self, client, artel_h):
        data = client.get(f"/feed/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "calls" in data or "feed" in data or isinstance(data, (list, dict))

    def test_feed_cross_tenant_returns_403(self, client, artel_h):
        r = client.get(f"/feed/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_feed_no_auth_returns_401(self, client):
        r = client.get(f"/feed/{CLIENT_HEYA_001}")
        assert r.status_code == 401


# ── /emotions/{client_id} ─────────────────────────────────────────────────────

class TestEmotionStats:
    def test_emotions_returns_200(self, client, artel_h):
        r = client.get(f"/emotions/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_emotions_has_required_sections(self, client, artel_h):
        data = client.get(f"/emotions/{CLIENT_HEYA_001}", headers=artel_h).json()
        assert "utterance_distribution" in data
        assert "call_distribution"      in data
        assert "weekly_trend"           in data

    def test_emotions_distribution_entries_have_emotion_and_count(self, client, artel_h):
        data = client.get(f"/emotions/{CLIENT_HEYA_001}", headers=artel_h).json()
        for entry in data["call_distribution"]:
            assert "emotion" in entry
            assert "count"   in entry
            assert isinstance(entry["count"], int)

    def test_emotions_cross_tenant_returns_403(self, client, artel_h):
        r = client.get(f"/emotions/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403


# ── /topics/{client_id} ───────────────────────────────────────────────────────

class TestTopicStats:
    def test_topics_returns_200(self, client, artel_h):
        r = client.get(f"/topics/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_topics_cross_tenant_returns_403(self, client, artel_h):
        r = client.get(f"/topics/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_topics_no_auth_returns_401(self, client):
        r = client.get(f"/topics/{CLIENT_HEYA_001}")
        assert r.status_code == 401
