---
name: track-feature-extraction
description: Extract per-track listening features (play count, active date range, circular time-of-day variance, day-of-week distribution, gap hours, density) from listening_history.db. Purely mechanical extraction — no category/threshold logic; see memory-category-thresholds for that.
---

# Track Feature Extraction

## Purpose
Turn a track's raw play history into a small set of numeric/structural features — the prerequisite input for classifying listening patterns into memory categories (see the `memory-category-thresholds` skill). This skill covers extraction only: no category labels, no thresholds.

## Prerequisites
- Python stdlib only (`sqlite3`, `math`, `collections.Counter`, `datetime`, `pathlib`) — no external dependencies.
- Input data: the `plays` table in `listening_history.db` — `track_id`, `track_name`, `artist_name`, `played_at`.
- **Canonical implementation lives in `track_features.py` at the repo root** (alongside `pull_history.py` and `session_detection.py`, all operating on the same DB). Import `extract_all_track_features` from there — the code shown below is a direct copy for reference, not a second source of truth.

## Procedure

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

## Known Edge Cases

**1. Time-of-day variance must be circular, not linear — this was a real bug, since fixed.** A naive `statistics.pvariance` on raw hour-of-day values treats 23:00 and 01:00 as far apart (differ by 22 on a 0-23 scale) even though they're only 2 hours apart on an actual clock. Fixed by mapping each time onto the unit circle (`angle = hour / 24 * 2*pi`) and computing `1 - mean resultant length` — the standard directional-statistics circular variance, bounded `[0, 1]`. Verified on a synthetic case: a consistent 23:00-01:00 listener scored **128.89** under the old naive method (falsely "erratic") vs **0.0085** under the fix (correctly "very consistent"). This matters directly for downstream classification (see `memory-category-thresholds`) — a genuinely consistent late-night pattern must not get miscategorized as erratic just because its times straddle midnight.

**2. `density_plays_per_day_busiest_window` buckets by calendar date (UTC), not a rolling 24h window.** A burst of plays spanning midnight (e.g. 11pm-1am) would be split across two calendar-day buckets and undercount the true burst size. Not yet exercised by real data (no track's plays currently straddle midnight), but worth revisiting once real burst-pattern tracks are being evaluated near a day boundary.

**3. Tracks with `play_count == 1` trivially zero out every variance/gap feature** (`active_days: 0`, `time_of_day_circular_variance: 0.0`, `gap_hours: []`). This is correct, not a bug — a single play has no pattern to measure yet. Most tracks in the current dataset fall into this bucket (58 of 88 as of this writing — this ratio will shift as more data accumulates, treat the numbers as a reference point, not a live count). Downstream classification (see `memory-category-thresholds`) treats these as `insufficient_data`.

**4. Rows with `track_id IS NULL` are excluded from `load_track_plays`.** Not currently an issue (0 NULLs as of this writing), but per-track grouping is impossible without an ID, so this exclusion is permanent, not a temporary gap.

## Verification Checklist
- [ ] `sum(day_of_week_distribution.values()) == play_count` for every track
- [ ] `len(gap_hours) == play_count - 1` for every track
- [ ] `density_plays_per_day_busiest_window <= play_count` for every track
- [ ] A track with `play_count == 1` returns `active_days: 0`, `time_of_day_circular_variance: 0.0`, `gap_hours: []`
- [ ] Circular variance synthetic check: a consistent time-of-day pattern spanning midnight scores near `0.0`, not a large naive-variance value
- [ ] Running against the real `listening_history.db` produces one feature dict per distinct non-NULL `track_id`, count matching `SELECT COUNT(DISTINCT track_id) FROM plays WHERE track_id IS NOT NULL`
