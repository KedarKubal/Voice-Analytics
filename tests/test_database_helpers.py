"""
test_database_helpers.py — Unit tests for database.py pure helper functions

No HTTP, no DB connection needed — tests isolated logic.
"""

import math
import pytest
from database import safe_json_float


class TestSafeJsonFloat:
    """safe_json_float converts any value to a JSON-serialisable float."""

    def test_normal_float_passthrough(self):
        assert safe_json_float(3.14) == pytest.approx(3.14)

    def test_integer_converts_to_float(self):
        result = safe_json_float(42)
        assert result == 42.0
        assert isinstance(result, float)

    def test_zero_returns_zero(self):
        assert safe_json_float(0) == 0.0

    def test_none_returns_default(self):
        assert safe_json_float(None) == 0.0

    def test_none_with_custom_default(self):
        assert safe_json_float(None, default=-1.0) == -1.0

    def test_nan_returns_default(self):
        assert safe_json_float(float("nan")) == 0.0

    def test_nan_with_custom_default(self):
        assert safe_json_float(float("nan"), default=99.9) == 99.9

    def test_positive_infinity_returns_default(self):
        assert safe_json_float(float("inf")) == 0.0

    def test_negative_infinity_returns_default(self):
        assert safe_json_float(float("-inf")) == 0.0

    def test_string_number_converts(self):
        result = safe_json_float("7.5")
        assert result == pytest.approx(7.5)

    def test_non_numeric_string_returns_default(self):
        assert safe_json_float("hello") == 0.0

    def test_empty_string_returns_default(self):
        assert safe_json_float("") == 0.0

    def test_result_is_json_serialisable(self):
        import json
        for val in [float("nan"), float("inf"), None, 42, "3.14"]:
            result = safe_json_float(val)
            # Should not raise
            json.dumps(result)

    def test_very_large_float_passthrough(self):
        big = 1e300
        assert safe_json_float(big) == pytest.approx(big)

    def test_very_small_float_passthrough(self):
        tiny = 1e-300
        assert safe_json_float(tiny) == pytest.approx(tiny)

    def test_negative_float_passthrough(self):
        assert safe_json_float(-5.5) == pytest.approx(-5.5)
