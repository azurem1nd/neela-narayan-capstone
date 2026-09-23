"""Multi-user hosted web app: connect Spotify, discover listening contexts
in your own recent history, create a playlist from one of them.

Reuses session_detection.py, track_features.py, and context_detection.py's
methodology unchanged -- this file only adds the live-data path (Spotify
API instead of listening_history.db) and the web/session layer around it.
"""

import os
import traceback
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
import spotipy
from spotipy.cache_handler import FlaskSessionCacheHandler
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

from context_detection import build_contexts, consolidate_by_category
from playlist_naming import generate_playlist_name, parse_playlist_name
from spotify_playlist import create_playlist

REPO_DIR = Path(__file__).resolve().parent
load_dotenv(REPO_DIR / ".env")

SCOPE = "user-read-recently-played playlist-modify-private streaming"

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ["FLASK_SECRET_KEY"]
app.config["SESSION_TYPE"] = "filesystem"
Session(app)


def get_spotify_oauth():
    return SpotifyOAuth(
        client_id=os.environ["SPOTIPY_CLIENT_ID"],
        client_secret=os.environ["SPOTIPY_CLIENT_SECRET"],
        redirect_uri=os.environ["SPOTIPY_REDIRECT_URI"],
        scope=SCOPE,
        cache_handler=FlaskSessionCacheHandler(session),
    )


def get_spotify_client():
    """Return an authenticated spotipy client for the current session, or None."""
    auth_manager = get_spotify_oauth()
    token_info = auth_manager.validate_token(auth_manager.cache_handler.get_cached_token())
    if not token_info:
        return None
    return spotipy.Spotify(auth_manager=auth_manager)


def fetch_recent_plays(sp, max_plays: int = 300) -> list[dict]:
    """Fetch the current user's recently played tracks, normalized and sorted.

    Paginates past Spotify's 50-item-per-call cap via the `before` cursor,
    up to max_plays -- a single page rarely contains enough repetition for
    Trigger/Companion/Spiral/Locked to fire and fragments into too many
    tiny sessions. Stops early and gracefully if the account has less
    history than max_plays (empty items or no further cursor) -- never
    assumes max_plays is always reachable.
    """
    plays = []
    before = None
    while len(plays) < max_plays:
        results = sp.current_user_recently_played(limit=50, before=before)
        items = results["items"]
        if not items:
            break
        for item in items:
            track = item.get("track")
            if track is None:
                # Spotify can return a null track for e.g. local files played
                # through a client -- skip rather than crash.
                continue
            artist_name = ", ".join(a["name"] for a in track.get("artists", [])) or "Unknown"
            plays.append({
                "played_at": item["played_at"],
                "track_id": track.get("id"),
                "track_name": track["name"],
                "artist_name": artist_name,
            })
        cursors = results.get("cursors")
        if not cursors or not cursors.get("before"):
            break  # no more history available
        before = cursors["before"]
    plays.sort(key=lambda p: p["played_at"])
    return plays


@app.route("/")
def index():
    sp = get_spotify_client()
    if sp is None:
        return render_template("index.html", logged_in=False)

    me = sp.current_user()
    return render_template("index.html", logged_in=True, display_name=me.get("display_name") or me["id"])


@app.route("/login")
def login():
    return redirect(get_spotify_oauth().get_authorize_url())


@app.route("/callback")
def callback():
    if "error" in request.args:
        return jsonify({"error": request.args["error"]}), 400

    code = request.args.get("code")
    if not code:
        return jsonify({"error": "missing 'code' in callback"}), 400

    auth_manager = get_spotify_oauth()
    auth_manager.get_access_token(code)
    session.permanent = True
    return redirect(url_for("index"))


@app.route("/analyze")
def analyze():
    sp = get_spotify_client()
    if sp is None:
        return redirect(url_for("index"))

    me = sp.current_user()
    plays = fetch_recent_plays(sp)
    raw_contexts = build_contexts(plays)
    contexts = consolidate_by_category(raw_contexts)

    now = datetime.now(timezone.utc)
    for context in contexts:
        context["playlist_name"] = generate_playlist_name(context["label"], now)

    return render_template(
        "contexts.html",
        display_name=me.get("display_name") or me["id"],
        contexts=contexts,
        total_plays=len(plays),
        first_played=plays[0]["played_at"] if plays else None,
        last_played=plays[-1]["played_at"] if plays else None,
        session_count=len(raw_contexts),
        today_display=now.strftime("%d %b %Y"),
    )


@app.route("/playlist/<playlist_id>")
def playlist_detail(playlist_id):
    """Dedicated page for one specific, already-created Spotify playlist.

    Reached only after /create-playlist has actually succeeded (see the
    library card's click handler in library.js) -- this route never
    creates anything itself. Re-fetches the playlist directly from
    Spotify by id rather than keeping any local copy: Spotify's own
    object already has the exact name/description this app set at
    creation time (nothing to duplicate or pass through a redirect),
    and its own access-control means a different user's session simply
    can't fetch a playlist they don't own (playlists here are always
    created public=False -- see spotify_playlist.py).
    """
    sp = get_spotify_client()
    if sp is None:
        return redirect(url_for("index"))

    try:
        playlist = sp.playlist(playlist_id)
    except SpotifyException:
        # Not found, not this user's, or Spotify hiccuped -- there is no
        # broken playlist page to show, just go back to a live library.
        return redirect(url_for("analyze"))

    name_parts = parse_playlist_name(playlist["name"])
    images = playlist.get("images") or []
    tracks = []
    for item in playlist["tracks"]["items"]:
        track = item.get("track")
        if track is None:
            continue
        tracks.append({
            "name": track.get("name"),
            "artist": ", ".join(a["name"] for a in track.get("artists", [])) or "Unknown",
        })

    return render_template(
        "playlist_detail.html",
        playlist={
            "id": playlist["id"],
            "name": playlist["name"],
            "category": name_parts["category"],
            "date": name_parts["date"],
            "description": playlist.get("description") or "",
            "track_count": playlist["tracks"]["total"],
            "image_url": images[0]["url"] if images else None,
            "url": playlist["external_urls"]["spotify"],
            "tracks": tracks,
        },
    )


@app.route("/spotify-token")
def spotify_token():
    """Give the frontend a valid access token for the Web Playback SDK.

    Reuses get_spotify_client() outright -- same auth_manager, same
    session-backed cache_handler, same automatic refresh-if-expired and
    invalid-if-scope-insufficient behavior (spotipy.SpotifyOAuth.validate_token
    returns None if the cached token's scope no longer covers what's
    currently configured, e.g. right after adding `streaming` to SCOPE
    -- so a stale pre-streaming session correctly falls through to 401
    here too, the same as every other route already falling through to
    a login redirect). Never touches the client secret; the token
    returned is always scoped to the current request's own session.
    """
    sp = get_spotify_client()
    if sp is None:
        return jsonify({"error": "not authenticated"}), 401
    token_info = sp.auth_manager.cache_handler.get_cached_token()
    return jsonify({"access_token": token_info["access_token"]})


@app.route("/create-playlist", methods=["POST"])
def create_playlist_route():
    """Create a real Spotify playlist from one library card, called via
    fetch() from library.js's card click handler -- JSON in, JSON out.

    Re-fetches and re-derives contexts fresh, same as /playlist/<id>'s
    caller relies on and as documented in context-detection/SKILL.md
    Known Limitation #3 -- this app has no persistence, so "the exact
    qualifying track IDs already calculated for that context" are
    recomputed from the user's current listening history rather than
    trusted from the client, then used completely unfiltered/unedited
    (match["playlist_track_ids"]) for the tracks actually sent to
    Spotify. The playlist name is generated fresh here via the same
    generate_playlist_name() every other route uses -- not supplied by
    the client -- so it's always byte-for-byte the real, current name.
    """
    sp = get_spotify_client()
    if sp is None:
        return jsonify({"error": "not authenticated"}), 401

    data = request.get_json(silent=True) or {}
    context_id = data.get("context_id")
    if not context_id:
        return jsonify({"error": "missing 'context_id'"}), 400

    try:
        plays = fetch_recent_plays(sp)
        contexts = consolidate_by_category(build_contexts(plays))

        match = next((c for c in contexts if c["context_id"] == context_id), None)
        if match is None:
            return jsonify({
                "error": "context not found -- your listening data may have "
                          "changed since you viewed it, try again"
            }), 404

        now = datetime.now(timezone.utc)
        playlist_name = generate_playlist_name(match["label"], now)

        result = create_playlist(
            sp,
            match["playlist_track_ids"],
            playlist_name,
            description=match["category_description"],
        )
        return jsonify(result)
    except Exception as exc:
        # TEMPORARY, for diagnosing a live 500 -- a bare 500 with no
        # body gives no way to tell which of the steps above actually
        # failed. Prints the real traceback server-side (never a
        # token/secret -- this route never handles either directly)
        # and echoes back just the exception's type/message, so the
        # cause is visible from the Network tab too without needing
        # terminal access. Remove once diagnosed.
        traceback.print_exc()
        return jsonify({
            "error": "playlist creation failed",
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
        }), 500


if __name__ == "__main__":
    app.run(debug=True)
