"""Multi-user hosted web app: connect Spotify, discover listening contexts
in your own recent history, create a playlist from one of them.

Reuses session_detection.py, track_features.py, and context_detection.py's
methodology unchanged -- this file only adds the live-data path (Spotify
API instead of listening_history.db) and the web/session layer around it.
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from flask_session import Session
import spotipy
from spotipy.cache_handler import FlaskSessionCacheHandler
from spotipy.oauth2 import SpotifyOAuth

from context_detection import build_contexts, consolidate_by_category
from playlist_naming import generate_playlist_name
from spotify_playlist import create_playlist

REPO_DIR = Path(__file__).resolve().parent
load_dotenv(REPO_DIR / ".env")

SCOPE = "user-read-recently-played playlist-modify-private"

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


@app.route("/create-playlist", methods=["POST"])
def create_playlist_route():
    sp = get_spotify_client()
    if sp is None:
        return redirect(url_for("index"))

    context_id = request.form.get("context_id")
    if not context_id:
        return jsonify({"error": "missing 'context_id'"}), 400

    playlist_name = request.form.get("playlist_name")
    if not playlist_name:
        return jsonify({"error": "missing 'playlist_name'"}), 400

    plays = fetch_recent_plays(sp)
    contexts = consolidate_by_category(build_contexts(plays))

    match = next((c for c in contexts if c["context_id"] == context_id), None)
    if match is None:
        return jsonify({
            "error": "context not found -- your listening data may have "
                      "changed since you viewed it, try again"
        }), 404

    result = create_playlist(
        sp,
        match["playlist_track_ids"],
        playlist_name,
        description=match["category_description"],
    )
    return render_template("playlist_created.html", result=result)


if __name__ == "__main__":
    app.run(debug=True)
