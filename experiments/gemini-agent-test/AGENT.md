# Gemini Spotify Agent (`agent_test.py`)

## Project Context

This experiment lives inside the "Untitled Vinyl Player" capstone, whose core purpose is context-based clustering of Spotify listening history — grouping tracks by detected patterns like time-of-day, repeat behavior, and session context into categories such as "companion," "spiral," or "trigger." This Gemini agent does **not** currently have access to or awareness of that clustering/session-detection logic — it only operates on the two narrow functions described below (`get_top_tracks`, `create_playlist`). It's a standalone proof-of-concept for the function-calling pattern itself, not an integrated part of the pipeline.

## What this is

A test of whether Gemini can act as an **agent** — given a natural-language goal, it decides on its own which of two available functions to call and in what order, rather than following a hard-coded call sequence. Gemini never executes anything itself: it only decides and requests; `agent_test.py` executes the real Python function locally and reports the result back. This is a standalone assessment of whether an LLM-orchestrated function-calling pattern is viable, not a component of the capstone's core clustering pipeline.

**This is fully isolated from the main "Untitled Vinyl Player" pipeline.** It does not read or write `listening_history.db`, does not touch `pull_history.py`/`run_pull.sh`, and does not use any session-detection or clustering logic. It uses its own OAuth token cache (`.cache_experiment`, separate from the main pipeline's `.cache`) so re-authenticating for this experiment never affects the live cron-driven data collection. See `ASSESSMENT.md` for the full experiment write-up and outcome.

## Tools available to the agent

Two plain Python functions are declared to Gemini as callable tools (`tools=[get_top_tracks, create_playlist]` — the SDK derives each function's schema automatically from its type hints and docstring):

- **`get_top_tracks(limit: int = 5) -> list[dict]`** — reads the user's most-listened tracks from Spotify (`sp.current_user_top_tracks`). Returns a list of `{id, name, artist}` dicts.
- **`create_playlist(track_ids: list[str], name: str) -> dict`** — creates a new private Spotify playlist and adds the given tracks to it. Returns `{playlist_id, playlist_url, name, track_count}`. See `.claude/skills/spotify-playlist-creation/SKILL.md` for exactly how this is implemented and the pitfalls involved — not duplicated here.

## How the decision loop works

1. `run_agent(prompt)` configures Gemini and starts a chat with `enable_automatic_function_calling=False` — this is what forces manual execution instead of the SDK silently calling the functions for you.
2. The natural-language prompt is sent to Gemini. Gemini's response may contain one or more `function_call` parts (its request to invoke a tool) instead of, or alongside, plain text.
3. The loop inspects `response.candidates[0].content.parts` for `function_call` entries:
   - **If none are found**, the loop ends — Gemini is done calling tools and `response.text` is its final natural-language answer.
   - **If any are found**, for each one: look up the real Python function by name (`AVAILABLE_FUNCTIONS[call.name]`), pull out the arguments Gemini supplied (`dict(call.args)`), and actually execute it locally. The call and its result are printed at each step so the reasoning is visible.
4. Each function's result is wrapped as a `function_response` and sent back to Gemini in the same chat (`chat.send_message(...)`), which lets Gemini see the outcome and decide its next move — call another tool, or stop and answer.
5. Steps 3–4 repeat until Gemini stops requesting function calls. In the current test prompt, this takes exactly two rounds: `get_top_tracks` first, then `create_playlist` using the track IDs from the first result — but the loop itself places no limit on how many rounds or which order the tools are called in; that's entirely Gemini's decision each time.

## OAuth scopes required, and why

`SCOPE = "user-top-read playlist-modify-private"`, on its own token cache (`.cache_experiment`):
- **`user-top-read`** — required by `get_top_tracks` (`current_user_top_tracks`), which does not work under the main pipeline's `user-read-recently-played` scope.
- **`playlist-modify-private`** — required by `create_playlist` to create/add tracks to a private playlist.

Neither scope is present in the main pipeline's `.cache` (which only ever requested `user-read-recently-played`), which is exactly why this experiment authenticates separately rather than reusing it.

## Known pitfalls

Not repeated here — see `.claude/skills/spotify-playlist-creation/SKILL.md` for the verified root causes and fixes (the legacy-playlist-endpoint 403, Gemini's float/int argument coercion, and forcing a visible consent screen when expanding scope).
