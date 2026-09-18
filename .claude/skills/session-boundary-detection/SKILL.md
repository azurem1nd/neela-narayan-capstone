---
name: session-boundary-detection
description: Split a chronological list of Spotify plays (played_at, track_id) into listening sessions using a 30-minute gap rule, and compute basic per-session features. Foundational data-processing step for clustering — use whenever session boundaries need to be derived from listening_history.db.
---

# Session Boundary Detection

## Purpose
Given the chronological list of `(played_at, track_id)` plays in `listening_history.db`, split them into listening sessions and compute basic features per session (start, end, duration, tracks). This is foundational data-processing infrastructure for the capstone's clustering work — session objects are the unit that later gets clustered by time-of-day, day-of-week, and repeat-count, not raw individual plays.

## Prerequisites
- Python stdlib only (`sqlite3`, `datetime`, `pathlib`) — no external dependencies.
- Input data: the `plays` table in `listening_history.db` (see `pull_history.py` for its schema) — specifically `played_at` (ISO-8601 string, primary key) and `track_id`.
- **Canonical implementation lives in `session_detection.py` at the repo root** (alongside `pull_history.py`, since both operate on the same DB). Import `detect_sessions`/`load_plays` from there — the code shown below is a direct copy for reference, not a second source of truth. If the two ever diverge, `session_detection.py` is correct.

## Procedure

1. **Load plays, sorted ascending by `played_at`:**
   ```python
   def load_plays(db_path):
       conn = sqlite3.connect(db_path)
       rows = conn.execute(
           "SELECT played_at, track_id FROM plays ORDER BY played_at ASC"
       ).fetchall()
       conn.close()
       return rows
   ```

2. **Detect sessions from the loaded plays:**
   ```python
   from datetime import datetime

   GAP_MINUTES = 30

   def _parse(played_at: str) -> datetime:
       return datetime.fromisoformat(played_at.replace("Z", "+00:00"))

   def detect_sessions(plays: list[tuple[str, str]], gap_minutes: float = GAP_MINUTES) -> list[dict]:
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
   ```

3. **Output shape** — a list of session dicts, chronologically ordered:
   ```python
   {
       "session_id": 1,
       "start": "2026-09-18T09:23:05.626Z",
       "end": "2026-09-18T09:49:53.950Z",
       "duration_minutes": 26.8,
       "track_ids": ["1OWBh1eVxUdA1Z6UA8r4nh", "22NHkFYbgxB2Zirj29Gbp8"],
       "track_count": 2,
   }
   ```

## Known Edge Cases

**1. Single-track sessions are valid and must never be discarded or merged.** A lone play with a >30-minute gap on both sides is a real session (e.g. a one-off skip or a single "trigger" listen) — the algorithm naturally produces these since every play belongs to exactly one group, including groups of size 1. Don't add logic to filter these out later.

**2. The gap rule is strictly "exceeds," not "meets or exceeds."** A gap of *exactly* 30:00 between two consecutive plays does **not** start a new session — only a gap *greater than* 30 minutes does. This is implemented as `gap_seconds > gap_threshold_seconds` (strict `>`), not `>=`. This is a common off-by-one point to get wrong; test the exact boundary explicitly (see Verification Checklist).

**3. `played_at` parsing matches the exact convention already used in `pull_history.py`** (`.replace("Z", "+00:00")` before `datetime.fromisoformat`), kept consistent with the existing codebase rather than relying on Python 3.11+'s native `Z`-suffix support in `fromisoformat` — this way the code stays correct even if ever run under an older Python.

**4. Duplicate `played_at` values across two rows can't happen** given `played_at TEXT PRIMARY KEY` in the existing `plays` schema, so this isn't handled as a special case — if it ever did happen, a zero-second gap would just place both in the same session, which is the correct behavior anyway.

**5. Empty input returns an empty list, not an error or an exception.**

**6. Session duration is a simple timestamp diff (last play's `played_at` minus first play's `played_at`), not adjusted for track length.** A single-track session therefore always has `duration_minutes == 0` — this is intentional, not a bug, per the stated design (duration measures the span between recorded play *events*, not actual listening time).

## Verification Checklist
- [ ] A single-play input returns exactly one session with `track_count == 1` and `duration_minutes == 0`
- [ ] Two plays exactly 30:00 apart land in the **same** session (boundary is strict `>`, not `>=`)
- [ ] Two plays 30:01 (or more) apart are split into two separate sessions
- [ ] Sessions are returned in chronological order, with `session_id` starting at 1 and incrementing
- [ ] `track_ids` within each session preserve chronological play order, not just membership
- [ ] `duration_minutes` for a multi-play session matches a hand-computed `(end - start)` for at least one real example from `listening_history.db`
- [ ] An empty plays list returns `[]` with no exception
- [ ] Running against the real `listening_history.db` produces a session count that's sane relative to the total play count (i.e. sessions ≤ plays, and roughly matches what you'd expect from eyeballing timestamp gaps in the data)
