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
