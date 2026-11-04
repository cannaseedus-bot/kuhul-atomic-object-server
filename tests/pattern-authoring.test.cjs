const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');

test('user can author patterns that become policy and are replayed', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-mem-'));
  const storeDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-db-'));
  process.env.KUHUL_MEMORY_DIR = dataDir;
  process.env.KUHUL_DATA_DIR = storeDir;
  const app = require('../orchestrator.js');
  const server = app.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  const send = async (url, method = 'GET', body) => {
    const res = await fetch(base + url, {
      method, headers: { 'Content-Type': 'application/json' },
      ...(body === undefined ? {} : { body: JSON.stringify(body) })
    });
    return { status: res.status, body: await res.json() };
  };
  try {
    // author a pattern directly (no model, no snapshot)
    const created = await send('/api/daemon/agents/daemon-bot/patterns', 'POST', { pattern: 'MY OWN *', response: 'you said my own thing', mode: 'buddy' });
    assert.equal(created.status, 201);
    assert.match(created.body.patternId, /^user\./);

    // it is live policy: the reply engine now matches it
    const reply = await send('/api/daemon/agents/daemon-bot/reply', 'POST', { text: 'my own thing', mode: 'buddy' });
    assert.equal(reply.status, 200);
    assert.equal(reply.body.text, 'you said my own thing');

    // it is replayed: catalog (policy) + admissions (replay) both carry it
    const patterns = await send('/api/daemon/agents/daemon-bot/patterns');
    assert.equal(patterns.status, 200);
    assert.ok(patterns.body.patterns.some(p => p.id === created.body.patternId));
    assert.ok(patterns.body.admissions.some(a => a.patternId === created.body.patternId && a.authority === 'user_authored'));

    // duplicate pattern is rejected
    const dup = await send('/api/daemon/agents/daemon-bot/patterns', 'POST', { pattern: 'my own *', response: 'x', mode: 'buddy' });
    assert.equal(dup.status, 409);
  } finally {
    await new Promise(resolve => server.close(resolve));
    app.locals.objectStore.close();
    fs.rmSync(dataDir, { recursive: true, force: true });
    fs.rmSync(storeDir, { recursive: true, force: true });
  }
});
