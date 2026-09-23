/* Track Record Web Playback SDK bootstrap -- Stage 1 only.

   Goal: get this browser tab registered as a real Spotify Connect
   device ("TRACK RECORD") using the *existing* OAuth session's access
   token (served by GET /spotify-token, which reuses get_spotify_client()
   server-side -- no new auth system, no token hardcoded here). Reports
   connection status via the #player-status widget. No play/pause/track
   controls yet -- that's Stage 2.
*/

(function () {
  const statusEl = document.getElementById('player-status');
  const valueEl = document.getElementById('player-status-value');
  if (!statusEl || !valueEl) return;

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

  window.onSpotifyWebPlaybackSDKReady = () => {
    const player = new Spotify.Player({
      name: 'TRACK RECORD',
      getOAuthToken: (callback) => {
        fetchAccessToken()
          .then(callback)
          .catch(() => setStatus('error', 'ERROR -- could not refresh Spotify token'));
      },
      volume: 0.5,
    });

    // Exposed for Stage 2 (play/pause/track controls) to build on --
    // this stage only ever reads/sets deviceId and connected here.
    window.trackRecordPlayer = { player: player, deviceId: null, connected: false };

    player.addListener('ready', ({ device_id }) => {
      window.trackRecordPlayer.deviceId = device_id;
      window.trackRecordPlayer.connected = true;
      setStatus('connected', 'CONNECTED');
    });

    player.addListener('not_ready', ({ device_id }) => {
      window.trackRecordPlayer.deviceId = device_id;
      window.trackRecordPlayer.connected = false;
      setStatus('connecting', 'CONNECTING...');
    });

    player.addListener('initialization_error', ({ message }) => {
      console.error('Spotify Player initialization_error:', message);
      setStatus('error', 'ERROR -- player failed to initialize');
    });

    player.addListener('authentication_error', ({ message }) => {
      console.error('Spotify Player authentication_error:', message);
      setStatus('error', 'ERROR -- Spotify authentication failed');
    });

    player.addListener('account_error', ({ message }) => {
      console.error('Spotify Player account_error:', message);
      setStatus('error', 'ERROR -- Spotify Premium is required for playback');
    });

    player.addListener('playback_error', ({ message }) => {
      console.error('Spotify Player playback_error:', message);
    });

    player.addListener('player_state_changed', (state) => {
      window.trackRecordPlayer.lastState = state;
    });

    player.addListener('autoplay_failed', () => {
      console.warn('Spotify Player autoplay_failed');
    });

    fetchAccessToken()
      .then(() => player.connect())
      .catch(() => setStatus('error', 'ERROR -- not connected to Spotify'));
  };

  // If the SDK script itself never loads (network block/ad blocker),
  // onSpotifyWebPlaybackSDKReady never fires -- fail visibly instead
  // of leaving a silent, permanent "CONNECTING..." state.
  window.setTimeout(() => {
    if (!window.Spotify) {
      setStatus('error', 'ERROR -- Spotify SDK failed to load');
    }
  }, 8000);
})();
