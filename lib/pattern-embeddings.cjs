// Pattern embedding + cosine retrieval over Ollama's embedding model.
// Pure math is deterministic and network-free; embedMany/embedOne are the only I/O.
const EMBEDDING_ENDPOINT = 'http://127.0.0.1:11434';
const EMBEDDING_MODEL = 'embeddinggemma:latest';

function embeddableText(pattern) {
  return String(pattern || '').toUpperCase().replace(/[^\p{L}\p{N}]+/gu, ' ').replace(/\s+/g, ' ').trim();
}

function cosineSimilarity(a, b) {
  let dot = 0, na = 0, nb = 0;
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) { dot += a[i] * b[i]; na += a[i] * a[i]; nb += b[i] * b[i]; }
  if (!na || !nb) return 0;
  return dot / (Math.sqrt(na) * Math.sqrt(nb));
}

function rank(queryVector, vectors) {
  return vectors
    .map((vec, index) => ({ index, score: cosineSimilarity(queryVector, vec) }))
    .sort((a, b) => b.score - a.score);
}

async function embedMany(texts, endpoint = EMBEDDING_ENDPOINT, model = EMBEDDING_MODEL) {
  const response = await fetch(endpoint + '/api/embed', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ model, input: texts })
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw Error('embed backend HTTP ' + response.status + ': ' + JSON.stringify(data).slice(0, 400));
  return data.embeddings || [];
}

async function embedOne(text, endpoint = EMBEDDING_ENDPOINT, model = EMBEDDING_MODEL) {
  const [vector] = await embedMany([text], endpoint, model);
  if (!vector) throw Error('embed backend returned no vector');
  return vector;
}

module.exports = { EMBEDDING_ENDPOINT, EMBEDDING_MODEL, embeddableText, cosineSimilarity, rank, embedMany, embedOne };
