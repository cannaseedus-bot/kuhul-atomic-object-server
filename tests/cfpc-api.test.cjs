const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');

test('cfpc contracts are registered and addressable', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-cfpc-'));
  process.env.KUHUL_DATA_DIR = dir;
  const app = require('../orchestrator.js');
  const server = app.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  try {
    const list = await (await fetch(base + '/api/daemon/cfpc')).json();
    assert.ok(Array.isArray(list.contracts));
    assert.ok(list.contracts.length >= 26, 'expected at least 26 cfpc contracts');
    assert.ok(list.gapCapabilityMap && list.gapCapabilityMap.QUERY_GAP === 'pattern_discovery');

    const fn = await (await fetch(base + '/api/daemon/cfpc/verify_contract')).json();
    assert.equal(fn['@kind'], 'semantic.function.v1');

    const resolver = await (await fetch(base + '/api/daemon/cfpc/what-is-intent')).json();
    assert.equal(resolver['@kind'], 'cfpc.intent_resolver');

    assert.equal((await fetch(base + '/api/daemon/cfpc/does-not-exist')).status, 404);
  } finally {
    await new Promise(resolve => server.close(resolve));
    app.locals.objectStore.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
