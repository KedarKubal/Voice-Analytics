"""
test_health.py — Health, root, and queue status endpoints

Covers:
  • GET /         → service info shape
  • GET /health/db → database connectivity
  • GET /health/queue → queue status
"""

class TestRoot:
    def test_root_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_root_contains_service_name(self, client):
        data = client.get("/").json()
        assert "Heya AI" in data["service"]

    def test_root_contains_status_running(self, client):
        data = client.get("/").json()
        assert data["status"] == "running"

    def test_root_lists_endpoints(self, client):
        data = client.get("/").json()
        assert isinstance(data["endpoints"], list)
        assert len(data["endpoints"]) > 0

    def test_root_no_auth_required(self, client):
        # Public endpoint — should work without any headers
        r = client.get("/")
        assert r.status_code == 200


class TestHealthDB:
    def test_db_health_returns_200_when_connected(self, client):
        r = client.get("/health/db")
        assert r.status_code == 200

    def test_db_health_response_shape(self, client):
        data = client.get("/health/db").json()
        assert data.get("database") == "connected"

    def test_db_health_no_auth_required(self, client):
        r = client.get("/health/db")
        assert r.status_code == 200


class TestHealthQueue:
    def test_queue_endpoint_requires_auth(self, client):
        r = client.get("/health/queue")
        assert r.status_code == 401

    def test_queue_returns_200_with_admin_token(self, client, admin_h):
        r = client.get("/health/queue", headers=admin_h)
        assert r.status_code == 200

    def test_queue_response_has_pending_count(self, client, admin_h):
        data = client.get("/health/queue", headers=admin_h).json()
        assert "pending" in data or "queue" in str(data).lower()
