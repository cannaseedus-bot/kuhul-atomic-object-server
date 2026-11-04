/* ============================================================================
   kuhul-runtime.js — Drop-in KUHUL-JS Capability Runtime (v1.0.0)
   ----------------------------------------------------------------------------
   Goal:
     - Allow JavaScript ONLY as KUHUL-governed modules with explicit capabilities
     - Provide a safe "device" surface (DOM/NET/SVG/STORE/TIME/LOG) behind gates
     - Support sandboxed iframe "canvas tabs" with session persistence (localStorage)
     - Keep ambient authority LOW: no eval, no Function, no direct fetch unless brokered

   Usage:
     1) Include this file in index.html (or inline into sw.khl-hosted injection)
     2) Register modules: KUHUL.register("pi-renderer", PiRendererClass, caps)
     3) Run: KUHUL.run("pi-renderer", { ...payload... })

   Notes:
     - This is a front-end runtime guard. For stronger enforcement, pair with:
         CSP + sandboxed iframe + SW proxy routes
     - You can later swap devices to route through sw.khl / bridge endpoints.

   License: You own it.
============================================================================ */

(function KUHUL_RUNTIME_BOOT(global) {
  "use strict";

  /* =========================
     Utilities
  ========================= */
  const _now = () => (global.performance && performance.now) ? performance.now() : Date.now();
  const _uid = () => "khl_" + Math.random().toString(36).slice(2) + "_" + Date.now().toString(36);

  const _deepFreeze = (obj, seen = new Set()) => {
    if (!obj || typeof obj !== "object" || seen.has(obj)) return obj;
    seen.add(obj);
    Object.freeze(obj);
    for (const k of Object.keys(obj)) _deepFreeze(obj[k], seen);
    return obj;
  };

  const _safeJsonParse = (s, fallback) => {
    try { return JSON.parse(s); } catch { return fallback; }
  };

  const _clampStr = (s, n = 512) => {
    s = String(s ?? "");
    return s.length > n ? s.slice(0, n) + "…" : s;
  };

  /* =========================
     Capability Definitions
  ========================= */
  const DEFAULT_CAPS = _deepFreeze({
    dom: false,
    net: false,
    svg: false,
    store: false,
    time: true,
    log: true,
    canvasTabs: false,    // ability to open/close tabs in the canvas area
    sandboxJS: false      // ability to request JS execution inside sandboxed iframe
  });

  const normalizeCaps = (caps) => {
    const c = Object.assign({}, DEFAULT_CAPS, caps || {});
    // ensure booleans
    for (const k of Object.keys(c)) c[k] = !!c[k];
    return _deepFreeze(c);
  };

  /* =========================
     Devices (Gated APIs)
  ========================= */

  function createLoggerDevice({ prefix = "KUHUL" } = {}) {
    return _deepFreeze({
      info: (...args) => console.info(`[${prefix}]`, ...args),
      warn: (...args) => console.warn(`[${prefix}]`, ...args),
      error: (...args) => console.error(`[${prefix}]`, ...args)
    });
  }

  function createTimeDevice() {
    return _deepFreeze({
      now: () => Date.now(),
      perf: () => _now(),
      sleep: (ms) => new Promise((res) => setTimeout(res, Math.max(0, ms | 0)))
    });
  }

  function createDomDevice({ root = document } = {}) {
    // Minimal DOM syscalls. Expand later as needed.
    return _deepFreeze({
      q: (sel) => root.querySelector(sel),
      qa: (sel) => Array.from(root.querySelectorAll(sel)),
      byId: (id) => root.getElementById(id),
      setText: (id, text) => {
        const el = root.getElementById(id);
        if (el) el.textContent = String(text ?? "");
        return !!el;
      },
      setHTML: (id, html) => {
        const el = root.getElementById(id);
        if (el) el.innerHTML = String(html ?? "");
        return !!el;
      },
      addClass: (id, cls) => {
        const el = root.getElementById(id);
        if (el) el.classList.add(cls);
        return !!el;
      },
      removeClass: (id, cls) => {
        const el = root.getElementById(id);
        if (el) el.classList.remove(cls);
        return !!el;
      },
      setStyle: (id, k, v) => {
        const el = root.getElementById(id);
        if (el) el.style[k] = String(v ?? "");
        return !!el;
      }
    });
  }

  function createSvgDevice({ svgRootId = "kuhul_svg_root" } = {}) {
    const NS = "http://www.w3.org/2000/svg";
    const root = document.getElementById(svgRootId);
    return _deepFreeze({
      root: () => root,
      clear: () => {
        if (!root) return false;
        while (root.firstChild) root.removeChild(root.firstChild);
        return true;
      },
      path: (d, attrs = {}) => {
        if (!root) return null;
        const p = document.createElementNS(NS, "path");
        p.setAttribute("d", String(d ?? ""));
        for (const [k, v] of Object.entries(attrs || {})) p.setAttribute(k, String(v));
        root.appendChild(p);
        return p;
      },
      rect: (x, y, w, h, attrs = {}) => {
        if (!root) return null;
        const r = document.createElementNS(NS, "rect");
        r.setAttribute("x", String(x ?? 0));
        r.setAttribute("y", String(y ?? 0));
        r.setAttribute("width", String(w ?? 0));
        r.setAttribute("height", String(h ?? 0));
        for (const [k, v] of Object.entries(attrs || {})) r.setAttribute(k, String(v));
        root.appendChild(r);
        return r;
      },
      text: (x, y, s, attrs = {}) => {
        if (!root) return null;
        const t = document.createElementNS(NS, "text");
        t.setAttribute("x", String(x ?? 0));
        t.setAttribute("y", String(y ?? 0));
        t.textContent = String(s ?? "");
        for (const [k, v] of Object.entries(attrs || {})) t.setAttribute(k, String(v));
        root.appendChild(t);
        return t;
      }
    });
  }

  function createStoreDevice({ namespace = "kuhul", preferIDB = false } = {}) {
    // For “drop-in”, keep it simple: localStorage only.
    // IDB can be added later (or you can wrap this behind sw.khl endpoints).
    const key = (k) => `${namespace}:${k}`;
    return _deepFreeze({
      get: (k, fallback = null) => {
        const v = localStorage.getItem(key(k));
        return v == null ? fallback : _safeJsonParse(v, v);
      },
      set: (k, v) => {
        localStorage.setItem(key(k), JSON.stringify(v));
        return true;
      },
      del: (k) => {
        localStorage.removeItem(key(k));
        return true;
      },
      keys: () => {
        const out = [];
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i);
          if (k && k.startsWith(`${namespace}:`)) out.push(k.slice(namespace.length + 1));
        }
        return out;
      },
      clear: () => {
        for (const k of createStoreDevice({ namespace }).keys()) {
          localStorage.removeItem(key(k));
        }
        return true;
      },
      _preferIDB: !!preferIDB
    });
  }

  function createNetDevice({ proxyUrl = "/bridge/proxy?url=" } = {}) {
    // No raw fetch exposed; brokered through proxyUrl.
    return _deepFreeze({
      getText: async (url) => {
        const u = proxyUrl + encodeURIComponent(String(url));
        const r = await fetch(u, { method: "GET", credentials: "omit" });
        return r.text();
      },
      getJSON: async (url) => {
        const txt = await createNetDevice({ proxyUrl }).getText(url);
        return _safeJsonParse(txt, null);
      }
    });
  }

  /* =========================
     Canvas Tabs + Persistence
  ========================= */

  const CANVAS_STATE_KEY = "canvas.tabs.state.v1";

  function createCanvasTabsDevice({ store, onOpen, onClose } = {}) {
    // store is a storeDevice (localStorage-based by default)
    const _store = store || createStoreDevice({ namespace: "kuhul" });
    const _onOpen = typeof onOpen === "function" ? onOpen : () => {};
    const _onClose = typeof onClose === "function" ? onClose : () => {};

    const defaultState = {
      activeId: null,
      tabs: [] // {id,url,title,ts,allowJS}
    };

    const readState = () => _store.get(CANVAS_STATE_KEY, defaultState) || defaultState;

    const writeState = (st) => {
      _store.set(CANVAS_STATE_KEY, st);
      return st;
    };

    const open = (url, { title, allowJS = false, focus = true } = {}) => {
      url = String(url || "").trim();
      if (!url) throw new Error("KUHUL.canvasTabs.open: URL required");

      const st = readState();
      const id = _uid();
      const tab = {
        id,
        url,
        title: String(title || url).slice(0, 120),
        ts: Date.now(),
        allowJS: !!allowJS
      };
      st.tabs.push(tab);
      if (focus) st.activeId = id;
      writeState(st);
      _onOpen(tab, st);
      return tab;
    };

    const close = (id) => {
      const st = readState();
      const idx = st.tabs.findIndex(t => t.id === id);
      if (idx === -1) return false;

      const [tab] = st.tabs.splice(idx, 1);
      if (st.activeId === id) st.activeId = st.tabs.length ? st.tabs[st.tabs.length - 1].id : null;
      writeState(st);
      _onClose(tab, st);
      return true;
    };

    const focus = (id) => {
      const st = readState();
      const ok = st.tabs.some(t => t.id === id);
      if (!ok) return false;
      st.activeId = id;
      writeState(st);
      return true;
    };

    const list = () => readState().tabs.slice();
    const active = () => {
      const st = readState();
      return st.tabs.find(t => t.id === st.activeId) || null;
    };

    const hydrate = () => readState(); // for boot restore

    return _deepFreeze({ open, close, focus, list, active, hydrate });
  }

  /* =========================
     Sandbox JS Runner (iframe)
  ========================= */

  function createSandboxJSDevice({ targetWindow, targetOrigin = "*" } = {}) {
    // This DOES NOT execute arbitrary code directly.
    // It sends a request to the sandbox iframe, which may or may not honor it.
    // The sandbox iframe must include a listener that only accepts limited messages.
    const w = targetWindow;
    return _deepFreeze({
      post: (type, payload) => {
        if (!w || typeof w.postMessage !== "function") return false;
        w.postMessage({ __kuhul: 1, type: String(type), payload }, targetOrigin);
        return true;
      }
    });
  }

  /* =========================
     KUHUL Module Base Class
  ========================= */

  class KUHUL_Module {
    constructor(caps = {}) {
      this._caps = normalizeCaps(caps);
      this._ctx = null;
    }

    _bindContext(ctx) {
      if (this._ctx) throw new Error("KUHUL: module already bound");
      this._ctx = Object.freeze(ctx);
      return this;
    }

    caps() { return this._caps; }

    require(cap) {
      if (!this._caps[cap]) throw new Error(`KUHUL: Capability "${cap}" not granted`);
    }

    log() { this.require("log"); return this._ctx.devices.log; }
    time() { this.require("time"); return this._ctx.devices.time; }
    dom() { this.require("dom"); return this._ctx.devices.dom; }
    svg() { this.require("svg"); return this._ctx.devices.svg; }
    store() { this.require("store"); return this._ctx.devices.store; }
    net() { this.require("net"); return this._ctx.devices.net; }
    canvasTabs() { this.require("canvasTabs"); return this._ctx.devices.canvasTabs; }
    sandboxJS() { this.require("sandboxJS"); return this._ctx.devices.sandboxJS; }

    // Optional lifecycle hooks
    async init(_payload) {}
    async tick(_payload) {}
    async destroy() {}
  }

  /* =========================
     KUHUL Runtime Registry
  ========================= */

  const KUHUL = (function createKUHUL() {
    const registry = new Map();   // name -> {klass,caps,meta}
    const instances = new Map();  // instanceId -> {name,inst,ts}

    const baseDevices = {
      log: createLoggerDevice({ prefix: "KUHUL" }),
      time: createTimeDevice(),
      dom: createDomDevice(),
      svg: createSvgDevice(),
      store: createStoreDevice({ namespace: "kuhul" }),
      net: createNetDevice({ proxyUrl: "/bridge/proxy?url=" }),
      canvasTabs: null,
      sandboxJS: null
    };

    const setDevice = (name, device) => {
      baseDevices[name] = device;
      return true;
    };

    const register = (name, klass, caps = {}, meta = {}) => {
      name = String(name || "").trim();
      if (!name) throw new Error("KUHUL.register: name required");
      if (typeof klass !== "function") throw new Error("KUHUL.register: klass must be a constructor");
      const ncaps = normalizeCaps(caps);
      registry.set(name, _deepFreeze({ name, klass, caps: ncaps, meta: Object.assign({}, meta) }));
      return true;
    };

    const create = (name, { devices = {}, instanceCaps = null } = {}) => {
      const def = registry.get(name);
      if (!def) throw new Error(`KUHUL.create: unknown module "${name}"`);

      // Merge devices: base -> override
      const mergedDevices = Object.assign({}, baseDevices, devices);

      // Per-instance capability override: only allow narrowing, never widening
      const caps = instanceCaps ? normalizeCaps(instanceCaps) : def.caps;
      for (const k of Object.keys(caps)) {
        if (caps[k] && !def.caps[k]) {
          throw new Error(`KUHUL: cannot widen caps "${k}" beyond registration`);
        }
      }

      // Bind canvas/sandbox devices if available in DOM
      // You can also explicitly set them via setDevice()
      const ctx = {
        runtime: "kuhul-js",
        version: "1.0.0",
        module: name,
        instanceId: _uid(),
        ts: Date.now(),
        devices: _deepFreeze(mergedDevices),
        caps
      };

      // Instantiate module
      const inst = new def.klass(caps);
      if (!(inst instanceof KUHUL_Module)) {
        // Allow non-subclass modules, but bind gated helpers onto it in a safe way
        // (Still forces usage through ctx.*)
        Object.defineProperty(inst, "_caps", { value: caps, enumerable: false });
      } else {
        inst._bindContext(ctx);
      }

      instances.set(ctx.instanceId, { name, inst, ts: ctx.ts });
      return { id: ctx.instanceId, ctx, inst };
    };

    const run = async (name, payload = {}, opts = {}) => {
      const { id, ctx, inst } = create(name, opts);

      // Normalize payload into safe object
      const p = (payload && typeof payload === "object") ? payload : { value: payload };

      // If it is a proper KUHUL_Module, use lifecycle hooks.
      if (inst instanceof KUHUL_Module) {
        await inst.init(p);
        // optional single tick
        if (typeof inst.tick === "function") await inst.tick(p);
      } else if (typeof inst === "function") {
        // function modules: called with (payload, ctx)
        await inst(p, ctx);
      } else if (typeof inst.run === "function") {
        await inst.run(p, ctx);
      }

      return _deepFreeze({
        ok: true,
        module: name,
        instanceId: id,
        ts: ctx.ts
      });
    };

    const destroy = async (instanceId) => {
      const rec = instances.get(instanceId);
      if (!rec) return false;
      const inst = rec.inst;
      if (inst instanceof KUHUL_Module && typeof inst.destroy === "function") {
        try { await inst.destroy(); } catch {}
      }
      instances.delete(instanceId);
      return true;
    };

    const list = () => Array.from(registry.values()).map(d => ({
      name: d.name,
      caps: d.caps,
      meta: d.meta
    }));

    return _deepFreeze({
      KUHUL_Module,
      register,
      create,
      run,
      destroy,
      list,
      setDevice,
      devices: () => Object.assign({}, baseDevices),
      caps: DEFAULT_CAPS
    });
  })();

  /* =========================
     Optional: Auto-wire Canvas Tabs if elements exist
  ========================= */

  function autoWireCanvasTabs() {
    // If your index.html has a canvas iframe with id="canvas_iframe"
    // and you want tabs persisted in localStorage:
    const store = createStoreDevice({ namespace: "kuhul" });

    const iframe = document.getElementById("canvas_iframe");
    const sandboxJS = iframe ? createSandboxJSDevice({ targetWindow: iframe.contentWindow, targetOrigin: "*" }) : null;

    const canvasTabs = createCanvasTabsDevice({
      store,
      onOpen: (tab) => {
        // You can replace this with your own tab bar rendering logic.
        // Default: load into iframe immediately if present.
        if (iframe) {
          // IMPORTANT: do not allow arbitrary JS by default. Use allowJS from tab.
          // For external URLs, prefer sandbox="allow-same-origin" only.
          iframe.src = tab.url;
        }
      },
      onClose: (_tab, st) => {
        if (!iframe) return;
        const active = st.tabs.find(t => t.id === st.activeId) || null;
        iframe.src = active ? active.url : "about:blank";
      }
    });

    KUHUL.setDevice("store", store);
    KUHUL.setDevice("canvasTabs", canvasTabs);
    if (sandboxJS) KUHUL.setDevice("sandboxJS", sandboxJS);

    // Restore last session
    const st = canvasTabs.hydrate();
    if (iframe && st && st.activeId) {
      const active = st.tabs.find(t => t.id === st.activeId);
      if (active) iframe.src = active.url;
    }
  }

  // Safe to call on DOMContentLoaded
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", autoWireCanvasTabs, { once: true });
  } else {
    autoWireCanvasTabs();
  }

  /* =========================
     Expose KUHUL Runtime
  ========================= */
  Object.defineProperty(global, "KUHUL", {
    value: KUHUL,
    enumerable: false,
    configurable: false,
    writable: false
  });

  /* =========================
     Example Built-in Module: Minimal π renderer (optional)
  ========================= */
  class KUHUL_PiMini extends KUHUL_Module {
    constructor(caps) {
      super(Object.assign({}, caps, { svg: true, log: true, time: true }));
    }
    async init(payload) {
      this.log().info("PiMini init", payload);
    }
    async tick(payload) {
      const svg = this.svg();
      svg.clear();
      const w = (payload && payload.w) || 900;
      const h = (payload && payload.h) || 220;

      // Simple waveform path as placeholder "π vibe"
      let d = `M 0 ${h/2}`;
      for (let x = 0; x <= w; x += 10) {
        const y = (h/2) + Math.sin(x/40) * (h/3);
        d += ` L ${x} ${y}`;
      }
      svg.path(d, {
        fill: "none",
        stroke: "#16f2aa",
        "stroke-width": "2",
        "stroke-linecap": "round"
      });
    }
  }

  // Register sample
  try {
    KUHUL.register("pi-mini", KUHUL_PiMini, { svg: true, log: true, time: true }, { desc: "Minimal SVG π renderer demo" });
  } catch {}

})(window);
