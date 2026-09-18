"""Session-level listening contexts.

Joins session_detection.py's session boundaries with track_features.py's
per-track classification, so a session can inherit a context label from
its qualifying member tracks (plurality vote) instead of requiring every
individual track to independently qualify. Falls back to a session-native
label (Glimpse/Block/Exploration) for sessions with zero classified
tracks, or where the plurality winner doesn't meet a minimum
representation threshold (see MIN_REPRESENTATION_RATIO) -- a single
qualifying track should not define an entire session's context. See
.claude/skills/context-detection/SKILL.md for the full methodology and
known limitations.
"""

from collections import Counter

from session_detection import detect_sessions
from track_features import classify_track, extract_track_features

QUALIFYING_LABELS = {"Spiral", "Trigger", "Companion"}

# Minimum share of a session's distinct tracks a plurality winner must cover
# to define the session's context, rather than a session-native fallback.
# Chosen against real data: 15% is the smallest threshold that filters out
# both observed thin-signal cases (1/21 = 4.8%, 3/25 = 12.0%) without going
# further than the evidence supports -- 20%/25% produced identical results
# on that same data, so 15% is the least aggressive choice that still works.
MIN_REPRESENTATION_RATIO = 0.15


def _fallback_context(session: dict, distinct_track_count: int) -> dict:
    """Session-native label for sessions with zero track-level signal.

    Glimpse: a single distinct track, no session structure to characterize.
    Block: concentrated listening, few distinct artists relative to tracks.
    Exploration: diverse listening, many distinct artists relative to tracks.

    Uses distinct_track_count (deduplicated), not session["track_count"]
    (raw play events, which double-counts a replayed track within one
    session) -- keeps this consistent with the track_count already shown
    in the context dict build_contexts() returns.
    """
    if distinct_track_count == 1:
        return {"label": "Glimpse", "description": "A single track, played once."}

    ratio = session["distinct_artist_count"] / distinct_track_count
    if ratio < 0.5:
        return {
            "label": "Block",
            "description": (
                f"{distinct_track_count} tracks across "
                f"{session['distinct_artist_count']} artists — a concentrated run."
            ),
        }
    return {
        "label": "Exploration",
        "description": (
            f"{distinct_track_count} tracks across "
            f"{session['distinct_artist_count']} artists — broad, varied listening."
        ),
    }


def build_contexts(plays: list[dict]) -> list[dict]:
    """Group live plays into sessions, each labeled with an inherited or
    fallback context.

    Args:
        plays: normalized play dicts with played_at, track_id, artist_name
            (as produced by app.py's fetch_recent_plays).

    Returns:
        List of context dicts, one per detected session:
        {context_id, label, description, track_ids, track_count}.
    """
    by_track: dict[str, list[dict]] = {}
    for p in plays:
        if p["track_id"] is not None:
            by_track.setdefault(p["track_id"], []).append(p)

    classification_by_track = {}
    for track_id, track_plays in by_track.items():
        features = extract_track_features(track_plays)
        classification_by_track[track_id] = classify_track(features)

    session_tuples = [
        (p["played_at"], p["track_id"], p["artist_name"])
        for p in plays
        if p["track_id"] is not None
    ]
    sessions = detect_sessions(session_tuples)

    contexts = []
    for sess in sessions:
        distinct_ids = list(dict.fromkeys(sess["track_ids"]))
        labels = [classification_by_track[tid] for tid in distinct_ids]
        qualifying = [label for label in labels if label in QUALIFYING_LABELS]

        label = None
        if qualifying:
            winner, count = Counter(qualifying).most_common(1)[0]
            if count / len(distinct_ids) >= MIN_REPRESENTATION_RATIO:
                label = winner
                description = f"{label} — {count} of {len(distinct_ids)} tracks show this pattern."

        if label is None:
            fallback = _fallback_context(sess, len(distinct_ids))
            label = fallback["label"]
            description = fallback["description"]

        contexts.append({
            "context_id": sess["session_id"],
            "label": label,
            "description": description,
            "track_ids": distinct_ids,
            "track_count": len(distinct_ids),
        })

    return contexts
