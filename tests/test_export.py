"""
test_export.py — GET /export/csv/{client_id} and GET /export/report/{client_id}

Covers:
  • CSV: correct Content-Type, Content-Disposition, header row, data rows
  • CSV: all expected columns present
  • CSV: numeric fields are parseable numbers
  • HTML Report: correct Content-Type, contains client name, KPI sections
  • HTML Report: is valid HTML (has <html> tag)
  • Cross-tenant isolation (403)
  • No auth → 401
"""

import csv
import io
import pytest
from conftest import CLIENT_HEYA_001, CLIENT_HEYA_002


# ── CSV Export ────────────────────────────────────────────────────────────────

EXPECTED_CSV_COLUMNS = [
    "Call ID", "Date & Time", "Direction", "Duration (sec)", "Successful",
    "User Sentiment", "Conversation Flow", "Sentiment Trajectory",
    "Engagement Score", "Silence Ratio (%)", "Interruptions", "Hesitations",
    "Total Turns", "Agent Talk Time (sec)", "Customer Talk Time (sec)",
    "Avg Pitch (Hz)", "Agent Avg Pitch (Hz)", "Customer Avg Pitch (Hz)",
    "Avg Energy", "Agent Avg Energy", "Customer Avg Energy",
]


class TestCSVExport:
    def test_returns_200(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_content_type_is_csv(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}", headers=artel_h)
        assert "text/csv" in r.headers.get("content-type", "")

    def test_content_disposition_is_attachment(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}", headers=artel_h)
        cd = r.headers.get("content-disposition", "")
        assert "attachment" in cd
        assert ".csv" in cd

    def test_filename_contains_client_id(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}", headers=artel_h)
        cd = r.headers.get("content-disposition", "")
        assert CLIENT_HEYA_001 in cd

    def test_csv_has_header_row(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}", headers=artel_h)
        reader = csv.reader(io.StringIO(r.text))
        header = next(reader)
        assert len(header) > 0
        assert "Call ID" in header

    def test_csv_has_all_expected_columns(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}", headers=artel_h)
        reader = csv.reader(io.StringIO(r.text))
        header = next(reader)
        for col in EXPECTED_CSV_COLUMNS:
            assert col in header, f"Missing CSV column: {col}"

    def test_csv_has_data_rows(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}", headers=artel_h)
        reader = csv.reader(io.StringIO(r.text))
        rows = list(reader)
        assert len(rows) > 1, "CSV has only header, no data rows"

    def test_csv_duration_column_is_numeric(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}", headers=artel_h)
        reader = csv.DictReader(io.StringIO(r.text))
        for row in reader:
            dur = row.get("Duration (sec)", "")
            if dur:
                float(dur)  # Must not raise

    def test_csv_engagement_score_is_numeric(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}", headers=artel_h)
        reader = csv.DictReader(io.StringIO(r.text))
        for row in reader:
            eng = row.get("Engagement Score", "")
            if eng:
                float(eng)  # Must not raise

    def test_csv_no_auth_returns_401(self, client):
        r = client.get(f"/export/csv/{CLIENT_HEYA_001}")
        assert r.status_code == 401

    def test_csv_cross_tenant_returns_403(self, client, artel_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_csv_admin_can_export_any_client(self, client, admin_h):
        for cid in [CLIENT_HEYA_001, CLIENT_HEYA_002]:
            r = client.get(f"/export/csv/{cid}", headers=admin_h)
            assert r.status_code == 200

    def test_mvaa_csv_returns_200(self, client, mvaa_h):
        r = client.get(f"/export/csv/{CLIENT_HEYA_002}", headers=mvaa_h)
        assert r.status_code == 200


# ── HTML Report ───────────────────────────────────────────────────────────────

class TestHTMLReport:
    def test_returns_200(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_001}", headers=artel_h)
        assert r.status_code == 200

    def test_content_type_is_html(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_001}", headers=artel_h)
        assert "text/html" in r.headers.get("content-type", "")

    def test_html_has_doctype_and_html_tag(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_001}", headers=artel_h)
        assert "<!DOCTYPE html>" in r.text or "<html" in r.text

    def test_html_contains_client_name(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_001}", headers=artel_h)
        assert "Artel Apartments" in r.text

    def test_html_contains_heya_branding(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_001}", headers=artel_h)
        assert "Heya" in r.text

    def test_html_contains_kpi_section(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_001}", headers=artel_h)
        assert "Total Calls" in r.text or "Performance" in r.text

    def test_html_contains_engagement_benchmark(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_001}", headers=artel_h)
        assert "62.0" in r.text or "benchmark" in r.text.lower() or "industry" in r.text.lower()

    def test_html_contains_recommendations_section(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_001}", headers=artel_h)
        assert "Recommendation" in r.text or "Priority" in r.text

    def test_html_no_auth_returns_401(self, client):
        r = client.get(f"/export/report/{CLIENT_HEYA_001}")
        assert r.status_code == 401

    def test_html_cross_tenant_returns_403(self, client, artel_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_002}", headers=artel_h)
        assert r.status_code == 403

    def test_html_mvaa_contains_correct_client_name(self, client, mvaa_h):
        r = client.get(f"/export/report/{CLIENT_HEYA_002}", headers=mvaa_h)
        assert r.status_code == 200
        assert "MVAA Legal" in r.text
