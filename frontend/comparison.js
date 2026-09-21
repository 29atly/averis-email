(function () {
  const { cases, fieldDefinitions, getCase, selectCase, mismatch, unresolved } = window.ShippingStore;
  const caseSelect = document.getElementById('caseSelect');
  const surface = document.getElementById('comparisonSurface');
  const eligible = cases.filter(item => item.category === 'bl_comparison');
  caseSelect.innerHTML = eligible.map(item => `<option value="${item.id}">${item.id} · ${item.subject}</option>`).join('');
  let item = getCase();
  if (item.category !== 'bl_comparison') item = eligible[0];
  caseSelect.value = item.id;
  selectCase(item.id);
  function render(current) {
    document.getElementById('backToEmail').href = `message.html?case=${current.id}`;
    if (current.status === 'review') {
      surface.innerHTML = `<div class="empty"><span class="pill orange">Human review required</span><h2>${current.subject}</h2><p>The system cannot complete a dependable comparison until the missing values are confirmed.</p><a class="primary-button" href="review.html?case=${current.id}">Review uncertain values</a></div>`;
      return;
    }
    const differences = fieldDefinitions.filter(([key]) => mismatch(current.values[key]));
    const rows = fieldDefinitions.map(([key,label]) => {
      const pair = current.values[key]; const flagged = mismatch(pair); const needsReview = unresolved(pair);
      return `<div class="compare-row ${needsReview ? 'unresolved' : flagged ? 'flagged' : ''}" role="row"><div class="field-name">${label}</div><div class="field-value"><strong>${pair[0].raw}</strong><a href="evidence.html?case=${current.id}&field=${key}">View Shipping Instruction source</a></div><div class="field-value"><strong>${pair[1].raw}</strong><a href="evidence.html?case=${current.id}&field=${key}">View Bill of Lading source</a></div><span class="pill ${needsReview || flagged ? 'orange' : 'teal'}">${needsReview ? 'Needs review' : flagged ? 'Mismatch' : 'Match'}</span></div>`;
    }).join('');
    surface.innerHTML = `<div class="case-banner"><div><span class="kicker">${current.id} · Comparison complete</span><h2>${current.subject}</h2><p>${current.siFile} compared with ${current.blFile}</p></div><span class="case-result ${differences.length ? 'mismatch' : 'match'}">${differences.length ? `${differences.length} mismatch detected` : 'No mismatch detected'}</span></div><div class="comparison-table" role="table" aria-label="SI and BL field comparison"><div class="compare-row header" role="row"><div>Field</div><div>Shipping instruction</div><div>Draft bill of lading</div><div>Result</div></div>${rows}</div><div class="surface-foot"><span>Completed in ${current.processingTime} · Evidence attached to all 7 fields</span><a class="secondary-button" href="activity.html?case=${current.id}">Processing activity</a></div>`;
  }
  caseSelect.addEventListener('change', () => { selectCase(caseSelect.value); location.href = `comparison.html?case=${caseSelect.value}`; });
  render(item);
})();
