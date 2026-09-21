(function () {
  const { cases, getCase, selectCase } = window.ShippingStore;
  const select = document.getElementById('caseSelect');
  select.innerHTML = cases.map(item => `<option value="${item.id}">${item.id} · ${item.subject}</option>`).join('');
  const item = getCase(); select.value = item.id; selectCase(item.id);
  const warning = item.status === 'review';
  document.getElementById('activityCase').textContent = `${item.id} · ${item.subject}`;
  document.getElementById('activityStatus').textContent = warning ? 'Attention required' : 'Complete';
  document.getElementById('activityStatus').className = `pill ${warning ? 'orange' : 'teal'}`;
  const steps = item.category !== 'bl_comparison' ? [['Email classified', titleCase(item.category), false],['Workflow routed','No document comparison required',false]] : [['Email classified','Bill of Lading comparison',false],['Attachments resolved',`${item.siFile} + ${item.blFile}`,false],['Documents extracted','Digital text extraction',false],['Seven fields extracted','Raw and normalized values preserved',false],['Source evidence linked','File, page, and original text attached',false],['Validation complete',warning ? `${item.reviewFields?.length || 1} uncertain values require review` : 'All required fields present',warning],['Deterministic comparison',warning ? 'Paused until human confirmation' : 'Comparison result ready',warning]];
  document.getElementById('timeline').innerHTML = steps.map(([title,detail,isWarning]) => `<div class="timeline-item ${isWarning ? 'warning' : ''}"><i></i><strong>${title}</strong><span>${detail}</span></div>`).join('');
  document.getElementById('activityMetrics').innerHTML = `<div class="metric-card"><span>Processing time</span><strong>${item.processingTime || '—'}</strong><small>${warning ? 'Awaiting human action' : 'Processing complete'}</small></div><div class="metric-card"><span>Evidence coverage</span><strong>${item.values ? '7 / 7' : '—'}</strong><small>${item.values ? 'Every required field linked' : 'Not applicable'}</small></div><div class="metric-card"><span>Document extraction</span><strong>${item.values ? 'Complete' : 'Not required'}</strong><small>${item.values ? 'Original text preserved' : 'Classification only'}</small></div>`;
  select.addEventListener('change', () => { selectCase(select.value); location.href = `activity.html?case=${select.value}`; });
})();
