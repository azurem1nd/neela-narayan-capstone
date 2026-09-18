"""Per-track feature extraction from Spotify listening history.

Step 1 of track-pattern-classification: extraction only, no category
thresholds or classification logic yet.
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


if __name__ == "__main__":
    all_features = extract_all_track_features()
    print(f"{len(all_features)} unique tracks\n")
    for f in all_features:
        print(f"{f['track_name']} — {f['artist_name']}")
        print(f"  play_count: {f['play_count']}")
        print(f"  active_days: {f['active_days']}  (first {f['first_played']} -> last {f['last_played']})")
        print(f"  time_of_day_circular_variance: {f['time_of_day_circular_variance']}")
        print(f"  day_of_week_distribution: {f['day_of_week_distribution']}")
        print(f"  gap_hours: {f['gap_hours']}")
        print(f"  density_plays_per_day_busiest_window: {f['density_plays_per_day_busiest_window']}")
        print()
