---
name: track-pattern-classification
description: Classify individual tracks into listening-pattern categories (Companion/Trigger/Spiral implemented; Ghost/Return not yet implemented) based on per-track features extracted from listening_history.db.
---

# Track Pattern Classification

## Purpose
Classify individual tracks by their listening *pattern* — not genre, not one-off popularity, but the shape of how a track gets replayed over time (steady companion, sudden burst, escalating repeat, dormant-then-reactivated). Built in two stages:

1. **Feature extraction** (done, tested) — turn a track's raw play history into a small set of numeric/structural features.
2. **Classification** (Trigger/Companion/Spiral done; Ghost/Return not yet implemented) — map those features onto named categories using thresholds chosen against real feature distributions pulled from `listening_history.db`, not guessed in the abstract.

**Epistemic scope, important:** these labels describe a measurable behavioral *shape* in play timestamps — same-day concentration, cross-day return, burst density. They are **not** a claim about a verified psychological trigger, life event, or place. The data can establish *that* a pattern occurred, never *why*. Treat every label below as "candidate," not "proven cause."

## Prerequisites
- Python stdlib only (`sqlite3`, `math`, `collections.Counter`, `datetime`, `pathlib`) — no external dependencies.
- Input data: the `plays` table in `listening_history.db` — `track_id`, `track_name`, `artist_name`, `played_at`.
- **Canonical implementation lives in `track_features.py` at the repo root** (alongside `pull_history.py` and `session_detection.py`, all operating on the same DB). Import `extract_all_track_features` from there — the code shown below is a direct copy for reference, not a second source of truth.

## Procedure

### Step 1: Feature Extraction (built and tested)

1. **Load all plays, grouped by track, sorted ascending within each group:**
   ```python
   def load_track_plays(db_path):
       conn = sqlite3.connect(db_path)
       rows = conn.execute(
           "SELECT track_id, track_name, artist_name, played_at FROM plays "
           "WHERE track_id IS NOT NULL ORDER BY played_at ASC"
       ).fetchall()
       conn.close()

       by_track = {}
       for track_id, track_name, artist_name, played_at in rows:
           by_track.setdefault(track_id, []).append({
               "track_name": track_name,
               "artist_name": artist_name,
               "played_at": played_at,
           })
       return by_track
   ```

2. **Circular variance helper** for time-of-day (see Known Edge Cases for why this matters):
   ```python
   import math

   def _circular_variance(hours_of_day: list[float]) -> float:
       n = len(hours_of_day)
       angles = [h / 24 * 2 * math.pi for h in hours_of_day]
       sum_cos = sum(math.cos(a) for a in angles)
       sum_sin = sum(math.sin(a) for a in angles)
       mean_resultant_length = math.sqrt(sum_cos**2 + sum_sin**2) / n
       return round(1 - mean_resultant_length, 4)
   ```

3. **Extract features for one track's plays:**
   ```python
   from collections import Counter
   from datetime import datetime

   DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

   def _parse(played_at: str) -> datetime:
       return datetime.fromisoformat(played_at.replace("Z", "+00:00"))

   def extract_track_features(plays: list[dict]) -> dict:
       timestamps = [_parse(p["played_at"]) for p in plays]
       play_count = len(timestamps)

       first_played = timestamps[0]
       last_played = timestamps[-1]
       active_days = (last_played - first_played).total_seconds() / 86400

       hours_of_day = [t.hour + t.minute / 60 for t in timestamps]
       time_of_day_circular_variance = _circular_variance(hours_of_day)

       day_counts = Counter(DAY_NAMES[t.weekday()] for t in timestamps)
       day_of_week_distribution = {day: day_counts.get(day, 0) for day in DAY_NAMES}

       gap_hours = [
           round((b - a).total_seconds() / 3600, 2)
           for a, b in zip(timestamps, timestamps[1:])
       ]

       date_counts = Counter(t.date() for t in timestamps)
       density_plays_per_day_busiest_window = max(date_counts.values())

       return {
           "play_count": play_count,
           "first_played": plays[0]["played_at"],
           "last_played": plays[-1]["played_at"],
           "active_days": round(active_days, 2),
           "time_of_day_circular_variance": time_of_day_circular_variance,
           "day_of_week_distribution": day_of_week_distribution,
           "gap_hours": gap_hours,
           "density_plays_per_day_busiest_window": density_plays_per_day_busiest_window,
       }
   ```

4. **Run across every track:**
   ```python
   def extract_all_track_features(db_path=DB_PATH) -> list[dict]:
       by_track = load_track_plays(db_path)
       results = []
       for track_id, plays in by_track.items():
           features = extract_track_features(plays)
           features["track_id"] = track_id
           features["track_name"] = plays[0]["track_name"]
           features["artist_name"] = plays[0]["artist_name"]
           results.append(features)
       results.sort(key=lambda f: f["play_count"], reverse=True)
       return results
   ```

5. **Output shape** — a list of per-track feature dicts:
   ```python
   {
       "track_id": "3lIHa4fUwNKOCSS5k3Za0i",
       "track_name": "nothing",
       "artist_name": "Steve Lacy",
       "play_count": 6,
       "first_played": "2026-09-14T13:45:54.319Z",
       "last_played": "2026-09-18T08:01:52.670Z",
       "active_days": 3.76,
       "time_of_day_circular_variance": 0.2187,
       "day_of_week_distribution": {"Mon": 2, "Tue": 1, "Wed": 1, "Thu": 1, "Fri": 1, "Sat": 0, "Sun": 0},
       "gap_hours": [0.62, 19.35, 22.18, 25.35, 22.77],
       "density_plays_per_day_busiest_window": 2,
   }
   ```

### Step 2: Classification

Thresholds below were chosen by sorting real per-track features from the live dataset and looking for natural breakpoints, not picked in the abstract. See Known Limitations for what's provisional vs. solid.

```python
def classify_track(features: dict) -> str:
    """
    Classify a track's listening pattern from its features.

    Returns one of: "Spiral", "Trigger", "Companion", "insufficient_data".

    IMPORTANT: these labels describe a measurable behavioral SHAPE in the
    play timestamps (same-day concentration, cross-day return, burst
    density) -- they are not a claim about a verified psychological
    trigger, life event, or place. The data can establish THAT a pattern
    occurred, never WHY.

    Thresholds (Spiral is provisional, Ghost/Return are not implemented --
    see Known Limitations):
      - insufficient_data: play_count < 2 (no repeat to measure a pattern from)
      - Spiral (PROVISIONAL): density_plays_per_day_busiest_window >= 3
      - Trigger: play_count >= 2 and active_days < 0.5 (all plays same day, never returned)
      - Companion: play_count >= 2 and active_days >= 0.5 (returned on a later day)

    Spiral is checked before Trigger/Companion since it's the more specific
    signal. A track can in principle satisfy both Spiral's density
    condition and Trigger's same-day condition at once (true for the one
    current real example, "One Of Your Girls") -- in that case Spiral
    takes precedence.
    """
    if features["play_count"] < 2:
        return "insufficient_data"

    if features["density_plays_per_day_busiest_window"] >= 3:
        return "Spiral"

    if features["active_days"] < 0.5:
        return "Trigger"

    return "Companion"


def classify_all_tracks(db_path=DB_PATH) -> list[dict]:
    """Extract features for every track and attach a classification label to each."""
    features = extract_all_track_features(db_path)
    for f in features:
        f["classification"] = classify_track(f)
    return features
```

**Why these thresholds, specifically:**
- **Trigger vs. Companion boundary (`active_days` at 0.5)** sits inside a real *empty gap* in the data — the actual sorted `active_days` values for multi-play tracks jump straight from `0.03` to `0.95` with nothing in between, so any threshold placed in that gap is equally defensible. `0.5` was picked as a clean, explainable round number, not because it's more "correct" than `0.4` or `0.6`.
- **Trigger requires only `play_count >= 2`**, not a higher bar. A same-day replay with no later return (e.g. "bebe," "Static": played, then replayed once 37 minutes later, never again) is already a meaningful signal on its own, even without a third play.
- **Companion requires only `play_count >= 2`**, same reasoning — a single overnight return (e.g. many tracks at `active_days ≈ 0.95`, one repeat ~23h later at nearly the same time of day) already shows a real signal via `time_of_day_circular_variance ≈ 0.01` (extremely consistent), even this early.

### Ghost / Return — NOT IMPLEMENTED (known limitation, not a bug)

Proposed logic, recorded here so it isn't re-derived from scratch later, but **deliberately left uncoded**:
- **Ghost**: a track that was Companion-shaped (established repeat pattern), then went **7+ days silent**.
- **Return**: 2+ renewed plays after that silent gap — i.e. a Ghost track reactivating.

**Why unimplemented:** the current dataset's longest observed gap between two plays of the same track is only **~40.64 hours** (~1.7 days). There is no real example anywhere near a 7-day silence to validate a dormancy threshold against — any number picked now would be pure guesswork with zero real data behind it, unlike Trigger/Companion/Spiral above. Revisit once multi-week data has accumulated (the cron pipeline is already collecting continuously) and a real long-gap example actually exists to test against.

## Known Edge Cases

**1. Time-of-day variance must be circular, not linear — this was a real bug, since fixed.** A naive `statistics.pvariance` on raw hour-of-day values treats 23:00 and 01:00 as far apart (differ by 22 on a 0-23 scale) even though they're only 2 hours apart on an actual clock. Fixed by mapping each time onto the unit circle (`angle = hour / 24 * 2*pi`) and computing `1 - mean resultant length` — the standard directional-statistics circular variance, bounded `[0, 1]`. Verified on a synthetic case: a consistent 23:00-01:00 listener scored **128.89** under the old naive method (falsely "erratic") vs **0.0085** under the fix (correctly "very consistent"). This matters directly for classification — a genuinely consistent late-night "Companion" track must not get miscategorized as erratic just because its times straddle midnight.

**2. `density_plays_per_day_busiest_window` buckets by calendar date (UTC), not a rolling 24h window.** A burst of plays spanning midnight (e.g. 11pm-1am) would be split across two calendar-day buckets and undercount the true burst size. Not yet exercised by real data (no track's plays currently straddle midnight), but worth revisiting once real Trigger/Spiral candidates are being evaluated near a day boundary.

**3. Tracks with `play_count == 1` trivially zero out every variance/gap feature** (`active_days: 0`, `time_of_day_circular_variance: 0.0`, `gap_hours: []`). This is correct, not a bug — a single play has no pattern to measure yet. As of this writing, 53 of 83 tracks fall into this bucket, meaning most tracks currently have no classifiable pattern at all; these classify as `insufficient_data`, distinct from the three implemented named categories.

**4. Rows with `track_id IS NULL` are excluded from `load_track_plays`.** Not currently an issue (0 NULLs as of this writing), but per-track grouping is impossible without an ID, so this exclusion is permanent, not a temporary gap.

**5. Spiral is provisional — validated by exactly one real track.** Only "One Of Your Girls" (3 plays in ~6 minutes, `density=3`) has ever hit the `density_plays_per_day_busiest_window >= 3` threshold. One example is not enough to be confident the boundary is in the right place (unlike Trigger/Companion's `active_days` boundary, which sits in a real empty gap in the data) — revisit this threshold once more burst-pattern tracks accumulate.

**6. Companion currently spans two very different maturity levels without distinguishing them.** 19 of the 27 current Companion tracks have only *one* overnight repeat (`active_days ≈ 0.95-0.96`); the other 7 (the Steve Lacy set) are well-established with `play_count` up to 6 and `active_days` up to 3.76. Both sit under the same "Companion" label today. This is a known limitation, not something to fix right now — a future "strength" or "confidence" score could distinguish early-forming vs. established Companions without needing a new category.

**7. Ghost/Return are unimplemented — see the "Ghost / Return" subsection above** for the proposed logic and why it's deliberately left uncoded (no real example of a 7+ day gap exists yet to validate against).

## Verification Checklist

**Extraction (can verify now):**
- [ ] `sum(day_of_week_distribution.values()) == play_count` for every track
- [ ] `len(gap_hours) == play_count - 1` for every track
- [ ] `density_plays_per_day_busiest_window <= play_count` for every track
- [ ] A track with `play_count == 1` returns `active_days: 0`, `time_of_day_circular_variance: 0.0`, `gap_hours: []`
- [ ] Circular variance synthetic check: a consistent time-of-day pattern spanning midnight scores near `0.0`, not a large naive-variance value
- [ ] Running against the real `listening_history.db` produces one feature dict per distinct non-NULL `track_id`, count matching `SELECT COUNT(DISTINCT track_id) FROM plays WHERE track_id IS NOT NULL`

**Classification (Trigger/Companion/Spiral — can verify now):**
- [ ] Every track with `play_count == 1` classifies as `insufficient_data`, never force-fit into a named category
- [ ] A track with `play_count >= 2`, `active_days < 0.5`, `density < 3` classifies as `Trigger`
- [ ] A track with `play_count >= 2`, `active_days >= 0.5`, `density < 3` classifies as `Companion`
- [ ] A track with `density_plays_per_day_busiest_window >= 3` classifies as `Spiral`, even if it would otherwise also match Trigger (precedence check, real example: "One Of Your Girls")
- [ ] Total classified counts sum to the total track count (`Spiral + Trigger + Companion + insufficient_data == len(features)`), confirming no track is double-counted or dropped
- [ ] Each of Trigger/Companion/Spiral is reachable by at least one real track in the current dataset (confirmed as of this writing: 2 Trigger, 27 Companion, 1 Spiral, 53 insufficient_data)

**Classification (Ghost/Return — cannot verify, not implemented):**
- [ ] N/A until multi-week data exists with a real 7+ day gap to test against
