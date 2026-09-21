(function () {
  const { fieldDefinitions, getCase, mismatch, unresolved, selectCase } = window.ShippingStore;
  const item = getCase(); selectCase(item.id);
  const requested = new URLSearchParams(location.search).get('field');
  const key = fieldDefinitions.some(([field]) => field === requested) ? requested : fieldDefinitions.find(([field]) => mismatch(item.values?.[field]))?.[0] || 'shipper';
  const label = fieldDefinitions.find(([field]) => field === key)[1];
  const pair = item.values?.[key];
  document.getElementById('backToComparison').href = `comparison.html?case=${encodeURIComponent(item.id)}`;
  document.getElementById('fieldTabs').innerHTML = fieldDefinitions.map(([field,name]) => `<a class="${field === key ? 'active' : ''}" href="evidence.html?case=${encodeURIComponent(item.id)}&field=${field}">${name}</a>`).join('');
  if (!pair) {
    document.getElementById('evidenceContent').innerHTML = '<div class="empty">Source evidence is unavailable for this field.</div>'; return;
  }
  const card = (source, index) => `<article class="proof-card"><div class="proof-meta"><span class="doc-type">${index === 0 ? 'Shipping instruction' : 'Draft bill of lading'}</span><h2>${escapeHTML(source.file_path || 'No document identified')}</h2><p>Page ${escapeHTML(source.page_number ?? 'unavailable')} · Value: ${escapeHTML(source.raw ?? 'Unavailable')}${source.corrected ? ' (human correction)' : ''}</p></div><div class="source-quote">${escapeHTML(source.source_text || 'Source text unavailable')}</div></article>`;
  const result = unresolved(pair) ? 'Missing values require review.' : mismatch(pair) ? 'The normalized values are different.' : 'The normalized values match.';
  document.getElementById('evidenceContent').innerHTML = `<div class="proof-grid">${pair.map(card).join('')}</div><div class="verification-strip"><div><small>${label} · Verification result</small><strong>${result}</strong></div></div>`;
})();
