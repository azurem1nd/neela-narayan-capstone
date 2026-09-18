"""Multi-user hosted web app: connect Spotify, discover memory categories in
your own recent listening, create a playlist from one of them.

Reuses session_detection.py and track_features.py's classification logic
unchanged -- this file only adds the live-data path (Spotify API instead
of listening_history.db) and the web/session layer around it.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, request, session, url_for
from flask_session import Session
import spotipy
from spotipy.cache_handler import FlaskSessionCacheHandler
from spotipy.oauth2 import SpotifyOAuth

from session_detection import detect_sessions
from track_features import classify_track, extract_track_features
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


def fetch_recent_plays(sp) -> list[dict]:
    """Fetch the current user's recently played tracks, normalized and sorted."""
    results = sp.current_user_recently_played(limit=50)
    plays = []
    for item in results["items"]:
        track = item["track"]
        artist_name = ", ".join(a["name"] for a in track.get("artists", [])) or "Unknown"
        plays.append({
            "played_at": item["played_at"],
            "track_id": track.get("id"),
            "track_name": track["name"],
            "artist_name": artist_name,
        })
    plays.sort(key=lambda p: p["played_at"])
    return plays


def classify_recent_plays(plays: list[dict]) -> tuple[list[dict], list[dict]]:
    """Group live plays by track and session, classify each track. No DB involved."""
    by_track: dict[str, list[dict]] = {}
    for p in plays:
        if p["track_id"] is None:
            continue
        by_track.setdefault(p["track_id"], []).append(p)

    classified = []
    for track_id, track_plays in by_track.items():
        features = extract_track_features(track_plays)
        features["track_id"] = track_id
        features["track_name"] = track_plays[0]["track_name"]
        features["artist_name"] = track_plays[0]["artist_name"]
        features["classification"] = classify_track(features)
        classified.append(features)

    session_tuples = [
        (p["played_at"], p["track_id"], p["artist_name"])
        for p in plays
        if p["track_id"] is not None
    ]
    sessions = detect_sessions(session_tuples)

    return classified, sessions


@app.route("/")
def index():
    return jsonify({
        "status": "ok",
        "logged_in": get_spotify_client() is not None,
        "login_url": url_for("login"),
    })


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
    return redirect(url_for("analyze"))


@app.route("/analyze")
def analyze():
    sp = get_spotify_client()
    if sp is None:
        return jsonify({"error": "not authenticated", "login_url": url_for("login")}), 401

    me = sp.current_user()
    plays = fetch_recent_plays(sp)
    classified, sessions = classify_recent_plays(plays)

    by_category: dict[str, list[dict]] = {}
    for f in classified:
        by_category.setdefault(f["classification"], []).append(f)

    return jsonify({
        "connected_as": {"id": me["id"], "display_name": me.get("display_name")},
        "play_count": len(plays),
        "session_count": len(sessions),
        "categories": by_category,
    })


@app.route("/create-playlist", methods=["POST"])
def create_playlist_route():
    sp = get_spotify_client()
    if sp is None:
        return jsonify({"error": "not authenticated", "login_url": url_for("login")}), 401

    category = (request.get_json(silent=True) or {}).get("category") or request.args.get("category")
    if not category:
        return jsonify({"error": "missing 'category'"}), 400

    plays = fetch_recent_plays(sp)
    classified, _ = classify_recent_plays(plays)

    track_ids = [f["track_id"] for f in classified if f["classification"] == category]
    if not track_ids:
        return jsonify({"error": f"no tracks currently classified as '{category}'"}), 404

    result = create_playlist(sp, track_ids, f"{category} — from your recent listening")
    return jsonify(result)


if __name__ == "__main__":
    app.run(debug=True)
