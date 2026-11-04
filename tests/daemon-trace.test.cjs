'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { createDaemon, TRACE_SCHEMA, PHASES } = require('../daemon.js');

test('reply trace records the canonical phase walk', () => {
  const reply = createDaemon().reply('HI');
  assert.equal(reply.trace.schema, TRACE_SCHEMA);
  assert.deepEqual(reply.trace.phases.map(phase => phase.phase), [...PHASES]);
  assert.equal(reply.trace.phases.find(phase => phase.phase === 'Yax').status, 'skipped');
  assert.equal(reply.trace.status, 'ok');
  assert.deepEqual(reply.trace.steps.map(step => step.seq), reply.trace.steps.map((_, index) => index + 1));
});

test('srai hop nests a child trace whose parent is the parent reply', () => {
  const reply = createDaemon().reply('HI');
  assert.equal(reply.trace.srai.length, 1);
  assert.equal(reply.trace.srai[0].target, 'HELLO');
  assert.equal(reply.trace.children.length, 1);
  assert.equal(reply.trace.children[0].parent, reply.trace.id);
  assert.equal(reply.trace.children[0].depth, 1);
});

test('normalization substitutions are recorded', () => {
  const reply = createDaemon().reply("what's up");
  assert.equal(reply.trace.input.substitutions[0].replace, 'what is');
  assert.match(reply.trace.input.normalized, /^WHAT IS/);
});

test('predicate writes and condition reads are recorded', () => {
  const daemon = createDaemon();
  const state = daemon.createSession();
  const write = daemon.reply('MY NAME IS Alex', state);
  assert.equal(write.trace.predicates.set[0].name, 'name');
  const read = daemon.reply('WHAT IS MY NAME', state);
  assert.equal(read.trace.conditions.length, 1);
  assert.equal(read.trace.predicates.get.length, 1);
});

test('wildcard captures are recorded by 1-based slot', () => {
  const reply = createDaemon().reply('cats and dogs');
  assert.deepEqual(reply.trace.captures.map(capture => capture.slot), [1, 2]);
  assert.equal(reply.trace.match.id, 'aiml.and');
});

test('admission and commit stay false for a pattern engine', () => {
  const reply = createDaemon().reply('HELLO');
  assert.deepEqual(reply.trace.admission, { owner: 'XCFE', admitted: false, reason: 'pattern_match_only' });
  assert.equal(reply.trace.commit.authorized, false);
  assert.equal(reply.trace.commit.phase, 'Xul');
});

test('trace can be disabled and leaves the reply shape intact', () => {
  const reply = createDaemon({ emitTrace: false }).reply('HI');
  assert.equal(reply.trace, undefined);
  assert.equal(reply.matched, 'aiml.hi');
});