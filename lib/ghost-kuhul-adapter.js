/* ============================================================
   ghost-kuhul-adapter.js — Ghost ⇄ KUHUL Sandbox Adapter v1.0.0
   Runs in the PARENT (Ghost shell, index.html context).

   Responsibilities:
   - Create/manage the sandbox iframe (Canvas tab)
   - PostMessage RPC to kuhul-sandbox-bridge.js inside iframe
   - Enforce "JS only in canvas" policy by never executing page JS in parent
   - Persist per-URL canvas session state (open/closed, last URL, caps, token)
     using localStorage (IDB optional later)

   Works with:
   - kuhul-sandbox-bridge.js (inside iframe)

   Usage (example):
     const KUHUL = GhostKUHUL.create({
       iframeEl: document.querySelector("#canvasFrame"),
       statusEl: document.querySelector("#canvasStatus"),
       storageKey: "ghost.canvas.sessions.v1",
       parentOrigin: window.location.origin,
     });

     KUHUL.restore();              // restore last open canvas tabs
     KUHUL.open("https://google.com");
     KUHUL.close();                // hides iframe but preserves session state

   ============================================================ */

(() => {
  "use strict";

  /* ------------------------- small utils ------------------------- */

  const now = () => Date.now();

  const safeJSON = {
    parse(s) { try { return JSON.parse(s); } catch { return null; } },
    stringify(v) { try { return JSON.stringify(v); } catch { return null; } }
  };

  const clampStr = (s, max = 4096) => {
    s = (s == null) ? "" : String(s);
    return s.length > max ? s.slice(0, max) : s;
  };

  const isObj = (x) => !!x && typeof x === "object" && !Array.isArray(x);

  const uid = () => "gk_" + Math.random().toString(16).slice(2) + "_" + now().toString(16);

  function pick(obj, keys) {
    const out = {};
    for (const k of keys) if (k in obj) out[k] = obj[k];
    return out;
  }

  function normalizeURL(input) {
    const s = clampStr(input, 4096).trim();
    if (!s) return null;
    try {
      // allow user to type "google.com"
      const u = new URL(s.includes("://") ? s : ("https://" + s));
      return u.toString();
    } catch {
      return null;
    }
  }

  function sameOrigin(urlA, urlB) {
    try { return new URL(urlA).origin === new URL(urlB).origin; } catch { return false; }
  }

  /* --------------------- session persistence --------------------- */

  function loadStore(key) {
    try {
      const raw = localStorage.getItem(key);
      const v = safeJSON.parse(raw);
      return isObj(v) ? v : { v: 1, sessions: {}, lastActiveId: null };
    } catch {
      return { v: 1, sessions: {}, lastActiveId: null };
    }
  }

  function saveStore(key, data) {
    try {
      const raw = safeJSON.stringify(data);
      if (!raw) return false;
      localStorage.setItem(key, raw);
      return true;
    } catch {
      return false;
    }
  }

  /* --------------------- RPC / postMessage ---------------------- */

  function createRPC({ parentOrigin }) {
    const pending = new Map();

    function onMessage(evt) {
      const d = evt.data;
      if (!d || typeof d !== "object") return;
      // Optionally pin origin: in many sandbox cases evt.origin may be "null".
      // We still accept replies but we require reqId to match.
      if (!d.reqId || typeof d.reqId !== "string") return;

      const p = pending.get(d.reqId);
      if (!p) return;

      if (d.type === "kuhul:ok") {
        pending.delete(d.reqId);
        p.resolve({ ok: true, payload: d.payload, raw: d });
      } else if (d.type === "kuhul:err") {
        pending.delete(d.reqId);
        p.resolve({ ok: false, error: d.payload, raw: d });
      } else if (d.type === "kuhul:bridge.ready") {
        // broadcast style event; doesn't resolve a pending request
      }
    }

    window.addEventListener("message", onMessage);

    function call(iframeWin, type, payload, { token, timeoutMs = 8000 } = {}) {
      if (!iframeWin) return Promise.resolve({ ok: false, error: { code: "NO_IFRAME", message: "No iframe window" } });
      const reqId = uid();
      const msg = { type, reqId, payload: payload || {} };
      if (token) msg.token = token;

      return new Promise((resolve) => {
        const t = setTimeout(() => {
          pending.delete(reqId);
          resolve({ ok: false, error: { code: "TIMEOUT", message: "No response" } });
        }, Math.max(500, Math.min(timeoutMs, 60000)));

        pending.set(reqId, {
          resolve: (r) => {
            clearTimeout(t);
            resolve(r);
          }
        });

        // targetOrigin: allow "*" because sandbox origin may be null
        try { iframeWin.postMessage(msg, "*"); }
        catch {
          clearTimeout(t);
          pending.delete(reqId);
          resolve({ ok: false, error: { code: "POST_FAIL", message: "postMessage failed" } });
        }
      });
    }

    return { call };
  }

  /* --------------------- Sandbox Document ---------------------- */

  // We load the iframe using srcdoc so we control the bridge.
  // The external URL is rendered inside a nested <iframe> so its JS
  // stays confined to THAT inner iframe.
  //
  // Outer iframe (this) = same-origin with parent (because srcdoc),
  // contains kuhul-sandbox-bridge.js and UI chrome.
  // Inner iframe = navigates to user URL with sandbox restrictions.
  //
  // This prevents external page JS from accessing bridge directly.
  function buildCanvasSrcdoc({ bridgeSrc = "kuhul-sandbox-bridge.js", initialURL = "about:blank" }) {
    const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");

    // Inner sandbox attributes:
    // - allow-scripts: allow JS, but only inside inner frame
    // - allow-forms: optional, helps login forms
    // - allow-popups: optional, many sites use it
    // - allow-top-navigation-by-user-activation: optional for links
    // - DO NOT allow-same-origin (keeps origin opaque -> reduces risk)
    const innerSandbox = [
      "allow-scripts",
      "allow-forms",
      "allow-popups",
      "allow-downloads",
      "allow-top-navigation-by-user-activation"
    ].join(" ");

    return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>KUHUL Canvas</title>
  <style>
    :root{
      --bg:#050812; --panel:#070b16; --line:rgba(22,242,170,.25);
      --txt:#d9fff5; --muted:rgba(217,255,245,.65);
      --accent:#16f2aa; --warn:#ffcc66;
      --r:14px;
      color-scheme: dark;
    }
    html,body{height:100%;margin:0;background:var(--bg);color:var(--txt);font:12px ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;}
    .wrap{height:100%;display:flex;flex-direction:column;}
    .bar{display:flex;gap:8px;align-items:center;padding:10px;background:linear-gradient(180deg,var(--panel),rgba(7,11,22,.7));border-bottom:1px solid var(--line);}
    .pill{padding:6px 10px;border:1px solid var(--line);border-radius:999px;color:var(--muted);}
    .url{flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
    .btn{cursor:pointer;padding:6px 10px;border-radius:10px;border:1px solid var(--line);background:rgba(255,255,255,.03);color:var(--txt);}
    .btn:hover{border-color:rgba(22,242,170,.5)}
    .frameWrap{flex:1;min-height:0;background:#000;}
    iframe#page{width:100%;height:100%;border:0;background:#000;}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="bar">
      <div class="pill">CANVAS</div>
      <div class="pill url" id="urlLabel">${esc(initialURL)}</div>
      <button class="btn" id="btnReload" title="Reload page">Reload</button>
      <button class="btn" id="btnBlank" title="Go blank">Blank</button>
    </div>
    <div class="frameWrap">
      <iframe id="page" sandbox="${innerSandbox}" referrerpolicy="no-referrer" src="${esc(initialURL)}"></iframe>
    </div>
  </div>

  <script src="${esc(bridgeSrc)}"></script>
  <script>
    // Minimal local UI controls (not exposed to parent except through bridge ops)
    (function(){
      const page = document.getElementById('page');
      const urlLabel = document.getElementById('urlLabel');
      document.getElementById('btnReload').addEventListener('click', ()=> {
        try { page.contentWindow.location.reload(); } catch { page.src = page.src; }
      });
      document.getElementById('btnBlank').addEventListener('click', ()=> {
        page.src = 'about:blank';
        urlLabel.textContent = 'about:blank';
      });

      // Listen for parent navigation command via bridge messages:
      window.addEventListener('message', (evt)=>{
        const d = evt.data;
        if(!d || typeof d !== 'object') return;
        if(d.type === 'kuhul:nav' && d.payload && typeof d.payload.url === 'string'){
          const u = d.payload.url;
          page.src = u;
          urlLabel.textContent = u;
        }
      });
    })();
  </script>
</body>
</html>`;
  }

  /* --------------------- Main Adapter Class ---------------------- */

  class GhostKUHULAdapter {
    constructor(opts = {}) {
      this.opts = {
        storageKey: opts.storageKey || "ghost.canvas.sessions.v1",
        parentOrigin: opts.parentOrigin || window.location.origin,
        iframeEl: opts.iframeEl || null,
        statusEl: opts.statusEl || null,
        bridgeSrc: opts.bridgeSrc || "kuhul-sandbox-bridge.js",
        // default caps: JS can only run via scriptRegistry (not raw code)
        caps: Object.assign({
          dom_read: false,
          dom_write: false,
          net_fetch: false,
          storage: true,
          js_run: false,
          console: true
        }, opts.caps || {})
      };

      this.store = loadStore(this.opts.storageKey);
      this.rpc = createRPC({ parentOrigin: this.opts.parentOrigin });

      // active session
      this.activeId = this.store.lastActiveId;
      this.ready = false;
      this._bridgeReadySeen = false;

      this._listenBridgeReady();
    }

    _listenBridgeReady() {
      window.addEventListener("message", (evt) => {
        const d = evt.data;
        if (!d || typeof d !== "object") return;
        if (d.type === "kuhul:bridge.ready") {
          this._bridgeReadySeen = true;
          this._setStatus(`canvas bridge ready (${d?.payload?.href || ""})`);
          // if we have an active session, init it
          if (this.activeId) this._initActive().catch(() => {});
        }
      });
    }

    _setStatus(text) {
      if (!this.opts.statusEl) return;
      this.opts.statusEl.textContent = clampStr(text, 2000);
    }

    _persist() {
      this.store.lastActiveId = this.activeId || null;
      saveStore(this.opts.storageKey, this.store);
    }

    _ensureIframe() {
      if (!this.opts.iframeEl) throw new Error("Missing iframeEl");
      return this.opts.iframeEl;
    }

    _session(id) {
      return this.store.sessions[id] || null;
    }

    _createSession(url) {
      const id = uid();
      const token = uid(); // token used to authenticate parent → bridge (optional)
      const s = {
        id,
        createdAt: now(),
        updatedAt: now(),
        url,
        open: true,
        token,
        caps: Object.assign({}, this.opts.caps)
      };
      this.store.sessions[id] = s;
      this.activeId = id;
      this._persist();
      return s;
    }

    _buildSrcdocForSession(s) {
      return buildCanvasSrcdoc({
        bridgeSrc: this.opts.bridgeSrc,
        initialURL: s.url || "about:blank"
      });
    }

    async _initActive() {
      const s = this._session(this.activeId);
      if (!s) return;

      const iframe = this._ensureIframe();
      if (!iframe.contentWindow) return;

      // Send init to bridge (in outer srcdoc)
      const res = await this.rpc.call(
        iframe.contentWindow,
        "kuhul:init",
        {
          parentOrigin: "*", // bridge uses this for its own outbound postMessage; keep wildcard
          token: s.token,
          caps: s.caps
        },
        { token: s.token, timeoutMs: 6000 }
      );

      if (res.ok) {
        this.ready = true;
        this._setStatus("canvas active");
      } else {
        this._setStatus(`canvas init error: ${res?.error?.code || "ERR"}`);
      }
    }

    /* ---------------- Public API ---------------- */

    restore() {
      // If there was an open session last time, re-open it.
      const id = this.store.lastActiveId;
      if (!id) return false;
      const s = this._session(id);
      if (!s) return false;

      // If it was open, show it again.
      if (s.open) {
        this.open(s.url, { reuse: true, sessionId: id });
        return true;
      }
      return false;
    }

    open(url, { reuse = false, sessionId = null } = {}) {
      const u = normalizeURL(url);
      if (!u) {
        this._setStatus("bad url");
        return null;
      }

      let s = null;

      if (reuse && sessionId && this._session(sessionId)) {
        s = this._session(sessionId);
        s.url = u;
        s.open = true;
        s.updatedAt = now();
        this.activeId = s.id;
      } else {
        s = this._createSession(u);
      }

      const iframe = this._ensureIframe();
      iframe.style.display = "block";
      iframe.setAttribute("data-kuhul-session", s.id);

      // Load outer frame
      iframe.srcdoc = this._buildSrcdocForSession(s);

      // Persist
      this._persist();

      this._setStatus("loading canvas…");
      return s.id;
    }

    close() {
      const iframe = this._ensureIframe();
      iframe.style.display = "none";

      if (this.activeId && this._session(this.activeId)) {
        const s = this._session(this.activeId);
        s.open = false;
        s.updatedAt = now();
      }

      this._persist();
      this._setStatus("canvas closed (session saved)");
    }

    toggle() {
      const iframe = this._ensureIframe();
      if (iframe.style.display === "none" || getComputedStyle(iframe).display === "none") this.reopen();
      else this.close();
    }

    reopen() {
      if (!this.activeId) return false;
      const s = this._session(this.activeId);
      if (!s) return false;

      s.open = true;
      s.updatedAt = now();

      const iframe = this._ensureIframe();
      iframe.style.display = "block";

      // If the iframe is already loaded, just show it. If not, reload.
      if (!iframe.srcdoc) iframe.srcdoc = this._buildSrcdocForSession(s);

      this._persist();
      this._setStatus("canvas open");
      return true;
    }

    navigate(url) {
      const u = normalizeURL(url);
      if (!u) {
        this._setStatus("bad url");
        return Promise.resolve(false);
      }

      if (!this.activeId) this._createSession(u);
      const s = this._session(this.activeId);
      s.url = u;
      s.updatedAt = now();
      s.open = true;
      this._persist();

      const iframe = this._ensureIframe();
      iframe.style.display = "block";

      // If outer is not loaded yet, reload srcdoc
      if (!iframe.contentWindow || !this._bridgeReadySeen) {
        iframe.srcdoc = this._buildSrcdocForSession(s);
        this._setStatus("loading canvas…");
        return Promise.resolve(true);
      }

      // Send a nav command to outer frame UI shim (not via bridge ops)
      try {
        iframe.contentWindow.postMessage({ type: "kuhul:nav", payload: { url: u } }, "*");
        this._setStatus("navigated");
      } catch {
        this._setStatus("nav failed");
      }

      return Promise.resolve(true);
    }

    // Optional: call bridge ops (dom/net/storage/js registry)
    call(op, payload = {}, { timeoutMs = 8000 } = {}) {
      const iframe = this._ensureIframe();
      if (!this.activeId) return Promise.resolve({ ok: false, error: { code: "NO_SESSION", message: "No active session" } });
      const s = this._session(this.activeId);
      if (!s) return Promise.resolve({ ok: false, error: { code: "NO_SESSION", message: "Missing session" } });

      return this.rpc.call(
        iframe.contentWindow,
        op,
        payload,
        { token: s.token, timeoutMs }
      );
    }

    // Convenience wrappers
    async storageGet(key) { return this.call("kuhul:storage.get", { key }); }
    async storageSet(key, value) { return this.call("kuhul:storage.set", { key, value }); }
    async fetch(url, opts = {}) { return this.call("kuhul:net.fetch", Object.assign({ url }, opts)); }

    listSessions() {
      return Object.values(this.store.sessions).map(s => pick(s, ["id","url","open","updatedAt","createdAt"]));
    }

    setCaps(capsPatch = {}) {
      if (!this.activeId) return false;
      const s = this._session(this.activeId);
      if (!s) return false;
      for (const k of Object.keys(s.caps)) {
        if (k in capsPatch) s.caps[k] = !!capsPatch[k];
      }
      s.updatedAt = now();
      this._persist();
      // re-init bridge with updated caps if possible
      this._initActive().catch(() => {});
      return true;
    }
  }

  /* --------------------- Public Export ---------------------- */

  window.GhostKUHUL = {
    create(opts) { return new GhostKUHULAdapter(opts); }
  };
})();
