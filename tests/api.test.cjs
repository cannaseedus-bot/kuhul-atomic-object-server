const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { decode } = require('../lib/object-store.cjs');
test('manifest routes serve CRUD, binary export and accurate HTTP errors', async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-api-'));
  process.env.KUHUL_DATA_DIR = dir;
  const app = require('../orchestrator.js');
  const server = app.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  const base = 'http://127.0.0.1:' + server.address().port;
  const send = (url, method = 'GET', body, headers = {}) => fetch(base + url, {
    method, headers: { 'Content-Type': 'application/json', ...headers },
    ...(body === undefined ? {} : { body: JSON.stringify(body) })
  });
  try {
    assert.equal((await send('/')).status, 200);
    assert.equal((await send('/api/manifest')).status, 200);
    assert.equal((await send('/api/inventory')).status, 200);
    const table = '/api/tables/objects/rows';
    const row = { id: 'api-test', object: { key: '⟁TEST' }, dtype: 'uint8', data: [0, 255, 12] };
    assert.equal((await send(table, 'POST', row)).status, 201);
    assert.equal((await send(table, 'POST', row)).status, 409);
    assert.deepEqual(await (await send(table + '/api-test')).json(), row);
    assert.equal((await send(table + '/api-test', 'PUT', { ...row, data: [2] })).status, 200);
    const binary = await send('/api/tables/objects/binary');
    assert.equal(binary.headers.get('content-type'), 'application/octet-stream');
    assert.deepEqual(decode(Buffer.from(await binary.arrayBuffer())).objects.find(r => r.id === row.id).data, [2]);
    assert.equal((await send(table + '/api-test', 'PUT', { ...row, id: 'different' })).status, 400);
    assert.equal((await send(table + '?limit=0')).status, 400);
    assert.equal((await send(table, 'POST', { ...row, id: 'bad', data: [256] })).status, 400);
    assert.equal((await send(table, 'POST', row, { Origin: 'https://unrelated.example' })).status, 403);
    assert.equal((await send('/api/no-such-route')).status, 404);
    assert.equal((await send('/api/tables/no-such-table/rows')).status, 404);
    assert.equal((await send('/orchestrator.js')).status, 404);
    assert.equal((await send('/lib/object-store.cjs')).status, 404);
    assert.equal((await send('/.kuhul-data/tables.kdb')).status, 404);
    assert.equal((await send('/api/infer', 'POST', {})).status, 400);
    assert.equal((await send('/api/infer', 'POST', { prompt: '   ' })).status, 400);
    assert.equal((await send('/api/infer', 'POST', { '@infer': {} })).status, 400);
    const invalid = await fetch(base + table, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{bad' });
    assert.equal(invalid.status, 400);
    assert.equal((await send(table + '/api-test', 'DELETE')).status, 204);
    assert.equal((await send(table + '/api-test')).status, 404);
  } finally {
    await new Promise(resolve => server.close(resolve));
    app.locals.objectStore.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
