(function () {
  const icons = {
    queue: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 5h16v14H4z"/><path d="m4 6 8 7 8-7"/></svg>',
    review: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M7 4h10v17H7z"/><path d="M9 4V2h6v2M9.5 12l2 2 4-5"/></svg>',
    complete: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="9"/><path d="m8 12 2.5 2.5L16 9"/></svg>',
    history: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 12a8 8 0 1 0 2.3-5.7L4 8.6"/><path d="M4 4v4.6h4.6M12 7v5l3 2"/></svg>'
  };
  const active = document.body.dataset.module;
  const params = new URLSearchParams(location.search);
  const listView = params.get('view');
  const selected = window.ShippingStore?.getCase();
  const reviewCount = window.ShippingStore?.cases.filter(item => item.status === 'review').length || 0;
  const completedCount = window.ShippingStore?.cases.filter(item => item.status === 'complete').length || 0;
  const modules = [
    { id: 'inbox', href: 'index.html', icon: icons.queue, label: 'Work Queue', count: window.ShippingStore?.cases.length || 0 },
    { id: 'review', href: 'review.html', icon: icons.review, label: 'Needs Human Review', count: reviewCount },
    { id: 'completed', href: 'index.html?view=completed', icon: icons.complete, label: 'Completed Cases', count: completedCount },
    { id: 'activity', href: `activity.html${selected ? `?case=${encodeURIComponent(selected.id)}` : ''}`, icon: icons.history, label: 'Activity History', count: '' }
  ];
  const navigationActive = active === 'inbox' && listView === 'completed' ? 'completed' : active === 'message' || active === 'comparison' || active === 'evidence' ? 'inbox' : active;

  document.getElementById('sidebar').innerHTML = `
    <div class="brand">
      <div class="brand-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none"><path d="M3 15h18l-3.2 5H6.5L3 15Z" fill="currentColor"/><path d="M7 5h10v10H7V5Z" stroke="currentColor" stroke-width="1.8"/><path d="M10 8h4M10 11h4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></div>
      <div><strong>Shipping Mailroom</strong><small>Document verification</small></div>
    </div>
    <div class="nav-label">Modules</div>
    <nav class="module-nav" aria-label="Application modules">
      ${modules.map(item => `<a href="${item.href}" class="${navigationActive === item.id ? 'active' : ''}" ${navigationActive === item.id ? 'aria-current="page"' : ''}><span class="nav-icon" aria-hidden="true">${item.icon}</span><span>${item.label}</span>${item.count !== '' ? `<b>${item.count}</b>` : ''}</a>`).join('')}
    </nav>
    <div class="sidebar-profile">
      <div class="profile-avatar">DR</div>
      <div class="profile-copy"><strong>Demo Reviewer</strong><span>Operations Team</span></div>
    </div>`;

  const topbar = document.getElementById('topbar');
  topbar.innerHTML = `
    <label class="global-search">
      <span class="search-icon" aria-hidden="true">⌕</span>
      <span class="sr-only">Search emails and shipping documents</span>
      <input id="globalSearch" type="search" placeholder="Search emails and shipping documents" autocomplete="off">
    </label>
    <div class="pipeline-state"><span></span>Pipeline connected</div>`;

  const search = document.getElementById('globalSearch');
  if (active !== 'inbox') {
    search.addEventListener('keydown', event => {
      if (event.key === 'Enter' && search.value.trim()) location.href = `index.html?search=${encodeURIComponent(search.value.trim())}`;
    });
  }

  window.notify = message => {
    const toast = document.getElementById('toast');
    if (!toast) return;
    toast.textContent = message;
    toast.classList.add('show');
    clearTimeout(window.toastTimer);
    window.toastTimer = setTimeout(() => toast.classList.remove('show'), 2400);
  };
  window.titleCase = value => String(value).replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase());
  window.escapeHTML = value => String(value ?? '').replace(/[&<>'"]/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' })[character]);

  if (active === 'review' && document.getElementById('reviewDetail')) {
    const { cases, fieldDefinitions, getCase, selectCase } = window.ShippingStore;
    const queue = cases.filter(item => item.status === 'review');
    let reviewItem = getCase();
    if (!queue.some(entry => entry.id === reviewItem?.id)) reviewItem = queue[0];
    if (reviewItem) selectCase(reviewItem.id);
    document.getElementById('queueCount').textContent = queue.length;
    document.getElementById('queueList').innerHTML = queue.length ? queue.map(entry => `
      <a class="queue-item ${entry.id === reviewItem?.id ? 'active' : ''}" href="review.html?case=${encodeURIComponent(entry.id)}">
        <strong>${escapeHTML(entry.subject)}</strong><span>${escapeHTML(entry.id)} · ${escapeHTML(titleCase(entry.reviewReasonCode || 'review required'))}</span>
      </a>`).join('') : '<div class="empty">The human review queue is clear.</div>';
    const detail = document.getElementById('reviewDetail');
    if (!reviewItem) {
      detail.innerHTML = '<div class="empty"><h2>No cases waiting</h2><p>New uncertain or incomplete cases will appear here.</p></div>';
    } else {
      const reviewFields = reviewItem.reviewFields || [];
      const fieldName = key => fieldDefinitions.find(([field]) => field === key)?.[1] || titleCase(key);
      const inputs = reviewItem.canConfirmValues ? reviewFields.map(key => ['si', 'bl'].map((side, index) => {
        const value = reviewItem.values[key][index];
        return `<div><label>${side.toUpperCase()} · ${escapeHTML(fieldName(key))}</label><p>${escapeHTML(value.source_text || 'No source text available')}</p><input data-side="${side}" data-review-field="${key}" value="${escapeHTML(value.normalized == null ? '' : value.raw)}" required></div>`;
      }).join('')).join('') : '';
      const categoryInput = !reviewItem.siFile && !reviewItem.blFile ? `<label>Confirm classification<select id="reviewCategory"><option value="">Choose category</option>${Object.entries(window.ShippingStore.categoryLabels).filter(([key]) => key !== 'unclassified').map(([key, label]) => `<option value="${key.toUpperCase()}">${escapeHTML(label)}</option>`).join('')}</select></label>` : '';
      detail.innerHTML = `<div class="case-banner"><div><span class="kicker">${escapeHTML(reviewItem.id)} · Decision needed</span><h2>${escapeHTML(reviewItem.subject)}</h2></div></div><div class="review-detail"><div class="review-alert"><h2>Why this needs you</h2><p>${escapeHTML(reviewItem.reviewReason)}</p></div><form class="review-form" id="reviewForm"><div class="review-fields">${inputs}${categoryInput}</div><div class="button-row">${inputs || categoryInput ? '<button class="primary-button" type="submit">Confirm and continue</button>' : ''}<a class="secondary-button" href="message.html?case=${encodeURIComponent(reviewItem.id)}">View original email and attachments</a><button class="secondary-button" type="button" id="retryButton">Retry processing</button></div></form></div>`;
      document.getElementById('reviewForm').addEventListener('submit', async event => {
        event.preventDefault();
        const payload = { revision: reviewItem.revision, si: {}, bl: {} };
        document.querySelectorAll('[data-review-field]').forEach(input => { payload[input.dataset.side][input.dataset.reviewField] = input.value.trim(); });
        const category = document.getElementById('reviewCategory')?.value;
        if (category) payload.category = category;
        const button = event.submitter; button.disabled = true;
        try {
          const result = await window.ShippingStore.review(reviewItem.id, payload);
          location.href = `${result.category === 'bl_comparison' ? 'comparison' : 'message'}.html?case=${encodeURIComponent(result.id)}`;
        } catch (error) { notify(error.message); button.disabled = false; }
      });
      document.getElementById('retryButton').addEventListener('click', async event => {
        event.target.disabled = true; notify('Processing email again…');
        try { await window.ShippingStore.retry(reviewItem.id); location.reload(); }
        catch (error) { notify(error.message); event.target.disabled = false; }
      });
    }
  }
})();
