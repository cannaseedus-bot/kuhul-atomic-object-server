/* UI projection and input adapter for the manifest-owned API contract. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const keys = new Map([...document.querySelectorAll('[data-asx-key]')].map(n => [n.dataset.asxKey, n]));
  let manifest, tableDescriptions = new Map(), busy = false;
  const show = (id, value) => { byId(id).textContent = typeof value === 'string' ? value : JSON.stringify(value, null, 2); };
  const notice = (message, error = false) => { show('notice', message); byId('notice').classList.toggle('error', error); };
  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...options.headers }, cache: 'no-store' });
    const data = response.status === 204 ? null : await response.json();
    if (!response.ok) throw Error(data?.error || data?.['@error']?.['@message'] || 'HTTP ' + response.status);
    return data;
  }
  function route(action, params = {}) {
    const def = manifest.api.routes.find(r => r.action === action);
    if (!def) throw Error('Action is not declared: ' + action);
    return { method: def.method, url: def.path.replace(/:([a-z]+)/g, (_, name) => {
      if (!(name in params)) throw Error('Missing route parameter: ' + name);
      return encodeURIComponent(params[name]);
    }) };
  }
  async function api(action, params, body) {
    const def = route(action, params);
    return request(def.url, { method: def.method, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  }
  const selection = () => ({ table: byId('table-select').value, id: byId('row-id').value.trim() });
  function fill(row) {
    byId('row-id').value = row.id; byId('dtype').value = row.dtype;
    byId('object-json').value = JSON.stringify(row.object, null, 2);
    byId('data-json').value = JSON.stringify(row.data);
  }
  async function rows() {
    const { table } = selection();
    const result = await api('rows', { table });
    const list = byId('row-list'); list.replaceChildren();
    for (const row of result.data) {
      const button = document.createElement('button'); button.className = 'row-item';
      button.textContent = row.id + ' / ' + row.dtype + ' [' + row.data.length + ']';
      button.addEventListener('click', () => { fill(row); show('api-output', row); });
      list.append(button);
    }
    if (!result.total) list.textContent = 'This table is empty. Save an object to begin.';
    show('page-info', 'Showing ' + result.data.length + ' of ' + result.total + ' rows. Load any ID directly.');
    show('table-description', tableDescriptions.get(table) || '');
  }
  async function refresh() {
    const result = await api('tables'), selected = byId('table-select').value;
    byId('table-select').replaceChildren();
    tableDescriptions = new Map(result.data.map(t => [t.name, t.description]));
    for (const table of result.data) byId('table-select').add(new Option(table.name, table.name));
    if (tableDescriptions.has(selected)) byId('table-select').value = selected;
    show('table-count', String(result.data.length));
    show('row-count', String(result.data.reduce((n, t) => n + t.count, 0)));
    show('byte-count', result.data.reduce((n, t) => n + t.bytes, 0).toLocaleString() + ' B');
    await rows();
    show('connection', '● Server connected');
  }
  function fold() {
    const from = Number(byId('source-phase').value), to = Number(byId('target-phase').value);
    const weight = byId('arc-weight').valueAsNumber;
    if (!Number.isFinite(weight)) throw Error('Arc weight must be finite');
    const multiplier = Math.cos((to - from) * manifest.folds.angleStep);
    show('arc-result', (weight * multiplier).toFixed(4) + ' effective · ' + multiplier.toFixed(2) + ' geometry multiplier');
    [...byId('phase-chain').children].forEach((n, i) => n.classList.toggle('active', i === from || i === to));
  }
  const handlers = {
    refresh,
    load: async () => { const row = await api('row', selection()); fill(row); show('api-output', row); },
    save: async () => {
      const params = selection();
      const body = { id: params.id, object: JSON.parse(byId('object-json').value), dtype: byId('dtype').value, data: JSON.parse(byId('data-json').value) };
      const result = await api('put', params, body); show('api-output', result); await refresh();
      notice('Saved ' + params.table + '/' + params.id + ' to the binary database.');
    },
    remove: async () => {
      const params = selection(); await api('remove', params); show('api-output', { deleted: params.id }); await refresh();
      notice('Deleted ' + params.table + '/' + params.id + '.');
    },
    download: async () => {
      const def = route('binary', selection()), response = await fetch(def.url, { cache: 'no-store' });
      if (!response.ok) throw Error('Binary export failed: ' + response.status);
      const url = URL.createObjectURL(await response.blob()), a = document.createElement('a');
      a.href = url; a.download = selection().table + '.kdb'; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    },
    fold,
    inspect: () => { show('manifest-output', { manifest, resolvedDOMKeys: [...keys.keys()] }); byId('manifest-details').open = true; },
    infer: async () => {
      const prompt = byId('prompt').value.trim(); if (!prompt) throw Error('Enter a prompt');
      show('completion', 'Running…');
      const result = await window.KuhulClient.infer({ model: byId('model').value, prompt });
      if (result['@error']) { show('completion', result['@error']); throw Error(result['@error']['@message']); }
      show('completion', result);
    }
  };
  async function call(name) {
    if (busy) return;
    try {
      if (!manifest || !Object.hasOwn(manifest.asx.actions, name)) throw Error('Unknown ASX action: ' + name);
      const handler = handlers[manifest.asx.actions[name]];
      if (!handler) throw Error('No adapter for ' + name);
      busy = true; document.querySelectorAll('[data-asx-call]').forEach(b => { b.disabled = true; });
      await handler();
    } catch (error) { notice(error.message, true); show('api-output', { error: error.message }); }
    finally { busy = false; document.querySelectorAll('[data-asx-call]').forEach(b => { b.disabled = false; }); }
  }
  window.ASX = Object.freeze({ get: key => keys.get(key), call });
  document.addEventListener('click', event => {
    const button = event.target.closest('[data-asx-call]'); if (button) call(button.dataset.asxCall);
  });
  byId('table-select').addEventListener('change', () => rows().catch(error => notice(error.message, true)));
  function tableRow(parent, values) {
    const tr = document.createElement('tr');
    for (const value of values) { const td = document.createElement('td'); td.textContent = value; tr.append(td); }
    byId(parent).append(tr);
  }
  async function boot() {
    manifest = await request('./manifest.json');
    for (const [i, phase] of manifest.folds.phases.entries()) {
      byId('source-phase').add(new Option(phase, i)); byId('target-phase').add(new Option(phase, i));
      const node = document.createElement('span'); node.textContent = String(i + 1).padStart(2, '0') + ' / ' + phase; byId('phase-chain').append(node);
    }
    byId('target-phase').value = '1'; fold();
    for (const def of [...manifest.api.routes, ...manifest.api.adapters]) tableRow('route-list', [def.method, def.path, def.action || def.adapter]);
    handlers.inspect(); byId('manifest-details').open = false;
    const inventory = await request('./stack-inventory.json');
    show('inventory-summary', inventory.files.length + ' inventoried files · ' + inventory.generatedAt);
    for (const item of inventory.files) tableRow('inventory-list', [item.path, item.plane, item.role]);
    try { await refresh(); notice('Ready. Select a table or save a new object.'); }
    catch (error) { show('connection', '○ Server unavailable'); notice('Shell loaded. Start the orchestrator for object storage. ' + error.message, true); }
    if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(error => notice('Service worker: ' + error.message, true));
  }
  boot().catch(error => { show('connection', '○ Boot failed'); notice(error.message, true); });
})();
