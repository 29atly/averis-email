(function () {
  const store = window.ShippingStore;
  const form = document.getElementById('gmailSettingsForm');
  const address = document.getElementById('gmailAddress');
  const password = document.getElementById('gmailPassword');
  const enabled = document.getElementById('gmailEnabled');
  const badge = document.getElementById('gmailConnectionBadge');
  const error = document.getElementById('gmailSettingsError');
  const save = document.getElementById('gmailSave');
  const test = document.getElementById('gmailTest');
  const remove = document.getElementById('gmailRemove');
  let current = null;

  const formatTime = value => {
    if (!value) return 'Not checked yet';
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
  };

  function showError(message = '') {
    error.textContent = message;
    error.hidden = !message;
  }

  function render(settings) {
    current = settings;
    address.value = settings.address || '';
    password.value = '';
    password.placeholder = settings.configured ? 'Leave blank to keep the saved app password' : 'Enter the 16-character app password';
    enabled.checked = settings.enabled;
    badge.textContent = settings.enabled ? 'Reading new mail' : settings.configured ? 'Connected · paused' : 'Not configured';
    badge.className = `connection-badge ${settings.enabled ? 'connected' : settings.configured ? 'paused' : ''}`;
    document.getElementById('gmailStatusAddress').textContent = settings.address || 'Not connected';
    document.getElementById('gmailStatusEnabled').textContent = settings.enabled ? 'On' : 'Off';
    document.getElementById('gmailLastPoll').textContent = formatTime(settings.last_poll_at);
    document.getElementById('gmailIngestedCount').textContent = settings.ingested_count;
    const lastError = document.getElementById('gmailLastError');
    lastError.textContent = settings.last_error ? `Latest issue: ${settings.last_error}` : '';
    lastError.hidden = !settings.last_error;
    remove.hidden = !settings.configured;
  }

  async function refresh() {
    try {
      render(await store.getGmailSettings());
    } catch (requestError) {
      showError(requestError.message);
    }
  }

  function payload() {
    const result = { address: address.value.trim(), enabled: enabled.checked };
    if (password.value) result.password = password.value;
    return result;
  }

  test.addEventListener('click', async () => {
    showError('');
    test.disabled = save.disabled = true;
    test.textContent = 'Testing…';
    try {
      const request = {};
      if (address.value.trim()) request.address = address.value.trim();
      if (password.value) request.password = password.value;
      await store.testGmailSettings(request);
      notify('Gmail connection successful.');
    } catch (requestError) {
      showError(requestError.message);
    } finally {
      test.disabled = save.disabled = false;
      test.textContent = 'Test connection';
    }
  });

  form.addEventListener('submit', async event => {
    event.preventDefault();
    showError('');
    if (!address.value.trim()) { showError('Enter the Gmail address.'); address.focus(); return; }
    if (!current?.configured && !password.value) { showError('Enter a Google app password for the first connection.'); password.focus(); return; }
    test.disabled = save.disabled = true;
    save.textContent = 'Saving…';
    try {
      render(await store.saveGmailSettings(payload()));
      notify(enabled.checked ? 'Gmail connected. New mail will appear automatically.' : 'Gmail settings saved. Automatic reading is paused.');
    } catch (requestError) {
      showError(requestError.message);
    } finally {
      test.disabled = save.disabled = false;
      save.textContent = 'Save settings';
    }
  });

  remove.addEventListener('click', async () => {
    if (!confirm('Remove the saved Gmail address, app password, and synchronization checkpoint?')) return;
    remove.disabled = true;
    showError('');
    try {
      render(await store.clearGmailSettings());
      notify('Gmail connection removed. Previously imported emails remain available.');
    } catch (requestError) {
      showError(requestError.message);
    } finally {
      remove.disabled = false;
    }
  });

  window.addEventListener('mailroom:inbox', event => {
    if (['gmail_sync', 'gmail_settings'].includes(event.detail?.type)) refresh();
  });

  refresh();
})();
