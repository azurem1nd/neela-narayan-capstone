import sqlite3
import sys
import traceback
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler

REPO_DIR = Path(__file__).resolve().parent
load_dotenv(REPO_DIR / ".env")

DB_PATH = REPO_DIR / "listening_history.db"
CACHE_PATH = REPO_DIR / ".cache"


def get_spotify_client():
    cache_handler = CacheFileHandler(cache_path=str(CACHE_PATH))
    auth_manager = SpotifyOAuth(
        scope="user-read-recently-played",
        cache_handler=cache_handler,
        open_browser=False,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS plays (
            played_at TEXT PRIMARY KEY,
            track_name TEXT NOT NULL,
            artist_name TEXT NOT NULL,
            track_id TEXT,
            played_at_epoch_ms INTEGER NOT NULL
        )
    """)
    conn.commit()


def get_latest_epoch_ms(conn):
    row = conn.execute("SELECT MAX(played_at_epoch_ms) FROM plays").fetchone()
    return row[0]


def played_at_to_epoch_ms(played_at: str) -> int:
    dt = datetime.fromisoformat(played_at.replace("Z", "+00:00"))
    return int(dt.timestamp() * 1000)


def main():
    conn = sqlite3.connect(DB_PATH)
    init_db(conn)

    sp = get_spotify_client()
    after = get_latest_epoch_ms(conn)
    if after:
        results = sp.current_user_recently_played(limit=50, after=after)
    else:
        results = sp.current_user_recently_played(limit=50)

    items = results["items"]
    inserted = 0
    for item in items:
        played_at = item["played_at"]
        track = item["track"]
        artist_name = ", ".join(a["name"] for a in track.get("artists", [])) or "Unknown"
        cur = conn.execute(
            "INSERT OR IGNORE INTO plays "
            "(played_at, track_name, artist_name, track_id, played_at_epoch_ms) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                played_at,
                track["name"],
                artist_name,
                track.get("id"),
                played_at_to_epoch_ms(played_at),
            ),
        )
        inserted += cur.rowcount

    conn.commit()
    conn.close()
    print(f"[{datetime.now().isoformat()}] fetched {len(items)} items, inserted {inserted} new rows")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print(f"[{datetime.now().isoformat()}] pull_history.py failed:", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
