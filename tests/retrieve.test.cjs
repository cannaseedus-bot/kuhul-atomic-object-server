const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { cosineSimilarity, rank, embeddableText } = require('../lib/pattern-embeddings.cjs');

test('cosine and rank are deterministic', () => {
  assert.equal(cosineSimilarity([1, 0], [1, 0]), 1);
  assert.equal(cosineSimilarity([1, 0], [0, 1]), 0);
  const ranked = rank([1, 0, 0], [[0, 1, 0], [1, 0, 0], [0, 0, 1]]);
  assert.equal(ranked[0].index, 1);
  assert.ok(ranked[0].score > ranked[1].score);
});

test('embeddableText strips wildcards and normalizes', () => {
  assert.equal(embeddableText('TELL ME ABOUT *'), 'TELL ME ABOUT');
  assert.equal(embeddableText('what is a cannabis strain'), 'WHAT IS A CANNABIS STRAIN');
});

test('retrieve endpoint returns semantic matches', async (t) => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-mem-'));
  const storeDir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-db-'));
  process.env.KUHUL_MEMORY_DIR = dataDir;
  process.env.KUHUL_DATA_DIR = storeDir;
  const app = require('../orchestrator.js');
  const server = app.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  try {
    const res = await fetch(base + '/api/daemon/agents/daemon-bot/retrieve', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: 'what is a strain', limit: 3 })
    });
    if (res.status === 502) { t.skip('embedding backend unreachable'); return; }
    assert.equal(res.status, 200);
    const body = await res.json();
    assert.ok(Array.isArray(body.matches));
    assert.ok(body.matches.length >= 1);
    assert.ok(Number.isFinite(body.matches[0].score));
    assert.ok(typeof body.matches[0].pattern === 'string');
  } finally {
    await new Promise(resolve => server.close(resolve));
    app.locals.objectStore.close();
    fs.rmSync(dataDir, { recursive: true, force: true });
    fs.rmSync(storeDir, { recursive: true, force: true });
  }
});
