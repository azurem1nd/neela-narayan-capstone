---
name: memory-category-thresholds
description: Classify tracks into memory categories (Trigger/Companion/Spiral implemented; Ghost/Return proposed but not implemented) using explicit, data-derived thresholds applied to features from track-feature-extraction. This is the approved classification methodology — thresholds and rationale live here.
---

# Memory Category Thresholds

## Purpose
Classify individual tracks by their listening *pattern* — not genre, not one-off popularity, but the shape of how a track gets replayed over time (steady companion, sudden burst, escalating repeat, dormant-then-reactivated). This is the classification stage: it consumes features already computed by the `track-feature-extraction` skill and maps them onto named categories using thresholds chosen against real feature distributions, not guessed in the abstract.

**Epistemic scope, important:** these labels describe a measurable behavioral *shape* in play timestamps — same-day concentration, cross-day return, burst density. They are **not** a claim about a verified psychological trigger, life event, or place. The data can establish *that* a pattern occurred, never *why*. Treat every label below as "candidate," not "proven cause."

## Prerequisites
- Per-track features already computed — see the `track-feature-extraction` skill for how (`extract_all_track_features` in `track_features.py`).
- Python stdlib only — no dependencies beyond what extraction already uses.
- **Canonical implementation lives in `track_features.py` at the repo root**, in `classify_track` and `classify_all_tracks`. The code shown below is a direct copy for reference, not a second source of truth.

## Procedure

Thresholds below were chosen by sorting real per-track features from the live dataset and looking for natural breakpoints, not picked in the abstract. See Known Limitations for what's provisional vs. solid.

```python
def classify_track(features: dict) -> str:
    """
    Classify a track's listening pattern from its features.

    Returns one of: "Spiral", "Trigger", "Companion", "insufficient_data".

    IMPORTANT: these labels describe a measurable behavioral SHAPE in the
    play timestamps (same-day concentration, cross-day return, burst
    density) -- they are not a claim about a verified psychological
    trigger, life event, or place. The data can establish THAT a pattern
    occurred, never WHY.

    Thresholds (Spiral is provisional, Ghost/Return are not implemented --
    see Known Limitations):
      - insufficient_data: play_count < 2 (no repeat to measure a pattern from)
      - Spiral (PROVISIONAL): density_plays_per_day_busiest_window >= 3
      - Trigger: play_count >= 2 and active_days < 0.5 (all plays same day, never returned)
      - Companion: play_count >= 2 and active_days >= 0.5 (returned on a later day)

    Spiral is checked before Trigger/Companion since it's the more specific
    signal. A track can in principle satisfy both Spiral's density
    condition and Trigger's same-day condition at once (true for the one
    current real example, "One Of Your Girls") -- in that case Spiral
    takes precedence.
    """
    if features["play_count"] < 2:
        return "insufficient_data"

    if features["density_plays_per_day_busiest_window"] >= 3:
        return "Spiral"

    if features["active_days"] < 0.5:
        return "Trigger"

    return "Companion"


def classify_all_tracks(db_path=DB_PATH) -> list[dict]:
    """Extract features for every track and attach a classification label to each."""
    features = extract_all_track_features(db_path)
    for f in features:
        f["classification"] = classify_track(f)
    return features
```

**Why these thresholds, specifically:**
- **Trigger vs. Companion boundary (`active_days` at 0.5)** sits inside a real *empty gap* in the data — the actual sorted `active_days` values for multi-play tracks jump straight from `0.03` to `0.95` with nothing in between, so any threshold placed in that gap is equally defensible. `0.5` was picked as a clean, explainable round number, not because it's more "correct" than `0.4` or `0.6`.
- **Trigger requires only `play_count >= 2`**, not a higher bar. A same-day replay with no later return (e.g. "bebe," "Static": played, then replayed once 37 minutes later, never again) is already a meaningful signal on its own, even without a third play.
- **Companion requires only `play_count >= 2`**, same reasoning — a single overnight return (e.g. many tracks at `active_days ≈ 0.95`, one repeat ~23h later at nearly the same time of day) already shows a real signal via `time_of_day_circular_variance ≈ 0.01` (extremely consistent), even this early.

### Ghost / Return — NOT IMPLEMENTED (known limitation, not a bug)

Proposed logic, recorded here so it isn't re-derived from scratch later, but **deliberately left uncoded**:
- **Ghost**: a track that was Companion-shaped (established repeat pattern), then went **7+ days silent**.
- **Return**: 2+ renewed plays after that silent gap — i.e. a Ghost track reactivating.

**Why unimplemented:** the current dataset's longest observed gap between two plays of the same track is only **~40.64 hours** (~1.7 days). There is no real example anywhere near a 7-day silence to validate a dormancy threshold against — any number picked now would be pure guesswork with zero real data behind it, unlike Trigger/Companion/Spiral above. Revisit once multi-week data has accumulated (the cron pipeline is already collecting continuously) and a real long-gap example actually exists to test against.

## Known Edge Cases

**1. Spiral is provisional — validated by exactly one real track.** Only "One Of Your Girls" (3 plays in ~6 minutes, `density=3`) has ever hit the `density_plays_per_day_busiest_window >= 3` threshold. One example is not enough to be confident the boundary is in the right place (unlike Trigger/Companion's `active_days` boundary, which sits in a real empty gap in the data) — revisit this threshold once more burst-pattern tracks accumulate.

**2. Companion currently spans two very different maturity levels without distinguishing them.** A large share of current Companion tracks have only *one* overnight repeat (`active_days ≈ 0.95-0.96`) — 19 of 27 Companion tracks, as of this writing; a smaller, more established set (the Steve Lacy tracks) have `play_count` up to 6 and `active_days` up to 3.76 — 8 of 27, as of this writing. Both sit under the same "Companion" label today. These counts are a reference point, not a live count — they will shift as more data accumulates. This is a known limitation, not something to fix right now — a future "strength" or "confidence" score could distinguish early-forming vs. established Companions without needing a new category.

**3. Ghost/Return are unimplemented — see the "Ghost / Return" subsection above** for the proposed logic and why it's deliberately left uncoded (no real example of a 7+ day gap exists yet to validate against).

## Verification Checklist

**Trigger/Companion/Spiral — can verify now:**
- [ ] Every track with `play_count == 1` classifies as `insufficient_data`, never force-fit into a named category
- [ ] A track with `play_count >= 2`, `active_days < 0.5`, `density < 3` classifies as `Trigger`
- [ ] A track with `play_count >= 2`, `active_days >= 0.5`, `density < 3` classifies as `Companion`
- [ ] A track with `density_plays_per_day_busiest_window >= 3` classifies as `Spiral`, even if it would otherwise also match Trigger (precedence check, real example: "One Of Your Girls")
- [ ] Total classified counts sum to the total track count (`Spiral + Trigger + Companion + insufficient_data == len(features)`), confirming no track is double-counted or dropped
- [ ] Each of Trigger/Companion/Spiral is reachable by at least one real track in the current dataset

**Ghost/Return — cannot verify, not implemented:**
- [ ] N/A until multi-week data exists with a real 7+ day gap to test against
