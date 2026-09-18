"""Session-boundary detection over Spotify listening history."""

import sqlite3
from datetime import datetime
from pathlib import Path

GAP_MINUTES = 30

REPO_DIR = Path(__file__).resolve().parent
DB_PATH = REPO_DIR / "listening_history.db"


def _parse(played_at: str) -> datetime:
    return datetime.fromisoformat(played_at.replace("Z", "+00:00"))


def load_plays(db_path: Path = DB_PATH) -> list[tuple[str, str]]:
    """Load (played_at, track_id) pairs from listening_history.db, sorted ascending."""
    conn = sqlite3.connect(db_path)
    rows = conn.execute(
        "SELECT played_at, track_id FROM plays ORDER BY played_at ASC"
    ).fetchall()
    conn.close()
    return rows


def detect_sessions(plays: list[tuple[str, str]], gap_minutes: float = GAP_MINUTES) -> list[dict]:
    """
    Split chronological (played_at, track_id) plays into listening sessions.

    A new session starts whenever the gap between two consecutive plays
    exceeds `gap_minutes`. Single-track sessions are valid and are never
    merged or discarded.

    Args:
        plays: (played_at, track_id) tuples. played_at is an ISO-8601 string
            (e.g. Spotify's format, with or without a trailing 'Z').
        gap_minutes: session-boundary threshold in minutes.

    Returns:
        List of session dicts, chronologically ordered, each with:
        session_id, start, end, duration_minutes, track_ids, track_count.
    """
    if not plays:
        return []

    sorted_plays = sorted(plays, key=lambda p: _parse(p[0]))
    gap_threshold_seconds = gap_minutes * 60

    groups = [[sorted_plays[0]]]
    for prev, curr in zip(sorted_plays, sorted_plays[1:]):
        gap_seconds = (_parse(curr[0]) - _parse(prev[0])).total_seconds()
        if gap_seconds > gap_threshold_seconds:
            groups.append([curr])
        else:
            groups[-1].append(curr)

    sessions = []
    for i, group in enumerate(groups, start=1):
        start = group[0][0]
        end = group[-1][0]
        duration_minutes = (_parse(end) - _parse(start)).total_seconds() / 60
        sessions.append({
            "session_id": i,
            "start": start,
            "end": end,
            "duration_minutes": duration_minutes,
            "track_ids": [track_id for _, track_id in group],
            "track_count": len(group),
        })
    return sessions


if __name__ == "__main__":
    plays = load_plays()
    sessions = detect_sessions(plays)
    print(f"Loaded {len(plays)} plays -> {len(sessions)} sessions")
    for s in sessions:
        print(
            f"  session {s['session_id']}: {s['track_count']} tracks, "
            f"{s['duration_minutes']:.1f} min, {s['start']} -> {s['end']}"
        )
