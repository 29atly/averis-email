// Exercise the real browser scripts with a minimal DOM and mocked HTTP boundary.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

async function boot(module, records, options = {}) {
  const elements = new Map(); const scripts = []; const requests = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, { innerHTML: '', textContent: '', value: '', dataset: {},
      classList: { add() {}, remove() {} }, children: [], listeners: {},
      append(...items) { this.children.push(...items); }, prepend(item) { this.children.unshift(item); },
      replaceChildren(...items) { this.children = items; }, remove() {},
      querySelectorAll() { return []; }, addEventListener(name, listener) { this.listeners[name] = listener; } });
    return elements.get(id);
  }
  const context = { URLSearchParams, setTimeout, clearTimeout, console,
    location: { origin: 'http://localhost:8000', pathname: '/ui/index.html', search: options.search || '', reload() {} },
    localStorage: { getItem() { return null; }, setItem() {} },
    document: { body: { dataset: { module }, append(node) {
      scripts.push(node.src);
      try { vm.runInContext(fs.readFileSync(`frontend/${node.src}`, 'utf8'), context); node.onload(); }
      catch (error) { node.onerror(error); }
    } }, createElement: tag => ({ ...element(`created-${Math.random()}`), tag }),
      getElementById: element, querySelector: () => element('main'), querySelectorAll: () => [] },
    fetch: async (url, init) => {
      requests.push({ url, init });
      if (options.fail) return { ok: false, status: 503, json: async () => ({ detail: 'Inbox unavailable' }) };
      const body = url.includes('?limit=') ? records : records.find(item => url.includes(encodeURIComponent(item.id)));
      return { ok: true, json: async () => body };
    } };
  context.window = context;
  vm.createContext(context);
  await vm.runInContext(fs.readFileSync('frontend/data.js', 'utf8'), context);
  return { context, elements, scripts, requests };
}

const fields = ['shipper','consignee','notify_party','port_of_loading','port_of_discharge','container_count','gross_weight_kg'];
const item = { id: 'email_1', subject: '<img src=x onerror=alert(1)>', sender: 'sender@example.com', body: 'Message',
  category: 'bl_comparison', status: 'complete', attachments: [], activity: [], values: Object.fromEntries(fields.map(field => [field,
    [{raw: '<script>SI</script>', normalized: 'A', source_text: '<script>source</script>'}, {raw: 'BL', normalized: 'B'}]])),
  defectFields: fields, evidenceCoverage: 0, revision: 1 };

test('queue loads API data before rendering and does not process the inbox', async () => {
  const result = await boot('inbox', [{ ...item, status: 'pending', category: 'unclassified' }]);
  assert.deepEqual(result.scripts, ['app.js', 'inbox.js']);
  assert.equal(result.requests.length, 1);
  assert.match(result.elements.get('emailRows').innerHTML, /Open to process/);
  assert.doesNotMatch(result.elements.get('emailRows').innerHTML, /<img/);
});

test('all detail modules load successfully with real contract shape', async () => {
  for (const module of ['message','comparison','evidence','activity']) {
    const result = await boot(module, [item]);
    assert.deepEqual(result.scripts, ['app.js', `${module}.js`]);
    assert.equal(result.requests.length, 2);
    assert.equal(result.elements.get('main').children.some(child => child.textContent === 'Unable to load the mailroom'), false);
    for (const [id, element] of result.elements) {
      assert.doesNotMatch(element.innerHTML, /<script>|<img/, `${module}: unsafe ${id}`);
    }
  }
});

test('review and empty states do not crash', async () => {
  for (const module of ['inbox', 'review', 'message', 'comparison', 'evidence', 'activity']) {
    const result = await boot(module, []);
    assert.equal(result.elements.get('main').children.some(child => child.textContent === 'Unable to load the mailroom'), false, module);
  }
  const result = await boot('review', [{ ...item, status: 'review', canConfirmValues: true, reviewFields: ['shipper'] }]);
  assert.match(result.elements.get('reviewDetail').innerHTML, /data-side="si"/);
  assert.match(result.elements.get('reviewDetail').innerHTML, /data-side="bl"/);
  assert.doesNotMatch(result.elements.get('reviewDetail').innerHTML, /<script>|<img/);
});

test('connection errors are shown without displaying demo data', async () => {
  const result = await boot('inbox', [], { fail: true });
  assert.equal(result.scripts.length, 0);
  assert.equal(result.context.ShippingStore, undefined);
  assert.equal(result.elements.get('main').children[1].textContent, 'Inbox unavailable');
});
