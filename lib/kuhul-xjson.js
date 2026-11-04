/**
 * K'uhul XJSON Engine
 *
 * Handles XJSON schema validation, transformation, and execution
 * for model inference operations.
 *
 * XJSON = eXecutable JSON - the data format for K'uhul operations
 */

(function(global) {
  'use strict';

  /**
   * XJSON Schema Definitions
   */
  const XJSON_SCHEMAS = {
    infer: {
      required: ['@runner', '@model', '@prompt'],
      optional: ['@params', '@context', '@mode']
    },
    completion: {
      required: ['@model', '@runner', '@text'],
      optional: ['@tokens', '@metrics', '@scxq2']
    },
    error: {
      required: ['@runner', '@message', '@code'],
      optional: []
    }
  };

  /**
   * XJSON Module
   */
  const XJSON = {
    /**
     * Create an inference request
     * @param {Object} options - Inference options
     * @returns {Object} XJSON request object
     */
    createInferRequest: function(options) {
      const {
        runner = 'lam.o',
        model,
        prompt,
        params = {},
        context = [],
        mode = 'chat'
      } = options;

      if (!model || !prompt) {
        throw new Error('XJSON: model and prompt are required');
      }

      return {
        '@infer': {
          '@runner': runner,
          '@model': model,
          '@prompt': prompt,
          '@params': {
            temperature: params.temperature ?? 0.7,
            top_p: params.top_p ?? 0.9,
            ...params
          },
          '@context': context,
          '@mode': mode
        }
      };
    },

    /**
     * Create a completion response
     * @param {Object} options - Completion options
     * @returns {Object} XJSON response object
     */
    createCompletionResponse: function(options) {
      const {
        model,
        runner = 'lam.o',
        text,
        tokens = {},
        metrics = {},
        scxq2 = null
      } = options;

      const response = {
        '@completion': {
          '@model': model,
          '@runner': runner,
          '@text': text,
          '@tokens': {
            input: tokens.input ?? 0,
            output: tokens.output ?? 0
          },
          '@metrics': {
            latency_ms: metrics.latency_ms ?? 0,
            backend: metrics.backend ?? 'ollama',
            ...metrics
          }
        }
      };

      if (scxq2) {
        response['@completion']['@scxq2'] = scxq2;
      }

      return response;
    },

    /**
     * Create an error response
     * @param {Object} options - Error options
     * @returns {Object} XJSON error object
     */
    createErrorResponse: function(options) {
      const {
        runner = 'lam.o',
        message,
        code = 500
      } = options;

      return {
        '@error': {
          '@runner': runner,
          '@message': message,
          '@code': code
        }
      };
    },

    /**
     * Validate XJSON object against schema
     * @param {Object} xjson - XJSON object
     * @param {string} type - Schema type ('infer', 'completion', 'error')
     * @returns {Object} Validation result {valid: boolean, errors: string[]}
     */
    validate: function(xjson, type) {
      const errors = [];
      const schema = XJSON_SCHEMAS[type];

      if (!schema) {
        return { valid: false, errors: [`Unknown schema type: ${type}`] };
      }

      const keyPrefix = type === 'infer' ? '@infer' :
                        type === 'completion' ? '@completion' : '@error';

      const data = xjson[keyPrefix];

      if (!data) {
        return { valid: false, errors: [`Missing ${keyPrefix} key`] };
      }

      // Check required fields
      for (const field of schema.required) {
        if (data[field] === undefined) {
          errors.push(`Missing required field: ${field}`);
        }
      }

      return {
        valid: errors.length === 0,
        errors: errors
      };
    },

    /**
     * Check if object is XJSON inference request
     * @param {Object} obj - Object to check
     * @returns {boolean}
     */
    isInferRequest: function(obj) {
      return obj && typeof obj === 'object' && '@infer' in obj;
    },

    /**
     * Check if object is XJSON completion response
     * @param {Object} obj - Object to check
     * @returns {boolean}
     */
    isCompletion: function(obj) {
      return obj && typeof obj === 'object' && '@completion' in obj;
    },

    /**
     * Check if object is XJSON error response
     * @param {Object} obj - Object to check
     * @returns {boolean}
     */
    isError: function(obj) {
      return obj && typeof obj === 'object' && '@error' in obj;
    },

    /**
     * Extract text from completion
     * @param {Object} xjson - XJSON completion
     * @returns {string} Extracted text
     */
    extractText: function(xjson) {
      if (this.isCompletion(xjson)) {
        return xjson['@completion']['@text'] || '';
      }
      return '';
    },

    /**
     * Extract error message
     * @param {Object} xjson - XJSON error
     * @returns {string} Error message
     */
    extractError: function(xjson) {
      if (this.isError(xjson)) {
        return xjson['@error']['@message'] || 'Unknown error';
      }
      return '';
    },

    /**
     * Convert Ollama request to XJSON
     * @param {Object} ollamaRequest - Ollama API request
     * @returns {Object} XJSON request
     */
    fromOllamaRequest: function(ollamaRequest) {
      return {
        '@infer': {
          '@runner': 'lam.o',
          '@model': ollamaRequest.model || 'llama3',
          '@prompt': ollamaRequest.prompt || '',
          '@params': {
            temperature: ollamaRequest.options?.temperature ?? 0.7,
            top_p: ollamaRequest.options?.top_p ?? 0.9,
            ...ollamaRequest.options
          },
          '@context': ollamaRequest.context || [],
          '@mode': 'chat'
        }
      };
    },

    /**
     * Convert XJSON to Ollama request
     * @param {Object} xjson - XJSON request
     * @returns {Object} Ollama API request
     */
    toOllamaRequest: function(xjson) {
      const infer = xjson['@infer'] || {};
      const params = infer['@params'] || {};

      return {
        model: infer['@model'],
        prompt: infer['@prompt'],
        stream: false,
        context: infer['@context'] || [],
        options: {
          temperature: params.temperature,
          top_p: params.top_p,
          num_predict: params.max_tokens
        }
      };
    },

    /**
     * Convert Ollama response to XJSON
     * @param {Object} ollamaResponse - Ollama API response
     * @param {Object} request - Original XJSON request
     * @param {number} latencyMs - Request latency
     * @returns {Object} XJSON response
     */
    fromOllamaResponse: function(ollamaResponse, request, latencyMs) {
      const infer = request['@infer'] || {};

      return {
        '@completion': {
          '@model': infer['@model'] || ollamaResponse.model || 'unknown',
          '@runner': 'lam.o',
          '@text': ollamaResponse.response || ollamaResponse.message?.content || '',
          '@tokens': {
            input: ollamaResponse.prompt_eval_count || 0,
            output: ollamaResponse.eval_count || 0
          },
          '@metrics': {
            latency_ms: latencyMs,
            backend: 'ollama',
            total_duration: ollamaResponse.total_duration || 0,
            load_duration: ollamaResponse.load_duration || 0,
            eval_duration: ollamaResponse.eval_duration || 0,
            tokens_per_second: ollamaResponse.eval_count ?
              (ollamaResponse.eval_count / (ollamaResponse.eval_duration / 1e9)) : 0
          }
        }
      };
    },

    /**
     * Merge XJSON objects
     * @param {...Object} objects - XJSON objects to merge
     * @returns {Object} Merged XJSON
     */
    merge: function(...objects) {
      const result = {};

      for (const obj of objects) {
        for (const key of Object.keys(obj)) {
          if (key.startsWith('@')) {
            result[key] = { ...(result[key] || {}), ...obj[key] };
          } else {
            result[key] = obj[key];
          }
        }
      }

      return result;
    },

    /**
     * Pretty print XJSON
     * @param {Object} xjson - XJSON object
     * @returns {string} Formatted JSON string
     */
    format: function(xjson) {
      return JSON.stringify(xjson, null, 2);
    },

    /**
     * Parse XJSON string
     * @param {string} str - JSON string
     * @returns {Object} Parsed XJSON
     */
    parse: function(str) {
      try {
        return JSON.parse(str);
      } catch (e) {
        return this.createErrorResponse({
          message: `Parse error: ${e.message}`,
          code: 400
        });
      }
    },

    /**
     * Validate the K'UHUL XSL semantic-binding descriptor. This validates
     * data structure only; it does not admit or dispatch a Micronaut.
     */
    validateSemanticBindings: function(descriptor) {
      const errors = [];
      if (!descriptor || typeof descriptor !== 'object' || Array.isArray(descriptor)) {
        return { valid: false, errors: ['Descriptor root must be an object'] };
      }
      if (descriptor['@meta']?.['@format'] !== 'kuhul.xsl.semantic-bindings/1') {
        errors.push('Unsupported or missing @meta.@format');
      }
      for (const [phase, code] of Object.entries({
        Pop: '000', Wo: '001', Yax: '010', Sek: '011', "Ch'en": '100', Xul: '101'
      })) {
        if (descriptor['@phases']?.[phase]?.['@code'] !== code) {
          errors.push(`Missing or invalid phase binding: ${phase}`);
        }
      }
      if (!descriptor['@micronauts'] || typeof descriptor['@micronauts'] !== 'object') {
        errors.push('Missing @micronauts semantic bindings');
      }
      if (descriptor['@xcfe']?.['@admission'] !== 'external_per_invocation') {
        errors.push('XCFE admission must remain external per invocation');
      }
      if (!descriptor['@apiRoutes']?.['@routes']?.descriptor?.['@path'] ||
          !descriptor['@apiRoutes']?.['@routes']?.stylesheet?.['@path'] ||
          !descriptor['@apiRoutes']?.['@routes']?.['context-fields']?.['@path'] ||
          !descriptor['@apiRoutes']?.['@routes']?.['intent-graph']?.['@path'] ||
          !descriptor['@apiRoutes']?.['@routes']?.['intent-questions']?.['@path']) {
        errors.push('Missing XJSON API route bindings');
      }
      if (descriptor['@topology']?.['@intentGraph']?.['@schema'] !== 'kgf.intent-graph/1' ||
          descriptor['@topology']?.['@intentGraph']?.['@effect'] !== 'proposal_only') {
        errors.push('Missing proposal-only intent graph binding');
      }
      return { valid: errors.length === 0, errors };
    },

    /** Resolve a read-only semantic binding from the XJSON map structure. */
    resolveSemanticBinding: function(descriptor, options = {}) {
      const validation = this.validateSemanticBindings(descriptor);
      if (!validation.valid) throw new Error(validation.errors.join('; '));
      let value = descriptor;
      if (options.micronaut) value = value['@micronauts'][options.micronaut];
      if (options.phase) {
        value = options.micronaut
          ? value?.['@phaseBindings']?.[options.phase]
          : value?.['@phases']?.[options.phase];
      }
      const path = Array.isArray(options.keyPath)
        ? options.keyPath
        : (options.keyPath ? String(options.keyPath).split('.') : []);
      for (const part of path) {
        if (Array.isArray(value)) {
          const index = Number(part);
          if (!Number.isInteger(index) || index < 1) throw new Error(`Invalid one-based XJSON array index: ${part}`);
          value = value[index - 1];
        } else {
          value = value?.[part];
        }
      }
      if (value === undefined) throw new Error('Semantic binding was not found');
      return value;
    },

    /** Read a route from the descriptor; routes describe transport, not authority. */
    semanticRoute: function(descriptor, routeId, method) {
      const validation = this.validateSemanticBindings(descriptor);
      if (!validation.valid) throw new Error(validation.errors.join('; '));
      const route = descriptor['@apiRoutes']?.['@routes']?.[routeId];
      if (!route || (method && route['@method'] !== method)) {
        throw new Error(`Unknown or incompatible semantic route: ${routeId}`);
      }
      return route['@path'];
    },

    /** Reversibly encode JSON values as the XJSON XML-node vocabulary. */
    toSemanticXml: function(value) {
      const validXml = (text) => {
        for (const character of text) {
          const cp = character.codePointAt(0);
          if (!(cp === 0x9 || cp === 0xA || cp === 0xD ||
                (cp >= 0x20 && cp <= 0xD7FF) ||
                (cp >= 0xE000 && cp <= 0xFFFD) ||
                (cp >= 0x10000 && cp <= 0x10FFFF))) {
            throw new Error('Value contains a character forbidden by XML 1.0');
          }
        }
        return text;
      };
      const textEscape = (input) => validXml(String(input))
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/\r/g, '&#xD;');
      const attrEscape = (input) => validXml(String(input))
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;')
        .replace(/\t/g, '&#x9;').replace(/\n/g, '&#xA;').replace(/\r/g, '&#xD;');
      const encode = (item, tag, extra = '') => {
        if (item === null) return `<xj:${tag}${extra} kind="null"/>`;
        if (Array.isArray(item)) {
          return `<xj:${tag}${extra} kind="array">${item.map(child => encode(child, 'item')).join('')}</xj:${tag}>`;
        }
        if (typeof item === 'object') {
          const children = Object.keys(item).map(key => encode(item[key], 'entry', ` key="${attrEscape(key)}"`)).join('');
          return `<xj:${tag}${extra} kind="object">${children}</xj:${tag}>`;
        }
        if (typeof item === 'boolean') return `<xj:${tag}${extra} kind="boolean">${item}</xj:${tag}>`;
        if (typeof item === 'number') {
          if (!Number.isFinite(item)) throw new Error('XJSON numbers must be finite');
          const kind = Number.isInteger(item) ? 'integer' : 'number';
          return `<xj:${tag}${extra} kind="${kind}">${item}</xj:${tag}>`;
        }
        if (typeof item === 'string') return `<xj:${tag}${extra} kind="string">${textEscape(item)}</xj:${tag}>`;
        throw new Error(`Unsupported XJSON value type: ${typeof item}`);
      };
      return `<?xml version="1.0" encoding="UTF-8"?>${encode(value, 'value', ' xmlns:xj="https://kuhul.dev/xjson/1" version="1"')}`;
    },

    /** Fetch XJSON or XML-node bindings from the loopback XSL interface. */
    fetchSemanticBindings: async function(baseUrl = 'http://127.0.0.1:6171', format = 'json') {
      if (format !== 'json' && format !== 'xml') throw new Error('format must be json or xml');
      const descriptorResponse = await fetch(new URL('/api/xsl/descriptor', baseUrl));
      if (!descriptorResponse.ok) throw new Error(`XJSON bindings API returned HTTP ${descriptorResponse.status}`);
      const descriptor = await descriptorResponse.json();
      const validation = this.validateSemanticBindings(descriptor);
      if (!validation.valid) throw new Error(validation.errors.join('; '));
      if (format === 'json') return descriptor;
      const xmlPath = this.semanticRoute(descriptor, 'xml', 'GET');
      const response = await fetch(new URL(xmlPath, baseUrl));
      if (!response.ok) throw new Error(`XJSON XML projection returned HTTP ${response.status}`);
      return response.text();
    },

    fetchSemanticStylesheet: async function(baseUrl = 'http://127.0.0.1:6171') {
      const descriptor = await this.fetchSemanticBindings(baseUrl, 'json');
      const path = this.semanticRoute(descriptor, 'stylesheet', 'GET');
      const response = await fetch(new URL(path, baseUrl));
      if (!response.ok) throw new Error(`XSL stylesheet endpoint returned HTTP ${response.status}`);
      return response.text();
    },

    /** Submit user context for field proposal generation; never commits it. */
    proposeSemanticFields: async function(prompt, options = {}, baseUrl = 'http://127.0.0.1:6171') {
      if (typeof prompt !== 'string' || !prompt.trim()) throw new Error('prompt must be a non-empty string');
      const descriptor = await this.fetchSemanticBindings(baseUrl, 'json');
      const route = this.semanticRoute(descriptor, 'context-fields', 'POST');
      const response = await fetch(new URL(route, baseUrl), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          prompt: prompt.trim(),
          field_count: options.fieldCount ?? 4,
          keys_per_field: options.keysPerField ?? 8
        })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Field proposal API returned HTTP ${response.status}`);
      return result;
    },

    /** Read the validated intent topology; the graph carries no dispatch authority. */
    fetchIntentGraph: async function(baseUrl = 'http://127.0.0.1:6171') {
      const descriptor = await this.fetchSemanticBindings(baseUrl, 'json');
      const path = this.semanticRoute(descriptor, 'intent-graph', 'GET');
      const response = await fetch(new URL(path, baseUrl));
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Intent graph API returned HTTP ${response.status}`);
      if (result['@kind'] !== 'kgf.intent-graph/1' || result['@authority'] !== 'data_only') {
        throw new Error('Intent graph response does not match its data-only contract');
      }
      return result;
    },

    /** Request question candidates for a CFPC-classified gap; never admits or dispatches. */
    proposeIntentQuestions: async function(fieldKey, prompt, options = {}, baseUrl = 'http://127.0.0.1:6171') {
      if (typeof fieldKey !== 'string' || !fieldKey.trim()) throw new Error('fieldKey must be a non-empty string');
      if (typeof prompt !== 'string' || !prompt.trim()) throw new Error('prompt must be a non-empty string');
      const descriptor = await this.fetchSemanticBindings(baseUrl, 'json');
      const path = this.semanticRoute(descriptor, 'intent-questions', 'POST');
      const response = await fetch(new URL(path, baseUrl), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          field_key: fieldKey.trim(),
          prompt: prompt.trim(),
          weight: options.weight ?? 0.5,
          confidence: options.confidence ?? 0.5,
          relativity: options.relativity ?? 0.5,
          gate: options.gate ?? 1.0
        })
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Intent question API returned HTTP ${response.status}`);
      if (result['@kind'] !== 'kgf.intent-graph.question-proposals.v1' ||
          result['@authority'] !== 'proposal_only' || result['@admission'] !== 'not_evaluated') {
        throw new Error('Intent graph response violates the proposal-only contract');
      }
      return result;
    }
  };

  // Export
  global.XJSON = XJSON;

  // CommonJS/Node.js export
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { XJSON };
  }

})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this);
