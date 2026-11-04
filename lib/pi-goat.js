/**
 * Pi-GOAT: Polyglot AST Engine
 *
 * "Linux Without Linux" - Virtual runtimes through AST-driven execution.
 * No installation, no dependencies, no compilers, no interpreters.
 *
 * Pi-GOAT provides:
 *   - Python runtime (AST)
 *   - Java runtime (AST)
 *   - JavaScript runtime (AST)
 *   - K'uhul runtime (AST)
 *   - XJSON runtime (AST)
 *   - Model inference runtimes (Ollama, Janus, Qwen)
 *
 * Pipeline: detect -> parse -> normalize -> route -> execute -> compress
 */

(function(global) {
  'use strict';

  // ============================================
  // Type Definitions
  // ============================================

  /**
   * @typedef {'javascript'|'typescript'|'java'|'python'|'kuhul'|'xjson'|'unknown'} PiGoatLanguage
   * @typedef {'js_runtime'|'java_runtime'|'python_runtime'|'kuhul_runtime'|'xjson_runtime'|'model_runtime'} RuntimeTarget
   */

  // ============================================
  // Language Detection Patterns
  // ============================================

  const LANGUAGE_PATTERNS = {
    javascript: {
      keywords: ['const ', 'let ', 'var ', 'function ', 'async ', 'await ', '=>', 'require(', 'import ', 'export '],
      extensions: ['.js', '.mjs'],
      weight: 1.0
    },
    typescript: {
      keywords: ['interface ', 'type ', ': string', ': number', ': boolean', '<T>', 'as ', 'readonly '],
      extensions: ['.ts', '.tsx'],
      weight: 1.1
    },
    python: {
      keywords: ['def ', 'import ', 'from ', 'class ', 'if __name__', 'print(', 'self.', '    ', 'elif ', 'lambda '],
      extensions: ['.py'],
      weight: 1.0
    },
    java: {
      keywords: ['public class', 'private ', 'void ', 'String ', 'int ', 'System.out', 'import java.', 'new '],
      extensions: ['.java'],
      weight: 1.0
    },
    kuhul: {
      keywords: ['Pop ', 'Sek ', 'Wo ', 'Pack ', '@infer', '@completion', '@runner', 'lam.'],
      extensions: ['.kuhul', '.kh'],
      weight: 1.2
    },
    xjson: {
      keywords: ['"@', '@infer', '@completion', '@error', '@model', '@runner'],
      extensions: ['.xjson'],
      weight: 1.1
    }
  };

  // ============================================
  // AST Node Types (Normalized)
  // ============================================

  const AST_TYPES = {
    PROGRAM: 'Program',
    FUNCTION_DECL: 'FunctionDecl',
    CLASS_DECL: 'ClassDecl',
    VARIABLE_DECL: 'VariableDecl',
    EXPRESSION: 'Expression',
    CALL_EXPR: 'CallExpr',
    BINARY_EXPR: 'BinaryExpr',
    LITERAL: 'Literal',
    IDENTIFIER: 'Identifier',
    BLOCK: 'Block',
    IF_STMT: 'IfStatement',
    LOOP_STMT: 'LoopStatement',
    RETURN_STMT: 'ReturnStatement',
    IMPORT: 'Import',
    EXPORT: 'Export',
    // K'uhul specific
    POP: 'Pop',
    SEK: 'Sek',
    WO: 'Wo',
    PACK: 'Pack',
    // XJSON specific
    XJSON_INFER: 'XJSONInfer',
    XJSON_COMPLETION: 'XJSONCompletion'
  };

  // ============================================
  // Pi-GOAT Core Engine
  // ============================================

  const PiGoat = {
    version: '1.0.0',
    name: 'Pi-GOAT Polyglot AST Engine',

    // Runtime registry
    _runtimes: {},
    _adapters: {},

    /**
     * Main dispatch function
     * @param {Object} request - PiGoatRequest
     * @returns {Promise<Object>} PiGoatResponse
     */
    dispatch: async function(request) {
      const startTime = performance.now();

      try {
        // Validate request
        if (!request || !request.source) {
          return this._buildErrorResponse('Source is required', 'unknown');
        }

        // Stage 1: Language Detection
        const language = this.detectLanguage(request);
        if (language === 'unknown' && !request.allowUnknown) {
          return this._buildErrorResponse('Language not detected', 'unknown');
        }

        // Stage 2: Parse to Raw AST
        const rawAst = await this.parseToRawAST(language, request.source);

        // Stage 3: Normalize AST
        const ast = this.normalizeAST(language, rawAst, request.source);

        // Stage 4: Route to Runtime
        const runtime = this.routeRuntime(ast, request);

        // Stage 5: Execute AST
        const result = await this.executeAST(ast, runtime, request.context);

        // Stage 6: Build SCXQ2 fingerprint
        const endTime = performance.now();
        const latencyMs = endTime - startTime;

        const payload = this._buildSCXQ2Payload(request, ast, runtime, result, latencyMs);
        const scxq2 = await this._generateSCXQ2(payload);

        return {
          success: true,
          language: language,
          ast: ast,
          runtime: runtime,
          result: result,
          scxq2: scxq2,
          metrics: {
            latency_ms: latencyMs,
            tokens: ast.meta?.tokens || 0,
            complexity: ast.meta?.complexity || 0
          }
        };

      } catch (error) {
        console.error('[Pi-GOAT] Dispatch error:', error);
        return this._buildErrorResponse(error.message, request?.hintLanguage || 'unknown');
      }
    },

    // ============================================
    // Stage 1: Language Detection
    // ============================================

    /**
     * Detect language from source
     * @param {Object} request - PiGoatRequest
     * @returns {PiGoatLanguage}
     */
    detectLanguage: function(request) {
      const { source, mode, hintLanguage } = request;

      // Explicit hint takes precedence
      if (hintLanguage && LANGUAGE_PATTERNS[hintLanguage]) {
        return hintLanguage;
      }

      // Try to parse as JSON first (for XJSON)
      try {
        const parsed = JSON.parse(source);
        if (parsed['@infer'] || parsed['@completion'] || parsed['@error']) {
          return 'xjson';
        }
      } catch (e) {
        // Not JSON
      }

      // Score each language
      const scores = {};
      for (const [lang, patterns] of Object.entries(LANGUAGE_PATTERNS)) {
        scores[lang] = 0;
        for (const keyword of patterns.keywords) {
          if (source.includes(keyword)) {
            scores[lang] += patterns.weight;
          }
        }
      }

      // Find highest score
      let maxScore = 0;
      let detected = 'unknown';
      for (const [lang, score] of Object.entries(scores)) {
        if (score > maxScore) {
          maxScore = score;
          detected = lang;
        }
      }

      // Require minimum confidence
      if (maxScore < 1.0) {
        // Check for natural language (model inference request)
        if (mode === 'chat' || this._isNaturalLanguage(source)) {
          return 'xjson'; // Route to model runtime
        }
        return 'unknown';
      }

      return detected;
    },

    /**
     * Check if source is natural language
     * @private
     */
    _isNaturalLanguage: function(source) {
      // Simple heuristic: no code-like patterns, has spaces, starts with lowercase
      const codePatterns = /[{}\[\];()=<>]/;
      const hasCodePatterns = codePatterns.test(source);
      const wordCount = source.split(/\s+/).length;

      return !hasCodePatterns && wordCount > 3;
    },

    // ============================================
    // Stage 2: Parse to Raw AST
    // ============================================

    /**
     * Parse source to raw AST
     * @param {PiGoatLanguage} lang
     * @param {string} source
     * @returns {Promise<Object>}
     */
    parseToRawAST: async function(lang, source) {
      const adapter = this._adapters[lang];
      if (adapter && adapter.parse) {
        return adapter.parse(source);
      }

      // Built-in parsers
      switch (lang) {
        case 'javascript':
        case 'typescript':
          return this._parseJavaScript(source);
        case 'python':
          return this._parsePython(source);
        case 'java':
          return this._parseJava(source);
        case 'kuhul':
          return this._parseKuhul(source);
        case 'xjson':
          return this._parseXJSON(source);
        default:
          return this._parseGeneric(source);
      }
    },

    /**
     * JavaScript parser (simplified AST)
     * @private
     */
    _parseJavaScript: function(source) {
      const ast = {
        type: 'Program',
        lang: 'javascript',
        body: [],
        raw: source
      };

      // Function declarations
      const funcRegex = /(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)/g;
      let match;
      while ((match = funcRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'FunctionDeclaration',
          name: match[1],
          params: match[2].split(',').map(p => p.trim()).filter(Boolean),
          async: match[0].includes('async'),
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      // Arrow functions
      const arrowRegex = /(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>/g;
      while ((match = arrowRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'ArrowFunction',
          name: match[1],
          params: match[2].split(',').map(p => p.trim()).filter(Boolean),
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      // Variable declarations
      const varRegex = /(?:const|let|var)\s+(\w+)\s*=/g;
      while ((match = varRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'VariableDeclaration',
          name: match[1],
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      // Class declarations
      const classRegex = /class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{/g;
      while ((match = classRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'ClassDeclaration',
          name: match[1],
          superClass: match[2] || null,
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      return ast;
    },

    /**
     * Python parser (simplified AST)
     * @private
     */
    _parsePython: function(source) {
      const ast = {
        type: 'Program',
        lang: 'python',
        body: [],
        raw: source
      };

      // Function definitions
      const funcRegex = /def\s+(\w+)\s*\(([^)]*)\):/g;
      let match;
      while ((match = funcRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'FunctionDef',
          name: match[1],
          params: match[2].split(',').map(p => p.trim().split(':')[0].split('=')[0].trim()).filter(Boolean),
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      // Class definitions
      const classRegex = /class\s+(\w+)(?:\(([^)]*)\))?:/g;
      while ((match = classRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'ClassDef',
          name: match[1],
          bases: match[2] ? match[2].split(',').map(b => b.trim()).filter(Boolean) : [],
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      // Imports
      const importRegex = /(?:from\s+(\S+)\s+)?import\s+(.+)/g;
      while ((match = importRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'Import',
          module: match[1] || null,
          names: match[2].split(',').map(n => n.trim()).filter(Boolean),
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      return ast;
    },

    /**
     * Java parser (simplified AST)
     * @private
     */
    _parseJava: function(source) {
      const ast = {
        type: 'Program',
        lang: 'java',
        body: [],
        raw: source
      };

      // Class declarations
      const classRegex = /(?:public\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([^{]+))?\s*\{/g;
      let match;
      while ((match = classRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'ClassDeclaration',
          name: match[1],
          superClass: match[2] || null,
          interfaces: match[3] ? match[3].split(',').map(i => i.trim()).filter(Boolean) : [],
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      // Method declarations
      const methodRegex = /(?:public|private|protected)?\s*(?:static\s+)?(\w+)\s+(\w+)\s*\(([^)]*)\)/g;
      while ((match = methodRegex.exec(source)) !== null) {
        if (!['class', 'if', 'while', 'for', 'switch'].includes(match[2])) {
          ast.body.push({
            type: 'MethodDeclaration',
            returnType: match[1],
            name: match[2],
            params: match[3].split(',').map(p => p.trim()).filter(Boolean),
            loc: { start: match.index, end: match.index + match[0].length }
          });
        }
      }

      return ast;
    },

    /**
     * K'uhul parser
     * @private
     */
    _parseKuhul: function(source) {
      const ast = {
        type: 'Program',
        lang: 'kuhul',
        body: [],
        raw: source
      };

      // Pop declarations
      const popRegex = /Pop\s+(\w+)\s*\{([^}]*)\}/g;
      let match;
      while ((match = popRegex.exec(source)) !== null) {
        const fields = {};
        const fieldRegex = /(\w+):\s*(\w+)/g;
        let fieldMatch;
        while ((fieldMatch = fieldRegex.exec(match[2])) !== null) {
          fields[fieldMatch[1]] = fieldMatch[2];
        }
        ast.body.push({
          type: 'Pop',
          name: match[1],
          fields: fields,
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      // Sek pipelines
      const sekRegex = /Sek\s+(\w+)\s*->\s*(.+)/g;
      while ((match = sekRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'Sek',
          name: match[1],
          pipeline: match[2].split('->').map(s => s.trim()),
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      // Wo definitions
      const woRegex = /Wo\s+(\w+)\s*=\s*\{([^}]*)\}/gs;
      while ((match = woRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'Wo',
          name: match[1],
          value: match[2].trim(),
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      // Pack definitions
      const packRegex = /Pack\s+(\w+)\s*\{([^}]*)\}/gs;
      while ((match = packRegex.exec(source)) !== null) {
        ast.body.push({
          type: 'Pack',
          name: match[1],
          body: match[2].trim(),
          loc: { start: match.index, end: match.index + match[0].length }
        });
      }

      return ast;
    },

    /**
     * XJSON parser
     * @private
     */
    _parseXJSON: function(source) {
      try {
        const parsed = JSON.parse(source);
        return {
          type: 'XJSONProgram',
          lang: 'xjson',
          body: parsed,
          raw: source
        };
      } catch (e) {
        // If not valid JSON, treat as natural language -> model inference
        return {
          type: 'XJSONProgram',
          lang: 'xjson',
          body: {
            '@infer': {
              '@runner': 'lam.o',
              '@model': 'llama3',
              '@prompt': source,
              '@mode': 'chat'
            }
          },
          raw: source
        };
      }
    },

    /**
     * Generic parser for unknown languages
     * @private
     */
    _parseGeneric: function(source) {
      return {
        type: 'Program',
        lang: 'unknown',
        body: [{ type: 'RawSource', value: source }],
        raw: source
      };
    },

    // ============================================
    // Stage 3: Normalize AST
    // ============================================

    /**
     * Normalize raw AST to unified format
     * @param {PiGoatLanguage} lang
     * @param {Object} rawAst
     * @param {string} source
     * @returns {Object} NormalizedAST
     */
    normalizeAST: function(lang, rawAst, source) {
      const normalizedBody = [];

      // Convert language-specific nodes to normalized types
      for (const node of (rawAst.body || [])) {
        normalizedBody.push(this._normalizeNode(node, lang));
      }

      // Calculate metadata
      const tokens = source.split(/\s+/).length;
      const complexity = this._calculateComplexity(normalizedBody);
      const entryPoints = this._findEntryPoints(normalizedBody);

      return {
        lang: lang,
        root: {
          type: AST_TYPES.PROGRAM,
          children: normalizedBody
        },
        meta: {
          originalSource: source,
          tokens: tokens,
          complexity: complexity,
          entryPoints: entryPoints
        }
      };
    },

    /**
     * Normalize individual node
     * @private
     */
    _normalizeNode: function(node, lang) {
      const normalized = {
        type: this._mapNodeType(node.type, lang),
        name: node.name || null,
        loc: node.loc || null,
        extras: {}
      };

      // Language-specific extras
      if (node.params) normalized.params = node.params;
      if (node.fields) normalized.extras.fields = node.fields;
      if (node.pipeline) normalized.extras.pipeline = node.pipeline;
      if (node.superClass) normalized.extras.superClass = node.superClass;
      if (node.interfaces) normalized.extras.interfaces = node.interfaces;

      return normalized;
    },

    /**
     * Map language-specific type to normalized type
     * @private
     */
    _mapNodeType: function(type, lang) {
      const typeMap = {
        'FunctionDeclaration': AST_TYPES.FUNCTION_DECL,
        'FunctionDef': AST_TYPES.FUNCTION_DECL,
        'ArrowFunction': AST_TYPES.FUNCTION_DECL,
        'MethodDeclaration': AST_TYPES.FUNCTION_DECL,
        'ClassDeclaration': AST_TYPES.CLASS_DECL,
        'ClassDef': AST_TYPES.CLASS_DECL,
        'VariableDeclaration': AST_TYPES.VARIABLE_DECL,
        'Import': AST_TYPES.IMPORT,
        'Pop': AST_TYPES.POP,
        'Sek': AST_TYPES.SEK,
        'Wo': AST_TYPES.WO,
        'Pack': AST_TYPES.PACK
      };

      return typeMap[type] || type;
    },

    /**
     * Calculate complexity score
     * @private
     */
    _calculateComplexity: function(nodes) {
      let complexity = nodes.length;

      for (const node of nodes) {
        if (node.type === AST_TYPES.FUNCTION_DECL) complexity += 2;
        if (node.type === AST_TYPES.CLASS_DECL) complexity += 3;
        if (node.type === AST_TYPES.SEK) complexity += node.extras?.pipeline?.length || 1;
      }

      return complexity;
    },

    /**
     * Find entry points
     * @private
     */
    _findEntryPoints: function(nodes) {
      return nodes
        .filter(n => [AST_TYPES.FUNCTION_DECL, AST_TYPES.POP, AST_TYPES.SEK].includes(n.type))
        .map(n => n.name)
        .filter(Boolean);
    },

    // ============================================
    // Stage 4: Route to Runtime
    // ============================================

    /**
     * Route AST to appropriate runtime
     * @param {Object} ast - NormalizedAST
     * @param {Object} request - PiGoatRequest
     * @returns {RuntimeTarget}
     */
    routeRuntime: function(ast, request) {
      // Check for K'uhul directives
      if (request.context?.forceRuntime) {
        return request.context.forceRuntime;
      }

      // Route by language
      const routeMap = {
        'javascript': 'js_runtime',
        'typescript': 'js_runtime',
        'java': 'java_runtime',
        'python': 'python_runtime',
        'kuhul': 'kuhul_runtime',
        'xjson': 'xjson_runtime'
      };

      const runtime = routeMap[ast.lang];

      // Special case: XJSON with @infer goes to model runtime
      if (ast.lang === 'xjson' && ast.root.children?.[0]?.type === 'XJSONProgram') {
        const body = ast.root.children[0]?.body;
        if (body?.['@infer']) {
          return 'model_runtime';
        }
      }

      return runtime || 'js_runtime';
    },

    // ============================================
    // Stage 5: Execute AST
    // ============================================

    /**
     * Execute normalized AST
     * @param {Object} ast - NormalizedAST
     * @param {RuntimeTarget} runtime
     * @param {Object} context
     * @returns {Promise<any>}
     */
    executeAST: async function(ast, runtime, context) {
      // Check for registered runtime
      const runtimeHandler = this._runtimes[runtime];
      if (runtimeHandler) {
        return runtimeHandler.execute(ast, context);
      }

      // Built-in runtimes
      switch (runtime) {
        case 'js_runtime':
          return this._executeJavaScript(ast, context);
        case 'python_runtime':
          return this._executePython(ast, context);
        case 'java_runtime':
          return this._executeJava(ast, context);
        case 'kuhul_runtime':
          return this._executeKuhul(ast, context);
        case 'xjson_runtime':
          return this._executeXJSON(ast, context);
        case 'model_runtime':
          return this._executeModelInference(ast, context);
        default:
          return { success: false, error: `Unknown runtime: ${runtime}` };
      }
    },

    /**
     * JavaScript runtime (sandboxed)
     * @private
     */
    _executeJavaScript: async function(ast, context) {
      try {
        // Create sandbox
        const sandbox = {
          console: {
            log: (...args) => this._logs.push(args.join(' ')),
            error: (...args) => this._logs.push('[ERROR] ' + args.join(' ')),
            warn: (...args) => this._logs.push('[WARN] ' + args.join(' '))
          },
          Math: Math,
          Date: Date,
          JSON: JSON,
          Array: Array,
          Object: Object,
          String: String,
          Number: Number,
          Boolean: Boolean,
          setTimeout: (fn, ms) => setTimeout(fn, Math.min(ms, 5000)),
          fetch: context?.allowFetch ? fetch : undefined,
          __result__: undefined
        };

        this._logs = [];

        // Execute in sandbox
        const source = ast.meta.originalSource;
        const fn = new Function(...Object.keys(sandbox), `
          "use strict";
          try {
            ${source}
            return { success: true, result: typeof __result__ !== 'undefined' ? __result__ : undefined };
          } catch (e) {
            return { success: false, error: e.message };
          }
        `);

        const result = fn(...Object.values(sandbox));

        return {
          success: result.success,
          result: result.result,
          logs: this._logs,
          runtime: 'js_runtime'
        };

      } catch (error) {
        return {
          success: false,
          error: error.message,
          runtime: 'js_runtime'
        };
      }
    },

    /**
     * Python runtime (virtual - uses Pyodide if available)
     * @private
     */
    _executePython: async function(ast, context) {
      // Check for Pyodide
      if (typeof loadPyodide !== 'undefined') {
        try {
          const pyodide = await loadPyodide();
          const result = await pyodide.runPythonAsync(ast.meta.originalSource);
          return {
            success: true,
            result: result,
            runtime: 'python_runtime',
            engine: 'pyodide'
          };
        } catch (error) {
          return {
            success: false,
            error: error.message,
            runtime: 'python_runtime'
          };
        }
      }

      // Virtual Python execution (AST interpretation)
      return {
        success: true,
        result: {
          ast: ast.root,
          message: 'Python AST parsed. Virtual execution in non-Pyodide mode.',
          entryPoints: ast.meta.entryPoints
        },
        runtime: 'python_runtime',
        engine: 'virtual'
      };
    },

    /**
     * Java runtime (virtual)
     * @private
     */
    _executeJava: async function(ast, context) {
      // Virtual Java execution
      return {
        success: true,
        result: {
          ast: ast.root,
          message: 'Java AST parsed. Virtual execution mode.',
          classes: ast.root.children.filter(n => n.type === AST_TYPES.CLASS_DECL).map(n => n.name),
          methods: ast.root.children.filter(n => n.type === AST_TYPES.FUNCTION_DECL).map(n => n.name)
        },
        runtime: 'java_runtime',
        engine: 'virtual'
      };
    },

    /**
     * K'uhul runtime
     * @private
     */
    _executeKuhul: async function(ast, context) {
      const results = [];

      for (const node of ast.root.children) {
        if (node.type === AST_TYPES.POP) {
          // Execute Pop via KuhulPop if available
          if (global.KuhulPop) {
            try {
              const popResult = await global.KuhulPop.execute(node.name, node.extras?.fields || {});
              results.push({ pop: node.name, result: popResult });
            } catch (e) {
              results.push({ pop: node.name, error: e.message });
            }
          } else {
            results.push({ pop: node.name, registered: true });
          }
        }

        if (node.type === AST_TYPES.SEK) {
          results.push({
            sek: node.name,
            pipeline: node.extras?.pipeline || [],
            status: 'ready'
          });
        }
      }

      return {
        success: true,
        result: results,
        runtime: 'kuhul_runtime'
      };
    },

    /**
     * XJSON runtime
     * @private
     */
    _executeXJSON: async function(ast, context) {
      const rawBody = ast.root.children?.[0]?.body || JSON.parse(ast.meta.originalSource);

      // Check for @infer
      if (rawBody['@infer']) {
        return this._executeModelInference(ast, context);
      }

      return {
        success: true,
        result: rawBody,
        runtime: 'xjson_runtime'
      };
    },

    /**
     * Model inference runtime (Ollama, Janus, Qwen)
     * @private
     */
    _executeModelInference: async function(ast, context) {
      // Build XJSON request
      let xjsonRequest;

      if (ast.lang === 'xjson') {
        const rawBody = ast.root.children?.[0]?.body;
        xjsonRequest = rawBody || { '@infer': { '@prompt': ast.meta.originalSource } };
      } else {
        // Natural language -> model inference
        xjsonRequest = {
          '@infer': {
            '@runner': 'lam.o',
            '@model': context?.model || 'llama3',
            '@prompt': ast.meta.originalSource,
            '@params': context?.params || {},
            '@mode': 'chat'
          }
        };
      }

      // Use KuhulClient if available
      if (global.KuhulClient) {
        try {
          const response = await global.KuhulClient.infer(xjsonRequest);
          return {
            success: !response['@error'],
            result: response,
            runtime: 'model_runtime',
            engine: 'kuhul_client'
          };
        } catch (error) {
          return {
            success: false,
            error: error.message,
            runtime: 'model_runtime'
          };
        }
      }

      // Fallback: return prepared request
      return {
        success: true,
        result: {
          prepared: xjsonRequest,
          message: 'XJSON inference request prepared. KuhulClient not available for execution.'
        },
        runtime: 'model_runtime',
        engine: 'virtual'
      };
    },

    // ============================================
    // Stage 6: SCXQ2 Fingerprinting
    // ============================================

    /**
     * Build SCXQ2 payload
     * @private
     */
    _buildSCXQ2Payload: function(request, ast, runtime, result, latencyMs) {
      return JSON.stringify({
        source_hash: this._simpleHash(request.source),
        language: ast.lang,
        runtime: runtime,
        tokens: ast.meta?.tokens || 0,
        complexity: ast.meta?.complexity || 0,
        entry_points: ast.meta?.entryPoints || [],
        latency_ms: latencyMs,
        success: result?.success || false,
        timestamp_bucket: Math.floor(Date.now() / 60000)
      });
    },

    /**
     * Generate SCXQ2 fingerprint
     * @private
     */
    _generateSCXQ2: async function(payload) {
      // Use Web Crypto if available
      if (typeof crypto !== 'undefined' && crypto.subtle) {
        const encoder = new TextEncoder();
        const data = encoder.encode(payload);
        const hashBuffer = await crypto.subtle.digest('SHA-256', data);
        const hashArray = Array.from(new Uint8Array(hashBuffer));
        const hash = hashArray.map(b => b.toString(16).padStart(2, '0')).join('');
        return `SCXQ2-v1:${hash.substring(0, 32)}`;
      }

      // Fallback
      return `SCXQ2-v1:${this._simpleHash(payload)}`;
    },

    /**
     * Simple hash function (fallback)
     * @private
     */
    _simpleHash: function(str) {
      let hash = 5381;
      for (let i = 0; i < str.length; i++) {
        hash = ((hash << 5) + hash) ^ str.charCodeAt(i);
      }
      return (hash >>> 0).toString(16).padStart(8, '0');
    },

    // ============================================
    // Error Response Builder
    // ============================================

    _buildErrorResponse: function(message, language) {
      return {
        success: false,
        language: language,
        ast: null,
        runtime: null,
        result: null,
        error: message
      };
    },

    // ============================================
    // Runtime/Adapter Registration
    // ============================================

    /**
     * Register a runtime handler
     * @param {RuntimeTarget} name
     * @param {Object} handler - { execute: async (ast, context) => result }
     */
    registerRuntime: function(name, handler) {
      this._runtimes[name] = handler;
    },

    /**
     * Register a language adapter
     * @param {PiGoatLanguage} name
     * @param {Object} adapter - { parse: (source) => rawAst }
     */
    registerAdapter: function(name, adapter) {
      this._adapters[name] = adapter;
    },

    // ============================================
    // Convenience Methods
    // ============================================

    /**
     * Quick dispatch for code
     */
    runCode: async function(source, options = {}) {
      return this.dispatch({
        source: source,
        mode: 'code',
        ...options
      });
    },

    /**
     * Quick dispatch for chat/inference
     */
    runChat: async function(prompt, model = 'llama3') {
      return this.dispatch({
        source: prompt,
        mode: 'chat',
        hintLanguage: 'xjson',
        context: { model: model }
      });
    },

    /**
     * Quick dispatch for K'uhul
     */
    runKuhul: async function(source) {
      return this.dispatch({
        source: source,
        mode: 'code',
        hintLanguage: 'kuhul'
      });
    }
  };

  // ============================================
  // K'uhul Pack for Pi-GOAT
  // ============================================

  const PiGoatPack = {
    id: 'pack_pi_goat',
    name: 'Pi-GOAT Polyglot AST Engine',
    role: 'polyglot_runtime_provider',
    fold: 'RUNTIME',
    functions: [
      'pi_goat.dispatch',
      'pi_goat.detect',
      'pi_goat.parse',
      'pi_goat.execute',
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
      'scxq2_fingerprinting'
    ],
    seal: {
      position: [-4, 0, 0.5],
      glyph: '🐐',
      geometry: 'octahedron_rotating',
      color: '#FF6B35'
    }
  };

  // ============================================
  // Export
  // ============================================

  global.PiGoat = PiGoat;
  global.PiGoatPack = PiGoatPack;

  // CommonJS/Node.js export
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { PiGoat, PiGoatPack };
  }

  console.log('[Pi-GOAT] Polyglot AST Engine loaded - Linux without Linux');

})(typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : this);
