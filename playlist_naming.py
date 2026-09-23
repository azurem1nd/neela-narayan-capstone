"""Playlist Nomenclature: the single source of truth for a context-derived
playlist's display name -- used identically on the webpage card and as
the actual Spotify playlist name. See
.claude/skills/playlist-nomenclature/SKILL.md for the full methodology.
"""

from datetime import datetime

_MONTH_ABBREVIATIONS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr", 5: "May", 6: "Jun",
    7: "Jul", 8: "Aug", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dec",
}


def generate_playlist_name(category: str, created_at: datetime) -> str:
    """Build "{category} - {DD Mon YYYY}" -- a literal hyphen (not an em
    dash), and a hardcoded month table so the output doesn't depend on
    the deployment environment's locale (unlike strftime's %b).

    created_at is when the user is creating the playlist, not when the
    underlying listening happened -- a single fetch can span many days.
    Does not validate `category` against a fixed list, so it works
    unchanged for any future category (e.g. Ghost/Return, if built).
    """
    return f"{category} - {created_at.day:02d} {_MONTH_ABBREVIATIONS[created_at.month]} {created_at.year}"


def parse_playlist_name(name: str) -> dict:
    """Reverse of generate_playlist_name(): split a name this module
    produced back into its category and date-string parts.

    Exists for a page that only has a playlist's name back from Spotify
    to work with (Spotify's playlist object has no separate "category"
    or "created date" field of its own) -- reads the same literal
    " - " separator generate_playlist_name() writes, rather than
    introducing a second, independent notion of the format.
    """
    category, _, date_str = name.partition(" - ")
    return {"category": category, "date": date_str}
