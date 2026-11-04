import json

code = '''/**
 * micronaut_bundle_server.js - GGUF Inference Enabled
 */

const http = require('http');
const fs = require('fs');
const path = require('path');
const bson = require('bson');

const manifest = JSON.parse(fs.readFileSync('manifest.json', 'utf8'));
const PORT = manifest.port || 7420;
const ROOT = path.resolve(manifest.public_dir || './www');
const BUNDLES_DIR = path.join(__dirname, 'bundles');

console.log('[bundle-server] Starting...');
console.log('[bundle-server] Port:', PORT);

const loadedBundles = {};
let activeBundle = null;

function loadBundle(bundlePath) {
    try {
        const data = fs.readFileSync(bundlePath);
        const bundle = bson.deserialize(data);
        console.log('[bundle] Loaded:', bundle.name);
        return bundle;
    } catch (e) {
        console.error('[bundle] Failed:', bundlePath, e.message);
        return null;
    }
}

function scanBundles() {
    const files = fs.readdirSync(BUNDLES_DIR);
    const bundles = [];
    for (const file of files) {
        if (file.endsWith('.bson')) {
            const bundle = loadBundle(path.join(BUNDLES_DIR, file));
            if (bundle) {
                loadedBundles[bundle.id] = bundle;
                bundles.push({ id: bundle.id, name: bundle.name, experts: bundle.experts.length });
            }
        }
    }
    console.log('[bundle] Scanned', bundles.length, 'bundles');
    return bundles;
}

function setActiveBundle(bundleId) {
    if (!loadedBundles[bundleId]) return { success: false, error: 'Not found: ' + bundleId };
    activeBundle = loadedBundles[bundleId];
    console.log('[bundle] Active:', activeBundle.name);
    return { success: true, bundle: activeBundle };
}

function selectExperts(query, bundle) {
    if (!bundle) return [];
    const q = query.toLowerCase().trim();
    const scores = bundle.experts.map(expert => {
        let score = expert.bias + (bundle.learned.biases[expert.id] || 0);
        let matches = 0;
        for (const kw of (expert.keywords || [])) {
            if (q.includes(kw.toLowerCase())) { score += 0.35; matches++; }
        }
        if (matches > 1) score += 0.15 * (matches - 1);
        if (expert.domain === 'mathematics' && q.match(/\d+\s*[\+\-\*\/]\s*\d+/)) { score += 0.5; matches++; }
        return { ...expert, score, matches };
    });
    const max = Math.max(...scores.map(s => s.score));
    const exps = scores.map(s => Math.exp(s.score - max));
    const sum = exps.reduce((a, b) => a + b, 0);
    return scores.map((s, i) => ({
        id: s.id, name: s.name, domain: s.domain, weight: exps[i] / sum, matches: s.matches, system_prompt: s.system_prompt
    })).sort((a, b) => b.weight - a.weight);
}

let llm = null;

async function loadGGUFModel(modelPath) {
    if (!modelPath) { console.log('[GGUF] No model path'); return null; }
    try {
        console.log('[GGUF] Loading:', modelPath);
        const { Llama } = await import('node-llama-cpp');
        llm = new Llama({ modelPath: modelPath, contextSize: 2048, threads: 4 });
        console.log('[GGUF] Loaded successfully');
        return llm;
    } catch (e) {
        console.error('[GGUF] Failed:', e.message);
        return null;
    }
}

async function generateWithGGUF(query, experts, bundle) {
    const topExpert = experts[0];
    const systemPrompt = topExpert.system_prompt || ('You are ' + bundle.agent.persona + ', a helpful assistant.');
    if (!llm) return generateFallback(query, experts, bundle);
    try {
        const prompt = '<|system|>\n' + systemPrompt + '</s>\n<|user|>\n' + query + '</s>\n<|assistant|>\n';
        const response = await llm.prompt(prompt, { maxTokens: 512, temperature: 0.7, topP: 0.9 });
        return { text: response.trim(), experts: experts, source: 'gguf', bundle: bundle.name };
    } catch (e) {
        console.error('[GGUF] Error:', e.message);
        return generateFallback(query, experts, bundle);
    }
}

function generateFallback(query, experts, bundle) {
    const top = experts[0];
    const q = query.toLowerCase().trim();
    const mathMatch = q.match(/(\d+)\s*([\+\-\*\/])\s*(\d+)/);
    if (mathMatch) {
        const a = parseFloat(mathMatch[1]), op = mathMatch[2], b = parseFloat(mathMatch[3]);
        let result;
        if (op === '+') result = a + b;
        else if (op === '-') result = a - b;
        else if (op === '*') result = a * b;
        else if (op === '/') result = a / b;
        if (result !== undefined) return { text: 'Answer: ' + result + '. Expert: ' + top.name + ' (' + (top.weight*100).toFixed(1) + '%).', experts: experts, source: 'math', bundle: bundle.name };
    }
    if (q.match(/^(hi|hello|hey)$/)) return { text: 'Hello! I am ' + bundle.name + '. How can I help?', experts: experts, source: 'greeting', bundle: bundle.name };
    return { text: 'Query: "' + query + '"\nExpert: ' + top.name + ' (' + (top.weight*100).toFixed(1) + '%)', experts: experts, source: 'default', bundle: bundle.name };
}

const server = http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }

    if (url === '/api/bundles' && req.method === 'GET') {
        const bundles = Object.values(loadedBundles).map(b => ({ id: b.id, name: b.name, experts: b.experts.length, active: activeBundle && activeBundle.id === b.id }));
        res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ bundles, active: activeBundle ? activeBundle.id : null })); return;
    }

    if (url === '/api/bundle/switch' && req.method === 'POST') {
        let body = '';
        req.on('data', c => body += c);
        req.on('end', () => {
            const { bundleId } = JSON.parse(body);
            const result = setActiveBundle(bundleId);
            res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(result));
        });
        return;
    }

    if (url === '/api/micronaut/route' && req.method === 'POST') {
        let body = '';
        req.on('data', c => body += c);
        req.on('end', () => {
            const { query } = JSON.parse(body);
            const experts = selectExperts(query, activeBundle);
            res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ experts, bundle: activeBundle ? activeBundle.name : null }));
        });
        return;
    }

    if (url === '/api/micronaut/chat' && req.method === 'POST') {
        let body = '';
        req.on('data', c => body += c);
        req.on('end', async () => {
            const { query } = JSON.parse(body);
            const experts = selectExperts(query, activeBundle);
            const result = await generateWithGGUF(query, experts, activeBundle);
            res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(result));
        });
        return;
    }

    if (url === '/api/micronaut/train' && req.method === 'POST') {
        let body = '';
        req.on('data', c => body += c);
        req.on('end', () => {
            const { expertId, reward, learningRate } = JSON.parse(body);
            if (activeBundle) {
                const lr = learningRate || 0.01;
                const current = activeBundle.learned.biases[expertId] || 0;
                activeBundle.learned.biases[expertId] = current + lr * (reward || 1.0);
                const bundlePath = path.join(BUNDLES_DIR, activeBundle.id + '.bson');
                fs.writeFileSync(bundlePath, bson.serialize(activeBundle));
                res.writeHead(200, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ ok: true, expertId, newBias: activeBundle.learned.biases[expertId], saved: true }));
            } else {
                res.writeHead(400, { 'Content-Type': 'application/json' }); res.end(JSON.stringify({ error: 'No active bundle' }));
            }
        });
        return;
    }

    if (url === '/api/micronaut/experts' && req.method === 'GET') {
       
