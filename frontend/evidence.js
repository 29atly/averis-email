(function () {
  const { fieldDefinitions, getCase, mismatch, selectCase } = window.ShippingStore;
  const item = getCase(); selectCase(item.id);
  const params = new URLSearchParams(location.search);
  const requested = params.get('field');
  const key = fieldDefinitions.some(([field]) => field === requested) ? requested : fieldDefinitions.find(([field]) => mismatch(item.values?.[field]))?.[0] || 'shipper';
  const label = fieldDefinitions.find(([field]) => field === key)?.[1] || titleCase(key);
  const pair = item.values?.[key];
  document.getElementById('backToComparison').href = `comparison.html?case=${item.id}`;
  document.getElementById('fieldTabs').innerHTML = fieldDefinitions.map(([field,name]) => `<a class="${field === key ? 'active' : ''}" href="evidence.html?case=${item.id}&field=${field}">${name}</a>`).join('');
  const page = source => `<div class="document-page"><div class="fake-line"></div><div class="fake-line short"></div><div class="fake-line"></div><div class="fake-line"></div><div class="source-highlight">${source.source_text}</div><div class="fake-line"></div><div class="fake-line short"></div><div class="fake-line"></div></div>`;
  if (!pair) {
    document.getElementById('evidenceContent').innerHTML = '<section class="surface"><div class="empty">Source evidence is unavailable for this field.</div></section>';
    return;
  }
  const different = mismatch(pair);
  document.getElementById('evidenceContent').innerHTML = `<div class="proof-grid"><article class="proof-card"><div class="proof-meta"><span class="doc-type">Shipping instruction</span><h2>${pair[0].file_path}</h2><p>Page ${pair[0].page_number} · Extracted value: ${pair[0].raw}</p></div>${page(pair[0])}</article><article class="proof-card"><div class="proof-meta"><span class="doc-type">Draft bill of lading</span><h2>${pair[1].file_path}</h2><p>Page ${pair[1].page_number} · Extracted value: ${pair[1].raw}</p></div>${page(pair[1])}</article></div><div class="verification-strip"><div><small>${label} · Verification result</small><strong>${different ? 'The normalized values are different.' : 'The normalized values match.'}</strong></div><div class="delta">SI ${pair[0].normalized} ${different ? '→' : '='} BL ${pair[1].normalized}</div></div>`;
})();
