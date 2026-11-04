'use strict';
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const roles = {
  'orchestrator.js': ['server', 'Express host; manifest routes; lam.o inference adapter; public asset allowlist'],
  'manifest.json': ['authority', 'PWA metadata, route registry, table schemas and seeds, fold geometry, ASX actions'],
  'sw.js': ['carrier', 'Manifest shell cache; network-only API transport; legacy carrier messages'],
  'index.html': ['ui', 'ASX keyed object editor, fold inspector, route and inventory browser'],
  'atomic.css': ['ui', 'Canonical ASX token block and responsive console layout'],
  'styles.css': ['ui', 'Existing model-runner styles; retained for compatibility'],
  'lib/object-api.cjs': ['server', 'Binds declared routes to object storage operations'],
  'lib/object-store.cjs': ['storage', 'KDB1 checksummed binary codec and atomic single-writer persistence'],
  'lib/atomic-app.js': ['ui', 'Manifest-resolved ASX action dispatch and DOM projection'],
  'lib/kuhul-client.js': ['adapter', 'Same-origin XJSON inference client; abortable timeout; explicit fallback'],
  'lib/kuhul-xjson.js': ['contract', 'XJSON request, completion and error helpers'],
  'lib/scxq2.js': ['adapter', 'SCXQ2 fingerprints and IR utilities; distinct from KDB1 binary format'],
  'lib/kuhul-runtime.js': ['optional', 'Capability-gated browser modules and canvas devices; not booted by console'],
  'lib/kuhul-packs.js': ['optional', 'Pack capability declarations and seal ribbon'],
  'lib/ghost-kuhul-adapter.js': ['optional', 'Parent iframe RPC and canvas session adapter'],
  'lib/kuhul-sandbox-bridge.js': ['optional', 'Sandbox-side capability and message bridge'],
  'lib/ghost.kuhul.js': ['optional', 'Physical intent bridge requiring an external compatible JS kernel'],
  'lib/pi-goat.js': ['optional', 'Polyglot parsing, runtime dispatch and pack adapter'],
  'lib/pi-goat-api.js': ['optional', 'REST, XJSON, mesh and dot-notation API language adapter'],
  'field/main.py': ['field', 'Python bundle CLI and deterministic tick JSONL output; typed PiEvent input'],
  'field/pi_kernel.py': ['field', 'Field forces, symbolic impulses, constraints, integration, projection, hash chain'],
  'field/pi_fields.py': ['field', 'Active wind and attraction-well force compositor'],
  'field/pi_constraints.py': ['field', 'Spring constraints'],
  'field/pi_types.py': ['field', 'World, body, event, constraint and projection dataclasses'],
  'field/pi_hash.py': ['field', 'Canonical snapshots and SHA-256'],
  'field/pi_symbolic.py': ['field', 'Symbolic tree to kernel-owned event intent extraction'],
  'field/field_composition.py': ['legacy-field', 'Alternate standalone field compositor; not imported by PiKernel']
};
const candidates = ['index.html', 'manifest.json', 'orchestrator.js', 'sw.js', 'atomic.css', 'styles.css'];
for (const dir of ['lib', 'field']) {
  for (const name of fs.readdirSync(path.join(root, dir))) {
    if (/\.(js|cjs|py|json)$/.test(name)) candidates.push(dir + '/' + name);
  }
}
const files = candidates.sort().map(file => {
  const bytes = fs.readFileSync(path.join(root, file));
  const [plane, role] = roles[file] || [file.startsWith('field/') ? 'field-contract' : 'contract', 'JSON schema or field specification'];
  return { path: file, plane, role, bytes: bytes.length, sha256: crypto.createHash('sha256').update(bytes).digest('hex') };
});
const inventory = { version: 1, generatedAt: new Date().toISOString(), files,
  boundaries: ['Node executes declared REST actions; no sw.khl interpreter is present.',
    'Python field CLI remains independent; field specs are seeded into the fields table.',
    'Optional browser modules are inventoried but not automatically executed.',
    'Only shell assets are cached; API requests require the server.'] };
fs.writeFileSync(path.join(root, 'stack-inventory.json'), JSON.stringify(inventory, null, 2) + '\n');
console.log('Inventoried ' + files.length + ' stack files');
