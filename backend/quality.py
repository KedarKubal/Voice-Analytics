"""
quality.py — Call quality scoring for Heya AI Voice Analytics

Produces a single 0–100 quality score and A–F grade per call by
combining four signals with fixed weights:

  Engagement score   35%   (acoustic engagement — most objective)
  Conversation flow  25%   (pause-based quality: smooth/moderate/poor)
  Call outcome       25%   (call_successful: direct business result)
  Customer emotion   15%   (dominant_emotion from emotion2vec)
"""

_FLOW_SCORES = {"smooth": 100, "moderate": 60, "poor": 20}

_EMOTION_SCORES = {
    "happy":     100,
    "surprised":  75,
    "neutral":    60,
    "fearful":    35,
    "sad":        30,
    "disgusted":  20,
    "angry":      15,
}

_GRADE_THRESHOLDS = [(80, "A"), (65, "B"), (50, "C"), (35, "D")]


def compute_quality_score(
    engagement_score:  float | None,
    conversation_flow: str   | None,
    call_successful:   bool  | None,
    dominant_emotion:  str   | None,
) -> int:
    eng     = float(engagement_score if engagement_score is not None else 50)
    flow    = _FLOW_SCORES.get(conversation_flow if conversation_flow is not None else "", 50)
    outcome = 100 if call_successful is True else (0 if call_successful is False else 50)
    emotion = _EMOTION_SCORES.get(dominant_emotion if dominant_emotion is not None else "", 50)
    return round(eng * 0.35 + flow * 0.25 + outcome * 0.25 + emotion * 0.15)


def quality_grade(score: int) -> str:
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return "F"
