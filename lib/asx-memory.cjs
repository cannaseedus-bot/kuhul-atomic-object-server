'use strict';
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');

const SCHEMA = 'asx.memory.replay.v1';
const MAX_BYTES = 32 * 1024 * 1024;
let pendingWrite = Promise.resolve();

function userScope(userId) {
  return crypto.createHash('sha256').update(String(userId), 'utf8').digest('hex');
}

async function readMemory(filename) {
  try {
    const raw = await fs.readFile(filename, 'utf8');
    if (Buffer.byteLength(raw, 'utf8') > MAX_BYTES) throw Error('ASX memory file exceeds its configured 32 MiB limit');
    const value = JSON.parse(raw);
    if (value.schema !== SCHEMA || !Array.isArray(value.records)) throw Error('Unsupported or malformed .asx_memory.json');
    return value;
  } catch (error) {
    if (error.code === 'ENOENT') return { schema: SCHEMA, version: 1, records: [] };
    throw error;
  }
}

async function transact(filename, update) {
  let result;
  const operation = pendingWrite.then(async () => {
    const memory = await readMemory(filename);
    result = await update(memory);
    memory.updatedAt = new Date().toISOString();
    const serialized = JSON.stringify(memory, null, 2) + '\n';
    if (Buffer.byteLength(serialized, 'utf8') > MAX_BYTES) throw Error('ASX memory capacity reached (32 MiB)');
    await fs.mkdir(path.dirname(filename), { recursive: true });
    const temporary = filename + '.' + process.pid + '.' + crypto.randomUUID() + '.tmp';
    await fs.writeFile(temporary, serialized, { encoding: 'utf8', flag: 'wx' });
    try { await fs.rename(temporary, filename); }
    catch (error) { await fs.rm(temporary, { force: true }); throw error; }
  });
  pendingWrite = operation.catch(() => {});
  await operation;
  return result;
}

async function appendRecord(filename, record) {
  return transact(filename, memory => {
    if (memory.records.length >= 50000) throw Error('ASX memory record limit reached (50000)');
    memory.records.push(record);
    return record;
  });
}

async function listRecords(filename, predicate = () => true) {
  await pendingWrite;
  const memory = await readMemory(filename);
  return memory.records.filter(predicate);
}

async function getRecord(filename, id) {
  await pendingWrite;
  const memory = await readMemory(filename);
  return memory.records.find(record => record.id === id) || null;
}

module.exports = { SCHEMA, userScope, appendRecord, listRecords, getRecord };
