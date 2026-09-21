(function () {
  const { cases, getCase, selectCase } = window.ShippingStore;
  const select = document.getElementById('caseSelect');
  select.innerHTML = cases.map(item => `<option value="${escapeHTML(item.id)}">${escapeHTML(item.id)} · ${escapeHTML(item.subject)}</option>`).join('');
  const item = getCase(); select.value = item.id; selectCase(item.id);
  document.getElementById('activityCase').textContent = `${item.id} · ${item.subject}`;
  document.getElementById('activityStatus').textContent = titleCase(item.status);
  document.getElementById('activityStatus').className = `pill ${item.status === 'review' ? 'orange' : 'teal'}`;
  document.getElementById('timeline').innerHTML = item.activity.map(step => `<div class="timeline-item ${step.warning ? 'warning' : ''}"><i></i><strong>${escapeHTML(step.title)}</strong><span>${escapeHTML(step.timestamp)} · ${escapeHTML(step.detail)}</span></div>`).join('') || '<div class="empty">No processing activity recorded.</div>';
  document.getElementById('activityMetrics').innerHTML = `<div class="metric-card"><span>Processing time</span><strong>${escapeHTML(item.processingTime || '—')}</strong><small>Last pipeline execution</small></div><div class="metric-card"><span>Evidence coverage</span><strong>${item.category === 'bl_comparison' ? `${item.evidenceCoverage} / 7` : '—'}</strong><small>Fields with source text and page on both documents</small></div><div class="metric-card"><span>Processing</span><strong>${escapeHTML(titleCase(item.status))}</strong><small>${escapeHTML(item.reviewReason || 'Result available')}</small></div><button class="secondary-button" id="retryProcessing">Retry processing</button>`;
  document.getElementById('retryProcessing').onclick = async event => {
    event.target.disabled = true; notify('Processing email again…');
    try { await window.ShippingStore.retry(item.id); location.reload(); }
    catch (error) { notify(error.message); event.target.disabled = false; }
  };
  select.addEventListener('change', () => { selectCase(select.value); location.href = `activity.html?case=${encodeURIComponent(select.value)}`; });
})();
