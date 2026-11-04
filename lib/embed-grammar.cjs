'use strict';
const fs = require('node:fs');
const path = require('node:path');
const repoRoot = path.resolve(__dirname, '..');
const kitRoot = path.join(repoRoot, 'vendor', 'key-grammar-kit', 'data');
const manifestPath = path.join(repoRoot, 'manifest.json');
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
const read = p => JSON.parse(fs.readFileSync(path.join(kitRoot, p), 'utf8'));
const patterns = read('programs/micronauts/daemon-bot.json');
manifest.keyGrammar = {
  version: 'key-grammar-json/1',
  source: 'vendor/key-grammar-kit/data/manifest/css.manifest.json',
  authority: 'semantic manifest > graph realization > projection',
  address: 'key -> Book(key) -> declared neighborhood',
  css: read('manifest/css.manifest.json'),
  kuhul: read('manifest/kuhul.manifest.json'),
  aiml: read('manifest/aiml.manifest.json'),
  nodes: read('manifest/nodes.manifest.json'),
  grammar: {
    normalization: 'surface -> normalized key -> declared neighborhood',
    node: { required: ['key', 'phase'], phaseEnum: manifest.folds.phases },
    horizontalFold: 'same phase; distinct keys; weight * cos(0)',
    verticalFold: 'same key; ordered phase transition',
    actions: ['phase','fold','map','filter'],
    authority: 'declarations_only'
  }
};
manifest.aimlDaemon = {
  kind: 'kuhul.daemon-bot.xaiml-pattern-bank.v1', composition: 'KXML + AIML = XAIML',
  version: patterns['@version'], owner: patterns['@owner'],
  phase: patterns['@fold'], authority: patterns['@authority'], source: patterns['@source'],
  state: patterns['@state'],
  patterns: patterns['@patterns'],
  execution: { mode: 'pattern_match_only', arbitraryCode: false, network: false, tools: false,
    semanticCommit: false, promotion: false },
  feedActions: read('apps/daemon-bot-knowledge.json').feed_actions,
  rules: read('apps/daemon-bot-knowledge.json').rules
};
manifest.daemonApp = read('apps/daemon-bot.asx-app.json');
manifest.grammarSources = {
  aiml: 'vendor/key-grammar-kit/aiml.runtime-grammar.v5.ebnf',
  kxml: 'vendor/key-grammar-kit/data/programs/micronauts/daemon-bot.kxml',
  xaimlSchema: 'vendor/key-grammar-kit/data/schema/xaiml.xsd',
  daemon: 'vendor/key-grammar-kit/data/programs/micronauts/daemon-bot.json',
  css: 'vendor/key-grammar-kit/data/manifest/css.manifest.json'
};
manifest.xaiml = {
  ...(manifest.xaiml || {}),
  schema: 'kuhul.xaiml.source-contract.v1',
  definition: 'KXML + AIML = XAIML',
  sourcesAreLocalCopies: true
};
fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
