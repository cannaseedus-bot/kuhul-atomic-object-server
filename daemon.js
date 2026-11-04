'use strict';
const DEFAULT_MANIFEST = require('./manifest.json');
const fs = require('node:fs');
const path = require('node:path');
const MAX_DEPTH = 16;

// Reply trace: observation only. Contract: data/grammar/daemon-bot.trace.contracts.json
const TRACE_SCHEMA = 'daemon-bot.reply-trace.v1';
const PHASES = Object.freeze(['Pop', 'Wo', 'Yax', 'Sek', "Ch'en", 'Xul']);
const TRACE_STATUS = Object.freeze({
  OK: 'ok',
  NO_MATCH: 'no_match',
  RECURSION_LIMIT: 'recursion_limit',
  RENDER_ERROR: 'render_error'
});
const TRACE_SUBSTITUTIONS = Object.freeze([
  [/\bwhat's\b/gi, 'what is'],
  [/\bwhats\b/gi, 'what is'],
  [/\bwho's\b/gi, 'who is'],
  [/\bu\b/gi, 'you'],
  [/\bur\b/gi, 'your'],
  [/\bpls\b/gi, 'please']
]);

function normalizeWithTrace(value) {
  const raw = String(value ?? '');
  const substitutions = TRACE_SUBSTITUTIONS
    .filter(([pattern]) => { pattern.lastIndex = 0; const fired = pattern.test(raw); pattern.lastIndex = 0; return fired; })
    .map(([pattern, replace]) => ({ find: pattern.source, replace }));
  return { raw, normalized: normalize(raw), substitutions };
}

function createTrace(id, parent, depth, input) {
  return {
    schema: TRACE_SCHEMA,
    id,
    parent,
    depth,
    input: { raw: String(input ?? ''), normalized: '', substitutions: [] },
    phases: PHASES.map(phase => ({ phase, status: 'not_reached', detail: null })),
    match: null,
    captures: [],
    srai: [],
    children: [],
    xcfe: [],
    predicates: { get: [], set: [] },
    conditions: [],
    mode: { family: 'behavior', value: null, narrows_only: true },
    admission: { owner: 'XCFE', admitted: false, reason: 'pattern_match_only' },
    commit: { authorized: false, phase: 'Xul', reason: 'trace_is_observation_only' },
    status: TRACE_STATUS.OK,
    steps: []
  };
}

function markPhase(trace, phase, status, detail = null) {
  const record = trace.phases.find(item => item.phase === phase);
  if (record) { record.status = status; record.detail = detail; }
  trace.steps.push({ seq: trace.steps.length + 1, phase, event: status, detail });
}
const normalize = value => String(value ?? '').normalize('NFKC').replace(/[’']/g, "'")
  .replace(/\bwhat's\b/gi, 'what is').replace(/\bwhats\b/gi, 'what is')
  .replace(/\bwho's\b/gi, 'who is').replace(/\bu\b/gi, 'you')
  .replace(/\bur\b/gi, 'your').replace(/\bpls\b/gi, 'please')
  .toUpperCase().replace(/[^\p{L}\p{N}*_^'-]+/gu, ' ').trim().replace(/\s+/g, ' ');
function glob(pattern, input) {
  const p = normalize(pattern).split(' ').filter(Boolean), words = normalize(input).split(' ').filter(Boolean);
  const memo = new Map();
  function walk(i,j,captures) {
    const key = i + ':' + j;
    if (memo.has(key)) return null;
    if (i === p.length) return j === words.length ? captures : null;
    if (p[i] === '*' || p[i] === '^') {
      const min = p[i] === '*' ? 1 : 0;
      for (let end=words.length; end>=j+min; end--) {
        const next = end > j ? [...captures, words.slice(j,end).join(' ')] : captures;
        const result=walk(i+1,end,next);
        if (result) return result;
      }
      memo.set(key,true); return null;
    }
    return j < words.length && (p[i] === '_' || p[i] === words[j]) ? walk(i+1,j+1,captures) : null;
  }
  return walk(0,0,[]);
}
function loadXaimlPatterns(manifest, root=__dirname) {
  const sources = manifest.aimlDaemonExtensions?.xaimlSources || [];
  if (!Array.isArray(sources)) throw Error('aimlDaemonExtensions.xaimlSources must be an array');
  const rootPath = path.resolve(root);
  const patterns = [];
  for (const source of sources) {
    if (typeof source !== 'string' || path.isAbsolute(source)) throw Error('XAIML source must be a relative repository path');
    const filename = path.resolve(rootPath, source);
    if (!filename.startsWith(rootPath + path.sep)) throw Error('XAIML source escapes repository root: ' + source);
    const stat = fs.statSync(filename);
    if (!stat.isFile() || stat.size > 1024 * 1024) throw Error('XAIML source must be a file under 1 MiB: ' + source);
    const bank = JSON.parse(fs.readFileSync(filename, 'utf8'));
    if (bank.format !== 'kuhul.xaiml.pattern-bank.v1' || !Array.isArray(bank.patterns)) {
      throw Error('Unsupported XAIML pattern bank: ' + source);
    }
    for (const [index, item] of bank.patterns.entries()) {
      if (!item || typeof item.id !== 'string' || !item.id || typeof item.pattern !== 'string' || !item.pattern.trim() || !Array.isArray(item.template)) {
        throw Error(`Invalid XAIML pattern ${index + 1} in ${source}`);
      }
      patterns.push({ ...item, topic: item.topic || null, source });
    }
  }
  return patterns;
}
const GENDER_PAIRS=[['he','she'],['him','her'],['his','hers'],['himself','herself'],['man','woman'],['boy','girl'],['brother','sister'],['father','mother'],['dad','mom'],['husband','wife'],['son','daughter'],['uncle','aunt'],['nephew','niece'],['sir','maam'],['grandfather','grandmother'],['boyfriend','girlfriend'],['king','queen'],['actor','actress'],['waiter','waitress'],['male','female'],['masculine','feminine'],['gentleman','lady'],['mister','missus'],['mr','ms']];
const GENDER_MAP=Object.freeze(GENDER_PAIRS.reduce((m,[a,b])=>{m[a]=b;m[b]=a;return m;},{}));
const PERSON_PAIRS=[['i','you'],['me','you'],['we','you'],['us','you'],['my','your'],['mine','yours'],['our','your'],['ours','yours'],['myself','yourself'],['ourselves','yourselves'],['am','are']];
const PERSON_MAP=Object.freeze(PERSON_PAIRS.reduce((m,[a,b])=>{m[a]=b;return m;},{}));
const PERSON2_PAIRS=[['i','he'],['me','him'],['we','they'],['us','them'],['my','his'],['mine','his'],['our','their'],['ours','theirs'],['myself','himself'],['ourselves','themselves'],['am','is']];
const PERSON2_MAP=Object.freeze(PERSON2_PAIRS.reduce((m,[a,b])=>{m[a]=b;return m;},{}));
const SRAI_OPERATOR_NAMES=Object.freeze(['CAUSE','CONTRAST','DEPENDENCY','CONSTRAINT','EVIDENCE','SEQUENCE','BOUNDARY','STATE','CONFLICT','ALTERNATIVE','INVARIANT','TEST','RELATION','SUBSTITUTE','VERIFY','DIRECT']);

function reflectText(value, map){
  if(!value)return value;
  return value.split(/\s+/).map(tok=>{const k=tok.toLowerCase();const rep=map[k];return rep!==undefined?rep:tok;}).join(' ');
}

function createDaemon({manifest=DEFAULT_MANIFEST, random=Math.random, name='Daemon Bot', maker='K\'UHUL', version='0.2', xcfeDispatch={}, emitTrace=true}={}) {
  const section=manifest.aimlDaemon;
  if (!section || !Array.isArray(section.patterns)) throw Error('manifest.aimlDaemon.patterns is required');
  const xaimlPatterns = loadXaimlPatterns(manifest);
  const categories=[
    ...section.patterns.map((p,i)=>({id:p.id||'daemon.manifest.'+i,pattern:p.pattern,template:p.template,topic:p.topic||null,that:p.that||null,phase:p.phase||'Wo'})),
    ...((manifest.aimlDaemonExtensions?.patterns)||[]).map(p=>({...p,topic:p.topic||null})),
    ...xaimlPatterns
  ];
  const ids = new Set();
  for (const category of categories) {
    if (ids.has(category.id)) throw Error('Duplicate daemon pattern id: ' + category.id);
    ids.add(category.id);
  }
  const order=new Map((manifest.aimlDaemonExtensions?.patternOrder||[]).map((id,i)=>[id,i]));
  categories.sort((a,b)=>(order.get(a.id)??0)-(order.get(b.id)??0));
  const session=()=>({predicates:Object.create(null),topic:'',that:''});
  let traceSequence=0;
  const nextTraceId=()=>'trace-'+(++traceSequence).toString(36);
  function reply(input,state=session(),depth=0,parentTraceId=null) {
    const trace=createTrace(nextTraceId(),parentTraceId,depth,input);
    const finish=result=>emitTrace?{...result,trace}:result;
    if(depth>MAX_DEPTH){
      trace.status=TRACE_STATUS.RECURSION_LIMIT;
      markPhase(trace,'Xul','failed','srai_recursion_limit');
      return finish({text:'I reached the safe SRAI recursion limit.',matched:null,phase:'Xul'});
    }
    const normalizedInput=normalizeWithTrace(input);
    const normalized=normalizedInput.normalized;
    trace.input={raw:normalizedInput.raw,normalized,substitutions:normalizedInput.substitutions};
    trace.mode.value=state.behaviorMode||null;
    markPhase(trace,'Pop','entered',`${normalized.split(' ').filter(Boolean).length} token(s); ${normalizedInput.substitutions.length} substitution(s)`);
    const matchesContext = c => {
      const condition = c.conditions || {};
      if (condition.mood && condition.mood !== state.mood) return false;
        if (condition.emotion && condition.emotion !== state.emotion) return false;
      if (condition.userPreference && condition.userPreference !== state.userPreference) return false;
      if (condition.temperatureRange && (typeof state.temperature !== 'number' || state.temperature < condition.temperatureRange.min || state.temperature > condition.temperatureRange.max)) return false;
      if (condition.memoryTags?.length && !condition.memoryTags.every(tag => (state.memoryTags || []).includes(tag))) return false;
      return true;
    };
    const topicCategories=categories.filter(c=>!c.topic||c.topic===state.topic)
      .filter(c=>!c.mode||c.mode===state.behaviorMode)
      .filter(c=>!c.that||glob(c.that,normalize(state.that||'')))
      .filter(matchesContext);
    const specificity=pattern=>normalize(pattern).split(' ').filter(word=>word&&word!=='*'&&word!=='^'&&word!=='_').length;
    const score = category => {
      const selection = category.selection || {};
      const literal = normalize(category.pattern).split(' ').filter(word => word && !['*','^','_'].includes(word));
      const inputWords = new Set(normalized.split(' ').filter(Boolean));
      const lexical = literal.length ? literal.filter(word => inputWords.has(word)).length / literal.length : 0;
      const weight = Number.isFinite(selection.weight) ? selection.weight : 1;
      const confidence = Number.isFinite(selection.confidence) ? selection.confidence : 1;
      const relativityPrior = Number.isFinite(selection.relativity) ? selection.relativity : 1;
      const relativity = (lexical + relativityPrior) / 2;
        const temperatureFit = Number.isFinite(selection.temperature) && Number.isFinite(state.temperature)
          ? 1 - Math.abs(state.temperature - selection.temperature) : 1;
      let piSimilarity = 1;
      const source = category.piField?.coordinates, query = state.piCoordinates;
      if (Array.isArray(source) && source.length === 3 && Array.isArray(query) && query.length === 3 && [...source, ...query].every(Number.isFinite)) {
        const dot = source.reduce((sum, value, index) => sum + value * query[index], 0);
        const sourceNorm = Math.hypot(...source), queryNorm = Math.hypot(...query);
        if (sourceNorm && queryNorm) piSimilarity = Math.max(0, Math.min(1, (dot / (sourceNorm * queryNorm) + 1) / 2));
      }
        return { value: (weight * confidence * relativity * temperatureFit * piSimilarity), weight, confidence, relativity, temperatureFit, piSimilarity };
    };
    const ordered=[...topicCategories].sort((a,b)=>{
      const ta=a.topic===state.topic?0:1, tb=b.topic===state.topic?0:1;
      if(ta!==tb)return ta-tb;
      const rank = score(b).value - score(a).value;
      return rank || specificity(b.pattern)-specificity(a.pattern);
    });
    let selected=null,captures=[];
    for(const c of ordered){const found=glob(c.pattern,normalized);if(found){selected=c;captures=found;break;}}
    if(!selected){
      trace.status=TRACE_STATUS.NO_MATCH;
      markPhase(trace,'Sek','entered',`no candidate matched among ${ordered.length} in-scope category(s)`);
      markPhase(trace,'Xul','entered','fallback_emitted; commit_authorized=false');
      return finish({text:'I have no rule for "'+normalized+'". Ask HELP to see examples.',matched:null,phase:'Xul'});
    }
    const ranking=score(selected);
    const selectedPhase=selected.phase||'Wo';
    trace.match={id:selected.id,pattern:selected.pattern,topic:selected.topic||null,phase:selectedPhase,source:selected.source||'manifest',specificity:specificity(selected.pattern)};
    trace.captures=captures.map((value,index)=>({slot:index+1,value}));
    markPhase(trace,'Wo','entered',`bound ${captures.length} capture slot(s)`);
    markPhase(trace,'Yax','skipped','deterministic_rule_match_has_no_generation_stage');
    markPhase(trace,'Sek','entered',`selected ${selected.id} from ${ordered.length} candidate(s)`);
    let output='',visible=true;
    const render=(source,quiet=false,stars=captures,collect=false)=>{
      if(typeof source==='string'){if(!quiet&&!collect)output+=source;return source;}
      if(Array.isArray(source)){
        let acc='';
        for(const node of source) acc += render(node,quiet,stars,collect);
        return acc;
      }
      if(!source||typeof source!=='object')return '';
      switch(source.tag){
        case 'text': {const value=String(source.value??'');if(!quiet&&!collect)output+=value;return value;}
        case 'star': {const value=stars[(Number(source.index)||1)-1]||'';if(!quiet&&!collect)output+=value;return value;}
        case 'bot': {const value=({name,maker,version})[source.name]||'';if(!quiet&&!collect)output+=value;return value;}
        case 'get': {const value=state.predicates[source.name]||'';trace.predicates.get.push({name:String(source.name),found:Object.prototype.hasOwnProperty.call(state.predicates,source.name)});if(!quiet&&!collect)output+=value;return value;}
        case 'set': {
          const value=render(source.children||[],true,stars,true);
          state.predicates[source.name]=value;
          trace.predicates.set.push({name:String(source.name),value});
          if(!quiet&&!collect)output+=value;
          return value;
        }
        case 'think': render(source.children||[],true,stars,false);return '';
        case 'srai': {
          const target=render(source.children||[],true,stars,true);
          const child=reply(target,state,depth+1,trace.id);
          trace.srai.push({target,depth:depth+1,child:child.trace?.id||null,matched:child.matched||null,status:child.trace?.status||TRACE_STATUS.OK});
          if(child.trace)trace.children.push(child.trace);
          trace.steps.push({seq:trace.steps.length+1,phase:'Pop',event:'srai_redirect',detail:target});
          if(!quiet&&!collect)output+=child.text;
          return child.text;
        }
        case 'condition': {
          const value=source.var!==undefined?state.predicates[source.var]:state.predicates[source.name];
          const items=source.items||[];
          const found=items.find(item=>item.value!==undefined&&String(item.value)===String(value??''));
          const fallback=items.find(item=>item.value===undefined);
          const chosen=found||fallback;
          trace.conditions.push({name:String(source.var!==undefined?source.var:source.name),value:String(value??''),matched:Boolean(found),fallback:Boolean(!found&&fallback)});
          return chosen?render(chosen.children||[],quiet,stars,collect):'';
        }
        case 'random': {
          const items=source.items||[];if(!items.length)return '';
          const index=Math.min(items.length-1,Math.max(0,Math.floor(random()*items.length)));
          trace.steps.push({seq:trace.steps.length+1,phase:'Yax',event:'random_choice',detail:((index+1)+'/'+items.length)});
          return render(items[index],quiet,stars,collect);
        }
        case 'topic': state.topic=String(source.value||'').toLowerCase();trace.steps.push({seq:trace.steps.length+1,phase:'Wo',event:'topic_set',detail:state.topic});return '';
        case 'gender':
        case 'person':
        case 'person2': {
          const maps={gender:GENDER_MAP,person:PERSON_MAP,person2:PERSON2_MAP};
          const value=render(source.children||[],true,stars,true);
          const transformed=reflectText(value,maps[source.tag]);
          if(!quiet&&!collect)output+=transformed;
          return transformed;
        }
        case 'learn':
        case 'learnf': {
          // Learning banks are not compiled into the JSON engine; degrade silently.
          trace.steps.push({seq:trace.steps.length+1,phase:'Xul',event:'learning_bank_ignored',detail:String(source.tag)});
          render(source.children||[],true,stars,false);
          return '';
        }
        case 'xcfe': {
          const op=String(source.op||source.name||'');
          const attrs=source.attrs||source.params||{};
          const dispatch=xcfeDispatch[op];
          trace.xcfe.push({op,admitted:false,authority:'host_dispatch',dispatch:dispatch?'host':'unbound'});
          trace.steps.push({seq:trace.steps.length+1,phase:'Sek',event:'xcfe_dispatch',detail:(op||'unnamed')+': '+(dispatch?'host':'unbound')});
          const value=dispatch?String(dispatch(attrs,state)):(op?'[XCFE:'+op+']':'');
          if(!quiet&&!collect)output+=value;
          return value;
        }
        default: {
          const tag=String(source.tag||'');
          const isOperator=tag.startsWith('xcfe:')||tag.startsWith('operator:')||tag.startsWith('ELIZA-1:')||SRAI_OPERATOR_NAMES.includes(tag);
          throw Error((isOperator?'Unsupported SRAI operator: ':'Unsupported manifest template node: ')+tag);
        }
      }
    };
    try{ render(selected.template); }
    catch(error){
      trace.status=TRACE_STATUS.RENDER_ERROR;
      markPhase(trace,'Xul','failed','render_error');
      error.trace=trace;
      throw error;
    }
    const text=output.replace(/\s+/g,' ').trim();
    state.that=text;
    markPhase(trace,"Ch'en",'entered',`${trace.predicates.get.length} predicate read(s); ${trace.predicates.set.length} write(s); ${trace.conditions.length} condition(s)`);
    markPhase(trace,'Xul','entered','emitted; commit_authorized=false');
    return finish({text,matched:selected.id,pattern:selected.pattern,phase:selected.phase,topic:state.topic,
      selection_score:Number(ranking.value.toFixed(6)),selection:ranking,memoryTags:selected.conditions?.memoryTags||[]});
  }
  return Object.freeze({
    createSession:session,
    reply(text,state=session()){return reply(text,state);},
    catalog(){return categories.map(({id,pattern,topic,phase,mode,source})=>({id,pattern,topic,phase,mode:mode||null,source:source||'manifest'}));},
    inspect(){return {patterns:categories.length,topics:[...new Set(categories.map(c=>c.topic).filter(Boolean))],
      extendedSection:manifest.aimlDaemonExtensions?.sectionId||null,
      xaimlSources:manifest.aimlDaemonExtensions?.xaimlSources||[]};}
  });
}
module.exports={createDaemon,normalize,normalizeWithTrace,glob,loadXaimlPatterns,TRACE_SCHEMA,PHASES,TRACE_STATUS};