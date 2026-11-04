import React, { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { TeachChip } from './TeachChip';

type Props = { seedBotUrl: string; userId: string; agentId?: string; apiBase?: string; avatarSrc?: string };
type TraceStep = { seq: number; phase: string; event: string; detail: string | null };
type ReplyTrace = {
  schema: string;
  id: string;
  parent: string | null;
  depth: number;
  input: { raw: string; normalized: string; substitutions: Array<{ find: string; replace: string }> };
  phases: Array<{ phase: string; status: string; detail: string | null }>;
  match: { id: string; pattern: string; topic: string | null; phase: string; source: string; specificity: number } | null;
  captures: Array<{ slot: number; value: string }>;
  srai: Array<{ target: string; depth: number; child: string | null; matched: string | null; status: string }>;
  children: ReplyTrace[];
  xcfe: Array<{ op: string; admitted: boolean; authority: string; dispatch: string }>;
  predicates: { get: Array<{ name: string; found: boolean }>; set: Array<{ name: string; value: string }> };
  conditions: Array<{ name: string; value: string; matched: boolean; fallback: boolean }>;
  mode: { family: string; value: string | null; narrows_only: boolean };
  admission: { owner: string; admitted: boolean; reason: string };
  commit: { authorized: boolean; phase: string; reason: string };
  status: string;
  steps: TraceStep[];
};
const traceSummary = (trace: ReplyTrace) => {
  const walked = trace.phases.filter(phase => phase.status === 'entered').map(phase => phase.phase).join(' → ') || 'none';
  return `${trace.id} · ${trace.status} · ${trace.match?.phase ?? 'Xul'} · ${walked} · srai:${trace.srai.length} · xcfe:${trace.xcfe.length} · commit:${trace.commit.authorized}`;
};
type Bubble = { id: number; role: 'user' | 'daemon' | 'error'; text: string; route: string; trace?: ReplyTrace };
type AgentReply = { text: string; matched?: string | null; state?: Record<string, unknown>; route?: string; trace?: ReplyTrace };
type Mode = { label: string; description: string };
type LearningCandidate = { id: string; status: string; mode: string; candidate: { pattern: string; response: string; micronautBindings: Array<{ref:string;weight:number}> } };

export function DaemonBotWidget({ seedBotUrl, userId, agentId = 'daemon-bot', apiBase = '/api', avatarSrc = '/micronaut/logo.svg' }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const stateRef = useRef<Record<string, unknown>>({});
  const historyRef = useRef<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const sessionIdRef = useRef(globalThis.crypto?.randomUUID?.() || `session-${Date.now()}-${Math.random().toString(16).slice(2)}`);
  const [messages, setMessages] = useState<Bubble[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [mode, setMode] = useState('buddy');
  const [modes, setModes] = useState<Record<string, Mode>>({});
  const [snapshotId, setSnapshotId] = useState('');
  const [candidates, setCandidates] = useState<LearningCandidate[]>([]);
  const [memoryNotice, setMemoryNotice] = useState('');
  const base = apiBase.replace(/\/$/, '');
  const agent = encodeURIComponent(agentId);

  useEffect(() => {
    let active = true;
    fetch(`${base}/behavior/modes`).then(response => {
      if (!response.ok) throw new Error(`Mode registry returned ${response.status}`);
      return response.json();
    }).then(registry => { if (active && registry?.modes) setModes(registry.modes); })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : String(cause)); });
    return () => { active = false; };
  }, [base]);

  const askBot = useCallback(async (utterance: string) => {
    const r = await fetch(seedBotUrl + '?q=' + encodeURIComponent(utterance) + '&raw=1', { credentials: 'include' });
    if (!r.ok) throw new Error('Bot responded ' + r.status);
    return r.text();
  }, [seedBotUrl]);

  const watchWorker = async (workerId: string, bubbleId: number, word: string) => {
    const statusUrl = `${base}/daemon/agents/${agent}/commands/${encodeURIComponent(workerId)}`;
    for (let attempt = 0; attempt < 420; attempt += 1) {
      await new Promise(resolve => setTimeout(resolve, 5000));
      try {
        const response = await fetch(statusUrl);
        if (!response.ok) continue;
        const status = await response.json() as {status:string;outputPath?:string;attentionPath?:string;stdout?:string;stderr?:string};
        if (status.status === 'RUNNING' || status.status === 'starting') continue;
        const detail = status.status === 'COMPLETED_DATA_ONLY'
          ? `Completed ${word}. Field: ${status.outputPath}\nAttention vectors: ${status.attentionPath}`
          : `Worker ${status.status.toLowerCase()} for ${word}.\n${status.stderr || status.stdout || ''}`;
        setMessages(current => current.map(message => message.id === bubbleId
          ? { ...message, text: `${message.text}\n\n${detail}` }
          : message));
        return;
      } catch { /* A transient status request failure should not stop the worker. */ }
    }
  };

  const send = async (event: FormEvent) => {
    event.preventDefault();
    const text = inputRef.current?.value.trim();
    if (!text || busy) return;
    if (inputRef.current) inputRef.current.value = '';
    setBusy(true);
    setError('');
    const userRoute = `${base}/daemon/agents/${agent}/reply`;
    const commandRoute = `${base}/daemon/agents/${agent}/commands`;
    const userMessageId = Date.now();
    let replyTrace: ReplyTrace | undefined;
    setMessages(current => [...current, { id: userMessageId, role: 'user', text, route: commandRoute }]);
    try {
      const commandResponse = await fetch(commandRoute, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, mode, sessionId: sessionIdRef.current, userId })
      });
      const commandResult = await commandResponse.json();
      if (!commandResponse.ok) throw new Error(commandResult.error || `Command route returned ${commandResponse.status}`);
      if (commandResult.handled) {
        const output = (commandResult.results || []).map((result: {status:string;word:string;model?:string;backend?:string;workerId:string;outputPath?:string;attentionPath?:string;statusRoute?:string;summary?:string;error?:string}) =>
          result.status === 'running'
            ? `Started background distillation and embedding for ${result.word} with ${result.model} (${result.backend}). Worker: ${result.workerId}\nStatus: ${result.statusRoute}\nField: ${result.outputPath}\nAttention vectors: ${result.attentionPath}`
            : result.status === 'failed_to_start'
              ? `Could not start distillation for ${result.word} (${result.workerId}): ${result.error || ''}`
              : result.status === 'completed_data_only'
              ? `Distilled ${result.word} with ${result.model} (${result.backend}). Worker: ${result.workerId}\nOutput: ${result.outputPath}\n${result.summary || ''}`
              : `Distillation failed for ${result.word} (${result.workerId}): ${result.error || ''}\n${result.summary || ''}`
        ).join('\n\n');
        const suffix = commandResult.skippedCount ? `\n\n${commandResult.skippedCount} repeated or additional tool call(s) were not run; this turn allows one registered tool call.` : '';
        const answer = `${output || 'The registered command pattern ran.'}${suffix}`;
        const route = `COMMAND · ${commandRoute}`;
        const workerBubbleId = Date.now() + 1;
        setMessages(current => [...current, { id: workerBubbleId, role: 'daemon', text: answer, route }]);
        for (const result of commandResult.results || []) {
          if (result.status === 'running') void watchWorker(result.workerId, workerBubbleId, result.word);
        }
        historyRef.current = [...historyRef.current, { role: 'user', content: text }, { role: 'assistant', content: answer }].slice(-24);
        return;
      }
      setMessages(current => current.map(message => message.id === userMessageId ? { ...message, route: `${commandRoute} → ${userRoute}` } : message));
      const matchResponse = await fetch(userRoute, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, state: stateRef.current, mode, sessionId: sessionIdRef.current, userId })
      });
      const matched = await matchResponse.json() as AgentReply;
      if (!matchResponse.ok) throw new Error((matched as { error?: string }).error || `XAIML route returned ${matchResponse.status}`);
      if (matched.state) stateRef.current = matched.state;
      replyTrace = matched.trace;
      let answer = matched.text;
      let replyRoute = matched.matched ? `XAIML:${matched.matched} · ${userRoute}` : '';
      if (!matched.matched) {
        const modelRoute = `${base}/daemon/agents/${agent}/respond`;
        const response = await fetch(modelRoute, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text, history: historyRef.current, mode, sessionId: sessionIdRef.current, userId })
        });
        const result = await response.json() as AgentReply;
        if (!response.ok) throw new Error((result as { error?: string }).error || `Model route returned ${response.status}`);
        answer = result.text;
        replyTrace = result.trace;
        replyRoute = `${result.route || 'MODEL'} · ${modelRoute}`;
        historyRef.current = [...historyRef.current, { role: 'user', content: text }, { role: 'assistant', content: answer }].slice(-24);
      }
      setMessages(current => [...current, { id: Date.now() + 1, role: 'daemon', text: answer || '', route: replyRoute, trace: replyTrace }]);
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : String(cause);
      setError(message);
      setMessages(current => [...current, { id: Date.now() + 1, role: 'error', text: message, route: userRoute }]);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  };

  const reset = () => {
    stateRef.current = {};
    historyRef.current = [];
    setMessages([]);
    setSnapshotId('');
    setCandidates([]);
    setMemoryNotice('');
    setError('');
  };

  const saveSnapshot = async () => {
    if (messages.filter(message => message.role !== 'error').length < 2) return;
    if (!window.confirm('Save this conversation snapshot in local .asx_memory.json for replay and candidate learning?')) return;
    setBusy(true);
    setMemoryNotice('Saving replay snapshot…');
    try {
      const response = await fetch(`${base}/daemon/agents/${agent}/snapshots`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ consent: true, userId, sessionId: sessionIdRef.current, mode,
          messages: messages.filter(message => message.role !== 'error').map(message => ({ role: message.role, text: message.text, route: message.route })) })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Snapshot route returned ${response.status}`);
      setSnapshotId(result.id);
      setMemoryNotice(`Replay snapshot saved (${result.count} turns). It remains data only.`);
    } catch (cause) {
      setMemoryNotice(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };

  const proposePatterns = async () => {
    if (!snapshotId) return;
    setBusy(true);
    setMemoryNotice('Preparing candidate patterns from the saved replay…');
    try {
      const response = await fetch(`${base}/daemon/agents/${agent}/learning/propose`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ snapshotId, userId })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Learning route returned ${response.status}`);
      setCandidates(result.candidates || []);
      setMemoryNotice(`${(result.candidates || []).length} proposal(s) saved for review. Nothing was admitted.`);
    } catch (cause) {
      setMemoryNotice(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };

  const admitCandidate = async (candidateId: string) => {
    if (!window.confirm('Admit this plain-text XAIML pattern to this daemon? This is a host-approved grammar change.')) return;
    setBusy(true);
    try {
      const response = await fetch(`${base}/daemon/agents/${agent}/learning/admit`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidateId, userId, approved: true })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Admission route returned ${response.status}`);
      setCandidates(current => current.map(candidate => candidate.id === candidateId ? { ...candidate, status: 'admitted' } : candidate));
      setMemoryNotice(`Admitted ${result.patternId} after explicit host approval.`);
    } catch (cause) {
      setMemoryNotice(cause instanceof Error ? cause.message : String(cause));
    } finally { setBusy(false); }
  };

  return <section className="db-chat" aria-label={`${agentId} chat`}>
    <div className="db-transcript" aria-live="polite" aria-busy={busy}>
      {messages.map(message => message.role === 'daemon' ? <div key={message.id} className="db-reply-row">
        <div className="db-avatar-shell" title={`${agentId} topology avatar`}><img className="db-avatar" src={avatarSrc} alt="" aria-hidden="true" /></div>
        <article className="db-bubble db-bubble-daemon" data-route={message.route}>
          <div className="db-bubble-role">{agentId}</div>
          <div className="db-bubble-text">{message.text}</div>
          <div className="db-bubble-route">{message.route}</div>
          {message.trace && <details className="db-bubble-trace" data-trace-id={message.trace.id} data-trace-status={message.trace.status}>
            <summary>{traceSummary(message.trace)}</summary>
            <pre>{JSON.stringify(message.trace, null, 2)}</pre>
          </details>}
        </article>
      </div> : <article key={message.id} className={`db-bubble db-bubble-${message.role}`} data-route={message.route}>
        <div className="db-bubble-role">{message.role === 'user' ? 'You' : 'Route error'}</div>
        <div className="db-bubble-text">{message.text}</div>
        <div className="db-bubble-route">{message.route}</div>
      </article>)}
      {busy && <div className="db-reply-row db-live-reply" role="status">
        <div className="db-avatar-shell db-avatar-working" title={`${agentId} is processing`}><img className="db-avatar" src={avatarSrc} alt="" aria-hidden="true" /></div>
        <div className="db-pending">{agentId} is following its reply route…</div>
      </div>}
    </div>
    {error && <p className="db-chat-error" role="alert">{error}</p>}
    <form className="db-form" onSubmit={send}>
      <label className="db-mode-picker">Behavior mode
        <select value={mode} onChange={event => setMode(event.target.value)} disabled={busy}>
          {Object.entries(modes).map(([id, item]) => <option key={id} value={id}>{item.label}</option>)}
        </select>
      </label>
      <div className="db-input-row">
        <input ref={inputRef} className="db-input" placeholder={`Ask ${agentId}`} aria-label="Message" required disabled={busy} />
        <button type="submit" className="db-btn" disabled={busy}>{busy ? 'Sending…' : 'Send'}</button>
      </div>
      <div className="db-suggestions">
        <button type="button" className="db-chip" onClick={() => { if (inputRef.current) inputRef.current.value = 'HELP'; inputRef.current?.focus(); }}>Help</button>
        <button type="button" className="db-chip" onClick={reset}>New session</button>
        <button type="button" className="db-chip" onClick={saveSnapshot} disabled={busy || messages.filter(message => message.role !== 'error').length < 2}>Save replay snapshot</button>
        {snapshotId && <button type="button" className="db-chip" onClick={proposePatterns} disabled={busy}>Propose patterns</button>}
        <TeachChip userId={userId} askBot={askBot} />
      </div>
    </form>
    {memoryNotice && <p className="db-memory-notice" role="status">{memoryNotice}</p>}
    {candidates.length > 0 && <section className="db-learning-candidates" aria-label="Candidate patterns">
      <h3>Candidate grammar · review required</h3>
      {candidates.map(candidate => <article className="db-candidate" key={candidate.id}>
        <code>{candidate.candidate.pattern}</code>
        <p>{candidate.candidate.response}</p>
        <small>Mode: {candidate.mode} · {candidate.candidate.micronautBindings.map(binding => `${binding.ref} ${binding.weight.toFixed(2)}`).join(', ') || 'no bindings'} · {candidate.status}</small>
        {candidate.status !== 'admitted' && <button type="button" className="db-chip" onClick={() => admitCandidate(candidate.id)} disabled={busy}>Approve pattern</button>}
      </article>)}
    </section>}
  </section>;
}