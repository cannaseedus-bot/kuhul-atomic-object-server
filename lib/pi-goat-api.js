/**
 * Pi-GOAT API Language Adapter
 *
 * Treats API as a first-class language in MX2LM.
 * API is not just a protocol - it's the semantic bloodstream.
 *
 * Supports:
 *   - REST (GET /path?x=1)
 *   - XJSON API ({"@api": {...}})
 *   - K'uhul API Pops (Pop call_api { ... })
 *   - GAS shard calls (?path=...)
 *   - PHP router calls (/api.php?route=...)
 *   - Mesh node calls (mx2lm://node/123/api/...)
 *   - Dot notation (api.tokens.balance)
 */

(function(global) {
  'use strict';

  // ============================================
  // API Language Detection
  // ============================================

  /**
   * Detect if source is API language
   * @param {string} source
   * @returns {boolean}
   */
  function detectAPILanguage(source) {
    const src = source.trim();

    // HTTP verbs
    if (/^(GET|POST|PUT|DELETE|PATCH)\s+/i.test(src)) return true;

    // Mesh URI
    if (src.startsWith('mx2lm://')) return true;

    // PHP router
    if (src.includes('api.php')) return true;

    // GAS shard
    if (src.includes('?path=')) return true;

    // XJSON API
    try {
      const obj = JSON.parse(src);
      if (obj['@api'] || obj['@shard']) return true;
    } catch (e) {
      // Not JSON
    }

    // Dot notation API (api.tokens.balance)
    if (/^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*$/.test(src)) return true;

    return false;
  }

  // ============================================
  // API Raw AST Parser
  // ============================================

  /**
   * Parse API source to raw AST
   * @param {string} source
   * @returns {Object} APIRawAST
   */
  function parseAPIToRawAST(source) {
    const src = source.trim();

    // 1. Try XJSON API
    try {
      const obj = JSON.parse(src);
      if (obj['@api'] || obj['@shard'] || obj['@infer']) {
        return parseXJSONAPI(obj);
      }
    } catch (e) {
      // Not JSON
    }

    // 2. Mesh URI (mx2lm://...)
    if (src.startsWith('mx2lm://')) {
      return parseMeshURI(src);
    }

    // 3. HTTP verb line (GET /path...)
    if (/^(GET|POST|PUT|DELETE|PATCH)\s+/i.test(src)) {
      return parseHTTPLine(src);
    }

    // 4. PHP/GAS query style
    if (src.includes('api.php') || src.includes('?path=')) {
      return parseQueryStyleAPI(src);
    }

    // 5. Dot notation (api.tokens.balance)
    if (/^[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_.]*$/.test(src)) {
      return parseDotNotationAPI(src);
    }

    // 6. Fallback: treat as CALL
    return {
      method: 'CALL',
      endpoint: src,
      params: {},
      protocol: 'xjson'
    };
  }

  /**
   * Parse XJSON API format
   * @private
   */
  function parseXJSONAPI(obj) {
    if (obj['@api']) {
      const a = obj['@api'];
      return {
        method: (a['@method'] || 'CALL').toUpperCase(),
        endpoint: a['@endpoint'] || '',
        params: a['@params'] || {},
        headers: a['@headers'] || {},
        body: a['@body'],
        protocol: 'xjson'
      };
    }

    if (obj['@infer']) {
      return {
        method: 'POST',
        endpoint: 'infer',
        params: {
          runner: obj['@infer']['@runner'],
          model: obj['@infer']['@model']
        },
        body: { prompt: obj['@infer']['@prompt'] },
        protocol: 'xjson'
      };
    }

    if (obj['@shard']) {
      return {
        method: 'GET',
        endpoint: obj['@shard']['@endpoint'] || 'shard',
        params: obj['@shard']['@params'] || {},
        protocol: 'gas'
      };
    }

    return {
      method: 'CALL',
      endpoint: 'unknown',
      params: {},
      protocol: 'xjson'
    };
  }

  /**
   * Parse mesh URI
   * @private
   */
  function parseMeshURI(src) {
    // mx2lm://node/<id>/api/<endpoint>?key=value
    const withoutScheme = src.replace('mx2lm://', '');
    const [nodeAndRest, queryString] = withoutScheme.split('?');
    const parts = nodeAndRest.split('/');
    const endpoint = parts.slice(3).join('/') || 'status';

    const params = {};
    if (queryString) {
      new URLSearchParams(queryString).forEach((v, k) => { params[k] = v; });
    }

    return {
      method: 'CALL',
      endpoint: endpoint,
      params: { ...params, nodeId: parts[1] },
      protocol: 'mesh'
    };
  }

  /**
   * Parse HTTP verb line
   * @private
   */
  function parseHTTPLine(src) {
    const match = src.match(/^(GET|POST|PUT|DELETE|PATCH)\s+(\S+)/i);
    if (!match) {
      return { method: 'GET', endpoint: 'root', params: {}, protocol: 'http' };
    }

    const method = match[1].toUpperCase();
    const urlPart = match[2];

    let pathname = urlPart;
    const params = {};

    if (urlPart.includes('?')) {
      const [path, query] = urlPart.split('?');
      pathname = path;
      new URLSearchParams(query).forEach((v, k) => { params[k] = v; });
    }

    return {
      method: method,
      endpoint: pathname.replace(/^\//, '') || 'root',
      params: params,
      protocol: 'http'
    };
  }

  /**
   * Parse query style API (PHP/GAS)
   * @private
   */
  function parseQueryStyleAPI(src) {
    const params = {};
    let pathname = 'root';

    if (src.includes('?')) {
      const queryPart = src.split('?')[1] || '';
      new URLSearchParams(queryPart).forEach((v, k) => { params[k] = v; });
    }

    if (src.includes('api.php')) {
      return {
        method: 'POST',
        endpoint: params['route'] || 'root',
        params: params,
        protocol: 'php'
      };
    }

    if (params['path']) {
      return {
        method: 'GET',
        endpoint: params['path'],
        params: params,
        protocol: 'gas'
      };
    }

    return {
      method: 'CALL',
      endpoint: 'root',
      params: params,
      protocol: 'http'
    };
  }

  /**
   * Parse dot notation API
   * @private
   */
  function parseDotNotationAPI(src) {
    const parts = src.split('.');
    const endpoint = parts.slice(0, 2).join('/');
    const remaining = parts.slice(2).join('.');

    const params = {};
    if (remaining) {
      params['detail'] = remaining;
    }

    return {
      method: 'CALL',
      endpoint: endpoint,
      params: params,
      protocol: 'xjson'
    };
  }

  // ============================================
  // API AST Normalizer
  // ============================================

  /**
   * Normalize API raw AST to unified format
   * @param {Object} raw - APIRawAST
   * @param {string} originalSource
   * @returns {Object} NormalizedAST
   */
  function normalizeAPIAST(raw, originalSource) {
    const paramNodes = Object.entries(raw.params || {}).map(([k, v]) => ({
      type: 'Param',
      name: k,
      value: v
    }));

    const bodyNode = raw.body !== undefined ? {
      type: 'Body',
      value: raw.body
    } : undefined;

    const root = {
      type: 'APICall',
      kind: raw.method,
      name: raw.endpoint,
      params: paramNodes,
      body: bodyNode ? [bodyNode] : [],
      extras: {
        protocol: raw.protocol,
        headers: raw.headers || {}
      }
    };

    return {
      lang: 'api',
      root: root,
      meta: {
        originalSource: originalSource,
        tokens: originalSource.length,
        complexity: paramNodes.length + (bodyNode ? 1 : 0),
        entryPoints: ['api']
      }
    };
  }

  // ============================================
  // API Runtime Router
  // ============================================

  /**
   * Route API to appropriate runtime
   * @param {Object} ast - NormalizedAST
   * @returns {string} RuntimeTarget
   */
  function routeAPIRuntime(ast) {
    const protocol = ast.root.extras?.protocol || 'http';
    const endpoint = ast.root.name || '';

    switch (protocol) {
      case 'gas':
        return 'gas_runtime';
      case 'php':
        return 'php_runtime';
      case 'mesh':
        return 'mesh_runtime';
      default:
        break;
    }

    // Route by endpoint prefix
    if (endpoint.startsWith('backend/')) return 'backend_shard_runtime';
    if (endpoint.startsWith('frontend/')) return 'frontend_shard_runtime';
    if (endpoint.startsWith('design/')) return 'design_shard_runtime';
    if (endpoint === 'infer') return 'model_runtime';

    return 'http_runtime';
  }

  // ============================================
  // API Executor
  // ============================================

  /**
   * Execute API call
   * @param {Object} ast - NormalizedAST
   * @param {Object} context - Execution context
   * @returns {Promise<Object>} Result
   */
  async function executeAPI(ast, context = {}) {
    const node = ast.root;
    const method = (node.kind || 'CALL');
    const endpoint = node.name || 'root';
    const protocol = node.extras?.protocol || 'http';
    const headers = node.extras?.headers || {};

    const params = {};
    (node.params || []).forEach(p => {
      if (p.name) params[p.name] = p.value;
    });

    const bodyNode = (node.body || [])[0];
    const body = bodyNode ? bodyNode.value : undefined;

    try {
      let result;

      switch (protocol) {
        case 'http':
        case 'https':
          result = await executeHTTPAPI(method, endpoint, params, body, headers, context);
          break;

        case 'gas':
          result = await executeGASAPI(endpoint, params, context);
          break;

        case 'php':
          result = await executePHPAPI(endpoint, params, body, context);
          break;

        case 'mesh':
          result = await executeMeshAPI(endpoint, params, body, context);
          break;

        case 'xjson':
          result = await executeXJSONAPI(endpoint, params, body, context);
          break;

        default:
          result = await executeHTTPAPI(method, endpoint, params, body, headers, context);
      }

      return {
        success: true,
        result: result,
        runtime: protocol + '_runtime',
        endpoint: endpoint,
        method: method
      };

    } catch (error) {
      return {
        success: false,
        error: error.message,
        runtime: protocol + '_runtime',
        endpoint: endpoint
      };
    }
  }

  /**
   * Execute HTTP API
   * @private
   */
  async function executeHTTPAPI(method, endpoint, params, body, headers, context) {
    const baseUrl = context.baseUrl || window.location.origin;
    const url = new URL(endpoint.startsWith('/') ? endpoint : '/' + endpoint, baseUrl);

    Object.entries(params).forEach(([k, v]) => {
      url.searchParams.append(k, String(v));
    });

    const init = {
      method: method === 'CALL' ? 'POST' : method,
      headers: { 'Content-Type': 'application/json', ...headers }
    };

    if (method !== 'GET' && body !== undefined) {
      init.body = JSON.stringify(body);
    }

    const response = await fetch(url.toString(), init);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    return response.json();
  }

  /**
   * Execute GAS API
   * @private
   */
  async function executeGASAPI(endpoint, params, context) {
    const gasUrl = context.gasUrl || 'https://script.google.com/macros/s/YOUR-GAS-ID/exec';
    const url = new URL(gasUrl);
    url.searchParams.set('path', endpoint);

    Object.entries(params).forEach(([k, v]) => {
      if (k !== 'path') url.searchParams.append(k, String(v));
    });

    const response = await fetch(url.toString());

    if (!response.ok) {
      throw new Error(`GAS error: ${response.status}`);
    }

    return response.json();
  }

  /**
   * Execute PHP API
   * @private
   */
  async function executePHPAPI(route, params, body, context) {
    const baseUrl = context.phpUrl || window.location.origin + '/api.php';
    const url = new URL(baseUrl);
    url.searchParams.set('route', route);

    Object.entries(params).forEach(([k, v]) => {
      if (k !== 'route') url.searchParams.append(k, String(v));
    });

    const response = await fetch(url.toString(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined
    });

    if (!response.ok) {
      throw new Error(`PHP error: ${response.status}`);
    }

    return response.json();
  }

  /**
   * Execute Mesh API
   * @private
   */
  async function executeMeshAPI(endpoint, params, body, context) {
    // Use mesh router if available
    if (global.MeshRouter && typeof global.MeshRouter.routeAPI === 'function') {
      return global.MeshRouter.routeAPI({ endpoint, params, body });
    }

    // Fallback: try local orchestrator
    const nodeId = params.nodeId;
    delete params.nodeId;

    const baseUrl = context.meshUrl || 'http://localhost:61683';
    const url = new URL('/api/' + endpoint, baseUrl);

    Object.entries(params).forEach(([k, v]) => {
      url.searchParams.append(k, String(v));
    });

    if (nodeId) {
      url.searchParams.set('nodeId', nodeId);
    }

    const response = await fetch(url.toString(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body !== undefined ? JSON.stringify(body) : undefined
    });

    return response.json();
  }

  /**
   * Execute XJSON API (symbolic)
   * @private
   */
  async function executeXJSONAPI(endpoint, params, body, context) {
    // Build XJSON request
    const xjsonRequest = {
      '@api': {
        '@endpoint': endpoint,
        '@params': params,
        '@body': body
      }
    };

    // Use KuhulClient if available
    if (global.KuhulClient && endpoint === 'infer') {
      return global.KuhulClient.infer(body || {});
    }

    // Symbolic execution: return prepared request
    return {
      prepared: xjsonRequest,
      mode: 'xjson_symbolic',
      message: 'XJSON API prepared for execution'
    };
  }

  // ============================================
  // Mesh Node Registry
  // ============================================

  const MeshRouter = {
    _nodes: [],

    /**
     * Register a mesh node
     */
    register: function(node) {
      const idx = this._nodes.findIndex(n => n.id === node.id);
      if (idx >= 0) {
        this._nodes[idx] = { ...this._nodes[idx], ...node };
      } else {
        this._nodes.push(node);
      }
    },

    /**
     * Get all nodes
     */
    getNodes: function() {
      return this._nodes.slice();
    },

    /**
     * Route API to best node
     */
    routeAPI: async function(req) {
      const candidates = this._nodes.filter(n =>
        n.supports && n.supports.includes('api')
      );

      if (!candidates.length) {
        throw new Error('No mesh nodes available for API');
      }

      const target = this._selectBest(candidates);
      const url = new URL('/api', target.url);
      url.searchParams.set('endpoint', req.endpoint);

      Object.entries(req.params || {}).forEach(([k, v]) => {
        url.searchParams.append(k, String(v));
      });

      const response = await fetch(url.toString(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: req.body !== undefined ? JSON.stringify(req.body) : undefined
      });

      return response.json();
    },

    /**
     * Select best node
     * @private
     */
    _selectBest: function(nodes) {
      const weight = (n) => {
        const cap = n.capacity === 'heavy' ? 3 : n.capacity === 'medium' ? 2 : 1;
        const latency = 10000 - (n.latencyMs || 500);
        return cap * latency;
      };

      return nodes.sort((a, b) => weight(b) - weight(a))[0];
    }
  };

  // ============================================
  // Pi-GOAT API Integration
  // ============================================

  const PiGoatAPI = {
    name: 'Pi-GOAT API Language Adapter',
    version: '1.0.0',

    /**
     * Check if source is API language
     */
    isAPILanguage: detectAPILanguage,

    /**
     * Full dispatch for API
     */
    dispatch: async function(request) {
      const startTime = performance.now();

      try {
        const source = request.source || request;
        const raw = parseAPIToRawAST(source);
        const ast = normalizeAPIAST(raw, source);
        const runtime = routeAPIRuntime(ast);
        const result = await executeAPI(ast, request.context || {});

        const endTime = performance.now();
        const latencyMs = endTime - startTime;

        // Generate SCXQ2 if available
        let scxq2 = null;
        if (global.SCXQ2) {
          const payload = JSON.stringify({
            type: 'api_call',
            endpoint: ast.root.name,
            method: ast.root.kind,
            params: Object.fromEntries((ast.root.params || []).map(p => [p.name, p.value])),
            runtime: runtime,
            latency_ms: latencyMs
          });
          scxq2 = await global.SCXQ2.fingerprint(payload);
        }

        return {
          success: result.success,
          language: 'api',
          ast: ast,
          runtime: runtime,
          result: result.result,
          scxq2: scxq2,
          metrics: {
            latency_ms: latencyMs,
            endpoint: ast.root.name,
            method: ast.root.kind,
            protocol: ast.root.extras?.protocol
          }
        };

      } catch (error) {
        return {
          success: false,
          language: 'api',
          ast: null,
          runtime: null,
          error: error.message
        };
      }
    },

    // Export individual functions
    parse: parseAPIToRawAST,
    normalize: normalizeAPIAST,
    route: routeAPIRuntime,
    execute: executeAPI
  };

  // ============================================
  // Register with Pi-GOAT if available
  // ============================================

  if (global.PiGoat) {
    // Register API language adapter
    global.PiGoat.registerAdapter('api', {
      parse: parseAPIToRawAST,
      detect: detectAPILanguage
    });

    // Register API runtime
    global.PiGoat.registerRuntime('api_runtime', {
      execute: async (ast, context) => executeAPI(ast, context)
    });

    console.log('[Pi-GOAT API] Registered API as first-class language');
  }

  // ============================================
  // Export
  // ============================================

  global.PiGoatAPI = PiGoatAPI;
  global.MeshRouter = MeshRouter;

  // CommonJS/Node.js export
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { PiGoatAPI, MeshRouter };
  }

  console.log('[Pi-GOAT API] API Language Adapter loaded - API is the semantic bloodstream');

})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this);
