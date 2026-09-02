"""
test_quality.py — Pure unit tests for quality.py

No DB, no HTTP — tests the scoring math in complete isolation.

Weights (from quality.py):
  engagement_score  35%   (0–100 float)
  conversation_flow 25%   smooth=100 / moderate=60 / poor=20
  call_successful   25%   True=100 / False=0 / None=50
  dominant_emotion  15%   happy=100 / surprised=75 / neutral=60 /
                          fearful=35 / sad=30 / disgusted=20 / angry=15

Grade thresholds: ≥80 → A, ≥65 → B, ≥50 → C, ≥35 → D, else F
"""

import pytest
from quality import compute_quality_score, quality_grade


# ── compute_quality_score ─────────────────────────────────────────────────────

class TestComputeQualityScore:

    def test_perfect_call_scores_100(self):
        score = compute_quality_score(100, "smooth", True, "happy")
        assert score == 100

    def test_worst_call_scores_near_zero(self):
        score = compute_quality_score(0, "poor", False, "angry")
        # 0*0.35 + 20*0.25 + 0*0.25 + 15*0.15 = 0 + 5 + 0 + 2.25 = 7 (rounded)
        assert score == round(0 * 0.35 + 20 * 0.25 + 0 * 0.25 + 15 * 0.15)

    def test_average_call_scores_mid_range(self):
        score = compute_quality_score(50, "moderate", None, "neutral")
        # 50*0.35 + 60*0.25 + 50*0.25 + 60*0.15 = 17.5+15+12.5+9 = 54
        expected = round(50 * 0.35 + 60 * 0.25 + 50 * 0.25 + 60 * 0.15)
        assert score == expected

    def test_engagement_weight_is_35_percent(self):
        s1 = compute_quality_score(100, "poor", False, "angry")
        s2 = compute_quality_score(0,   "poor", False, "angry")
        # Only engagement differs: delta should be 35
        assert (s1 - s2) == round(100 * 0.35)

    def test_flow_smooth_vs_poor_difference(self):
        s_smooth = compute_quality_score(50, "smooth", None, "neutral")
        s_poor   = compute_quality_score(50, "poor",   None, "neutral")
        # Flow delta: (100-20)*0.25 = 20
        assert (s_smooth - s_poor) == round((100 - 20) * 0.25)

    def test_successful_call_bonus_vs_failed(self):
        s_ok   = compute_quality_score(50, "moderate", True,  "neutral")
        s_fail = compute_quality_score(50, "moderate", False, "neutral")
        # Verify each score against formula directly (avoids banker's rounding edge case)
        assert s_ok   == round(50 * 0.35 + 60 * 0.25 + 100 * 0.25 + 60 * 0.15)
        assert s_fail == round(50 * 0.35 + 60 * 0.25 +   0 * 0.25 + 60 * 0.15)

    def test_none_outcome_uses_50_midpoint(self):
        s_none = compute_quality_score(50, "moderate", None, "neutral")
        s_ok   = compute_quality_score(50, "moderate", True, "neutral")
        # Difference should be (100-50)*0.25 = 12 or 13
        diff = s_ok - s_none
        assert diff == round((100 - 50) * 0.25)

    def test_all_none_inputs_use_defaults(self):
        score = compute_quality_score(None, None, None, None)
        # eng=50, flow=50, outcome=50, emotion=50 → all 50
        # 50*0.35 + 50*0.25 + 50*0.25 + 50*0.15 = 50
        assert score == 50

    def test_unknown_emotion_uses_50_default(self):
        s_unknown = compute_quality_score(50, "moderate", None, "unknown_emotion")
        s_none    = compute_quality_score(50, "moderate", None, None)
        assert s_unknown == s_none  # both fall back to emotion=50

    def test_unknown_flow_uses_50_default(self):
        s_unknown = compute_quality_score(50, "unknown_flow", None, "neutral")
        # flow=50, so: 50*0.35 + 50*0.25 + 50*0.25 + 60*0.15 = 17.5+12.5+12.5+9 = 51.5 → 52
        expected = round(50 * 0.35 + 50 * 0.25 + 50 * 0.25 + 60 * 0.15)
        assert s_unknown == expected

    def test_engagement_score_100_happy_smooth_successful(self):
        score = compute_quality_score(100, "smooth", True, "happy")
        assert score == round(100 * 0.35 + 100 * 0.25 + 100 * 0.25 + 100 * 0.15)

    def test_each_emotion_score_maps_correctly(self):
        from quality import _EMOTION_SCORES
        base = compute_quality_score(50, "moderate", None, None)  # emotion=50
        for emotion, expected_pts in _EMOTION_SCORES.items():
            score = compute_quality_score(50, "moderate", None, emotion)
            expected = round(50 * 0.35 + 60 * 0.25 + 50 * 0.25 + expected_pts * 0.15)
            assert score == expected, f"Emotion {emotion}: expected {expected}, got {score}"

    @pytest.mark.parametrize("eng", [0, 25, 50, 75, 100])
    def test_score_is_integer(self, eng):
        score = compute_quality_score(eng, "smooth", True, "happy")
        assert isinstance(score, int)

    def test_score_is_non_negative(self):
        score = compute_quality_score(0, "poor", False, "angry")
        assert score >= 0

    def test_score_does_not_exceed_100(self):
        score = compute_quality_score(100, "smooth", True, "happy")
        assert score <= 100


# ── quality_grade ─────────────────────────────────────────────────────────────

class TestQualityGrade:

    def test_grade_a_at_80(self):
        assert quality_grade(80) == "A"

    def test_grade_a_at_100(self):
        assert quality_grade(100) == "A"

    def test_grade_b_at_65(self):
        assert quality_grade(65) == "B"

    def test_grade_b_at_79(self):
        assert quality_grade(79) == "B"

    def test_grade_c_at_50(self):
        assert quality_grade(50) == "C"

    def test_grade_c_at_64(self):
        assert quality_grade(64) == "C"

    def test_grade_d_at_35(self):
        assert quality_grade(35) == "D"

    def test_grade_d_at_49(self):
        assert quality_grade(49) == "D"

    def test_grade_f_at_34(self):
        assert quality_grade(34) == "F"

    def test_grade_f_at_0(self):
        assert quality_grade(0) == "F"

    @pytest.mark.parametrize("score,expected", [
        (100, "A"), (80, "A"), (79, "B"), (65, "B"),
        (64, "C"), (50, "C"), (49, "D"), (35, "D"),
        (34, "F"), (0, "F"),
    ])
    def test_grade_boundary_table(self, score, expected):
        assert quality_grade(score) == expected

    def test_grade_boundaries_are_inclusive_lower_bound(self):
        # Each threshold is the minimum score for that grade
        thresholds = {"A": 80, "B": 65, "C": 50, "D": 35}
        for grade, threshold in thresholds.items():
            assert quality_grade(threshold) == grade, f"Grade {grade} at score {threshold}"
