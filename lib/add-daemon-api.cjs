'use strict';
const fs=require('node:fs');
const file='manifest.json', m=JSON.parse(fs.readFileSync(file,'utf8'));
const section=(id,title,body)=>({sectionId:id,title,...body});
m.aimlDaemon=section('sec.runtime.daemon-bot.v1','Daemon Bot AIML reply engine',m.aimlDaemon);
m.keyGrammar=section('sec.grammar.key-grammar.v1','CSS-style key grammar and K\'UHUL phases',m.keyGrammar);
m.aimlDaemonExtensions=section(m.aimlDaemonExtensions.sectionId,m.aimlDaemonExtensions.title,m.aimlDaemonExtensions);
m.aimlDaemonExtensions.patterns=m.aimlDaemonExtensions.patterns.map((p,i)=>({...p,sectionId:'sec.aiml.rule.'+String(i+1).padStart(3,'0')}));
m.api.routes.push(
 {method:'POST',path:'/api/daemon/reply',action:'daemonReply'},
 {method:'GET',path:'/api/daemon/patterns',action:'daemonPatterns'}
);
fs.writeFileSync(file,JSON.stringify(m,null,2)+'\n');
let api=fs.readFileSync('lib/object-api.cjs','utf8');
api=api.replace("const { ObjectStore } = require('./object-store.cjs');","const { ObjectStore } = require('./object-store.cjs');\nconst { createDaemon } = require('../daemon.js');");
api=api.replace("const handlers = {","const daemon = createDaemon({ manifest });\n  const handlers = {\n    daemonReply: (req, res) => {\n      if (typeof req.body?.text !== 'string' || !req.body.text.trim()) return res.status(400).json({ error: 'text is required' });\n      const state = req.body.state && typeof req.body.state === 'object' ? req.body.state : daemon.createSession();\n      res.json({ ...daemon.reply(req.body.text, state), state });\n    },\n    daemonPatterns: (_req, res) => res.json({ ...daemon.inspect(), patterns: manifest.aimlDaemon.patterns, extensions: manifest.aimlDaemonExtensions }),");
fs.writeFileSync('lib/object-api.cjs',api);
let server=fs.readFileSync('orchestrator.js','utf8').replace('"atomic.css", "styles.css", "manifest.json"', '"daemon.js", "atomic.css", "styles.css", "manifest.json"');
fs.writeFileSync('orchestrator.js',server);
let pkg=JSON.parse(fs.readFileSync('package.json','utf8'));pkg.scripts.inventory='node tools/inventory.cjs';fs.writeFileSync('package.json',JSON.stringify(pkg,null,2)+'\n');
