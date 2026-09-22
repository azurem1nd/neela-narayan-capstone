/* Track Record landing page -- toggles between the subtitle link
   ("connect to spotify" / "your music library") and the About
   paragraph when the TRACK RECORD wordmark is clicked. Both are
   states of the same landing system, not separate pages. */

(function () {
  const toggle = document.getElementById('wordmark-toggle');
  const subtitle = document.getElementById('subtitle-panel');
  const about = document.getElementById('about-panel');
  if (!toggle || !subtitle || !about) return;

  toggle.addEventListener('click', () => {
    const showingAbout = !about.hidden;
    about.hidden = showingAbout;
    subtitle.hidden = !showingAbout;
    toggle.setAttribute('aria-expanded', String(!showingAbout));
  });
})();
