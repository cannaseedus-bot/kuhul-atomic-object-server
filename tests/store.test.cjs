const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { ObjectStore, encode, decode } = require('../lib/object-store.cjs');
const contract = require('../manifest.json').database;
test('binary roundtrip preserves typed values and rejects corrupted bytes', () => {
  const tables = { sample: [
    { id: 'bytes', object: { key: '⟁', nested: { value: 1 } }, dtype: 'uint8', data: [0, 255] },
    { id: 'float', object: {}, dtype: 'float32', data: [Math.fround(0.1), -2] },
    { id: 'double', object: {}, dtype: 'float64', data: [Math.PI, -1e100] }
  ] };
  const bytes = encode(tables);
  assert.deepEqual(decode(bytes), tables);
  bytes[bytes.length - 33] ^= 1;
  assert.throws(() => decode(bytes), /checksum/);
});
test('CRUD survives restart; invalid writes and duplicates leave the snapshot intact', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-store-'));
  let store;
  try {
    store = new ObjectStore(contract, dir);
    assert.throws(() => new ObjectStore(contract, dir), /writer.lock/);
    const row = { id: 'test', object: { phase: 'Sek' }, dtype: 'float64', data: [1, 2.5] };
    assert.equal(store.put('objects', row, true).created, true);
    assert.throws(() => store.put('objects', row, true), { status: 409 });
    assert.throws(() => store.put('objects', { ...row, dtype: 'uint8', data: [-1] }), { status: 400 });
    assert.throws(() => store.put('objects', { ...row, data: [Infinity] }), { status: 400 });
    assert.throws(() => store.put('objects', { ...row, dtype: 'float32', data: [1e100] }), { status: 400 });
    assert.throws(() => store.put('__proto__', row), { status: 404 });
    assert.throws(() => store.put('objects', { ...row, id: '../escape' }), { status: 400 });
    store.close(); store = new ObjectStore(contract, dir);
    assert.deepEqual(store.get('objects', 'test'), row);
    store.remove('objects', 'test');
    store.close(); store = new ObjectStore(contract, dir);
    assert.throws(() => store.get('objects', 'test'), { status: 404 });
  } finally { store?.close(); fs.rmSync(dir, { recursive: true, force: true }); }
});
test('failed commit does not mutate memory', () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'kuhul-failure-'));
  const store = new ObjectStore(structuredClone(contract), dir);
  try {
    const before = fs.readFileSync(store.file);
    store.contract.limits.maxDatabaseBytes = before.length;
    assert.throws(() => store.put('objects', { id: 'oversize', object: {}, data: [1, 2, 3] }), { status: 413 });
    assert.throws(() => store.get('objects', 'oversize'), { status: 404 });
    assert.deepEqual(fs.readFileSync(store.file), before);
  } finally { store.close(); fs.rmSync(dir, { recursive: true, force: true }); }
});
