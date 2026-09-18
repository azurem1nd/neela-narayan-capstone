---
name: context-detection
description: Join session boundaries with per-track memory-category classification so a session inherits a context label from its qualifying member tracks (plurality vote, with a minimum-representation floor). Sessions with zero qualifying tracks (every track is insufficient_data) become "Glimpse" -- the user-facing name for that state, at any session size. Sessions with some signal that's too thin to meet the floor fall back to Block/Exploration based on artist diversity. Turns raw sessions + track labels into the "contexts" shown to a user and used for playlist creation.
---

# Context Detection

## Purpose
Give each detected listening session a single, evidence-based label — a "context" — by combining `session-boundary-detection`'s session boundaries with `memory-category-thresholds`'s per-track classification. This is what turns raw track-level labels (which silently exclude any track with only one play) into something a user can actually browse and turn into a playlist, and it's the layer that scopes playlist creation to one specific listening occasion instead of pooling every track anywhere that happens to share a label. A plurality winner must also cover a minimum share of the session's tracks to count — a single stray qualifying track should not define an entire session (see Procedure step 3 and Known Limitations #2).

**`Glimpse` is the user-facing name for `insufficient_data`.** `memory-category-thresholds::classify_track()` returns the literal string `"insufficient_data"` for any track with fewer than 2 plays — that string is never shown to a user directly; it's an internal, technical state. Whenever a session has *zero* qualifying tracks (every distinct track is `insufficient_data`), this layer labels the session `Glimpse`, at whatever size the session actually is — not restricted to single-track sessions. `track_features.py` itself is untouched; this naming lives entirely in this layer, which is exactly its job (translating track/session truth into what a user sees).

**Framing note:** a "context" here is one detected session, not a recurring pattern aggregated across many sessions over time. The original project vision (`plan.md`) describes clusters as persistent identities (e.g. "shower songs") that would need accumulated history across weeks — this app deliberately has no persistent database (a live one-shot fetch per visit), so per-session context is the defensible, MVP-scoped definition, not a full realization of that original vision.

## Prerequisites
- Reuses `session_detection.detect_sessions()` and `track_features.extract_track_features()`/`classify_track()` unchanged — no new thresholds, no modification to either module.
- Input: a list of normalized play dicts (`played_at`, `track_id`, `track_name`, `artist_name`) — the same shape `app.py`'s `fetch_recent_plays()` already produces.
- **Canonical implementation lives in `context_detection.py` at the repo root.** Import `build_contexts` from there.

## Procedure

```python
from collections import Counter
from session_detection import detect_sessions
from track_features import classify_track, extract_track_features

QUALIFYING_LABELS = {"Spiral", "Trigger", "Companion"}

# A plurality winner must cover at least this share of a session's distinct
# tracks to define the session's context -- chosen against real data, see
# Known Limitations #2.
MIN_REPRESENTATION_RATIO = 0.15

def _diversity_fallback(session, distinct_track_count):
    """Only called when some qualifying track exists but under-represents --
    NOT called for the zero-qualifying case, which is Glimpse (see build_contexts)."""
    ratio = session["distinct_artist_count"] / distinct_track_count
    if ratio < 0.5:
        return {"label": "Block", "description": f"{distinct_track_count} tracks across {session['distinct_artist_count']} artists — a concentrated run."}
    return {"label": "Exploration", "description": f"{distinct_track_count} tracks across {session['distinct_artist_count']} artists — broad, varied listening."}

def build_contexts(plays):
    by_track = {}
    for p in plays:
        if p["track_id"] is not None:
            by_track.setdefault(p["track_id"], []).append(p)

    classification_by_track = {
        track_id: classify_track(extract_track_features(track_plays))
        for track_id, track_plays in by_track.items()
    }

    session_tuples = [(p["played_at"], p["track_id"], p["artist_name"]) for p in plays if p["track_id"] is not None]
    sessions = detect_sessions(session_tuples)

    contexts = []
    for sess in sessions:
        distinct_ids = list(dict.fromkeys(sess["track_ids"]))
        labels = [classification_by_track[tid] for tid in distinct_ids]
        qualifying = [l for l in labels if l in QUALIFYING_LABELS]

        if not qualifying:
            # Every distinct track is insufficient_data -- Glimpse, at any size.
            label = "Glimpse"
            description = f"{len(distinct_ids)} tracks, none played more than once in this window — a fleeting listening encounter."
        else:
            winner, count = Counter(qualifying).most_common(1)[0]
            if count / len(distinct_ids) >= MIN_REPRESENTATION_RATIO:
                label = winner
                description = f"{label} — {count} of {len(distinct_ids)} tracks show this pattern."
            else:
                fallback = _diversity_fallback(sess, len(distinct_ids))
                label, description = fallback["label"], fallback["description"]

        contexts.append({
            "context_id": sess["session_id"],
            "label": label,
            "description": description,
            "track_ids": distinct_ids,
            "track_count": len(distinct_ids),
        })
    return contexts
```

**Output shape** — one dict per detected session:
```python
{
    "context_id": 2,
    "label": "Companion",
    "description": "Companion — 2 of 3 tracks show this pattern.",
    "track_ids": ["X", "Y", "Z"],
    "track_count": 3,
}
```

## Known Limitations

**0. Why `MIN_REPRESENTATION_RATIO = 0.15`, specifically.** Without a representation floor, a session with 1 Trigger track out of 22 distinct tracks (4.5%) would be labeled "Trigger" purely because nothing else qualified to compete — not because Trigger is actually representative of that session. Verified against real live data (a single `current_user_recently_played(limit=50)` fetch): two real sessions had plurality winners covering only 4.8% (1/21) and 12.0% (3/25) of their distinct tracks. 15% is the smallest threshold that routes *both* of those thin-signal cases to the session-native fallback instead — 20% and 25% were also tested and produced identical results on that same data, so 15% is the least aggressive choice the evidence actually supports, not an arbitrarily stricter one.

**0b. Bug found and fixed alongside the threshold change:** `_fallback_context` originally used `session["track_count"]` (raw play events, per `session-boundary-detection`'s own documented convention) instead of the deduplicated distinct-track count — so a session's fallback description could show a different track count than the context's own `track_count` field, and a session with one track replayed multiple times would never correctly trigger `Glimpse`. Fixed by passing the deduplicated count in explicitly.

**1. Plurality tie-breaking is unspecified beyond "most common."** If a session has an exact tie (e.g. 1 Companion and 1 Trigger track), `Counter.most_common(1)` breaks ties by first-insertion order, which is deterministic but not a deliberately chosen rule. Not engineered further for v1 — revisit if ties turn out to be common in practice.

**2a. Glimpse's boundary is categorical (zero qualifying tracks), not a calibrated threshold.** Unlike `MIN_REPRESENTATION_RATIO`, deciding "Glimpse vs. some real signal" reuses the code's existing empty/non-empty `qualifying` list check — no new number was introduced or needed. This was a deliberate widening of Glimpse's definition (previously arbitrarily restricted to `distinct_track_count == 1`) to match what the code's control flow already implied: a qualifying track always wins its session outright (1/1 = 100% ≥ 15%), so a single-track session only ever reached the fallback when that track was `insufficient_data` anyway. A "mostly insufficient_data" percentage-based alternative was considered and explicitly rejected — it would require picking and justifying another arbitrary threshold, the same problem `MIN_REPRESENTATION_RATIO` solved for with real data (see #0), without equivalent evidence to calibrate it.

**2b. Block/Exploration thresholds were calibrated on a different data regime than they're now used in.** They were originally proposed against an accumulated multi-day local database (`listening_history.db`, via the old cron pipeline), calibrated on exactly 2 real data points for the Block/Exploration boundary. They're now applied to a single live `current_user_recently_played(limit=50)` fetch per visit — a much smaller, single-window sample that may produce a different `track_count`/`distinct_artist_count` distribution than the regime they were calibrated against. Treat as provisional; revisit once real usage data from the live flow exists.

**3. `context_id` is the session's index within one `build_contexts()` call, not a stable identifier across requests.** `/create-playlist` re-fetches and re-classifies fresh, then looks up the matching `context_id` — if new plays happened between viewing contexts and clicking "create playlist," the session numbering could shift and the lookup could miss. Handled as a clear "try again" error, not silently using the wrong tracks — not solved further since re-fetching fresh (rather than caching results) is the app's established stateless pattern.

**4. A track's classification reflects its entire play history in the fetched window, not just its plays within one particular session.** A track classified "Companion" (returned on a separate day) can still appear in an earlier, single-play session from that same window — its classification is who it *is* across the whole fetch, not scoped to any one session. This is intentional (matches `memory-category-thresholds`'s own scope — Trigger/Companion are cross-session, track-level concepts), not a bug.

## Verification Checklist
- [ ] A session with a clear majority (e.g. 2 Companion + 1 Trigger, 67%) labels as the majority, with an accurate "`N` of `M`" evidence count
- [ ] A session where the plurality winner covers less than 15% of distinct tracks falls through to `Block`/`Exploration`, not the thin-signal label, and NOT `Glimpse` (some real signal existed, just under-represented)
- [ ] A session with zero qualifying tracks (every distinct track is `insufficient_data`) labels as `Glimpse`, regardless of how many distinct tracks it has — 1, 5, or 20
- [ ] A session with some qualifying signal below the representation floor, >1 distinct track, and a low artist-diversity ratio labels as `Block`
- [ ] A session with some qualifying signal below the representation floor, >1 distinct track, and a high artist-diversity ratio labels as `Exploration`
- [ ] `track_ids` in each context are deduplicated (a track replayed multiple times within one session appears once in `track_ids`, `track_count` reflects distinct tracks not play events)
- [ ] Every session from `detect_sessions()` produces exactly one context — no session dropped, no session double-counted
- [ ] `track_features.py`'s `classify_track()` and the literal `"insufficient_data"` string it returns are unchanged — the Glimpse naming lives entirely in this module
