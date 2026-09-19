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
