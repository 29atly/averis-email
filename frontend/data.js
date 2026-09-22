/* Load the API before rendering modules; failures never fall back to demo records. */
(async function () {
  const params = new URLSearchParams(location.search);
  const base = (window.AVERIS_API_URL || (location.pathname.startsWith('/ui/') ? location.origin : 'http://localhost:8000')).replace(/\/$/, '');
  const main = document.querySelector('main');
  const moduleName = document.body.dataset.module;
  const loading = document.createElement('div');
  loading.className = 'loading-state';
  loading.innerHTML = '<p role="status">Loading your mailroom…</p><div class="skeleton" aria-hidden="true"></div><div class="skeleton" aria-hidden="true"></div><div class="skeleton" aria-hidden="true"></div><div class="skeleton" aria-hidden="true"></div>';
  main.setAttribute('aria-busy', 'true');
  main.prepend(loading);
  async function request(path, options = {}) {
    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
    const headers = isFormData ? { ...options.headers } : { 'Content-Type': 'application/json', ...options.headers };
    const response = await fetch(base + path, { ...options, headers });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${response.status})`);
    }
    return response.json();
  }
  const script = src => new Promise((resolve, reject) => {
    const node = document.createElement('script'); node.src = src; node.onload = resolve; node.onerror = reject; document.body.append(node);
  });
  try {
    const cases = [];
    if (moduleName !== 'settings') {
      for (let offset = 0; ; offset += 1000) {
        const batch = await request(`/cases?limit=1000&offset=${offset}`);
        cases.push(...batch);
        if (batch.length < 1000) break;
      }
    }
    const fieldDefinitions = [['shipper', 'Shipper'], ['consignee', 'Consignee'], ['notify_party', 'Notify party'], ['port_of_loading', 'Port of loading'], ['port_of_discharge', 'Port of discharge'], ['container_count', 'Container count'], ['gross_weight_kg', 'Gross weight']];
    const categoryLabels = { unclassified: 'Not processed', bl_comparison: 'Bill of Lading Comparison', si_request: 'Shipping Instruction Request', invoice_query: 'Invoice Query', general: 'General', review: 'REVIEW', spam: 'Spam' };
    const getSelectedId = () => params.get('case') || localStorage.getItem('selectedCase');
    const getCase = (id = getSelectedId()) => cases.find(item => item.id === id) || cases[0];
    const selectCase = id => localStorage.setItem('selectedCase', id);
    const module = moduleName;
    let selected = getCase();
    if (module === 'review' && selected?.status !== 'review') selected = cases.find(item => item.status === 'review');
    if (['comparison', 'evidence'].includes(module) && selected?.category !== 'bl_comparison') selected = cases.find(item => item.category === 'bl_comparison');
    if (selected && !['inbox', 'settings'].includes(module)) {
      loading.querySelector('p').textContent = 'Processing email and loading its result…';
      const detail = await request(`/cases/${encodeURIComponent(selected.id)}`);
      cases[cases.findIndex(item => item.id === detail.id)] = detail;
      selectCase(detail.id);
      // Make fallback selection consistent even when the URL names another category.
      params.set('case', detail.id);
    }
    const mismatch = pair => pair?.every(value => value.normalized != null) && pair[0].normalized !== pair[1].normalized;
    const unresolved = pair => !pair || pair.some(value => value.normalized == null);
    window.ShippingStore = { cases, fieldDefinitions, categoryLabels, getCase, getSelectedId, selectCase, mismatch, unresolved,
      getDifferences: item => fieldDefinitions.filter(([key]) => item.defectFields?.includes(key)),
      downloadURL: path => base + path,
      review: (id, payload) => request(`/cases/${encodeURIComponent(id)}/review`, { method: 'POST', body: JSON.stringify(payload) }),
      retry: id => request(`/cases/${encodeURIComponent(id)}/retry`, { method: 'POST' }),
      create: formData => request('/cases', { method: 'POST', body: formData }),
      process: id => request(`/cases/${encodeURIComponent(id)}/process`, { method: 'POST' }),
      getGmailSettings: () => request('/settings/gmail'),
      saveGmailSettings: payload => request('/settings/gmail', { method: 'PUT', body: JSON.stringify(payload) }),
      testGmailSettings: payload => request('/settings/gmail/test', { method: 'POST', body: JSON.stringify(payload) }),
      clearGmailSettings: () => request('/settings/gmail', { method: 'DELETE' }) };
    if (typeof EventSource !== 'undefined') {
      const events = new EventSource(`${base}/events`);
      events.addEventListener('inbox', event => {
        try {
          window.dispatchEvent(new CustomEvent('mailroom:inbox', { detail: JSON.parse(event.data) }));
        } catch (_error) { /* Ignore malformed or stale event payloads. */ }
      });
      window.addEventListener('beforeunload', () => events.close(), { once: true });
    }
    loading.remove();
    main.removeAttribute('aria-busy');
    await script('app.js');
    if (!selected && !['inbox', 'review', 'settings'].includes(module)) {
      main.innerHTML = '<div class="empty">No case is available for this view. <a href="index.html">Open the inbox</a>.</div>';
    } else if (module !== 'review') {
      await script(`${module}.js`);
    }
  } catch (error) {
    main.removeAttribute('aria-busy');
    main.classList.add('error-state');
    main.replaceChildren();
    const title = document.createElement('h2'); title.textContent = 'Unable to load the mailroom';
    const detail = document.createElement('p'); detail.textContent = error.message || 'Check the API connection.';
    const retry = document.createElement('button'); retry.textContent = 'Try again'; retry.className = 'primary-button'; retry.onclick = () => location.reload();
    main.append(title, detail, retry);
  }
})();
