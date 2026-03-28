// ---------------------------------------------------------------------------
//  Feedback Modal  (frontend/js/feedback.js)
// ---------------------------------------------------------------------------
/* global _fetch, showToast, API */

let _feedbackScreenshot = null; // base64 string (no data: prefix)

function _el(tag, attrs, children) {
  const el = document.createElement(tag);
  if (attrs) Object.entries(attrs).forEach(([k, v]) => {
    if (k === 'textContent') el.textContent = v;
    else if (k === 'className') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  });
  if (children) children.forEach(c => { if (c) el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); });
  return el;
}

function openFeedbackModal() {
  document.getElementById('feedback-modal')?.remove();

  // Category select
  const catSelect = _el('select', { id: 'feedback-category', className: 'form-input' });
  [['general', 'Allgemein'], ['bug', 'Bug melden'], ['vorschlag', 'Vorschlag']].forEach(([val, txt]) => {
    const opt = _el('option', { value: val, textContent: txt });
    catSelect.appendChild(opt);
  });

  // Textarea
  const textarea = _el('textarea', {
    id: 'feedback-text',
    className: 'form-input',
    rows: '5',
    placeholder: 'Was m\u00f6chtest du uns mitteilen? (mind. 10 Zeichen)',
  });

  // Screenshot button
  const screenshotBtn = _el('button', {
    type: 'button',
    className: 'btn btn-secondary feedback-screenshot-btn',
    textContent: ' Screenshot aufnehmen',
    onclick: () => _captureFeedbackScreenshot(),
  });
  const camIcon = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  camIcon.setAttribute('viewBox', '0 0 24 24');
  camIcon.setAttribute('fill', 'none');
  camIcon.setAttribute('stroke', 'currentColor');
  camIcon.setAttribute('stroke-width', '2');
  camIcon.setAttribute('width', '16');
  camIcon.setAttribute('height', '16');
  camIcon.style.cssText = 'vertical-align:-3px;margin-right:4px';
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('x', '3'); rect.setAttribute('y', '3');
  rect.setAttribute('width', '18'); rect.setAttribute('height', '18'); rect.setAttribute('rx', '2');
  const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
  circle.setAttribute('cx', '12'); circle.setAttribute('cy', '13'); circle.setAttribute('r', '3');
  camIcon.appendChild(rect);
  camIcon.appendChild(circle);
  screenshotBtn.prepend(camIcon);

  const previewDiv = _el('div', { id: 'feedback-screenshot-preview' });

  // Action buttons
  const cancelBtn = _el('button', {
    className: 'btn btn-secondary',
    textContent: 'Abbrechen',
    onclick: () => closeFeedbackModal(),
  });
  const submitBtn = _el('button', {
    className: 'btn btn-primary',
    id: 'feedback-submit-btn',
    textContent: 'Absenden',
    onclick: () => _submitFeedback(),
  });

  // Assemble modal content
  const content = _el('div', { className: 'modal-content feedback-modal-content' }, [
    _el('h3', { textContent: 'Feedback senden' }),
    _el('p', { textContent: 'Hilf uns, DetourAI zu verbessern! Beschreibe dein Anliegen oder deinen Vorschlag.' }),
    _el('div', { className: 'form-group' }, [
      _el('label', { textContent: 'Kategorie' }),
      catSelect,
    ]),
    _el('div', { className: 'form-group' }, [
      _el('label', { textContent: 'Dein Feedback' }),
      textarea,
    ]),
    _el('div', { className: 'form-group' }, [
      screenshotBtn,
      previewDiv,
    ]),
    _el('div', { className: 'modal-actions' }, [cancelBtn, submitBtn]),
  ]);

  // Modal backdrop
  const modal = _el('div', { id: 'feedback-modal', className: 'modal-backdrop' });
  modal.addEventListener('click', (e) => { if (e.target === modal) closeFeedbackModal(); });
  modal.appendChild(content);

  document.body.appendChild(modal);
  setTimeout(() => textarea.focus(), 100);
}

function closeFeedbackModal() {
  const modal = document.getElementById('feedback-modal');
  if (modal) modal.remove();
  _feedbackScreenshot = null;
}

async function _captureFeedbackScreenshot() {
  if (typeof html2canvas === 'undefined') {
    showToast('Screenshot-Bibliothek nicht geladen.', 'warning');
    return;
  }

  const modal = document.getElementById('feedback-modal');
  if (modal) modal.style.display = 'none';

  try {
    const canvas = await html2canvas(document.body, {
      scale: 0.5,
      useCORS: true,
      logging: false,
    });

    const dataUrl = canvas.toDataURL('image/png');
    _feedbackScreenshot = dataUrl.replace('data:image/png;base64,', '');

    if (modal) modal.style.display = '';
    _renderScreenshotPreview();
  } catch (err) {
    if (modal) modal.style.display = '';
    showToast('Screenshot fehlgeschlagen.', 'warning');
    console.error('Screenshot capture error:', err);
  }
}

function _renderScreenshotPreview() {
  const container = document.getElementById('feedback-screenshot-preview');
  if (!container) return;

  container.replaceChildren();

  if (!_feedbackScreenshot) return;

  const img = _el('img', {
    src: 'data:image/png;base64,' + _feedbackScreenshot,
    alt: 'Screenshot-Vorschau',
  });
  const removeLink = _el('span', {
    className: 'feedback-screenshot-remove',
    textContent: 'Entfernen',
    onclick: () => _removeFeedbackScreenshot(),
  });
  const row = _el('div', { className: 'feedback-preview-row' }, [img, removeLink]);
  container.appendChild(row);
}

function _removeFeedbackScreenshot() {
  _feedbackScreenshot = null;
  _renderScreenshotPreview();
}

async function _submitFeedback() {
  const text = (document.getElementById('feedback-text')?.value || '').trim();
  const category = document.getElementById('feedback-category')?.value || 'general';

  if (text.length < 10) {
    showToast('Bitte mindestens 10 Zeichen eingeben.', 'warning');
    return;
  }

  const btn = document.getElementById('feedback-submit-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = 'Wird gesendet\u2026';
  }

  try {
    const resp = await _fetch(`${API}/feedback`, {
      method: 'POST',
      body: JSON.stringify({
        text,
        category,
        screenshot: _feedbackScreenshot || null,
      }),
    }, 'Feedback wird gesendet\u2026');

    await resp.json();
    closeFeedbackModal();
    showToast('Danke f\u00fcr dein Feedback!', 'info');
  } catch (err) {
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Absenden';
    }
    const msg = err.message || 'Unbekannter Fehler';
    showToast('Feedback konnte nicht gesendet werden: ' + msg, 'warning');
  }
}
