/* Track Record Web Playback SDK bootstrap -- Stage 3.

   Stage 1 proved the browser can register as a real Spotify Connect
   device ("TRACK RECORD") using the *existing* OAuth session's access
   token (served by GET /spotify-token, which reuses get_spotify_client()
   server-side -- no new auth system, no token hardcoded here). Stage 2
   proved it could start one hardcoded test track.

   Stage 3 replaces that test button with real playback of whatever
   playlist this specific page is for (its Spotify URI is read off the
   #player-status element's data-playlist-uri, set server-side from the
   playlist /playlist/<id> just fetched from Spotify -- never invented
   here). Same single Spotify.Player instance and same device_id as
   before; only the "what to play" and the transport controls are new.
*/

(function () {
  const statusEl = document.getElementById('player-status');
  const valueEl = document.getElementById('player-status-value');
  const nowPlayingEl = document.getElementById('player-now-playing');
  const playBtn = document.getElementById('player-play-btn');
  const prevBtn = document.getElementById('player-prev-btn');
  const nextBtn = document.getElementById('player-next-btn');
  if (!statusEl || !valueEl) return;

  const playlistUri = statusEl.dataset.playlistUri || null;

  function setStatus(state, message) {
    statusEl.dataset.state = state;
    valueEl.textContent = message;
  }

  function setControlsEnabled(enabled) {
    [playBtn, prevBtn, nextBtn].forEach((btn) => {
      if (btn) btn.disabled = !enabled;
    });
  }

  function updateNowPlaying(state) {
    if (!nowPlayingEl) return;
    const track = state && state.track_window && state.track_window.current_track;
    if (!track) {
      nowPlayingEl.textContent = '';
      return;
    }
    const artists = (track.artists || []).map((a) => a.name).join(', ');
    nowPlayingEl.textContent = 'Now playing: ' + track.name + (artists ? ' — ' + artists : '');
  }

  function fetchAccessToken() {
    return fetch('/spotify-token', { credentials: 'same-origin' }).then((res) => {
      if (!res.ok) throw new Error('not authenticated');
      return res.json();
    }).then((data) => data.access_token);
  }

  // Starting playback of a specific playlist on a specific device is a
  // Web API call (PUT /me/player/play), not an SDK method -- the SDK's
  // own player.togglePlay()/nextTrack()/previousTrack() only control
  // playback that's already active on this device.
  function startPlaylistPlayback() {
    if (!window.trackRecordPlayer || !window.trackRecordPlayer.deviceId) {
      setStatus('not-ready', 'Not ready');
      return;
    }
    if (!playlistUri) {
      console.error('No playlist URI on this page -- nothing to play.');
      setStatus('error', 'Playback error');
      return;
    }
    const deviceId = window.trackRecordPlayer.deviceId;

    fetchAccessToken()
      .then((token) => fetch(
        `https://api.spotify.com/v1/me/player/play?device_id=${encodeURIComponent(deviceId)}`,
        {
          method: 'PUT',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ context_uri: playlistUri }),
        },
      ))
      .then((res) => {
        if (!res.ok && res.status !== 204) {
          return res.json().catch(() => ({})).then((body) => {
            throw new Error(`play request failed: ${res.status} ${body && body.error ? body.error.message : ''}`);
          });
        }
        // player_state_changed is the authoritative source for
        // "Playing" once Spotify's servers actually start the
        // playlist -- this just confirms the request was accepted.
      })
      .catch((err) => {
        console.error('Start playlist playback failed:', err);
        setStatus('error', 'Playback error');
      });
  }

  window.onSpotifyWebPlaybackSDKReady = () => {
    const player = new Spotify.Player({
      name: 'TRACK RECORD',
      getOAuthToken: (callback) => {
        fetchAccessToken()
          .then(callback)
          .catch(() => setStatus('error', 'Playback error'));
      },
      volume: 0.5,
    });

    // Exposed for later stages (queue, more controls) to build on.
    window.trackRecordPlayer = { player: player, deviceId: null, connected: false };

    player.addListener('ready', ({ device_id }) => {
      window.trackRecordPlayer.deviceId = device_id;
      window.trackRecordPlayer.connected = true;
      setStatus('ready', 'Player ready');
      if (playBtn) playBtn.disabled = false;
      // prev/next stay disabled until playback actually starts and a
      // real track_window exists to move within.
    });

    player.addListener('not_ready', ({ device_id }) => {
      window.trackRecordPlayer.deviceId = device_id;
      window.trackRecordPlayer.connected = false;
      setStatus('not-ready', 'Not ready');
      setControlsEnabled(false);
    });

    player.addListener('initialization_error', ({ message }) => {
      console.error('Spotify Player initialization_error:', message);
      setStatus('error', 'Playback error');
    });

    player.addListener('authentication_error', ({ message }) => {
      console.error('Spotify Player authentication_error:', message);
      setStatus('error', 'Playback error');
    });

    player.addListener('account_error', ({ message }) => {
      // Fires for a non-Premium account -- Web Playback SDK playback
      // requires Premium. Logged distinctly so the real cause is
      // findable in devtools even though the widget text is generic.
      console.error('Spotify Player account_error (Premium required?):', message);
      setStatus('error', 'Playback error');
    });

    player.addListener('playback_error', ({ message }) => {
      console.error('Spotify Player playback_error:', message);
      setStatus('error', 'Playback error');
    });

    player.addListener('player_state_changed', (state) => {
      window.trackRecordPlayer.lastState = state;
      updateNowPlaying(state);

      if (!state) {
        // No active session on this device (yet) -- leave whatever
        // ready/not-ready status is already showing alone.
        return;
      }

      setStatus(state.paused ? 'ready' : 'playing', state.paused ? 'Player ready' : 'Playing');
      if (playBtn) playBtn.textContent = state.paused ? 'PLAY' : 'PAUSE';
      if (prevBtn) prevBtn.disabled = false;
      if (nextBtn) nextBtn.disabled = false;
    });

    player.addListener('autoplay_failed', () => {
      console.warn('Spotify Player autoplay_failed');
    });

    if (playBtn) {
      playBtn.addEventListener('click', () => {
        if (!window.trackRecordPlayer.lastState) {
          // Nothing loaded on this device yet -- start this playlist.
          startPlaylistPlayback();
        } else {
          player.togglePlay().catch((err) => console.error('togglePlay failed:', err));
        }
      });
    }
    if (prevBtn) {
      prevBtn.addEventListener('click', () => {
        player.previousTrack().catch((err) => console.error('previousTrack failed:', err));
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        player.nextTrack().catch((err) => console.error('nextTrack failed:', err));
      });
    }

    fetchAccessToken()
      .then(() => player.connect())
      .catch(() => setStatus('error', 'Playback error'));
  };

  // If the SDK script itself never loads (network block/ad blocker),
  // onSpotifyWebPlaybackSDKReady never fires -- fail visibly instead
  // of leaving a silent, permanent "Connecting..." state.
  window.setTimeout(() => {
    if (!window.Spotify) {
      setStatus('error', 'Playback error');
    }
  }, 8000);
})();
