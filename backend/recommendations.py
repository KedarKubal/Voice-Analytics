"""
recommendations.py  —  Heya AI Voice Analytics
Pattern detection engine — turns raw call metrics into actionable advice.

Every detector returns a dict:
    id             unique slug
    priority       "critical" | "warning" | "info"
    title          one-line headline
    insight        why this matters (specific numbers)
    action         what to do about it (concrete, specific)
    metric         the key number vs benchmark
    affected_calls how many calls are affected
    trend          "worsening" | "stable" | "improving"
"""

from sqlalchemy import func, case, or_
from database import get_db, Call, AudioInsight, TranscriptUtterance


# ── Benchmarks ────────────────────────────────────────────────────────────────
B = {
    "silence_ratio":      0.15,   # >15% silence is elevated
    "silence_critical":   0.30,   # >30% silence is a problem
    "engagement_healthy": 65.0,   # 65/100 minimum healthy score
    "engagement_low":     45.0,   # <45 is critically low
    "success_rate":       0.80,   # 80% success rate target
    "interruptions_high": 5,      # >5 interruptions/call is high
    "interruptions_avg":  3.0,    # avg >3 is elevated
    "poor_flow_warning":  0.40,   # >40% poor flow is elevated
    "poor_flow_critical": 0.65,   # >65% poor flow is critical
    "deteriorating":      0.35,   # >35% deteriorating calls is concerning
    "negative_sentiment": 0.25,   # >25% negative callers is high
}

_PRIORITY_ORDER = {"critical": 0, "warning": 1, "info": 2}


# ═══════════════════════════════════════════════════════════════════════════════
# INDIVIDUAL DETECTORS
# ═══════════════════════════════════════════════════════════════════════════════

def _detect_silence(db, client_id: str, total: int) -> dict | None:
    avg_silence = (
        db.query(func.avg(AudioInsight.silence_ratio))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id)
        .scalar() or 0
    )
    high_count = (
        db.query(func.count(AudioInsight.id))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id,
                AudioInsight.silence_ratio > B["silence_critical"])
        .scalar() or 0
    )
    ratio = high_count / total

    if ratio < 0.10:
        return None

    is_critical = ratio > 0.40 or float(avg_silence) > 0.35
    return {
        "id":            "high_silence",
        "priority":      "critical" if is_critical else "warning",
        "title":         f"{high_count} calls have excessive dead air",
        "insight":       (
            f"{high_count} calls ({round(ratio*100)}%) exceed 30% silence. "
            f"Platform average is {float(avg_silence)*100:.1f}% — "
            f"the healthy benchmark is 15%. Dead air is the #1 driver of "
            f"call abandonment and low engagement scores."
        ),
        "action":        (
            "Add filler acknowledgements to the agent's prompt (e.g. 'Let me "
            "look that up for you') to fill processing gaps. Review LLM response "
            "latency — if it exceeds 1.5 s, the caller perceives the agent as unresponsive. "
            "Target: silence ratio below 15%."
        ),
        "metric":        f"{float(avg_silence)*100:.1f}% avg silence (benchmark: 15%)",
        "affected_calls": high_count,
        "trend":         "worsening",
    }


def _detect_engagement(db, client_id: str, total: int) -> dict | None:
    avg_eng = (
        db.query(func.avg(AudioInsight.engagement_score))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id)
        .scalar() or 0
    )
    low_count = (
        db.query(func.count(AudioInsight.id))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id,
                AudioInsight.engagement_score < B["engagement_low"])
        .scalar() or 0
    )

    if float(avg_eng) >= B["engagement_healthy"]:
        return None

    is_critical = float(avg_eng) < B["engagement_low"]
    return {
        "id":            "low_engagement",
        "priority":      "critical" if is_critical else "warning",
        "title":         f"Avg engagement is {float(avg_eng):.1f}/100 — below target",
        "insight":       (
            f"Platform average of {float(avg_eng):.1f}/100 is below the 65-point "
            f"healthy threshold. {low_count} individual calls scored below 45. "
            f"Low engagement correlates strongly with unsuccessful outcomes and "
            f"poor caller retention."
        ),
        "action":        (
            "Open the Calls tab, filter by 'poor' flow, and review the transcripts "
            "of the bottom 10 scoring calls. Look for patterns: long agent monologues, "
            "slow response times, or repeated clarification requests. Update the agent "
            "script to be more conversational and concise."
        ),
        "metric":        f"{float(avg_eng):.1f}/100 avg (benchmark: 65+)",
        "affected_calls": low_count,
        "trend":         "stable",
    }


def _detect_success_rate(db, client_id: str) -> dict | None:
    total = (
        db.query(func.count(Call.id))
        .filter(Call.client_id == client_id)
        .scalar() or 0
    )
    successful = (
        db.query(func.count(Call.id))
        .filter(Call.client_id == client_id, Call.call_successful == True)
        .scalar() or 0
    )
    if total == 0:
        return None

    rate = successful / total
    if rate >= B["success_rate"]:
        return None

    failed = total - successful
    return {
        "id":            "low_success_rate",
        "priority":      "critical",
        "title":         f"Call success rate is {rate*100:.1f}% — below 80% target",
        "insight":       (
            f"{failed} of {total} calls did not complete their goal. "
            f"A sub-80% success rate means more than 1 in 5 callers is hanging up "
            f"without a resolution — direct revenue and satisfaction loss."
        ),
        "action":        (
            "Filter the Calls tab by 'Unsuccessful' outcome and read the call summaries. "
            "Identify the top 3 failure reasons. Use Ask Your Data: "
            "'What are the most common reasons calls fail?' Then update the agent's "
            "decision tree to handle those specific scenarios."
        ),
        "metric":        f"{rate*100:.1f}% success rate (target: 80%+)",
        "affected_calls": failed,
        "trend":         "worsening",
    }


def _detect_flow(db, client_id: str, total: int) -> dict | None:
    poor = (
        db.query(func.count(AudioInsight.id))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id,
                AudioInsight.conversation_flow == "poor")
        .scalar() or 0
    )
    ratio = poor / total

    if ratio < B["poor_flow_warning"]:
        return None

    is_critical = ratio > B["poor_flow_critical"]
    return {
        "id":            "poor_conversation_flow",
        "priority":      "critical" if is_critical else "warning",
        "title":         f"{poor} calls have poor conversation flow ({round(ratio*100)}%)",
        "insight":       (
            f"{round(ratio*100)}% of calls are classified as 'poor' flow "
            f"(avg pause > 1 second). Conversation flow is the strongest single "
            f"predictor of engagement score and call outcome — more predictive "
            f"than call length or sentiment alone."
        ),
        "action":        (
            "Poor flow is almost always caused by agent processing latency. "
            "Check your LLM provider's p95 response time. If it's above 1.2 s, "
            "switch to a faster model for the first turn. Also add stream-response "
            "mode to Retell so the caller hears output while the model is still generating."
        ),
        "metric":        f"{round(ratio*100)}% poor flow (target: <20%)",
        "affected_calls": poor,
        "trend":         "worsening" if ratio > 0.60 else "stable",
    }


def _detect_trajectory(db, client_id: str, total: int) -> dict | None:
    traj_counts = dict(
        db.query(AudioInsight.sentiment_trajectory, func.count(AudioInsight.id))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id,
                AudioInsight.sentiment_trajectory.isnot(None))
        .group_by(AudioInsight.sentiment_trajectory)
        .all()
    )
    traj_total    = sum(traj_counts.values())
    deteriorating = traj_counts.get("deteriorating", 0)
    improving     = traj_counts.get("improving", 0)

    if traj_total == 0 or deteriorating / traj_total < B["deteriorating"]:
        return None

    return {
        "id":            "deteriorating_trajectory",
        "priority":      "warning",
        "title":         f"{deteriorating} calls deteriorate as they progress",
        "insight":       (
            f"{round(deteriorating/traj_total*100)}% of calls show declining caller "
            f"vocal energy from start to finish. Callers are losing interest or "
            f"becoming frustrated during the conversation — not at the start, but "
            f"as the call continues."
        ),
        "action":        (
            "The agent is likely front-loading too much information before offering "
            "a resolution. Move the value proposition and resolution offer to within "
            "the first 60 seconds. Shorten the information-gathering phase. "
            "Review calls where trajectory is 'improving' to understand what those "
            "agents do differently."
        ),
        "metric":        (
            f"{round(deteriorating/traj_total*100)}% deteriorating vs "
            f"{round(improving/traj_total*100)}% improving (target: more improving than deteriorating)"
        ),
        "affected_calls": deteriorating,
        "trend":         "worsening" if deteriorating > improving * 1.5 else "stable",
    }


def _detect_interruptions(db, client_id: str, total: int) -> dict | None:
    avg_int = (
        db.query(func.avg(AudioInsight.interruption_count))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id)
        .scalar() or 0
    )
    high_count = (
        db.query(func.count(AudioInsight.id))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id,
                AudioInsight.interruption_count > B["interruptions_high"])
        .scalar() or 0
    )

    if float(avg_int) < B["interruptions_avg"] and high_count < total * 0.15:
        return None

    return {
        "id":            "high_interruptions",
        "priority":      "warning",
        "title":         f"Agent interrupts callers in {high_count} calls",
        "insight":       (
            f"Average {float(avg_int):.1f} interruptions per call — "
            f"benchmark is under 3. {high_count} calls had more than 5 interruptions. "
            f"Frequent interruptions are the most common driver of negative sentiment "
            f"in AI voice agent deployments."
        ),
        "action":        (
            "Increase the agent's 'interruption_sensitivity' setting in the Retell "
            "dashboard (higher value = more patient). Add a rule: agent must wait "
            "at least 300 ms of silence before responding. Review high-interruption "
            "call transcripts for trigger phrases that cause premature responses."
        ),
        "metric":        f"{float(avg_int):.1f} interruptions/call avg (benchmark: <3)",
        "affected_calls": high_count,
        "trend":         "stable",
    }


def _detect_negative_sentiment(db, client_id: str) -> dict | None:
    total = (
        db.query(func.count(Call.id))
        .filter(Call.client_id == client_id)
        .scalar() or 0
    )
    negative = (
        db.query(func.count(Call.id))
        .filter(Call.client_id == client_id, Call.user_sentiment == "negative")
        .scalar() or 0
    )

    if total == 0 or negative / total < B["negative_sentiment"]:
        return None

    rate = negative / total
    return {
        "id":            "negative_sentiment",
        "priority":      "critical" if rate > 0.40 else "warning",
        "title":         f"{negative} callers ended the call with negative sentiment",
        "insight":       (
            f"{round(rate*100)}% negative sentiment rate. These are callers who are "
            f"actively dissatisfied — high churn risk and potential for negative reviews. "
            f"Industry benchmark for AI voice agents is under 15% negative."
        ),
        "action":        (
            "Use Ask Your Data: 'What are callers complaining about?' to surface "
            "the top complaint themes. Build a dedicated resolution path for the "
            "most common complaint. Ensure the agent ends every call with a "
            "satisfaction confirmation and a clear next step for unresolved issues."
        ),
        "metric":        f"{round(rate*100)}% negative (benchmark: <15%)",
        "affected_calls": negative,
        "trend":         "worsening" if rate > 0.35 else "stable",
    }


def _detect_healthy(avg_eng: float, success_rate: float) -> dict | None:
    if avg_eng < 65 or success_rate < 0.80:
        return None
    return {
        "id":            "performing_well",
        "priority":      "info",
        "title":         "Core metrics are above benchmark",
        "insight":       (
            f"Success rate ({success_rate*100:.1f}%) and engagement "
            f"({avg_eng:.1f}/100) are both healthy. "
            f"Focus on the long-tail outlier calls dragging averages down — "
            f"they represent the highest-leverage improvement opportunity."
        ),
        "action":        (
            "In the Calls tab, filter by 'poor' flow AND 'deteriorating' trajectory "
            "together — these are your highest-risk calls. Read their summaries to "
            "identify the specific scenarios the agent struggles with most."
        ),
        "metric":        f"{success_rate*100:.1f}% success · {avg_eng:.1f}/100 engagement",
        "affected_calls": 0,
        "trend":         "stable",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# CLIENT ALERT DETECTORS  (call-level flags for the client dashboard)
# ═══════════════════════════════════════════════════════════════════════════════

_FLAGGED_WORDS = [
    "fuck", "fucking", "shit", "bitch", "asshole", "bastard", "cunt",
    "damn", "ass", "dick", "piss", "crap", "bloody hell",
    "idiot", "stupid", "moron", "useless", "scam", "fraud",
    "sue", "lawsuit", "lawyer", "terrible", "awful", "disgusting",
    "pathetic", "incompetent", "ridiculous", "outrageous", "worst service",
    "cancel", "refund", "chargeback", "rip off", "ripoff",
]


def _alert_disconnects(db, client_id: str) -> dict | None:
    count = (
        db.query(func.count(Call.id))
        .filter(
            Call.client_id == client_id,
            Call.duration_ms.isnot(None),
            Call.duration_ms < 20_000,
        ).scalar() or 0
    )
    if count == 0:
        return None
    return {
        "id":            "early_disconnect",
        "priority":      "critical" if count > 5 else "warning",
        "title":         f"{count} call{'s' if count != 1 else ''} disconnected within 20 seconds",
        "insight":       (
            f"{count} call{'s' if count != 1 else ''} ended in under 20 seconds — "
            "likely callers hanging up before any meaningful conversation started. "
            "This is a strong signal that the agent's opening is not landing well."
        ),
        "action":        (
            "Review the agent's greeting script. If the first response is delayed >1.5s "
            "or sounds robotic, callers hang up immediately. Tighten the TTS warm-up and "
            "make the opening line conversational. Short disconnects are the highest-priority "
            "call-quality problem to fix."
        ),
        "metric":        f"{count} calls < 20s duration",
        "affected_calls": count,
        "trend":         "worsening",
    }


def _alert_very_poor_engagement(db, client_id: str) -> dict | None:
    count = (
        db.query(func.count(AudioInsight.id))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id, AudioInsight.engagement_score < 25)
        .scalar() or 0
    )
    if count == 0:
        return None
    return {
        "id":            "very_poor_engagement",
        "priority":      "critical" if count > 3 else "warning",
        "title":         f"{count} call{'s' if count != 1 else ''} with critically low engagement",
        "insight":       (
            f"{count} call{'s' if count != 1 else ''} scored below 25/100 engagement — "
            "far below the healthy benchmark of 65. These calls had near-complete "
            "breakdowns in caller connection or one-sided agent monologues."
        ),
        "action":        (
            "Open these calls in the Calls tab (sort by lowest engagement). Listen to "
            "recordings to understand what drove disengagement. Common causes: agent "
            "responses that don't acknowledge the caller's words, excessive form-filling "
            "monologues, or complete misunderstanding of the caller's intent."
        ),
        "metric":        f"{count} calls below 25/100 engagement",
        "affected_calls": count,
        "trend":         "worsening",
    }


def _alert_abusive_language(db, client_id: str) -> dict | None:
    word_filters = [
        TranscriptUtterance.content.ilike(f"%{w}%") for w in _FLAGGED_WORDS
    ]
    flagged = (
        db.query(func.count(func.distinct(TranscriptUtterance.call_id)))
        .join(Call, TranscriptUtterance.call_id == Call.id)
        .filter(Call.client_id == client_id, or_(*word_filters))
        .scalar() or 0
    )
    if flagged == 0:
        return None
    return {
        "id":            "flagged_language",
        "priority":      "critical",
        "title":         f"{flagged} call{'s' if flagged != 1 else ''} contain flagged or abusive language",
        "insight":       (
            f"{flagged} call{'s' if flagged != 1 else ''} contain potentially abusive, distressing, or "
            "escalatory language in the transcript. These indicate highly frustrated callers "
            "or escalating disputes that may require human review."
        ),
        "action":        (
            "Review these calls immediately. Add an escalation trigger to the agent: if "
            "the caller uses aggressive language, the agent should de-escalate and offer a "
            "callback or supervisor. Flag repeat callers for compliance review. Consider "
            "adding a human handoff path for distressed interactions."
        ),
        "metric":        f"{flagged} calls with flagged language",
        "affected_calls": flagged,
        "trend":         "worsening",
    }


def _alert_extreme_silence(db, client_id: str) -> dict | None:
    count = (
        db.query(func.count(AudioInsight.id))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id, AudioInsight.silence_ratio > 0.65)
        .scalar() or 0
    )
    if count == 0:
        return None
    return {
        "id":            "extreme_silence",
        "priority":      "warning",
        "title":         f"{count} call{'s' if count != 1 else ''} with extreme silence (>65%)",
        "insight":       (
            f"{count} call{'s' if count != 1 else ''} had more than 65% dead air — "
            "meaning most of the call was silence. This usually signals a technical failure, "
            "an unresponsive agent, or a caller who stopped engaging entirely."
        ),
        "action":        (
            "Check these calls for pipeline issues (TTS failure, missed audio chunks). "
            "If the silence is on the agent side, investigate LLM response latency. "
            "If it is on the caller side, the agent may need better re-engagement prompts "
            "when the caller goes quiet (e.g. 'Are you still there?')."
        ),
        "metric":        f"{count} calls with >65% silence",
        "affected_calls": count,
        "trend":         "stable",
    }


def _alert_high_interruptions(db, client_id: str) -> dict | None:
    count = (
        db.query(func.count(AudioInsight.id))
        .join(Call, AudioInsight.call_id == Call.id)
        .filter(Call.client_id == client_id, AudioInsight.interruption_count >= 8)
        .scalar() or 0
    )
    if count == 0:
        return None
    return {
        "id":            "excessive_interruptions",
        "priority":      "warning",
        "title":         f"{count} call{'s' if count != 1 else ''} with 8+ interruptions",
        "insight":       (
            f"{count} call{'s' if count != 1 else ''} had 8 or more interruptions — "
            "a level that typically makes callers feel unheard and drives dissatisfaction. "
            "Excessive cross-talk is a primary driver of poor sentiment trajectories."
        ),
        "action":        (
            "Increase the agent's end-of-turn detection buffer — it is jumping in too fast. "
            "Aim for a 400–600ms silence gap before the agent responds. Review the barge-in "
            "sensitivity settings and reduce the agent's tendency to speak over partial utterances."
        ),
        "metric":        f"{count} calls with 8+ interruptions",
        "affected_calls": count,
        "trend":         "stable",
    }


def generate_client_alerts(client_id: str) -> list[dict]:
    """
    Call-level alert detection for the client dashboard.
    Flags specific problem patterns: early disconnects, very poor engagement,
    abusive language, extreme silence, excessive interruptions.
    """
    alerts = []
    with get_db() as db:
        total = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id).scalar() or 0
        )
        if total == 0:
            return []

        for fn in [
            lambda: _alert_disconnects(db, client_id),
            lambda: _alert_very_poor_engagement(db, client_id),
            lambda: _alert_abusive_language(db, client_id),
            lambda: _alert_extreme_silence(db, client_id),
            lambda: _alert_high_interruptions(db, client_id),
        ]:
            try:
                r = fn()
                if r:
                    alerts.append(r)
            except Exception as e:
                print(f"  ⚠ Client alert detector failed: {e}")

    return sorted(alerts, key=lambda r: _PRIORITY_ORDER.get(r["priority"], 3))


# ═══════════════════════════════════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def generate_recommendations(client_id: str) -> list[dict]:
    """
    Run all detectors against a client's call data and return
    a prioritised list of actionable recommendations.
    """
    recs = []

    with get_db() as db:
        total_insights = (
            db.query(func.count(AudioInsight.id))
            .join(Call, AudioInsight.call_id == Call.id)
            .filter(Call.client_id == client_id)
            .scalar() or 0
        )

        if total_insights == 0:
            return [{
                "id":            "no_data",
                "priority":      "info",
                "title":         "No audio insights yet",
                "insight":       "Run the audio pipeline on your calls to generate recommendations.",
                "action":        "python ingest_dataset.py --phase 2",
                "metric":        "0 calls processed",
                "affected_calls": 0,
                "trend":         "stable",
            }]

        # Run each detector
        for fn in [
            lambda: _detect_silence(db, client_id, total_insights),
            lambda: _detect_flow(db, client_id, total_insights),
            lambda: _detect_success_rate(db, client_id),
            lambda: _detect_engagement(db, client_id, total_insights),
            lambda: _detect_trajectory(db, client_id, total_insights),
            lambda: _detect_interruptions(db, client_id, total_insights),
            lambda: _detect_negative_sentiment(db, client_id),
        ]:
            try:
                result = fn()
                if result:
                    recs.append(result)
            except Exception as e:
                print(f"  ⚠ Recommendation detector failed: {e}")

        # Healthy check — only if no criticals
        avg_eng = float(
            db.query(func.avg(AudioInsight.engagement_score))
            .join(Call, AudioInsight.call_id == Call.id)
            .filter(Call.client_id == client_id)
            .scalar() or 0
        )
        total_calls = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id)
            .scalar() or 0
        )
        successful = (
            db.query(func.count(Call.id))
            .filter(Call.client_id == client_id, Call.call_successful == True)
            .scalar() or 0
        )
        success_rate = successful / total_calls if total_calls else 0

        healthy = _detect_healthy(avg_eng, success_rate)
        if healthy:
            recs.append(healthy)

    # Sort: critical → warning → info
    return sorted(recs, key=lambda r: _PRIORITY_ORDER.get(r["priority"], 3))
