# Build Log

## 2026-09-11
- **Time spent:** ~1 hr
- **Tokens used:** ~25000 (plan.md drafting via Claude)
- **Shipped:** Capstone idea locked in, repo created, `project-setup` branch, plan.md committed with descriptive message

## 2026-09-16
- Time spent: ~1 hr
- Token used: ~15000
- Shipped: potify Developer app created; `test_connect.py` written and working; spotipy installed in `.venv`; Authorization Code flow completed end-to-end (browser login → callback → auth success); confirmed live pull of Recently Played tracks with real timestamps.

## 2026-09-16
- Set up gitignore, for .cache, .env and .venv. 
- Because I was connecting to the Spotify API. It is in .env where credentials/configuration can live. Don't want an API secret accidentally appearing in a public GitHub repository.

## 2026-09-17
- **Time spent:** ~3 hrs
- **Tokens used:** rough estimate only, no exact telemetry for this session — likely well over 100000 given the length and iteration
- **Shipped:**
  - Built and successfully tested `agent_test.py` (`assessment-2-neela` branch) — a Gemini function-calling agent that pulls top tracks (`get_top_tracks`) and creates a real private Spotify playlist from them (`create_playlist`), with manual (not auto) function execution. Verified end-to-end against the real Spotify account, not just a clean local run.
  - Debugged and fixed two real issues: (1) Gemini's function-calling protocol has no distinct integer type, so numeric args like `limit` arrive as floats — fixed by casting to `int()` inside the tool function; (2) Spotify's legacy `user_playlist_create` endpoint (`POST /users/{user_id}/playlists`) returns a bare, undocumented 403 even with correct scope, dashboard config, and a Premium account — confirmed via direct API testing, fixed by switching to `current_user_playlist_create` (`POST /me/playlists`).
  - Consolidated the lessons into `.claude/skills/spotify-playlist-creation/SKILL.md`, correcting a factual error along the way: an earlier draft (`skills.md`) had misattributed the 403 to a stale OAuth cache silently reusing insufficient scope — disproven by directly querying Spotify's token endpoint, which confirmed the correct scope was genuinely granted all along.
  - Tested with top 5, 10, and 20 track counts.
  - Established, then corrected, a playlist naming convention: settled on `"Top X Current - dd/mm/yy"` (X = dynamic track count, date only, no time), replacing an earlier em-dash + timestamp version.
  - Hit Gemini's free-tier daily quota limit (20 `generate_content` calls/day for the model in use) partway through testing.
  - Accidentally deleted all 6 test playlists while cleaning up the library — confirmed via the API that Spotify's "unfollow playlist" call permanently deletes a playlist you own rather than just hiding it. Unrecoverable via the API, but trivially recreatable since names/track IDs were already logged; recreation queued for once the Gemini quota resets.
  - Wrote `experiments/gemini-agent-test/AGENT.md` documenting the experiment's purpose, tools, decision loop, and required scopes — explicit that it has no access to or awareness of the core clustering/session-detection pipeline.

