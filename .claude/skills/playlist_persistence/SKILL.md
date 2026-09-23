---
name: playlist_persistence
description: Decides whether a context card click should reuse an existing Spotify playlist, update it in place, or create a new one, scoped per authenticated user + context. Use whenever the card-click -> playlist flow changes, when a new caller needs "give me the current playlist for this user+context" without duplicating it, or when adjusting the pattern-change threshold/signature formula.
---

# Playlist Persistence

## Purpose
Before this skill existed, clicking a context card called
`spotify_playlist.create_playlist()` unconditionally -- every click
created a brand new Spotify playlist, even for the exact same user and
the exact same listening pattern seconds later. A playlist represents
a **listening pattern**, not a button click or an analysis run:
repeated analysis of essentially the same pattern should resolve to
the same Spotify playlist, and a genuinely evolved pattern should
update that playlist rather than spawn a duplicate.

This module (`playlist_persistence.py`) is the single decision point
for that: given `(user_id, context, current_track_ids)`, it decides
**reuse** / **update** / **create**, and is the only thing in this
project that stores a Spotify playlist ID anywhere.

## Prerequisites
- An already-authenticated `spotipy.Spotify` client (`sp`) -- this
  module never touches OAuth/session; that stays `app.py`'s job (see
  `get_spotify_client()`).
- The context's canonical label (`context_detection.py`'s
  `context_id`, e.g. `"Exploration"`) and its current
  `playlist_track_ids` -- computed by `context_detection.py`, passed
  in as-is, never recomputed or second-guessed here.
- A playlist name and description already computed by
  `playlist_naming.py` / `category-descriptions` (in
  `context_detection.py`) -- this module only uses them when it
  actually needs to create a playlist, never generates its own.
- `spotify_playlist.py`'s `create_playlist()` / `update_playlist()` --
  the only two functions that actually call Spotify's create/replace
  endpoints. This module decides *which* to call; it never calls
  `sp.current_user_playlist_create()` or `sp.playlist_replace_items()`
  directly itself.

## Data model
One SQLite file, `track_record.db` (repo root, gitignored -- same
convention as `pull_history.py`'s `listening_history.db`; stdlib
`sqlite3`, no new dependency). One table:

```sql
CREATE TABLE context_playlists (
    user_id TEXT NOT NULL,              -- sp.current_user()["id"]
    context TEXT NOT NULL,              -- context_detection.py's context_id
    spotify_playlist_id TEXT NOT NULL,
    spotify_playlist_url TEXT NOT NULL,
    track_ids TEXT NOT NULL,            -- JSON array, as last sent to Spotify
    track_signature TEXT NOT NULL,      -- see "Track signature" below
    created_at TEXT NOT NULL,           -- ISO 8601 UTC, set once
    updated_at TEXT NOT NULL,           -- ISO 8601 UTC, set on create/update only
    last_seen_at TEXT NOT NULL,         -- ISO 8601 UTC, set on every resolve
    PRIMARY KEY (user_id, context)
);
```

`PRIMARY KEY (user_id, context)` is the whole multi-user-safety
mechanism: a lookup is always scoped to both, so `user_A + Exploration`
and `user_B + Exploration` are physically different rows and can never
collide or leak into each other.

## Track signature
`compute_track_signature(track_ids)`: `sha256("\n".join(sorted(set(track_ids))))`.
Sorting the deduplicated set first makes the signature depend only on
*which* tracks qualify, never their order or how many times a caller's
list happened to repeat one -- `[A, B, C]` and `[C, A, B]` hash
identically.

## Change ratio (same-pattern vs. meaningfully-changed)
`compute_change_ratio(old_ids, new_ids)` is the **Jaccard distance**
between the two track-ID sets:

```
change_ratio = |old ^ new| / |old | new|
             = 1 - |old & new| / |old | new|
```

(`^` symmetric difference, `|` union, `&` intersection.) `0.0` means
identical sets; `1.0` means completely disjoint sets. Symmetric by
construction -- swapping which set is "old" and which is "new" never
changes the result. Two sets have `change_ratio == 0.0` if and only if
they have the same `track_signature`; that's not a coincidence, it's
the same condition checked two ways.

```python
PLAYLIST_PATTERN_CHANGE_THRESHOLD = 0.30
```

Below this, an existing playlist is reused untouched. At or above it,
its tracks are replaced in place. **Provisional, like
`MIN_REPRESENTATION_RATIO` and `MIN_DISTINCT_TRACKS_FOR_EVIDENCE`
elsewhere in this project (see `context-detection/SKILL.md`)** -- no
historical multi-run track-set-diff data exists yet to calibrate
against, since this is the first feature that could ever produce it.
Real per-session distinct-track counts observed elsewhere in this
project run roughly 14-25 for a single fetch, so a handful of tracks
changing lands well under 30% while substantial turnover clearly
exceeds it -- a reasonable starting point given that scale, not a
guess pulled from nowhere, but revisit once real repeated-visit data
exists.

## Decision table (`resolve_context_playlist`)
Called as `resolve_context_playlist(sp, user_id, context, track_ids, playlist_name, description)`:

1. **No `track_ids`** -> `action: "error"`, nothing created. (Empty
   track sets shouldn't occur given `context_detection.py`'s own
   guarantees, but this is not assumed.)
2. **No saved record for `(user_id, context)`** -> `action: "create"`
   via `spotify_playlist.create_playlist()`; save the new record.
3. **Saved record exists, but its `spotify_playlist_id` no longer
   resolves on Spotify** (cheap `sp.playlist(id, fields="id")` check)
   -> treated exactly like case 2: create a replacement, overwrite the
   record. (User deleted the playlist from Spotify directly, etc.)
4. **Saved record valid, `change_ratio < 0.30`** -> `action: "reuse"`.
   Zero Spotify writes -- only `last_seen_at` (and the stored
   `track_ids`/`track_signature`, refreshed to the current set so the
   *next* comparison is against the latest observed pattern, not a
   stale one from several visits ago) are updated.
5. **Saved record valid, `change_ratio >= 0.30`** -> `action: "update"`
   via `spotify_playlist.update_playlist()` (replaces the playlist's
   tracks in one call, same Spotify playlist ID/URL). Updates
   `track_ids`/`track_signature`/`updated_at`/`last_seen_at`. The
   playlist's **name and description are deliberately left as
   originally created** -- the spec this module implements only calls
   for updating "its Spotify contents" and the saved
   fields/timestamps, not renaming; the tradeoff is that the playlist
   page's displayed date (parsed from the name) reflects original
   creation, not the most recent pattern change. Revisit if that
   turns out to be confusing in practice -- `sp.playlist_change_details()`
   would need to be called alongside `update_playlist()`.

Return shape (all four actions):
```python
{"action": "reuse" | "update" | "create" | "error",
 "playlist_id": str | None, "playlist_url": str | None,
 "track_ids": [...], "context": str, "reason": str}
```

## Context disappearing / reappearing
If a saved record exists for a context that the current analysis run
doesn't currently produce, **nothing happens** -- there is no cleanup
job, and `resolve_context_playlist` is only ever called for a context
that *is* in the current run's card list (the card wouldn't exist to
click otherwise). The Spotify playlist is never deleted. If that
context reappears in a later run, its card click resolves against the
same saved record as always (cases 3-5 above) -- TRACK RECORD
"remembers" the pattern rather than re-deriving a fresh playlist for
it.

## Integration point
`app.py`'s `POST /create-playlist` route (route path kept stable on
purpose -- `library.js` only ever reads `data.playlist_id` back, so no
frontend contract change was needed): computes `match`/`playlist_name`
exactly as before, then calls `sp.current_user()["id"]` and
`resolve_context_playlist(...)` instead of `create_playlist()`
directly, and returns its result as JSON (or `{"error": ...}`, 400,
for the `"error"` action).

## Known Limitations
- **Filesystem persistence, not a hosted DB.** `track_record.db` is a
  local SQLite file. It survives page refreshes and new requests for
  the life of the running app instance (satisfies the actual product
  requirement), but on a host with an ephemeral filesystem and no
  mounted volume (some Render/Heroku-style deploys), it resets on
  redeploy. The `Procfile` here (`gunicorn app:app --bind 0.0.0.0:$PORT`,
  no declared persistent disk) doesn't rule this out. Still a strict
  improvement over the previous zero-persistence behavior; revisit if
  cross-deploy durability becomes a real requirement.
- **No locking against a genuine concurrent double-click race.** Two
  near-simultaneous requests for the same `(user_id, context)` (e.g.
  two browser tabs) could both see "no saved record" and both create a
  Spotify playlist; the DB upsert means the row always converges to
  one of them, but the "loser" could leave one orphaned Spotify
  playlist. Low-probability given the `Procfile`'s single (default)
  gunicorn worker; not solved here (would need a DB-level lock or
  `INSERT ... WHERE NOT EXISTS` pattern) since client-side `library.js`
  already prevents the common case (a single card's own double-click)
  with its shared `creating` flag.
- **No batching for playlists over ~100 tracks.** `update_playlist()`
  calls `sp.playlist_replace_items()` once, same as `create_playlist()`
  already called `sp.playlist_add_items()` once -- a pre-existing
  limitation of this codebase's Spotify calls, not introduced here.

## Verification Checklist
Mirrors the product spec's test cases -- run manually against a real
Spotify account (Premium not required for playlist creation, only for
Web Playback SDK playback elsewhere in the app):

- [ ] **First click**, no saved record -> `action: "create"`, exactly
      one new Spotify playlist, one new DB row.
- [ ] **Repeated click**, same user/context/tracks -> `action: "reuse"`,
      zero additional Spotify playlists.
- [ ] **Reordered tracks**, same set -> `action: "reuse"` (same
      `track_signature`).
- [ ] **Tiny change** (a track or two out of many) -> `action: "reuse"`
      (`change_ratio` below threshold).
- [ ] **Meaningful change** (substantial track-set turnover) ->
      `action: "update"`, same `playlist_id`/`playlist_url` as before,
      Spotify playlist's actual contents now match the new set.
- [ ] **Different context, same user** (e.g. Exploration vs. Trigger)
      -> independent DB rows, independent playlists.
- [ ] **Different user, same context** -> independent DB rows,
      independent playlists; user A's playlist is never returned to
      user B.
- [ ] **Context temporarily absent** from a run -> its saved record
      and Spotify playlist are untouched.
- [ ] **Context reappears** later -> resolves back to the existing
      saved playlist (case 4/5 above), not a new one.
- [ ] **Saved playlist deleted directly on Spotify** -> next resolve
      detects it (`_playlist_still_exists` returns `False`), creates a
      replacement, and the DB row now points at the new playlist ID.
