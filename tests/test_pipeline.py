"""
test_pipeline.py — Audio processing pipeline tests

Three layers:

  Layer 1 — Pure unit tests (no audio, no GPU, < 1s)
    Uses synthetic pandas DataFrames to verify every pure function
    in isolation: merge, assign_roles, pause features, engagement
    score, interruptions, hesitation, flow label, trajectory.

  Layer 2 — Acoustic feature tests (CPU + real .wav file)
    Calls add_acoustic_features() with a real recording.
    librosa always runs on CPU — no GPU needed.

  Layer 3 — GPU integration test (pyannote + full process_call)
    Loads the full pyannote diarisation pipeline onto GPU and
    runs process_call() on a real audio file end-to-end.
    Requires HF_TOKEN env var and CUDA. Marked @pytest.mark.gpu.
    Skip with: pytest tests/test_pipeline.py -m "not gpu"
"""

import os
import sys
import math
import pytest
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Real audio files from the dataset
ARTEL_RECORDINGS = r"D:\rmit\semester_4\project\dataset\artel_apartments\recordings"
SMALL_WAV = os.path.join(
    ARTEL_RECORDINGS,
    "call_037f9a7f2d7a7c25fd844ffb16a",
    "audio.wav",
)
TINY_WAV = os.path.join(
    ARTEL_RECORDINGS,
    "call_01522047922e22a77a4e5aea40f",
    "audio.wav",
)


# ── Helpers for building synthetic DataFrames ────────────────────────────────

def make_turns(*args) -> pd.DataFrame:
    """
    Build a turn DataFrame from (speaker, start, end) tuples.
    Adds duration_sec automatically.
    """
    rows = []
    for speaker, start, end in args:
        rows.append({
            "speaker":      speaker,
            "start_sec":    float(start),
            "end_sec":      float(end),
            "duration_sec": float(end - start),
        })
    return pd.DataFrame(rows).reset_index(drop=True)


def make_featured_turns(*args) -> pd.DataFrame:
    """
    Build a full-featured turn DataFrame (with all columns needed by metric functions).
    Each arg: (speaker, role, start, end, energy, pitch, pause)
    """
    rows = []
    for speaker, role, start, end, energy, pitch, pause in args:
        rows.append({
            "speaker":            speaker,
            "role":               role,
            "start_sec":          float(start),
            "end_sec":            float(end),
            "duration_sec":       float(end - start),
            "energy_mean":        energy,
            "pitch_mean_hz":      pitch,
            "pause_before_sec":   float(pause),
            "speech_rate_proxy":  1.0 / (float(end - start) + 1e-6),
        })
    return pd.DataFrame(rows).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — PURE UNIT TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestMergeAdjacentSameSpeaker:

    def _merge(self, df, gap=0.3):
        from pipeline import merge_adjacent_same_speaker
        return merge_adjacent_same_speaker(df, gap_threshold=gap)

    def test_same_speaker_within_gap_merged(self):
        df = make_turns(("A", 0, 1), ("A", 1.1, 2))  # gap = 0.1s < 0.3
        result = self._merge(df)
        assert len(result) == 1
        assert result.iloc[0]["end_sec"] == 2.0

    def test_same_speaker_beyond_gap_not_merged(self):
        df = make_turns(("A", 0, 1), ("A", 1.5, 2))  # gap = 0.5s > 0.3
        result = self._merge(df)
        assert len(result) == 2

    def test_different_speakers_not_merged(self):
        df = make_turns(("A", 0, 1), ("B", 1.1, 2))
        result = self._merge(df)
        assert len(result) == 2

    def test_three_consecutive_same_speaker_all_merged(self):
        df = make_turns(("A", 0, 1), ("A", 1.1, 2), ("A", 2.2, 3))
        result = self._merge(df)
        assert len(result) == 1
        assert result.iloc[0]["start_sec"] == 0.0
        assert result.iloc[0]["end_sec"]   == 3.0

    def test_duration_updated_after_merge(self):
        df = make_turns(("A", 0, 2), ("A", 2.1, 5))
        result = self._merge(df)
        assert result.iloc[0]["duration_sec"] == pytest.approx(5.0)

    def test_empty_dataframe_returns_empty(self):
        df = pd.DataFrame(columns=["speaker", "start_sec", "end_sec", "duration_sec"])
        result = self._merge(df)
        assert len(result) == 0

    def test_single_turn_returned_unchanged(self):
        df = make_turns(("A", 0, 5))
        result = self._merge(df)
        assert len(result) == 1

    def test_interleaved_speakers_preserved(self):
        df = make_turns(("A", 0, 1), ("B", 1.1, 2), ("A", 2.1, 3))
        result = self._merge(df)
        assert len(result) == 3

    def test_custom_gap_threshold_respected(self):
        # gap = 0.8s; with threshold=0.5 not merged; with threshold=1.0 merged
        df = make_turns(("A", 0, 1), ("A", 1.8, 2))
        assert len(self._merge(df, gap=0.5)) == 2
        assert len(self._merge(df, gap=1.0)) == 1


class TestAssignRoles:

    def _assign(self, df):
        from pipeline import assign_roles
        return assign_roles(df)

    def test_most_talk_time_is_agent(self):
        df = make_turns(("A", 0, 10), ("B", 11, 13))  # A=10s, B=2s
        result = self._assign(df)
        assert result[result["speaker"] == "A"]["role"].iloc[0] == "agent"
        assert result[result["speaker"] == "B"]["role"].iloc[0] == "customer"

    def test_customer_has_less_talk_time(self):
        df = make_turns(("X", 0, 5), ("Y", 6, 20))  # Y has 14s > X has 5s
        result = self._assign(df)
        assert result[result["speaker"] == "Y"]["role"].iloc[0] == "agent"
        assert result[result["speaker"] == "X"]["role"].iloc[0] == "customer"

    def test_single_speaker_all_marked_agent(self):
        df = make_turns(("A", 0, 5), ("A", 6, 10))
        result = self._assign(df)
        assert all(result["role"] == "agent")

    def test_role_column_created(self):
        df = make_turns(("A", 0, 5), ("B", 6, 7))
        result = self._assign(df)
        assert "role" in result.columns

    def test_original_dataframe_not_mutated(self):
        df = make_turns(("A", 0, 5), ("B", 6, 7))
        original_cols = list(df.columns)
        self._assign(df)
        assert list(df.columns) == original_cols  # no "role" added to original


class TestAddPauseFeatures:

    def _add_pauses(self, df):
        from pipeline import add_pause_features
        return add_pause_features(df)

    def test_first_turn_pause_equals_start_time(self):
        df = make_turns(("A", 2.0, 3.0))  # starts at 2s → 2s of initial silence
        result = self._add_pauses(df)
        assert result.iloc[0]["pause_before_sec"] == pytest.approx(2.0)

    def test_sequential_turns_gap_computed(self):
        df = make_turns(("A", 0, 1), ("B", 1.5, 2.5))  # gap = 0.5
        result = self._add_pauses(df)
        assert result.iloc[1]["pause_before_sec"] == pytest.approx(0.5)

    def test_overlapping_turns_pause_is_zero(self):
        df = make_turns(("A", 0, 2), ("B", 1.5, 3))  # B starts before A ends
        result = self._add_pauses(df)
        assert result.iloc[1]["pause_before_sec"] == 0.0

    def test_pause_column_added(self):
        df = make_turns(("A", 0, 1))
        result = self._add_pauses(df)
        assert "pause_before_sec" in result.columns

    def test_original_not_mutated(self):
        df = make_turns(("A", 0, 1), ("B", 1.5, 2))
        self._add_pauses(df)
        assert "pause_before_sec" not in df.columns

    def test_multiple_turns_all_computed(self):
        df = make_turns(("A", 0, 1), ("B", 2, 3), ("A", 4, 5))
        result = self._add_pauses(df)
        assert len(result) == 3
        assert result["pause_before_sec"].iloc[1] == pytest.approx(1.0)
        assert result["pause_before_sec"].iloc[2] == pytest.approx(1.0)


class TestAddSpeakingRate:

    def _add_rate(self, df):
        from pipeline import add_speaking_rate
        return add_speaking_rate(df)

    def test_rate_column_added(self):
        df = make_turns(("A", 0, 2))
        result = self._add_rate(df)
        assert "speech_rate_proxy" in result.columns

    def test_short_turn_has_higher_rate(self):
        df = make_turns(("A", 0, 0.5), ("B", 1, 5))  # 0.5s vs 4s
        result = self._add_rate(df)
        assert result.iloc[0]["speech_rate_proxy"] > result.iloc[1]["speech_rate_proxy"]

    def test_rate_is_inverse_of_duration(self):
        df = make_turns(("A", 0, 4))
        result = self._add_rate(df)
        expected = 1.0 / (4.0 + 1e-6)
        assert result.iloc[0]["speech_rate_proxy"] == pytest.approx(expected)

    def test_no_division_by_zero_on_zero_duration(self):
        df = make_turns(("A", 1, 1))  # zero-length turn
        result = self._add_rate(df)
        assert math.isfinite(result.iloc[0]["speech_rate_proxy"])


class TestAddBehaviorLabels:

    def _add_labels(self, df):
        from pipeline import add_behavior_labels
        df["energy_mean"]   = [0.01, 0.05, 0.03]
        df["pitch_mean_hz"] = [150.0, 300.0, 200.0]
        return add_behavior_labels(df)

    def test_long_turn_flag(self):
        df = make_turns(("A", 0, 4), ("B", 5, 7), ("A", 8, 9))
        result = self._add_labels(df)
        assert result.iloc[0]["is_long_turn"] == True   # 4s > 3
        assert result.iloc[1]["is_long_turn"] == False  # 2s
        assert result.iloc[2]["is_long_turn"] == False  # 1s

    def test_high_energy_flag_above_mean(self):
        df = make_turns(("A", 0, 2), ("B", 3, 5), ("A", 6, 8))
        result = self._add_labels(df)
        # energy_mean = [0.01, 0.05, 0.03], mean = 0.03
        assert result.iloc[1]["is_high_energy"] == True   # 0.05 > 0.03
        assert result.iloc[0]["is_high_energy"] == False  # 0.01 < 0.03

    def test_all_columns_created(self):
        df = make_turns(("A", 0, 2), ("B", 3, 5), ("A", 6, 8))
        result = self._add_labels(df)
        for col in ["is_long_turn", "is_high_energy", "is_high_pitch"]:
            assert col in result.columns


class TestComputeInterruptions:

    def _compute(self, *args):
        from pipeline import compute_interruptions
        df = make_turns(*args)
        return compute_interruptions(df)

    def test_no_overlap_zero_interruptions(self):
        assert self._compute(("A", 0, 1), ("B", 1.5, 2.5)) == 0

    def test_one_overlap_one_interruption(self):
        # B starts at 0.8 while A ends at 1.0 → overlap
        assert self._compute(("A", 0, 1), ("B", 0.8, 2)) == 1

    def test_multiple_overlaps_counted(self):
        # Turn 2 and turn 3 both overlap their predecessor
        assert self._compute(
            ("A", 0, 2),
            ("B", 1.5, 3),   # overlaps A
            ("A", 2.8, 4),   # overlaps B
        ) == 2

    def test_sequential_turns_no_interruptions(self):
        assert self._compute(
            ("A", 0, 1), ("B", 1, 2), ("A", 2, 3)
        ) == 0

    def test_single_turn_zero_interruptions(self):
        assert self._compute(("A", 0, 5)) == 0

    def test_exact_boundary_not_interruption(self):
        # B starts exactly when A ends — not an interruption
        assert self._compute(("A", 0, 1), ("B", 1.0, 2)) == 0


class TestComputeHesitationCount:

    def _compute(self, pauses, threshold=1.0):
        from pipeline import compute_hesitation_count
        df = pd.DataFrame({"pause_before_sec": pauses})
        return compute_hesitation_count(df, threshold)

    def test_pauses_above_threshold_counted(self):
        assert self._compute([0.5, 1.5, 0.3, 2.0]) == 2

    def test_pauses_at_threshold_not_counted(self):
        assert self._compute([1.0, 1.0]) == 0  # > threshold, not >=

    def test_no_hesitations(self):
        assert self._compute([0.1, 0.2, 0.3]) == 0

    def test_all_hesitations(self):
        assert self._compute([2.0, 3.0, 1.5]) == 3

    def test_custom_threshold(self):
        assert self._compute([0.5, 0.8, 1.2], threshold=0.6) == 2

    def test_missing_column_returns_zero(self):
        from pipeline import compute_hesitation_count
        df = pd.DataFrame({"some_other_col": [1, 2, 3]})
        assert compute_hesitation_count(df) == 0

    def test_empty_series_returns_zero(self):
        assert self._compute([]) == 0


class TestComputeEngagementScore:

    def _compute(self, rows):
        from pipeline import compute_engagement_score
        df = pd.DataFrame(rows)
        return compute_engagement_score(df)

    def test_empty_dataframe_returns_zero(self):
        from pipeline import compute_engagement_score
        assert compute_engagement_score(pd.DataFrame()) == 0.0

    def test_returns_float(self):
        rows = [
            {"energy_mean": 0.03, "speech_rate_proxy": 0.5, "pause_before_sec": 0.4},
        ]
        assert isinstance(self._compute(rows), float)

    def test_score_in_valid_range(self):
        rows = [
            {"energy_mean": 0.05, "speech_rate_proxy": 0.8, "pause_before_sec": 0.2},
            {"energy_mean": 0.04, "speech_rate_proxy": 0.6, "pause_before_sec": 0.3},
        ]
        score = self._compute(rows)
        assert 0.0 <= score <= 100.0

    def test_high_energy_high_rate_low_pause_gives_high_score(self):
        rows = [
            {"energy_mean": 0.10, "speech_rate_proxy": 0.90, "pause_before_sec": 0.1},
            {"energy_mean": 0.08, "speech_rate_proxy": 0.85, "pause_before_sec": 0.1},
        ]
        score = self._compute(rows)
        assert score > 70.0

    def test_low_energy_low_rate_high_pause_gives_low_score(self):
        rows = [
            {"energy_mean": 0.001, "speech_rate_proxy": 0.01, "pause_before_sec": 5.0},
            {"energy_mean": 0.001, "speech_rate_proxy": 0.01, "pause_before_sec": 4.0},
        ]
        score = self._compute(rows)
        assert score < 30.0

    def test_formula_weights_correct(self):
        # energy=0.05 → energy_score=1.0, rate=0.80 → rate_score=1.0, pause=0 → pause_score=1.0
        # score = 0.4*1.0 + 0.3*1.0 + 0.3*1.0 = 1.0 → 100.0
        rows = [
            {"energy_mean": 0.05, "speech_rate_proxy": 0.80, "pause_before_sec": 0.0},
        ]
        score = self._compute(rows)
        assert score == pytest.approx(100.0, abs=1.0)


class TestLabelConversationFlow:

    def _label(self, pause):
        from pipeline import label_conversation_flow
        return label_conversation_flow(pause)

    def test_low_pause_is_smooth(self):
        assert self._label(0.3) == "smooth"
        assert self._label(0.0) == "smooth"
        assert self._label(0.59) == "smooth"

    def test_boundary_0_6_is_smooth(self):
        # > 0.6 triggers moderate — exactly 0.6 is NOT > 0.6, so it's still smooth
        assert self._label(0.6) == "smooth"
        assert self._label(0.61) == "moderate"

    def test_mid_range_is_moderate(self):
        assert self._label(0.8) == "moderate"
        assert self._label(0.99) == "moderate"

    def test_boundary_1_0_is_moderate(self):
        # > 1.0 triggers poor — exactly 1.0 is NOT > 1.0, so it's moderate
        assert self._label(1.0) == "moderate"
        assert self._label(1.01) == "poor"

    def test_high_pause_is_poor(self):
        assert self._label(1.5) == "poor"
        assert self._label(5.0) == "poor"

    def test_returns_string(self):
        assert isinstance(self._label(0.5), str)

    def test_all_valid_values(self):
        valid = {"smooth", "moderate", "poor"}
        for v in [0.0, 0.5, 0.6, 0.8, 1.0, 1.5]:
            assert self._label(v) in valid


class TestComputeSentimentTrajectory:

    def _compute(self, df):
        from pipeline import compute_sentiment_trajectory
        return compute_sentiment_trajectory(df)

    def test_fewer_than_3_turns_returns_stable(self):
        df = make_featured_turns(
            ("A", "agent",    0, 2, 0.05, 200, 0.5),
            ("B", "customer", 3, 5, 0.03, 180, 0.8),
        )
        assert self._compute(df) == "stable"

    def test_rising_energy_returns_improving(self):
        # First turn energy 0.01, last turn energy 0.05 → >15% increase
        df = make_featured_turns(
            ("B", "customer", 0,  2,  0.01, 180, 0.0),
            ("A", "agent",    3,  5,  0.04, 200, 0.5),
            ("B", "customer", 6,  8,  0.05, 210, 0.3),
        )
        assert self._compute(df) == "improving"

    def test_falling_energy_returns_deteriorating(self):
        # First turn energy 0.05, last turn energy 0.01 → >15% decrease
        df = make_featured_turns(
            ("B", "customer", 0,  2,  0.05, 200, 0.0),
            ("A", "agent",    3,  5,  0.03, 190, 0.4),
            ("B", "customer", 6,  8,  0.01, 170, 0.5),
        )
        assert self._compute(df) == "deteriorating"

    def test_stable_energy_returns_stable(self):
        # Same energy in first and last → stable
        df = make_featured_turns(
            ("B", "customer", 0,  2,  0.04, 200, 0.0),
            ("A", "agent",    3,  5,  0.04, 200, 0.3),
            ("B", "customer", 6,  8,  0.04, 200, 0.3),
        )
        assert self._compute(df) == "stable"

    def test_returns_one_of_three_values(self):
        valid = {"improving", "stable", "deteriorating"}
        df = make_featured_turns(
            ("B", "customer", 0, 2, 0.03, 180, 0.3),
            ("A", "agent",    3, 5, 0.04, 190, 0.4),
            ("B", "customer", 6, 8, 0.05, 200, 0.3),
        )
        assert self._compute(df) in valid


class TestBuildCallSummary:

    def _summary(self):
        from pipeline import build_call_summary, add_pause_features, add_speaking_rate
        df = make_featured_turns(
            ("A", "agent",    0,  5,  0.04, 200, 0.0),
            ("B", "customer", 6,  10, 0.03, 180, 1.0),
            ("A", "agent",    11, 15, 0.05, 210, 1.0),
            ("B", "customer", 16, 18, 0.02, 160, 1.0),
        )
        return build_call_summary(df, "/fake/path/audio.wav")

    def test_returns_dict(self):
        assert isinstance(self._summary(), dict)

    def test_required_keys_present(self):
        s = self._summary()
        required = [
            "file_name", "num_speakers", "total_turns", "total_duration_sec",
            "total_silence_sec", "avg_pause_sec", "silence_ratio",
            "agent_talk_time_sec", "customer_talk_time_sec",
            "interruption_count", "hesitation_count", "engagement_score",
            "conversation_flow", "sentiment_trajectory",
            "agent_dominance_ratio", "avg_energy", "avg_pitch_hz",
        ]
        for key in required:
            assert key in s, f"Missing key: {key}"

    def test_file_name_extracted_from_path(self):
        s = self._summary()
        assert s["file_name"] == "audio.wav"

    def test_silence_ratio_between_0_and_1(self):
        s = self._summary()
        assert 0.0 <= s["silence_ratio"] <= 1.0

    def test_engagement_score_in_valid_range(self):
        s = self._summary()
        assert 0.0 <= s["engagement_score"] <= 100.0

    def test_conversation_flow_valid_value(self):
        s = self._summary()
        assert s["conversation_flow"] in ("smooth", "moderate", "poor")

    def test_sentiment_trajectory_valid_value(self):
        s = self._summary()
        assert s["sentiment_trajectory"] in ("improving", "stable", "deteriorating")

    def test_total_turns_matches_dataframe_rows(self):
        s = self._summary()
        assert s["total_turns"] == 4

    def test_num_speakers_correct(self):
        s = self._summary()
        assert s["num_speakers"] == 2

    def test_agent_dominance_ratio_positive(self):
        s = self._summary()
        assert s["agent_dominance_ratio"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 2 — ACOUSTIC FEATURE TESTS  (CPU + real .wav file)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.skipif(not os.path.exists(SMALL_WAV), reason="Real audio file not found")
class TestAddAcousticFeatures:
    """add_acoustic_features() uses librosa which always runs on CPU."""

    def _df_for_audio(self):
        """Synthetic turns that cover the first 10 seconds of the audio."""
        df = make_turns(
            ("A", 0.0, 3.0),
            ("B", 3.5, 7.0),
            ("A", 7.5, 10.0),
        )
        df["role"] = ["agent", "customer", "agent"]
        return df

    def test_energy_column_added(self):
        from pipeline import add_acoustic_features
        df = self._df_for_audio()
        result = add_acoustic_features(SMALL_WAV, df)
        assert "energy_mean" in result.columns

    def test_pitch_column_added(self):
        from pipeline import add_acoustic_features
        df = self._df_for_audio()
        result = add_acoustic_features(SMALL_WAV, df)
        assert "pitch_mean_hz" in result.columns

    def test_energy_values_are_non_negative(self):
        from pipeline import add_acoustic_features
        df = self._df_for_audio()
        result = add_acoustic_features(SMALL_WAV, df)
        valid = result["energy_mean"].dropna()
        assert (valid >= 0).all()

    def test_row_count_preserved(self):
        from pipeline import add_acoustic_features
        df = self._df_for_audio()
        result = add_acoustic_features(SMALL_WAV, df)
        assert len(result) == 3

    def test_original_columns_preserved(self):
        from pipeline import add_acoustic_features
        df = self._df_for_audio()
        result = add_acoustic_features(SMALL_WAV, df)
        for col in ["speaker", "start_sec", "end_sec", "duration_sec"]:
            assert col in result.columns


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — GPU INTEGRATION  (full pyannote pipeline)
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.gpu
@pytest.mark.skipif(not os.path.exists(SMALL_WAV), reason="Real audio file not found")
class TestProcessCall:
    """
    Full end-to-end pipeline: pyannote diarisation on GPU → acoustic features
    → all composite metrics. Requires HF_TOKEN env var and CUDA.

    Run only with: pytest tests/test_pipeline.py -m gpu
    Skip with:     pytest tests/test_pipeline.py -m "not gpu"
    """

    @pytest.fixture(scope="class")
    def pipeline_and_result(self):
        """Load the pyannote pipeline once and run process_call on the small file."""
        from pipeline import load_pipeline, process_call
        pipe = load_pipeline()
        turn_df, summary = process_call(SMALL_WAV, pipe)
        return turn_df, summary

    def test_process_call_returns_tuple(self, pipeline_and_result):
        turn_df, summary = pipeline_and_result
        assert isinstance(turn_df, pd.DataFrame)
        assert isinstance(summary, dict)

    def test_turn_dataframe_is_not_empty(self, pipeline_and_result):
        turn_df, _ = pipeline_and_result
        assert len(turn_df) > 0

    def test_turn_dataframe_has_required_columns(self, pipeline_and_result):
        turn_df, _ = pipeline_and_result
        required = ["speaker", "start_sec", "end_sec", "duration_sec", "role",
                    "energy_mean", "pitch_mean_hz", "pause_before_sec"]
        for col in required:
            assert col in turn_df.columns, f"Missing column: {col}"

    def test_roles_assigned(self, pipeline_and_result):
        turn_df, _ = pipeline_and_result
        assert "role" in turn_df.columns
        assert set(turn_df["role"].unique()).issubset({"agent", "customer", "other"})

    def test_start_before_end_all_turns(self, pipeline_and_result):
        turn_df, _ = pipeline_and_result
        assert (turn_df["start_sec"] < turn_df["end_sec"]).all()

    def test_duration_positive_all_turns(self, pipeline_and_result):
        turn_df, _ = pipeline_and_result
        assert (turn_df["duration_sec"] > 0).all()

    def test_summary_has_required_keys(self, pipeline_and_result):
        _, summary = pipeline_and_result
        required = [
            "engagement_score", "silence_ratio", "conversation_flow",
            "sentiment_trajectory", "interruption_count", "hesitation_count",
            "total_turns", "agent_talk_time_sec", "customer_talk_time_sec",
            "avg_energy", "avg_pitch_hz",
        ]
        for key in required:
            assert key in summary, f"Missing key: {key}"

    def test_engagement_score_in_valid_range(self, pipeline_and_result):
        _, summary = pipeline_and_result
        assert 0.0 <= summary["engagement_score"] <= 100.0

    def test_silence_ratio_between_0_and_1(self, pipeline_and_result):
        _, summary = pipeline_and_result
        assert 0.0 <= summary["silence_ratio"] <= 1.0

    def test_conversation_flow_is_valid(self, pipeline_and_result):
        _, summary = pipeline_and_result
        assert summary["conversation_flow"] in ("smooth", "moderate", "poor")

    def test_sentiment_trajectory_is_valid(self, pipeline_and_result):
        _, summary = pipeline_and_result
        assert summary["sentiment_trajectory"] in ("improving", "stable", "deteriorating")

    def test_interruption_count_non_negative(self, pipeline_and_result):
        _, summary = pipeline_and_result
        assert summary["interruption_count"] >= 0

    def test_hesitation_count_non_negative(self, pipeline_and_result):
        _, summary = pipeline_and_result
        assert summary["hesitation_count"] >= 0

    def test_agent_and_customer_talk_times_positive(self, pipeline_and_result):
        _, summary = pipeline_and_result
        assert summary["agent_talk_time_sec"] >= 0
        assert summary["customer_talk_time_sec"] >= 0

    def test_talk_times_dont_exceed_total_duration(self, pipeline_and_result):
        _, summary = pipeline_and_result
        total = summary["agent_talk_time_sec"] + summary["customer_talk_time_sec"]
        assert total <= summary["total_duration_sec"] + 0.1  # small float tolerance

    def test_turns_are_sorted_by_start_time(self, pipeline_and_result):
        turn_df, _ = pipeline_and_result
        starts = list(turn_df["start_sec"])
        assert starts == sorted(starts)
