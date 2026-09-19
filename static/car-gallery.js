document.querySelectorAll('[data-car-gallery]').forEach((gallery) => {
  const slides = [...gallery.querySelectorAll('.car-gallery-slide')];
  if (slides.length < 2) return;
  const dots = [...gallery.querySelectorAll('[data-slide]')];
  const controls = gallery.querySelector('[data-gallery-controls]');
  const pause = gallery.querySelector('[data-pause]');
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  let current = 0;
  let paused = true;
  function show(index) {
    current = (index + slides.length) % slides.length;
    slides.forEach((slide, i) => { slide.hidden = i !== current; });
    dots.forEach((dot, i) => dot.setAttribute('aria-pressed', String(i === current)));
  }
  function updatePause() {
    pause.textContent = paused ? 'Play slideshow' : 'Pause slideshow';
  }
  function choose(index) { paused = true; updatePause(); show(index); }
  gallery.querySelector('[data-previous]').addEventListener('click', () => choose(current - 1));
  gallery.querySelector('[data-next]').addEventListener('click', () => choose(current + 1));
  dots.forEach((dot, i) => dot.addEventListener('click', () => choose(i)));
  pause.addEventListener('click', () => { paused = !paused; updatePause(); });
  reducedMotion.addEventListener('change', () => { if (reducedMotion.matches) { paused = true; updatePause(); } });
  controls.hidden = false;
  updatePause();
  setInterval(() => {
    if (!paused && !document.hidden && !gallery.matches(':hover, :focus-within')) show(current + 1);
  }, 5000);
});
