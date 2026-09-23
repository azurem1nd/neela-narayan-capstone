"""Spotify playlist creation, reusable across callers.

See .claude/skills/spotify-playlist-creation/SKILL.md for the full
methodology and known pitfalls (legacy endpoint 403, etc.). This module
is the canonical implementation that skill documents.
"""


def create_playlist(sp, track_ids: list[str], name: str, description: str = "") -> dict:
    """Create a private playlist for sp's authenticated user and add tracks to it.

    Args:
        sp: an already-authenticated spotipy.Spotify client.
        track_ids: Spotify track IDs to add to the new playlist.
        name: name for the new playlist.
        description: optional playlist description (shown in the Spotify
            app), e.g. a category's CATEGORY_DESCRIPTIONS text.
    """
    playlist = sp.current_user_playlist_create(name, public=False, description=description)
    sp.playlist_add_items(playlist["id"], track_ids)
    return {
        "playlist_id": playlist["id"],
        "playlist_url": playlist["external_urls"]["spotify"],
        "name": name,
        "track_count": len(track_ids),
    }


def update_playlist(sp, playlist_id: str, track_ids: list[str]) -> dict:
    """Replace an existing playlist's tracks with track_ids, in place.

    Used by playlist_persistence.py when a context's qualifying track
    set has meaningfully changed since it was last resolved -- keeps
    the same Spotify playlist identity (id/URL never change) instead
    of creating a duplicate. Deliberately does not touch the
    playlist's name or description; see
    .claude/skills/playlist_persistence/SKILL.md for why an "update"
    leaves those as originally created.

    Note: like create_playlist() above, this sends track_ids in one
    call with no >100-item batching -- a pre-existing limitation of
    this codebase's Spotify calls, not new here.
    """
    sp.playlist_replace_items(playlist_id, track_ids)
    return {"playlist_id": playlist_id, "track_count": len(track_ids)}
