SKILL 1
# Skill: Spotify Playlist Creation

## Purpose
Create a Spotify playlist from a given list of track IDs. Used whenever a set of tracks (e.g., a detected cluster) needs to be materialized as a real, playable Spotify playlist.

## Prerequisites
- Existing spotipy OAuth setup
- **Required scope: `playlist-modify-private`** (creating a public playlist needs `playlist-modify-public` instead)
- This scope must be present in the token from the start — see "Known pitfall" below.

## Procedure
Creating a playlist is a **two-step API operation**, not one call:
1. `sp.user_playlist_create(user_id, name, public=False)` — creates the empty playlist, returns a playlist object containing its ID
2. `sp.playlist_add_items(playlist_id, track_ids)` — adds tracks to the newly created playlist

Do not assume a single call handles both steps.

## Known pitfalls (discovered via real debugging, Sept 2026)

**1. Stale OAuth cache silently reuses old, insufficient scope.**
If a `.cache` file already exists from a prior, narrower-scope authorization (e.g., only `user-read-recently-played`), simply requesting a broader scope in code does NOT guarantee the user is re-prompted. Spotipy may silently reuse the old token, causing a bare `403 Forbidden` on the new endpoint with no explanation in the error body.

**Fix:** when expanding scope, delete the existing `.cache` file (or use a separate cache path) AND set `show_dialog=True` on `SpotifyOAuth` to force a real, visible consent screen. Confirm the user actually saw and approved a screen listing the new permission — if no visible consent screen appeared, the scope expansion likely didn't take effect.

**2. Gemini function-calling passes numbers as float, not int.**
If a function-calling schema (e.g., Gemini's) is the caller, integer parameters (like `limit=5`) may arrive as `5.0` (float) rather than `5` (int). Spotify's API rejects float values for integer parameters.

**Fix:** cast defensively inside the function itself (`limit = int(limit)`), rather than trusting the caller's type.

**3. A bare `403 Forbidden` with no body detail can have several distinct causes** — don't assume it's one specific thing:
- Insufficient/stale scope (see pitfall #1 — check this first)
- App still in Spotify Developer Dashboard "Development Mode" with account not properly added under Users and Access
- (Ruled out in our case: Spotify Premium is NOT required for playlist creation — Free tier can create playlists; this was a false lead worth not re-chasing)

## Verification checklist
- [ ] `.cache` deleted / fresh, `show_dialog=True` set, when scope has changed
- [ ] Confirm user saw a real consent screen listing both old and new permissions
- [ ] Playlist ID captured from step 1 before calling step 2
- [ ] Track IDs passed as a list, in Spotify URI or bare ID format matching what `playlist_add_items` expects