const IMPLEMENTATIONS = Object.freeze({
  add: (a, b) => a + b, sub: (a, b) => a - b, mul: (a, b) => a * b,
  div: (a, b) => { if (b === 0) throw new Error('division by zero'); return a / b; },
  clamp: (a, lo, hi) => { if (lo > hi) throw new Error('lo must be <= hi'); return Math.min(Math.max(a, lo), hi); },
  lerp: (a, b, t) => { if (t < 0 || t > 1) throw new Error('t must be between 0 and 1'); return a + (b - a) * t; },
  norm: (v, lo, hi) => { if (hi === lo) throw new Error('hi must differ from lo'); return (v - lo) / (hi - lo); },
  mod: (a, b) => { if (b === 0) throw new Error('modulo by zero'); return a % b; },
  compose: (f, g) => { requireFunctions([f, g]); return x => f(g(x)); },
  pipe: (...fs) => { requireFunctions(fs); return x => fs.reduce((v, f) => f(v), x); },
  curry: (fn, arity) => { if (typeof fn !== 'function' || !Number.isInteger(arity) || arity < 1) throw new Error('function and positive arity required'); const collect = xs => (...ys) => { const all = [...xs, ...ys]; return all.length >= arity ? fn(...all) : collect(all); }; return collect([]); },
  memo: (fn, keyFn) => { requireFunctions([fn, keyFn]); const cache = new Map(); return (...args) => { const key = keyFn(...args); if (!cache.has(key)) cache.set(key, fn(...args)); return cache.get(key); }; },
  bfs: (graph, start) => walk(graph, start, false), dfs: (graph, start) => walk(graph, start, true),
  dijkstra: (graph, start, end) => shortestPath(graph, start, end),
  topo: graph => topological(graph), cycle: graph => findCycle(graph),
  layout2d: graph => { const normalized = normalizeGraph(graph), ids = [...normalized.nodes], radius = 100; const nodes = ids.map((id, index) => { const angle = -Math.PI / 2 + (2 * Math.PI * index / Math.max(1, ids.length)); return { id, x: Number((radius + radius * Math.cos(angle)).toFixed(3)), y: Number((radius + radius * Math.sin(angle)).toFixed(3)) }; }); return { nodes, edges: normalized.edges.map(([from, to, weight]) => ({ from, to, weight, directed: normalized.directed })) }; },
  sheetCss: sheets => sheets.css, sheetAiml: sheets => sheets.aiml,
  sheetMath: sheets => sheets.math, sheetGraph: sheets => sheets.graph,
  sheetDb: sheets => sheets.database,
});

function requireFunctions(items) { if (!items.length || items.some(item => typeof item !== 'function')) throw new Error('function arguments required'); }
function normalizeGraph(graph) {
  if (!graph || !Array.isArray(graph.nodes) || !Array.isArray(graph.edges)) throw new Error('graph requires nodes and edges arrays');
  const nodes = new Set(graph.nodes.map(String));
  if (nodes.size !== graph.nodes.length) throw new Error('graph node IDs must be unique');
  const adj = new Map([...nodes].map(id => [id, []]));
  const edges = graph.edges.map(edge => {
    if (!Array.isArray(edge) || edge.length < 2) throw new Error('edge must be [from,to,weight?]');
    const [from, to, rawWeight = 1] = edge; const weight = Number(rawWeight);
    if (!nodes.has(String(from)) || !nodes.has(String(to)) || !Number.isFinite(weight)) throw new Error('edge references unknown node or invalid weight');
    adj.get(String(from)).push([String(to), weight]);
    if (!graph.directed) adj.get(String(to)).push([String(from), weight]);
    return [String(from), String(to), weight];
  });
  return { nodes, adj, edges, directed: graph.directed === true };
}
function walk(graph, start, depthFirst) {
  const g = normalizeGraph(graph); start = String(start);
  if (!g.nodes.has(start)) throw new Error(`unknown start node ${start}`);
  const pending = [start], seen = new Set(), result = [];
  while (pending.length) { const node = depthFirst ? pending.pop() : pending.shift(); if (seen.has(node)) continue; seen.add(node); result.push(node); const neighbors = g.adj.get(node).map(item => item[0]); if (depthFirst) neighbors.reverse(); pending.push(...neighbors.filter(next => !seen.has(next))); }
  return result;
}
function shortestPath(graph, start, end) {
  const g = normalizeGraph(graph); start = String(start); end = String(end);
  if (!g.nodes.has(start) || !g.nodes.has(end)) throw new Error('start/end node not found');
  if (g.edges.some(edge => edge[2] < 0)) throw new Error('Dijkstra requires non-negative edge weights');
  const dist = new Map([...g.nodes].map(id => [id, Infinity])), prev = new Map(), todo = new Set(g.nodes); dist.set(start, 0);
  while (todo.size) { let node = null; for (const id of todo) if (node === null || dist.get(id) < dist.get(node)) node = id; if (node === null || !Number.isFinite(dist.get(node))) break; todo.delete(node); if (node === end) break; for (const [next, weight] of g.adj.get(node)) { const candidate = dist.get(node) + weight; if (candidate < dist.get(next)) { dist.set(next, candidate); prev.set(next, node); } } }
  if (!Number.isFinite(dist.get(end))) return { path: [], distance: null };
  const path = [end]; while (path[0] !== start) path.unshift(prev.get(path[0])); return { path, distance: dist.get(end) };
}
function topological(graph) {
  if (!graph?.directed) throw new Error('topological sort requires a directed graph');
  const g = normalizeGraph(graph), indegree = new Map([...g.nodes].map(id => [id, 0]));
  for (const [from, to] of g.edges) { void from; indegree.set(to, indegree.get(to) + 1); }
  const queue = [...indegree].filter(([, n]) => n === 0).map(([id]) => id), result = [];
  while (queue.length) { const node = queue.shift(); result.push(node); for (const [next] of g.adj.get(node)) { indegree.set(next, indegree.get(next) - 1); if (indegree.get(next) === 0) queue.push(next); } }
  if (result.length !== g.nodes.size) throw new Error('graph contains a cycle'); return result;
}
function findCycle(graph) {
  const g = normalizeGraph(graph), state = new Map(), parent = new Map(); let found = null;
  function visit(node) { state.set(node, 1); for (const [next] of g.adj.get(node)) { if (state.get(next) === 1) { const chain = [next]; for (let cur = node; cur !== next && cur !== undefined; cur = parent.get(cur)) chain.unshift(cur); chain.unshift(next); found = chain; return true; } if (!state.has(next)) { parent.set(next, node); if (visit(next)) return true; } } state.set(node, 2); return false; }
  for (const node of g.nodes) if (!state.has(node) && visit(node)) break; return found;
}

export function createCapabilityRuntime({ manifest, root = document, graph, sheets = manifest.sheets }) {
  const entries = Object.entries(manifest).filter(([, value]) => value?.kind === 'operation');
  function read(id) {
    const declaration = manifest[id]; if (!declaration || declaration.kind !== 'operation') throw new Error(`unknown operation ${id}`);
    const element = root.querySelector(`.${declaration.className}`); if (!element) throw new Error(`CSS declaration missing: ${declaration.className}`);
    const css = getComputedStyle(element); const actual = {
      id: css.getPropertyValue('--cap-id').trim().replace(/^['"]|['"]$/g, ''),
      arity: css.getPropertyValue('--cap-arity').trim(), guard: css.getPropertyValue('--cap-guard').trim().replace(/^['"]|['"]$/g, ''),
      expression: css.getPropertyValue('--cap-eval').trim().replace(/^['"]|['"]$/g, ''),
    };
    if (actual.id !== id || actual.guard !== declaration.guard || actual.expression !== declaration.expression) throw new Error(`${id}: CSS declaration does not match capability manifest`);
    if (actual.arity !== String(declaration.arity)) throw new Error(`${id}: CSS arity does not match capability manifest`);
    return { declaration, actual };
  }
  function invoke(id, args = [], { allowGated = false } = {}) {
    const { declaration, actual } = read(id); const expected = declaration.dynamicArity ?? declaration.arity;
    if (typeof expected === 'number' && args.length !== expected) throw new Error(`${id}: expected ${expected} args, received ${args.length}`);
    if (typeof expected === 'string' && (!Array.isArray(args) || args.length < 1)) throw new Error(`${id}: at least one arg required`);
    if (!allowGated && declaration.authority === 'gated') throw new Error(`${id}: gated operation requires explicit admission`);
    if (id.startsWith('⟁GRAPH:')) {
      const implementation = IMPLEMENTATIONS[declaration.implementation];
      if (!implementation) throw new Error(`no implementation for ${id}`);
      return implementation(graph, ...args);
    }
    if (id.startsWith('⟁SHEET:')) return IMPLEMENTATIONS[declaration.implementation](sheets);
    const implementation = IMPLEMENTATIONS[declaration.implementation]; if (!implementation) throw new Error(`no implementation for ${id}`);
    if (id.startsWith('⟁MATH:')) {
      if (args.some(value => !Number.isFinite(Number(value)))) throw new Error(`${id}: finite numeric arguments required`);
      args = args.map(Number);
    }
    const result = implementation(...args); return typeof result === 'number' && !Number.isFinite(result) ? (() => { throw new Error(`${id}: result is not finite`); })() : result;
  }
  function evaluate(id, args = []) {
    if (id === '⟁EVAL:CALL') { const [target, params] = args; if (!manifest[target]?.callableByEvaluator) throw new Error(`${target} is not evaluator-callable`); return invoke(target, params); }
    if (id === '⟁EVAL:TRACE') { const [target, params] = args; const result = evaluate('⟁EVAL:CALL', [target, params]); return { input: params, steps: [{ id: target, output: result }], output: result }; }
    if (id === '⟁EVAL:PIPELINE') { const [steps, input] = args; if (!Array.isArray(steps)) throw new Error('pipeline steps must be an array'); let value = input; const trace = []; for (const step of steps) { if (!manifest[step.id]?.callableByEvaluator) throw new Error(`${step.id} is not evaluator-callable`); const output = invoke(step.id, step.args ?? [value]); trace.push({ id: step.id, input: value, output }); value = output; } return { value, steps: trace }; }
    throw new Error('unknown evaluator entry point');
  }
  function readAgent(agentId) {
    const policy = manifest.agentBindings?.[agentId];
    const element = policy?.className && root.querySelector(`.${policy.className}`);
    if (!element) throw new Error(`unknown or unprojected agent ${agentId}`);
    const css = getComputedStyle(element);
    const cssId = css.getPropertyValue('--agent-id').trim().replace(/^['"]|['"]$/g, '');
    const canCall = css.getPropertyValue('--agent-can-call').trim().replace(/^['"]|['"]$/g, '').split(/\s+/).filter(Boolean);
    const canChain = css.getPropertyValue('--agent-can-chain').trim().replace(/^['"]|['"]$/g, '').split(/\s+/).filter(Boolean);
    if (cssId !== agentId) throw new Error(`${agentId} CSS identity mismatch`);
    if (!sameSet(canCall, policy.capabilities) || !sameSet(canChain, policy.chains)) throw new Error(`${agentId} CSS routing policy differs from capability manifest`);
    return { id: agentId, policy, canCall, canChain, vector: css.getPropertyValue('--agent-vector').trim(), domain: css.getPropertyValue('--agent-domain').trim() };
  }
  function sameSet(left = [], right = []) { return left.length === right.length && left.every(value => right.includes(value)); }
  function invokeForAgent(agentId, capability, args) {
    const agent = readAgent(agentId);
    if (!agent.canCall.includes(capability) && !agent.canCall.includes('*')) throw new Error(`${agentId} cannot call ${capability}`);
    if (!manifest[capability] || manifest[capability].kind !== 'operation') throw new Error(`unknown capability ${capability}`);
    const result = invoke(capability, args);
    return { agent, result };
  }
  function canChain(fromId, toId) {
    const source = readAgent(fromId); readAgent(toId);
    return source.canChain.includes('*') || source.canChain.includes(toId);
  }
  function planAgentCall(source, capability, args, target) {
    read('⟁AGENT:CALL'); const { result } = invokeForAgent(source, capability, args);
    if (!canChain(source, target)) throw new Error(`${source} -> ${target} is not an allowed chain`);
    return { status: 'candidate_handoff', source, capability, target, result, locallyChecked: true, xcfeAdmitted: false, executedByTarget: false, note: 'Local capability result proposed for handoff; no remote agent or XCFE admission was invoked.' };
  }
  return Object.freeze({ entries, read, invoke, evaluate, readAgent, invokeForAgent, canChain, planAgentCall });
}
