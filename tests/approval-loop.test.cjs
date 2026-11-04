const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path'), crypto = require('node:crypto');
const memoryStore = require('../lib/asx-memory.cjs');

test('model-proposed patterns require explicit user approval and track it', async () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-mem-'));
  const storeDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-db-'));
  process.env.KUHUL_MEMORY_DIR = dataDir;
  process.env.KUHUL_DATA_DIR = storeDir;
  const app = require('../orchestrator.js');
  const server = app.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  const userId = 'test-approval-' + crypto.randomUUID().slice(0, 8);
  const memPath = path.join(dataDir, '.asx_memory.json');
  try {
    // Simulate the model proposing a candidate (same record shape daemonAgentPropose writes).
    const scope = memoryStore.userScope(userId);
    const candidateId = crypto.randomUUID();
    await memoryStore.appendRecord(memPath, {
      id: candidateId, type: 'grammar_candidate', schema: 'asx.memory.grammar-candidate.v1',
      createdAt: new Date().toISOString(), agentId: 'daemon-bot', userScope: scope,
      sourceSnapshotId: null, mode: 'buddy', status: 'pending_review', admission: 'proposal_only',
      candidate: { pattern: 'TEST *', response: 'test reply', mode: 'buddy', micronautBindings: [], conditions: {}, selection: {}, piField: { key: null, coordinates: null } },
    });

    const json = async (url, method = 'GET', body) => {
      const res = await fetch(base + url, {
        method, headers: { 'Content-Type': 'application/json' },
        ...(body === undefined ? {} : { body: JSON.stringify(body) })
      });
      return { status: res.status, body: await res.json() };
    };

    // 1) not approved yet
    let list = await json('/api/daemon/agents/daemon-bot/learning/candidates?userId=' + userId);
    let mine = list.body.candidates.find(c => c.id === candidateId);
    assert.equal(mine.status, 'pending_review');

    // 2) reject is impossible without approved:true
    const reject = await json('/api/daemon/agents/daemon-bot/learning/admit', 'POST', { candidateId, userId, approved: false });
    assert.equal(reject.status, 400);

    // 3) approve
    const admit = await json('/api/daemon/agents/daemon-bot/learning/admit', 'POST', { candidateId, userId, approved: true });
    assert.equal(admit.status, 201);
    assert.equal(admit.body.status, 'admitted');

    // 4) now tracked as approved
    list = await json('/api/daemon/agents/daemon-bot/learning/candidates?userId=' + userId);
    mine = list.body.candidates.find(c => c.id === candidateId);
    assert.equal(mine.status, 'admitted');
  } finally {
    await new Promise(resolve => server.close(resolve));
    app.locals.objectStore.close();
    fs.rmSync(dataDir, { recursive: true, force: true });
    fs.rmSync(storeDir, { recursive: true, force: true });
  }
});
