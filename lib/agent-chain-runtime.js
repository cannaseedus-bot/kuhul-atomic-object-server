function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])]));
  return value;
}
function stable(value) { return JSON.stringify(canonical(value)); }
const chainRecords = new Map();

async function sha256(value) {
  if (!globalThis.crypto?.subtle) throw new Error('Web Crypto SHA-256 is unavailable in this context');
  const bytes = new TextEncoder().encode(stable(value));
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}

function resultPayload(result) {
  return { schema: result.schema, tick: result.tick, chainId: result.chainId, initialValue: result.initialValue,
    plan: result.plan, value: result.value, trace: result.trace, final_agent: result.final_agent };
}

export async function runAgentChain(runtime, steps, initialValue, { tick = Date.now(), chainId = `local-${tick}` } = {}) {
  runtime.read('⟁AGENT:CHAIN');
  if (!Array.isArray(steps) || !steps.length) throw new Error('chain requires at least one step');
  let value = initialValue;
  let previousAgent = null;
  const trace = [];
  const plan = steps.map(step => ({ agent: step.agent, capability: step.capability, args: step.args ?? null }));

  for (let index = 0; index < plan.length; index += 1) {
    const step = plan[index];
    if (previousAgent && previousAgent !== step.agent) {
      if (!runtime.canChain(previousAgent, step.agent)) throw new Error(`${previousAgent} cannot chain to ${step.agent}`);
      trace.push({ kind: 'handoff', tick, step: index, from: previousAgent, to: step.agent, value_in: value, value_out: value, guard_state: 'pass' });
    }
    const args = step.args === null ? [value] : step.args.map(arg => arg === null ? value : arg);
    const { agent, result } = runtime.invokeForAgent(step.agent, step.capability, args);
    trace.push({ kind: 'capability_call', tick, step: index, agent_id: agent.id, agent_vector: agent.vector,
      agent_domain: agent.domain, capability_id: step.capability, args, result, guard_state: 'pass' });
    value = result;
    previousAgent = step.agent;
  }

  const result = { schema: 'kuhul.agent-chain.local.v1', tick, chainId, initialValue, plan, value, trace, final_agent: previousAgent,
    authority: 'local_allowlist_replay_only', xcfeAdmitted: false, verifiedTick: false };
  runtime.read('⟁AGENT:ATTEST');
  result.attestation_sha256 = await sha256(resultPayload(result));
  chainRecords.set(chainId, result);
  while (chainRecords.size > 100) chainRecords.delete(chainRecords.keys().next().value);
  return result;
}

export function readAgentTrace(runtime, chainId) {
  runtime.read('⟁AGENT:TRACE');
  const result = chainRecords.get(chainId);
  if (!result) throw new Error(`unknown local chain trace ${chainId}`);
  return result.trace;
}

export async function verifyAgentChain(runtime, chainResult) {
  try {
    runtime.read('⟁AGENT:TRACE'); runtime.read('⟁AGENT:ATTEST');
    if (chainResult?.schema !== 'kuhul.agent-chain.local.v1') throw new Error('unsupported chain result schema');
    const replay = await runAgentChain(runtime, chainResult.plan, chainResult.initialValue,
      { tick: chainResult.tick, chainId: chainResult.chainId });
    const traceMatches = stable(replay.trace) === stable(chainResult.trace);
    const valueMatches = stable(replay.value) === stable(chainResult.value);
    const digestMatches = replay.attestation_sha256 === chainResult.attestation_sha256;
    return { status: traceMatches && valueMatches && digestMatches ? 'local_replay_pass' : 'local_replay_failed',
      locallyVerified: traceMatches && valueMatches && digestMatches, xcfeAdmitted: false, verifiedTick: false,
      traceMatches, valueMatches, digestMatches, attestation_sha256: replay.attestation_sha256 };
  } catch (error) {
    return { status: 'local_replay_failed', locallyVerified: false, xcfeAdmitted: false, verifiedTick: false, error: error.message };
  }
}
