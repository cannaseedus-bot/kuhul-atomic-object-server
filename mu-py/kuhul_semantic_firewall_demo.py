#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
K'UHUL Semantic Firewall - Practical Implementation
Demonstrates semantic validation, safe error handling, and fallback strategies
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from enum import Enum
import json

# ============================================================================
# SEMANTIC REGISTRY
# ============================================================================

KUHUL_REGISTRY = {
    "@meta": {
        "version": "1.0",
        "hash": "sha256:kuhul_registry_canonical_v1",
        "generated": "2025-07-11T00:00:00Z"
    },
    
    "phases": {
        "Pop": {
            "id": 1,
            "allowed_predecessors": ["Xul"],
            "allowed_successors": ["Wo"]
        },
        "Wo": {
            "id": 2,
            "allowed_predecessors": ["Pop"],
            "allowed_successors": ["Yax"]
        },
        "Yax": {
            "id": 3,
            "allowed_predecessors": ["Wo"],
            "allowed_successors": ["Sek"]
        },
        "Sek": {
            "id": 4,
            "allowed_predecessors": ["Yax"],
            "allowed_successors": ["Xul"]
        },
        "Xul": {
            "id": 5,
            "allowed_predecessors": ["Sek"],
            "allowed_successors": ["Pop"]
        }
    },
    
    "opcodes": {
        "bind": {
            "id": 16,
            "allowed_phases": ["Wo"],
            "lowering": "runtime.bind",
            "backend_required": False
        },
        "load": {
            "id": 17,
            "allowed_phases": ["Yax"],
            "lowering": "ggml_view_tensor",
            "backend_required": True
        },
        "matmul": {
            "id": 32,
            "allowed_phases": ["Sek"],
            "lowering": "ggml_mul_mat",
            "backend_required": True
        },
        "rope": {
            "id": 33,
            "allowed_phases": ["Sek"],
            "lowering": "ggml_rope",
            "backend_required": True
        },
        "softmax": {
            "id": 34,
            "allowed_phases": ["Sek"],
            "lowering": "ggml_soft_max",
            "backend_required": True
        },
        "scale": {
            "id": 35,
            "allowed_phases": ["Sek"],
            "lowering": "ggml_scale",
            "backend_required": True
        },
        "mask": {
            "id": 36,
            "allowed_phases": ["Sek"],
            "lowering": "ggml_mul",
            "backend_required": True
        }
    },
    
    "folds": {
        "transformer.block.*.attention.q": "query projection",
        "transformer.block.*.attention.k": "key projection",
        "transformer.block.*.attention.v": "value projection",
        "transformer.block.*.attention.scores": "attention scores"
    },
    
    "@capabilities": {
        "runtime": "llama.cpp",
        "backend": "D3D11",
        "dtypes": ["F32", "F16", "Q4_0"],
        "ops": ["matmul", "rope", "softmax", "scale", "mask", "add", "mul"],
        "phases": ["Pop", "Wo", "Yax", "Sek", "Xul"]
    }
}

# ============================================================================
# ERROR TYPES
# ============================================================================

@dataclass
class ValidationError:
    code: str
    message: str
    recoverable: bool = False
    fallbacks: List[str] = None
    
    def to_dict(self) -> Dict:
        return {
            "@error": self.code,
            "message": self.message,
            "recoverable": self.recoverable,
            "fallbacks": self.fallbacks or []
        }

# ============================================================================
# SEMANTIC VALIDATOR
# ============================================================================

class SemanticValidator:
    """Validates K'UHUL documents against registry."""
    
    def __init__(self, registry: Dict):
        self.registry = registry
        self.errors: List[ValidationError] = []
        self.warnings: List[str] = []
    
    def validate(self, doc: Dict) -> bool:
        """Execute full validation pipeline."""
        self.errors.clear()
        self.warnings.clear()
        
        print("\n  🔍 VALIDATION PIPELINE\n")
        
        # Step 1: Schema
        print("  1️⃣ Schema validation...")
        if not self._check_schema(doc):
            return False
        print("     ✓ Schema valid\n")
        
        # Step 2: Registry hash
        print("  2️⃣ Registry hash check...")
        self._check_registry_hash(doc)
        print("     ✓ Registry compatible\n")
        
        # Step 3: Vocabulary
        print("  3️⃣ Vocabulary validation...")
        if not self._check_vocabulary(doc):
            return False
        print("     ✓ All tokens recognized\n")
        
        # Step 4: Phase sequence
        print("  4️⃣ Phase sequence validation...")
        if not self._check_phase_sequence(doc):
            return False
        print("     ✓ Phase transitions legal\n")
        
        # Step 5: Opcodes
        print("  5️⃣ Opcode validation...")
        if not self._check_opcodes(doc):
            return False
        print("     ✓ All opcodes valid\n")
        
        # Step 6: Fold paths
        print("  6️⃣ Fold path validation...")
        if not self._check_fold_paths(doc):
            return False
        print("     ✓ All fold paths recognized\n")
        
        # Step 7: Backend capability
        print("  7️⃣ Backend capability check...")
        if not self._check_backend_capability(doc):
            return False
        print("     ✓ Backend supports all ops\n")
        
        return True
    
    def _check_schema(self, doc: Dict) -> bool:
        if "@schema" not in doc:
            self.errors.append(ValidationError(
                "MISSING_SCHEMA",
                "Document missing @schema declaration"
            ))
            return False
        
        if doc["@schema"] != "kxml/1":
            self.errors.append(ValidationError(
                "UNSUPPORTED_SCHEMA",
                f"Schema {doc['@schema']} not supported"
            ))
            return False
        
        return True
    
    def _check_registry_hash(self, doc: Dict):
        doc_hash = doc.get("@registry_hash", "")
        runtime_hash = self.registry["@meta"]["hash"]
        
        if doc_hash and doc_hash != runtime_hash:
            self.warnings.append(
                f"Registry mismatch (document: {doc_hash[:16]}..., "
                f"runtime: {runtime_hash[:16]}...)"
            )
    
    def _check_vocabulary(self, doc: Dict) -> bool:
        # Check phases
        for phase in doc.get("phases", []):
            if phase not in self.registry["phases"]:
                self.errors.append(ValidationError(
                    "UNKNOWN_PHASE",
                    f"Phase '{phase}' not in registry"
                ))
                return False
        
        # Check opcodes
        for instr in doc.get("instructions", []):
            opcode = instr.get("opcode")
            if opcode not in self.registry["opcodes"]:
                self.errors.append(ValidationError(
                    "UNKNOWN_OPCODE",
                    f"Opcode '{opcode}' not in registry",
                    recoverable=True,
                    fallbacks=self._find_fallbacks(opcode)
                ))
                return False
        
        return True
    
    def _check_phase_sequence(self, doc: Dict) -> bool:
        phases = doc.get("phases", [])
        
        for i in range(1, len(phases)):
            prev_phase = phases[i - 1]
            curr_phase = phases[i]
            
            allowed = self.registry["phases"][prev_phase]["allowed_successors"]
            if curr_phase not in allowed:
                self.errors.append(ValidationError(
                    "ILLEGAL_PHASE_TRANSITION",
                    f"Cannot transition {prev_phase} → {curr_phase} "
                    f"(allowed: {allowed})"
                ))
                return False
        
        return True
    
    def _check_opcodes(self, doc: Dict) -> bool:
        for instr in doc.get("instructions", []):
            phase = instr.get("phase")
            opcode = instr.get("opcode")
            
            opcode_def = self.registry["opcodes"].get(opcode)
            if not opcode_def:
                continue  # Already caught in vocabulary check
            
            if phase not in opcode_def["allowed_phases"]:
                self.errors.append(ValidationError(
                    "OPCODE_NOT_ALLOWED_IN_PHASE",
                    f"Opcode '{opcode}' not allowed in phase '{phase}' "
                    f"(allowed: {opcode_def['allowed_phases']})"
                ))
                return False
        
        return True
    
    def _check_fold_paths(self, doc: Dict) -> bool:
        for instr in doc.get("instructions", []):
            args = instr.get("args", {})
            for key, val in args.items():
                if isinstance(val, str) and val.startswith("transformer."):
                    # Check against fold patterns
                    if not self._fold_path_matches(val):
                        self.errors.append(ValidationError(
                            "UNKNOWN_FOLD_PATH",
                            f"Fold path '{val}' not recognized"
                        ))
                        return False
        
        return True
    
    def _check_backend_capability(self, doc: Dict) -> bool:
        caps = self.registry["@capabilities"]
        
        for instr in doc.get("instructions", []):
            opcode = instr.get("opcode")
            opcode_def = self.registry["opcodes"].get(opcode)
            
            if opcode_def and opcode_def["backend_required"]:
                if opcode not in caps["ops"]:
                    self.errors.append(ValidationError(
                        "UNSUPPORTED_OPCODE",
                        f"Backend '{caps['backend']}' does not support '{opcode}'",
                        recoverable=True,
                        fallbacks=self._find_backend_fallbacks(opcode)
                    ))
                    return False
        
        return True
    
    def _fold_path_matches(self, path: str) -> bool:
        for pattern in self.registry["folds"].keys():
            # Simple wildcard matching
            pattern_parts = pattern.split(".")
            path_parts = path.split(".")
            
            if len(pattern_parts) == len(path_parts):
                match = True
                for p, f in zip(pattern_parts, path_parts):
                    if p != "*" and p != f:
                        match = False
                        break
                if match:
                    return True
        return False
    
    def _find_fallbacks(self, opcode: str) -> List[str]:
        """Find similar opcodes as fallbacks."""
        # Simple substring matching
        candidates = [
            op for op in self.registry["opcodes"].keys()
            if opcode[0] in op
        ]
        return candidates[:3]
    
    def _find_backend_fallbacks(self, opcode: str) -> List[str]:
        """Find backend-supported alternatives."""
        caps = self.registry["@capabilities"]
        
        # Examples
        fallback_map = {
            "flash_attention": ["matmul", "softmax", "matmul"],
            "flash_attn_v3": ["matmul", "scale", "mask", "softmax", "matmul"]
        }
        
        return fallback_map.get(opcode, [])
    
    def get_errors(self) -> List[Dict]:
        return [e.to_dict() for e in self.errors]
    
    def get_warnings(self) -> List[str]:
        return self.warnings

# ============================================================================
# SEMANTIC ADAPTER
# ============================================================================

class SemanticAdapter:
    """Adapts validated documents to executable form."""
    
    def __init__(self, registry: Dict):
        self.registry = registry
    
    def adapt(self, validated_doc: Dict) -> Dict:
        """Convert validated document to adapted form."""
        
        adapted = {
            "@adapted": True,
            "@timestamp": "2025-07-11T00:00:00Z",
            "operations": []
        }
        
        print("\n  🔧 ADAPTATION PIPELINE\n")
        
        for instr in validated_doc.get("instructions", []):
            print(f"  Adapting: {instr['opcode']} in {instr['phase']}...")
            
            opcode_def = self.registry["opcodes"][instr["opcode"]]
            lowering = opcode_def["lowering"]
            
            adapted_op = {
                "opcode": instr["opcode"],
                "phase": instr["phase"],
                "lowering": lowering,
                "backend_call": self._resolve_backend_call(lowering),
                "args": instr.get("args", {})
            }
            
            adapted["operations"].append(adapted_op)
            print(f"     ✓ Lowered to: {lowering}\n")
        
        return adapted
    
    def _resolve_backend_call(self, lowering: str) -> str:
        """Resolve lowering string to backend call."""
        # In production, this would actually invoke the backend
        # For demo, we just map to C function names
        
        mapping = {
            "ggml_mul_mat": "ggml_mul_mat(ctx, a, b)",
            "ggml_rope": "ggml_rope(ctx, x, pos)",
            "ggml_soft_max": "ggml_soft_max(ctx, x)",
            "ggml_scale": "ggml_scale(ctx, x, scale)",
            "ggml_mul": "ggml_mul(ctx, a, b)",
            "runtime.bind": "runtime_bind_semantic_node(node, tensor)"
        }
        
        return mapping.get(lowering, lowering)

# ============================================================================
# DEMONSTRATION: SAFE FAILURE MODES
# ============================================================================

def demo_valid_document():
    """Demo: Valid document passes all checks."""
    
    print("\n" + "=" * 70)
    print("✅ VALID DOCUMENT")
    print("=" * 70)
    
    doc = {
        "@schema": "kxml/1",
        "@registry_hash": "sha256:kuhul_registry_canonical_v1",
        "phases": ["Pop", "Wo", "Yax", "Sek", "Xul"],
        "instructions": [
            {"phase": "Wo", "opcode": "bind", "args": {
                "node_ref": "transformer.block.17.attention.q"
            }},
            {"phase": "Sek", "opcode": "rope", "args": {
                "tensor": "transformer.block.17.attention.q"
            }},
            {"phase": "Sek", "opcode": "matmul", "args": {
                "left": "transformer.block.17.attention.q",
                "right": "transformer.block.17.attention.k"
            }},
            {"phase": "Sek", "opcode": "softmax", "args": {
                "input": "transformer.block.17.attention.scores"
            }}
        ]
    }
    
    validator = SemanticValidator(KUHUL_REGISTRY)
    if validator.validate(doc):
        print("\n  ✅ VALIDATION PASSED\n")
        
        adapter = SemanticAdapter(KUHUL_REGISTRY)
        adapted = adapter.adapt(doc)
        
        print("\n  ✅ ADAPTATION COMPLETE\n")
        print("  Adapted operations:")
        for op in adapted["operations"]:
            print(f"    • {op['opcode']} → {op['lowering']}")

def demo_unknown_opcode():
    """Demo: Unknown opcode caught safely."""
    
    print("\n" + "=" * 70)
    print("❌ UNKNOWN OPCODE (CAUGHT SAFELY)")
    print("=" * 70)
    
    doc = {
        "@schema": "kxml/1",
        "phases": ["Pop", "Wo", "Yax", "Sek", "Xul"],
        "instructions": [
            {"phase": "Sek", "opcode": "quantum_attention", "args": {}}
        ]
    }
    
    validator = SemanticValidator(KUHUL_REGISTRY)
    if not validator.validate(doc):
        print("\n  ❌ VALIDATION FAILED\n")
        print("  Errors:")
        for error in validator.get_errors():
            print(f"    • {error['@error']}: {error['message']}")
            if error['fallbacks']:
                print(f"      Fallbacks: {error['fallbacks']}")

def demo_illegal_phase_transition():
    """Demo: Illegal phase transition caught."""
    
    print("\n" + "=" * 70)
    print("❌ ILLEGAL PHASE TRANSITION (CAUGHT SAFELY)")
    print("=" * 70)
    
    doc = {
        "@schema": "kxml/1",
        "phases": ["Pop", "Sek", "Yax"],  # Sek before Yax is illegal
        "instructions": []
    }
    
    validator = SemanticValidator(KUHUL_REGISTRY)
    if not validator.validate(doc):
        print("\n  ❌ VALIDATION FAILED\n")
        print("  Errors:")
        for error in validator.get_errors():
            print(f"    • {error['@error']}: {error['message']}")

def demo_unsupported_backend_op():
    """Demo: Unsupported backend operation caught."""
    
    print("\n" + "=" * 70)
    print("❌ UNSUPPORTED BACKEND OPERATION (CAUGHT SAFELY)")
    print("=" * 70)
    
    doc = {
        "@schema": "kxml/1",
        "phases": ["Pop", "Wo", "Yax", "Sek", "Xul"],
        "instructions": [
            {"phase": "Sek", "opcode": "flash_attention", "args": {}}
        ]
    }
    
    validator = SemanticValidator(KUHUL_REGISTRY)
    if not validator.validate(doc):
        print("\n  ❌ VALIDATION FAILED\n")
        print("  Errors:")
        for error in validator.get_errors():
            print(f"    • {error['@error']}: {error['message']}")
            if error['fallbacks']:
                print(f"      Suggested fallback: {' → '.join(error['fallbacks'])}")

def demo_registry_negotiation():
    """Demo: Capability negotiation."""
    
    print("\n" + "=" * 70)
    print("🤝 CAPABILITY NEGOTIATION")
    print("=" * 70)
    
    caps = KUHUL_REGISTRY["@capabilities"]
    
    print(f"\n  Runtime: {caps['runtime']}")
    print(f"  Backend: {caps['backend']}")
    print(f"  Data types: {caps['dtypes']}")
    print(f"\n  Supported operations in phase Sek:")
    
    for op in caps["ops"]:
        if op in KUHUL_REGISTRY["opcodes"]:
            phases = KUHUL_REGISTRY["opcodes"][op]["allowed_phases"]
            if "Sek" in phases:
                print(f"    ✓ {op}")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n╔════════════════════════════════════════════════════════════════════╗")
    print("║  K'UHUL SEMANTIC FIREWALL - PRACTICAL DEMONSTRATION             ║")
    print("║  Shows safe error handling and registry-based validation        ║")
    print("╚════════════════════════════════════════════════════════════════════╝")
    
    # Run demonstrations
    demo_valid_document()
    demo_unknown_opcode()
    demo_illegal_phase_transition()
    demo_unsupported_backend_op()
    demo_registry_negotiation()
    
    print("\n" + "=" * 70)
    print("✅ ALL DEMONSTRATIONS COMPLETE")
    print("=" * 70)
    print("""
Key Takeaways:

1. Unknown tokens are CLASSIFIED not EXECUTED
   → No crashes, structured error responses

2. Phase transitions are VALIDATED
   → Illegal sequences caught before execution

3. Backend capabilities are NEGOTIATED
   → Model knows what it can emit

4. Errors are RECOVERABLE
   → Fallback strategies suggested

5. Registry is the SOURCE OF TRUTH
   → Semantic meaning comes from registry, not from XML structure alone
""")
