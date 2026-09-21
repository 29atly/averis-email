(function () {
  const { cases, categoryLabels, getDifferences, selectCase } = window.ShippingStore;
  const params = new URLSearchParams(location.search);
  let filter = params.get('view') === 'completed' ? 'completed' : 'all';
  const rows = document.getElementById('emailRows');
  const search = document.getElementById('globalSearch');
  const count = document.getElementById('mailboxCount');
  const requestedSearch = params.get('search') || '';
  search.value = requestedSearch;

  const preview = item => item.body.replace(/\s+/g, ' ').trim().slice(0, 105);
  const categoryTone = category => ({ bl_comparison: 'blue', si_request: 'purple', invoice_query: 'orange', general: 'gray', spam: 'red' })[category] || 'gray';
  const resultFor = item => {
    if (item.status === 'pending') return { label: 'Open to process', tone: 'gray' };
    if (item.status === 'review') return { label: 'Needs human review', tone: 'orange' };
    if (item.category !== 'bl_comparison') return { label: 'Classification complete', tone: 'gray' };
    const differences = getDifferences(item);
    if (differences.length) return { label: `${differences.length} mismatches found`, tone: 'red' };
    return { label: 'No mismatch detected', tone: 'teal' };
  };

  function render() {
    const query = search.value.trim().toLowerCase();
    const result = cases.filter(item => {
      const matchesSearch = `${item.id} ${item.subject} ${item.sender} ${item.body}`.toLowerCase().includes(query);
      const matchesFilter = filter === 'all' ||
        filter === item.category ||
        (filter === 'completed' && item.status === 'complete');
      return matchesSearch && matchesFilter;
    });

    count.textContent = `${result.length} ${result.length === 1 ? 'message' : 'messages'}`;
    rows.innerHTML = result.length ? result.map((item, index) => {
      const outcome = resultFor(item);
      return `<button type="button" class="email-row ${index === 0 ? 'unread' : ''}" data-case="${escapeHTML(item.id)}" role="row">
        <span class="row-check" aria-hidden="true"></span>
        <span class="email-sender">${escapeHTML(item.sender)}</span>
        <span class="email-subject">${escapeHTML(item.subject)} <span class="email-preview">— ${escapeHTML(preview(item))}</span></span>
        <span class="pill email-category ${categoryTone(item.category)}">${escapeHTML(categoryLabels[item.category])}</span>
        <span class="pill email-result ${outcome.tone}">${escapeHTML(outcome.label)}</span>
        <span class="email-time">${escapeHTML(item.time)}</span>
      </button>`;
    }).join('') : '<div class="empty">No emails match this view.</div>';

    rows.querySelectorAll('[data-case]').forEach(row => row.addEventListener('click', () => {
      selectCase(row.dataset.case);
      location.href = `message.html?case=${encodeURIComponent(row.dataset.case)}`;
    }));
  }

  search.addEventListener('input', render);
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-filter]').forEach(item => item.classList.remove('active'));
    button.classList.add('active');
    filter = button.dataset.filter;
    render();
  }));

  if (filter === 'completed') {
    document.querySelectorAll('[data-filter]').forEach(item => item.classList.remove('active'));
  }
  render();
})();
