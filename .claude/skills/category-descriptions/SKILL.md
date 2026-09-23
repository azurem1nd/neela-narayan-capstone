---
name: category-descriptions
description: Canonical source of the short, human-voiced CATEGORY_DESCRIPTIONS text for each listening-context category (Trigger/Companion/Spiral/Locked/Exploration/Glimpse) -- plain-language explanations of what a category means, shown in the app's UI and written into a created Spotify playlist's description field. Use when adding a category, renaming one, or changing description wording.
---

# Category Descriptions

## Purpose
Give each listening-context category a short, human-voiced explanation of
*what it means* -- conversational, not clinical -- distinct from the
per-session evidence line (`context["description"]`, e.g. "3 of 23 tracks
show this pattern") which explains the basis for *one specific session*.
This is the text a person actually reads to understand what "Trigger" or
"Locked" is telling them about their own listening, both on the page and
inside a playlist they create from it.

## Prerequisites
- `CATEGORY_DESCRIPTIONS` lives in `context_detection.py`, keyed by the
  exact label strings `build_contexts()` assigns (`QUALIFYING_LABELS`'s
  three track-level labels, plus `Locked`/`Exploration`/`Glimpse`).
- No calibration/threshold work needed -- this is hand-written prose, not
  a derived value. The *meaning* behind each category is owned elsewhere
  (`memory-category-thresholds/SKILL.md` for Trigger/Companion/Spiral,
  `context-detection/SKILL.md` for Locked/Exploration/Glimpse) -- this
  skill owns the *wording*, not the classification logic.

## Procedure

**The dict** (`context_detection.py`):
```python
CATEGORY_DESCRIPTIONS = {
    "Trigger": "You repeated a song several times, but only within the same day.",
    "Companion": "You returned to a song across different days.",
    "Spiral": "You played a song intensely and repeatedly in a short period.",
    "Locked": "You stayed with a smaller set of artists and tracks, creating a familiar listening loop.",
    "Exploration": "You moved across many different artists and tracks without one strong repetition pattern.",
    "Glimpse": "A fleeting listen, with too little repetition to reveal a pattern.",
}
```

**Attached to every context** inside `build_contexts()`:
```python
contexts.append({
    ...
    "category_description": CATEGORY_DESCRIPTIONS[label],
    ...
})
```

**Used in two places:**
1. `templates/contexts.html` renders it next to the per-session evidence
   line: `{{ context.category_description }}`.
2. `app.py`'s `/create-playlist` route passes it through as the actual
   Spotify playlist description:
   ```python
   create_playlist(sp, match["track_ids"], name, description=match["category_description"])
   ```
   `spotify_playlist.py::create_playlist()`'s `description` param forwards
   it to `sp.current_user_playlist_create(name, public=False, description=description)`
   (see `spotify-playlist-creation/SKILL.md`).

## Voice/tone guidelines for future descriptions
- **Second person** ("you played," "you wandered") -- it's describing the
  reader's own listening back to them, not a report about a generic user.
- **Conversational, not clinical.** No feature names, no thresholds, no
  metrics leaking into the text (never "play_count," "active_days,"
  "distinct_artist_count," "≥15%," etc.) -- the *why* behind a category
  lives in the technical skills; this text is the plain-language result.
- **Sentence fragments are fine** ("A fleeting listen, with too little
  repetition to reveal a pattern.") -- matches the existing six, which
  mix full sentences and fragments freely.
- **Short.** One sentence or fragment, matching the length of the
  existing six (roughly 6-16 words) -- not a definition, a description.
- **Describe the felt pattern, not the mechanism** -- "you were locked
  in," not "you listened to few artists relative to tracks."

## Current canonical descriptions
| Category | Description |
|---|---|
| Trigger | You repeated a song several times, but only within the same day. |
| Companion | You returned to a song across different days. |
| Spiral | You played a song intensely and repeatedly in a short period. |
| Locked | You stayed with a smaller set of artists and tracks, creating a familiar listening loop. |
| Exploration | You moved across many different artists and tracks without one strong repetition pattern. |
| Glimpse | A fleeting listen, with too little repetition to reveal a pattern. |

## Known Limitations
- **No fallback for a missing key.** `CATEGORY_DESCRIPTIONS[label]` is a
  plain dict lookup with no `.get()`/default -- if `context_detection.py`
  ever adds or renames a label without a same-commit update here,
  `build_contexts()` raises `KeyError` immediately rather than silently
  showing blank/placeholder text. Deliberate: a missing description
  should fail loudly during development, not ship silently.
- **Ghost/Return have no entries** -- neither is implemented in
  `classify_track()` yet (see `memory-category-thresholds/SKILL.md`), so
  there's nothing to describe. Add entries here in the same change that
  implements either.
- **Wording is editorial, not calibrated.** Unlike `MIN_REPRESENTATION_RATIO`
  or `MIN_DISTINCT_TRACKS_FOR_EVIDENCE`, there's no real-data process
  behind these strings -- changing one is a writing decision, not a
  threshold decision, and doesn't need the same evidentiary bar.
- **Two sources of truth for "what a category is."** This skill owns the
  *words*; `memory-category-thresholds/SKILL.md` and
  `context-detection/SKILL.md` own the *rule*. If a category's underlying
  meaning changes, update the rule's skill and consider whether the
  wording here still matches.

## Verification Checklist
- [ ] Every label `build_contexts()` can currently produce (`Trigger`,
      `Companion`, `Spiral`, `Locked`, `Exploration`, `Glimpse`) has a
      `CATEGORY_DESCRIPTIONS` entry -- no `KeyError` when building contexts
- [ ] Each category's description renders correctly and non-empty on
      `/analyze`, visually confirmed against a real or synthetic session
      of that category
- [ ] A playlist created via `/create-playlist` shows the matching
      description in its **Spotify description field**, checked in the
      actual Spotify app/web -- not just trusting the API response
- [ ] New/changed wording follows the voice guidelines above (second
      person, conversational, no clinical/technical terms, short)
- [ ] If a description's wording changes, `context-detection/SKILL.md`'s
      cross-reference (or copy, if duplication was kept) doesn't silently
      go stale
