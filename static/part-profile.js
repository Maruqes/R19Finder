(() => {
  'use strict';
  const form = document.querySelector('[data-part-form]');
  if (!form) return;
  const $ = selector => form.querySelector(selector);
  const initial = JSON.parse($('[data-part-profile]').dataset.profile);
  const fields = new Map([...form.querySelectorAll('[data-fact-field]')].map(el => [el.dataset.factField, el]));
  const state = {facts: initial.facts || [], rejected: initial.rejected || [], pending: [], handled: [], undo: [], draft: null, run: null, busy: false, dirty: false, editVersion: 0};
  const storageKey = 'part-draft:' + (form.dataset.requestId || 'new');
  const status = message => { $('[data-fill-status]').textContent = message; };
  const uid = () => {
    if (globalThis.crypto?.randomUUID) return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 15) | 64; bytes[8] = (bytes[8] & 63) | 128;
    const hex = [...bytes].map(x => x.toString(16).padStart(2, '0')).join('');
    return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
  };
  const store = value => { try { if (value) sessionStorage.setItem(storageKey, value); else sessionStorage.removeItem(storageKey); } catch (_) { /* Draft link also appears in the address bar. */ } };
  const node = (tag, text, className) => { const el = document.createElement(tag); if (text) el.textContent = text; if (className) el.className = className; return el; };
  const button = (text, fn) => { const el = node('button', text, 'btn btn-quiet'); el.type = 'button'; el.addEventListener('click', fn); return el; };
  const profile = () => ({schema_version: 1, facts: state.facts.filter(f => f.value.trim()), rejected: state.rejected.slice(-60)});
  const csrf = () => form.elements.csrf.value;
  const minimal = values => { const data = new FormData(); data.set('csrf', csrf()); for (const [key,value] of Object.entries(values)) data.set(key, value); return data; };
  async function api(path, data) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 45000);
    try {
      const response = await fetch(path, {method: data ? 'POST' : 'GET', body: data, signal: controller.signal, headers: {Accept: 'application/json'}});
      const body = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(body.error || `Request failed (${response.status}). Your form is still here.`);
      return body;
    } catch (error) {
      if (error instanceof TypeError || error.name === 'AbortError') throw new Error('Connection interrupted. Your form is still here. Retry explicitly or resume the saved draft.');
      throw error;
    } finally { clearTimeout(timer); }
  }
  function changed() { state.dirty = true; state.editVersion++; }
  function factFor(field, value = '') { return {id: uid(), field, value, origin: 'user', review_status: 'accepted', verification_status: 'unverified', evidence: [], reason: '', run_id: ''}; }
  function renderFact(fact, container, index) {
    const row = node('div', '', 'fact-row' + (fact.origin === 'ai' ? ' is-suggestion' : ''));
    row.dataset.factId = fact.id;
    const input = node(fact.field === 'quantity' ? 'input' : fact.field === 'buying_unit' ? 'select' : 'textarea');
    if (fact.field === 'quantity') { input.type = 'number'; input.min = '1'; input.max = '999'; input.step = '1'; }
    if (fact.field === 'buying_unit') for (const [value, label] of [['','Not specified'],['individual','Individual'],['pair','Pair'],['set','Set'],['unknown','Unknown']]) input.add(new Option(label, value));
    input.value = fact.value; input.name = 'part_' + fact.field;
    input.placeholder = ({references: 'E.g. OEM 001234 · maker · exact or possible reference', measurements: 'E.g. Width 240 mm · measured on the original', compatible_vehicles: 'Make, model, generation, years, engine and fitment restrictions', aliases: 'E.g. Feu arrière gauche (French)', mountings: 'E.g. Three mounting studs; connector with six pins'})[fact.field] || '';
    input.id = 'part-' + fact.field + (index ? '-' + index : ''); input.rows = fact.field === 'quantity' ? 1 : 2; input.maxLength = 1500;
    input.setAttribute('aria-label', fields.get(fact.field).dataset.label + (index ? ' ' + (index + 1) : ''));
    if (fact.field === 'quantity') input.inputMode = 'numeric';
    input.addEventListener('input', () => { fact.value = input.value; fact.verification_status = 'unverified'; fact.identifier = null; const identifierInfo = row.querySelector('[data-identifier-meta]'); if (identifierInfo) identifierInfo.remove(); const checkbox = row.querySelector('input[type=checkbox]'); if (checkbox) checkbox.checked = false; changed(); });
    row.append(input);
    if (fact.identifier) {
      const identifier = fact.identifier;
      const meta = node('div', '', 'identifier-details'); meta.dataset.identifierMeta = '';
      meta.append(node('p', `${identifier.kind.toUpperCase()} · ${identifier.code} · ${identifier.manufacturer || 'Maker unknown'} · ${identifier.match === 'supported' ? 'Source-supported candidate — review fitment' : 'Unverified candidate'}`));
      if (identifier.matched_attributes.length) meta.append(node('p', 'Matching attributes: ' + identifier.matched_attributes.join('; ')));
      if (identifier.unresolved_attributes.length) meta.append(node('p', 'Still to check: ' + identifier.unresolved_attributes.join('; ')));
      row.append(meta);
    }
    if (fact.language) row.append(node('span', ({en:'English',pt:'Português',fr:'Français',de:'Deutsch',es:'Español'})[fact.language], 'badge'));
    const actions = node('div', '', 'fact-actions');
    if (fact.origin === 'ai') {
      actions.append(node('span', fact.review_status === 'pending' ? 'Review AI suggestion' : 'AI suggestion · reviewed', 'badge'));
      if (fact.reason) row.append(node('p', fact.reason, 'help-text'));
      for (const source of fact.evidence || []) {
        const p = node('p', '', 'help-text');
        if (source.url && /^https?:\/\//i.test(source.url)) {
          const a = node('a', source.note || 'Source cited by AI', 'text-link'); a.href = source.url; a.target = '_blank'; a.rel = 'noopener noreferrer'; p.append(a);
        } else p.textContent = source.note;
        row.append(p);
      }
      if (fact.review_status === 'pending') actions.append(button('Accept as unverified', () => { fact.review_status = 'accepted'; changed(); render(); }));
      actions.append(button('Dismiss', () => { dismiss(fact); render(); }));
    } else if (fields.get(fact.field).dataset.multiple === 'true') {
      actions.append(button('Remove', () => { state.facts = state.facts.filter(f => f.id !== fact.id); changed(); render(); }));
    }
    if (fact.value.trim()) {
      const label = node('label', '', 'help-text'); const check = node('input'); check.type = 'checkbox'; check.checked = fact.verification_status === 'user_confirmed';
      check.addEventListener('change', () => { fact.verification_status = check.checked ? 'user_confirmed' : 'unverified'; if (check.checked) fact.review_status = 'accepted'; changed(); render(); });
      label.append(check, document.createTextNode('I have confirmed this fact')); actions.append(label);
    }
    row.append(actions); container.append(row);
  }
  function dismiss(fact) {
    state.facts = state.facts.filter(f => f.id !== fact.id); state.pending = state.pending.filter(f => f.id !== fact.id);
    state.rejected.push(fact.field + ': ' + fact.value); state.handled = [...new Set([...state.handled, fact.id])].slice(-200); changed();
  }
  function render() {
    for (const [field, el] of fields) {
      const rows = el.querySelector('[data-fact-rows]'); rows.replaceChildren();
      let facts = state.facts.filter(f => f.field === field);
      if (!facts.length) { const fact = factFor(field); state.facts.push(fact); facts = [fact]; }
      facts.forEach((fact, i) => renderFact(fact, rows, i));
      if (facts.some(f => f.review_status === 'pending')) el.closest('details').open = true;
    }
    const conflicts = $('[data-conflicts]'); conflicts.replaceChildren();
    for (const fact of state.pending) {
      const box = node('div', '', 'profile-conflict');
      box.append(node('h4', fields.get(fact.field)?.dataset.label || fact.field));
      box.append(node('p', 'Your value: ' + state.facts.filter(f => f.field === fact.field && f.value).map(f => f.value).join('; '), 'help-text'));
      box.append(node('p', 'AI suggests: ' + fact.value));
      box.append(node('p', fact.reason, 'help-text'));
      box.append(button('Keep mine', () => { dismiss(fact); render(); }));
      box.append(button('Use suggestion as unverified', () => {
        const current = state.facts.filter(f => f.field === fact.field);
        state.undo.push({id: fact.id, value: fact.value, previous: current});
        if (fields.get(fact.field).dataset.multiple !== 'true') state.facts = state.facts.filter(f => f.field !== fact.field);
        state.facts.push({...fact, review_status: 'accepted'}); state.pending = state.pending.filter(f => f.id !== fact.id); changed(); render();
      }));
      conflicts.append(box);
    }
    const pending = state.facts.filter(f => f.review_status === 'pending').length + state.pending.length;
    $('[data-review-panel]').hidden = !pending && !state.handled.length;
    $('[data-undo-fill]').hidden = !state.undo.length;
    $('[data-accept-all]').disabled = !state.facts.some(f => f.review_status === 'pending');
  }
  for (const [field, el] of fields) {
    const add = el.querySelector('[data-add-fact]');
    if (add) { add.hidden = false; add.addEventListener('click', () => { if (state.facts.filter(f => f.field === field).length >= 30) return status('Up to 30 values per field.'); state.facts.push(factFor(field)); changed(); render(); el.querySelector('[data-fact-rows]').lastElementChild.querySelector('textarea').focus(); }); }
  }
  function draftPhotos(draft) {
    const area = $('[data-draft-photos]'); area.replaceChildren();
    if (draft.photos.length) area.append(node('p', 'Saved draft photos', 'help-text'));
    for (const photo of draft.photos) {
      const label = node('label'); const image = node('img'); image.src = photo.url; image.alt = 'Saved part reference photo';
      const check = node('input'); check.type = 'checkbox'; check.name = 'remove_draft_photos'; check.value = photo.id;
      label.append(image, check, document.createTextNode('Remove')); area.append(label);
    }
    const oldPhotos = form.querySelector('fieldset'); if (oldPhotos) { oldPhotos.hidden = true; oldPhotos.querySelectorAll('input').forEach(input => { input.disabled = true; }); }
  }
  async function saveDraft() {
    if (!form.reportValidity()) throw new Error('Complete the required description first.');
    const version = state.editVersion;
    const selectedFiles = [...form.elements.photos.files];
    const data = new FormData(form);
    data.set('part_profile', JSON.stringify(profile()));
    data.set('review_state', JSON.stringify({pending: state.pending, handled: state.handled.slice(-200), undo: state.undo.slice(-60)}));
    data.set('request_id', form.dataset.requestId);
    if (state.draft) data.set('revision', state.draft.revision);
    const draft = await api(state.draft ? `/part-drafts/${state.draft.id}/update` : '/part-drafts', data);
    state.draft = draft; store(draft.id);
    const url = new URL(location.href); url.searchParams.set('draft', draft.id); history.replaceState(null, '', url);
    if ([...form.elements.photos.files].every((f, i) => f === selectedFiles[i]) && form.elements.photos.files.length === selectedFiles.length) form.elements.photos.value = '';
    form.elements.photos.dispatchEvent(new Event('change'));
    const previews = $('[data-previews]'); if (previews) previews.replaceChildren();
    draftPhotos(draft); state.dirty = version !== state.editVersion;
    // The server may invalidate AI facts after a vehicle change.
    const invalidated = draft.content.part_profile.facts.filter(f => f.review_status === 'pending');
    for (const fact of invalidated) { const local = state.facts.find(f => f.id === fact.id); if (local) Object.assign(local, fact); }
    render();
    if (state.dirty) throw new Error('Your edits made during saving are still in the form. Save again to include them.');
    return draft;
  }
  function busy(value) {
    state.busy = value;
    $('[data-fill]').disabled = value || !!state.run;
    $('[data-find-identifiers]').disabled = value || !!state.run;
    $('[data-save-draft]').disabled = value;
    form.querySelector('[type=submit]').disabled = value;
  }
  async function action(fn) { if (state.busy) return; busy(true); try { await fn(); } catch (error) { status(error.message); } finally { busy(false); } }
  function applyResult(run) {
    const original = run.input;
    const sameCar = (form.elements.car_id.value || '') === (original.car_id || '') && (form.elements.car_id.value || form.elements.vehicle.value.trim() === original.vehicle);
    if (!sameCar) { status('The vehicle changed during AI fill. These suggestions were not applied. Run AI again with the current vehicle.'); return; }
    if ((run.output.suggestions || []).some(f => !state.handled.includes(f.id))) state.undo = [];
    const merged = PartProfileMerge.merge(state.facts, original.part_profile.facts || [], run.output.suggestions || [],
      [...fields].filter(([,el]) => el.dataset.multiple === 'true').map(([key]) => key), state.handled);
    state.facts = merged.facts; state.pending.push(...merged.pending); state.undo.push(...merged.undo); state.handled = merged.handled;
    const notes = $('[data-ai-notes]'); notes.replaceChildren();
    for (const key of ['missing_information', 'conflicts', 'limitations']) {
      for (const text of run.output[key] || []) notes.append(node('p', text, 'help-text'));
    }
    changed(); render(); status('AI details applied. Review highlighted fields and resolve alternatives before saving.');
  }
  let progressSnapshot = null;
  function renderProgress() {
    if (!progressSnapshot || !state.run) return;
    const {data, received} = progressSnapshot;
    const extra = Math.max(0, Math.floor((Date.now() - received) / 1000));
    const duration = seconds => `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, '0')}s`;
    $('[data-fill-progress]').hidden = false;
    $('[data-fill-model]').textContent = `${data.provider === 'codex' ? 'Codex' : 'Open WebUI'} · ${data.model || 'Account default'}`;
    $('[data-fill-timing]').textContent = `Elapsed: ${duration(data.elapsed_seconds + extra)}` +
      (data.queue_position ? ` · Queue position: ${data.queue_position}` : ` · Processing: ${duration(data.running_seconds + extra)} · Limit: 5 minutes`);
    $('[data-fill-service]').textContent = `${data.worker_online ? 'AI service online' : 'AI service not responding'} · Last status check ${extra}s ago`;
  }
  const progressTimer = setInterval(renderProgress, 1000);
  window.addEventListener('pagehide', () => clearInterval(progressTimer), {once: true});
  let pollTimer;
  async function poll() {
    clearTimeout(pollTimer);
    if (!state.run || !state.draft) return;
    if (document.hidden || state.busy) { pollTimer = setTimeout(poll, 3000); return; }
    const runId = state.run;
    try {
      const result = await api(`/part-drafts/${state.draft.id}/enrichments/${runId}`);
      if (runId !== state.run) return;
      if (['queued', 'running'].includes(result.status)) {
        progressSnapshot = {data: result.progress, received: Date.now()};
        status(result.progress.message); renderProgress();
        pollTimer = setTimeout(poll, 3000); return;
      }
      state.run = null; $('[data-fill-progress]').hidden = true; progressSnapshot = null; $('[data-cancel-fill]').hidden = true; busy(false);
      if (result.status === 'completed') { applyResult(result); await action(async () => { await saveDraft(); }); }
      else status(result.error || 'AI fill cancelled. Your draft is safe.');
    } catch (error) { status(error.message + ' Checking again shortly.'); pollTimer = setTimeout(poll, 10000); }
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden && state.run) poll(); });
  const startFill = purpose => action(async () => {
    $('[data-ai-fill]').scrollIntoView({block:'start', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
    if (state.pending.length || state.facts.some(f => f.review_status === 'pending')) throw new Error('Review the previous suggestions before starting another AI fill.');
    status('Saving draft…'); await saveDraft();
    const data = minimal({revision: state.draft.revision, idempotency_key: uid(), model: $('#part-model').value, reasoning_effort: $('#part-effort').value, purpose, include_photos: $('#part-send-photos').checked ? 'on' : ''});
    const run = await api(`/part-drafts/${state.draft.id}/enrichments`, data); state.run = run.id; state.undo = [];
    $('[data-cancel-fill]').hidden = false; status('Request saved. Checking the AI queue…'); pollTimer = setTimeout(poll, 1500);
  });
  $('[data-fill]').addEventListener('click', () => startFill('profile'));
  $('[data-find-identifiers]').hidden = false;
  $('[data-find-identifiers]').addEventListener('click', () => startFill('identifiers'));
  $('[data-cancel-fill]').addEventListener('click', () => action(async () => {
    if (!state.run) return;
    const result = await api(`/part-drafts/${state.draft.id}/enrichments/${state.run}/cancel`, minimal({}));
    state.run = null; $('[data-fill-progress]').hidden = true; progressSnapshot = null; clearTimeout(pollTimer); $('[data-cancel-fill]').hidden = true; status(result.message);
  }));
  $('[data-save-draft]').addEventListener('click', () => action(async () => { await saveDraft(); status('Draft saved for seven days in this browser session.'); }));
  $('[data-accept-all]').addEventListener('click', () => { state.facts.forEach(f => { if (f.review_status === 'pending') f.review_status = 'accepted'; }); changed(); render(); });
  $('[data-undo-fill]').addEventListener('click', () => {
    state.facts = PartProfileMerge.undoFill(state.facts, state.undo);
    state.pending = []; state.undo = []; changed(); render(); status('AI changes undone. Your later edits have been preserved.');
  });
  $('#part-model').addEventListener('change', () => {
    const effort = $('#part-effort'); effort.replaceChildren(new Option('Model default', ''));
    const values = JSON.parse($('#part-model').selectedOptions[0].dataset.efforts || '[]');
    for (const value of values) effort.add(new Option(value, value)); effort.disabled = !values.length;
  });
  form.addEventListener('input', changed);
  form.elements.car_id.addEventListener('change', () => {
    for (const fact of state.facts) if (fact.origin === 'ai') { fact.review_status = 'pending'; fact.verification_status = 'unverified'; }
    changed(); render();
  });
  form.addEventListener('submit', event => {
    event.preventDefault();
    action(async () => {
      if (state.run) throw new Error('Wait for AI to finish or cancel AI fill before saving.');
      if (state.pending.length || state.facts.some(f => f.review_status === 'pending')) { $('[data-review-panel]').hidden = false; $('[data-review-panel]').scrollIntoView({block: 'center'}); throw new Error('Review highlighted suggestions and alternatives before saving.'); }
      await saveDraft();
      const result = await api(`/part-drafts/${state.draft.id}/commit`, minimal({revision: state.draft.revision}));
      state.dirty = false; store(null); location.assign(result.url);
    });
  });
  window.addEventListener('beforeunload', event => { if (state.dirty) { event.preventDefault(); event.returnValue = ''; } });
  async function resume(id) {
    const draft = await api('/part-drafts/' + id);
    if (draft.saved_url) { state.dirty = false; store(null); location.assign(draft.saved_url); return; }
    if (draft.request_id !== form.dataset.requestId) throw new Error('This draft belongs to a different part. Open it from its original form.');
    state.draft = draft;
    form.elements.description.value = draft.content.description; form.elements.vehicle.value = draft.content.vehicle; form.elements.car_id.value = draft.content.car_id;
    state.facts = draft.content.part_profile.facts || []; state.rejected = draft.content.part_profile.rejected || [];
    Object.assign(state, {pending: [], handled: [], undo: []}, draft.content.review_state || {});
    state.dirty = false; draftPhotos(draft); render(); $('[data-resume-draft]').hidden = true; status('Draft restored.');
    store(id);
    if (draft.run?.provider) {
      const selection = draft.run.provider + ':' + draft.run.model;
      if ([...$('#part-model').options].some(option => option.value === selection)) $('#part-model').value = selection;
      $('#part-model').dispatchEvent(new Event('change')); $('#part-effort').value = draft.run.reasoning_effort || '';
    }
    if (draft.run) {
      state.run = draft.run.id; $('[data-cancel-fill]').hidden = !['queued', 'running'].includes(draft.run.status); pollTimer = setTimeout(poll, 500);
    }
    const manual = $('[data-manual-vehicle]'); if (manual) manual.hidden = Boolean(form.elements.car_id.value);
    state.dirty = false;
  }
  let saved;
  try { saved = new URL(location.href).searchParams.get('draft') || sessionStorage.getItem(storageKey); } catch (_) { /* storage unavailable */ }
  if (saved && /^[a-f0-9-]{36}$/i.test(saved)) {
    $('[data-resume-draft]').hidden = false;
    $('[data-resume]').addEventListener('click', () => action(() => resume(saved)));
    $('[data-discard-resume]').addEventListener('click', () => { store(null); $('[data-resume-draft]').hidden = true; const url = new URL(location.href); url.searchParams.delete('draft'); history.replaceState(null, '', url); });
  }
  $('[data-ai-fill]').hidden = false;
  render();
  $('#part-model').dispatchEvent(new Event('change'));
})();
