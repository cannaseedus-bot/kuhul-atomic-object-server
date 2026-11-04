const fs = require('node:fs');
const manifest = JSON.parse(fs.readFileSync('manifest.json', 'utf8'));
Object.assign(manifest, {
  name: "K'UHUL Atomic Object Server", short_name: "K'UHUL",
  description: 'ASX key grammar, fold inspection, JSON objects and binary data[] tables',
  version: '2.0.0', start_url: './', scope: './'
});
manifest.shortcuts = [{ name: 'Object tables', url: './#tables' }, { name: 'Runtime inventory', url: './#inventory' }];
manifest.api = {
  version: '1', base: '/api', authority: 'manifest.json',
  routes: [
    ['GET', '/api/manifest', 'manifest'],
    ['GET', '/api/inventory', 'inventory'],
    ['GET', '/api/tables', 'tables'],
    ['GET', '/api/tables/:table/binary', 'binary'],
    ['GET', '/api/tables/:table/rows', 'rows'],
    ['POST', '/api/tables/:table/rows', 'create'],
    ['GET', '/api/tables/:table/rows/:id', 'row'],
    ['PUT', '/api/tables/:table/rows/:id', 'put'],
    ['DELETE', '/api/tables/:table/rows/:id', 'remove']
  ].map(([method, path, action]) => ({ method, path, action })),
  adapters: [
    { method: 'POST', path: '/api/infer', adapter: 'lam.o' },
    { method: 'GET', path: '/api/health', adapter: 'lam.o' },
    { method: 'GET', path: '/api/models', adapter: 'lam.o' },
    { method: 'GET', path: '/api/caps', adapter: 'lam.o' }
  ]
};
manifest.database = {
  id: 'kuhul-atomic', version: 1, storage: 'server-kdb1', byteOrder: 'little-endian',
  format: 'KDB1 + u32 metadata length + UTF-8 metadata + packed data[] + SHA-256',
  dtypes: ['uint8', 'float32', 'float64'],
  limits: { maxRowsPerTable: 10000, maxValuesPerRow: 65536, maxObjectBytes: 65536, maxDatabaseBytes: 67108864 },
  tables: {
    objects: { description: 'Symbolic JSON objects addressed by row id', data: [
      { id: 'welcome', object: { key: '⟁WELCOME', phase: 'Pop', message: 'JSON declares. Adapters execute. ASX renders.' }, dtype: 'uint8', data: [] }
    ] },
    tensors: { description: 'Typed numeric lanes and fold arc samples', data: [
      { id: 'phase-cosines', object: { source: 'Pop', formula: 'cos(j * pi / 3)', phase: 'Sek' }, dtype: 'float64', data: [1, 0.5, -0.5, -1, -0.5, 0.5] }
    ] },
    fields: { description: 'Field configuration objects and numeric data', data: [
      { id: 'wind', object: JSON.parse(fs.readFileSync('field/wind_field_spec.json', 'utf8')), dtype: 'float32', data: [] },
      { id: 'attraction-well', object: JSON.parse(fs.readFileSync('field/attraction_well_spec.json', 'utf8')), dtype: 'float32', data: [] }
    ] },
    events: { description: 'User-managed event objects and numeric samples', data: [] }
  }
};
manifest.folds = {
  phases: ['Pop', 'Wo', 'Yax', 'Sek', "Ch'en", 'Xul'],
  angleStep: Math.PI / 3,
  effectiveArc: 'weight * cos(targetAngle - sourceAngle)',
  horizontal: 'Different nodes at one shared phase',
  vertical: 'One node through Pop → Wo → Yax → Sek → Ch’en → Xul'
};
manifest.asx = {
  grammar: 'asx-key-grammar/1',
  root: '⟁PAGE',
  actions: { 'tables.refresh': 'refresh', 'row.load': 'load', 'row.save': 'save', 'row.delete': 'remove',
    'table.export': 'download', 'fold.inspect': 'fold', 'model.infer': 'infer', 'manifest.inspect': 'inspect' }
};
manifest.runtime = { adapter: 'node-express', kernel: null, field: { entry: 'field/main.py', mode: 'python-cli' },
  note: 'JavaScript compatibility adapter; no sw.khl VM is present in this stack.' };
manifest.shell = { assets: ['./', './index.html', './atomic.css', './manifest.json', './stack-inventory.json',
  './lib/atomic-app.js', './lib/kuhul-client.js', './lib/kuhul-xjson.js', './lib/scxq2.js'] };
fs.writeFileSync('manifest.json', JSON.stringify(manifest, null, 2) + '\n');
let server = fs.readFileSync('orchestrator.js', 'utf8');
server = server.replace('const app = express();', `const path = require("node:path");
const fs = require("node:fs");
const manifest = require("./manifest.json");
const { mountObjectAPI } = require("./lib/object-api.cjs");
const app = express();`);
server = server.replace('app.use(cors());', '// The local API accepts same-origin browser clients.');
server = server.replace("app.use(express.json({ limit: '10mb' }));", "app.use(express.json({ limit: '2mb' }));\nconst objectStore = mountObjectAPI(app, manifest, __dirname);");
server = server.replace('streaming: true,', 'streaming: false,');
server = server.replace('if (!infer["@prompt"] && !infer["@prompt"].trim())', 'if (typeof infer["@prompt"] !== "string" || !infer["@prompt"].trim())');
server = server.replace('if (body["@infer"])', 'if (body && body["@infer"])');
server = server.replace('// Convert from simple format', 'body = body || {};\n  // Convert from simple format');
server = server.replace('app.use(express.static(__dirname));', `// Expose only declared public assets; database and server sources stay private.
app.use("/api", (req, res) => res.status(404).json({ error: "Unknown API route" }));
app.use((error, req, res, next) => {
  console.error(error.message);
  const status = error.status || 500;
  res.status(status).json({ error: status < 500 ? error.message : "Internal server error" });
});
const publicFiles = new Set(["index.html", "atomic.css", "styles.css", "manifest.json", "stack-inventory.json",
  "KHANARY-ATOMIC-MASTER-GUIDE.html", "kuhul_atomic_horizontal_vertical_folds_guide.html", "asx-key-grammar.html", "sw.js"]);
app.get("*", (req, res, next) => {
  const relative = req.path === "/" ? "index.html" : req.path.slice(1);
  const library = /^lib\\/[a-zA-Z0-9._-]+\\.(js|json)$/.test(relative);
  const icon = /^icons\\/[a-zA-Z0-9._-]+\\.(png|svg|ico)$/.test(relative);
  if (!publicFiles.has(relative) && !library && !icon) return res.status(404).send("Not found");
  if (relative === "sw.js") res.set("Cache-Control", "no-cache");
  res.sendFile(path.join(__dirname, relative));
});`);
server = server.replace('app.listen(CONFIG.port, () => {', 'if (require.main === module) {\nconst server = app.listen(CONFIG.port, process.env.HOST || "127.0.0.1", () => {');
server = server.replace('module.exports = app;', `process.once("exit", () => objectStore.close());
for (const signal of ["SIGINT", "SIGTERM"]) process.once(signal, () => server.close(() => { objectStore.close(); process.exit(0); }));
}
module.exports = app;`);
fs.writeFileSync('orchestrator.js', server);
let client = fs.readFileSync('lib/kuhul-client.js', 'utf8');
client = client.replace("orchestratorUrl: 'http://localhost:61683/api/infer'", "orchestratorUrl: '/api/infer'")
 .replace("healthUrl: 'http://localhost:61683/api/health'", "healthUrl: '/api/health'")
 .replace("ollamaTagsUrl: 'http://localhost:11434/api/tags'", "ollamaTagsUrl: '/api/models'")
 .replace('fallbackToOllama: true', 'fallbackToOllama: false');
client = client.replace('if (global.XJSON && global.XJSON.isInferRequest(xjsonOrOptions))', "if (xjsonOrOptions && xjsonOrOptions['@infer'])");
client = client.replace('if (global.XJSON && global.XJSON.isCompletion(response))', "if (response && response['@completion'])")
 .replace('} else if (global.XJSON && global.XJSON.isError(response))', "} else if (response && response['@error'])");
client = client.replace(/    _fetchWithTimeout: function\(url, options, timeout\) \{[\s\S]*?\n    \},/, `    _fetchWithTimeout: async function(url, options, timeout) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      try { return await fetch(url, { ...options, signal: controller.signal }); }
      finally { clearTimeout(timer); }
    },`);
fs.writeFileSync('lib/kuhul-client.js', client);
let main = fs.readFileSync('field/main.py', 'utf8').replace('PiWorldSpec, PiBody, PiConstraint', 'PiWorldSpec, PiBody, PiConstraint, PiEvent');
main = main.replace(/kernel.enqueue_event\(\{[\s\S]*?\} if isinstance\(\{\}, dict\) else None\)/, 'kernel.enqueue_event(PiEvent(type="impulse", target=bodies[0].id, payload={"impulse": [0, 2, 0]}))');
fs.writeFileSync('field/main.py', main);
let kernel = fs.readFileSync('field/pi_kernel.py', 'utf8');
kernel = kernel.replace('        h = self.step_seal()', '        previous_hash = self.prev_hash\n        h = self.step_seal()').replace('prev_hash=self.prev_hash', 'prev_hash=previous_hash');
fs.writeFileSync('field/pi_kernel.py', kernel);
console.log('Manifest, orchestrator, client and field integration updated');
