import spotipy
from spotipy.oauth2 import SpotifyOAuth

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope="user-read-recently-played"))

results = sp.current_user_recently_played(limit=10)
for item in results["items"]:
    print(item["played_at"], "-", item["track"]["name"])