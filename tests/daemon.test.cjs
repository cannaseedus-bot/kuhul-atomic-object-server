'use strict';
const {test}=require('node:test'),assert=require('node:assert/strict');
const {createDaemon,normalize,glob}=require('../daemon.js');
const manifest=require('../manifest.json');
test('normalization, wildcard and multi-capture matching',()=>{
 assert.equal(normalize("what's u doing?"),'WHAT IS YOU DOING');
 assert.deepEqual(glob('* AND *','cats and dogs'),['CATS','DOGS']);
 assert.deepEqual(glob('WHAT ABOUT ^','WHAT ABOUT'),[]);
});
test('starter AIML rules cover synonyms, wildcard passthrough, bot keys and safe fallback',()=>{
 const bot=createDaemon({manifest});const s=bot.createSession();
 assert.match(bot.reply('hi',s).text,/Daemon Bot/);
 assert.match(bot.reply('what about css',s).text,/css/i);
 assert.match(bot.reply('who made you',s).text,/K'UHUL/);
 assert.match(bot.reply('<img src=x onerror=alert(1)>',s).text,/no rule/i);
});
test('condition, random, silent session memory and topic routing',()=>{
 const bot=createDaemon({manifest,random:()=>0});const s=bot.createSession();
 assert.match(bot.reply('what was my last topic',s).text,/No topic stored/);
 assert.match(bot.reply('remember atomic folds',s).text,/Stored/);
 assert.match(bot.reply('what was my last topic',s).text,/ATOMIC FOLDS/);
 bot.reply('i am happy and i like geometry',s);
 assert.deepEqual([s.predicates.mood,s.predicates.likes],['HAPPY','GEOMETRY']);
 assert.match(bot.reply('roll',s).text,/One/);
 bot.reply('switch to coder',s);assert.equal(s.topic,'coder');
 assert.match(bot.reply('hello',s).text,/Coder mode/);
 assert.match(bot.reply('what mode am i in',s).text,/coder mode/);
 bot.reply('switch to assistant',s);assert.match(bot.reply('hello',s).text,/Assistant mode/);
 bot.reply('switch to idle',s);assert.match(bot.reply('hello',s).text,/daemon bot/i);
});
test('manifest sections and phase metadata are explicitly addressable',()=>{
 assert.equal(manifest.aimlDaemon.sectionId,'sec.runtime.daemon-bot.v1');
 assert.equal(manifest.keyGrammar.sectionId,'sec.grammar.key-grammar.v1');
 assert.equal(manifest.aimlDaemonExtensions.sectionId,'sec.aiml.extended-condition-random-memory-topics.v1');
 assert.ok(manifest.aimlDaemonExtensions.patterns.every(p=>p.sectionId&&manifest.folds.phases.includes(p.phase||'Wo')));
});
test('reply API takes supplied session and rejects empty input',async()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'daemon-api-'));process.env.KUHUL_DATA_DIR=dir;
 const app=require('../orchestrator.js'),server=app.listen(0,'127.0.0.1');await new Promise(r=>server.once('listening',r));
 try{
  const base='http://127.0.0.1:'+server.address().port;
  let response=await fetch(base+'/api/daemon/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'switch to coder'})});
  assert.equal(response.status,200);let data=await response.json();assert.equal(data.state.topic,'coder');
  response=await fetch(base+'/api/daemon/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'hello',state:data.state})});
  assert.match((await response.json()).text,/Coder mode/);
  assert.equal((await fetch(base+'/api/daemon/patterns')).status,200);
  assert.equal((await fetch(base+'/api/daemon/reply',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'})).status,400);
 }finally{await new Promise(r=>server.close(r));app.locals.objectStore.close();fs.rmSync(dir,{recursive:true,force:true});}
});
