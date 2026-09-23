"""Playlist persistence: decides whether a context card click should
reuse an existing Spotify playlist, update it in place, or create a
new one -- instead of the previous behavior of creating a brand new
Spotify playlist on every single click.

See .claude/skills/playlist_persistence/SKILL.md for the full
methodology (exact change-ratio formula, decision table, known
limitations).

Deliberately does NOT own: Spotify OAuth/session (app.py), context
classification (context_detection.py), playlist naming
(playlist_naming.py), description generation (category-descriptions,
in context_detection.py), or the actual Spotify create/replace API
calls (spotify_playlist.py) -- this module only decides which of
those to invoke, and remembers the result for next time.
"""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from spotipy.exceptions import SpotifyException

from spotify_playlist import create_playlist, update_playlist

REPO_DIR = Path(__file__).resolve().parent
DB_PATH = REPO_DIR / "track_record.db"

# Below this fraction of changed tracks (symmetric, order-independent
# -- see compute_change_ratio), an existing playlist is reused as-is.
# At or above it, the existing playlist's tracks are replaced rather
# than a new playlist being created. 0.30 is the spec's suggested
# starting point; no historical multi-run track-set-diff data exists
# yet to calibrate against (this is the first feature that could ever
# produce it). Real per-session distinct-track counts observed
# elsewhere in this project (context-detection/SKILL.md) run roughly
# 14-25 for a single fetch, so a handful of tracks changing lands well
# under 30% while substantial turnover clearly exceeds it -- a
# reasonable, non-arbitrary starting point given that scale, but
# provisional like MIN_REPRESENTATION_RATIO and
# MIN_DISTINCT_TRACKS_FOR_EVIDENCE elsewhere in this project. Revisit
# once real repeated-visit data exists.
PLAYLIST_PATTERN_CHANGE_THRESHOLD = 0.30


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the persistence table if it doesn't exist yet. Safe to
    call on every app startup (CREATE TABLE IF NOT EXISTS)."""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS context_playlists (
                user_id TEXT NOT NULL,
                context TEXT NOT NULL,
                spotify_playlist_id TEXT NOT NULL,
                spotify_playlist_url TEXT NOT NULL,
                track_ids TEXT NOT NULL,
                track_signature TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                PRIMARY KEY (user_id, context)
            )
        """)
        conn.commit()
    finally:
        conn.close()


def compute_track_signature(track_ids: list[str]) -> str:
    """Deterministic, order-independent fingerprint of a track set.

    sorted(set(...)) first so [A, B, C] and [C, A, B] (and any
    duplicates) all hash identically -- the signature represents the
    qualifying *set*, not a specific fetch's ordering or shape.
    """
    unique_sorted = sorted(set(track_ids))
    joined = "\n".join(unique_sorted)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def compute_change_ratio(old_ids: list[str], new_ids: list[str]) -> float:
    """Symmetric, order-independent fraction of the track set that
    changed -- the Jaccard distance between the two track-ID sets:

        change_ratio = |old ^ new| / |old | new|
                      = 1 - |old & new| / |old | new|

    (^ = symmetric difference, | = union, & = intersection.) 0.0 means
    identical sets; 1.0 means completely disjoint sets. Symmetric by
    construction -- which set is "old" and which is "new" doesn't
    affect the result, only which tracks differ does. Two sets with
    the same signature (see compute_track_signature) always have a
    change_ratio of exactly 0.0, and vice versa -- signature equality
    and set equality are the same condition.
    """
    old_set, new_set = set(old_ids), set(new_ids)
    union = old_set | new_set
    if not union:
        return 0.0
    symmetric_difference = old_set ^ new_set
    return len(symmetric_difference) / len(union)


def _get_saved_record(user_id: str, context: str) -> sqlite3.Row | None:
    conn = _get_conn()
    try:
        cur = conn.execute(
            "SELECT * FROM context_playlists WHERE user_id = ? AND context = ?",
            (user_id, context),
        )
        return cur.fetchone()
    finally:
        conn.close()


def _upsert_record(
    user_id: str, context: str, playlist_id: str, playlist_url: str,
    track_ids: list[str], signature: str, created_at: str, updated_at: str, last_seen_at: str,
) -> None:
    conn = _get_conn()
    try:
        conn.execute("""
            INSERT INTO context_playlists
                (user_id, context, spotify_playlist_id, spotify_playlist_url,
                 track_ids, track_signature, created_at, updated_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (user_id, context) DO UPDATE SET
                spotify_playlist_id = excluded.spotify_playlist_id,
                spotify_playlist_url = excluded.spotify_playlist_url,
                track_ids = excluded.track_ids,
                track_signature = excluded.track_signature,
                updated_at = excluded.updated_at,
                last_seen_at = excluded.last_seen_at
        """, (
            user_id, context, playlist_id, playlist_url,
            json.dumps(track_ids), signature, created_at, updated_at, last_seen_at,
        ))
        conn.commit()
    finally:
        conn.close()


def _playlist_still_exists(sp, playlist_id: str) -> bool:
    """Cheap existence check (id field only) against Spotify -- used
    to detect a saved playlist the user deleted (or that otherwise no
    longer resolves) so a replacement can be created instead of
    silently failing to reuse/update it (Test 10 in SKILL.md)."""
    try:
        sp.playlist(playlist_id, fields="id")
        return True
    except SpotifyException:
        return False


def resolve_context_playlist(
    sp, user_id: str, context: str, track_ids: list[str],
    playlist_name: str, description: str = "",
) -> dict:
    """The single decision point for what a context card click should
    do: reuse an existing Spotify playlist, update its tracks in
    place, or create a new one. See module docstring / SKILL.md for
    the full decision table.

    Args:
        sp: an already-authenticated spotipy.Spotify client -- this
            function never authenticates, that stays app.py's job.
        user_id: sp.current_user()["id"], the real Spotify user id.
            Never share persistence across different user_ids.
        context: the canonical category label (e.g. "Exploration") --
            context_detection.py's context_id, used as-is.
        track_ids: the context's current playlist_track_ids, already
            computed and filtered by context_detection.py.
        playlist_name: already computed via playlist_naming.py.
        description: already computed category description text.

    Returns:
        {"action": "reuse" | "update" | "create" | "error",
         "playlist_id": str | None, "playlist_url": str | None,
         "track_ids": [...], "context": str, "reason": str}
    """
    if not track_ids:
        return {
            "action": "error",
            "playlist_id": None,
            "playlist_url": None,
            "track_ids": [],
            "context": context,
            "reason": "no qualifying tracks -- refusing to create an empty playlist",
        }

    now = datetime.now(timezone.utc).isoformat()
    new_signature = compute_track_signature(track_ids)

    saved = _get_saved_record(user_id, context)

    if saved is not None and not _playlist_still_exists(sp, saved["spotify_playlist_id"]):
        # Saved record points at a playlist Spotify no longer has --
        # can't reuse or update it, so fall through exactly like "no
        # saved record" below (creates a replacement).
        saved = None

    if saved is None:
        result = create_playlist(sp, track_ids, playlist_name, description=description)
        _upsert_record(
            user_id, context, result["playlist_id"], result["playlist_url"],
            track_ids, new_signature, now, now, now,
        )
        return {
            "action": "create",
            "playlist_id": result["playlist_id"],
            "playlist_url": result["playlist_url"],
            "track_ids": track_ids,
            "context": context,
            "reason": "no existing playlist for this user + context",
        }

    old_ids = json.loads(saved["track_ids"])
    change_ratio = compute_change_ratio(old_ids, track_ids)

    if change_ratio < PLAYLIST_PATTERN_CHANGE_THRESHOLD:
        # Identical (ratio 0.0) or only a small change -- reuse
        # without touching Spotify at all beyond the existence check
        # above. Still refreshes the saved track_ids/signature to the
        # current set so future comparisons are against the latest
        # observed pattern, not a stale one from several visits ago.
        _upsert_record(
            user_id, context, saved["spotify_playlist_id"], saved["spotify_playlist_url"],
            track_ids, new_signature, saved["created_at"], saved["updated_at"], now,
        )
        reason = (
            "track set unchanged since last resolve" if change_ratio == 0.0
            else f"change ratio {change_ratio:.0%} below {PLAYLIST_PATTERN_CHANGE_THRESHOLD:.0%} threshold"
        )
        return {
            "action": "reuse",
            "playlist_id": saved["spotify_playlist_id"],
            "playlist_url": saved["spotify_playlist_url"],
            "track_ids": track_ids,
            "context": context,
            "reason": reason,
        }

    # Meaningful change -- update the existing playlist's contents in
    # place rather than creating a duplicate. Name/description are
    # deliberately left as originally created (see SKILL.md).
    update_playlist(sp, saved["spotify_playlist_id"], track_ids)
    _upsert_record(
        user_id, context, saved["spotify_playlist_id"], saved["spotify_playlist_url"],
        track_ids, new_signature, saved["created_at"], now, now,
    )
    return {
        "action": "update",
        "playlist_id": saved["spotify_playlist_id"],
        "playlist_url": saved["spotify_playlist_url"],
        "track_ids": track_ids,
        "context": context,
        "reason": f"change ratio {change_ratio:.0%} at/above {PLAYLIST_PATTERN_CHANGE_THRESHOLD:.0%} threshold -- updated existing playlist",
    }
