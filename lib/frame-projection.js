/* Manifest-driven top-level frames and key-pattern browser. */
(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  let manifest, definitions, keyEntries = [], keysLoaded = false;
  let canvasProperties = {
    width: 1200, minimumHeight: 440, rowHeight: 36, background: '#020b12',
    font: '13px ui-monospace, Consolas, monospace',
    palette: ['#22f2b3', '#38bdf8', '#c084fc', '#fbbf24'], maxItems: 250,
  };

  async function readJson(path) {
    const response = await fetch('./' + path, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${path}: HTTP ${response.status}`);
    return response.json();
  }

  function drawKeyCanvas(entries) {
    const canvas = byId('key-pattern-canvas');
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;
    const groups = [...new Set(entries.map(item => item.source))].map(source => ({
      source, items: entries.filter(item => item.source === source),
    }));
    const width = Number(canvasProperties.width) || 1200;
    const rowHeight = Number(canvasProperties.rowHeight) || 36;
    const height = Math.max(Number(canvasProperties.minimumHeight) || 250,
      66 + Math.max(1, ...groups.map(group => group.items.length)) * rowHeight);
    canvas.width = width;
    canvas.height = height;
    const colors = Array.isArray(canvasProperties.palette) && canvasProperties.palette.length
      ? canvasProperties.palette : ['#22f2b3', '#38bdf8', '#c084fc', '#fbbf24'];
    context.fillStyle = canvasProperties.background || '#020b12';
    context.fillRect(0, 0, width, height);
    context.font = canvasProperties.font || '13px ui-monospace, Consolas, monospace';
    context.textBaseline = 'middle';
    const columnWidth = width / Math.max(1, groups.length);
    groups.forEach((group, groupIndex) => {
      const color = colors[groupIndex % colors.length];
      const left = groupIndex * columnWidth;
      const hubX = left + 17;
      context.fillStyle = color;
      context.fillText(group.source, left + 14, 23, columnWidth - 28);
      context.strokeStyle = `${color}55`;
      context.lineWidth = 1;
      group.items.forEach((item, itemIndex) => {
        const y = 55 + itemIndex * rowHeight;
        context.beginPath();
        context.moveTo(hubX, 37);
        context.lineTo(hubX, y);
        context.lineTo(left + 29, y);
        context.stroke();
        context.beginPath();
        context.arc(left + 29, y, 3, 0, Math.PI * 2);
        context.fillStyle = color;
        context.fill();
        context.fillStyle = '#d8e7f3';
        const label = item.key.length > 31 ? `${item.key.slice(0, 28)}…` : item.key;
        context.fillText(label, left + 39, y, columnWidth - 48);
      });
    });
  }

  function setFrame(id, updateHash = true) {
    const frame = definitions.frames.find(item => item.id === id) || definitions.frames[0];
    const visible = new Set(frame.sections);
    document.body.dataset.frame = frame.id;
    const aside = document.querySelector('.layout > aside');
    if (aside) aside.hidden = frame.id !== 'dashboard';
    for (const item of definitions.frames) {
      for (const sectionId of item.sections) {
        const section = byId(sectionId);
        if (section) section.hidden = !visible.has(sectionId);
      }
    }
    for (const button of byId('frame-tabs').querySelectorAll('button')) {
      const active = button.dataset.frameId === frame.id;
      button.setAttribute('aria-current', active ? 'page' : 'false');
    }
    if (updateHash) history.replaceState(null, '', `#frame=${encodeURIComponent(frame.id)}`);
    window.scrollTo({ top: 0, behavior: 'smooth' });
    if (frame.id === 'key-patterns') loadKeys().catch(error => {
      byId('key-pattern-status').textContent = `Could not load key manifests: ${error.message}`;
    });
  }

  function showKeys() {
    const query = byId('key-pattern-filter').value.trim().toLocaleLowerCase();
    const list = byId('key-pattern-list');
    list.replaceChildren();
    const matching = keyEntries.filter(item => !query || `${item.key} ${item.values} ${item.source}`.toLocaleLowerCase().includes(query));
    const maxItems = Number(canvasProperties.maxItems) || 250;
    drawKeyCanvas(matching.slice(0, maxItems));
    for (const item of matching.slice(0, maxItems)) {
      const card = document.createElement('article');
      card.className = 'key-pattern-card';
      const key = document.createElement('h3'); key.textContent = item.key;
      const values = document.createElement('p'); values.textContent = item.values || '(no value tracks)';
      const source = document.createElement('small'); source.textContent = item.source;
      card.append(key, values, source); list.append(card);
    }
    byId('key-pattern-status').textContent = `${matching.length} manifest keys${matching.length > maxItems ? ` · showing first ${maxItems}` : ''}`;
  }

  async function loadKeys() {
    if (keysLoaded) { showKeys(); return; }
    const panel = definitions.panels.find(item => item.kind === 'manifest-key-browser');
    if (!panel) throw new Error('No manifest-key-browser panel is declared');
    if (panel.canvasKey) byId('key-pattern-canvas').dataset.asxKey = panel.canvasKey;
    const loaded = await Promise.all(panel.sources.map(async source => {
      const data = await readJson(source.path);
      return Object.entries(data).slice(0, source.limit).map(([key, value]) => ({
        key,
        values: Array.isArray(value) ? value.map(String).join(' · ') : typeof value === 'object' && value !== null
          ? JSON.stringify(value) : String(value),
        source: source.label,
      }));
    }));
    keyEntries = loaded.flat(); keysLoaded = true; showKeys();
  }

  async function boot() {
    manifest = await readJson('manifest.json');
    definitions = await readJson(manifest.uiFrames.definition);
    const tabs = byId('frame-tabs');
    const frameButtons = [];
    for (const frame of definitions.frames) {
      const button = document.createElement('button');
      button.type = 'button'; button.dataset.frameId = frame.id;
      button.dataset.asxKey = frame.glyph; button.textContent = frame.label;
      button.addEventListener('click', () => setFrame(frame.id)); frameButtons.push(button);
    }
    const chatPanel = definitions.panels.find(item => item.frame === 'daemon-chat' && item.kind === 'iframe');
    if (chatPanel) {
      byId('daemon-chat-iframe').src = chatPanel.src;
      byId('chat-open-link').href = chatPanel.src;
      byId('daemon-chat-iframe').title = chatPanel.title;
    }
    for (const panel of definitions.panels.filter(item => item.kind === 'iframe' && item.frame !== 'daemon-chat')) {
      const iframe = byId(`${panel.frame}-iframe`);
      if (iframe) { iframe.src = panel.src; iframe.title = panel.title; }
    }
    const app = await readJson(manifest.daemonAppSource);
    canvasProperties = app['@components']?.['⟁CANVAS']?.['@properties'] || canvasProperties;
    const canvas = byId('key-pattern-canvas');
    if (canvasProperties.accessibleLabel) canvas.setAttribute('aria-label', canvasProperties.accessibleLabel);
    if (canvasProperties.fit === 'responsive') canvas.style.maxWidth = '100%';
    if (canvasProperties.interaction !== 'filter_linked') byId('key-pattern-filter').disabled = true;
    tabs.replaceChildren(...frameButtons);
    byId('key-pattern-filter').addEventListener('input', showKeys);
    const requested = new URLSearchParams(location.hash.slice(1)).get('frame');
    setFrame(requested || definitions.defaultFrame || 'daemon-chat', false);
  }

  boot().catch(error => {
    const status = byId('connection');
    if (status) status.textContent = `Frame metadata unavailable · ${error.message}`;
  });
})();
