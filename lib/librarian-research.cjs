'use strict';

const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawn } = require('node:child_process');

const STOP = new Set(['a', 'an', 'and', 'are', 'does', 'do', 'for', 'have', 'how', 'is', 'many', 'of', 'the', 'to', 'what', 'which', 'who', 'why']);
const MAX_SOURCE_TEXT = 5000;

function tokens(value) {
  return String(value).normalize('NFKC').toLowerCase().match(/[a-z0-9]+/g) || [];
}

function questionKey(question) {
  const words = tokens(question);
  return words.join('-').slice(0, 140).replace(/-+$/, '') || 'question';
}

function queryTerms(question) {
  const words = tokens(question);
  const content = words.filter(word => !STOP.has(word));
  return content.length ? content.join(' ') : words.join(' ');
}

function sourceExcerpt(sourceText, question) {
  const wanted = new Set(queryTerms(question).split(/\s+/).filter(Boolean));
  const quantity = /\b(?:how\s+many|how\s+much|total|count|number\s+of)\b/i.test(question);
  const targetTerms = [...wanted].filter(term => !['saturn', 'planet', 'planets'].includes(term));
  const sentences = String(sourceText || '').match(/[^.!?]+[.!?]?/g) || [];
  const ranked = sentences.map((sentence, index) => {
    const present = new Set(tokens(sentence));
    const overlap = [...wanted].filter(term => present.has(term));
    const hasRequestedQuantity = !/\bremaining\s+\d[\d,]*\s+/i.test(sentence) && targetTerms.some(term => new RegExp(`\\b\\d[\\d,]*\\s+(?:(?:confirmed|known|currently\\s+known)\\s+)?${term}s?\\b`, 'i').test(sentence));
    return { sentence: sentence.trim(), index, overlap, score: overlap.length / Math.max(wanted.size, 1), hasRequestedQuantity };
  }).filter(item => item.sentence && item.overlap.length && (!quantity || item.hasRequestedQuantity));
  ranked.sort((a, b) => b.score - a.score || a.index - b.index);
  return ranked.slice(0, quantity ? 2 : 2).map(item => item.sentence).join(' ').slice(0, 900);
}

function quantityEvidence(record) {
  if (!/\b(?:how\s+many|how\s+much|total|count|number\s+of)\b/i.test(record.question)) return null;
  const terms = new Set(queryTerms(record.question).split(/\s+/).filter(Boolean));
  const rows = [];
  for (const source of record.sources || []) {
    const sentences = String(source.text || '').match(/[^.!?]+[.!?]?/g) || [];
    for (const sentence of sentences) {
      const present = new Set(tokens(sentence));
      const targetTerms = [...terms].filter(term => present.has(term) && !['saturn', 'planet', 'planets'].includes(term));
      for (const target of targetTerms) {
        const escaped = target.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const match = sentence.match(new RegExp(`\\b(\\d[\\d,]*)\\s+(?:(?:confirmed|known|currently\\s+known)\\s+)?${escaped}s?\\b`, 'i'));
        if (!match) continue;
        const asOf = sentence.match(/\bas of\s+([A-Z][a-z]+\s+\d{4})\b/i);
        rows.push({ source: source.source, title: source.title, url: source.url, term: target, value: match[1].replace(/,/g, ''), asOf: asOf?.[1] || null, sentence: sentence.trim() });
        break;
      }
    }
  }
  if (!rows.length) return { status: 'no_direct_quantity_evidence', rows: [] };
  const bySource = new Map();
  for (const row of rows) {
    const prior = bySource.get(row.source);
    if (!prior || (row.asOf && !prior.asOf)) bySource.set(row.source, row);
  }
  const selected = [...bySource.values()];
  return { status: new Set(selected.map(row => row.value)).size > 1 ? 'sources_disagree' : 'sources_agree', rows: selected };
}

function quantityAnswer(evidence) {
  if (!evidence) return null;
  if (!evidence.rows.length) return 'The retrieved source passages did not state a number for this question, so I cannot give a source-grounded total.';
  const rows = evidence.rows;
  const statements = rows.map(row => `${row.source} states ${row.value}${row.asOf ? ` (as of ${row.asOf})` : ''}`).join('; ');
  if (evidence.status === 'sources_disagree') {
    return `The retrieved sources report different totals: ${statements}. The counts may differ because discoveries and confirmations change over time; check the linked source dates.`;
  }
  return `The retrieved sources report ${rows[0].value}${rows[0].asOf ? ` (as of ${rows[0].asOf})` : ''}. ${statements}.`;
}

function validateQuantityFormatting(answer, evidence) {
  if (!evidence?.rows?.length) return { ok: false, reason: 'no source quantity is available' };
  const text = String(answer || '');
  const numbers = (text.match(/\b\d[\d,]*(?:\.\d+)?\b/g) || []).map(value => value.replace(/,/g, ''));
  const allowed = new Set(evidence.rows.flatMap(row => [row.value, ...(row.asOf?.match(/\d{4}/g) || [])]));
  const unsupported = numbers.filter(value => !allowed.has(value));
  if (unsupported.length) return { ok: false, reason: `unsupported numeric claim(s): ${[...new Set(unsupported)].join(', ')}` };
  for (const row of evidence.rows) {
    if (!numbers.includes(row.value) || !text.toLowerCase().includes(row.source.toLowerCase())) {
      return { ok: false, reason: `formatted reply omitted ${row.source}'s retrieved value` };
    }
    if (row.asOf && !text.includes(row.asOf)) return { ok: false, reason: `formatted reply omitted ${row.source}'s source date` };
  }
  if (evidence.status === 'sources_disagree' && !/differ|disagree|conflict|different|not the same/i.test(text)) {
    return { ok: false, reason: 'formatted reply did not disclose the source disagreement' };
  }
  return { ok: true, reason: null };
}

function runPythonJson(root, scriptName, args, input, timeoutMs = 30000, parseJson = true) {
  const python = process.env.KUHUL_PYTHON || process.env.PYTHON || 'python';
  const script = path.join(root, scriptName);
  return new Promise((resolve, reject) => {
    const child = spawn(python, [script, ...args], { cwd: root, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    const timer = setTimeout(() => child.kill(), timeoutMs);
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', chunk => { stdout += chunk; if (stdout.length > 128_000) child.kill(); });
    child.stderr.on('data', chunk => { stderr += chunk; if (stderr.length > 32_000) child.kill(); });
    child.on('error', error => { clearTimeout(timer); reject(error); });
    child.on('close', code => {
      clearTimeout(timer);
      if (code !== 0) return reject(Error(`${scriptName} exited with code ${code}: ${stderr.slice(-2000)}`));
      if (!parseJson) return resolve(stdout.trim());
      try { resolve(JSON.parse(stdout.trim())); }
      catch (error) { reject(Error(`${scriptName} returned invalid JSON: ${error.message}`)); }
    });
    child.stdin.end(input);
  });
}

function ngrams(words, width) {
  const out = [];
  for (let i = 0; i + width <= words.length; i += 1) out.push(words.slice(i, i + width).join(' '));
  return out;
}

function cleanHtml(value) {
  return String(value || '').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, ' ')
    .replace(/<style\b[^>]*>[\s\S]*?<\/style>/gi, ' ').replace(/<nav\b[^>]*>[\s\S]*?<\/nav>/gi, ' ')
    .replace(/<header\b[^>]*>[\s\S]*?<\/header>/gi, ' ').replace(/<footer\b[^>]*>[\s\S]*?<\/footer>/gi, ' ')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').replace(/&quot;/gi, '"')
    .replace(/&#8217;|&rsquo;/gi, '’').replace(/&#8211;|&ndash;/gi, '–')
    .replace(/&#8212;|&mdash;/gi, '—').replace(/&#0*39;|&apos;/gi, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n)))
    .replace(/\s+/g, ' ').trim().slice(0, MAX_SOURCE_TEXT);
}

async function getText(url, host) {
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:' || parsed.hostname !== host) throw Error('research URL failed host policy');
  const response = await fetch(parsed, { headers: { 'user-agent': 'Kuhul-Micronaut/1.0 (local source retrieval)' }, signal: AbortSignal.timeout(15000) });
  if (!response.ok) throw Error(`${host} returned HTTP ${response.status}`);
  const body = await response.text();
  if (body.length > 2_000_000) throw Error(`${host} page exceeded the retrieval size limit`);
  return body;
}

async function getJson(url, host, timeoutMs = 12000) {
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:' || parsed.hostname !== host) throw Error('research URL failed host policy');
  const response = await fetch(parsed, { headers: { 'user-agent': 'Kuhul-Micronaut/1.0 (local source retrieval)' }, signal: AbortSignal.timeout(timeoutMs) });
  if (!response.ok) throw Error(`${host} returned HTTP ${response.status}`);
  return response.json();
}

async function retrieveWikipedia(terms) {
  const searchUrl = new URL('https://en.wikipedia.org/w/api.php');
  searchUrl.search = new URLSearchParams({ action: 'query', list: 'search', srsearch: terms, srlimit: '2', format: 'json', origin: '*' });
  const result = await getJson(searchUrl, 'en.wikipedia.org');
  const queryWords = tokens(terms);
  const hits = (result.query?.search || []).map(hit => {
    const titleWords = new Set(tokens(hit.title));
    const overlap = queryWords.filter(word => titleWords.has(word)).length;
    return { ...hit, _score: overlap / Math.max(queryWords.length, 1) + (hit.title.toLowerCase() === terms.toLowerCase() ? 1 : 0) };
  }).sort((a, b) => b._score - a._score).slice(0, 1);
  if (!hits.length) throw Error('Wikipedia search returned no pages');
  const pagesUrl = new URL('https://en.wikipedia.org/w/api.php');
  pagesUrl.search = new URLSearchParams({ action: 'query', pageids: hits.map(hit => hit.pageid).join('|'), prop: 'extracts|info', exintro: '1', explaintext: '1', inprop: 'url', format: 'json' });
  const pages = await getJson(pagesUrl, 'en.wikipedia.org');
  return hits.map(hit => {
    const page = pages.query?.pages?.[hit.pageid] || {};
    return { source: 'Wikipedia', title: cleanHtml(page.title || hit.title), url: page.fullurl || `https://en.wikipedia.org/wiki/${encodeURIComponent(hit.title.replace(/ /g, '_'))}`, text: cleanHtml(page.extract), retrieved_at: new Date().toISOString() };
  }).filter(item => item.text);
}

async function retrieveNasa(terms) {
  if (tokens(terms).includes('saturn')) {
    const html = await getText('https://science.nasa.gov/saturn/facts/', 'science.nasa.gov');
    const main = html.match(/<main\b[^>]*>([\s\S]*?)<\/main>/i)?.[1] || html;
    const article = main.match(/<article\b[^>]*>([\s\S]*?)<\/article>/i)?.[1] || main;
    const text = cleanHtml(article);
    if (text) return [{ source: 'NASA', title: 'Saturn Facts', url: 'https://science.nasa.gov/saturn/facts/', text, retrieved_at: new Date().toISOString() }];
  }
  const url = new URL('https://science.nasa.gov/wp-json/wp/v2/search');
  url.search = new URLSearchParams({ search: terms, per_page: '3' });
  const hits = await getJson(url, 'science.nasa.gov');
  if (!Array.isArray(hits) || !hits.length) throw Error('NASA search returned no pages');
  const pages = await Promise.all(hits.slice(0, 2).map(async hit => {
    const match = String(hit._links?.self?.[0]?.href || '').match(/^https:\/\/science\.nasa\.gov\/wp-json\/wp\/v2\/([a-z0-9-]+)\/(\d+)/i);
    let text = '';
    let title = cleanHtml(hit.title);
    let canonical = hit.url;
    if (match) {
      const page = await getJson(`https://science.nasa.gov/wp-json/wp/v2/${match[1]}/${match[2]}?_fields=title,link,content`, 'science.nasa.gov');
      title = cleanHtml(page.title?.rendered || title);
      canonical = page.link || canonical;
      text = cleanHtml(page.content?.rendered);
    }
    return { source: 'NASA', title, url: canonical, text, retrieved_at: new Date().toISOString() };
  }));
  return pages.filter(item => item.url && item.text);
}

async function retrieveQuestion(question, root, { replyDepth = 'balanced' } = {}) {
  const words = tokens(question);
  const terms = queryTerms(question);
  const searchedAt = new Date().toISOString();
  const settled = await Promise.allSettled([retrieveNasa(terms), retrieveWikipedia(terms)]);
  const sources = [];
  const failures = [];
  for (let i = 0; i < settled.length; i += 1) {
    const result = settled[i];
    if (result.status === 'fulfilled') sources.push(...result.value);
    else failures.push({ source: i === 0 ? 'NASA' : 'Wikipedia', error: String(result.reason?.message || result.reason).slice(0, 300) });
  }
  for (const source of sources) source.excerpt = sourceExcerpt(source.text, question);
  const questionId = questionKey(question);
  const record = {
    schema: 'kuhul.micronaut_data.research.v1', question_id: questionId, question: question.trim(),
    query_terms: terms, ngrams: { unigram: [...new Set(words)], bigram: ngrams(words, 2), trigram: ngrams(words, 3) },
    retrieved_at: searchedAt, retrieval_status: sources.length ? 'retrieved' : 'unavailable',
    authority: 'source_evidence_only; not_verified_fact', created_by: ['Librarian-µ', 'Factory-µ'],
    sources, failures
  };
  const dir = path.join(root, 'micronauts-data');
  await fs.mkdir(dir, { recursive: true });
  const target = path.join(dir, `${questionId}.json`);
  try {
    const previous = JSON.parse(await fs.readFile(target, 'utf8'));
    if (previous.question && previous.question.toLowerCase() !== question.trim().toLowerCase()) {
      record.question_id = `${questionId}-${crypto.createHash('sha256').update(question.trim()).digest('hex').slice(0, 10)}`;
    }
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  await runPythonJson(root, 'mu-factory.py', ['research-record', '--data-root', dir], JSON.stringify(record), 30000, false);
  try {
    record.reply_field = await runPythonJson(root, 'micronaut/main.py', [
      'research-field', '--question', question, '--record', path.join(dir, `${record.question_id}.json`),
      '--reply-depth', replyDepth
    ], '');
    record.cfpc = record.reply_field.cfpc;
  } catch (error) {
    record.cfpc = { schema: 'kuhul.cfpc.classification.v1', evidence_status: 'unavailable', error: String(error.message || error).slice(0, 500), authority: 'proposal_only' };
  }
  record.evidence_resolution = quantityEvidence(record);
  if (record.reply_field) record.reply_field.quantity_evidence = record.evidence_resolution;
  await runPythonJson(root, 'mu-factory.py', ['research-record', '--data-root', dir], JSON.stringify(record), 30000, false);
  return record;
}

function evidencePrompt(record, { quantityEvidence: quantities = null, replyDepth = 'balanced' } = {}) {
  if (!record.sources.length) return `\n\nLive retrieval was attempted for this question but returned no usable sources. Do not imply that source data was retrieved. Retrieval errors: ${JSON.stringify(record.failures)}`;
  const evidence = record.sources.map(item => ({ source: item.source, title: item.title, url: item.url, text: item.excerpt || item.text }));
  const field = record.reply_field || { question: record.question, reply_depth: { level: replyDepth }, cfpc: record.cfpc || null, viable_data: { sources: evidence }, quantity_evidence: quantities };
  field.reply_depth = { level: replyDepth, guidance: field.reply_depth?.guidance };
  field.quantity_evidence = quantities;
  const { dispatch, phase_trace, ...formattingField } = field;
  return `\n\nReply-formatting field (the model formats this field; it does not retrieve or add facts):\n${JSON.stringify(formattingField)}\nUse only the retrieved source evidence in the field. Follow reply_depth. Do not add a number absent from quantity_evidence. If its status is sources_disagree, report each source value with its date and do not choose one as definitive. Cite the named sources in your prose; clickable source links are also shown separately.`;
}

module.exports = { retrieveQuestion, evidencePrompt, questionKey, quantityEvidence, quantityAnswer, sourceExcerpt, validateQuantityFormatting };
