'use strict';
const fs=require('node:fs'), manifest=JSON.parse(fs.readFileSync('manifest.json','utf8'));
const base=manifest.aimlDaemon.patterns;
const add=(id,pattern,nodes,extra={})=>({id,pattern,template:nodes,...extra});
const text=value=>({tag:'text',value});
const srai=target=>({tag:'srai',children:[text(target)]});
const list=(value,nodes)=>({value,children:nodes});
manifest.aimlDaemon.sectionId='sec.aiml.daemon-bot.v1';
manifest.aimlDaemonExtensions={
 sectionId:'sec.aiml.extended-condition-random-memory-topics.v1',
 title:'Extended AIML: condition, random, think/set memory and topic modes',
 schema:'aiml-manifest-ast/1',
 semantics:{condition:'first exact predicate value, then bare li default',random:'uniform among li',think:'execute set nodes silently',set:'session-scoped predicate; topic changes active category scope',srai:'bounded recursive rematch, maximum depth 16'},
 patternOrder:['hello','coder.hello','assistant.hello','fallback.mode'],
 patterns:[
 add('what.condition','WHAT IS CONDITION',[text('<condition> branches on a predicate. Use named value branches with a bare default, or compare one var and value.')]),
 add('condition.alias','CONDITION',[srai('WHAT IS CONDITION')]),
 add('example.condition','EXAMPLE CONDITION',[text('<condition name="mood"><li value="happy">Glad to hear it.</li><li>I do not know your mood.</li></condition> Try I AM HAPPY then HOW AM I.')]),
 add('condition.example.alias','SHOW ME CONDITION',[srai('EXAMPLE CONDITION')]),
 add('mode.query','WHAT MODE AM I IN',[{tag:'condition',name:'mode',items:[list('assistant',[text('You are in assistant mode.')]),list('coder',[text('You are in coder mode.')]),list('idle',[text('You are in the default idle mode.')]),list('',[text('Mode is unset.')]),list(undefined,[text('Mode is unset.')])]}]),
 add('what.random','WHAT IS RANDOM',[text('<random> picks one li response for each match.')]),
 add('random.alias','RANDOM',[srai('WHAT IS RANDOM')]),
 add('example.random','EXAMPLE RANDOM',[text('<random><li>One.</li><li>Two.</li><li>Three.</li></random> Ask ROLL.')]),
 add('random.example.alias','SHOW ME RANDOM',[srai('EXAMPLE RANDOM')]),
 add('roll','ROLL',[{tag:'random',items:[[text('One.')],[text('Two.')],[text('Three.')]]}]),
 add('roll.capture','ROLL *',[text('Rolling '),{tag:'star'},text(': '),{tag:'random',items:[[text('One.')],[text('Two.')],[text('Three.')]]}]),
 add('greet.random','GREET RANDOM',[{tag:'random',items:[[text('Hello. I am '),{tag:'bot',name:'name'},text('.')],[text('Hi. '),{tag:'bot',name:'name'},text(' here.')],[text('Greetings from the background process.')]]}]),
 add('what.think','WHAT IS THINK',[text('<think> executes its contents silently; use it for session <set> memory without printing the stored value.')]),
 add('think.alias','THINK',[srai('WHAT IS THINK')]),
 add('example.think','EXAMPLE THINK',[text('<think><set name="lastTopic"><star/></set></think> stores a value without echoing it.')]),
 add('think.example.alias','SHOW ME THINK',[srai('EXAMPLE THINK')]),
 add('remember','REMEMBER *',[{tag:'think',children:[{tag:'set',name:'lastTopic',children:[{tag:'star'}]}]},text('Stored. Ask WHAT WAS MY LAST TOPIC.')]),
 add('last.topic','WHAT WAS MY LAST TOPIC',[{tag:'condition',name:'lastTopic',items:[list('',[text('No topic stored yet. Try: REMEMBER AIML.')]),list(undefined,[text('Your last topic was '),{tag:'get',name:'lastTopic'},text('.')])]}]),
 add('mood.and.likes','I AM * AND I LIKE *',[{tag:'think',children:[{tag:'set',name:'mood',children:[{tag:'star',index:1}]},{tag:'set',name:'likes',children:[{tag:'star',index:2}]}]},text('Noted: mood '),{tag:'get',name:'mood'},text(', likes '),{tag:'get',name:'likes'},text('.')]),
 add('what.topic','WHAT IS TOPIC',[text('<topic name="..."> scopes categories. SWITCH TO CODER or SWITCH TO ASSISTANT changes the active topic.')]),
 add('topic.alias','TOPIC',[srai('WHAT IS TOPIC')]),
 add('example.topic','EXAMPLE TOPIC',[text('Try SWITCH TO CODER, then HELLO. SWITCH TO ASSISTANT changes the scoped greeting.')]),
 add('topic.example.alias','SHOW ME TOPIC',[srai('EXAMPLE TOPIC')]),
 ...[['coder','Coder mode on. I answer in AIML XML.'],['assistant','Assistant mode on. I explain AIML in plain language.'],['idle','Idle mode. I answer generic categories.']].map(([mode,message])=>add('switch.'+mode,'SWITCH TO '+mode.toUpperCase(),[{tag:'topic',value:mode},{tag:'think',children:[{tag:'set',name:'mode',children:[text(mode)]}]},text(message)])),
 add('coder.hello','HELLO',[text('<category><pattern>HELLO</pattern><template>Hi.</template></category> Coder mode: here is the XML for a greeting.')],{topic:'coder'}),
 add('coder.category','WRITE A CATEGORY',[text('<category><pattern>HELLO</pattern><template>Hi.</template></category>')],{topic:'coder'}),
 add('coder.wildcard','WRITE A WILDCARD RULE',[text('<category><pattern>TELL ME ABOUT *</pattern><template>You asked about <star/>.</template></category>')],{topic:'coder'}),
 add('coder.srai','WRITE AN SRAI RULE',[text('<category><pattern>HI</pattern><template><srai>HELLO</srai></template></category>')],{topic:'coder'}),
 add('coder.key','WRITE A BOT KEY',[text('<bot name="name"/> reads the bot name key.')],{topic:'coder'}),
 add('assistant.hello','HELLO',[text('Assistant mode here. Ask WHAT IS A PATTERN, TEMPLATE, WILDCARD, SRAI, or KEY.')],{topic:'assistant'}),
 add('assistant.explain','EXPLAIN *',[{tag:'srai',children:[{tag:'star'}]}],{topic:'assistant'}),
 add('log.greeting','LOG GREETING',[{tag:'think',children:[{tag:'set',name:'greeted',children:[text('yes')]}]},text('Greeting logged.')]),
 add('greeted.query','DID I GREET YOU',[{tag:'condition',name:'greeted',items:[list('yes',[text('Yes, you greeted me this session.')]),list(undefined,[text('No greeting recorded yet. Try LOG GREETING.')])]}]),
 add('mood.check','MOOD CHECK',[{tag:'condition',name:'mood',items:[list('happy',[{tag:'random',items:[[text('Happy is a good daemon state.')],[text('Glad the process is content.')]]}]),list('tired',[text('A tired daemon still answers. Rest well.')]),list(undefined,[{tag:'random',items:[[text('I have no mood on file. Try I AM HAPPY.')],[text('Set a mood first: I AM HAPPY.')]]}])]}]),
 add('mode.alias','MODE',[srai('WHAT MODE AM I IN')]),
 add('fallback.mode','*',[{tag:'condition',name:'mode',items:[list('coder',[text('No coder rule for: '),{tag:'star'},text('. Try WRITE A CATEGORY or SWITCH TO ASSISTANT.')]),list('assistant',[text('I do not have an explanation rule for '),{tag:'star'},text('. Try EXPLAIN PATTERNS or SWITCH TO CODER.')]),list(undefined,[text('I do not have a rule for '),{tag:'star'},text('. Ask HELP or SWITCH TO ASSISTANT.')])]}])
 ]
};
manifest.aimlDaemon.session={persistence:'in-memory',scope:'conversation',predicates:['name','mood','likes','lastTopic','greeted','mode'],topic:'conversation-scoped',that:'last-response'};
manifest.aimlDaemon.permissions={network:'none',tools:false,arbitraryCode:false,semanticCommit:false};
fs.writeFileSync('manifest.json',JSON.stringify(manifest,null,2)+'\n');
