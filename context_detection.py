"""Session-level listening contexts.

Joins session_detection.py's session boundaries with track_features.py's
per-track classification, so a session can inherit a context label from
its qualifying member tracks (plurality vote) instead of requiring every
individual track to independently qualify.

Three-way decision per session, in order:
1. A qualifying track (Spiral/Trigger/Companion) dominates the session
   (see MIN_REPRESENTATION_RATIO) -> that label wins outright.
2. No dominant qualifying track, but the session has enough distinct
   tracks to say something about it (see MIN_DISTINCT_TRACKS_FOR_EVIDENCE)
   -> a session-native label (Block/Exploration) based on artist
   diversity, regardless of whether any track happened to qualify
   elsewhere in the fetch. This is deliberately independent of
   cross-session track classification: a session can be genuinely
   exploratory (many distinct tracks/artists, no repeats) even when every
   one of its tracks is "insufficient_data" on its own -- Exploration is
   about this session's own breadth, not about borrowing a label from a
   track's unrelated history elsewhere in the fetch.
3. Neither of the above -- the session itself is too small to say
   anything -> "Glimpse". This IS the user-facing name for
   insufficient_data at the session level: not a technical state, and no
   longer gated on cross-session track qualification (see 2).

See .claude/skills/context-detection/SKILL.md for the full methodology
and known limitations.
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

# Minimum distinct tracks a session needs to reach the diversity fallback
# (Block/Exploration) instead of Glimpse, when no qualifying track
# dominates. PROVISIONAL: real session data (12 real sessions, as of
# 2026-09-19) has no example of a multi-track session with zero qualifying
# tracks -- every real session with >=2 distinct tracks already has at
# least one Spiral/Trigger/Companion track. 2 is the smallest value that
# preserves Glimpse's original single-track meaning while not requiring
# cross-session repetition evidence for anything larger. Revisit once a
# real multi-track, zero-repeat session is observed -- see SKILL.md.
MIN_DISTINCT_TRACKS_FOR_EVIDENCE = 2


def _diversity_fallback(session: dict, distinct_track_count: int) -> dict:
    """Session-native label for sessions with no dominant qualifying
    pattern (either no qualifying track at all, or one that exists but
    doesn't meet MIN_REPRESENTATION_RATIO) but enough distinct tracks
    (MIN_DISTINCT_TRACKS_FOR_EVIDENCE) to judge the session's own breadth.

    Block: concentrated listening, few distinct artists relative to tracks.
    Exploration: diverse listening, many distinct artists relative to tracks.

    Uses distinct_track_count (deduplicated), not session["track_count"]
    (raw play events, which double-counts a replayed track within one
    session) -- keeps this consistent with the track_count already shown
    in the context dict build_contexts() returns.
    """
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
        distinct_track_count = len(distinct_ids)
        labels = [classification_by_track[tid] for tid in distinct_ids]
        qualifying = [label for label in labels if label in QUALIFYING_LABELS]

        dominant = None
        if qualifying:
            candidate, count = Counter(qualifying).most_common(1)[0]
            if count / distinct_track_count >= MIN_REPRESENTATION_RATIO:
                dominant = (candidate, count)

        if dominant is not None:
            label, count = dominant
            description = f"{label} — {count} of {distinct_track_count} tracks show this pattern."
        elif distinct_track_count >= MIN_DISTINCT_TRACKS_FOR_EVIDENCE:
            # No dominant qualifying track, but enough distinct tracks to
            # judge this session's own breadth -- independent of whether
            # any track happened to qualify elsewhere in the fetch.
            fallback = _diversity_fallback(sess, distinct_track_count)
            label = fallback["label"]
            description = fallback["description"]
        else:
            # Too few distinct tracks to say anything about this session.
            label = "Glimpse"
            description = (
                f"{distinct_track_count} tracks, none played more than once in "
                "this window — a fleeting listening encounter."
            )

        contexts.append({
            "context_id": sess["session_id"],
            "label": label,
            "description": description,
            "track_ids": distinct_ids,
            "track_count": distinct_track_count,
        })

    return contexts
