/* Track Record Web Playback SDK bootstrap -- Stage 2.

   Stage 1 proved the browser can register as a real Spotify Connect
   device ("TRACK RECORD") using the *existing* OAuth session's access
   token (served by GET /spotify-token, which reuses get_spotify_client()
   server-side -- no new auth system, no token hardcoded here).

   Stage 2 adds exactly one thing on top of that: a temporary "PLAY
   TEST TRACK" button that starts real playback of one known track on
   this real device, via the Spotify Web API's /me/player/play
   endpoint (not the SDK itself -- the SDK only owns local playback
   state once Spotify's servers tell this device to play something).
   Still no playlist playback, no pause/skip, no second player.
*/

(function () {
  const statusEl = document.getElementById('player-status');
  const valueEl = document.getElementById('player-status-value');
  const testBtn = document.getElementById('player-test-btn');
  if (!statusEl || !valueEl) return;

  // "Cut To The Feeling" by Carly Rae Jepsen -- the same track Spotify's
  // own Web Playback SDK quickstart guide uses as its example URI.
  const TEST_TRACK_URI = 'spotify:track:11dFghVXANMlKmJXsNCbNl';

  function setStatus(state, message) {
    statusEl.dataset.state = state;
    valueEl.textContent = message;
  }

  function fetchAccessToken() {
    return fetch('/spotify-token', { credentials: 'same-origin' }).then((res) => {
      if (!res.ok) throw new Error('not authenticated');
      return res.json();
    }).then((data) => data.access_token);
  }

  function playTestTrack() {
    if (!window.trackRecordPlayer || !window.trackRecordPlayer.deviceId) {
      setStatus('not-ready', 'Not ready');
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
          body: JSON.stringify({ uris: [TEST_TRACK_URI] }),
        },
      ))
      .then((res) => {
        if (!res.ok && res.status !== 204) {
          return res.json().catch(() => ({})).then((body) => {
            throw new Error(`play request failed: ${res.status} ${body && body.error ? body.error.message : ''}`);
          });
        }
        // player_state_changed (below) is the authoritative source for
        // "Playing" once Spotify's servers actually start the track;
        // this just confirms the request itself was accepted.
      })
      .catch((err) => {
        console.error('PLAY TEST TRACK failed:', err);
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

    // Exposed for Stage 3 (playlist playback, transfer, etc.) to
    // build on -- this stage only ever reads/sets deviceId here.
    window.trackRecordPlayer = { player: player, deviceId: null, connected: false };

    player.addListener('ready', ({ device_id }) => {
      window.trackRecordPlayer.deviceId = device_id;
      window.trackRecordPlayer.connected = true;
      setStatus('ready', 'Player ready');
      if (testBtn) testBtn.disabled = false;
    });

    player.addListener('not_ready', ({ device_id }) => {
      window.trackRecordPlayer.deviceId = device_id;
      window.trackRecordPlayer.connected = false;
      setStatus('not-ready', 'Not ready');
      if (testBtn) testBtn.disabled = true;
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
      if (state && !state.paused) {
        setStatus('playing', 'Playing');
      }
    });

    player.addListener('autoplay_failed', () => {
      console.warn('Spotify Player autoplay_failed');
    });

    if (testBtn) testBtn.addEventListener('click', playTestTrack);

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
