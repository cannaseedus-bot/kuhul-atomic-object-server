'use strict';
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const TYPES = { uint8: 1, float32: 4, float64: 8 };
const fail = (status, message) => { throw Object.assign(new Error(message), { status }); };
function validateRow(input, limits) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) fail(400, 'Expected a row object');
  const { id, object = {}, dtype = 'float64', data = [] } = input;
  if (typeof id !== 'string' || !/^[a-zA-Z0-9_-]{1,80}$/.test(id)) fail(400, 'id must contain 1–80 letters, digits, underscores or hyphens');
  if (!object || typeof object !== 'object' || Array.isArray(object)) fail(400, 'object must be a JSON object');
  if (!Object.hasOwn(TYPES, dtype)) fail(400, 'dtype must be uint8, float32 or float64');
  if (!Array.isArray(data) || data.length > limits.maxValuesPerRow) fail(400, 'Invalid or oversized data[]');
  if (data.some(v => typeof v !== 'number' || !Number.isFinite(v) ||
    (dtype === 'uint8' && (!Number.isInteger(v) || v < 0 || v > 255)) ||
    (dtype === 'float32' && !Number.isFinite(Math.fround(v))))) fail(400, 'data[] contains values outside dtype range');
  if (Buffer.byteLength(JSON.stringify(object)) > limits.maxObjectBytes) fail(413, 'Object is too large');
  return { id, object, dtype, data: dtype === 'float32' ? data.map(Math.fround) : data };
}
// KDB1: magic, metadata byte length (u32 LE), UTF-8 JSON metadata, numeric LE bytes, SHA-256.
function encode(tables) {
  let offset = 0;
  const payloads = [];
  const metadata = Object.fromEntries(Object.entries(tables).map(([name, rows]) => [name, rows.map(row => {
    const bytes = Buffer.alloc(row.data.length * TYPES[row.dtype]);
    row.data.forEach((v, i) => {
      if (row.dtype === 'uint8') bytes.writeUInt8(v, i);
      else if (row.dtype === 'float32') bytes.writeFloatLE(v, i * 4);
      else bytes.writeDoubleLE(v, i * 8);
    });
    const entry = { id: row.id, object: row.object, dtype: row.dtype, length: row.data.length, offset };
    offset += bytes.length; payloads.push(bytes); return entry;
  })]));
  const meta = Buffer.from(JSON.stringify(metadata));
  const header = Buffer.alloc(8); header.write('KDB1'); header.writeUInt32LE(meta.length, 4);
  const body = Buffer.concat([header, meta, ...payloads]);
  return Buffer.concat([body, crypto.createHash('sha256').update(body).digest()]);
}
function decode(buffer) {
  if (buffer.length < 42 || buffer.toString('ascii', 0, 4) !== 'KDB1') throw Error('Invalid KDB1 header');
  const end = buffer.length - 32;
  if (!crypto.timingSafeEqual(crypto.createHash('sha256').update(buffer.subarray(0, end)).digest(), buffer.subarray(end))) throw Error('KDB1 checksum mismatch');
  const start = 8 + buffer.readUInt32LE(4);
  if (start > end) throw Error('Invalid metadata length');
  const meta = JSON.parse(buffer.toString('utf8', 8, start));
  return Object.fromEntries(Object.entries(meta).map(([name, rows]) => [name, rows.map(row => {
    const width = TYPES[row.dtype];
    if (!width || !Number.isSafeInteger(row.offset) || !Number.isSafeInteger(row.length) ||
      row.offset < 0 || row.length < 0 || start + row.offset + row.length * width > end) throw Error('Invalid binary range');
    const data = Array.from({ length: row.length }, (_, i) => {
      const at = start + row.offset + i * width;
      return row.dtype === 'uint8' ? buffer.readUInt8(at) : row.dtype === 'float32' ? buffer.readFloatLE(at) : buffer.readDoubleLE(at);
    });
    return { id: row.id, object: row.object, dtype: row.dtype, data };
  })]));
}
class ObjectStore {
  constructor(contract, directory) {
    this.contract = contract;
    this.directory = directory;
    this.file = path.join(directory, 'tables.kdb');
    this.tables = Object.fromEntries(Object.entries(contract.tables).map(([name, def]) =>
      [name, (def.data || []).map(row => validateRow(row, contract.limits))]));
    fs.mkdirSync(directory, { recursive: true });
    // A single process owns the database; never silently overwrite another writer.
    this.lock = path.join(directory, 'writer.lock');
    try { this.lockFD = fs.openSync(this.lock, 'wx'); }
    catch (e) { if (e.code === 'EEXIST') throw Error('Database writer.lock exists; stop the other server before removing a stale lock'); throw e; }
    try {
      fs.writeSync(this.lockFD, String(process.pid));
      if (fs.existsSync(this.file)) {
        const persisted = decode(fs.readFileSync(this.file));
        for (const name of Object.keys(this.tables)) if (Object.hasOwn(persisted, name)) {
          this.tables[name] = persisted[name].map(row => validateRow(row, contract.limits));
        }
      } else this.commit(this.tables);
    } catch (e) { this.close(); throw e; }
  }
  close() {
    if (this.lockFD !== undefined) { fs.closeSync(this.lockFD); this.lockFD = undefined; fs.unlinkSync(this.lock); }
  }
  table(name) {
    if (!Object.hasOwn(this.tables, name)) fail(404, 'Unknown table');
    return this.tables[name];
  }
  list() {
    return Object.entries(this.tables).map(([name, rows]) => ({ name, count: rows.length,
      description: this.contract.tables[name].description,
      bytes: rows.reduce((n, r) => n + r.data.length * TYPES[r.dtype], 0) }));
  }
  get(name, id) {
    const row = this.table(name).find(r => r.id === id);
    if (!row) fail(404, 'Unknown row');
    return structuredClone(row);
  }
  commit(next) {
    const bytes = encode(next);
    if (bytes.length > this.contract.limits.maxDatabaseBytes) fail(413, 'Database size limit reached');
    const tmp = this.file + '.tmp';
    const fd = fs.openSync(tmp, 'w');
    try { fs.writeFileSync(fd, bytes); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
    try { fs.renameSync(tmp, this.file); } catch (e) { fs.rmSync(tmp, { force: true }); throw e; }
    this.tables = next;
  }
  put(name, input, createOnly = false) {
    const rows = this.table(name);
    const row = validateRow(input, this.contract.limits);
    const index = rows.findIndex(r => r.id === row.id);
    if (createOnly && index !== -1) fail(409, 'Row already exists');
    if (index === -1 && rows.length >= this.contract.limits.maxRowsPerTable) fail(413, 'Table is full');
    const next = rows.slice();
    if (index === -1) next.push(row); else next[index] = row;
    this.commit({ ...this.tables, [name]: next });
    return { created: index === -1, row: structuredClone(row) };
  }
  remove(name, id) {
    this.get(name, id);
    this.commit({ ...this.tables, [name]: this.table(name).filter(r => r.id !== id) });
  }
  binary(name) { return encode({ [name]: this.table(name) }); }
}
module.exports = { ObjectStore, encode, decode, validateRow };
