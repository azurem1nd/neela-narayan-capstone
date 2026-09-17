# Assessment 2 — Gemini Agent Experiment

## Purpose
Standalone test to evaluate whether Gemini can act as an agent using function-calling to:
1. Pull my top 5 tracks from Spotify
2. Create a playlist from those tracks

This is isolated from the main "Untitled Vinyl Player" pipeline (context-based clustering) — it does not use listening_history.db, session detection, or any clustering logic. It's a separate test of whether an LLM-orchestrated agent pattern is viable, not a feature of the core MVP.

## Scope
- New folder: experiments/gemini-agent-test/
- New file: agent_test.py
- Uses existing spotipy OAuth (expanded scope: playlist-modify-private, added for this test only)
- Uses GEMINI_API_KEY from .env for function-calling via google-generativeai

## Outcome
Worked end-to-end: Gemini correctly reasoned through the two-step task, called `get_top_tracks` then `create_playlist` in the right order via manual function-calling (no auto-execution), and a real private playlist was created on Spotify from the results.

Issues hit and fixed along the way:
- `gemini-2.0-flash` has been retired; API error pointed directly to its replacement, `gemini-3.6-flash`.
- Gemini's function-calling protocol has no distinct integer type, so numeric args (e.g. `limit`) arrive as floats — had to cast to `int()` inside the tool function.
- Spotify's legacy `user_playlist_create` (`POST /users/{user_id}/playlists`) now returns a bare, undocumented 403 even with correct scope, dashboard config, and a Premium account. Switched to `current_user_playlist_create` (`POST /me/playlists`), which works.
- Required expanding OAuth scope to `user-top-read playlist-modify-private`, done via a separate `.cache_experiment` token file so the live cron-driven main pipeline's `.cache` was never touched.

Conclusion: an LLM-orchestrated agent pattern (declare tools, let the model choose calls, execute locally, feed results back) is viable for this kind of task with Gemini's function-calling — the friction was in API/library currency (model name, type coercion, deprecated endpoint), not the orchestration pattern itself.
