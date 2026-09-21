/* Load the API before rendering modules; failures never fall back to demo records. */
(async function () {
  const params = new URLSearchParams(location.search);
  const base = (window.AVERIS_API_URL || (location.pathname.startsWith('/ui/') ? location.origin : 'http://localhost:8000')).replace(/\/$/, '');
  const main = document.querySelector('main');
  const loading = document.createElement('p');
  loading.textContent = 'Loading emails…';
  main.prepend(loading);
  async function request(path, options = {}) {
    const response = await fetch(base + path, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers } });
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
    for (let offset = 0; ; offset += 1000) {
      const batch = await request(`/cases?limit=1000&offset=${offset}`);
      cases.push(...batch);
      if (batch.length < 1000) break;
    }
    const fieldDefinitions = [['shipper', 'Shipper'], ['consignee', 'Consignee'], ['notify_party', 'Notify party'], ['port_of_loading', 'Port of loading'], ['port_of_discharge', 'Port of discharge'], ['container_count', 'Container count'], ['gross_weight_kg', 'Gross weight']];
    const categoryLabels = { unclassified: 'Not processed', bl_comparison: 'Bill of Lading Comparison', si_request: 'Shipping Instruction Request', invoice_query: 'Invoice Query', general: 'General', spam: 'Spam' };
    const getSelectedId = () => params.get('case') || localStorage.getItem('selectedCase');
    const getCase = (id = getSelectedId()) => cases.find(item => item.id === id) || cases[0];
    const selectCase = id => localStorage.setItem('selectedCase', id);
    const module = document.body.dataset.module;
    let selected = getCase();
    if (module === 'review' && selected?.status !== 'review') selected = cases.find(item => item.status === 'review');
    if (['comparison', 'evidence'].includes(module) && selected?.category !== 'bl_comparison') selected = cases.find(item => item.category === 'bl_comparison');
    if (selected && module !== 'inbox') {
      loading.textContent = 'Processing email and loading its result…';
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
      retry: id => request(`/cases/${encodeURIComponent(id)}/retry`, { method: 'POST' }) };
    loading.remove();
    await script('app.js');
    if (!selected && !['inbox', 'review'].includes(module)) {
      main.innerHTML = '<div class="empty">No case is available for this view. <a href="index.html">Open the work queue</a>.</div>';
    } else if (module !== 'review') {
      await script(`${module}.js`);
    }
  } catch (error) {
    main.replaceChildren();
    const title = document.createElement('h2'); title.textContent = 'Unable to load the mailroom';
    const detail = document.createElement('p'); detail.textContent = error.message || 'Check the API connection.';
    const retry = document.createElement('button'); retry.textContent = 'Try again'; retry.onclick = () => location.reload();
    main.append(title, detail, retry);
  }
})();
