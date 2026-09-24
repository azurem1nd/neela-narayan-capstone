# TRACK RECORD

TRACK RECORD is a Spotify-connected listening companion that finds the contexts hidden in the way you listen to music.

Instead of organising music by genre, artist, or album, it looks at listening behaviour — repetition, returns, sessions, and listening patterns — and turns them into personal contexts.

## How it works

1. Connect your Spotify account.
2. TRACK RECORD retrieves your recent listening history.
3. Listening sessions are detected from gaps between plays.
4. Listening behaviour is analysed using repetition, active days, session duration, and artist/track patterns.
5. Behavioural patterns are classified into contexts such as **Spiral, Trigger, Companion, Locked, Explore,** and **Glimpse**.
6. Contexts are presented as visual records.
7. A context can be turned into a Spotify playlist.

## Why

Spotify records what you listen to, but not necessarily the context behind it.

TRACK RECORD asks:

> **What if my listening history could remember the way I listened, not just what I listened to?**

It turns listening behaviour into personal, revisitable playlists.

## AI

Claude Code is used as an AI-assisted development agent for implementation, debugging, testing, and iteration.

The core listening analysis is deterministic. A Gemini-powered interpretation layer is being added to replace hardcoded context descriptions with context-specific explanations and playlist descriptions.

## Tech

* Python / Flask
* Spotify Web API
* Spotify OAuth
* Spotify Web Playback SDK
* HTML / CSS / JavaScript
* Claude Code
* Gemini
* Railway

## Current status

* Spotify authentication
* Recent listening history
* Session detection
* Behavioural context classification
* Context-based track selection
* Visual context cards
* Spotify playlist creation and reuse
* Playlist detail and browser playback
* Open in Spotify
* Gemini interpretation layer in progress
