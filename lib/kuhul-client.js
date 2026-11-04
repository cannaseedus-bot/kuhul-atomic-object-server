/**
 * K'uhul Client Library
 *
 * High-level client for K'uhul model inference operations.
 * Implements lam.o runner protocol with XJSON and SCXQ2 support.
 *
 * Sek kuhul_client -> build_xjson -> call_runner -> attach_scxq2 -> return
 */

(function(global) {
  'use strict';

  /**
   * Default configuration
   */
  const DEFAULT_CONFIG = {
    orchestratorUrl: '/api/infer',
    ollamaUrl: 'http://localhost:11434/api/generate',
    ollamaTagsUrl: '/api/models',
    healthUrl: '/api/health',
    timeout: 120000,
    enableSCXQ2: true,
    enableLogging: true,
    fallbackToOllama: false
  };

  /**
   * K'uhul Client
   */
  const KuhulClient = {
    config: { ...DEFAULT_CONFIG },

    /**
     * Configure client
     * @param {Object} options - Configuration options
     */
    configure: function(options) {
      this.config = { ...this.config, ...options };
    },

    /**
     * Run model inference
     * @param {Object} xjsonOrOptions - XJSON request or options object
     * @returns {Promise<Object>} XJSON response
     */
    infer: async function(xjsonOrOptions) {
      const startTime = performance.now();

      // Build XJSON request if needed
      let xjsonRequest;
      if (xjsonOrOptions && xjsonOrOptions['@infer']) {
        xjsonRequest = xjsonOrOptions;
      } else {
        xjsonRequest = global.XJSON ?
          global.XJSON.createInferRequest(xjsonOrOptions) :
          this._buildBasicRequest(xjsonOrOptions);
      }

      try {
        // Try orchestrator first
        let response;
        try {
          response = await this._callOrchestrator(xjsonRequest);
        } catch (orchestratorError) {
          if (this.config.fallbackToOllama) {
            console.warn('[KuhulClient] Orchestrator unavailable, falling back to Ollama');
            response = await this._callOllama(xjsonRequest);
          } else {
            throw orchestratorError;
          }
        }

        const endTime = performance.now();
        const latencyMs = endTime - startTime;

        // Normalize response
        let xjsonResponse;
        if (response && response['@completion']) {
          xjsonResponse = response;
        } else if (response && response['@error']) {
          return response;
        } else {
          xjsonResponse = this._normalizeResponse(response, xjsonRequest, latencyMs);
        }

        // Attach SCXQ2 if enabled
        if (this.config.enableSCXQ2 && global.SCXQ2) {
          const scxq2 = await global.SCXQ2.fromInference(xjsonRequest, xjsonResponse);
          xjsonResponse['@completion']['@scxq2'] = scxq2;
        }

        // Log if enabled
        if (this.config.enableLogging) {
          this._log(xjsonRequest, xjsonResponse);
        }

        return xjsonResponse;

      } catch (error) {
        console.error('[KuhulClient] Inference error:', error);
        return global.XJSON ?
          global.XJSON.createErrorResponse({
            runner: 'lam.o',
            message: error.message,
            code: error.status || 500
          }) :
          this._buildErrorResponse(error);
      }
    },

    /**
     * Health check for runner and backend
     * @returns {Promise<Object>} Health status
     */
    healthCheck: async function() {
      const results = {
        orchestrator: false,
        ollama: false
      };

      // Check orchestrator
      try {
        const orchResponse = await this._fetchWithTimeout(
          this.config.healthUrl,
          { method: 'GET' },
          5000
        );
        results.orchestrator = orchResponse.ok;
      } catch (e) {
        results.orchestrator = false;
      }

      // Check Ollama
      try {
        const ollamaResponse = await this._fetchWithTimeout(
          this.config.ollamaTagsUrl,
          { method: 'GET' },
          5000
        );
        results.ollama = ollamaResponse.ok;
      } catch (e) {
        results.ollama = false;
      }

      return results;
    },

    /**
     * Get available models
     * @returns {Promise<Array>} List of models
     */
    getModels: async function() {
      try {
        const response = await this._fetchWithTimeout(
          this.config.ollamaTagsUrl,
          { method: 'GET' },
          10000
        );

        if (response.ok) {
          const data = await response.json();
          return data.models || [];
        }

        return [];
      } catch (error) {
        console.warn('[KuhulClient] Failed to get models:', error);
        return [];
      }
    },

    /**
     * Call orchestrator endpoint
     * @private
     */
    _callOrchestrator: async function(xjsonRequest) {
      const response = await this._fetchWithTimeout(
        this.config.orchestratorUrl,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-Kuhul-Runner': 'lam.o'
          },
          body: JSON.stringify(xjsonRequest)
        },
        this.config.timeout
      );

      if (!response.ok) {
        const error = new Error(`Orchestrator error: ${response.status}`);
        error.status = response.status;
        throw error;
      }

      return response.json();
    },

    /**
     * Call Ollama directly
     * @private
     */
    _callOllama: async function(xjsonRequest) {
      const infer = xjsonRequest['@infer'] || {};
      const params = infer['@params'] || {};

      const ollamaRequest = {
        model: infer['@model'] || 'llama3',
        prompt: infer['@prompt'] || '',
        stream: false,
        options: {
          temperature: params.temperature,
          top_p: params.top_p
        }
      };

      const response = await this._fetchWithTimeout(
        this.config.ollamaUrl,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(ollamaRequest)
        },
        this.config.timeout
      );

      if (!response.ok) {
        const error = new Error(`Ollama error: ${response.status}`);
        error.status = response.status;
        throw error;
      }

      return response.json();
    },

    /**
     * Fetch with timeout
     * @private
     */
    _fetchWithTimeout: async function(url, options, timeout) {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeout);
      try { return await fetch(url, { ...options, signal: controller.signal }); }
      finally { clearTimeout(timer); }
    },

    /**
     * Build basic request (fallback without XJSON module)
     * @private
     */
    _buildBasicRequest: function(options) {
      return {
        '@infer': {
          '@runner': 'lam.o',
          '@model': options.model || 'llama3',
          '@prompt': options.prompt || '',
          '@params': {
            temperature: options.temperature ?? 0.7,
            top_p: options.top_p ?? 0.9
          },
          '@context': options.context || [],
          '@mode': options.mode || 'chat'
        }
      };
    },

    /**
     * Normalize response to XJSON format
     * @private
     */
    _normalizeResponse: function(data, request, latencyMs) {
      const infer = request['@infer'] || {};

      return {
        '@completion': {
          '@model': infer['@model'] || data.model || 'unknown',
          '@runner': 'lam.o',
          '@text': data.response || data.message?.content || '',
          '@tokens': {
            input: data.prompt_eval_count || 0,
            output: data.eval_count || 0
          },
          '@metrics': {
            latency_ms: latencyMs,
            backend: 'ollama',
            total_duration: data.total_duration || 0,
            load_duration: data.load_duration || 0,
            eval_duration: data.eval_duration || 0
          }
        }
      };
    },

    /**
     * Build error response (fallback without XJSON module)
     * @private
     */
    _buildErrorResponse: function(error) {
      return {
        '@error': {
          '@runner': 'lam.o',
          '@message': error.message || 'Unknown error',
          '@code': error.status || 500
        }
      };
    },

    /**
     * Log inference to console and potentially storage
     * @private
     */
    _log: function(request, response) {
      console.log('[KuhulClient] Inference:', {
        model: request['@infer']?.['@model'],
        latency: response['@completion']?.['@metrics']?.latency_ms,
        tokens: response['@completion']?.['@tokens'],
        scxq2: response['@completion']?.['@scxq2']
      });
    }
  };

  /**
   * K'uhul State Manager
   * Manages reactive state bindings for K'uhul elements
   */
  const KuhulState = {
    _state: {},
    _bindings: new Map(),
    _listeners: new Map(),

    /**
     * Set state value
     * @param {string} key - State key
     * @param {any} value - State value
     */
    set: function(key, value) {
      const oldValue = this._state[key];
      this._state[key] = value;

      // Update bindings
      if (this._bindings.has(key)) {
        for (const element of this._bindings.get(key)) {
          this._updateElement(element, value);
        }
      }

      // Notify listeners
      if (this._listeners.has(key)) {
        for (const listener of this._listeners.get(key)) {
          listener(value, oldValue);
        }
      }
    },

    /**
     * Get state value
     * @param {string} key - State key
     * @returns {any} State value
     */
    get: function(key) {
      return this._state[key];
    },

    /**
     * Bind element to state
     * @param {string} key - State key
     * @param {HTMLElement} element - DOM element
     */
    bind: function(key, element) {
      if (!this._bindings.has(key)) {
        this._bindings.set(key, new Set());
      }
      this._bindings.get(key).add(element);

      // Initialize with current value
      if (key in this._state) {
        this._updateElement(element, this._state[key]);
      }
    },

    /**
     * Subscribe to state changes
     * @param {string} key - State key
     * @param {Function} listener - Callback function
     */
    subscribe: function(key, listener) {
      if (!this._listeners.has(key)) {
        this._listeners.set(key, new Set());
      }
      this._listeners.get(key).add(listener);
    },

    /**
     * Update element with value
     * @private
     */
    _updateElement: function(element, value) {
      if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
        element.value = value;
      } else if (element.tagName === 'SELECT') {
        element.value = value;
      } else {
        element.textContent = value;
      }
    },

    /**
     * Initialize bindings from data-kuhul-bind attributes
     */
    initBindings: function() {
      const elements = document.querySelectorAll('[data-kuhul-bind]');
      for (const element of elements) {
        const key = element.dataset.kuhulBind;
        this.bind(key, element);

        // Add two-way binding for inputs
        if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
          element.addEventListener('input', () => {
            this._state[key] = element.value;
          });
        } else if (element.tagName === 'SELECT') {
          element.addEventListener('change', () => {
            this._state[key] = element.value;
          });
        }
      }
    }
  };

  /**
   * K'uhul Pop Handler
   * Handles Pop (operation) bindings
   */
  const KuhulPop = {
    _handlers: {},

    /**
     * Register Pop handler
     * @param {string} name - Pop name
     * @param {Function} handler - Handler function
     */
    register: function(name, handler) {
      this._handlers[name] = handler;
    },

    /**
     * Execute Pop
     * @param {string} name - Pop name
     * @param {Object} args - Pop arguments
     * @returns {Promise<any>} Pop result
     */
    execute: async function(name, args = {}) {
      const handler = this._handlers[name];
      if (!handler) {
        console.warn(`[KuhulPop] Unknown Pop: ${name}`);
        return null;
      }

      try {
        return await handler(args);
      } catch (error) {
        console.error(`[KuhulPop] Error executing ${name}:`, error);
        throw error;
      }
    },

    /**
     * Initialize Pop bindings from data-kuhul-pop attributes
     */
    initBindings: function() {
      const elements = document.querySelectorAll('[data-kuhul-pop]');
      for (const element of elements) {
        const popName = element.dataset.kuhulPop;
        const argsStr = element.dataset.kuhulArgs;
        let args = {};

        if (argsStr) {
          try {
            args = JSON.parse(argsStr);
          } catch (e) {
            console.warn('[KuhulPop] Invalid args JSON:', argsStr);
          }
        }

        element.addEventListener('click', () => {
          this.execute(popName, args);
        });
      }
    }
  };

  // Export
  global.KuhulClient = KuhulClient;
  global.KuhulState = KuhulState;
  global.KuhulPop = KuhulPop;

  // CommonJS/Node.js export
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { KuhulClient, KuhulState, KuhulPop };
  }

})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this);
