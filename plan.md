Plan: Context-Based Music Clustering ("Untitled Vinyl Player" project)
Problem

Existing tools organize music by genre, artist, or era, and generic auto-playlists (e.g. Spotify's Daily Mix) are unclaimed and impersonal. People's real listening life is organized around context — a train song, a shower playlist, an obsessive three-day repeat — but that context evaporates because no one manually tags it. Music also gets forgotten simply because new releases keep flooding in, not because it stopped mattering.

Core Mechanism

Detect listening context automatically from session-level behavior — time of day, day of week, session duration, and repeat intensity — and use that context (not genre or manual tagging) as the anchor for a cluster. A cluster persists even as the songs inside it change over time (e.g. "shower songs" stays a stable identity even as which tracks live there shifts).

Visual Model

A turntable/player as the home screen. The active cluster loads onto the platter. Other clusters are browsable as physical discs on a shelf below — tap one to load it. This replaces a flat list/grid with a "crate-digging" interaction.

MVP Scope (what actually gets built and demoed)
Pull personal listening history (Spotify data export, since live API doesn't expose full history or skip data)
Detect session boundaries (e.g. gap-based: >30 min silence = new session)
Cluster sessions using time-of-day, day-of-week, and repeat-count as features
Auto-generate a plain-language label suggestion per cluster from its context (e.g. "mornings, ~10 min")
Simple visualization proving clusters are distinguishable — does not need to be the full turntable/shelf UI yet; a clean list or basic chart is acceptable for MVP
Demo success criterion: at least 3–4 clusters emerge from real personal data that feel recognizable and can be labeled in one sentence without straining
Final Goals (stretch, beyond MVP)
Full turntable + shelf interactive UI (as prototyped)
Manual rename/merge/split of clusters, feeding back into future clustering
"Obsessive repeat" micro-clusters (single track, bounded timeframe) as a distinct cluster type
Resurgence detection (a dormant cluster/track reactivating)
Persistent cluster identity across song turnover, visualized (e.g. disc "wear" over time)
AI-Involvement Level

Target: Collaborative build — AI-assisted implementation, human-directed design.

Reasoning: The conceptual design (visual metaphor, clustering logic, differentiation from existing tools) was developed independently through iterative refinement across multiple sessions. Implementation (data pipeline, clustering script, scaffolding) is being built with Claude Code as a coding partner, using Plan Mode before each significant implementation step so that architecture decisions are reviewed before code is written, not after. Every plan is reviewed and approved manually before execution; nothing is accepted un-reviewed. This keeps authorship of the idea and design decisions with me, while using AI to accelerate implementation of well-specified pieces.

