/**
 * K'uhul Pack Definitions
 *
 * Central registry for all K'uhul packs in the system.
 * Each pack defines a capability domain with Pops, Seks, and Wos.
 */

(function(global) {
  'use strict';

  // ============================================
  // Pack Registry
  // ============================================

  const KuhulPacks = {
    _packs: {},
    _initialized: false,

    /**
     * Register a pack
     * @param {Object} pack - Pack definition
     */
    register: function(pack) {
      if (!pack.id) {
        console.error('[KuhulPacks] Pack must have an id');
        return;
      }
      this._packs[pack.id] = pack;
      console.log(`[KuhulPacks] Registered pack: ${pack.id}`);
    },

    /**
     * Get a pack by ID
     * @param {string} id - Pack ID
     * @returns {Object|null}
     */
    get: function(id) {
      return this._packs[id] || null;
    },

    /**
     * List all registered packs
     * @returns {Object[]}
     */
    list: function() {
      return Object.values(this._packs);
    },

    /**
     * Initialize all packs
     */
    init: function() {
      if (this._initialized) return;

      // Register built-in packs
      this.register(PACK_LAM_O);
      this.register(PACK_PI_GOAT);
      this.register(PACK_SCXQ2);
      this.register(PACK_ASX_RAM);
      this.register(PACK_MX2LM);

      this._initialized = true;
      console.log(`[KuhulPacks] Initialized ${Object.keys(this._packs).length} packs`);
    },

    /**
     * Get pack manifest for OS registration
     * @returns {Object}
     */
    getManifest: function() {
      const packs = {};
      for (const [id, pack] of Object.entries(this._packs)) {
        packs[id] = {
          n: pack.name,
          t: pack.role,
          f: pack.fold,
          fn: pack.functions,
          ca: pack.capabilities,
          st: 'live'
        };
      }
      return packs;
    }
  };

  // ============================================
  // Pack Definitions
  // ============================================

  /**
   * Pack: lam.o - Ollama Model Runner
   */
  const PACK_LAM_O = {
    id: 'pack_lam_o',
    name: 'Ollama Model Runner Pack',
    role: 'model_runner_backend',
    fold: 'AI',
    functions: [
      'lam.o.infer',
      'lam.o.describe',
      'lam.o.health',
      'lam.o.models',
      'lam.o.caps'
    ],
    capabilities: [
      'multiple_models',
      'local_inference',
      'model_management',
      'streaming',
      'xjson_protocol'
    ],
    seal: {
      position: [-8, 0, 0],
      glyph: '⚛️',
      geometry: 'torus_lattice',
      color: '#00FF88'
    },
    pops: {
      'lam.o.infer': {
        params: {
          model: 'string',
          prompt: 'string',
          params: 'map?',
          mode: 'string?'
        },
        returns: '@completion'
      },
      'lam.o.health': {
        params: {},
        returns: 'health_status'
      },
      'lam.o.models': {
        params: {},
        returns: 'model_list'
      }
    },
    seks: {
      'model_pipeline': 'route -> infer -> compress -> log'
    }
  };

  /**
   * Pack: Pi-GOAT - Polyglot AST Engine
   */
  const PACK_PI_GOAT = {
    id: 'pack_pi_goat',
    name: 'Pi-GOAT Polyglot AST Engine',
    role: 'polyglot_runtime_provider',
    fold: 'RUNTIME',
    functions: [
      'pi_goat.dispatch',
      'pi_goat.detect',
      'pi_goat.parse',
      'pi_goat.normalize',
      'pi_goat.route',
      'pi_goat.execute',
      'pi_goat.run_code',
      'pi_goat.run_chat',
      'pi_goat.run_kuhul',
      'pi_goat.register_runtime',
      'pi_goat.register_adapter'
    ],
    capabilities: [
      'javascript_runtime',
      'typescript_runtime',
      'python_runtime',
      'java_runtime',
      'kuhul_runtime',
      'xjson_runtime',
      'model_runtime',
      'ast_normalization',
      'language_detection',
      'virtual_sandbox',
      'scxq2_fingerprinting'
    ],
    seal: {
      position: [-4, 0, 0.5],
      glyph: '🐐',
      geometry: 'octahedron_rotating',
      color: '#FF6B35'
    },
    pops: {
      'pi_goat.dispatch': {
        params: {
          source: 'string',
          mode: 'string?',
          hintLanguage: 'string?',
          context: 'map?'
        },
        returns: 'pi_goat_response'
      },
      'pi_goat.run_code': {
        params: {
          source: 'string',
          language: 'string?'
        },
        returns: 'execution_result'
      }
    },
    seks: {
      'ast_pipeline': 'detect -> parse -> normalize -> route -> execute -> compress'
    },
    runtimes: {
      'js_runtime': {
        engine: 'sandbox_function',
        sandbox: true,
        async: true
      },
      'python_runtime': {
        engine: 'pyodide_or_virtual',
        sandbox: true,
        async: true
      },
      'java_runtime': {
        engine: 'virtual',
        sandbox: true
      },
      'kuhul_runtime': {
        engine: 'kuhul_pop',
        sandbox: false
      },
      'xjson_runtime': {
        engine: 'json_parse',
        sandbox: true
      },
      'model_runtime': {
        engine: 'kuhul_client',
        sandbox: false,
        async: true
      }
    }
  };

  /**
   * Pack: SCXQ2 - Semantic Compression
   */
  const PACK_SCXQ2 = {
    id: 'pack_scxq2',
    name: 'SCXQ2 Compression Engine',
    role: 'semantic_compression',
    fold: 'COMPRESSION',
    functions: [
      'scxq2.fingerprint',
      'scxq2.from_inference',
      'scxq2.from_dom',
      'scxq2.from_scx_ir',
      'scxq2.verify',
      'scxq2.attach',
      'scxq2.parse'
    ],
    capabilities: [
      'sha256_hashing',
      'deterministic_fingerprinting',
      'inference_verification',
      'dom_fingerprinting',
      'scx_ir_integration'
    ],
    seal: {
      position: [8, 0, 0],
      glyph: '🗜️',
      geometry: 'torus_adaptive',
      color: '#FFFF00'
    },
    pops: {
      'scxq2.fingerprint': {
        params: { payload: 'string' },
        returns: 'scxq2_hash'
      },
      'scxq2.verify': {
        params: { fingerprint: 'string', payload: 'string' },
        returns: 'boolean'
      }
    }
  };

  /**
   * Pack: ASX RAM - Memory Layer
   */
  const PACK_ASX_RAM = {
    id: 'pack_asx_ram',
    name: 'ASX RAM + IDB Memory',
    role: 'dual_layer_storage',
    fold: 'MEMORY',
    functions: [
      'asx.set',
      'asx.get',
      'asx.delete',
      'asx.clear',
      'asx.persist',
      'asx.restore',
      'asx.list_keys',
      'asx.get_size'
    ],
    capabilities: [
      'volatile_storage',
      'persistent_storage',
      'idb_integration',
      'compression_cache',
      'chat_history'
    ],
    seal: {
      position: [12, 0, 0.5],
      glyph: '🧬',
      geometry: 'crystal_fractured',
      color: '#FF00FF'
    },
    pops: {
      'asx.set': {
        params: { key: 'string', value: 'any', persist: 'boolean?' },
        returns: 'void'
      },
      'asx.get': {
        params: { key: 'string' },
        returns: 'any'
      }
    }
  };

  /**
   * Pack: MX2LM - Central Orchestrator
   */
  const PACK_MX2LM = {
    id: 'pack_mx2lm',
    name: 'MX2LM Quantum Chat Intelligence',
    role: 'central_orchestrator',
    fold: 'INTELLIGENCE',
    functions: [
      'mx2lm.orchestrate',
      'mx2lm.route_language',
      'mx2lm.coordinate_seals',
      'mx2lm.broadcast',
      'mx2lm.receive',
      'mx2lm.infer_intent'
    ],
    capabilities: [
      'polyglot_awareness',
      'seal_coordination',
      'real_time_chat',
      'code_suggestions',
      'language_translation',
      'debugging_help',
      'intent_inference'
    ],
    seal: {
      position: [4, 2, -2],
      glyph: '🧠',
      geometry: 'neural_sphere_quantum',
      color: '#00F0FF'
    },
    broadcasts: [
      'GLYPH_EXPANSION_SIGNALS',
      'LANGUAGE_DISPATCH_HINTS',
      'COMPRESSION_RATIOS',
      'EXECUTION_STATUS',
      'CHAT_CONTEXT'
    ],
    receives: [
      'SEAL_STATUS_UPDATES',
      'EXECUTION_RESULTS',
      'LANGUAGE_SELECTION',
      'COMPRESSION_METRICS',
      'USER_INTENT'
    ],
    pops: {
      'mx2lm.orchestrate': {
        params: { input: 'string', context: 'map?' },
        returns: 'orchestration_result'
      }
    }
  };

  // ============================================
  // Horizontal Ribbon Seal Configuration
  // ============================================

  const SEAL_RIBBON = {
    name: 'Horizontal Seal Ribbon',
    geometry: {
      start: [-8, 0, 0],
      end: [16, 0, 0],
      length: 24,
      center: [4, 0, 0],
      mx2lm_offset: [0, 2, -2]
    },
    seals: [
      { id: 'SEAL_0_KUHUL', position: [-8, 0, 0], glyph: '🔤', color: '#00FF00', pack: 'pack_lam_o' },
      { id: 'SEAL_1_JAVASCRIPT', position: [-4, 0, 0.5], glyph: '💻', color: '#FFFF00', pack: 'pack_pi_goat' },
      { id: 'SEAL_2_JAVA', position: [0, 0, 1.0], glyph: '☕', color: '#FF6600', pack: 'pack_pi_goat' },
      { id: 'SEAL_3_PYTHON', position: [4, 0, 0.5], glyph: '🐍', color: '#3776AB', pack: 'pack_pi_goat' },
      { id: 'SEAL_4_COMPRESSION', position: [8, 0, 0], glyph: '🗜️', color: '#FFFF00', pack: 'pack_scxq2' },
      { id: 'SEAL_5_MEMORY', position: [12, 0, 0.5], glyph: '🧬', color: '#FF00FF', pack: 'pack_asx_ram' },
      { id: 'SEAL_6_INTEGRATION', position: [16, 0, 0], glyph: '🏁', color: '#FFFFFF', pack: 'pack_mx2lm' }
    ],
    mx2lm: { id: 'MX2LM_CENTRAL', position: [4, 2, -2], glyph: '🧠', color: '#00F0FF', pack: 'pack_mx2lm' }
  };

  // ============================================
  // Export
  // ============================================

  global.KuhulPacks = KuhulPacks;
  global.SEAL_RIBBON = SEAL_RIBBON;

  // Individual pack exports
  global.PACK_LAM_O = PACK_LAM_O;
  global.PACK_PI_GOAT = PACK_PI_GOAT;
  global.PACK_SCXQ2 = PACK_SCXQ2;
  global.PACK_ASX_RAM = PACK_ASX_RAM;
  global.PACK_MX2LM = PACK_MX2LM;

  // CommonJS/Node.js export
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
      KuhulPacks,
      SEAL_RIBBON,
      PACK_LAM_O,
      PACK_PI_GOAT,
      PACK_SCXQ2,
      PACK_ASX_RAM,
      PACK_MX2LM
    };
  }

})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this);
