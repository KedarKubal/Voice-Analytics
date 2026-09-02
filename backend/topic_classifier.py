"""
topic_classifier.py  —  Heya AI Voice Analytics
Keyword-based topic classification for call transcripts.

Run in heya_audio conda env (same env as the API):
    python topic_classifier.py --client client_heya_001
    python topic_classifier.py --all
    python topic_classifier.py --call call_<id>
    python topic_classifier.py --client client_heya_001 --reclassify

What it does
------------
For each call that has transcript text:
  1. Scores the text against every topic's keyword set (weighted)
  2. Assigns the highest-scoring topic + a confidence score (0–1)
  3. Writes topic + topic_confidence back to the calls table

Topics
------
booking, cancellation, complaint, payment, enquiry,
technical_support, emergency, follow_up, general
"""

import os
import sys
import argparse
import traceback
from dotenv import load_dotenv

load_dotenv()

from database import get_db, Call, Client

# ─────────────────────────────────────────────────────────────────────────────
# TOPIC DEFINITIONS
# keyword lists + weights (higher weight = fewer matches needed to win)
# ─────────────────────────────────────────────────────────────────────────────
TOPICS: dict[str, dict] = {
    "booking": {
        "weight": 1.0,
        "keywords": [
            "book", "booking", "appointment", "schedule", "reservation",
            "reschedule", "available", "availability", "time slot", "slot",
            "make an appointment", "set up a time", "arrange", "confirm",
        ],
    },
    "cancellation": {
        "weight": 1.3,
        "keywords": [
            "cancel", "cancellation", "cancelled", "canceling",
            "terminate", "end my", "close my account", "stop service",
            "withdraw", "opt out", "unsubscribe",
        ],
    },
    "complaint": {
        "weight": 1.4,
        "keywords": [
            "complaint", "complain", "unhappy", "not happy", "dissatisfied",
            "frustrated", "angry", "terrible", "awful", "unacceptable",
            "disgusting", "worst", "horrible", "ridiculous", "outrageous",
            "demand", "escalate", "this is not good", "very disappointed",
        ],
    },
    "payment": {
        "weight": 1.1,
        "keywords": [
            "pay", "payment", "invoice", "bill", "billing", "charge",
            "cost", "price", "fee", "refund", "money", "credit card",
            "debit", "outstanding", "overdue", "receipt", "transaction",
            "bank", "direct debit", "owe", "debt", "account balance",
        ],
    },
    "enquiry": {
        "weight": 0.8,
        "keywords": [
            "question", "asking", "wondering", "information", "info",
            "details", "want to know", "find out", "tell me about",
            "what is", "how does", "can you explain", "just calling to ask",
            "enquire", "inquiry",
        ],
    },
    "technical_support": {
        "weight": 1.1,
        "keywords": [
            "not working", "broken", "error", "technical issue", "bug",
            "crash", "login problem", "can't access", "doesn't work",
            "system down", "website", "app", "portal", "reset password",
            "locked out", "glitch", "connection",
        ],
    },
    "emergency": {
        "weight": 1.5,
        "keywords": [
            "urgent", "emergency", "immediately", "asap", "right now",
            "critical", "serious problem", "need help now", "dangerous",
            "safety", "life threatening", "police", "ambulance",
        ],
    },
    "follow_up": {
        "weight": 1.0,
        "keywords": [
            "follow up", "following up", "called before", "spoke last",
            "still waiting", "haven't heard", "update on", "status of",
            "checking in", "previously discussed", "last time",
        ],
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# CLASSIFIER
# ─────────────────────────────────────────────────────────────────────────────
def classify_topic(text: str) -> tuple[str, float]:
    """
    Classify the dominant topic of a transcript.
    Returns (topic_name, confidence_0_to_1).
    """
    if not text or not text.strip():
        return "general", 0.0

    lowered = text.lower()
    scores: dict[str, float] = {}

    for topic, cfg in TOPICS.items():
        hits = sum(1 for kw in cfg["keywords"] if kw in lowered)
        scores[topic] = hits * cfg["weight"]

    total = sum(scores.values())
    if total == 0:
        return "general", 0.0

    best       = max(scores, key=scores.get)
    best_score = scores[best]
    confidence = round(best_score / total, 4)

    return best, confidence


# ─────────────────────────────────────────────────────────────────────────────
# PER-CALL PROCESSOR  (called from API or CLI)
# ─────────────────────────────────────────────────────────────────────────────
def classify_call(call_id: str, reclassify: bool = False) -> bool:
    """
    Classify a single call and write topic + topic_confidence to DB.
    Returns True if classified, False if skipped.
    """
    with get_db() as db:
        call = db.query(Call).filter(Call.id == call_id).first()
        if not call:
            return False
        if call.topic and not reclassify:
            return False

        # Use stored transcript; fall back to joining utterances
        text = call.transcript or ""
        if not text.strip():
            from database import TranscriptUtterance
            utts = (
                db.query(TranscriptUtterance.content)
                .filter(TranscriptUtterance.call_id == call_id)
                .all()
            )
            text = " ".join(u.content for u in utts if u.content)

        if not text.strip():
            return False

    topic, confidence = classify_topic(text)

    with get_db() as db:
        call = db.query(Call).filter(Call.id == call_id).first()
        if call:
            call.topic            = topic
            call.topic_confidence = confidence

    return True


# ─────────────────────────────────────────────────────────────────────────────
# BATCH RUNNER
# ─────────────────────────────────────────────────────────────────────────────
def process_client(client_id: str, reclassify: bool = False):
    with get_db() as db:
        q = db.query(Call.id).filter(Call.client_id == client_id)
        if not reclassify:
            q = q.filter(Call.topic.is_(None))
        call_ids = [r.id for r in q.order_by(Call.id).all()]

    if not call_ids:
        print(f"  No unclassified calls for {client_id}")
        return

    print(f"\nClassifying {len(call_ids)} call(s) for {client_id}...")
    ok = skipped = 0
    for call_id in call_ids:
        result = classify_call(call_id, reclassify=reclassify)
        if result:
            ok += 1
        else:
            skipped += 1

    print(f"  Done — {ok} classified, {skipped} skipped (no transcript)")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Classify call topics")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--client", nargs="+", metavar="CLIENT_ID")
    group.add_argument("--all",    action="store_true")
    group.add_argument("--call",   metavar="CALL_ID")
    parser.add_argument("--reclassify", action="store_true",
                        help="Re-run even if topic already set")
    args = parser.parse_args()

    if args.call:
        ok = classify_call(args.call, reclassify=args.reclassify)
        print(f"{'Classified' if ok else 'Skipped'}: {args.call}")

    elif args.all:
        with get_db() as db:
            all_ids = [r.id for r in db.query(Client).order_by(Client.id).all()]
        for cid in all_ids:
            process_client(cid, reclassify=args.reclassify)

    else:
        for cid in args.client:
            process_client(cid, reclassify=args.reclassify)
