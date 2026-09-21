(function () {
  const { cases, categoryLabels, getDifferences, selectCase } = window.ShippingStore;
  const params = new URLSearchParams(location.search);
  let filter = params.get('view') === 'completed' ? 'completed' : 'all';
  const rows = document.getElementById('emailRows');
  const table = document.querySelector('.email-table');
  const search = document.getElementById('globalSearch');
  const count = document.getElementById('mailboxCount');
  const selectAll = document.getElementById('selectAll');
  const bulkBar = document.getElementById('bulkBar');
  const bulkStatus = document.getElementById('bulkStatus');
  const bulkProcess = document.getElementById('bulkProcess');
  const bulkClear = document.getElementById('bulkClear');
  const bulkStop = document.getElementById('bulkStop');
  const bulkProgress = document.getElementById('bulkProgress');
  const bulkProgressFill = document.getElementById('bulkProgressFill');
  document.getElementById('queueOverview').innerHTML = [
    ['index.html', 'In the mailroom', cases.length],
    ['review.html', 'Needs your attention', cases.filter(item => item.status === 'review').length],
    ['index.html?view=completed', 'Completed', cases.filter(item => item.status === 'complete').length]
  ].map(([href, label, total]) => `<a class="overview-item" href="${href}"><span>${label}</span><strong>${total}</strong></a>`).join('');
  const requestedSearch = params.get('search') || '';
  search.value = requestedSearch;

  const selected = new Set();
  let visible = [];
  let processing = false;
  let stopRequested = false;

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

  function refreshCounts() {
    document.querySelectorAll('.module-nav a').forEach(link => {
      const badge = link.querySelector('b');
      if (!badge) return;
      if (link.getAttribute('href') === 'index.html') badge.textContent = cases.length;
      if (link.getAttribute('href') === 'review.html') badge.textContent = cases.filter(item => item.status === 'review').length;
      if (link.getAttribute('href') === 'index.html?view=completed') badge.textContent = cases.filter(item => item.status === 'complete').length;
    });
  }

  function updateBulkBar() {
    const total = selected.size;
    const unprocessed = visible.filter(item => selected.has(item.id) && item.status === 'pending');
    bulkBar.hidden = total === 0;
    if (total > 0) table.classList.add('has-selection'); else table.classList.remove('has-selection');
    selectAll.checked = total > 0 && visible.every(item => selected.has(item.id));
    selectAll.indeterminate = total > 0 && !selectAll.checked;
    if (processing) return;
    bulkStatus.textContent = `${total} ${total === 1 ? 'email' : 'emails'} selected`;
    bulkProcess.textContent = unprocessed.length ? `Process ${unprocessed.length} selected` : 'Process selected';
    bulkProcess.disabled = unprocessed.length === 0;
    bulkProcess.title = unprocessed.length === 0 && total > 0 ? 'All selected emails are already processed.' : '';
  }

  function render() {
    document.getElementById('queueTitle').textContent = filter === 'completed' ? 'Completed cases' : 'Work queue';
    const query = search.value.trim().toLowerCase();
    visible = cases.filter(item => {
      const matchesSearch = `${item.id} ${item.subject} ${item.sender} ${item.body}`.toLowerCase().includes(query);
      const matchesFilter = filter === 'all' ||
        filter === item.category ||
        (filter === 'completed' && item.status === 'complete');
      return matchesSearch && matchesFilter;
    });

    document.querySelectorAll('[data-filter]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.filter === filter)));
    count.textContent = `${visible.length} ${visible.length === 1 ? 'message' : 'messages'}`;
    const previousPositions = window.MailroomMotion?.positions(rows);
    rows.innerHTML = visible.length ? visible.map((item, index) => {
      const outcome = resultFor(item);
      return `<div class="email-row ${index === 0 ? 'unread' : ''}" data-case="${escapeHTML(item.id)}">
        <span class="row-check"><input type="checkbox" class="row-select" data-select="${escapeHTML(item.id)}" aria-label="Select email from ${escapeHTML(item.sender)}: ${escapeHTML(item.subject)}" ${selected.has(item.id) ? 'checked' : ''}></span>
        <span class="row-avatar" aria-hidden="true">${escapeHTML(item.sender.slice(0, 2).toUpperCase())}</span>
        <span class="email-sender">${escapeHTML(item.sender)}</span>
        <span class="email-subject"><a class="email-open" href="message.html?case=${encodeURIComponent(item.id)}">${escapeHTML(item.subject)}</a> <span class="email-preview">${escapeHTML(preview(item))}</span></span>
        <span class="pill email-category ${categoryTone(item.category)}">${escapeHTML(categoryLabels[item.category])}</span>
        <span class="pill email-result ${outcome.tone}">${escapeHTML(outcome.label)}</span>
        <span class="email-time">${escapeHTML(item.time)}</span>
      </div>`;
    }).join('') : '<div class="empty">No emails match this view.</div>';

    window.MailroomMotion?.reveal(rows, previousPositions);
    rows.querySelectorAll('.email-open').forEach(link => link.addEventListener('click', () => selectCase(link.closest('[data-case]').dataset.case)));
    let lastIndex = null;
    rows.querySelectorAll('.row-select').forEach((box, index) => {
      box.addEventListener('click', event => {
        event.stopPropagation();
        if (event.shiftKey && lastIndex !== null) {
          const [from, to] = [lastIndex, index].sort((a, b) => a - b);
          const boxes = [...rows.querySelectorAll('.row-select')];
          for (let i = from; i <= to; i += 1) {
            boxes[i].checked = box.checked;
            if (box.checked) selected.add(boxes[i].dataset.select); else selected.delete(boxes[i].dataset.select);
          }
          updateBulkBar();
        }
        lastIndex = index;
      });
      box.addEventListener('change', () => {
        if (box.checked) selected.add(box.dataset.select); else selected.delete(box.dataset.select);
        updateBulkBar();
      });
    });
    updateBulkBar();
  }

  search.addEventListener('input', render);
  document.querySelectorAll('[data-filter]').forEach(button => button.addEventListener('click', () => {
    document.querySelectorAll('[data-filter]').forEach(item => item.classList.remove('active'));
    button.classList.add('active');
    filter = button.dataset.filter;
    selected.clear();
    render();
  }));

  selectAll.addEventListener('change', () => {
    if (selectAll.checked) visible.forEach(item => selected.add(item.id));
    else visible.forEach(item => selected.delete(item.id));
    render();
  });

  bulkClear.addEventListener('click', () => { selected.clear(); render(); });
  bulkStop.addEventListener('click', () => { stopRequested = true; bulkStop.disabled = true; bulkStop.textContent = 'Stopping…'; });

  bulkProcess.addEventListener('click', async () => {
    const queue = visible.filter(item => selected.has(item.id) && item.status === 'pending');
    if (!queue.length) return;
    processing = true; stopRequested = false;
    bulkBar.querySelector('.button-row').hidden = true;
    bulkStop.hidden = false; bulkStop.disabled = false; bulkStop.textContent = 'Stop';
    bulkProgress.hidden = false;
    let done = 0, needsReview = 0, failed = 0;
    for (const item of queue) {
      if (stopRequested) break;
      bulkStatus.textContent = `Processing ${done + 1} of ${queue.length}…`;
      bulkProgressFill.style.width = `${Math.round((done / queue.length) * 100)}%`;
      try {
        const updated = await window.ShippingStore.process(item.id);
        Object.assign(item, updated);
        if (updated.status === 'review') needsReview += 1;
      } catch (error) {
        failed += 1;
      }
      done += 1;
      bulkProgressFill.style.width = `${Math.round((done / queue.length) * 100)}%`;
      const row = rows.querySelector(`[data-case="${CSS.escape(item.id)}"]`);
      if (row) {
        const outcome = resultFor(item);
        const categoryPill = row.querySelector('.email-category');
        const resultPill = row.querySelector('.email-result');
        categoryPill.className = `pill email-category ${categoryTone(item.category)}`;
        categoryPill.textContent = categoryLabels[item.category];
        resultPill.className = `pill email-result ${outcome.tone}`;
        resultPill.textContent = outcome.label;
      }
    }
    processing = false;
    bulkBar.querySelector('.button-row').hidden = false;
    bulkStop.hidden = true;
    bulkProgress.hidden = true;
    bulkProgressFill.style.width = '0%';
    refreshCounts();
    const summary = [`${done} processed`, needsReview ? `${needsReview} need review` : null, failed ? `${failed} failed` : null].filter(Boolean).join(' · ');
    notify(stopRequested ? `Stopped early — ${summary}` : summary);
    updateBulkBar();
  });

  // -- compose dialog --------------------------------------------------
  const composeButton = document.getElementById('composeButton');
  const composeDialog = document.getElementById('composeDialog');
  const composeForm = document.getElementById('composeForm');
  const composeSubject = document.getElementById('composeSubject');
  const composeContent = document.getElementById('composeContent');
  const composeFiles = document.getElementById('composeFiles');
  const composeDrop = document.getElementById('composeDrop');
  const composeFileList = document.getElementById('composeFileList');
  const composeError = document.getElementById('composeError');
  const composeSubmit = document.getElementById('composeSubmit');
  const composeCancel = document.getElementById('composeCancel');
  const composeHint = document.getElementById('composeHint');
  const ALLOWED_EXTENSIONS = ['.pdf', '.xlsx', '.txt', '.docx', '.docs'];
  const MAX_FILE_BYTES = 10 * 1024 * 1024;
  const MAX_FILES = 10;
  let pendingFiles = [];
  let composing = false;
  let gmailRefreshPending = false;

  window.addEventListener('mailroom:inbox', event => {
    if (event.detail?.type !== 'gmail_sync' || !event.detail.ingested) return;
    if (composeDialog.open) {
      gmailRefreshPending = true;
      notify(`${event.detail.ingested} new ${event.detail.ingested === 1 ? 'email is' : 'emails are'} waiting. Close this form to refresh.`);
      return;
    }
    location.reload();
  });

  const formatSize = bytes => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / (1024 * 1024)).toFixed(1)} MB`;

  function showComposeError(message) {
    composeError.textContent = message;
    composeError.hidden = !message;
  }

  function renderFileList() {
    composeFileList.innerHTML = pendingFiles.map((file, index) => `
      <li class="file-chip">
        <span class="file-chip-name">${escapeHTML(file.name)}</span>
        <span class="file-chip-size">${formatSize(file.size)}</span>
        <button type="button" class="file-chip-remove" data-remove="${index}" aria-label="Remove ${escapeHTML(file.name)}">✕</button>
      </li>`).join('');
    composeFileList.querySelectorAll('[data-remove]').forEach(button => button.addEventListener('click', () => {
      pendingFiles.splice(Number(button.dataset.remove), 1);
      renderFileList();
    }));
  }

  function addFiles(fileList) {
    showComposeError('');
    for (const file of fileList) {
      const extension = `.${file.name.split('.').pop().toLowerCase()}`;
      if (pendingFiles.length >= MAX_FILES) { showComposeError(`You can attach up to ${MAX_FILES} files.`); break; }
      if (!ALLOWED_EXTENSIONS.includes(extension)) { showComposeError(`${file.name}: unsupported file type. Allowed: PDF, XLSX, TXT, DOCX.`); continue; }
      if (file.size > MAX_FILE_BYTES) { showComposeError(`${file.name}: exceeds the 10 MB limit.`); continue; }
      if (pendingFiles.some(existing => existing.name.toLowerCase() === file.name.toLowerCase())) { showComposeError(`${file.name}: already attached.`); continue; }
      pendingFiles.push(file);
    }
    renderFileList();
  }

  function resetComposeForm() {
    composeForm.reset();
    pendingFiles = [];
    renderFileList();
    showComposeError('');
    composeHint.textContent = 'Processing can take up to a minute.';
  }

  function openCompose() {
    resetComposeForm();
    composeDialog.showModal();
    composeSubject.focus();
  }

  composeButton.addEventListener('click', openCompose);
  document.getElementById('composeClose').addEventListener('click', () => { if (!composing) composeDialog.close(); });
  composeCancel.addEventListener('click', () => { if (!composing) composeDialog.close(); });
  composeDialog.addEventListener('cancel', event => { if (composing) event.preventDefault(); });
  composeDialog.addEventListener('click', event => { if (event.target === composeDialog && !composing) composeDialog.close(); });
  composeDialog.addEventListener('close', () => { if (gmailRefreshPending) location.reload(); });

  composeFiles.addEventListener('change', () => { addFiles(composeFiles.files); composeFiles.value = ''; });
  ['dragover', 'dragenter'].forEach(name => composeDrop.addEventListener(name, event => { event.preventDefault(); composeDrop.classList.add('dragover'); }));
  ['dragleave', 'drop'].forEach(name => composeDrop.addEventListener(name, () => composeDrop.classList.remove('dragover')));
  composeDrop.addEventListener('drop', event => { event.preventDefault(); if (event.dataTransfer?.files) addFiles(event.dataTransfer.files); });

  composeForm.addEventListener('submit', async event => {
    event.preventDefault();
    const subject = composeSubject.value.trim();
    const content = composeContent.value.trim();
    if (!subject && !content && !pendingFiles.length) {
      showComposeError('Add a subject, content, or at least one attachment.');
      return;
    }
    showComposeError('');
    composing = true;
    composeSubmit.disabled = true;
    composeCancel.disabled = true;
    composeSubmit.textContent = 'Creating…';
    const formData = new FormData();
    formData.set('subject', subject);
    formData.set('content', content);
    pendingFiles.forEach(file => formData.append('files', file));
    try {
      const created = await window.ShippingStore.create(formData);
      composeHint.textContent = 'Running the pipeline…';
      composeSubmit.textContent = 'Processing…';
      try {
        await window.ShippingStore.process(created.id);
        notify('Email created and processed.');
      } catch (error) {
        notify(`Email created, but processing failed: ${error.message}`);
      }
      composeDialog.close();
      location.reload();
    } catch (error) {
      showComposeError(error.message);
      composing = false;
      composeSubmit.disabled = false;
      composeCancel.disabled = false;
      composeSubmit.textContent = 'Create and process';
    }
  });

  if (filter === 'completed') {
    document.querySelectorAll('[data-filter]').forEach(item => item.classList.remove('active'));
  }
  render();
})();
