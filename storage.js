'use strict';
const isNode=typeof window==='undefined';
async function readAll(){if(isNode){const fs=await import('node:fs/promises');try{return JSON.parse(await fs.readFile('./learned-rules.json','utf8'));}catch{return{version:1,users:{}};}}const raw=localStorage.getItem('daemon-bot:learned-rules');return raw?JSON.parse(raw):{version:1,users:{}};}
async function writeAll(data){if(isNode){const fs=await import('node:fs/promises');await fs.writeFile('./learned-rules.json',JSON.stringify(data,null,2)+'\n');return;}localStorage.setItem('daemon-bot:learned-rules',JSON.stringify(data));}
async function saveRule(userId,rule){const data=await readAll(),user=(data.users[userId]||= {createdAt:new Date().toISOString(),rules:[]});user.rules.push({id:'rule_'+String(user.rules.length+1).padStart(3,'0'),pattern:rule.pattern,template:rule.template,hasWildcard:Boolean(rule.hasWildcard),taughtAt:new Date().toISOString()});await writeAll(data);return user.rules[user.rules.length-1];}
async function loadRules(userId){const data=await readAll();return data.users[userId]?.rules||[];}
module.exports={saveRule,loadRules};
