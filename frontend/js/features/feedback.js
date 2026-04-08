// Feedback — feedback modal with category selection and optional html2canvas screenshot.
// Reads: t (i18n.js), showToast (core), _fetch (api.js).
// Provides: openFeedbackModal.

// ---------------------------------------------------------------------------
// Module state
// ---------------------------------------------------------------------------

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

// ---------------------------------------------------------------------------
// Modal
// ---------------------------------------------------------------------------

/** Opens the feedback modal with category select, textarea, and optional screenshot capture. */
function openFeedbackModal() {
  document.getElementById('feedback-modal')?.remove();

  // Category select
  const catSelect = _el('select', { id: 'feedback-category', className: 'form-input' });
  [['general', t('feedback.category_general')], ['bug', t('feedback.category_bug')], ['vorschlag', t('feedback.category_suggestion')]].forEach(([val, txt]) => {
    const opt = _el('option', { value: val, textContent: txt });
    catSelect.appendChild(opt);
  });

  // Textarea
  const textarea = _el('textarea', {
    id: 'feedback-text',
    className: 'form-input',
    rows: '5',
    placeholder: t('feedback.textarea_placeholder'),
  });

  // Screenshot button
  const screenshotBtn = _el('button', {
    type: 'button',
    className: 'btn btn-secondary feedback-screenshot-btn',
    textContent: ' ' + t('feedback.screenshot_btn'),
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
    textContent: t('feedback.cancel'),
    onclick: () => closeFeedbackModal(),
  });
  const submitBtn = _el('button', {
    className: 'btn btn-primary',
    id: 'feedback-submit-btn',
    textContent: t('feedback.submit'),
    onclick: () => _submitFeedback(),
  });

  // Assemble modal content
  const content = _el('div', { className: 'modal-content feedback-modal-content' }, [
    _el('h3', { textContent: t('feedback.modal_title') }),
    _el('p', { textContent: t('feedback.modal_description') }),
    _el('div', { className: 'form-group' }, [
      _el('label', { textContent: t('feedback.category_label') }),
      catSelect,
    ]),
    _el('div', { className: 'form-group' }, [
      _el('label', { textContent: t('feedback.feedback_label') }),
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
    showToast(t('feedback.screenshot_lib_error'), 'warning');
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
    showToast(t('feedback.screenshot_failed'), 'warning');
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
    alt: t('feedback.screenshot_preview_alt'),
  });
  const removeLink = _el('span', {
    className: 'feedback-screenshot-remove',
    textContent: t('form.via_point_remove_aria'),
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
    showToast(t('feedback.textarea_placeholder'), 'warning');
    return;
  }

  const btn = document.getElementById('feedback-submit-btn');
  if (btn) {
    btn.disabled = true;
    btn.textContent = t('feedback.submit') + '\u2026';
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
      btn.textContent = t('feedback.submit');
    }
    const msg = err.message || 'Unbekannter Fehler';
    showToast('Feedback konnte nicht gesendet werden: ' + msg, 'warning');
  }
}
