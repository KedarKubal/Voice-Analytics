"""
pipeline.py  —  Heya AI Voice Analytics
Audio processing pipeline: diarisation → acoustic features → call summary

This is the importable production module extracted from v6_heya_pipeline.ipynb.
Your notebook is for exploration. This file is for everything else.

Usage:
    from pipeline import load_pipeline, process_call, process_folder

Quick start:
    from pipeline import load_pipeline, process_call, SAMPLE_RATE
    pipe = load_pipeline()
    turn_df, summary = process_call("audio/call_001.wav", pipe, SAMPLE_RATE)
"""

import os
import time
import warnings
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import librosa
import torch
import torchaudio
from dotenv import load_dotenv
from pyannote.audio import Pipeline

warnings.filterwarnings("ignore")

# ── Load .env file if it exists ───────────────────────────────────────────────
load_dotenv()


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG  —  everything in one place, easy to change
# ═══════════════════════════════════════════════════════════════════════════════
SAMPLE_RATE    = 16000
OUTPUT_FOLDER  = "pipeline_output"
DEVICE         = torch.device("cuda" if torch.cuda.is_available() else "cpu")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# ═══════════════════════════════════════════════════════════════════════════════
# GPU HELPERS
# ═══════════════════════════════════════════════════════════════════════════════
def log_gpu_memory(label: str = "") -> None:
    """Print current GPU memory usage. Silent on CPU."""
    if DEVICE.type != "cuda":
        return
    allocated = torch.cuda.memory_allocated(0) / 1e6
    reserved  = torch.cuda.memory_reserved(0)  / 1e6
    print(f"  GPU [{label}] → allocated: {allocated:.0f} MB | reserved: {reserved:.0f} MB")


def print_device_info() -> None:
    """Print what device the pipeline is running on."""
    print(f"Device : {DEVICE}")
    if DEVICE.type == "cuda":
        print(f"GPU    : {torch.cuda.get_device_name(0)}")
        vram = torch.cuda.get_device_properties(0).total_memory / 1e9
        print(f"VRAM   : {vram:.1f} GB")
    else:
        print("Running on CPU — consider installing CUDA PyTorch for 4x speedup")


# ═══════════════════════════════════════════════════════════════════════════════
# PIPELINE LOADER
# ═══════════════════════════════════════════════════════════════════════════════
def load_pipeline(hf_token: Optional[str] = None) -> Pipeline:
    """
    Load pyannote speaker diarisation pipeline onto GPU (or CPU).

    Args:
        hf_token: HuggingFace token. If None, reads from HF_TOKEN env var.

    Returns:
        pyannote Pipeline ready to run

    Example:
        pipe = load_pipeline()
        # or with explicit token:
        pipe = load_pipeline(hf_token="hf_xxx")
    """
    token = hf_token or os.getenv("HF_TOKEN", "")

    if not token:
        raise ValueError(
            "HF_TOKEN is empty.\n"
            "Set it in your .env file:  HF_TOKEN=hf_your_token_here\n"
            "Or pass it directly:       load_pipeline(hf_token='hf_xxx')"
        )

    print("Loading pyannote diarisation pipeline...")
    log_gpu_memory("before load")

    try:
        pipe = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token,
        )
    except TypeError:
        pipe = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
    pipe.to(DEVICE)

    log_gpu_memory("after load")
    print(f"✅ Pipeline ready on {DEVICE}")
    return pipe


# ═══════════════════════════════════════════════════════════════════════════════
# AUDIO LOADING
# ═══════════════════════════════════════════════════════════════════════════════
def load_audio_for_pyannote(audio_path: str, target_sr: int = 16000) -> dict:
    """
    Load audio file, convert to mono, resample to target_sr,
    and move waveform to the same device as the pipeline.

    Returns dict expected by pyannote: {"waveform": tensor, "sample_rate": int}
    """
    waveform, sample_rate = torchaudio.load(audio_path)

    # Convert stereo → mono
    if waveform.shape[0] > 1:
        waveform = torch.mean(waveform, dim=0, keepdim=True)

    # Resample if needed
    if sample_rate != target_sr:
        resampler = torchaudio.transforms.Resample(
            orig_freq=sample_rate, new_freq=target_sr
        )
        waveform = resampler(waveform)

    return {"waveform": waveform.to(DEVICE), "sample_rate": target_sr}


# ═══════════════════════════════════════════════════════════════════════════════
# DIARISATION → DATAFRAME
# ═══════════════════════════════════════════════════════════════════════════════
def build_turn_dataframe(diarization_result) -> pd.DataFrame:
    """
    Convert pyannote diarisation result into a clean DataFrame.
    One row per speaker turn.
    """
    rows = []
    for segment, _, speaker in diarization_result.itertracks(yield_label=True):
        rows.append({
            "speaker":      speaker,
            "start_sec":    float(segment.start),
            "end_sec":      float(segment.end),
            "duration_sec": float(segment.end - segment.start),
        })

    if not rows:
        return pd.DataFrame(columns=["speaker", "start_sec", "end_sec", "duration_sec"])

    return pd.DataFrame(rows).sort_values("start_sec").reset_index(drop=True)


def merge_adjacent_same_speaker(turn_df: pd.DataFrame,
                                 gap_threshold: float = 0.3) -> pd.DataFrame:
    """
    Merge consecutive turns by the same speaker if the gap between them
    is smaller than gap_threshold seconds.
    Avoids over-segmentation from diarisation.
    """
    if turn_df.empty:
        return turn_df.copy()

    rows    = []
    current = turn_df.iloc[0].to_dict()

    for i in range(1, len(turn_df)):
        nxt       = turn_df.iloc[i].to_dict()
        same_spk  = nxt["speaker"] == current["speaker"]
        small_gap = (nxt["start_sec"] - current["end_sec"]) <= gap_threshold

        if same_spk and small_gap:
            current["end_sec"]      = nxt["end_sec"]
            current["duration_sec"] = current["end_sec"] - current["start_sec"]
        else:
            rows.append(current)
            current = nxt

    rows.append(current)
    return pd.DataFrame(rows).reset_index(drop=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ROLE ASSIGNMENT
# ═══════════════════════════════════════════════════════════════════════════════
def assign_roles(turn_df: pd.DataFrame) -> pd.DataFrame:
    """
    Label each turn as 'agent' or 'customer'.
    Agent = speaker with the most total talk time.
    This is the standard assumption for inbound call-centre audio.
    """
    turn_df = turn_df.copy()
    totals  = turn_df.groupby("speaker")["duration_sec"].sum().sort_values(ascending=False)

    if len(totals) < 2:
        print("  ⚠ Only 1 speaker detected — all turns marked as agent")
        turn_df["role"] = "agent"
        return turn_df

    turn_df["role"] = turn_df["speaker"].map({
        totals.index[0]: "agent",
        totals.index[1]: "customer",
    }).fillna("other")

    return turn_df


# ═══════════════════════════════════════════════════════════════════════════════
# FEATURE EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════════
def add_pause_features(turn_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add pause_before_sec column — the silence gap before each turn starts.
    This captures hesitation and response latency.
    """
    turn_df      = turn_df.copy()
    pauses       = []
    previous_end = 0.0

    for _, row in turn_df.iterrows():
        pause = max(0.0, row["start_sec"] - previous_end)
        pauses.append(round(pause, 3))
        previous_end = row["end_sec"]

    turn_df["pause_before_sec"] = pauses
    return turn_df


def add_acoustic_features(audio_path: str,
                           turn_df: pd.DataFrame,
                           sr: int = 16000) -> pd.DataFrame:
    """
    Extract per-turn acoustic features using librosa (always runs on CPU).
    Adds: energy_mean (RMS), pitch_mean_hz (F0)

    Why these features:
        energy_mean  → vocal emphasis, stress, confidence
        pitch_mean_hz → emotional arousal, frustration indicators
    """
    y, sr = librosa.load(audio_path, sr=sr, mono=True)

    energy_means, pitch_means = [], []

    for _, row in turn_df.iterrows():
        s   = int(row["start_sec"] * sr)
        e   = int(row["end_sec"]   * sr)
        seg = y[s:e]

        if len(seg) == 0:
            energy_means.append(np.nan)
            pitch_means.append(np.nan)
            continue

        # RMS energy — correlates with vocal loudness and emphasis
        rms = librosa.feature.rms(y=seg)[0]
        energy_means.append(float(np.mean(rms)) if len(rms) > 0 else np.nan)

        # Fundamental frequency (pitch) — correlates with emotional state
        try:
            f0, _, _ = librosa.pyin(
                seg,
                fmin=librosa.note_to_hz("C2"),
                fmax=librosa.note_to_hz("C7"),
            )
            valid_f0 = f0[~np.isnan(f0)]
            pitch_means.append(float(np.mean(valid_f0)) if len(valid_f0) > 0 else np.nan)
        except Exception:
            pitch_means.append(np.nan)

    turn_df = turn_df.copy()
    turn_df["energy_mean"]   = energy_means
    turn_df["pitch_mean_hz"] = pitch_means
    return turn_df


def add_speaking_rate(turn_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add speech_rate_proxy column.
    Proxy = 1 / duration — higher value means shorter, faster turns.
    A true syllable-per-second rate requires ASR (Whisper) to compute properly.
    """
    turn_df = turn_df.copy()
    turn_df["speech_rate_proxy"] = 1 / (turn_df["duration_sec"] + 1e-6)
    return turn_df


def add_behavior_labels(turn_df: pd.DataFrame) -> pd.DataFrame:
    """
    Add boolean flag columns for dashboard filtering.
    is_long_turn   → turns > 3 seconds (monologues, explanations)
    is_high_energy → above-average RMS (emphasis, stress, frustration)
    is_high_pitch  → above-average F0 (arousal, nervousness)
    """
    turn_df = turn_df.copy()
    turn_df["is_long_turn"]   = turn_df["duration_sec"]  > 3
    turn_df["is_high_energy"] = turn_df["energy_mean"]   > turn_df["energy_mean"].mean()
    turn_df["is_high_pitch"]  = turn_df["pitch_mean_hz"] > turn_df["pitch_mean_hz"].mean()
    return turn_df


# ═══════════════════════════════════════════════════════════════════════════════
# COMPOSITE METRICS
# ═══════════════════════════════════════════════════════════════════════════════
def compute_interruptions(turn_df: pd.DataFrame) -> int:
    """
    Count turns where a speaker started before the previous speaker finished.
    These are interruptions — key friction signal in customer service calls.
    """
    count = 0
    for i in range(1, len(turn_df)):
        if turn_df.iloc[i]["start_sec"] < turn_df.iloc[i - 1]["end_sec"]:
            count += 1
    return count


def compute_hesitation_count(turn_df: pd.DataFrame,
                              threshold: float = 1.0) -> int:
    """
    Count pauses longer than threshold seconds.
    Long pauses = hesitation, uncertainty, or disengagement.
    Default threshold = 1.0 second (standard for call-centre analytics).
    """
    if "pause_before_sec" not in turn_df.columns:
        return 0
    return int((turn_df["pause_before_sec"] > threshold).sum())


def compute_engagement_score(turn_df: pd.DataFrame) -> float:
    """
    Composite engagement score from 0–100.

    Formula:
        40% weight → normalised RMS energy  (vocal presence)
        30% weight → normalised speech rate  (conversational pace)
        30% weight → inverted pause ratio    (low silence = high engagement)

    A score of 70+ is healthy for a business call.
    A score below 40 suggests disengagement or call quality issues.
    """
    if turn_df.empty:
        return 0.0

    avg_energy = turn_df["energy_mean"].mean(skipna=True)
    avg_rate   = turn_df["speech_rate_proxy"].mean(skipna=True)
    avg_pause  = turn_df["pause_before_sec"].mean(skipna=True)

    energy_score = min(avg_energy / 0.05, 1.0) if pd.notna(avg_energy) else 0.0
    rate_score   = min(avg_rate   / 0.80, 1.0) if pd.notna(avg_rate)   else 0.0
    pause_score  = 1.0 - min(avg_pause / 2.0, 1.0) if pd.notna(avg_pause) else 0.0

    score = (0.4 * energy_score) + (0.3 * rate_score) + (0.3 * pause_score)
    return round(score * 100, 2)


def label_conversation_flow(avg_pause_sec: float) -> str:
    """
    Human-readable conversation flow label based on average pause length.
    smooth   → avg pause < 0.6s  (natural, engaged conversation)
    moderate → avg pause 0.6–1.0s (some hesitation)
    poor     → avg pause > 1.0s  (significant hesitation or dead air)
    """
    if avg_pause_sec > 1.0:
        return "poor"
    elif avg_pause_sec > 0.6:
        return "moderate"
    return "smooth"


def compute_sentiment_trajectory(turn_df: pd.DataFrame) -> str:
    """
    Classify how caller engagement evolved over the call.

    Method: compare customer avg RMS energy in the first third of turns
    vs the last third. Energy is the most reliable per-turn acoustic proxy
    for engagement — rising energy at call end = caller more invested.

    Returns: "improving" | "stable" | "deteriorating"
    Threshold: ±15% change in energy between first and last third.
    """
    if len(turn_df) < 3:
        return "stable"

    third = max(len(turn_df) // 3, 1)
    first = turn_df.iloc[:third]
    last  = turn_df.iloc[-third:]

    # Prefer customer turns — caller sentiment is what the business cares about
    first_cust = first[first["role"] == "customer"]
    last_cust  = last[last["role"]  == "customer"]

    # Fall back to all turns if no customer turns in a segment
    if first_cust.empty: first_cust = first
    if last_cust.empty:  last_cust  = last

    e_first = first_cust["energy_mean"].mean(skipna=True)
    e_last  = last_cust["energy_mean"].mean(skipna=True)

    if pd.isna(e_first) or pd.isna(e_last) or e_first < 1e-8:
        return "stable"

    change = (e_last - e_first) / e_first

    if change >  0.15: return "improving"
    if change < -0.15: return "deteriorating"
    return "stable"


# ═══════════════════════════════════════════════════════════════════════════════
# CALL SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
def build_call_summary(turn_df: pd.DataFrame, audio_path: str) -> dict:
    """
    Build the call-level summary dictionary from a turn DataFrame.
    This dict maps directly to the audio_insights table in PostgreSQL.

    Returns dict with all keys needed by database.save_audio_insights()
    """
    summary = {}

    summary["file_name"]          = Path(audio_path).name
    summary["num_speakers"]       = int(turn_df["speaker"].nunique())
    summary["total_turns"]        = int(len(turn_df))
    summary["total_duration_sec"] = round(float(turn_df["duration_sec"].sum()), 2)
    summary["total_silence_sec"]  = round(float(turn_df["pause_before_sec"].sum()), 2)
    summary["avg_pause_sec"]      = round(float(turn_df["pause_before_sec"].mean()), 2)
    summary["silence_ratio"]      = round(
        summary["total_silence_sec"] /
        (summary["total_duration_sec"] + summary["total_silence_sec"] + 1e-6), 3
    )

    # Per-role stats
    for role in ["agent", "customer"]:
        rdf = turn_df[turn_df["role"] == role]
        summary[f"{role}_talk_time_sec"] = round(float(rdf["duration_sec"].sum()), 2)
        summary[f"{role}_num_turns"]     = int(len(rdf))

    # Composite metrics
    summary["interruption_count"]    = compute_interruptions(turn_df)
    summary["hesitation_count"]      = compute_hesitation_count(turn_df)
    summary["engagement_score"]      = compute_engagement_score(turn_df)
    summary["conversation_flow"]     = label_conversation_flow(summary["avg_pause_sec"])
    summary["sentiment_trajectory"]  = compute_sentiment_trajectory(turn_df)
    summary["agent_dominance_ratio"] = round(
        summary["agent_talk_time_sec"] / (summary["customer_talk_time_sec"] + 1e-6), 2
    )

    # Trajectory support data — energy in first vs last third of turns
    n     = len(turn_df)
    third = max(n // 3, 1)
    summary["trajectory_start_energy"] = round(
        float(turn_df.iloc[:third]["energy_mean"].mean(skipna=True)), 6
    )
    summary["trajectory_end_energy"] = round(
        float(turn_df.iloc[-third:]["energy_mean"].mean(skipna=True)), 6
    )

    # Acoustic averages — overall
    summary["avg_energy"]    = round(float(turn_df["energy_mean"].mean(skipna=True)), 6)
    summary["avg_pitch_hz"]  = round(float(turn_df["pitch_mean_hz"].mean(skipna=True)), 2)

    # Acoustic averages — per role
    for role in ["agent", "customer"]:
        rdf = turn_df[turn_df["role"] == role]
        summary[f"{role}_avg_energy"]   = round(float(rdf["energy_mean"].mean(skipna=True)), 6)
        summary[f"{role}_avg_pitch_hz"] = round(float(rdf["pitch_mean_hz"].mean(skipna=True)), 2)

    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════
def process_call(audio_path: str,
                 pipeline: Pipeline,
                 sample_rate: int = 16000) -> tuple[pd.DataFrame, dict]:
    """
    Run the full pipeline on a single audio file.

    Steps:
        1. Diarisation on GPU  → who spoke when
        2. Turn table cleanup  → merge gaps, filter short segments
        3. Role assignment     → agent vs customer
        4. Acoustic features   → energy, pitch (CPU)
        5. Behaviour labels    → flags for dashboard
        6. Call summary        → dict ready for DB insert

    Args:
        audio_path  : path to .wav / .mp3 / .flac file
        pipeline    : loaded pyannote Pipeline from load_pipeline()
        sample_rate : audio sample rate (default 16000)

    Returns:
        (turn_df, call_summary)
        turn_df      → pd.DataFrame, one row per speaker turn
        call_summary → dict, maps to audio_insights table

    Example:
        pipe = load_pipeline()
        turn_df, summary = process_call("calls/call_001.wav", pipe)
        print(summary["engagement_score"])
    """
    audio_path = str(audio_path)
    t0         = time.time()

    # ── Step 1: Diarisation on GPU ───────────────────────────────────────────
    audio_input = load_audio_for_pyannote(audio_path, sample_rate)
    diarization = pipeline(audio_input, num_speakers=2)

    # Free GPU cache — everything below is CPU
    if DEVICE.type == "cuda":
        torch.cuda.empty_cache()

    # ── Step 2: Build turn table ─────────────────────────────────────────────
    turn_df = build_turn_dataframe(diarization)

    if turn_df.empty:
        return pd.DataFrame(), {
            "file_name": Path(audio_path).name,
            "status":    "failed",
            "reason":    "no turns detected",
        }

    # ── Step 3: Cleanup + enrichment ─────────────────────────────────────────
    turn_df = merge_adjacent_same_speaker(turn_df)
    turn_df = turn_df[turn_df["duration_sec"] >= 0.3].reset_index(drop=True)
    turn_df = assign_roles(turn_df)
    turn_df = add_pause_features(turn_df)
    turn_df = add_acoustic_features(audio_path, turn_df, sr=sample_rate)
    turn_df = add_speaking_rate(turn_df)
    turn_df = add_behavior_labels(turn_df)

    # ── Step 4: Summary ──────────────────────────────────────────────────────
    call_summary                   = build_call_summary(turn_df, audio_path)
    call_summary["processing_sec"] = round(time.time() - t0, 1)
    call_summary["status"]         = "success"

    turn_df["file_name"] = Path(audio_path).name

    return turn_df, call_summary


def process_folder(folder_path: str,
                   pipeline: Pipeline,
                   sample_rate: int = 16000) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Run process_call() on every audio file in a folder.

    Returns:
        (all_turns_df, all_summaries_df)
        all_turns_df    → turn-level data for all calls combined
        all_summaries_df → one summary row per call

    Example:
        pipe = load_pipeline()
        turns, summaries = process_folder("sample_audio/", pipe)
        summaries.to_csv("results.csv", index=False)
    """
    folder      = Path(folder_path)
    audio_files = []
    for ext in ["*.wav", "*.mp3", "*.flac", "*.m4a"]:
        audio_files.extend(folder.glob(ext))
    audio_files = sorted(audio_files)

    if not audio_files:
        print(f"⚠ No audio files found in '{folder_path}'")
        return pd.DataFrame(), pd.DataFrame()

    print(f"\nFound {len(audio_files)} file(s) in '{folder_path}'")
    print("─" * 55)

    all_turns, all_summaries = [], []

    for idx, audio_file in enumerate(audio_files, 1):
        print(f"\n[{idx}/{len(audio_files)}] {audio_file.name}")
        log_gpu_memory("start")

        try:
            turn_df, summary = process_call(audio_file, pipeline, sample_rate)

            if not turn_df.empty:
                all_turns.append(turn_df)

            all_summaries.append(summary)

            if summary.get("status") == "success":
                print(f"  ✅ {summary['total_turns']} turns | "
                      f"engagement: {summary['engagement_score']} | "
                      f"flow: {summary['conversation_flow']} | "
                      f"{summary['processing_sec']}s")
            else:
                print(f"  ✗ {summary.get('reason', 'unknown error')}")

        except Exception as e:
            print(f"  ✗ Exception on {audio_file.name}: {e}")
            all_summaries.append({
                "file_name": audio_file.name,
                "status":    "failed",
                "reason":    str(e),
            })

        log_gpu_memory("end")

    turns_df     = pd.concat(all_turns, ignore_index=True) if all_turns else pd.DataFrame()
    summaries_df = pd.DataFrame(all_summaries)

    return turns_df, summaries_df


def save_csvs(turns_df: pd.DataFrame,
              summaries_df: pd.DataFrame,
              output_folder: str = OUTPUT_FOLDER) -> None:
    """Save pipeline output to CSV files."""
    os.makedirs(output_folder, exist_ok=True)

    turns_path     = os.path.join(output_folder, "all_turn_details.csv")
    summaries_path = os.path.join(output_folder, "all_call_summaries.csv")

    if not turns_df.empty:
        turns_df.to_csv(turns_path, index=False)
        print(f"✅ Turn details  → {turns_path}")

    if not summaries_df.empty:
        summaries_df.to_csv(summaries_path, index=False)
        print(f"✅ Call summaries → {summaries_path}")


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT  —  run directly to process your sample_audio folder
# python pipeline.py
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    print_device_info()
    print()

    pipe = load_pipeline()

    turns_df, summaries_df = process_folder("sample_audio", pipe, SAMPLE_RATE)

    save_csvs(turns_df, summaries_df)

    if not summaries_df.empty:
        successful = summaries_df[summaries_df["status"] == "success"]
        print(f"\n── Results ───────────────────────────────────────")
        print(f"Total files     : {len(summaries_df)}")
        print(f"Successful      : {len(successful)}")
        if not successful.empty:
            print(f"Avg engagement  : {successful['engagement_score'].mean():.1f}")
            print(f"Avg silence     : {successful['silence_ratio'].mean():.3f}")
            print(f"Avg interrupts  : {successful['interruption_count'].mean():.1f}")