// Small enhancements; every form and navigation link still works without JavaScript.
document.addEventListener('click', (event) => {
  const dismiss = event.target.closest('[data-dismiss-notice]');
  if (dismiss) dismiss.closest('[role=status]').remove();
});

const formAlert = document.querySelector('[role=alert][tabindex="-1"]');
if (formAlert) formAlert.focus();

const carProfile = document.getElementById('car_id');
const manualVehicle = document.querySelector('[data-manual-vehicle]');
if (carProfile && manualVehicle) {
  const updateVehicle = () => { manualVehicle.hidden = Boolean(carProfile.value); };
  carProfile.addEventListener('change', updateVehicle);
  window.addEventListener('pageshow', updateVehicle);
  updateVehicle();
}

for (const input of document.querySelectorAll('[data-photo-preview]')) {
  const area = input.closest('.upload-area');
  const previews = area.querySelector('[data-previews]');
  const status = area.querySelector('[data-upload-summary]');
  let objectURLs = [];
  input.addEventListener('change', () => {
    objectURLs.forEach((url) => URL.revokeObjectURL(url));
    objectURLs = [];
    previews.replaceChildren();
    const files = [...input.files];
    const size = files.reduce((total, file) => total + file.size, 0) / (1024 * 1024);
    status.textContent = files.length ? `${files.length} photo${files.length === 1 ? '' : 's'} selected · ${size.toFixed(1)} MB${files.length > 8 ? ' · Previewing the first 8' : ''}` : '';
    files.slice(0, 8).filter((file) => file.type.startsWith('image/')).forEach((file) => {
      const img = document.createElement('img');
      img.alt = `Preview: ${file.name}`;
      img.src = URL.createObjectURL(file);
      objectURLs.push(img.src);
      previews.append(img);
    });
  });
  window.addEventListener('pagehide', (event) => {
    if (!event.persisted) objectURLs.forEach((url) => URL.revokeObjectURL(url));
  });
}

for (const form of document.querySelectorAll('[data-submit-state]')) {
  form.addEventListener('submit', () => {
    // Wait for the browser to collect submitter values before disabling controls.
    window.setTimeout(() => {
      form.setAttribute('aria-busy', 'true');
      for (const button of form.querySelectorAll('button[type=submit]:not(:disabled)')) {
        button.dataset.originalLabel = button.innerHTML;
        button.disabled = true;
        button.textContent = 'Please wait…';
      }
    }, 0);
  });
}
window.addEventListener('pageshow', () => {
  for (const button of document.querySelectorAll('[data-original-label]')) {
    button.innerHTML = button.dataset.originalLabel;
    button.disabled = false;
    delete button.dataset.originalLabel;
    button.closest('form').removeAttribute('aria-busy');
  }
});

// Visible errors are friendlier than the browser trying to focus a collapsed field.
document.addEventListener('invalid', (event) => {
  let parent = event.target.parentElement;
  while (parent) {
    if (parent.tagName === 'DETAILS') parent.open = true;
    parent = parent.parentElement;
  }
}, true);

// Small local filters keep the garage useful as the collection grows.
const garageFilter = document.querySelector('[data-garage-filter]');
if (garageFilter) {
  const cards = [...document.querySelectorAll('[data-garage-grid] [data-car-name]')];
  const normalize = (value) => value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  garageFilter.addEventListener('input', () => {
    const query = normalize(garageFilter.value.trim());
    let visible = 0;
    for (const card of cards) {
      card.hidden = !normalize(card.dataset.carName).includes(query);
      if (!card.hidden) visible++;
    }
    document.querySelector('[data-garage-count]').textContent = query
      ? `${visible} of ${cards.length} cars`
      : `${cards.length} car${cards.length === 1 ? '' : 's'} in your garage`;
    document.querySelector('[data-garage-empty]').hidden = visible > 0;
  });
}

for (const field of document.querySelectorAll('[data-character-count]')) {
  const count = document.querySelector(`[data-count-for="${field.id}"]`);
  if (!count) continue;
  const update = () => { count.textContent = `${field.value.length.toLocaleString()} / ${field.maxLength.toLocaleString()}`; };
  field.addEventListener('input', update);
  update();
}

// Native file selection remains available alongside drag and drop.
for (const input of document.querySelectorAll('[data-photo-preview]')) {
  const area = input.closest('.upload-area');
  const status = area.querySelector('[data-upload-summary]');
  const clear = document.createElement('button');
  clear.type = 'button';
  clear.className = 'text-link';
  clear.textContent = 'Clear selected photos';
  clear.hidden = true;
  area.append(clear);
  const validate = () => {
    const files = [...input.files];
    const totalBytes = files.reduce((sum, file) => sum + file.size, 0);
    const existing = input.form.querySelectorAll('[name=remove_photos]:not(:checked)').length;
    let error = '';
    if (input.dataset.maxFiles && files.length + existing > Number(input.dataset.maxFiles)) {
      error = `This request supports ${input.dataset.maxFiles} photos in total. Remove existing photos or choose fewer files.`;
    } else if (input.dataset.maxSize && files.some((file) => file.size > Number(input.dataset.maxSize) * 1024 * 1024)) {
      error = `Each photo must be ${input.dataset.maxSize} MB or smaller.`;
    } else if (totalBytes >= 32 * 1024 * 1024) {
      error = 'These photos exceed the 32 MB upload limit. Choose fewer or smaller files.';
    } else if (files.some((file) => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) && !/\.(jpe?g|png|webp)$/i.test(file.name))) {
      error = 'Choose JPG, PNG or WebP photos.';
    }
    input.setCustomValidity(error);
    input.setAttribute('aria-invalid', String(Boolean(error)));
    if (error) status.textContent = error;
    else status.textContent = files.length ? `${files.length} photo${files.length === 1 ? '' : 's'} selected · ${(totalBytes / (1024 * 1024)).toFixed(1)} MB${files.length > 8 ? ' · Previewing the first 8' : ''}` : '';
    clear.hidden = files.length === 0;
  };
  clear.addEventListener('click', () => {
    input.value = '';
    input.dispatchEvent(new Event('change', { bubbles: true }));
    input.focus();
  });
  input.addEventListener('change', validate);
  input.form.querySelectorAll('[name=remove_photos]').forEach((checkbox) => checkbox.addEventListener('change', validate));
  let dragDepth = 0;
  area.addEventListener('dragenter', (event) => {
    event.preventDefault();
    dragDepth++;
    area.classList.add('is-dragging');
  });
  area.addEventListener('dragover', (event) => event.preventDefault());
  area.addEventListener('dragleave', () => {
    dragDepth--;
    if (dragDepth <= 0) area.classList.remove('is-dragging');
  });
  area.addEventListener('drop', (event) => {
    event.preventDefault();
    dragDepth = 0;
    area.classList.remove('is-dragging');
    if (event.dataTransfer.files.length) {
      input.files = event.dataTransfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  });
}

// Keep request navigation in sync with the selected section and browser history.
const sectionLinks = [...document.querySelectorAll('.subnav a[href^="#"]')];
if (sectionLinks.length) {
  const updateSection = () => {
    const target = sectionLinks.some((link) => link.hash === location.hash) ? location.hash : '#parts-found';
    for (const link of sectionLinks) {
      const active = link.hash === target;
      link.classList.toggle('is-active', active);
      if (active) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    }
  };
  window.addEventListener('hashchange', updateSection);
  updateSection();
}

// Each saved schedule has its own switch; the Save button is the no-JS fallback.
for (const form of document.querySelectorAll('[data-toggle-submit]')) {
  form.querySelector('[data-toggle-save]').hidden = true;
  form.addEventListener('change', (event) => {
    if (event.target.matches('input[role=switch]')) form.requestSubmit();
  });
}
