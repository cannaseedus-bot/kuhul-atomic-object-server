/* ============================================================
   kuhul-sandbox-bridge.js — KUHUL Sandbox Bridge v1.0.0
   Runs INSIDE the sandboxed iframe (canvas tab).
   Purpose:
   - Provide a strict postMessage bridge for the Ghost shell
   - Enforce allowlisted ops + per-session capabilities
   - Contain any JavaScript execution to the sandbox only
   - Optionally provide a tiny, capability-gated "script runner"

   SECURITY PRINCIPLES
   - No ambient authority: all actions must be requested via ops
   - Strict origin pinning (optional): only accept messages from parent
   - Deny-by-default policy: unknown op == reject
   - Harden globals: disable eval/Function, lock down dangerous APIs
   - Do not expose full DOM to parent; only safe responses via postMessage

   NOTE
   - This file should be injected into the iframe document (srcdoc)
     or hosted at a same-origin sandbox URL (recommended).
   - The parent shell should send {type:"kuhul:init", ...} first.

   ============================================================ */

(() => {
  "use strict";

  /* ----------------------------- Utilities ----------------------------- */

  const now = () => Date.now();

  const safeJSON = {
    parse(s) {
      try { return JSON.parse(s); } catch { return null; }
    },
    stringify(v) {
      try { return JSON.stringify(v); } catch { return null; }
    }
  };

  function clampStr(s, max = 4096) {
    s = (s == null) ? "" : String(s);
    return s.length > max ? s.slice(0, max) : s;
  }

  function clampObj(obj, maxJson = 100_000) {
    const j = safeJSON.stringify(obj);
    if (!j) return { __clamped__: true, __reason__: "unserializable" };
    if (j.length <= maxJson) return obj;
    // If too big, truncate by returning summary
    return { __clamped__: true, __reason__: "too_large", __json_len__: j.length };
  }

  function isPlainObject(x) {
    return !!x && typeof x === "object" && (Object.getPrototypeOf(x) === Object.prototype || Object.getPrototypeOf(x) === null);
  }

  function uid() {
    // deterministic-ish, no crypto requirement
    return "kmsg_" + Math.random().toString(16).slice(2) + "_" + now().toString(16);
  }

  /* ----------------------------- Harden ----------------------------- */

  // Attempt to disable dynamic code execution inside sandbox.
  // (Some environments may not allow redefining; we try best-effort.)
  function hardenDynamicCode() {
    try { Object.defineProperty(window, "eval", { value: undefined, configurable: false, writable: false }); } catch {}
    try { Object.defineProperty(window, "Function", { value: undefined, configurable: false, writable: false }); } catch {}
  }

  // Remove access to some high-risk APIs (best-effort; sandbox should already restrict)
  function hardenHighRiskAPIs() {
    const denyList = [
      "showOpenFilePicker",
      "showSaveFilePicker",
      "showDirectoryPicker",
      "webkitRequestFileSystem",
      "requestFileSystem",
      "openDatabase" // old WebSQL
    ];
    for (const k of denyList) {
      try { if (k in window) Object.defineProperty(window, k, { value: undefined, configurable: false, writable: false }); } catch {}
    }
  }

  hardenDynamicCode();
  hardenHighRiskAPIs();

  /* ----------------------------- State ----------------------------- */

  const BRIDGE = {
    v: "1.0.0",
    // Parent pinning (optional). If set, only accept messages from this origin.
    parentOrigin: "*",
    // Session auth token (optional). If set, messages must include matching token.
    token: null,
    // Capabilities granted to this sandbox tab (deny-by-default).
    caps: {
      dom_read: false,
      dom_write: false,
      net_fetch: false,
      storage: false,
      js_run: false,
      console: true
    },
    // Op allowlist: only these message types will be honored.
    allowOps: new Set([
      "kuhul:init",
      "kuhul:ping",
      "kuhul:capabilities",
      "kuhul:dom.query",
      "kuhul:dom.get",
      "kuhul:dom.setText",
      "kuhul:dom.setHTML",
      "kuhul:dom.setAttr",
      "kuhul:dom.addClass",
      "kuhul:dom.removeClass",
      "kuhul:dom.style",
      "kuhul:net.fetch",
      "kuhul:storage.get",
      "kuhul:storage.set",
      "kuhul:storage.del",
      "kuhul:js.run",
      "kuhul:console.log",
      "kuhul:console.warn",
      "kuhul:console.error"
    ]),
    // Rate limiting
    rate: {
      windowMs: 1000,
      max: 120,
      bucket: [],
      blockedUntil: 0
    },
    // A tiny "script registry" so JS can be *selected* not injected:
    // parent sends an id and args; bridge executes registered function only.
    scriptRegistry: Object.create(null),
    // Message correlation
    pending: new Map()
  };

  /* ----------------------------- Messaging ----------------------------- */

  function post(type, payload = {}, reqId = null) {
    const msg = {
      type,
      v: BRIDGE.v,
      ts: now(),
      reqId: reqId || null,
      payload: clampObj(payload)
    };
    try {
      window.parent.postMessage(msg, BRIDGE.parentOrigin);
    } catch {
      // no-op
    }
  }

  function ok(reqId, payload = {}) {
    post("kuhul:ok", payload, reqId);
  }

  function err(reqId, code, message, extra = {}) {
    post("kuhul:err", { code, message: clampStr(message, 2000), extra: clampObj(extra) }, reqId);
  }

  function deny(reqId, reason = "denied") {
    err(reqId, "DENY", reason);
  }

  /* ----------------------------- Rate Limit ----------------------------- */

  function rateCheck() {
    const t = now();
    const r = BRIDGE.rate;
    if (t < r.blockedUntil) return false;

    r.bucket = r.bucket.filter(x => (t - x) < r.windowMs);
    if (r.bucket.length >= r.max) {
      r.blockedUntil = t + 1500; // 1.5s cooloff
      return false;
    }
    r.bucket.push(t);
    return true;
  }

  /* ----------------------------- Auth / Validation ----------------------------- */

  function validMessage(evt) {
    // parentOrigin pinning (optional)
    if (BRIDGE.parentOrigin !== "*" && evt.origin !== BRIDGE.parentOrigin) return false;

    const d = evt.data;
    if (!d || typeof d !== "object") return false;

    if (!d.type || typeof d.type !== "string") return false;
    if (!BRIDGE.allowOps.has(d.type)) return false;

    // token check (optional)
    if (BRIDGE.token && d.token !== BRIDGE.token) return false;

    // reqId optional but recommended
    if (d.reqId != null && typeof d.reqId !== "string") return false;

    // payload must be object or undefined
    if (d.payload != null && !isPlainObject(d.payload)) return false;

    return true;
  }

  function requireCap(reqId, capName) {
    if (!BRIDGE.caps[capName]) {
      deny(reqId, `capability_required:${capName}`);
      return false;
    }
    return true;
  }

  /* ----------------------------- DOM Helpers ----------------------------- */

  function q(sel) {
    if (typeof sel !== "string") return null;
    sel = sel.trim();
    if (!sel || sel.length > 512) return null;
    try { return document.querySelector(sel); } catch { return null; }
  }

  function qAll(sel) {
    if (typeof sel !== "string") return [];
    sel = sel.trim();
    if (!sel || sel.length > 512) return [];
    try { return Array.from(document.querySelectorAll(sel)); } catch { return []; }
  }

  function elSnapshot(el) {
    if (!el) return null;
    const tag = (el.tagName || "").toLowerCase();
    const id = el.id || "";
    const cls = (el.className && typeof el.className === "string") ? el.className : "";
    return { tag, id, class: clampStr(cls, 512) };
  }

  /* ----------------------------- Storage (localStorage only) ----------------------------- */

  const storage = {
    get(k) {
      k = clampStr(k, 256);
      if (!k) return null;
      try {
        const v = localStorage.getItem(k);
        return v == null ? null : v;
      } catch { return null; }
    },
    set(k, v) {
      k = clampStr(k, 256);
      if (!k) return false;
      v = clampStr(v, 200_000);
      try { localStorage.setItem(k, v); return true; } catch { return false; }
    },
    del(k) {
      k = clampStr(k, 256);
      if (!k) return false;
      try { localStorage.removeItem(k); return true; } catch { return false; }
    }
  };

  /* ----------------------------- Net (fetch wrapper) ----------------------------- */

  async function safeFetch(reqId, p) {
    if (!requireCap(reqId, "net_fetch")) return;

    const url = clampStr(p?.url, 4096);
    if (!url) return err(reqId, "BAD_URL", "Missing url");

    // Method allowlist
    const method = String(p?.method || "GET").toUpperCase();
    const allowedMethods = new Set(["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"]);
    if (!allowedMethods.has(method)) return err(reqId, "BAD_METHOD", "Method not allowed");

    // Headers: allowlist only, and clamp values
    const inHeaders = isPlainObject(p?.headers) ? p.headers : {};
    const headers = new Headers();
    const headerAllow = new Set([
      "accept",
      "accept-language",
      "content-type",
      "x-kuhul",
      "x-kuhul-tab",
      "x-requested-with"
    ]);
    for (const [k, v] of Object.entries(inHeaders)) {
      const kk = String(k).toLowerCase();
      if (!headerAllow.has(kk)) continue;
      headers.set(kk, clampStr(v, 1024));
    }

    // Body (string only)
    let body = undefined;
    if (p?.body != null) {
      if (typeof p.body !== "string") return err(reqId, "BAD_BODY", "Body must be string");
      body = clampStr(p.body, 500_000);
    }

    // Mode/credentials locked down (sandbox should already help)
    const opts = {
      method,
      headers,
      body,
      mode: "cors",
      credentials: "omit",
      redirect: "follow",
      referrerPolicy: "no-referrer"
    };

    // Timeout (best-effort)
    const timeoutMs = Math.min(Math.max(Number(p?.timeoutMs || 12000), 1000), 60000);
    const ac = new AbortController();
    const t = setTimeout(() => ac.abort("timeout"), timeoutMs);

    try {
      const res = await fetch(url, { ...opts, signal: ac.signal });
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      const status = res.status;

      // Limit response size by reading as text with clamp
      let text = "";
      try {
        text = await res.text();
      } catch {
        text = "";
      }
      text = clampStr(text, 600_000);

      ok(reqId, {
        status,
        ok: res.ok,
        contentType: ct,
        url: res.url,
        text
      });
    } catch (e) {
      err(reqId, "FETCH_FAIL", "Fetch failed", { name: e?.name, message: String(e?.message || e) });
    } finally {
      clearTimeout(t);
    }
  }

  /* ----------------------------- Script Runner ----------------------------- */

  // IMPORTANT:
  // - If you want to allow "running JS", do NOT accept raw code strings.
  // - Accept only registered script IDs.
  // - Parent may load scripts by navigating to pages that include:
  //   <script type="application/kuhul-script" data-id="...">{...}</script>
  //   and you map them to safe functions (optional).
  function registerScript(id, fn) {
    id = clampStr(id, 128);
    if (!id || typeof fn !== "function") return false;
    BRIDGE.scriptRegistry[id] = fn;
    return true;
  }

  async function runScript(reqId, p) {
    if (!requireCap(reqId, "js_run")) return;

    const scriptId = clampStr(p?.id, 128);
    if (!scriptId) return err(reqId, "BAD_SCRIPT", "Missing script id");

    const fn = BRIDGE.scriptRegistry[scriptId];
    if (typeof fn !== "function") return err(reqId, "NO_SCRIPT", `No such script: ${scriptId}`);

    // Args must be JSON-serializable object
    const args = isPlainObject(p?.args) ? p.args : {};
    try {
      const out = await fn(args, { post, ok, err });
      ok(reqId, { id: scriptId, out: clampObj(out) });
    } catch (e) {
      err(reqId, "SCRIPT_FAIL", "Script execution failed", { id: scriptId, message: String(e?.message || e) });
    }
  }

  // A default script example (harmless)
  registerScript("kuhul.echo", async (args) => ({ echo: args }));

  /* ----------------------------- Handlers ----------------------------- */

  async function handle(evt) {
    if (!rateCheck()) return;

    if (!validMessage(evt)) return;

    const { type, reqId = uid(), payload = {}, token } = evt.data;

    switch (type) {
      case "kuhul:init": {
        // payload: { parentOrigin, token, caps }
        const po = payload.parentOrigin;
        const tk = payload.token;
        const caps = payload.caps;

        if (typeof po === "string" && po.length <= 256) BRIDGE.parentOrigin = po;
        if (typeof tk === "string" && tk.length <= 256) BRIDGE.token = tk;

        if (isPlainObject(caps)) {
          for (const k of Object.keys(BRIDGE.caps)) {
            if (k in caps) BRIDGE.caps[k] = !!caps[k];
          }
        }

        ok(reqId, {
          v: BRIDGE.v,
          parentOrigin: BRIDGE.parentOrigin,
          token: BRIDGE.token ? "set" : "none",
          caps: BRIDGE.caps,
          ready: true
        });
        break;
      }

      case "kuhul:ping": {
        ok(reqId, { pong: true, ts: now(), href: location.href });
        break;
      }

      case "kuhul:capabilities": {
        ok(reqId, { caps: BRIDGE.caps });
        break;
      }

      /* ---------------- DOM READ ---------------- */

      case "kuhul:dom.query": {
        if (!requireCap(reqId, "dom_read")) return;
        const sel = payload.selector;
        const all = !!payload.all;

        if (all) {
          const nodes = qAll(sel).slice(0, 100).map(elSnapshot);
          ok(reqId, { selector: clampStr(sel, 512), count: nodes.length, nodes });
        } else {
          const el = q(sel);
          ok(reqId, { selector: clampStr(sel, 512), node: elSnapshot(el) });
        }
        break;
      }

      case "kuhul:dom.get": {
        if (!requireCap(reqId, "dom_read")) return;
        const el = q(payload.selector);
        if (!el) return err(reqId, "NO_NODE", "No node for selector");

        const mode = String(payload.mode || "text");
        if (mode === "text") {
          ok(reqId, { text: clampStr(el.textContent, 200_000), node: elSnapshot(el) });
        } else if (mode === "html") {
          ok(reqId, { html: clampStr(el.innerHTML, 200_000), node: elSnapshot(el) });
        } else if (mode === "value") {
          // for inputs
          ok(reqId, { value: clampStr(el.value, 200_000), node: elSnapshot(el) });
        } else {
          err(reqId, "BAD_MODE", "mode must be text|html|value");
        }
        break;
      }

      /* ---------------- DOM WRITE ---------------- */

      case "kuhul:dom.setText": {
        if (!requireCap(reqId, "dom_write")) return;
        const el = q(payload.selector);
        if (!el) return err(reqId, "NO_NODE", "No node for selector");
        el.textContent = clampStr(payload.text, 200_000);
        ok(reqId, { ok: true, node: elSnapshot(el) });
        break;
      }

      case "kuhul:dom.setHTML": {
        if (!requireCap(reqId, "dom_write")) return;
        const el = q(payload.selector);
        if (!el) return err(reqId, "NO_NODE", "No node for selector");
        // WARNING: even in sandbox, HTML injection can be dangerous.
        // Recommended: keep dom_write off for untrusted pages.
        el.innerHTML = clampStr(payload.html, 200_000);
        ok(reqId, { ok: true, node: elSnapshot(el) });
        break;
      }

      case "kuhul:dom.setAttr": {
        if (!requireCap(reqId, "dom_write")) return;
        const el = q(payload.selector);
        if (!el) return err(reqId, "NO_NODE", "No node for selector");
        const name = clampStr(payload.name, 128);
        const value = clampStr(payload.value, 2000);
        if (!name) return err(reqId, "BAD_ATTR", "Missing attr name");
        // disallow event handler attrs
        if (name.toLowerCase().startsWith("on")) return deny(reqId, "event_attrs_denied");
        el.setAttribute(name, value);
        ok(reqId, { ok: true, node: elSnapshot(el), name });
        break;
      }

      case "kuhul:dom.addClass": {
        if (!requireCap(reqId, "dom_write")) return;
        const el = q(payload.selector);
        if (!el) return err(reqId, "NO_NODE", "No node for selector");
        const cls = clampStr(payload.class, 256).split(/\s+/).filter(Boolean).slice(0, 8);
        cls.forEach(c => el.classList.add(c));
        ok(reqId, { ok: true, node: elSnapshot(el), added: cls });
        break;
      }

      case "kuhul:dom.removeClass": {
        if (!requireCap(reqId, "dom_write")) return;
        const el = q(payload.selector);
        if (!el) return err(reqId, "NO_NODE", "No node for selector");
        const cls = clampStr(payload.class, 256).split(/\s+/).filter(Boolean).slice(0, 8);
        cls.forEach(c => el.classList.remove(c));
        ok(reqId, { ok: true, node: elSnapshot(el), removed: cls });
        break;
      }

      case "kuhul:dom.style": {
        if (!requireCap(reqId, "dom_write")) return;
        const el = q(payload.selector);
        if (!el) return err(reqId, "NO_NODE", "No node for selector");
        const name = clampStr(payload.name, 128);
        const value = clampStr(payload.value, 512);
        if (!name) return err(reqId, "BAD_STYLE", "Missing style name");
        // deny url(...) to reduce exfil / surprises
        if (/url\s*\(/i.test(value)) return deny(reqId, "style_url_denied");
        el.style[name] = value;
        ok(reqId, { ok: true, node: elSnapshot(el), name });
        break;
      }

      /* ---------------- NET ---------------- */

      case "kuhul:net.fetch": {
        await safeFetch(reqId, payload);
        break;
      }

      /* ---------------- STORAGE ---------------- */

      case "kuhul:storage.get": {
        if (!requireCap(reqId, "storage")) return;
        const key = clampStr(payload.key, 256);
        const v = storage.get(key);
        ok(reqId, { key, value: v });
        break;
      }

      case "kuhul:storage.set": {
        if (!requireCap(reqId, "storage")) return;
        const key = clampStr(payload.key, 256);
        const value = clampStr(payload.value, 200_000);
        const okSet = storage.set(key, value);
        ok(reqId, { key, ok: okSet });
        break;
      }

      case "kuhul:storage.del": {
        if (!requireCap(reqId, "storage")) return;
        const key = clampStr(payload.key, 256);
        const okDel = storage.del(key);
        ok(reqId, { key, ok: okDel });
        break;
      }

      /* ---------------- SCRIPT RUN ---------------- */

      case "kuhul:js.run": {
        // payload: { id, args }
        await runScript(reqId, payload);
        break;
      }

      /* ---------------- CONSOLE (sandbox-safe) ---------------- */

      case "kuhul:console.log": {
        if (!BRIDGE.caps.console) return;
        console.log("[KUHUL]", payload);
        ok(reqId, { ok: true });
        break;
      }

      case "kuhul:console.warn": {
        if (!BRIDGE.caps.console) return;
        console.warn("[KUHUL]", payload);
        ok(reqId, { ok: true });
        break;
      }

      case "kuhul:console.error": {
        if (!BRIDGE.caps.console) return;
        console.error("[KUHUL]", payload);
        ok(reqId, { ok: true });
        break;
      }

      default: {
        deny(reqId, "unknown_op");
        break;
      }
    }
  }

  window.addEventListener("message", (evt) => {
    // Always swallow errors; never crash the sandbox
    Promise.resolve(handle(evt)).catch(() => {});
  });

  /* ----------------------------- Boot Signal ----------------------------- */

  post("kuhul:bridge.ready", {
    v: BRIDGE.v,
    href: location.href,
    ua: clampStr(navigator.userAgent, 256),
    note: "Sandbox bridge active. Send kuhul:init to set origin/token/caps."
  });

})();
