"""
emotion_processor.py  —  Heya AI Voice Analytics
Per-turn emotion classification using emotion2vec_plus_large.

Run in heya_pipeline conda env (NOT heya_audio):
    conda activate heya_pipeline
    python emotion_processor.py --client client_heya_001
    python emotion_processor.py --client client_heya_002
    python emotion_processor.py --call   call_<id>

Install dependencies first (once):
    pip install funasr modelscope huggingface_hub soundfile

What it does
------------
For each transcript utterance that has word-timing data:
  1. Reads the call's audio file (from recordings.audio_path)
  2. Extracts the utterance's audio slice using transcript_words timestamps
  3. Runs emotion2vec_plus_large on that slice
  4. Writes emotion + confidence back to transcript_utterances

Then per call:
  5. Computes dominant customer emotion
  6. Updates audio_insights.dominant_emotion + sentiment_score

Processing time: ~0.5–2 s per utterance on GPU.
A 10-minute call has ~40 utterances → ~1 minute per call.
"""

import os
import sys
import argparse
import tempfile
import traceback
from collections import Counter
from pathlib import Path

import numpy as np
from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import func
from database import (
    get_db,
    Client, Call, Recording, TranscriptUtterance, TranscriptWord, AudioInsight,
)


# ═══════════════════════════════════════════════════════════════════════════════
# EMOTION LABELS
# ═══════════════════════════════════════════════════════════════════════════════
EMOTION_LABELS = {
    "happy":      {"icon": "happy",     "color": "#22c55e"},
    "sad":        {"icon": "sad",       "color": "#60a5fa"},
    "angry":      {"icon": "angry",     "color": "#ef4444"},
    "neutral":    {"icon": "neutral",   "color": "#94a3b8"},
    "fearful":    {"icon": "fearful",   "color": "#fb923c"},
    "disgusted":  {"icon": "disgusted", "color": "#a3e635"},
    "surprised":  {"icon": "surprised", "color": "#c084fc"},
    "unknown":    {"icon": "unknown",   "color": "#64748b"},
}

SAMPLE_RATE     = 16_000
MIN_SEGMENT_SEC = 1.5   # emotion2vec needs at least ~1.5s of speech for reliable prediction

# emotion2vec v2 may return Chinese or variant label names — map everything to our set
LABEL_MAP = {
    # English standard
    "angry": "angry", "anger": "angry",
    "disgusted": "disgusted", "disgust": "disgusted",
    "fearful": "fearful", "fear": "fearful",
    "happy": "happy", "happiness": "happy", "joy": "happy",
    "neutral": "neutral",
    "other": "neutral",          # "other" → treat as neutral
    "sad": "sad", "sadness": "sad",
    "surprised": "surprised", "surprise": "surprised",
    "unknown": "unknown",
    # Chinese labels (emotion2vec trained on Chinese data)
    "愤怒": "angry", "厌恶": "disgusted", "恐惧": "fearful",
    "快乐": "happy", "中性": "neutral", "其他": "neutral",
    "悲伤": "sad", "惊讶": "surprised", "未知": "unknown",
}


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL LOADER  (singleton — load once per process)
# ═══════════════════════════════════════════════════════════════════════════════
_emotion_model = None

def load_emotion_model():
    global _emotion_model
    if _emotion_model is not None:
        return _emotion_model

    print("Loading emotion2vec_plus_large...")
    from funasr import AutoModel
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"  Device: {device}")

    _emotion_model = AutoModel(
        model          = "iic/emotion2vec_plus_large",
        model_revision = "v2.0.5",
        disable_update = True,
        disable_pbar   = True,
        device         = device,
    )
    print(f"✅ emotion2vec loaded on {device}")
    return _emotion_model


# ═══════════════════════════════════════════════════════════════════════════════
# CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════════════
def _parse_label(raw: str) -> str | None:
    """
    Map a raw model label to a canonical emotion name.

    emotion2vec_plus_large returns labels in the format '开心/happy' (Chinese/English)
    or sometimes just English ('happy') or special tokens ('<unk>').
    Try the full string first, then each slash-separated part.
    """
    raw = raw.strip()

    # Special tokens
    if raw in ("<unk>", "unk", "<UNK>"):
        return "unknown"

    # Direct lookup (handles pure English or pure Chinese labels)
    result = LABEL_MAP.get(raw.lower()) or LABEL_MAP.get(raw)
    if result:
        return result

    # Slash-separated format: '开心/happy' — try each part
    for part in raw.split("/"):
        part = part.strip()
        result = LABEL_MAP.get(part.lower()) or LABEL_MAP.get(part)
        if result:
            return result

    return None

def classify_segment(audio_array: np.ndarray, sr: int) -> tuple[str, float]:
    """
    Classify the emotion in a numpy audio segment.
    Returns (emotion_label, confidence_score).
    """
    import soundfile as sf

    model = load_emotion_model()

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        tmp_path = f.name
        sf.write(f.name, audio_array, sr)

    try:
        result = model.generate(
            tmp_path,
            output_dir        = None,
            granularity       = "utterance",
            extract_embedding = False,
        )
    finally:
        os.unlink(tmp_path)

    if not result or not result[0]:
        return "unknown", 0.0

    entry  = result[0]
    labels = entry.get("labels", [])
    scores = entry.get("scores", [])

    if not labels or not scores:
        return "unknown", 0.0

    # Sort by score descending
    ranked = sorted(zip(scores, labels), reverse=True)

    # Walk from highest to lowest score, return first label that maps to a known emotion
    # If top prediction is "unknown", try the next best emotion as a fallback
    for score, raw in ranked:
        normalised = _parse_label(raw)
        if normalised and normalised != "unknown":
            if score >= 0.05:
                return normalised, round(float(score), 4)

    # All mapped to unknown — return unknown with the top score
    top_score, top_raw = ranked[0]
    return "unknown", round(float(top_score), 4)


# ═══════════════════════════════════════════════════════════════════════════════
# PER-CALL PROCESSOR
# ═══════════════════════════════════════════════════════════════════════════════
def process_call_emotions(call_id: str) -> int:
    """
    Label all utterances in one call with emotion2vec.
    Returns number of utterances labelled.
    """
    import librosa

    # ── Fetch everything from DB and convert to plain dicts immediately ───────
    # This avoids DetachedInstanceError — ORM objects cannot be used after the
    # session closes, but plain dicts can.
    with get_db() as db:
        rec = db.query(Recording).filter(Recording.call_id == call_id).first()
        if not rec or not rec.audio_path:
            print(f"  ⚠ No audio path for {call_id}")
            return 0

        audio_path = rec.audio_path

        utt_rows = db.query(TranscriptUtterance)\
            .filter(TranscriptUtterance.call_id == call_id)\
            .order_by(TranscriptUtterance.utterness_index)\
            .all()

        if not utt_rows:
            print(f"  ⚠ No utterances for {call_id}")
            return 0

        # Convert to plain dicts while session is still open
        utterances = [
            {"id": u.id, "index": u.utterness_index, "role": u.role}
            for u in utt_rows
        ]

        # Build timing map from transcript_words (also inside session)
        timing = {}
        for utt in utterances:
            words = db.query(TranscriptWord)\
                .filter(TranscriptWord.utterness_id == utt["id"])\
                .order_by(TranscriptWord.word_index)\
                .all()
            starts = [float(w.start_time_sec) for w in words if w.start_time_sec is not None]
            ends   = [float(w.end_time_sec)   for w in words if w.end_time_sec   is not None]
            if starts and ends:
                timing[utt["id"]] = (min(starts), max(ends))

    # Session is closed here — utterances and timing are plain Python objects ─

    if not timing:
        print(f"  ⚠ No word-timing data for {call_id} — cannot segment audio")
        return 0

    if not Path(audio_path).exists():
        print(f"  ⚠ Audio file not found: {audio_path}")
        return 0

    y, sr = librosa.load(audio_path, sr=SAMPLE_RATE, mono=True)

    labelled = 0
    emotions = []

    for utt in utterances:
        utt_id = utt["id"]
        if utt_id not in timing:
            continue

        start_sec, end_sec = timing[utt_id]
        if (end_sec - start_sec) < MIN_SEGMENT_SEC:
            continue

        segment = y[int(start_sec * sr) : int(end_sec * sr)]
        if len(segment) < int(MIN_SEGMENT_SEC * sr):
            continue

        try:
            emotion, score = classify_segment(segment, sr)
        except Exception as e:
            print(f"    ✗ utterance {utt_id}: {e}")
            continue

        # Each write is its own short session — no detached object risk
        with get_db() as db:
            u = db.query(TranscriptUtterance).filter(TranscriptUtterance.id == utt_id).first()
            if u:
                u.emotion       = emotion
                u.emotion_score = score

        emotions.append((utt["role"], emotion, score))
        labelled += 1
        print(f"    [{utt['index']:>3}] {utt['role']:<8} -> {emotion} ({score:.2f})")

    # ── Dominant customer emotion → audio_insights ────────────────────────────
    cust = [(e, s) for role, e, s in emotions if role == "user" and e != "unknown"]
    if cust:
        dominant, _ = Counter(e for e, _ in cust).most_common(1)[0]
        dom_scores  = [s for e, s in cust if e == dominant]
        dom_avg     = round(sum(dom_scores) / len(dom_scores), 4)

        with get_db() as db:
            ai = db.query(AudioInsight).filter(AudioInsight.call_id == call_id).first()
            if ai:
                ai.dominant_emotion       = dominant
                ai.dominant_emotion_score = dom_avg
                ai.sentiment_score        = dom_avg

        print(f"  → dominant customer emotion: {dominant} ({dom_avg:.2f})")

    return labelled


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH RUNNERS
# ═══════════════════════════════════════════════════════════════════════════════
def process_client(client_id: str, limit: int = None, offset: int = 0):
    """
    Process unlabelled calls for one client.
    Use --limit + --offset to process in safe chunks if memory is tight:
        python emotion_processor.py --client client_heya_001 --limit 50
        python emotion_processor.py --client client_heya_001 --limit 50 --offset 50
    """
    import gc
    import torch

    with get_db() as db:
        q = (
            db.query(Call.id)
            .join(TranscriptUtterance, TranscriptUtterance.call_id == Call.id)
            .filter(
                Call.client_id == client_id,
                TranscriptUtterance.emotion.is_(None),
            )
            .distinct()
            .order_by(Call.id)
        )
        if offset:
            q = q.offset(offset)
        if limit:
            q = q.limit(limit)
        call_ids = [r.id for r in q.all()]

    total = len(call_ids)
    if not total:
        print(f"  ✅ No unlabelled calls for {client_id} (offset={offset})")
        return

    print(f"\nProcessing {total} call(s) for {client_id} "
          f"(offset={offset}, limit={limit or 'all'})...\n")
    load_emotion_model()

    ok = failed = 0
    for idx, call_id in enumerate(call_ids, 1):
        print(f"[{idx:>3}/{total}] {call_id}")
        try:
            n = process_call_emotions(call_id)
            print(f"  ✅ {n} utterances labelled")
            ok += 1
        except Exception:
            traceback.print_exc()
            failed += 1
        finally:
            # Release GPU cache and Python objects after every call
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()

    print(f"\n{'═'*50}")
    print(f"Done — {ok} ✅  {failed} ✗")
    remaining = total - ok - failed
    if limit and ok + failed >= limit:
        print(f"\nRun again with --offset {offset + limit} to continue.")


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Label call transcript utterances with emotion2vec"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--client",
        nargs="+",
        metavar="CLIENT_ID",
        help="One or more client IDs  e.g. --client client_heya_001 client_heya_002",
    )
    group.add_argument("--all",  action="store_true", help="Process every client in the DB")
    group.add_argument("--call", metavar="CALL_ID",   help="Process one specific call_id")
    parser.add_argument(
        "--limit",  type=int, default=None,
        help="Max calls to process per client (chunk mode to avoid OOM)"
    )
    parser.add_argument(
        "--offset", type=int, default=0,
        help="Skip first N calls (use with --limit to continue a previous run)"
    )
    args = parser.parse_args()

    if args.call:
        load_emotion_model()
        n = process_call_emotions(args.call)
        print(f"\n✅ {n} utterances labelled for {args.call}")

    elif args.all:
        with get_db() as db:
            all_ids = [r.id for r in db.query(Client).order_by(Client.id).all()]
        print(f"Processing all {len(all_ids)} client(s): {all_ids}")
        for cid in all_ids:
            process_client(cid, limit=args.limit, offset=args.offset)

    else:
        for cid in args.client:
            process_client(cid, limit=args.limit, offset=args.offset)
