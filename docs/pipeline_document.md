# Heya AI — Audio Processing Pipeline: Complete Technical Documentation

**Project:** Heya AI Voice Analytics Platform  
**Course:** RMIT COSC2667 / COSC2777 — Semester 4  
**Files:** `backend/pipeline.py`, `backend/ingest_dataset.py`, `backend/emotion_processor.py`, `backend/topic_classifier.py`, `backend/webhook_processor.py`, `backend/run_single_pipeline.py`  
**Last Updated:** 2026-06-02

---

## Table of Contents

1. [What the Pipeline Does](#1-what-the-pipeline-does)
2. [Full Architecture Overview](#2-full-architecture-overview)
3. [Conda Environment Requirements](#3-conda-environment-requirements)
4. [Dataset Structure](#4-dataset-structure)
5. [Ingestion — Phase 1 (Metadata & Transcripts)](#5-ingestion--phase-1-metadata--transcripts)
6. [Audio Pipeline — Phase 2 (GPU Processing)](#6-audio-pipeline--phase-2-gpu-processing)
7. [Every Processing Step in Detail](#7-every-processing-step-in-detail)
8. [Emotion Processing (emotion2vec)](#8-emotion-processing-emotion2vec)
9. [Topic Classification](#9-topic-classification)
10. [Webhook Ingestion (Live Calls)](#10-webhook-ingestion-live-calls)
11. [Database — What Gets Written Where](#11-database--what-gets-written-where)
12. [How to Run Everything](#12-how-to-run-everything)
13. [Processing Status Lifecycle](#13-processing-status-lifecycle)
14. [Known Limitations & Gotchas](#14-known-limitations--gotchas)

---

## 1. What the Pipeline Does

The audio processing pipeline converts raw AI voice agent call recordings into structured analytics data stored in PostgreSQL. It is the engine that produces all the numbers seen in the Heya AI dashboard.

**Input:** A `.wav` audio file of a phone call between an AI agent and a customer.

**Output written to PostgreSQL:**
- Speaker diarisation (who spoke when)
- Engagement score (0–100)
- Silence ratio (fraction of call that is silent)
- Interruption count
- Hesitation count (pauses > 1 second)
- Conversation flow label (smooth / moderate / poor)
- Sentiment trajectory (improving / stable / deteriorating)
- Average energy and pitch per speaker
- Agent vs customer talk time breakdown
- Dominant customer emotion (via separate emotion2vec pass)
- Call topic (via separate keyword classifier)

**Two demo clients processed:**
| Client | Client ID | Calls | Status |
|---|---|---|---|
| Artel Apartments | `client_heya_001` | 371 | All processed |
| MVAA Legal | `client_heya_002` | 421 | 419 processed, 2 skipped (empty hangups) |

---

## 2. Full Architecture Overview

```
Retell AI Platform
      │  webhook (live calls)
      │  OR dataset folder (bulk import)
      ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1 — Metadata Ingestion  (heya_audio or heya_v2 env) │
│                                                             │
│  metadata.json  →  calls table                             │
│                 →  call_metadata table                      │
│                 →  tool_calls table                         │
│                 →  agents table (if new)                    │
│  transcript.json→  transcript_utterances table             │
│                 →  transcript_words table                   │
│  audio.wav path →  recordings table                        │
│                                                             │
│  processing_status set to: "pending"                        │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 2 — Audio Pipeline  (heya_pipeline env, GPU)        │
│                                                             │
│  audio.wav                                                  │
│    │                                                        │
│    ├─ pyannote speaker diarisation (GPU)                    │
│    │    → turn DataFrame: who spoke when                    │
│    │                                                        │
│    ├─ merge adjacent same-speaker turns                     │
│    ├─ filter turns < 0.3s                                   │
│    ├─ assign agent / customer roles                         │
│    ├─ add pause features (silence gaps)                     │
│    ├─ add acoustic features: energy + pitch (CPU, librosa)  │
│    ├─ add speaking rate proxy                               │
│    └─ add behaviour flags (long turn, high energy, pitch)   │
│                                                             │
│  build_call_summary() computes:                             │
│    engagement_score  silence_ratio  interruption_count      │
│    hesitation_count  conversation_flow  sentiment_trajectory│
│    avg_energy  avg_pitch_hz  agent/customer talk times      │
│                                                             │
│  save_audio_insights(call_id, summary)  →  audio_insights  │
│  processing_status set to: "completed"                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 3 — Emotion Processing  (heya_pipeline env, GPU)    │
│                                                             │
│  For each transcript utterance with word-timing data:       │
│    audio slice  →  emotion2vec_plus_large  →  emotion label │
│                                                             │
│  Per call: compute dominant customer emotion               │
│  → audio_insights.dominant_emotion                         │
│  → audio_insights.dominant_emotion_score                   │
│  → transcript_utterances.emotion (per utterance)           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  PHASE 4 — Topic Classification  (heya_audio env, CPU)     │
│                                                             │
│  call transcript text  →  keyword scoring  →  topic label   │
│  → calls.topic                                             │
│  → calls.topic_confidence                                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Conda Environment Requirements

| Phase | Env | Why that env |
|---|---|---|
| Phase 1 — metadata ingestion | `heya_audio` or `heya_v2` | Only needs SQLAlchemy + json parsing |
| Phase 2 — audio pipeline | **`heya_pipeline`** | Has torch 2.5.1+cu121, pyannote 3.x, librosa, torchaudio |
| Phase 3 — emotion processing | **`heya_pipeline`** | Has FunASR (emotion2vec), soundfile |
| Phase 4 — topic classification | `heya_audio` or `heya_v2` | CPU only, no special packages needed |
| Web API (FastAPI) | `heya_v2` | Unified single env for web server |

**Critical:** Never run Phase 2 or 3 from `heya_audio` or `heya_v2` — they have torch version conflicts that prevent pyannote from loading.

**Always set encoding on Windows before running:**
```powershell
$env:PYTHONIOENCODING = "utf-8"
```

---

## 4. Dataset Structure

```
project/
└── dataset/
    ├── artel_apartments/
    │   └── recordings/
    │       ├── call_01522047922e22a77a4e5aea40f/
    │       │   ├── audio.wav          ← raw call recording (16kHz mono)
    │       │   ├── metadata.json      ← Retell call metadata (agent, sentiment, cost...)
    │       │   └── transcript.json    ← utterances + word-level timestamps
    │       ├── call_037f9a7f2d7a7c25fd844ffb16a/
    │       │   └── ...
    │       └── ... (371 total)
    └── mvaa_legal/
        └── recordings/
            └── ... (421 total)
```

**`metadata.json` structure (Retell format):**
```json
{
  "call": {
    "call_id":       "call_xxx",
    "agent_id":      "agent_yyy",
    "direction":     "inbound",
    "call_type":     "web_call",
    "call_status":   "ended",
    "from_number":   "+61...",
    "to_number":     "+61...",
    "start_timestamp": 1700000000000,
    "end_timestamp":   1700001800000,
    "duration_ms":     60000,
    "transcript":      "Agent: Hello...",
    "call_analysis": {
      "call_summary":    "Customer called about booking...",
      "user_sentiment":  "Positive",
      "call_successful": true
    },
    "call_cost": { "combined_cost": 0.042, "product_costs": [...] },
    "tool_calls": [],
    "latency": { "llm": {"p50": 850}, "e2e": {"p50": 1200} }
  }
}
```

**`transcript.json` structure:**
```json
[
  {
    "role":    "agent",
    "content": "Hello, thank you for calling Artel Apartments.",
    "words": [
      {"word": "Hello", "start": 0.24, "end": 0.56},
      {"word": "thank", "start": 0.60, "end": 0.80},
      ...
    ]
  },
  {
    "role":    "user",
    "content": "Hi, I'd like to make a booking.",
    "words": [...]
  }
]
```

Word-level timestamps (start/end in seconds) are critical — they are used by the emotion processor to slice the audio per utterance.

---

## 5. Ingestion — Phase 1 (Metadata & Transcripts)

**File:** `backend/ingest_dataset.py`  
**Env:** `heya_audio` or `heya_v2`  
**GPU needed:** No

Phase 1 reads the JSON files and populates all non-audio tables. It is fast (~1 second per call) and must complete before Phase 2 can run.

### 5.1 What Phase 1 Does Per Call

```
call_xxx/
├── metadata.json ──→ ensure_client_exists()    → clients table
│                ──→ ensure_agent_exists()      → agents table
│                ──→ ingest_metadata()          → calls table
│                                               → call_metadata table
│                                               → tool_calls table
├── transcript.json ─→ ingest_transcript()      → transcript_utterances table
│                                               → transcript_words table
└── audio.wav path ──→ ingest_recording_path() → recordings table
```

### 5.2 `ensure_client_exists()`

Inserts a `clients` row if it doesn't already exist. Called once per client at the start of the batch.

```python
Client(id="client_heya_001", name="Artel Apartments", folder_name="artel_apartments")
```

### 5.3 `ensure_agent_exists()`

Inserts an `agents` row keyed on `agent_id` from the Retell metadata. The agent FK must exist before the call row is inserted. Note: `agent.persona_name` (Sasha, Justine, etc.) is set separately via a migration — `ingest_dataset.py` only sets `agent.name` which is the generic Retell agent name.

### 5.4 `ingest_metadata()`

Reads `metadata.json` and inserts:

**`calls` table — key fields mapped:**

| DB column | Source in metadata.json | Notes |
|---|---|---|
| `id` | `call.call_id` | Primary key |
| `client_id` | Config (not in JSON) | Set from CLIENTS config |
| `agent_id` | `call.agent_id` | FK → agents |
| `direction` | `call.direction` | "inbound" or "outbound" |
| `start_timstamp` | `call.start_timestamp` | ⚠ One `t` — DB typo, never fix |
| `duration_ms` | `call.duration_ms` | Call length in ms |
| `call_summary` | `call.call_analysis.call_summary` | AI-generated prose |
| `user_sentiment` | `call.call_analysis.user_sentiment` | "Positive"/"Neutral"/"Negative" |
| `call_successful` | `call.call_analysis.call_successful` | Boolean |
| `processing_status` | Hardcoded | Set to `"pending"` on insert |
| `total_cost` | `call.call_cost.combined_cost` | Float |

**`call_metadata` table:** Stores latency percentiles (LLM p50/p99, E2E p50/p99), token usage estimates, cost breakdown per product, and the full `call_analysis` blob as JSONB.

> **Typo note:** The `call_metadata` table has a column `disconnectio_rason` (missing letter, wrong spelling). This is preserved intentionally — fixing it would require a migration and break existing data. The Python code maps `disconnection_reason` from JSON to this misspelled column name.

**`tool_calls` table:** One row per tool call in the Retell transcript (usually empty for most calls).

### 5.5 `ingest_transcript()`

Reads `transcript.json` and inserts:

**`transcript_utterances`** — one row per speech turn:
- Skips `tool_call_invocation` and `tool_call_result` roles
- Normalises roles: `"agent"` → `"agent"`, everything else → `"user"`
- Deletes existing utterances for the call before re-inserting (idempotent)

**`transcript_words`** — one row per word with timing:
- `start_time_sec` and `end_time_sec` from Retell's word-level timestamps
- These timestamps are used by `emotion_processor.py` to slice audio per utterance

### 5.6 `ingest_recording_path()`

Inserts a `recordings` row with the absolute file path to `audio.wav`. This path is read by `emotion_processor.py` when it needs to load the audio file.

### 5.7 Running Phase 1

```powershell
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project\backend

# All calls, both clients
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" ingest_dataset.py --phase 1

# First 5 calls only (testing)
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" ingest_dataset.py --phase 1 --limit 5

# Check what's in the DB
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" ingest_dataset.py --summary
```

---

## 6. Audio Pipeline — Phase 2 (GPU Processing)

**File:** `backend/pipeline.py` (core logic), `backend/ingest_dataset.py` (runner)  
**Env:** `heya_pipeline` (torch 2.5.1+cu121, pyannote 3.x, librosa)  
**GPU needed:** Yes (pyannote diarisation runs on CUDA)

Phase 2 is the computationally expensive step. Each call takes 30–120 seconds depending on audio length and GPU speed.

### 6.1 Entry Points

| Script | Use case |
|---|---|
| `ingest_dataset.py --phase 2` | Bulk process all calls in the dataset |
| `run_single_pipeline.py` | Process one specific call by ID |
| `POST /process-call` (FastAPI) | Process via HTTP (same env restriction applies) |

### 6.2 The `load_pipeline()` Function

```python
def load_pipeline(hf_token: Optional[str] = None) -> Pipeline:
    token = hf_token or os.getenv("HF_TOKEN", "")
    try:
        pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", token=token)
    except TypeError:
        pipe = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1", use_auth_token=token)
    pipe.to(DEVICE)  # GPU if available
    return pipe
```

- Loads `pyannote/speaker-diarization-3.1` from HuggingFace
- Requires `HF_TOKEN` env var (set in `backend/.env`)
- Tries `token=` first (newer huggingface_hub), falls back to `use_auth_token=` (older)
- Moves the model to GPU if CUDA is available
- Load time: ~15–30 seconds (downloads model weights on first run, cached after)
- Should be called **once** and the pipeline object reused across all calls

### 6.3 The `process_call()` Function

The main function. Takes one audio file and a loaded pipeline, returns `(turn_df, summary)`.

```python
def process_call(audio_path: str, pipeline: Pipeline, sample_rate: int = 16000)
    -> tuple[pd.DataFrame, dict]
```

**Return values:**
- `turn_df` — pandas DataFrame, one row per speaker turn (see §7 for all columns)
- `summary` — dict mapping directly to `audio_insights` table columns

---

## 7. Every Processing Step in Detail

### Step 1 — Speaker Diarisation (GPU)

```python
audio_input = load_audio_for_pyannote(audio_path, sample_rate)
diarization = pipeline(audio_input, num_speakers=2)
```

**`load_audio_for_pyannote()`** prepares the audio for pyannote:
- Loads with `torchaudio.load()`
- Converts to mono (averages channels if stereo)
- Resamples to `target_sr` (16000 Hz) if needed
- Returns `{"waveform": tensor, "sample_rate": sr}`

**`pipeline(audio_input, num_speakers=2)`** runs pyannote on GPU:
- `num_speakers=2` is hardcoded — business calls always have exactly 2 parties (agent + customer)
- Returns a pyannote `Annotation` object with speaker segments
- After completion, `torch.cuda.empty_cache()` is called to free GPU memory — all subsequent steps run on CPU

**`build_turn_dataframe(diarization_result)`** converts the pyannote result into a DataFrame:

```
speaker | start_sec | end_sec | duration_sec
─────────────────────────────────────────────
SPEAKER_00 | 0.24  | 3.80 | 3.56
SPEAKER_01 | 4.10  | 6.20 | 2.10
SPEAKER_00 | 6.80  | 9.40 | 2.60
...
```

If the result contains zero turns → returns empty DataFrame + `{"status": "failed", "reason": "no turns detected"}`.

---

### Step 2 — Turn Cleanup

```python
turn_df = merge_adjacent_same_speaker(turn_df)
turn_df = turn_df[turn_df["duration_sec"] >= 0.3].reset_index(drop=True)
```

**`merge_adjacent_same_speaker(turn_df, gap_threshold=0.3)`:**
- Merges consecutive turns by the same speaker if the gap between them is ≤ 0.3 seconds
- Prevents over-segmentation from pyannote (very short gaps within one person speaking)
- `gap_threshold=0.3` is the standard call-centre value

**Minimum duration filter (`>= 0.3s`):**
- Removes very short artifacts (< 0.3 seconds)
- These are typically false detections from background noise
- Applied after merging to preserve the merged turn boundaries

---

### Step 3 — Role Assignment

```python
turn_df = assign_roles(turn_df)
```

**`assign_roles(turn_df)`:**
- Groups turns by speaker label (SPEAKER_00, SPEAKER_01)
- Computes total talk time per speaker
- Speaker with **most talk time** = "agent" (longest speaker in business calls is always the AI agent)
- Speaker with **second most** = "customer"
- Any additional speakers = "other"
- If only 1 speaker detected → all turns marked "agent"

**Result:** Adds a `role` column with values "agent", "customer", or "other".

---

### Step 4 — Pause Features

```python
turn_df = add_pause_features(turn_df)
```

**`add_pause_features(turn_df)`:**
- Adds `pause_before_sec` column — the silence gap before each turn starts
- First turn: `pause = start_sec` (time from call start to first speech)
- Subsequent turns: `pause = max(0, current_start - previous_end)`
- Overlapping turns (interruptions): pause clamped to 0
- Captures hesitation, response latency, dead air

---

### Step 5 — Acoustic Feature Extraction (CPU, librosa)

```python
turn_df = add_acoustic_features(audio_path, turn_df, sr=sample_rate)
```

**`add_acoustic_features(audio_path, turn_df, sr=16000)`:**
- Loads the entire audio with `librosa.load()` (mono, 16kHz)
- For each turn, slices the audio array: `y[start_sample : end_sample]`
- Computes two acoustic features per turn:

| Feature | How computed | What it measures |
|---|---|---|
| `energy_mean` | `librosa.feature.rms(y=segment).mean()` | Vocal loudness, emphasis, stress |
| `pitch_mean_hz` | `librosa.pyin()` averaged over non-NaN F0 values | Emotional arousal, nervousness |

**Edge cases:**
- Zero-length segment → `np.nan` for both features
- `pyin()` failure → `np.nan` for pitch (energy still computed)
- `pyin()` returns NaN frames for unvoiced sections → only voiced frames averaged

**Note:** librosa always runs on CPU regardless of CUDA availability. The acoustic feature step is CPU-bound and typically takes 10–40 seconds for a full call depending on length.

---

### Step 6 — Speaking Rate

```python
turn_df = add_speaking_rate(turn_df)
```

**`add_speaking_rate(turn_df)`:**
- Adds `speech_rate_proxy = 1 / (duration_sec + 1e-6)`
- Higher value = shorter turn = faster back-and-forth
- True syllable/second rate requires ASR (Whisper) — this is a structural proxy
- The `1e-6` prevents division by zero on zero-length turns

---

### Step 7 — Behaviour Labels

```python
turn_df = add_behavior_labels(turn_df)
```

**`add_behavior_labels(turn_df)`:**
Adds three boolean flag columns for dashboard filtering:

| Column | Rule | Use |
|---|---|---|
| `is_long_turn` | `duration_sec > 3` | Monologues, lengthy explanations |
| `is_high_energy` | `energy_mean > mean(energy_mean)` | Emphasis, stress, frustration |
| `is_high_pitch` | `pitch_mean_hz > mean(pitch_mean_hz)` | Arousal, nervousness |

---

### Step 8 — Call Summary Computation

```python
call_summary = build_call_summary(turn_df, audio_path)
```

**`build_call_summary(turn_df, audio_path)`** computes all call-level metrics from the turn DataFrame:

#### Engagement Score (0–100)

```python
eng     = float(engagement_score if engagement_score is not None else 50)
flow    = _FLOW_SCORES.get(conversation_flow if conversation_flow is not None else "", 50)
outcome = 100 if call_successful is True else (0 if call_successful is False else 50)
emotion = _EMOTION_SCORES.get(dominant_emotion if dominant_emotion is not None else "", 50)
score   = round(eng * 0.35 + flow * 0.25 + outcome * 0.25 + emotion * 0.15)
```

Wait — that is the **quality score** from `quality.py`. The **engagement score** in the pipeline is computed differently:

```python
# From pipeline.py compute_engagement_score()
energy_score = min(avg_energy / 0.05, 1.0)   # normalised RMS energy
rate_score   = min(avg_rate   / 0.80, 1.0)   # normalised speech rate proxy
pause_score  = 1.0 - min(avg_pause / 2.0, 1.0)  # inverted pause ratio

score = (0.4 * energy_score) + (0.3 * rate_score) + (0.3 * pause_score)
return round(score * 100, 2)
```

**Engagement score weights:**
- 40% — normalised RMS energy (vocal presence): `avg_energy / 0.05` capped at 1.0
- 30% — normalised speech rate: `avg_rate / 0.80` capped at 1.0
- 30% — inverted pause ratio: `1 - avg_pause / 2.0` capped at 0.0 minimum

**Interpretation:** Score 70+ is healthy for a business call. Below 40 suggests disengagement or call quality issues.

#### Conversation Flow Label

```python
def label_conversation_flow(avg_pause_sec: float) -> str:
    if avg_pause_sec > 1.0:  return "poor"
    elif avg_pause_sec > 0.6: return "moderate"
    return "smooth"
```

| Label | Avg pause | Meaning |
|---|---|---|
| `smooth` | ≤ 0.6s | Natural, engaged conversation |
| `moderate` | 0.6–1.0s | Some hesitation |
| `poor` | > 1.0s | Significant hesitation or dead air |

**Boundary note:** Both thresholds use strict `>` — exactly `0.6` is "smooth", exactly `1.0` is "moderate".

#### Sentiment Trajectory

```python
def compute_sentiment_trajectory(turn_df: pd.DataFrame) -> str:
```

Compares customer RMS energy in the **first third** of turns vs the **last third**.

```
third = max(len(turn_df) // 3, 1)
e_first = first_customer_third["energy_mean"].mean()
e_last  = last_customer_third["energy_mean"].mean()
change  = (e_last - e_first) / e_first

if change >  0.15: return "improving"
if change < -0.15: return "deteriorating"
return "stable"
```

- Prefers customer turns — falls back to all turns if no customer turns in a segment
- Threshold: ±15% change in average RMS energy
- < 3 turns total → always returns "stable"

#### Other Summary Fields

| Field | How computed |
|---|---|
| `total_turns` | `len(turn_df)` |
| `num_speakers` | `turn_df["speaker"].nunique()` |
| `total_duration_sec` | `turn_df["duration_sec"].sum()` |
| `total_silence_sec` | `turn_df["pause_before_sec"].sum()` |
| `avg_pause_sec` | `turn_df["pause_before_sec"].mean()` |
| `silence_ratio` | `total_silence_sec / (total_duration_sec + total_silence_sec + 1e-6)` |
| `agent_talk_time_sec` | `turn_df[role=="agent"]["duration_sec"].sum()` |
| `customer_talk_time_sec` | `turn_df[role=="customer"]["duration_sec"].sum()` |
| `agent_dominance_ratio` | `agent_talk / (customer_talk + 1e-6)` |
| `interruption_count` | Count of turns where `start_sec < prev_end_sec` |
| `hesitation_count` | Count of `pause_before_sec > 1.0s` |
| `avg_energy` | `turn_df["energy_mean"].mean()` |
| `avg_pitch_hz` | `turn_df["pitch_mean_hz"].mean()` |
| `trajectory_start_energy` | Mean energy of first `n//3` turns |
| `trajectory_end_energy` | Mean energy of last `n//3` turns |
| `processing_sec` | Wall-clock time for full `process_call()` |

---

## 8. Emotion Processing (emotion2vec)

**File:** `backend/emotion_processor.py`  
**Env:** `heya_pipeline`  
**Model:** `iic/emotion2vec_plus_large` v2.0.5 from ModelScope/HuggingFace  
**GPU needed:** Yes (CUDA, ~0.5–2s per utterance)

This is a separate pass run **after** Phase 2. It adds per-utterance emotion labels and a dominant call emotion.

### 8.1 Why It's Separate

- emotion2vec and pyannote both need GPU but come from different libraries (FunASR vs pyannote)
- Running them together risks VRAM conflicts on smaller GPUs
- The emotion pass is optional — dashboard still works without it (shows `dominant_emotion = null`)

### 8.2 The Model

`emotion2vec_plus_large` is a transformer model trained on Chinese and English speech for 7 emotion classes:

| Emotion | Dashboard color |
|---|---|
| `happy` | Green `#22c55e` |
| `neutral` | Gray `#94a3b8` |
| `sad` | Blue `#60a5fa` |
| `angry` | Red `#ef4444` |
| `fearful` | Orange `#fb923c` |
| `disgusted` | Lime `#a3e635` |
| `surprised` | Purple `#c084fc` |
| `unknown` | Dark gray `#64748b` |

The model returns labels in Chinese/English format (e.g., `"开心/happy"`) which are normalised via `LABEL_MAP`. Chinese-only labels and English-only labels are both handled.

### 8.3 Processing Flow Per Call

```
For each transcript utterance with word-timing data:
  1. Load full audio file (librosa, 16kHz mono)
  2. Slice audio: y[start_sample : end_sample]
     - Uses transcript_words.start_time_sec / end_time_sec
     - Skips segments < MIN_SEGMENT_SEC (1.5s) — too short for reliable prediction
  3. Write to temp .wav file (emotion2vec needs a file path)
  4. Run emotion2vec_plus_large → get (labels, scores) ranked by confidence
  5. Map labels to canonical names via LABEL_MAP
  6. Skip "unknown" → try next best emotion if score >= 0.05
  7. Write emotion + confidence to transcript_utterances.emotion
  8. Delete temp file

After all utterances:
  9. Count emotion votes from customer utterances only
  10. Dominant emotion = most common emotion by count
  11. Write to audio_insights.dominant_emotion
  12. Write average confidence to audio_insights.dominant_emotion_score
```

### 8.4 Session Safety

All DB reads are done inside one session and converted to plain dicts before the session closes. Each DB write (per utterance) uses its own short session. This prevents `DetachedInstanceError` — a bug that was fixed in `alerts.py` and `admin_router.py` during the testing phase.

### 8.5 Running the Emotion Processor

```powershell
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project\backend

# Process all calls for a client
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --client client_heya_001
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --client client_heya_002

# Process one specific call
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --call call_xxx
```

**Processing time:** ~0.5–2 seconds per utterance on GPU. A 10-minute call has ~40 utterances → ~1 minute per call. Full dataset (~800 calls): several hours.

---

## 9. Topic Classification

**File:** `backend/topic_classifier.py`  
**Env:** `heya_audio` or `heya_v2` (CPU only, no GPU needed)  
**Speed:** Very fast — pure keyword matching, ~50ms per call

### 9.1 How It Works

A weighted keyword scoring system. For each topic, every keyword present in the transcript text adds `1 × topic_weight` to the topic's score. The topic with the highest total score wins.

```python
for topic, cfg in TOPICS.items():
    hits = sum(1 for kw in cfg["keywords"] if kw in lowered)
    scores[topic] = hits * cfg["weight"]

best       = max(scores, key=scores.get)
confidence = round(scores[best] / sum(scores.values()), 4)
```

If no keywords match at all → returns `("general", 0.0)`.

### 9.2 Topics and Weights

| Topic | Weight | Why higher weight |
|---|---|---|
| `emergency` | 1.5 | Very specific keywords, high importance |
| `complaint` | 1.4 | Should win over generic enquiry keywords |
| `cancellation` | 1.3 | Strong intent signal words |
| `payment` | 1.1 | Specific financial vocabulary |
| `technical_support` | 1.1 | Technical language |
| `booking` | 1.0 | Common but specific |
| `follow_up` | 1.0 | Common but specific |
| `enquiry` | 0.8 | Generic — many calls mention these words incidentally |

**Example for "booking":** keywords include "book", "booking", "appointment", "schedule", "reservation", "reschedule", "available", "availability", "time slot", "slot", "make an appointment", "set up a time", "arrange", "confirm"

### 9.3 What It Writes

- `calls.topic` — the winning topic name (e.g., "booking")
- `calls.topic_confidence` — fraction of total score the winning topic holds (0.0–1.0)

### 9.4 Running the Topic Classifier

```powershell
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project\backend

# One client
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" topic_classifier.py --client client_heya_001

# All clients
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" topic_classifier.py --all

# One call
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" topic_classifier.py --call call_xxx

# Re-run even if already classified
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" topic_classifier.py --all --reclassify
```

---

## 10. Webhook Ingestion (Live Calls)

**File:** `backend/webhook_processor.py`  
**Triggered by:** `POST /webhook/retell` (FastAPI endpoint in `main.py`)

The webhook handler processes **live calls** from Retell as they end — no dataset folder involved.

### 10.1 Retell Webhook Events

| Event | What happens |
|---|---|
| `call_ended` | Triggers `ingest_webhook_call()` as a FastAPI BackgroundTask |
| `call_analyzed` | Updates existing call row with analysis data (if call already inserted) |
| Anything else | Returns `{"status": "ignored"}` |

### 10.2 `ingest_webhook_call()` Flow

```
1. Extract call_id + agent_id from payload
2. Look up client_id via agent_id → agents table
   (If agent not found → log warning + return)
3. Parse analysis: call_summary, user_sentiment, call_successful
4. Parse costs: total_cost, llm_cost, tts_cost, stt_cost
5. Upsert calls row (insert if new, update if exists)
6. Insert transcript_utterances + transcript_words (from transcript_object)
7. Save recording_url to recordings table
8. Set processing_status = "pending_audio"
```

### 10.3 Why Audio Pipeline Doesn't Run in the Webhook

The webhook handler must return within 3 seconds (Retell requirement). The pyannote diarisation pipeline takes 30–120 seconds. Therefore:

- Webhook only stores metadata and transcript → sets `processing_status = "pending_audio"`
- Audio pipeline runs separately (manually or via a scheduled job)
- `GET /health/queue` exposes how many calls are pending

**Production upgrade path documented in the code:**
```python
# Replace the background task with a Celery worker that:
# 1. Downloads the recording_url to a temp file
# 2. Runs process_call() in the heya_pipeline env
# 3. Saves results to audio_insights
# 4. Deletes the temp file
```

### 10.4 HMAC Signature Verification

The `/webhook/retell` endpoint in `main.py` checks for `RETELL_API_KEY` in the environment. If set, it verifies the HMAC-SHA256 signature in the `X-Retell-Signature` header. If not set, signature verification is skipped (dev mode).

---

## 11. Database — What Gets Written Where

### 11.1 Complete DB Write Map

| Phase | Table | Written by | Key fields |
|---|---|---|---|
| Phase 1 | `clients` | `ensure_client_exists()` | id, name, folder_name |
| Phase 1 | `agents` | `ensure_agent_exists()` | id, client_id, name |
| Phase 1 | `calls` | `ingest_metadata()` | id, client_id, direction, sentiment, successful, summary, cost fields, `processing_status="pending"` |
| Phase 1 | `call_metadata` | `ingest_metadata()` | latency p50/p99, token usage, cost breakdown, full analysis JSON |
| Phase 1 | `tool_calls` | `ingest_metadata()` | One row per tool call in the transcript |
| Phase 1 | `transcript_utterances` | `ingest_transcript()` | call_id, index, role (agent/user), content |
| Phase 1 | `transcript_words` | `ingest_transcript()` | utterness_id, word, start_time_sec, end_time_sec |
| Phase 1 | `recordings` | `ingest_recording_path()` | call_id, audio_path (absolute) |
| Phase 2 | `audio_insights` | `save_audio_insights()` | All acoustic metrics (see §11.2) |
| Phase 2 | `calls` | `ingest_dataset.py` | `processing_status="completed"` |
| Phase 3 | `transcript_utterances` | `emotion_processor.py` | emotion, emotion_score per utterance |
| Phase 3 | `audio_insights` | `emotion_processor.py` | dominant_emotion, dominant_emotion_score, sentiment_score |
| Phase 4 | `calls` | `topic_classifier.py` | topic, topic_confidence |
| Webhook | `calls` | `webhook_processor.py` | Same as Phase 1 but `processing_status="webhook_received"` then `"pending_audio"` |

### 11.2 `audio_insights` Table — All Columns

| Column | Type | Source | Description |
|---|---|---|---|
| `id` | SERIAL PK | Auto | Primary key |
| `call_id` | TEXT FK | FK → calls.id | Unique — one insight per call |
| `silence_ratio` | NUMERIC(8,4) | `pipeline.py` | Fraction of call that is silence |
| `speaking_rate` | NUMERIC(10,2) | `pipeline.py` | Speech rate proxy (1/duration) |
| `agent_talk_ratio` | NUMERIC(8,4) | `save_audio_insights()` | Agent talk / total talk |
| `user_talk_ratio` | NUMERIC(8,4) | `save_audio_insights()` | Customer talk / total talk |
| `interruption_count` | INT | `pipeline.py` | Turns starting before previous ends |
| `average_response_delay_sec` | NUMERIC(8,4) | `pipeline.py` | = avg_pause_sec |
| `sentiment_score` | NUMERIC(8,4) | `emotion_processor.py` | Overall sentiment score |
| `engagement_score` | NUMERIC(8,2) | `pipeline.py` | 0–100 composite score |
| `hesitation_count` | INT | `pipeline.py` | Pauses > 1.0s |
| `total_turns` | INT | `pipeline.py` | Speaker turn count |
| `agent_talk_time_sec` | NUMERIC(10,2) | `pipeline.py` | Seconds agent spoke |
| `customer_talk_time_sec` | NUMERIC(10,2) | `pipeline.py` | Seconds customer spoke |
| `avg_pause_sec` | NUMERIC(8,4) | `pipeline.py` | Average silence gap per turn |
| `avg_energy` | NUMERIC(10,6) | `pipeline.py` | Mean RMS energy all turns |
| `avg_pitch_hz` | NUMERIC(10,2) | `pipeline.py` | Mean F0 all turns |
| `agent_avg_energy` | NUMERIC(10,6) | `pipeline.py` | Mean RMS energy agent turns only |
| `customer_avg_energy` | NUMERIC(10,6) | `pipeline.py` | Mean RMS energy customer turns |
| `agent_avg_pitch_hz` | NUMERIC(10,2) | `pipeline.py` | Mean F0 agent turns |
| `customer_avg_pitch_hz` | NUMERIC(10,2) | `pipeline.py` | Mean F0 customer turns |
| `conversation_flow` | VARCHAR(20) | `pipeline.py` | smooth / moderate / poor |
| `processing_sec` | NUMERIC(8,2) | `pipeline.py` | Wall-clock processing time |
| `sentiment_trajectory` | VARCHAR(20) | `pipeline.py` | improving / stable / deteriorating |
| `trajectory_start_energy` | NUMERIC(10,6) | `pipeline.py` | Mean energy first third of turns |
| `trajectory_end_energy` | NUMERIC(10,6) | `pipeline.py` | Mean energy last third of turns |
| `dominant_emotion` | VARCHAR(20) | `emotion_processor.py` | Most common customer emotion |
| `dominant_emotion_score` | NUMERIC(8,4) | `emotion_processor.py` | Avg confidence of dominant emotion |

---

## 12. How to Run Everything

### 12.1 First-Time Full Dataset Ingestion

```powershell
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project\backend

# Step 1: Phase 1 — metadata + transcripts (heya_audio, fast, ~5 min for 800 calls)
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" ingest_dataset.py --phase 1

# Step 2: Phase 2 — audio pipeline (heya_pipeline, slow, GPU, ~6-8 hours for 800 calls)
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" ingest_dataset.py --phase 2

# Step 3: Emotion processing (heya_pipeline, GPU, ~several hours)
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --client client_heya_001
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" emotion_processor.py --client client_heya_002

# Step 4: Topic classification (heya_audio, fast, ~1 min for all calls)
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" topic_classifier.py --all

# Step 5: Build RAG vector store (heya_v2, needs Ollama running, ~5 min per client)
# Start Ollama first: & "C:\Users\Bhanu\AppData\Local\Programs\Ollama\ollama.exe" serve
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" -c "from rag import build_vector_store; build_vector_store('client_heya_001')"
& "C:\Users\Bhanu\miniconda3\envs\heya_v2\Scripts\python.exe" -c "from rag import build_vector_store; build_vector_store('client_heya_002')"
```

### 12.2 Process a Single Call

```powershell
$env:PYTHONIOENCODING = "utf-8"
cd D:\rmit\semester_4\project\backend

# First ensure it's in the DB (phase 1 must have run for this call)
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" run_single_pipeline.py `
    --call-id call_037f9a7f2d7a7c25fd844ffb16a `
    --audio "D:\rmit\semester_4\project\dataset\artel_apartments\recordings\call_037f9a7f2d7a7c25fd844ffb16a\audio.wav"
```

### 12.3 Check Database State

```powershell
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" ingest_dataset.py --summary
```

Output shows row counts for all 9 pipeline tables plus per-client call counts and average engagement score.

### 12.4 Test the Pipeline (limited calls)

```powershell
# Phase 1 test — first 5 calls
& "C:\Users\Bhanu\miniconda3\envs\heya_audio\Scripts\python.exe" ingest_dataset.py --phase 1 --limit 5

# Phase 2 test — first 3 calls
& "C:\Users\Bhanu\miniconda3\envs\heya_pipeline\python.exe" ingest_dataset.py --phase 2 --limit 3
```

---

## 13. Processing Status Lifecycle

Every call in the `calls` table has a `processing_status` column that tracks where it is in the pipeline:

```
                         ┌─────────────────────────────────────────┐
Dataset ingestion:       │  "pending"                              │
                         └──────────────┬──────────────────────────┘
                                        │  phase 2 completes
                         ┌──────────────▼──────────────────────────┐
                         │  "completed"                            │
                         └─────────────────────────────────────────┘

                         ┌─────────────────────────────────────────┐
Webhook ingestion:       │  "webhook_received"                     │
                         └──────────────┬──────────────────────────┘
                                        │  audio not processed yet
                         ┌──────────────▼──────────────────────────┐
                         │  "pending_audio"                        │
                         └──────────────┬──────────────────────────┘
                                        │  run_single_pipeline.py
                         ┌──────────────▼──────────────────────────┐
                         │  "completed"                            │
                         └─────────────────────────────────────────┘

Pipeline failure:        │  "failed"                               │
Empty hangup calls:      │  "skipped_empty"                        │
```

**`GET /health/queue`** (admin only) counts calls where `processing_status = "pending_audio"` — this is how admins know how many live calls are waiting for audio processing.

---

## 14. Known Limitations & Gotchas

### 14.1 The `start_timstamp` Typo

The `calls` table has a column named `start_timstamp` (one `t`, not two). This is a permanent typo preserved intentionally:
- Fixing it requires a `ALTER TABLE` migration + updating all code references
- The SQLAlchemy model maps `start_timstamp` correctly in Python
- The text_to_sql schema prompt explicitly warns the LLM: `"⚠ ONE 't' — never write start_timestamp"`
- The `call_metadata` table has `disconnectio_rason` (another typo) — same situation

### 14.2 `num_speakers=2` Is Hardcoded

```python
diarization = pipeline(audio_input, num_speakers=2)
```

The pyannote pipeline is told there are always exactly 2 speakers. This is appropriate for business calls (AI agent + one customer) but would be wrong for:
- Conference calls
- Calls where a third party joins
- Background voices counted as speakers

### 14.3 Audio Pipeline Cannot Run in Web Server Process

The FastAPI server runs in `heya_v2`. pyannote 3.x requires `heya_pipeline`. These environments cannot be loaded in the same Python process due to torch version conflicts. The `POST /process-call` endpoint exists but will fail unless the server is launched from `heya_pipeline` — which breaks the web API.

**Current approach:** Run the pipeline separately, on-demand or scheduled.  
**Production approach:** Celery worker queue in `heya_pipeline` env, separate process from the web server.

### 14.4 Emotion Processing Requires Word-Level Timestamps

`emotion_processor.py` uses `transcript_words.start_time_sec` and `end_time_sec` to slice audio per utterance. If a call's transcript doesn't have word-level timing data (some Retell configurations don't include it), the call is skipped with: `"No word-timing data for call_id — cannot segment audio"`.

### 14.5 Minimum Segment for Emotion (1.5 seconds)

`emotion2vec_plus_large` needs at least ~1.5 seconds of speech for reliable prediction. Utterances shorter than `MIN_SEGMENT_SEC = 1.5` are skipped. This means very short utterances ("Yes", "Okay", "Sure") don't get emotion labels.

### 14.6 The 2 Skipped MVAA Calls

Two MVAA Legal calls have `processing_status = "skipped_empty"`. These are immediate hangups — the audio file contains only silence or a few milliseconds of audio. `process_call()` returns an empty turn DataFrame → the pipeline marks them as skipped.

### 14.7 RAG Vector Store Is Not Rebuilt Automatically

After running Phase 2 on new calls, the pgvector embeddings in `call_embeddings` are stale. The RAG system's semantic search will not include new calls until `build_vector_store()` is run manually. Text-to-SQL and SQL fast-path work immediately because they query the live `calls` and `audio_insights` tables.

---

*This document covers the complete audio processing pipeline as implemented on 2026-06-02. `pipeline.py` is the core audio processing module and must be read alongside `ingest_dataset.py` (bulk runner), `emotion_processor.py` (emotion pass), and `topic_classifier.py` (topic pass) to understand the full data flow.*
