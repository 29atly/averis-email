(function () {
  const { categoryLabels, getCase, getDifferences, selectCase } = window.ShippingStore;
  const item = getCase();
  selectCase(item.id);
  const container = document.getElementById('messageContent');
  const comparison = item.category === 'bl_comparison';
  const differences = comparison ? getDifferences(item) : [];
  const initials = item.sender.split('@')[0].split(/[._-]/).slice(0, 2).map(part => part.charAt(0).toUpperCase()).join('') || 'EM';
  const attachments = item.attachments || [];

  let outcome;
  if (item.status === 'review') {
    outcome = { tone: 'review', title: 'Human review required', copy: item.reviewReason, action: `<a class="primary-button" href="review.html?case=${encodeURIComponent(item.id)}">Review case</a>` };
  } else if (!comparison) {
    outcome = { tone: 'classified', title: `Classified as ${categoryLabels[item.category]}`, copy: 'No document comparison is required for this email.', action: '' };
  } else if (differences.length) {
    outcome = { tone: 'mismatch', title: `${differences.length} mismatches detected`, copy: 'The Shipping Instruction and draft Bill of Lading contain different shipment details.', action: `<a class="primary-button" href="comparison.html?case=${encodeURIComponent(item.id)}">View document comparison</a>` };
  } else {
    outcome = { tone: 'match', title: 'No mismatch detected', copy: 'All 7 required shipment fields match. No action is required.', action: `<a class="secondary-button" href="comparison.html?case=${encodeURIComponent(item.id)}">View comparison details</a>` };
  }

  container.innerHTML = `
    <div class="message-toolbar">
      <a class="icon-link" href="index.html" aria-label="Back to Inbox">← <span>Back to Inbox</span></a>
      <span class="message-index">${escapeHTML(item.id)}</span>
    </div>
    <article class="message-article">
      <div class="message-subject-line">
        <h1>${escapeHTML(item.subject)} <span class="category-label">${escapeHTML(categoryLabels[item.category])}</span></h1>
      </div>
      <div class="sender-line">
        <span class="sender-avatar">${escapeHTML(initials)}</span>
        <div><div class="sender-name">${escapeHTML(item.sender)}</div><div class="sender-recipient">to ${escapeHTML(item.recipient)}</div></div>
        <span class="sender-time">${escapeHTML(item.receivedLabel)}</span>
      </div>
      <div class="message-body">${escapeHTML(item.body)}</div>
      ${attachments.length ? `<section class="attachment-area"><h2>${attachments.length} attachments</h2><div class="attachment-grid">${attachments.map(attachment => `<a class="attachment-card" href="${escapeHTML(window.ShippingStore.downloadURL(attachment.download_url))}"><span class="attachment-thumb">FILE</span><span><span class="attachment-name">${escapeHTML(attachment.name)}</span><span class="attachment-type">Original attachment</span></span></a>`).join('')}</div></section>` : ''}
      <div class="result-banner ${outcome.tone}"><div><strong>${escapeHTML(outcome.title)}</strong><p>${escapeHTML(outcome.copy)}</p></div>${outcome.action}</div>
    </article>`;
})();
