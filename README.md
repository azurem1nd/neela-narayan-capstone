# Untitled Vinyl Player

Untitled Vinyl Player is a Spotify-connected listening companion that finds the
contexts hidden in the way you listen to music.

Instead of organizing music by genre, artist, or album, it looks at listening
behaviour, when you listen, how long you listen, what you repeat, and when a
listening pattern appears, and turns those patterns into persistent listening
contexts.

The result is a collection of "records" representing moments and habits in
your listening history.

## How it works

1. Connect your Spotify account.
2. The app retrieves your recent listening history.
3. Listening sessions are detected from gaps between plays.
4. Sessions are grouped using behavioural patterns such as:
   - time of day
   - day of week
   - session duration
   - repeat intensity
5. These groups become listening contexts.
6. Each context is represented visually as a record.
7. A context can be turned into a Spotify playlist.

## Why

Music is often remembered through context:

- the songs played every morning
- the playlist repeated for an entire day
- music associated with a particular routine
- something you listened to obsessively for a short period and then abandoned

Untitled Vinyl Player tries to preserve those contexts instead of letting them
disappear into listening history.

## Tech

- Python / Flask
- Spotify Web API
- Spotify OAuth
- HTML / CSS / JavaScript
- SQLite
- Claude Code for AI-assisted development

## Current status

This is an ongoing prototype.

The current version:
- connects to Spotify
- retrieves recent listening history
- detects listening sessions
- groups sessions into contexts
- presents contexts through a vinyl / record-sleeve interface
- can create Spotify playlists from detected contexts

## Future direction

- In-page music playback using Spotify's Web Playback SDK
- Persistent context identity as listening behaviour changes
- Rename, merge and split contexts
- Manually add or remove tracks
- Detect short-lived obsessive listening patterns
- Detect when an old listening context resurfaces
