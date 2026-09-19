---
name: playlist-nomenclature
description: Single source of truth for a context-derived playlist's name -- "{Category} - {DD Mon YYYY}" (literal hyphen, not an em dash; date is when the user creates the playlist, not when the underlying listening happened). Used identically on the /analyze webpage card and as the actual Spotify playlist name. Use when changing the playlist naming format, or when adding a new context category and confirming it needs no naming-side changes.
---

# Playlist Nomenclature

## Purpose
Produce a consistent, predictable name for a context-derived playlist —
`{Category} - {DD Mon YYYY}` — and be the *only* place that constructs
one, so the webpage card and the real Spotify playlist always show the
exact same string. This is deliberately separate from classification
(`context-detection`/`memory-category-thresholds`), the human-voiced
description (`category-descriptions`), and playlist creation itself
(`spotify-playlist-creation`) — it only decides the *name*, nothing else.

## Prerequisites
- Input: a category string (whatever `context_detection.py::build_contexts()`
  put in `context["label"]`) and a `datetime` representing when the user
  is creating the playlist. No validation against a fixed category list —
  works unchanged for any category, including ones not implemented yet
  (`Ghost`/`Return` are documented in `memory-category-thresholds/SKILL.md`
  but not built; this skill needs no changes if/when they are).
- **Canonical implementation lives in `playlist_naming.py` at the repo
  root.** Import `generate_playlist_name` from there.

## Procedure

```python
from datetime import datetime

_MONTH_ABBREVIATIONS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}

def generate_playlist_name(category: str, created_at: datetime) -> str:
    return f"{category} - {created_at.day:02d} {_MONTH_ABBREVIATIONS[created_at.month]} {created_at.year}"
```

**Single call site, compute-once-and-carry-forward** (`app.py`):
```python
# /analyze -- one shared timestamp for the whole request
now = datetime.now(timezone.utc)
for context in contexts:
    context["playlist_name"] = generate_playlist_name(context["label"], now)
```
```html
<!-- templates/contexts.html -->
<p><strong>{{ context.playlist_name }}</strong></p>
...
<input type="hidden" name="playlist_name" value="{{ context.playlist_name }}">
```
```python
# /create-playlist -- forwards the submitted value verbatim, never recomputes
playlist_name = request.form.get("playlist_name")
result = create_playlist(sp, match["track_ids"], playlist_name, description=match["category_description"])
```
`templates/playlist_created.html` needs no changes — it already renders
`{{ result.name }}`, which is whatever `create_playlist()` was given.

## Known Limitations

**1. Name is computed once at `/analyze` render time, not at the literal `/create-playlist` POST moment.** `/analyze` and `/create-playlist` are separate requests with no shared server-side state for this — the only way to guarantee the exact string shown on the card is the exact string sent to Spotify is to compute it once and carry it forward via a hidden form field (the same pattern `context_id` already uses), rather than having each route independently reconstruct it. Consequence: a user who loads `/analyze` right before midnight and clicks "Create" right after gets the pre-midnight date. Deliberate, not a bug — recomputing fresh at POST time would usually match but could silently diverge across that exact boundary, which is worse for the "exact same name" requirement.

**2. Date is UTC.** There's no per-user timezone concept anywhere else in this app (Spotify's `played_at` values and the `/analyze` debug summary line are both UTC too) — nothing to draw a more "local" date from.

**3. Duplicate names are possible and unresolved.** Two playlists created for the same category on the same day (two different sessions both "Companion," or clicking "Create" twice) get the literal same name — Spotify allows duplicate playlist names, and this format (no track count, no time) doesn't disambiguate them. Matches the naming spec as given; not treated as a defect.

**4. `context_id` re-fetch drift is pre-existing and unrelated.** `/create-playlist` already re-fetches and re-classifies fresh (see `context-detection/SKILL.md` Known Limitation #3) — if listening data changed between viewing and clicking, the matched session could differ from what was shown. This skill doesn't change that; carrying `playlist_name` forward means the user gets exactly the name they saw, which is arguably more correct than silently recomputing a possibly-different name from newer data.

## Verification Checklist
- [ ] `generate_playlist_name("Companion", datetime(2026, 9, 18, tzinfo=timezone.utc))` returns exactly `"Companion - 18 Sep 2026"`
- [ ] The separator is a literal hyphen (`chr(45)`), not an em dash (`chr(8212)`) or en dash
- [ ] A single-digit day zero-pads (`day=5` → `"05"`, not `"5"`)
- [ ] All 12 months produce the correct abbreviation without relying on `strftime`/server locale
- [ ] The name shown on a `/analyze` card, the hidden `playlist_name` field's value, and the `name` actually sent to `sp.current_user_playlist_create()` are byte-for-byte identical for the same request
- [ ] `playlist_created.html` renders the correct name with zero changes to that template
- [ ] A category not in `context_detection.py`'s current label set (e.g. a future `Ghost`) still produces a correctly formatted name with no code change here
