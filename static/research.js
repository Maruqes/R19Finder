const providerSelect = document.getElementById('model');
const codexSelect = document.getElementById('codex_model');
const effortSelect = document.getElementById('reasoning_effort');

// Capture also handles images added by automatic history refreshes.
document.addEventListener('error', (event) => {
  if (event.target.matches?.('.listing-photo img')) event.target.hidden = true;
}, true);

function updateCodexSelector() {
  const isCodex = providerSelect.value === 'codex';
  codexSelect.parentElement.hidden = !isCodex;
  codexSelect.disabled = !isCodex;
  const previous = effortSelect.value;
  const levels = JSON.parse(codexSelect.selectedOptions[0].dataset.efforts || '[]');
  effortSelect.replaceChildren(new Option('Model default', ''));
  for (const level of levels) {
    effortSelect.add(new Option(level.charAt(0).toUpperCase() + level.slice(1), level));
  }
  effortSelect.value = levels.includes(previous) ? previous : '';
  effortSelect.disabled = !isCodex || !levels.length;
}

providerSelect.addEventListener('change', updateCodexSelector);
codexSelect.addEventListener('change', updateCodexSelector);
window.addEventListener('pageshow', updateCodexSelector);
updateCodexSelector();

let historySection = document.getElementById('search-history');
const updateStatus = document.getElementById('history-update-status');
let retryDelay = 4000;

async function refreshHistory() {
  if (document.hidden) {
    setTimeout(refreshHistory, 4000);
    return;
  }
  try {
    const response = await fetch(window.location.pathname, {
      cache: 'no-store', signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error('Unable to refresh');
    const page = new DOMParser().parseFromString(await response.text(), 'text/html');
    const next = page.getElementById('search-history');
    if (!next) throw new Error('Invalid response');
    const parts = document.getElementById('parts-found');
    const nextParts = page.getElementById('parts-found');
    // Do not close an open removal/restore control or discard a typed reason.
    if (parts && nextParts && !parts.querySelector('details[open] form') && parts.innerHTML !== nextParts.innerHTML) {
      const scroll = parts.querySelector('.parts-track')?.scrollLeft || 0;
      parts.replaceWith(nextParts);
      const track = nextParts.querySelector('.parts-track');
      if (track) track.scrollLeft = scroll;
    }
    // Keep expanded snapshots and never replace the user's search form.
    for (const article of historySection.querySelectorAll('[data-search-id]')) {
      const replacement = next.querySelector(`[data-search-id="${article.dataset.searchId}"]`);
      if (article.querySelector('details[open]') && replacement) {
        replacement.querySelector('details').open = true;
      }
    }
    if (next.innerHTML !== historySection.innerHTML) {
      historySection.replaceWith(next);
      historySection = next;
    }
    historySection.dataset.active = next.dataset.active;
    const active = next.dataset.active === 'true';
    const start = document.getElementById('start-search');
    start.disabled = active;
    start.textContent = active ? 'Search in progress' : 'Search for this part';
    updateStatus.textContent = active ? 'Updating automatically…' : 'Search history is up to date.';
    retryDelay = active ? 4000 : 15000;
  } catch {
    updateStatus.textContent = 'Unable to refresh. Retrying automatically; you can also use Refresh status.';
    retryDelay = Math.min(retryDelay * 2, 30000);
  }
  setTimeout(refreshHistory, retryDelay);
}

if (historySection.dataset.active === 'true') {
  updateStatus.textContent = 'Updating automatically…';
}
setTimeout(refreshHistory, retryDelay);
