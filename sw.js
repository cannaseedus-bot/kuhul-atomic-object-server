/* Browser carrier: static shell caching only. Server owns object and inference execution. */
'use strict';
const CACHE_NAME = 'kuhul-atomic-shell-v15';
const scope = new URL('./', self.registration.scope);
self.addEventListener('install', event => {
  event.waitUntil((async () => {
    const response = await fetch(new URL('manifest.json', scope), { cache: 'no-store' });
    if (!response.ok) throw Error('Manifest unavailable');
    const manifest = await response.json();
    const cache = await caches.open(CACHE_NAME);
    await cache.addAll(manifest.shell.assets.map(asset => new URL(asset, scope).href));
    await self.skipWaiting();
  })());
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const name of await caches.keys()) {
      if (name !== CACHE_NAME && (name.startsWith('kuhul-atomic-shell-') ||
        name.startsWith('kuhul-lam-o-') || name.startsWith('kuhul-xjson-cache-'))) await caches.delete(name);
    }
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const request = event.request, url = new URL(request.url);
  if (url.origin !== scope.origin) return;
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(fetch(request).catch(() => new Response(JSON.stringify({
      error: 'Server unavailable. Object writes require the orchestrator; no changes were committed.'
    }), { status: 503, headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } })));
    return;
  }
  if (request.method !== 'GET') return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE_NAME);
    const cached = await cache.match(request);
    // Only cache the explicit shell assets installed from the manifest.
    try {
      const response = await fetch(request);
      if (response.ok && cached) await cache.put(request, response.clone());
      return response;
    } catch {
      return cached || new Response('Not available offline', { status: 503 });
    }
  })());
});
self.addEventListener('message', event => {
  const reply = value => event.ports[0]?.postMessage(value);
  event.waitUntil((async () => {
    try {
      switch (event.data?.type) {
        case 'SKIP_WAITING': await self.skipWaiting(); reply({ success: true }); break;
        case 'KUHUL_CLEAR_CACHE': await caches.delete(CACHE_NAME); reply({ success: true }); break;
        case 'KUHUL_HEALTH_CHECK': {
          const response = await fetch(new URL('api/health', scope));
          const health = await response.json();
          reply({ orchestrator: true, ollama: !!health.ollama?.connected }); break;
        }
        case 'KUHUL_GET_MODELS': {
          const response = await fetch(new URL('api/models', scope));
          reply(await response.json()); break;
        }
        default: reply({ error: 'Unknown carrier message' });
      }
    } catch (error) { reply({ error: error.message }); }
  })());
});
