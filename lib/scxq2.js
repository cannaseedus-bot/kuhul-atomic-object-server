/**
 * SCXQ2 Fingerprint Generator
 *
 * Generates deterministic fingerprints for K'uhul model inference operations.
 * Implements the SCXQ2-v1 specification for identity verification.
 *
 * SCX IR Lowering:
 *   SCXQ2_COMPUTE(GEOM_CTX) -> hash(canonical_payload) -> SCXQ2:hash
 */

(function(global) {
  'use strict';

  const SCXQ2_VERSION = 'SCXQ2-v1';

  /**
   * SCXQ2 Module
   */
  const SCXQ2 = {
    version: SCXQ2_VERSION,

    /**
     * Build canonical payload from inference request/response
     * @param {Object} reqXJSON - XJSON request object
     * @param {Object} resXJSON - XJSON response object
     * @returns {string} Canonical JSON payload string
     */
    buildPayloadFromInference: function(reqXJSON, resXJSON) {
      const infer = reqXJSON['@infer'] || {};
      const completion = resXJSON['@completion'] || {};

      const payload = {
        runner: infer['@runner'] || 'lam.o',
        model: infer['@model'] || 'unknown',
        mode: infer['@mode'] || null,
        params: this._sortObject(infer['@params'] || {}),
        prompt_shape: {
          length: (infer['@prompt'] || '').length,
          has_context: !!(infer['@context'] && infer['@context'].length),
          context_length: (infer['@context'] || []).length
        },
        metrics: this._sortObject(completion['@metrics'] || {}),
        tokens: this._sortObject(completion['@tokens'] || {}),
        timestamp_bucket: Math.floor(Date.now() / 60000) // 1-minute buckets
      };

      return JSON.stringify(payload);
    },

    /**
     * Build payload from symbolic DOM element
     * @param {HTMLElement} element - DOM element with K'uhul attributes
     * @returns {string} Canonical JSON payload string
     */
    buildPayloadFromDOM: function(element) {
      const payload = {
        glyph: element.dataset.kuhulGlyph || null,
        semantic: element.dataset.kuhulSemantic || null,
        role: element.dataset.kuhulRole || null,
        capabilities: element.dataset.kuhulCapabilities?.split(',') || [],
        fold: element.dataset.kuhulFold || null,
        tag: element.tagName.toLowerCase(),
        id: element.id || null,
        classes: Array.from(element.classList).sort(),
        children_count: element.children.length
      };

      return JSON.stringify(this._sortObject(payload));
    },

    /**
     * Build payload from SCX IR operation
     * @param {string} operation - SCX IR operation name
     * @param {Object} context - Operation context
     * @returns {string} Canonical JSON payload string
     */
    buildPayloadFromSCXIR: function(operation, context) {
      const payload = {
        operation: operation,
        context: this._sortObject(context),
        timestamp_bucket: Math.floor(Date.now() / 60000)
      };

      return JSON.stringify(payload);
    },

    /**
     * Generate SCXQ2 fingerprint from payload
     * @param {string} payload - Canonical payload string
     * @returns {Promise<string>} SCXQ2 fingerprint
     */
    async fingerprint: async function(payload) {
      const hash = await this._hash(payload);
      return `${SCXQ2_VERSION}:${hash}`;
    },

    /**
     * Generate SCXQ2 fingerprint from inference pair
     * @param {Object} reqXJSON - XJSON request
     * @param {Object} resXJSON - XJSON response
     * @returns {Promise<string>} SCXQ2 fingerprint
     */
    async fromInference: async function(reqXJSON, resXJSON) {
      const payload = this.buildPayloadFromInference(reqXJSON, resXJSON);
      return this.fingerprint(payload);
    },

    /**
     * Generate SCXQ2 fingerprint from DOM element
     * @param {HTMLElement} element - DOM element
     * @returns {Promise<string>} SCXQ2 fingerprint
     */
    async fromDOM: async function(element) {
      const payload = this.buildPayloadFromDOM(element);
      return this.fingerprint(payload);
    },

    /**
     * Generate SCXQ2 fingerprint from SCX IR operation
     * @param {string} operation - SCX IR operation
     * @param {Object} context - Operation context
     * @returns {Promise<string>} SCXQ2 fingerprint
     */
    async fromSCXIR: async function(operation, context) {
      const payload = this.buildPayloadFromSCXIR(operation, context);
      return this.fingerprint(payload);
    },

    /**
     * Verify SCXQ2 fingerprint
     * @param {string} fingerprint - SCXQ2 fingerprint to verify
     * @param {string} payload - Payload to verify against
     * @returns {Promise<boolean>} True if valid
     */
    async verify: async function(fingerprint, payload) {
      if (!fingerprint || !fingerprint.startsWith(SCXQ2_VERSION)) {
        return false;
      }

      const expected = await this.fingerprint(payload);
      return fingerprint === expected;
    },

    /**
     * Extract metadata from SCXQ2 fingerprint
     * @param {string} fingerprint - SCXQ2 fingerprint
     * @returns {Object} Metadata object
     */
    parse: function(fingerprint) {
      if (!fingerprint || typeof fingerprint !== 'string') {
        return null;
      }

      const parts = fingerprint.split(':');
      if (parts.length !== 2) {
        return null;
      }

      return {
        version: parts[0],
        hash: parts[1],
        short: parts[1].substring(0, 8),
        valid: parts[0] === SCXQ2_VERSION
      };
    },

    /**
     * Attach SCXQ2 to element
     * @param {HTMLElement} element - Target element
     * @param {string} fingerprint - SCXQ2 fingerprint
     */
    attach: function(element, fingerprint) {
      if (element && fingerprint) {
        element.dataset.scxq2 = fingerprint;
      }
    },

    /**
     * Get SCXQ2 from element
     * @param {HTMLElement} element - Target element
     * @returns {string|null} SCXQ2 fingerprint or null
     */
    get: function(element) {
      return element?.dataset?.scxq2 || null;
    },

    /**
     * Compute deterministic hash (SHA-256)
     * @private
     * @param {string} data - Data to hash
     * @returns {Promise<string>} Hex hash string
     */
    _hash: async function(data) {
      // Use Web Crypto API if available
      if (typeof crypto !== 'undefined' && crypto.subtle) {
        const encoder = new TextEncoder();
        const dataBuffer = encoder.encode(data);
        const hashBuffer = await crypto.subtle.digest('SHA-256', dataBuffer);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        return hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
      }

      // Fallback: simple hash for environments without Web Crypto
      return this._fallbackHash(data);
    },

    /**
     * Fallback hash function (simple djb2 variant)
     * @private
     * @param {string} str - String to hash
     * @returns {string} Hex hash string
     */
    _fallbackHash: function(str) {
      let hash1 = 5381;
      let hash2 = 5381;

      for (let i = 0; i < str.length; i++) {
        const c = str.charCodeAt(i);
        hash1 = ((hash1 << 5) + hash1) ^ c;
        hash2 = ((hash2 << 5) + hash2) ^ (c * 33);
      }

      const combined = (hash1 >>> 0).toString(16).padStart(8, '0') +
                       (hash2 >>> 0).toString(16).padStart(8, '0');

      return combined.repeat(4).substring(0, 64);
    },

    /**
     * Sort object keys for deterministic serialization
     * @private
     * @param {Object} obj - Object to sort
     * @returns {Object} Sorted object
     */
    _sortObject: function(obj) {
      if (obj === null || typeof obj !== 'object') {
        return obj;
      }

      if (Array.isArray(obj)) {
        return obj.map(item => this._sortObject(item));
      }

      const sorted = {};
      const keys = Object.keys(obj).sort();

      for (const key of keys) {
        sorted[key] = this._sortObject(obj[key]);
      }

      return sorted;
    }
  };

  // SCX IR Operations for SCXQ2
  const SCXQ2_IR = {
    /**
     * SCX_STORE operation
     * @param {string} path - Storage path
     * @param {any} value - Value to store
     * @returns {Object} IR instruction
     */
    store: function(path, value) {
      return {
        op: 'SCX_STORE',
        path: path,
        value_type: typeof value,
        value_size: JSON.stringify(value).length
      };
    },

    /**
     * SCXQ2_COMPUTE operation
     * @param {string} context - Context type (GEOM_CTX, ERROR_CTX, etc.)
     * @returns {Object} IR instruction
     */
    compute: function(context) {
      return {
        op: 'SCXQ2_COMPUTE',
        context: context,
        version: SCXQ2_VERSION
      };
    },

    /**
     * SCXQ2_ATTACH operation
     * @param {string} target - Target path
     * @returns {Object} IR instruction
     */
    attach: function(target) {
      return {
        op: 'SCXQ2_ATTACH',
        target: target,
        version: SCXQ2_VERSION
      };
    },

    /**
     * SCX_ERROR operation
     * @param {string|number} code - Error code
     * @param {string} message - Error message
     * @returns {Object} IR instruction
     */
    error: function(code, message) {
      return {
        op: 'SCX_ERROR',
        code: code,
        message: message
      };
    }
  };

  // Export
  global.SCXQ2 = SCXQ2;
  global.SCXQ2_IR = SCXQ2_IR;

  // CommonJS/Node.js export
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { SCXQ2, SCXQ2_IR };
  }

})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this);
