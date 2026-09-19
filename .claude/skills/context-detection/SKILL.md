---
name: context-detection
description: Join session boundaries with per-track memory-category classification so a session inherits a context label from its qualifying member tracks (plurality vote, with a minimum-representation floor). If no qualifying track dominates, a session with enough distinct tracks (MIN_DISTINCT_TRACKS_FOR_EVIDENCE) falls back to Locked/Exploration based on artist diversity -- independent of whether any track happened to qualify elsewhere in the fetch. Sessions too small for that fall back to "Glimpse". Turns raw sessions + track labels into the "contexts" shown to a user and used for playlist creation (each context's human-voiced category_description text is owned by category-descriptions/SKILL.md).
---

# Context Detection

## Purpose
Give each detected listening session a single, evidence-based label — a "context" — by combining `session-boundary-detection`'s session boundaries with `memory-category-thresholds`'s per-track classification. This is what turns raw track-level labels (which silently exclude any track with only one play) into something a user can actually browse and turn into a playlist, and it's the layer that scopes playlist creation to one specific listening occasion instead of pooling every track anywhere that happens to share a label. A plurality winner must also cover a minimum share of the session's tracks to count — a single stray qualifying track should not define an entire session (see Procedure step 3 and Known Limitations #2).

**`Glimpse` is the user-facing name for "not enough evidence about this session."** It fires when a session has no dominant qualifying track *and* too few distinct tracks to judge the session's own breadth (below `MIN_DISTINCT_TRACKS_FOR_EVIDENCE`) — not simply "every track is insufficient_data." A session's breadth (`Exploration`) or concentration (`Locked`) is judged from *this session's own* distinct-track/distinct-artist counts, deliberately independent of whether any of its tracks happened to qualify as Spiral/Trigger/Companion from history elsewhere in the fetch — see Known Limitations #0c for why this changed. `track_features.py` itself is untouched; the Glimpse naming and the breadth/concentration judgment both live entirely in this layer, which is exactly its job (translating track/session truth into what a user sees).

**`Locked` was named `Block` until 2026-09-19.** Renamed for user-facing tone (matches the human-voiced `CATEGORY_DESCRIPTIONS` text below) — the decision rule (`distinct_artist_count / distinct_track_count < 0.5`) is unchanged. Historical `BUILD_LOG.md` entries from before the rename still say "Block," describing what the category was actually called when that work was done — left as an accurate historical record, not updated.

**Every final label carries a `category_description` field** — a short, static, human-voiced explanation of what the category *means*, distinct from the per-session `description` field here (which explains the evidence *for this specific session*, e.g. "3 of 23 tracks show this pattern"). The dict backing it (`CATEGORY_DESCRIPTIONS`), where it's used, and the writing/voice guidelines for it are owned entirely by `category-descriptions/SKILL.md` — see that skill, not this one, for its content and how to change it.

**Framing note:** a "context" here is one detected session, not a recurring pattern aggregated across many sessions over time. The original project vision (`plan.md`) describes clusters as persistent identities (e.g. "shower songs") that would need accumulated history across weeks — this app deliberately has no persistent database (a live one-shot fetch per visit), so per-session context is the defensible, MVP-scoped definition, not a full realization of that original vision.

## Prerequisites
- Reuses `session_detection.detect_sessions()` and `track_features.extract_track_features()`/`classify_track()` unchanged — no new thresholds, no modification to either module.
- Input: a list of normalized play dicts (`played_at`, `track_id`, `track_name`, `artist_name`) — the same shape `app.py`'s `fetch_recent_plays()` already produces.
- **Canonical implementation lives in `context_detection.py` at the repo root.** Import `build_contexts` from there.
- `category_description` (see Output shape below) comes from `CATEGORY_DESCRIPTIONS`, also in `context_detection.py` but documented separately — see `category-descriptions/SKILL.md`.

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

# Minimum distinct tracks a session needs to reach the diversity fallback
# (Locked/Exploration) instead of Glimpse, when no qualifying track
# dominates. PROVISIONAL -- see Known Limitations #0c.
MIN_DISTINCT_TRACKS_FOR_EVIDENCE = 2

# CATEGORY_DESCRIPTIONS (the human-voiced "what this category means" text)
# also lives in this file -- see category-descriptions/SKILL.md for its
# content, usage sites, and voice guidelines. Not reproduced here.

def _diversity_fallback(session, distinct_track_count):
    """Called whenever no qualifying track dominates (whether or not any
    qualifying track exists at all) and the session has enough distinct
    tracks to judge its own breadth -- see build_contexts."""
    ratio = session["distinct_artist_count"] / distinct_track_count
    if ratio < 0.5:
        return {"label": "Locked", "description": f"{distinct_track_count} tracks across {session['distinct_artist_count']} artists — a concentrated run."}
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
        distinct_track_count = len(distinct_ids)
        labels = [classification_by_track[tid] for tid in distinct_ids]
        qualifying = [l for l in labels if l in QUALIFYING_LABELS]

        dominant = None
        if qualifying:
            candidate, count = Counter(qualifying).most_common(1)[0]
            if count / distinct_track_count >= MIN_REPRESENTATION_RATIO:
                dominant = (candidate, count)

        if dominant is not None:
            label, count = dominant
            description = f"{label} — {count} of {distinct_track_count} tracks show this pattern."
        elif distinct_track_count >= MIN_DISTINCT_TRACKS_FOR_EVIDENCE:
            fallback = _diversity_fallback(sess, distinct_track_count)
            label, description = fallback["label"], fallback["description"]
        else:
            label = "Glimpse"
            description = f"{distinct_track_count} tracks, none played more than once in this window — a fleeting listening encounter."

        contexts.append({
            "context_id": sess["session_id"],
            "label": label,
            "description": description,
            "category_description": CATEGORY_DESCRIPTIONS[label],
            "track_ids": distinct_ids,
            "track_count": distinct_track_count,
        })
    return contexts
```

**Output shape** — one dict per detected session:
```python
{
    "context_id": 2,
    "label": "Companion",
    "description": "Companion — 2 of 3 tracks show this pattern.",
    "category_description": "This one keeps showing up. You never really stopped playing it.",
    "track_ids": ["X", "Y", "Z"],
    "track_count": 3,
}
```

## Known Limitations

**0. Why `MIN_REPRESENTATION_RATIO = 0.15`, specifically.** Without a representation floor, a session with 1 Trigger track out of 22 distinct tracks (4.5%) would be labeled "Trigger" purely because nothing else qualified to compete — not because Trigger is actually representative of that session. Verified against real live data (a single `current_user_recently_played(limit=50)` fetch): two real sessions had plurality winners covering only 4.8% (1/21) and 12.0% (3/25) of their distinct tracks. 15% is the smallest threshold that routes *both* of those thin-signal cases to the session-native fallback instead — 20% and 25% were also tested and produced identical results on that same data, so 15% is the least aggressive choice the evidence actually supports, not an arbitrarily stricter one.

**0c. Exploration/Locked no longer require a qualifying track to exist (fixed 2026-09-19).** Originally, the diversity fallback (`_diversity_fallback`) was only reachable when `qualifying` was non-empty — a session with *zero* qualifying tracks always became `Glimpse`, no matter how many distinct tracks or artists it had. This meant a session like "20 distinct tracks, 15 distinct artists, no track repeated anywhere in the fetch" — the clearest possible case of exploratory listening — was indistinguishable from a single track played once. Traced and confirmed via synthetic test cases (see Verification Checklist). Fixed by gating the diversity fallback on `MIN_DISTINCT_TRACKS_FOR_EVIDENCE` (a session-size check) instead of "qualifying is non-empty" — `Exploration`/`Locked` now reflect *this session's own* breadth/concentration regardless of whether any track happened to qualify from history elsewhere in the fetch. Real session data (12 real sessions, checked before implementing) had no example of a multi-track, zero-qualifying session to calibrate `MIN_DISTINCT_TRACKS_FOR_EVIDENCE` against — every real session with 2+ distinct tracks already had at least one qualifying track — so 2 was chosen as the smallest defensible value (preserves Glimpse's original single-track meaning) rather than calibrated the way `MIN_REPRESENTATION_RATIO` was. Confirmed via regression test that this fix does not change any of the 12 real sessions' existing labels. Revisit `MIN_DISTINCT_TRACKS_FOR_EVIDENCE` once a real multi-track, zero-repeat session is observed. This category was renamed `Block` → `Locked` shortly after (see Purpose section) — the rule and this history are otherwise unaffected by the rename.

**0b. Bug found and fixed alongside the threshold change:** `_fallback_context` originally used `session["track_count"]` (raw play events, per `session-boundary-detection`'s own documented convention) instead of the deduplicated distinct-track count — so a session's fallback description could show a different track count than the context's own `track_count` field, and a session with one track replayed multiple times would never correctly trigger `Glimpse`. Fixed by passing the deduplicated count in explicitly.

**1. Plurality tie-breaking is unspecified beyond "most common."** If a session has an exact tie (e.g. 1 Companion and 1 Trigger track), `Counter.most_common(1)` breaks ties by first-insertion order, which is deterministic but not a deliberately chosen rule. Not engineered further for v1 — revisit if ties turn out to be common in practice.

**2a. Glimpse's boundary is now `MIN_DISTINCT_TRACKS_FOR_EVIDENCE`-based, not purely categorical.** Originally "Glimpse vs. some real signal" reused the empty/non-empty `qualifying` list check with no new number needed. That was superseded by #0c: Glimpse now fires when `distinct_track_count < MIN_DISTINCT_TRACKS_FOR_EVIDENCE` (currently 2) regardless of qualifying tracks, so a single-track session is still Glimpse (1 < 2), but a 2+-track session with zero qualifying tracks now reaches the diversity fallback instead of Glimpse. A "mostly insufficient_data" percentage-based alternative was considered earlier and explicitly rejected in favor of a size-based floor, for the same reason `MIN_REPRESENTATION_RATIO` was calibrated rather than guessed — see #0c for why the resulting number is still provisional.

**2b. Locked/Exploration thresholds were calibrated on a different data regime than they're now used in.** They were originally proposed (as "Block"/Exploration) against an accumulated multi-day local database (`listening_history.db`, via the old cron pipeline), calibrated on exactly 2 real data points for the boundary. They're now applied to a single live `current_user_recently_played(limit=50)` fetch per visit — a much smaller, single-window sample that may produce a different `track_count`/`distinct_artist_count` distribution than the regime they were calibrated against. Treat as provisional; revisit once real usage data from the live flow exists.

**3. `context_id` is the session's index within one `build_contexts()` call, not a stable identifier across requests.** `/create-playlist` re-fetches and re-classifies fresh, then looks up the matching `context_id` — if new plays happened between viewing contexts and clicking "create playlist," the session numbering could shift and the lookup could miss. Handled as a clear "try again" error, not silently using the wrong tracks — not solved further since re-fetching fresh (rather than caching results) is the app's established stateless pattern.

**4. A track's classification reflects its entire play history in the fetched window, not just its plays within one particular session.** A track classified "Companion" (returned on a separate day) can still appear in an earlier, single-play session from that same window — its classification is who it *is* across the whole fetch, not scoped to any one session. This is intentional (matches `memory-category-thresholds`'s own scope — Trigger/Companion are cross-session, track-level concepts), not a bug.

## Verification Checklist
- [ ] A session with a clear majority (e.g. 2 Companion + 1 Trigger, 67%) labels as the majority, with an accurate "`N` of `M`" evidence count
- [ ] A session where the plurality winner covers less than 15% of distinct tracks falls through to `Locked`/`Exploration`, not the thin-signal label
- [ ] A session with `distinct_track_count < MIN_DISTINCT_TRACKS_FOR_EVIDENCE` (currently 2, i.e. a single-track session) labels as `Glimpse`, regardless of qualifying tracks
- [ ] A session with `distinct_track_count >= MIN_DISTINCT_TRACKS_FOR_EVIDENCE`, zero qualifying tracks, and a high artist-diversity ratio labels as `Exploration` (confirmed 2026-09-19: 5/5, 10/8, and 20/15 track/artist synthetic cases all correctly reach `Exploration`, where they previously incorrectly fell to `Glimpse`)
- [ ] A session with `distinct_track_count >= MIN_DISTINCT_TRACKS_FOR_EVIDENCE`, zero qualifying tracks, and a low artist-diversity ratio labels as `Locked` (confirmed 2026-09-19 as "Block," the pre-rename name for this same rule: 20 tracks/2 artists)
- [ ] A session with some qualifying signal below the representation floor, enough distinct tracks, and a low/high artist-diversity ratio still correctly labels `Locked`/`Exploration` (confirmed unchanged: 20-tracks-one-played-8x case still reaches `Exploration`)
- [ ] `track_ids` in each context are deduplicated (a track replayed multiple times within one session appears once in `track_ids`, `track_count` reflects distinct tracks not play events)
- [ ] Every session from `detect_sessions()` produces exactly one context — no session dropped, no session double-counted
- [ ] `track_features.py`'s `classify_track()` and the literal `"insufficient_data"` string it returns are unchanged — the Glimpse naming lives entirely in this module
- [ ] Re-running all 12 real sessions from `listening_history.db` through `build_contexts()` after this change produces identical labels to before (confirmed 2026-09-19 — no real session's label changed, since none had the previously-mis-gated shape)
- [ ] Every one of the 6 labels a session can receive has a non-empty `category_description` from `CATEGORY_DESCRIPTIONS` — a `KeyError` here means a label was added/renamed without updating the dict
