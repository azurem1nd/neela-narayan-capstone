/* Track Record library page -- view mode (single / grid) toggle and
   single-card navigation. Pure client-side presentation state layered
   on top of the cards the server already rendered from the current
   user's own contexts -- no data fetching, no page reload. */

(function () {
  const stage = document.getElementById('lib-stage');
  if (!stage) return;

  const cards = Array.from(document.querySelectorAll('.lib-card-wrapper'));
  const prevBtn = document.getElementById('lib-prev');
  const nextBtn = document.getElementById('lib-next');
  const positionLabel = document.getElementById('lib-position');
  const categoryLabel = document.getElementById('lib-position-label');
  const viewButtons = Array.from(document.querySelectorAll('[data-view-btn]'));

  let currentIndex = 0;

  function applyVisibility() {
    const view = stage.dataset.view;
    cards.forEach((card, i) => {
      const visible = view === 'multi' || i === currentIndex;
      card.hidden = !visible;
    });
    if (positionLabel) {
      positionLabel.textContent = `${currentIndex + 1} / ${cards.length}`;
    }
    if (categoryLabel && cards[currentIndex]) {
      categoryLabel.textContent = cards[currentIndex].dataset.category;
    }
    if (prevBtn) prevBtn.disabled = currentIndex === 0;
    if (nextBtn) nextBtn.disabled = currentIndex === cards.length - 1;
  }

  function setView(view) {
    stage.dataset.view = view;
    viewButtons.forEach((btn) => {
      btn.classList.toggle('is-active', btn.dataset.viewBtn === view);
    });
    // currentIndex is deliberately left untouched here -- switching
    // modes never resets which card single-view was showing.
    applyVisibility();
  }

  function goTo(index) {
    currentIndex = Math.max(0, Math.min(cards.length - 1, index));
    applyVisibility();
  }

  viewButtons.forEach((btn) => {
    btn.addEventListener('click', () => setView(btn.dataset.viewBtn));
  });

  if (prevBtn) prevBtn.addEventListener('click', () => goTo(currentIndex - 1));
  if (nextBtn) nextBtn.addEventListener('click', () => goTo(currentIndex + 1));

  document.addEventListener('keydown', (e) => {
    if (stage.dataset.view !== 'single') return;
    if (e.key === 'ArrowRight') goTo(currentIndex + 1);
    if (e.key === 'ArrowLeft') goTo(currentIndex - 1);
  });

  applyVisibility();
})();

/* Card click -> resolve_context_playlist() (reuse/update/create,
   see playlist_persistence.py) -> navigate to its detail page. Reuses
   the existing /create-playlist route (now JSON) and the exact
   qualifying-track/name/description it already computes server-side
   -- nothing about the tracks, naming, or reuse-vs-create decision is
   made here, this is purely the click/loading/error UI around that
   call. */
(function () {
  const cardFrames = Array.from(document.querySelectorAll('.ctx-card-frame'));
  if (cardFrames.length === 0) return;

  // One shared flag, not per-card: while a resolve is in flight, every
  // card is inert -- avoids two racing at once.
  let creating = false;

  // sessionStorage (not a JS variable) so this survives a full page
  // reload from clicking browser back to the library and clicking the
  // same card again in the same window/tab, while staying scoped to
  // this one tab (new tab/window starts fresh) and never persisting
  // across different users on a shared machine the way localStorage
  // would. This is purely a label hint for the loading overlay -- the
  // backend (playlist_persistence.py) is the actual source of truth
  // for whether a playlist already exists; this can't get "wrong" in
  // a way that breaks anything, only in a way that shows the less
  // accurate of two harmless loading labels for one click.
  const RESOLVED_KEY = 'trackrecord:resolvedContexts';

  function hasResolvedBefore(contextId) {
    try {
      const raw = window.sessionStorage.getItem(RESOLVED_KEY);
      return !!raw && JSON.parse(raw).includes(contextId);
    } catch (err) {
      return false;
    }
  }

  function markResolved(contextId) {
    try {
      const raw = window.sessionStorage.getItem(RESOLVED_KEY);
      const ids = raw ? JSON.parse(raw) : [];
      if (!ids.includes(contextId)) {
        ids.push(contextId);
        window.sessionStorage.setItem(RESOLVED_KEY, JSON.stringify(ids));
      }
    } catch (err) {
      // Private-browsing/storage-blocked -- loading label just won't
      // say "opening" on a later visit; not worth failing the click.
    }
  }

  function loadingLabel(contextId) {
    return hasResolvedBefore(contextId) ? 'Opening your playlist...' : 'Creating playlist...';
  }

  function setLoading(frame, isLoading, text) {
    const overlay = frame.querySelector('.ctx-card-loading');
    if (!overlay) return;
    if (text) overlay.textContent = text;
    overlay.hidden = !isLoading;
  }

  cardFrames.forEach((frame) => {
    frame.addEventListener('click', () => {
      if (creating) return;
      const contextId = frame.dataset.contextId;
      if (!contextId) return;

      creating = true;
      setLoading(frame, true, loadingLabel(contextId));

      fetch('/create-playlist', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ context_id: contextId }),
      })
        .then((res) => res.json().then((data) => ({ ok: res.ok, status: res.status, data: data })))
        .then(({ ok, status, data }) => {
          if (!ok || !data.playlist_id) {
            // TEMPORARY, for diagnosing a live 500 -- surfaces the
            // backend's exception_type/exception_message (see app.py's
            // /create-playlist) in the console, not just "failed".
            const detail = data && data.exception_type
              ? ` [${status}] ${data.exception_type}: ${data.exception_message}`
              : ` [${status}] ${(data && data.error) || 'no error detail returned'}`;
            throw new Error('playlist creation failed --' + detail);
          }
          markResolved(contextId);
          // Navigating away -- deliberately leave creating=true and the
          // loading overlay showing, there is nothing left to reset.
          window.location.href = '/playlist/' + data.playlist_id;
        })
        .catch((err) => {
          console.error('Create playlist failed:', err);
          creating = false;
          setLoading(frame, true, "Couldn't create playlist -- try again");
          window.setTimeout(() => setLoading(frame, false), 2500);
        });
    });
  });
})();
