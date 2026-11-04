#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const parser = require('../micronaut/xaiml/daemon-bot-parser.cjs');

async function readInput(args) {
  const fileIndex = args.indexOf('--file');
  if (fileIndex >= 0) {
    const file = args[fileIndex + 1];
    if (!file) throw new Error('--file requires a path');
    return fs.readFileSync(path.resolve(file), 'utf8');
  }
  if (!process.stdin.isTTY) {
    const chunks = [];
    for await (const chunk of process.stdin) chunks.push(chunk);
    if (chunks.length) return Buffer.concat(chunks).toString('utf8');
  }
  const source = args.filter((value, index) => value !== '--file' && args[index - 1] !== '--file').join(' ');
  if (!source) throw new Error('Provide a source string or --file <path>');
  return source;
}

readInput(process.argv.slice(2)).then(source => {
  const result = parser.parse(source);
  process.stdout.write(JSON.stringify(result, null, 2) + '\n');
}).catch(error => {
  process.stderr.write(`ASX parse failed: ${error.message}\n`);
  process.exitCode = 1;
});
