const { test } = require('node:test');
const assert = require('node:assert');
const { createDaemon } = require('../daemon.js');

const manifest = {
  aimlDaemon: { patterns: [
    { id: 'q', pattern: 'ASK', template: [{ tag: 'text', value: 'the answer is blue' }] },
    { id: 'follow', pattern: '*', that: 'THE ANSWER IS *', template: [{ tag: 'text', value: 'follow up on blue' }] },
    { id: 'gp', pattern: 'GENDER PAIR', template: [{ tag: 'gender', children: [{ tag: 'text', value: 'the man likes the woman' }] }] },
    { id: 'pp', pattern: 'PERSON PAIR', template: [{ tag: 'person', children: [{ tag: 'text', value: 'we are ourselves' }] }] },
    { id: 'g', pattern: 'GENDER TEST', template: [{ tag: 'gender', children: [{ tag: 'text', value: 'he likes her' }] }] },
    { id: 'p', pattern: 'PERSON TEST', template: [{ tag: 'person', children: [{ tag: 'text', value: 'I am fine' }] }] },
    { id: 'p2', pattern: 'PERSON2 TEST', template: [{ tag: 'person2', children: [{ tag: 'text', value: 'I am fine' }] }] },
    { id: 'l', pattern: 'LEARN TEST', template: [{ tag: 'learn', children: [{ tag: 'text', value: 'ignore' }] }, { tag: 'text', value: 'done' }] },
  ] },
  aimlDaemonExtensions: { patterns: [] },
};

test('gender reflection swaps pronouns', () => {
  const bot = createDaemon({ manifest });
  assert.strictEqual(bot.reply('gender test', bot.createSession()).text, 'she likes him');
});

test('person reflection swaps first/second person', () => {
  const bot = createDaemon({ manifest });
  assert.strictEqual(bot.reply('person test', bot.createSession()).text, 'you are fine');
});

test('person2 reflection swaps to third person', () => {
  const bot = createDaemon({ manifest });
  assert.strictEqual(bot.reply('person2 test', bot.createSession()).text, 'he is fine');
});

test('learn is a silent no-op', () => {
  const bot = createDaemon({ manifest });
  assert.strictEqual(bot.reply('learn test', bot.createSession()).text, 'done');
});

test('that context gates a follow-up pattern', () => {
  const bot = createDaemon({ manifest });
  const s = bot.createSession();
  assert.strictEqual(bot.reply('ask', s).text, 'the answer is blue');
  assert.strictEqual(bot.reply('anything', s).text, 'follow up on blue');
});

test('fuller reflection maps cover plurals and gender pairs', () => {
  const bot = createDaemon({ manifest });
  assert.strictEqual(bot.reply('gender pair', bot.createSession()).text, 'the woman likes the man');
  assert.strictEqual(bot.reply('person pair', bot.createSession()).text, 'you are yourselves');
});

test('operator node reports unsupported SRAI operator', () => {
  const m2 = { aimlDaemon: { patterns: [{ id: 'o', pattern: 'OP', template: [{ tag: 'ELIZA-1:CAUSE' }] }] }, aimlDaemonExtensions: { patterns: [] } };
  const bot = createDaemon({ manifest: m2 });
  assert.throws(() => bot.reply('op', bot.createSession()), /Unsupported SRAI operator: ELIZA-1:CAUSE/);
});
