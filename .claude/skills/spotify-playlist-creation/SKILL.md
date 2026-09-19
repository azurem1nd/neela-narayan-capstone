---
name: spotify-playlist-creation
description: Create a real Spotify playlist (create + add tracks) from a list of track IDs and a playlist name. Use whenever a set of tracks needs to be materialized as a playable Spotify playlist, regardless of caller (an LLM agent, a manual script, a future clustering pipeline).
---

# Spotify Playlist Creation

## Purpose
Create a Spotify playlist from a given list of track IDs and a playlist name — including actually adding the tracks to it. Use this whenever a set of tracks (e.g. a Gemini/LLM agent's tool call, a manual script, or a future clustering-generated cluster of songs) needs to become a real, playable Spotify playlist. This is a standalone job, independent of who or what is invoking it.

## Prerequisites
- An existing spotipy OAuth setup (`SpotifyOAuth` + a `CacheFileHandler` pointed at an absolute cache path).
- Required scope: `playlist-modify-private` (use `playlist-modify-public` instead if the playlist should be public — the scope must match the `public` flag passed when creating the playlist).
- If the app was previously authorized with a narrower scope, expanding it requires a fresh consent — see Pitfall 3.

## Procedure
Creating a playlist and populating it is **two separate API calls** — never assume one call does both:

1. **Create the playlist:**
   ```python
   playlist = sp.current_user_playlist_create(name, public=False)
   ```
   Use `current_user_playlist_create` (posts to `/me/playlists`). Do **not** use `user_playlist_create` (posts to the legacy `/users/{user_id}/playlists`) — see Pitfall 1.

2. **Add the tracks:**
   ```python
   sp.playlist_add_items(playlist["id"], track_ids)
   ```
   `track_ids` is a list of bare Spotify track ID strings (not full `spotify:track:...` URIs).

**Optional playlist description:** `current_user_playlist_create`/`user_playlist_create` both accept a `description` kwarg (verified against the installed spotipy 2.26.0's signature) — pass it at creation time, it can't be added after the fact via `playlist_add_items`. The canonical wrapper, `spotify_playlist.py::create_playlist(sp, track_ids, name, description="")`, exposes this — e.g. `context-detection`'s `CATEGORY_DESCRIPTIONS` text is passed through as a context's description when `/create-playlist` materializes it, so the playlist itself explains what the category means, not just its name.

## Naming Convention (for repeated top-tracks test runs)

When this skill is used to materialize a snapshot of a user's *current* top tracks (as in `experiments/gemini-agent-test/agent_test.py`), name the playlist deterministically as:

```
Top X Current - dd/mm/yy
```

where `X` is the actual number of tracks requested and the date is the run's actual date, no time component (e.g. `Top 10 Current - 18/09/26`). This keeps repeated test runs from producing ambiguous, identically-named playlists in the library. Compute this name in Python at call time (`datetime.now().strftime('%d/%m/%y')`, with the track count as a variable driving both the name and the request) and pass it in explicitly — don't rely on the calling LLM to format the date correctly.

This convention is specific to repeated top-tracks snapshots. A future caller (e.g. the clustering pipeline naming a playlist after a detected cluster like "companion" or "spiral") would use its own naming scheme, not this one — `create_playlist` itself stays generic and takes whatever `name` its caller decides on.

**What "Current" means:** the top tracks feeding this playlist come from `current_user_top_tracks`, which defaults to `time_range="medium_term"` — Spotify's own definition of this is "approximately last 6 months," not a real-time notion of "current." (Spotify's other options: `short_term` is "approximately last 4 weeks," `long_term` is "calculated from ~1 year of data and including all new data as it becomes available.") If the intent is a genuinely recent snapshot rather than a 6-month trend, request `time_range="short_term"` explicitly instead of relying on the default.

## Known Pitfalls

**1. `user_playlist_create` (legacy `POST /users/{user_id}/playlists`) returns a bare, undocumented 403 — even when everything else is correct.**
Verified root cause (confirmed by direct testing, superseding an earlier, disproven theory that blamed OAuth scope): this happens even with the correct scope genuinely granted, the app owner's account listed under the Spotify Developer Dashboard's Users and Access, the app in Development Mode, and a Premium account. It was confirmed by calling `POST /v1/me/playlists` directly with the identical access token via raw `requests` and seeing it succeed (`201`), while the identical token against `POST /v1/users/{user_id}/playlists` returns the bare 403.
- **Fix:** always use `sp.current_user_playlist_create(name, public=...)`.
- **Related spotipy quirk worth knowing:** its cache file's `scope` field is not trustworthy for debugging scope issues. In `spotipy/oauth2.py`, `_add_custom_values_to_token_info()` overwrites the real token response's `scope` with whatever was *requested* (`token_info["scope"] = self.scope`) before caching it. To check the real granted scope, call Spotify's token endpoint directly with `requests`, bypassing spotipy.

**2. LLM function-calling (e.g. Gemini) passes numeric arguments as float, not int.**
Function-calling protocols typically have only one numeric type, so an integer-typed argument can arrive as `5.0` instead of `5`. Spotify's API rejects a float where it expects an int (400 error).
- **Fix:** cast defensively inside the function itself (e.g. `limit = int(limit)`) — never trust the caller to send the correct Python type.

**3. Expanding OAuth scope needs a forced, visible consent screen.**
If a cache/token file already exists from a prior, narrower-scope authorization, just changing the `scope=` string in code doesn't reliably guarantee the user is shown a new consent screen.
- **Fix:** when expanding scope, use a fresh/separate cache path and pass `show_dialog=True` to `SpotifyOAuth`, forcing a visible consent screen every time. Confirm the user actually saw and approved a screen listing the requested permissions before trusting the resulting token.

## Verification Checklist
- [ ] Playlist ID captured from step 1's return value before calling step 2
- [ ] Track IDs are bare Spotify track ID strings, not full URIs
- [ ] `public=` flag matches the scope actually granted (`playlist-modify-private` ↔ `public=False`, `playlist-modify-public` ↔ `public=True`)
- [ ] Confirmed via the Spotify app/web that the playlist actually exists with the correct tracks — not just that the API call returned success
- [ ] If scope was just expanded, confirm a real consent screen was shown and approved, not silently skipped
