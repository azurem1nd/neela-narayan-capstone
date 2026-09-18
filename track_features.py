"""Per-track feature extraction and memory-category classification for
Spotify listening history.

See .claude/skills/track-feature-extraction/SKILL.md for the extraction
methodology and .claude/skills/memory-category-thresholds/SKILL.md for
the classification methodology and threshold rationale.
"""

import math
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent
DB_PATH = REPO_DIR / "listening_history.db"

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parse(played_at: str) -> datetime:
    return datetime.fromisoformat(played_at.replace("Z", "+00:00"))


def _circular_variance(hours_of_day: list[float]) -> float:
    """Circular variance of times-of-day (fractional hours, 0-24), correctly
    handling midnight wraparound (23:00 and 01:00 are close, not far apart).

    Standard directional-statistics formula: map each time onto the unit
    circle (angle = hour / 24 * 2*pi), average the resulting vectors, and
    take 1 minus the length of that average (the "mean resultant length").

    Returns a value in [0, 1]: 0.0 means all plays happen at the same time
    of day; 1.0 means times are maximally scattered around the full clock.
    """
    n = len(hours_of_day)
    angles = [h / 24 * 2 * math.pi for h in hours_of_day]
    sum_cos = sum(math.cos(a) for a in angles)
    sum_sin = sum(math.sin(a) for a in angles)
    mean_resultant_length = math.sqrt(sum_cos**2 + sum_sin**2) / n
    return round(1 - mean_resultant_length, 4)


def load_track_plays(db_path: Path = DB_PATH) -> dict[str, list[dict]]:
    """Group all plays by track_id, sorted ascending by played_at within each track."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT track_id, track_name, artist_name, played_at FROM plays "
        "WHERE track_id IS NOT NULL ORDER BY played_at ASC"
    ).fetchall()
    conn.close()

    by_track: dict[str, list[dict]] = {}
    for track_id, track_name, artist_name, played_at in rows:
        by_track.setdefault(track_id, []).append({
            "track_name": track_name,
            "artist_name": artist_name,
            "played_at": played_at,
        })
    return by_track


def extract_track_features(plays: list[dict]) -> dict:
    """Compute per-track features from a chronological list of that track's plays."""
    timestamps = [_parse(p["played_at"]) for p in plays]
    play_count = len(timestamps)

    first_played = timestamps[0]
    last_played = timestamps[-1]
    active_days = (last_played - first_played).total_seconds() / 86400

    # Time-of-day in fractional hours (0.0-23.99), using circular variance
    # so a track played at 23:00 and 01:00 correctly shows as consistent
    # (close on a 24h clock) rather than far apart.
    hours_of_day = [t.hour + t.minute / 60 for t in timestamps]
    time_of_day_circular_variance = _circular_variance(hours_of_day)

    day_counts = Counter(DAY_NAMES[t.weekday()] for t in timestamps)
    day_of_week_distribution = {day: day_counts.get(day, 0) for day in DAY_NAMES}

    gap_hours = [
        round((b - a).total_seconds() / 3600, 2)
        for a, b in zip(timestamps, timestamps[1:])
    ]

    # Density: plays-per-day in the busiest single calendar day (UTC date
    # of played_at) -- NOT a rolling 24h window, so a burst spanning
    # midnight would be split across two buckets. Flagging in case a
    # rolling window is actually what's wanted.
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


def extract_all_track_features(db_path: Path = DB_PATH) -> list[dict]:
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


def classify_track(features: dict) -> str:
    """
    Classify a track's listening pattern from its features.

    Returns one of: "Spiral", "Trigger", "Companion", "insufficient_data".

    IMPORTANT: these labels describe a measurable behavioral SHAPE in the
    play timestamps (same-day concentration, cross-day return, burst
    density) -- they are not a claim about a verified psychological
    trigger, life event, or place. The data can establish THAT a pattern
    occurred, never WHY.

    Thresholds (see SKILL.md for full rationale; Spiral is provisional,
    Ghost/Return are not implemented -- see SKILL.md Known Limitations):
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


def classify_all_tracks(db_path: Path = DB_PATH) -> list[dict]:
    """Extract features for every track and attach a classification label to each."""
    features = extract_all_track_features(db_path)
    for f in features:
        f["classification"] = classify_track(f)
    return features


if __name__ == "__main__":
    all_features = classify_all_tracks()
    print(f"{len(all_features)} unique tracks\n")
    for f in all_features:
        print(f"{f['track_name']} — {f['artist_name']}  [{f['classification']}]")
        print(f"  play_count: {f['play_count']}")
        print(f"  active_days: {f['active_days']}  (first {f['first_played']} -> last {f['last_played']})")
        print(f"  time_of_day_circular_variance: {f['time_of_day_circular_variance']}")
        print(f"  day_of_week_distribution: {f['day_of_week_distribution']}")
        print(f"  gap_hours: {f['gap_hours']}")
        print(f"  density_plays_per_day_busiest_window: {f['density_plays_per_day_busiest_window']}")
        print()
