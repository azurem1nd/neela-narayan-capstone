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

## 2026-09-18 - PART A
- **Time spent:** ~4-5 hrs (spans roughly 12:58 IST through end of session; includes active build time plus discussion/analysis)
- **Tokens used:** rough estimate only, no exact telemetry for this session
- **Shipped (implemented):**
  - Built and tested `session_detection.py` + `.claude/skills/session-boundary-detection/SKILL.md`: splits chronological plays into sessions on a strict `>30-minute` gap rule (boundary is `>`, not `>=`), single-track sessions valid and never merged/discarded, duration is a raw `played_at` timestamp diff. Verified against the real DB.
  - Added `distinct_artist_count` per session: splits comma-joined multi-artist track credits (e.g. "Steve Lacy, SZA") and counts unique individual artists rather than treating each raw artist-string as atomic. Verified by hand against real data.
  - Built `track_features.py`: per-track feature extraction (`play_count`, `active_days`, `day_of_week_distribution`, `gap_hours`, `density_plays_per_day_busiest_window`) from `listening_history.db`. Found and fixed a real bug the same day: the initial time-of-day variance used naive linear variance, which falsely scored a consistent late-night listener as erratic (23:00-01:00 spanning midnight); replaced with proper circular variance (mean resultant length on the unit circle), verified on a synthetic case (128.89 naive vs. 0.0085 circular for the identical consistent pattern).
  - Implemented `classify_track()`/`classify_all_tracks()` in `track_features.py`: real, data-derived thresholds for Trigger (`play_count>=2 AND active_days<0.5`), Companion (`play_count>=2 AND active_days>=0.5`), and Spiral (`density_plays_per_day_busiest_window>=3`, explicitly marked provisional — validated by only one real track). The Trigger/Companion `active_days=0.5` boundary was chosen because it sits inside a real empty gap in the sorted data (0.03 → 0.95, nothing in between). Ghost/Return were explicitly **not** implemented — proposed logic documented, but the longest real gap in the dataset (~40.64h) is nowhere near the proposed 7-day dormancy threshold, so there is no real example to validate against yet.
  - Created a combined `track-pattern-classification` skill documenting the above, then reorganized it into two focused skills per a later decision: `.claude/skills/track-feature-extraction/SKILL.md` (extraction only) and `.claude/skills/memory-category-thresholds/SKILL.md` (classification/thresholds only) — pure reorganization, no logic changes.
  - Minor hygiene: added `__pycache__/` to `.gitignore`.
- **Investigated (analysis performed, no code changes resulting):**
  - Confirmed the cron pipeline (`run_pull.sh` / `pull_history.py`) is healthy and actively collecting. An earlier appearance of "stale data" was traced to my own UTC-vs-IST timezone conversion error, not a real pipeline problem — confirmed by running the pull manually and watching the row count increase live.
  - Sorted real per-track feature distributions (`play_count`, `active_days`, `time_of_day_circular_variance`, `density`, `gap_hours`) across the full dataset to find natural breakpoints before choosing any thresholds, rather than guessing them.
  - Ran a full read-only verification of the classification system on request: confirmed Trigger's definition and implementation status, and produced a complete dataset snapshot (88 tracks, 145 plays, date range 2026-09-14 to 2026-09-18) with full per-track classification and category counts (Spiral: 1, Trigger: 2, Companion: 27, insufficient_data: 58).
  - Computed real per-session classification composition (session-level breakdown of member tracks' classifications) to evaluate whether/how track-level memory categories could extend to session-level context.
  - Confirmed (post-quota-reset) that `agent_test.py` still runs correctly end-to-end, creating a real "Top 10 Current - 18/09/26" playlist.
- **Decided (methodology agreed, not yet implemented):**
  - Decided to pursue "Approach 3" for the `insufficient_data` problem: keep track-level classification exactly as-is, and add a separate session-context layer that lets a session inherit a category from its qualifying member tracks (rather than requiring every individual track to independently qualify) — so a single-play track can still appear in a category playlist via session membership.
  - Established that Trigger and Companion are fundamentally track-level, cross-session concepts (they depend on a track's full play history, not any one session) and cannot be meaningfully redefined at the session level. Spiral, by contrast, is already session-shaped in spirit and is a plausible future candidate for being redefined as session-scoped rather than calendar-day-scoped.
  - Decided on plurality/majority as the v1 conflict-resolution rule for sessions where member tracks disagree on category (e.g. one real session: 8 Companion vs. 2 Trigger tracks → Companion wins).
  - Decided that sessions with zero track-level signal (100% `insufficient_data` — 3 real sessions currently, including a 30-track/103-minute session) must **not** be silently excluded, and require a session-native fallback classification using session-level features alone.
- **Proposed (discussed, not approved or implemented):**
  - Proposed three session-native fallback categories, deliberately distinct from Companion/Trigger/Spiral: **Glimpse** (`track_count == 1`), **Block** (`distinct_artist_count / track_count < 0.5`, concentrated/thematic listening), **Exploration** (ratio `>= 0.5`, diverse/discovery listening). Applied against the three real all-`insufficient_data` sessions as examples. Explicitly flagged as provisional — the Block/Exploration boundary is calibrated on only two real data points.
  - None of Approach 3, the plurality rule, or the Glimpse/Block/Exploration fallback has been implemented in code. Work was explicitly paused at the user's request before any implementation began.

## 2026-09-18 — Part B
(Continues from Part A; work ran past midnight into 2026-09-19.)
- **Time spent:** ~6-7 hrs (commit span 19:06 09-18 → 02:08 09-19)
- **Tokens used:** rough estimate only, no exact telemetry
- **Shipped (implemented):**
  - Built the multi-user Flask backend (`app.py`, `spotify_playlist.py`) for Railway: `/login`/`/callback` OAuth via `FlaskSessionCacheHandler` + server-side `Flask-Session` (so the token never sits in the visitor's browser), `/analyze`/`/create-playlist` as a live, stateless one-shot fetch (no DB). `Procfile`, `.env.example` added.
  - `/analyze` now calls `sp.current_user()` and surfaces `connected_as` — the app was already scoped per-user via the token but never showed who was connected.
  - Fixed the Railway deploy blocker: gunicorn defaults to `127.0.0.1:8000`, not reachable externally — bound to `0.0.0.0:$PORT` in the `Procfile`.
  - Added `session.permanent = True` and a guard for denied/missing OAuth `code` in `/callback` (previously an unhandled `KeyError` → 500).
  - Diagnosed a Railway crash: `FLASK_SECRET_KEY` is read at module level (boots-crashes if missing) vs. the lazy, function-scoped `SPOTIPY_*` reads — fixed by setting the env var.
  - Added a minimal landing page (`templates/index.html`) and post-auth confirmation flow.
  - Built `context_detection.py::build_contexts()` — the session↔classification join Part A had paused before implementing. Sessions inherit a label from qualifying member tracks by plurality vote, or fall back to `Glimpse`/`Block`/`Exploration`. `/analyze` renders real HTML (`contexts.html`); `/create-playlist` is now scoped to one session's `context_id` instead of pooling every same-labeled track across the whole fetch.
  - Fixed two real bugs found via live testing: (1) a session could be labeled "Trigger" off 1 of 21-22 tracks (4.8%) with zero competition — added `MIN_REPRESENTATION_RATIO = 0.15`, chosen by testing 10/15/20/25% against real sessions (15% was the smallest value fixing both observed thin-signal cases; 20/25% gave identical results). (2) the fallback path used raw play-event counts instead of deduplicated track counts, breaking `Glimpse` on replayed-single-track sessions.
  - Unified `Glimpse` and track-level `insufficient_data`: widened Glimpse to any session with zero qualifying tracks (not just single-track sessions) — no new threshold, reuses the existing empty/non-empty qualifying-list check.
  - Verified the full flow end-to-end against the real account (login → contexts → playlist creation → re-fetched and confirmed the created playlist's tracks matched).
  - Opened and merged PR #4 (`assessment-2-neela` → `main`); verified no conflicts before merge and confirmed `origin/main` afterward.
- **Investigated:**
  - Pre-build audit: confirmed `detect_sessions`/`classify_track` were already user-agnostic; only the auth/data-access layer was single-user.
  - OAuth production-readiness audit and Railway deployment-readiness audit (both read-only) — only real blocker found was the gunicorn bind.
  - Traced the multi-user ownership chain end-to-end — verdict: PASS, no hardcoded account/token/DB dependency.
  - Full breakdown of every context name the system can produce, distinguishing implemented vs. conceptual-only (Ghost/Return still unimplemented).
- **Decided:**
  - Live one-shot fetch, no persistent DB for the hosted app — `listening_history.db`/cron pipeline stay local-only, separate from what's served.
  - Gemini agent experiment stays out of scope for the hosted app.
  - Server-side session storage over Flask's default client-side cookie session.
  - "Context" = one detected session, not a cross-session recurring pattern — a defensible simplification of `plan.md`'s original vision given the no-persistent-DB architecture.
  - Glimpse's boundary is categorical (zero qualifying tracks), not a calibrated percentage.
- **Proposed, then rejected:**
  - A percentage-based "mostly insufficient_data" threshold for Glimpse — rejected in favor of the categorical rule, since it would need real-data calibration with no evidence to justify a specific number.

## 2026-09-19 - PART A 
- **Time spent:** ~11 hrs (real session span 02:30–13:43 IST, from local Claude Code transcript timestamps, excluding the portion already covered by Part B)
- **Tokens used:** 437,388 output tokens (real, from the local session transcript — not an estimate)
- **Shipped (implemented):**
  - Fixed `Exploration`/`Locked` to no longer require a qualifying (Spiral/Trigger/Companion) track to exist in a session — previously a session with real breadth (many distinct tracks/artists, zero repeats) fell into `Glimpse` instead, indistinguishable from a single track played once. Added `MIN_DISTINCT_TRACKS_FOR_EVIDENCE` (provisional — no real multi-track, zero-repeat session exists yet to calibrate it) as the new gate. Verified via synthetic cases and a zero-regression check against all 12 real sessions.
  - Renamed the `Block` category to `Locked` throughout code and Skills (historical `BUILD_LOG.md` entries left unchanged, as an accurate record of what it was called when built). Added `CATEGORY_DESCRIPTIONS` — short, human-voiced explanations of what each category means, shown on `/analyze` and passed through as the Spotify playlist's description field — then formalized as its own `category-descriptions` skill with voice/tone guidelines, kept separate from `context-detection`.
  - Added a raw play/session-count summary line to `/analyze` ("Fetched N plays, spanning X to Y → grouped into M sessions") so a result's shape is visible directly, not just asserted.
  - Replaced the single 50-play live fetch with pagination (up to 300 plays via Spotify's `before` cursor) — a 50-play window rarely contained enough repetition for Trigger/Companion/Spiral/Locked to fire and fragmented into too many tiny sessions.
  - Added the Playlist Nomenclature skill (`playlist_naming.py`) as the single source of truth for a playlist's name — `"{Category} - {DD Mon YYYY}"` (literal hyphen, date = creation time, not listening time) — computed once per `/analyze` request and carried through a hidden form field to `/create-playlist` so the webpage card and the real Spotify playlist always show byte-for-byte the same name. Kept separate from the existing, untouched description-generation skill.
  - **Deployment/testing:** Tested the deployed Railway version successfully, including Spotify authentication, analysis, context generation, and playlist creation. Confirmed the hosted app works end-to-end after the latest changes.
- **Investigated:**
  - Diagnosed two "duplicate category block" reports (Trigger, then Exploration) as expected per-session behavior — one context per detected session, not one per category — not a bug. Confirmed via code trace (no early-exit/filtering logic anywhere in the pipeline) and local synthetic reproduction matching the exact reported numbers.
  - Diagnosed "/analyze shows only one category" as a consequence of the live fetch window being small/temporally clustered, not a classification or rendering defect.
  - Considered switching `/analyze` to read from `listening_history.db` instead of a live fetch; found it would break multi-user isolation (every visitor would see the owner's personal data) and doesn't exist on Railway at all (gitignored, untracked) — this informed the pagination decision instead.
  - Re-confirmed the earlier second-Spotify-account 500 fix (null-track guard) was genuinely committed and pushed; could not independently confirm Railway's live deployment state or logs (no CLI/API access from this environment).
  - Recovered real historical time/token usage from the local Claude Code session transcript for BUILD_LOG purposes, rather than estimating.
- **Decided:**
  - Keep `/analyze` as a live, per-visitor fetch with no persistent database, even though it required extra work (pagination) to fix its real problem — preserves multi-user safety, which switching to a shared personal database would have broken.
  - Playlist Nomenclature and Playlist Description Generation stay separate skills/responsibilities; a playlist's name is computed once and threaded through rather than reconstructed independently on the webpage and in the Spotify API call.

## 2026-09-19 — Part B
(Continues from Part A — the frontend/visual redesign, testing, and validation phase.)
- **Time spent / tokens used:** not separately tracked for this portion of the session — see Part A above for the day's overall session figures.
- **Shipped (implemented):**
  - Moved the project from the functional MVP toward the actual visual identity of "Untitled Vinyl Player" — the frontend was redesigned around the vinyl/record-label metaphor already established in the project concept, in place of the unstyled default HTML.
  - Rebuilt the landing page around a hand-built vinyl disc and tonearm, with distinct logged-out and connected states — the record spins once Spotify is connected.
  - Redesigned the listening-context page so each detected context renders as a record-sleeve-style card instead of a plain list.
  - Redesigned the playlist-created confirmation page to match the same visual system.
  - Introduced a shared warm paper/ink/brass visual system, with a distinct muted color per listening category.
  - Set interface typography to Newsreader for the main interface and IBM Plex Mono for metadata.
  - Tightened interface copy throughout to be more direct and specific.
  - Implemented the redesign within the existing Flask application and template structure — the underlying Spotify/listening logic was not rebuilt.
- **Investigated / tested:**
  - Tested the redesigned frontend at both desktop and mobile widths.
  - Found a real mobile-only issue during that testing: text overflow caused by flexbox layout behavior.
  - Fixed the issue and re-tested the mobile layout successfully.
  - Sanity-checked the full redesign after the fix.
- **Validated (user testing):**
  - Tested the current build with 4 people.
  - All detected listening clusters were successfully shown for every tester.
  - Testers reported that the clusters felt accurate/representative of their own listening behavior.
  - Framed as early, qualitative validation of the clustering and context-detection system, not a statistically conclusive result — useful specifically because it tested whether the system's automatically generated contexts actually corresponded to how people understood their own listening behavior, not just whether the pipeline ran without errors.
- **Decided:**
  - This phase was a human-directed, AI-assisted implementation: product concept, goals, interaction direction, and visual direction came from the user; Claude Code was used to implement, inspect, test, debug, and iterate on the frontend.
  - The existing Spotify OAuth, listening-history retrieval, session detection, and context-generation logic were retained rather than rebuilt during this phase.
  - After completing and testing the redesign, the changes were committed and pushed as a checkpoint, creating a stable version to return to while continuing visual experimentation and refinement.
- **Next:** Visual refinement and asset/design iteration, including refining the vinyl, the record-sleeve/card system, colors, typography, and overall composition.

## 2026-09-22
- **Time spent:** ~7-8 hrs (commit span 16:15–23:57 IST, from git history — not separately tracked via session transcript)
- **Tokens used:** 390,901 output tokens (real, from the local session transcript — not an estimate)
- **Shipped (implemented):**
  - Rebuilt the landing page as "Track Record": initial brand palette (#FFF8E7 background, #260FC1 title/accent, #F253AD ticker), scoped to the landing page only so the rest of the app kept its existing vinyl-label identity at the time. New logged-out pitch copy about pattern-detection in listening history ("TRACK RECORD finds the patterns hiding in your listening history..."), and the footer ticker rebuilt into a seamless marquee showing "connect to spotify" / "connected to your spotify @[username]" depending on auth state.
  - Added a three.js hero graphic (static/js/turntable3d.js): a chrome/brushed-silver platter and tonearm (MeshPhysicalMaterial + a RoomEnvironment IBL for real reflections) with a black vinyl disc, procedural groove texture, and metallic label center — static while logged out, spinning once connected. Later revised the disc to a reflective/prismatic "burned CD" finish (physical iridescence plus an art-directed rainbow-streak texture). Made the disc a real link to /analyze in the connected state, with a hover/focus glow.
  - Connected-state CTA/disc label went from "see my library" to "my music library" (briefly "see my library" in between).
  - Went through several rounds of wordmark typography: the licensed Elastic font was initially unavailable, so Gluten stood in → the real Elastic.otf arrived and was wired up and verified actually loading (headless-browser check of document.fonts and the computed font) → switched to Unbounded (Google Fonts) + JetBrains Mono for a cleaner geometric look, dropping a per-letter jitter effect tuned for Elastic's hand-drawn wobble → briefly back to Elastic → briefly a local Unbounded-Regular.ttf file → settled by end of day on the Google-Fonts-loaded Unbounded (800 weight) as the wordmark's font, with JetBrains Mono for body/ticker/UI text throughout.
  - Rebuilt the landing page a second time, now pixel-matched against three supplied reference frames (disconnected/connected/about states): exact colors sampled from the references (#F0F0EB base, #BEE860 green, #E57BA1 pink ticker, #292929 ink, #260FC1 divider). This removed the three.js turntable graphic entirely (static/js/turntable3d.js deleted) since none of the reference images showed an illustration, replacing the connected-state disc link with a plain "your music library" text link.
  - Simplified further to the real 2-screen model the app actually has (logged-out: title + pitch + connect link together; logged-in: title + library link only), removing the click-to-toggle "About" panel from the previous pass.
  - Rebuilt the "my music library" page (contexts.html) as daisyUI hover-3d tilt cards — first a generic card design, then rebuilt again to pixel-match six supplied per-category reference card designs (Companion/Trigger/Locked/Spiral/Exploration/Glimpse), with layout, colors, and per-category accents all sampled from those references. context_detection.py's build_contexts()/consolidate_by_category() output feeds the cards unchanged — no classification, playlist-naming, or OAuth logic touched.
  - Added single-card (default, with prev/next + keyboard-arrow nav) and grid view modes for the library page, preserving the current card index when switching between them.
- **Investigated/fixed:**
  - The three.js hero graphic (while it still existed) was clipped/hidden behind the fixed ticker bar on short viewports — fixed with viewport-height-aware sizing, verified from 1440x650 through 1440x900.
  - The disc's material read as washed out — darkened the base gradient, pushed the streak texture to full saturation, and raised iridescence/metalness and light intensity so the reflections actually showed.
  - Found and fixed a [hidden] vs. CSS-specificity bug where the About panel and the subtitle link could both render visible at once (same class of bug as a prior fix on the library page's cards).
  - Flipped the library page to a dark background (#292929/#EEEFE9), then reverted after re-checking the six reference designs, which use a cream background with black text, not a dark theme.
  - Made the library page's UI chrome (back link, view toggle, nav buttons) consistently ink-colored instead of blue, to match the page heading.
  - Fixed the card footer so it tilts as one composition with the rest of the card — it had been a separate element outside the hover-3d wrapper and never moved on hover.
- **Decided:**
  - Landing and library page visual identity is driven directly by supplied reference images once they arrive, not further open-ended design experimentation — prior original passes (including the three.js turntable) were superseded once references landed.
  - Wordmark font settled on Unbounded via Google Fonts (no local font file) after testing Elastic (both a licensed file and a temporary stand-in) and a local Unbounded file; body/UI text settled on JetBrains Mono throughout.
  - Kept all existing OAuth/session/multi-user logic, classification, and playlist-naming untouched throughout — every visual pass in this session was frontend/presentation-layer only.
- **Next:** Work continued past midnight into 2026-09-23 on the library cards (real vector graphic/description assets, card-click navigation to a per-context detail page, text centering/positioning, background/foreground contrast) — to be logged separately.

## 2026-09-23
(Two natural phases, separated by a ~6-hour gap in commit activity — logged as Part A and Part B below rather than a single flat list.)

**Part A — library card visual polish** (continuing from 2026-09-22's "Next" note)
- **Time spent:** ~12 hrs (commit span 00:31–12:44 IST, from git history)
- **Shipped (implemented):**
  - Replaced the hand-approximated squiggle paths with the real supplied squiggle asset (Vector 4.svg), applied identically to all six cards.
  - Replaced the generic parameterized graphic approximations (dots/checker-wave/stripes/curved-stripes) with the six real per-category graphic assets (companion.svg, trigger.svg, locked.svg, spiral.svg, explore.svg, glimpse.svg), each already correctly colored for its category.
  - Gave Locked and Spiral their own dedicated scribble assets (locked_scribble.svg, spiral_scribble.svg) instead of the shared squiggle; Companion, Trigger, Exploration, and Glimpse kept the shared one.
  - Center-aligned the card description text.
  - Per explicit user direction, briefly swapped the visible card description to vector-traced mockup SVG text matching the exact reference typography, keeping the real CATEGORY_DESCRIPTIONS text available to assistive tech via a visually-hidden span — then, later the same day, reverted this after a data-flow audit found the visible description should be the real generated text per category-descriptions/SKILL.md's own documented intent, not the mockup's static placeholder wording; removed the six now-unused description SVG macros.
  - Gave the library page background a subtly distinct tone from the card itself (new --tr-page-bg token, #E7E7E1, separate from the card's own #F0F0EB) so cards read as distinct objects on the page.
  - Changed the landing page footer/ticker background from pink to #292929.
  - Replaced the plain-text "SPOTIFY.COM/TRACKRECORD" footer with the real supplied TRACKRECORD.svg wordmark, right-aligned in the card footer.
  - Added a "a library built from your listening habits" caption under "your music library" on hover/focus.
  - Added the supplied record-crate illustration to the landing page, served as static/img/record-crate.svg, shown on both the logged-in and logged-out states.
  - Gave Explore and Glimpse their own supplied number/pattern assets and real accent colors (#649AED, #E57BA1), replacing earlier approximations.
  - Restructured the card header (number + heading) from a shared flex row into a stacked CSS grid cell so the heading truly centers on the full card width independent of each category's number width; centered the date/track-count line as a single group.
  - Made the whole card clickable: added GET /context/<context_id> and templates/context_detail.html, a minimal per-context detail page reached by clicking a card (no playback or Spotify action yet, by scope) — superseded later the same day in Part B once real playlist creation and playback replaced it.
- **Investigated/fixed:**
  - Discovered locked.svg and glimpse.svg share the exact hex #9591F8 — confirmed the two categories' JPEG references only looked different due to compression noise, not a real design difference — and corrected --ctx-glimpse to match (was #9892FC, sampled from the lossier raster).
  - Found .ctx-card__desc had text-align: center but no horizontal margin, so its max-width box itself sat off-center even though its text was centered within that box; fixed on both the card description and the new context-detail description.
  - Found the card number and heading sharing one flex row meant the heading's centering was computed against "space remaining beside the number," not the true card center, so title position visually shifted per category depending on each number's width — fixed via the grid-cell restructure above; also added minimum-clearance padding for the two categories (Companion, Glimpse) whose long titles next to a wide number still ran into the glyph at true full centering.
  - Iterated the card number's outline stroke weight several times over the course of the day (0.18cqw to 0.35cqw to 0.50cqw to 1.50cqw to a final 1cqw), settling alongside the card border also moving from a fixed 1px hairline to 1cqw so it scales with the card; matched Explore/Glimpse's supplied vector-numeral outline weight to the other four categories' shared stroke system so all six read consistently.
- **Decided:**
  - The visible card description must be the real, live CATEGORY_DESCRIPTIONS text (context.category_description), not the reference mockup's static placeholder wording — category-descriptions/SKILL.md already documented this as the intended behavior.

**Part B — Web Playback SDK (Stages 1-3) and the `KeyError: 'tracks'` debugging saga**
- **Time spent:** ~1-1.5 hrs (commit span 18:50–20:01 IST, from git history)
- **Shipped (implemented):**
  - Web Playback SDK Stage 1: extended the existing OAuth SCOPE with "streaming" (nothing removed), added GET /spotify-token (reuses get_spotify_client(), never exposes the client secret), and added static/js/player.js to bootstrap a real Spotify.Player device on the context detail page with all 8 SDK event handlers wired — connection only, no playback yet.
  - Web Playback SDK Stage 2: added a temporary "PLAY TEST TRACK" button using the Stage 1 device, sending one hardcoded test track URI via Spotify's real Web API (PUT /me/player/play); narrowed the status widget's vocabulary to exactly Connecting.../Player ready/Not ready/Playing/Playback error.
  - Web Playback SDK Stage 3: connected context cards → real Spotify playlists → real playback end-to-end. A card click now POSTs to /create-playlist (JSON, not a form round-trip) and creates a real Spotify playlist via the existing create_playlist()/generate_playlist_name()/CATEGORY_DESCRIPTIONS (all reused unmodified), then navigates to a new GET /playlist/<playlist_id> page — the first real **playlist detail page** — showing the playlist's name/description/date/track-count/track-list and an **Open in Spotify** link, playable via the same SDK device: PLAY starts that exact playlist, PREV/NEXT/PLAY use the SDK's own transport methods, and player_state_changed is the only source for the "Playing" status. This retired /context/<id> and templates/context_detail.html from earlier in the day, plus the already-unused templates/playlist_created.html.
  - Diagnosed and fixed a live 500 error reported when clicking a context card — **playlist API debugging**: added temporary diagnostics (full server-side traceback, exception type/message surfaced in the JSON response and browser console) to /create-playlist, then extended the same wrapping to /playlist/<id> and get_spotify_client() once the first pass showed the error was happening elsewhere. This surfaced the real exception: **`KeyError: 'tracks'`**.
  - First fix attempt for the KeyError: added a one-second retry on the theory that a just-created playlist's read could momentarily lag (eventual consistency). Ruled out — the user reported "still the same error" after the retry was in place.
  - Second fix attempt: added the missing playlist-read-private OAuth scope, since SCOPE had only ever requested playlist-modify-private (needed to create a playlist, not read one back). Also did not resolve it on its own.
  - Correct fix, and the KeyError's actual resolution: verified directly against Spotify's current live API reference that a playlist's track-listing field is now **"items"** (a paging object), with "tracks" documented as deprecated — spotipy just passes through whatever Spotify's API actually sends, it doesn't rename fields. Updated /playlist/<playlist_id> to read `playlist["items"]["items"]`, with each entry's track under `"item"` (not `"track"`), guarded with isinstance checks so a malformed/missing response degrades to an explicit "couldn't load the track list" message instead of crashing or silently claiming 0 tracks; also handled a null/removed item and episode items (skipped, not assumed to be tracks). Removed the now-unneeded eventual-consistency retry. Added track artwork/album/duration display to the playlist detail page, not shown before.
- **Investigated/fixed:**
  - Traced the live 500 through three rounds of diagnosis (eventual-consistency retry, then missing OAuth scope, then the real tracks→items field rename) before reaching the actual root cause — each ruled-out hypothesis was disproven by the error persisting unchanged, not guessed away.
- **Decided:**
  - Kept the playlist-read-private scope fix even though it wasn't the crash's root cause — independently correct and necessary for /playlist/<id> to read a private playlist's contents at all.
  - Built the Web Playback SDK integration in three incremental, independently verified stages (connection only, then one test track, then full real playlist playback) rather than all at once.
- **Remaining limitations at end of day:**
  - Real SDK `ready` events and real browser playback could not be confirmed from this development environment across any of the three stages — the sandboxed headless browser used for automated verification lacks Widevine/EME DRM support, so Spotify.Player's constructor itself fails with "No supported keysystem was found," independent of whether the integration code is correct. Confirmation needed the user's own real, logged-in, Premium-account browser session.
  - No 30-second-preview playback mechanism was built on 23 September — what was implemented is full-track playback via a real Spotify Connect device (the Web Playback SDK), which is a different mechanism from Spotify's separate 30-second `preview_url` API. Checked for explicitly; found no evidence it was built this day.

**Approx. token usage:** ~486,754 tokens (real output-token counts recovered from the local Claude Code session transcript, summed across the full 2026-09-23 IST calendar day — not a rough guess: 302,603 for the Part A span + 184,151 for the Part B span)

