import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyOAuth, CacheFileHandler
import google.generativeai as genai

EXPERIMENT_DIR = Path(__file__).resolve().parent
REPO_DIR = EXPERIMENT_DIR.parent.parent
load_dotenv(REPO_DIR / ".env")

CACHE_PATH = EXPERIMENT_DIR / ".cache_experiment"
SCOPE = "user-top-read playlist-modify-private"


def get_spotify_client():
    cache_handler = CacheFileHandler(cache_path=str(CACHE_PATH))
    auth_manager = SpotifyOAuth(scope=SCOPE, cache_handler=cache_handler, show_dialog=True)
    return spotipy.Spotify(auth_manager=auth_manager)


def get_top_tracks(limit: int = 20) -> list[dict]:
    """Return the user's top tracks on Spotify, most-listened first.

    Args:
        limit: number of top tracks to return.
    """
    sp = get_spotify_client()
    results = sp.current_user_top_tracks(limit=int(limit))
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "artist": ", ".join(a["name"] for a in t["artists"]),
        }
        for t in results["items"]
    ]


def create_playlist(track_ids: list[str], name: str) -> dict:
    """Create a private Spotify playlist and add the given tracks to it.

    Args:
        track_ids: Spotify track IDs to add to the new playlist.
        name: name for the new playlist.
    """
    sp = get_spotify_client()
    playlist = sp.current_user_playlist_create(name, public=False)
    sp.playlist_add_items(playlist["id"], track_ids)
    return {
        "playlist_id": playlist["id"],
        "playlist_url": playlist["external_urls"]["spotify"],
        "name": name,
        "track_count": len(track_ids),
    }


AVAILABLE_FUNCTIONS = {
    "get_top_tracks": get_top_tracks,
    "create_playlist": create_playlist,
}


def run_agent(prompt: str):
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(
        model_name="gemini-3.6-flash",
        tools=[get_top_tracks, create_playlist],
    )
    chat = model.start_chat(enable_automatic_function_calling=False)

    print(f"[prompt] {prompt}\n")
    response = chat.send_message(prompt)

    while True:
        function_calls = [
            part.function_call
            for part in response.candidates[0].content.parts
            if part.function_call
        ]
        if not function_calls:
            break

        function_responses = []
        for call in function_calls:
            fn = AVAILABLE_FUNCTIONS[call.name]
            args = dict(call.args)
            print(f"[gemini decided to call] {call.name}({args})")
            result = fn(**args)
            print(f"[executed locally, result] {result}\n")
            function_responses.append(
                genai.protos.Part(
                    function_response=genai.protos.FunctionResponse(
                        name=call.name,
                        response={"result": result},
                    )
                )
            )
        response = chat.send_message(genai.protos.Content(parts=function_responses))

    print(f"[gemini final response] {response.text}")


if __name__ == "__main__":
    track_count = 20
    playlist_name = f"Top {track_count} Current - {datetime.now().strftime('%d/%m/%y')}"
    run_agent(
        f"Get my top {track_count} tracks on Spotify, then create a new private playlist "
        f"named exactly '{playlist_name}' containing those tracks."
    )
