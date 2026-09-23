/* Track Record Web Playback SDK bootstrap.

   Stage 1 proved the browser can register as a real Spotify Connect
   device ("TRACK RECORD") using the *existing* OAuth session's access
   token (served by GET /spotify-token, which reuses get_spotify_client()
   server-side -- no new auth system, no token hardcoded here). Stage 2
   proved it could start one hardcoded test track. Stage 3 added real
   playback of whatever playlist this page is for.

   2026-09-24: the visible TRACK RECORD PLAYER widget (status text +
   PREV/PLAY/NEXT buttons) was removed -- play control now lives on
   each track's own album art (see .playlist-card__track-art-btn in
   playlist_detail.html). This file still does the same SDK connection
   and playback-start work, just without a status UI to update; the
   playlist URI is read off the hidden #player-context element instead
   of the old #player-status widget.
*/

(function () {
  const contextEl = document.getElementById('player-context');
  if (!contextEl) return;

  const playlistUri = contextEl.dataset.playlistUri || null;

  // Per-track play control on each track's album art. Clicking a
  // track's photo starts the SAME playlist context at that track's
  // position, so Spotify's own single-device playback model does the
  // "stop the previous one" part for free; this file only needs to
  // track which row is currently the active one and toggle its icon.
  const trackEls = Array.from(document.querySelectorAll('.playlist-card__track'));
  const trackArtButtons = Array.from(document.querySelectorAll('.playlist-card__track-art-btn'));

  // Only the row matching the SDK's actual current_track.uri AND
  // actively playing (not paused) shows the pause icon -- every other
  // row, including a paused current track, shows play. Matches by URI
  // (not by the index we may have last clicked) so PREV/NEXT (via the
  // SDK's own gesture support, e.g. a connected Spotify Connect
  // remote) and a track click both keep the right row highlighted.
  function updatePlayingTrackHighlight(state) {
    const track = state && state.track_window && state.track_window.current_track;
    const activeUri = track ? track.uri : null;
    const isPlaying = !!(state && !state.paused);
    trackEls.forEach((li) => {
      const isActive = isPlaying && !!activeUri && li.dataset.trackUri === activeUri;
      li.dataset.playing = isActive ? 'true' : 'false';
    });
  }

  function fetchAccessToken() {
    return fetch('/spotify-token', { credentials: 'same-origin' }).then((res) => {
      if (!res.ok) throw new Error('not authenticated');
      return res.json();
    }).then((data) => data.access_token);
  }

  // Starting playback of a specific playlist (optionally at a given
  // track position) on a specific device is a Web API call (PUT
  // /me/player/play), not an SDK method -- the SDK's own
  // player.togglePlay() only controls playback already active on this
  // device.
  function startPlaylistPlayback(offsetPosition) {
    if (!window.trackRecordPlayer || !window.trackRecordPlayer.deviceId) {
      console.warn('Track click ignored -- player not ready yet.');
      return;
    }
    if (!playlistUri) {
      console.error('No playlist URI on this page -- nothing to play.');
      return;
    }
    const deviceId = window.trackRecordPlayer.deviceId;
    const body = { context_uri: playlistUri };
    if (typeof offsetPosition === 'number') {
      body.offset = { position: offsetPosition };
    }

    fetchAccessToken()
      .then((token) => fetch(
        `https://api.spotify.com/v1/me/player/play?device_id=${encodeURIComponent(deviceId)}`,
        {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(body),
        },
      ))
      .then((res) => {
        if (!res.ok && res.status !== 204) {
          return res.json().catch(() => ({})).then((resBody) => {
            throw new Error(`play request failed: ${res.status} ${resBody && resBody.error ? resBody.error.message : ''}`);
          });
        }
        // player_state_changed is the authoritative source for the
        // per-track playing/paused icon once Spotify's servers
        // actually start the playlist -- this just confirms the
        // request was accepted.
      })
      .catch((err) => {
        console.error('Start playlist playback failed:', err);
      });
  }

  window.onSpotifyWebPlaybackSDKReady = () => {
    const player = new Spotify.Player({
      name: 'TRACK RECORD',
      getOAuthToken: (callback) => {
        fetchAccessToken()
          .then(callback)
          .catch((err) => console.error('Spotify OAuth token fetch failed:', err));
      },
      volume: 0.5,
    });

    window.trackRecordPlayer = { player: player, deviceId: null, connected: false };

    player.addListener('ready', ({ device_id }) => {
      window.trackRecordPlayer.deviceId = device_id;
      window.trackRecordPlayer.connected = true;
    });

    player.addListener('not_ready', ({ device_id }) => {
      window.trackRecordPlayer.deviceId = device_id;
      window.trackRecordPlayer.connected = false;
    });

    player.addListener('initialization_error', ({ message }) => {
      console.error('Spotify Player initialization_error:', message);
    });

    player.addListener('authentication_error', ({ message }) => {
      console.error('Spotify Player authentication_error:', message);
    });

    player.addListener('account_error', ({ message }) => {
      // Fires for a non-Premium account -- Web Playback SDK playback
      // requires Premium.
      console.error('Spotify Player account_error (Premium required?):', message);
    });

    player.addListener('playback_error', ({ message }) => {
      console.error('Spotify Player playback_error:', message);
    });

    player.addListener('player_state_changed', (state) => {
      window.trackRecordPlayer.lastState = state;
      updatePlayingTrackHighlight(state);
    });

    player.addListener('autoplay_failed', () => {
      console.warn('Spotify Player autoplay_failed');
    });

    trackArtButtons.forEach((btn) => {
      btn.addEventListener('click', () => {
        if (!window.trackRecordPlayer.deviceId) {
          console.warn('Track click ignored -- player not ready yet.');
          return;
        }
        const li = btn.closest('.playlist-card__track');
        const uri = li && li.dataset.trackUri;
        const state = window.trackRecordPlayer.lastState;
        const current = state && state.track_window && state.track_window.current_track;
        const isThisTrackActive = !!(current && uri && current.uri === uri && !state.paused);

        if (isThisTrackActive) {
          // Clicking the photo of the track that's already playing
          // pauses it.
          player.togglePlay().catch((err) => console.error('togglePlay failed:', err));
        } else {
          // Starts this same playlist context at this track's
          // position -- Spotify's single-device playback model stops
          // whatever was playing before automatically.
          startPlaylistPlayback(Number(btn.dataset.trackIndex));
        }
      });
    });

    fetchAccessToken()
      .then(() => player.connect())
      .catch((err) => console.error('Spotify Player connect failed:', err));
  };

  // If the SDK script itself never loads (network block/ad blocker),
  // onSpotifyWebPlaybackSDKReady never fires -- log it instead of
  // failing silently forever.
  window.setTimeout(() => {
    if (!window.Spotify) {
      console.error('Spotify Web Playback SDK failed to load.');
    }
  }, 8000);
})();
