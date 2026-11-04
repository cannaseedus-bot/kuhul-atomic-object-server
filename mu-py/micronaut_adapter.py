#!/usr/bin/env python3
"""
Micronaut GGUF Adapter Loader - Python Implementation

Provides loading, validation, and routing for Micronaut MoE adapter configurations.
Compatible with GGUF model sidecar adapters.

Usage:
    from micronaut_adapter import AdapterLoader, Router
    
    # Load adapter
    config = AdapterLoader.load("micronaut_demo.bson")
    
    # Create router
    router = Router(config)
    
    # Select experts for input
    experts = router.select_experts("Write a Python function to sort a list")
    print(experts)  # [('exp-1', 0.45), ('exp-0', 0.23), ...]
"""

import struct
import json
import argparse
import hashlib
import gzip
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Tuple, Any
from datetime import datetime
import re


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Skill:
    """High-level skill definition mapping intents to actions"""
    id: str
    enabled: bool
    name: str
    trigger: str
    action: str
    priority: float = 0.5


@dataclass
class Expert:
    """Expert configuration for MoE routing"""
    id: str
    name: str
    domain: str
    weights_ref: str
    trainable: bool
    routing_bias: float = 0.0
    layer_start: Optional[int] = None
    layer_end: Optional[int] = None


@dataclass
class Agent:
    """Agent persona and configuration"""
    id: str
    name: str
    persona: str
    system_prompt: str
    interaction_count: int = 0
    temperature: float = 0.7
    learned_biases: Dict[str, float] = field(default_factory=dict)
    max_tokens: int = 2048
    last_modified: Optional[datetime] = None


@dataclass
class Memory:
    """Persistent memory configuration"""
    last_topic: Optional[str] = None
    preferred_language: Optional[str] = None
    persist_learning: bool = True
    name: Optional[str] = None
    max_memory_mb: int = 512
    description: Optional[str] = None


@dataclass
class ModelConfig:
    """Base GGUF model configuration"""
    id: str
    num_layers: int
    path: str
    num_experts: int
    vocab_size: Optional[int] = None
    hash: Optional[str] = None
    hidden_size: Optional[int] = None
    gpu_enabled: bool = True
    gpu_backend: str = "cuda"
    top_k_experts: int = 4
    allow_self_modify: bool = False
    state_file: Optional[str] = None


@dataclass
class AdapterConfig:
    """Complete adapter configuration"""
    version: str
    id: str
    experts: List[Expert]
    agent: Agent
    model: ModelConfig
    skills: List[Skill] = field(default_factory=list)
    memory: Optional[Memory] = None


# =============================================================================
# BSON Parser (Minimal Implementation)
# =============================================================================

class BSONType:
    """BSON type constants"""
    DOUBLE = 0x01
    STRING = 0x02
    DOCUMENT = 0x03
    ARRAY = 0x04
    BOOL = 0x08
    INT32 = 0x10
    INT64 = 0x12
    END = 0x00


class BSONParser:
    """
    Minimal BSON parser for Micronaut adapter files
    
    Note: For production use, consider using:
    - pymongo.bson (pip install pymongo)
    - bson (pip install bson)
    """
    
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0
    
    def read_cstring(self) -> str:
        """Read null-terminated string"""
        start = self.pos
        while self.pos < len(self.data) and self.data[self.pos] != 0:
            self.pos += 1
        result = self.data[start:self.pos].decode('utf-8')
        self.pos += 1  # Skip null terminator
        return result
    
    def read_int32(self) -> int:
        """Read little-endian int32"""
        value = struct.unpack_from('<i', self.data, self.pos)[0]
        self.pos += 4
        return value
    
    def read_int64(self) -> int:
        """Read little-endian int64"""
        value = struct.unpack_from('<q', self.data, self.pos)[0]
        self.pos += 8
        return value
    
    def read_double(self) -> float:
        """Read little-endian double"""
        value = struct.unpack_from('<d', self.data, self.pos)[0]
        self.pos += 8
        return value
    
    def read_bool(self) -> bool:
        """Read boolean"""
        value = self.data[self.pos] != 0
        self.pos += 1
        return value
    
    def read_string(self) -> str:
        """Read length-prefixed string"""
        length = self.read_int32()
        value = self.data[self.pos:self.pos + length - 1].decode('utf-8')
        self.pos += length
        return value
    
    def skip_document(self):
        """Skip entire document"""
        doc_length = self.read_int32()
        self.pos += doc_length - 4
    
    def parse_value(self, bson_type: int) -> Any:
        """Parse BSON value by type"""
        if bson_type == BSONType.STRING:
            return self.read_string()
        elif bson_type == BSONType.INT32:
            return self.read_int32()
        elif bson_type == BSONType.INT64:
            return self.read_int64()
        elif bson_type == BSONType.DOUBLE:
            return self.read_double()
        elif bson_type == BSONType.BOOL:
            return self.read_bool()
        elif bson_type == BSONType.DOCUMENT:
            self.skip_document()
            return None  # Simplified
        elif bson_type == BSONType.ARRAY:
            self.skip_document()
            return None  # Simplified
        else:
            raise ValueError(f"Unknown BSON type: {bson_type}")
    
    def parse_document(self) -> Dict[str, Any]:
        """Parse BSON document"""
        doc_length = self.read_int32()
        doc_end = self.pos + doc_length - 5  # -4 for length, -1 for END
        
        result = {}
        while self.pos < doc_end:
            bson_type = self.data[self.pos]
            self.pos += 1
            
            if bson_type == BSONType.END:
                break
            
            key = self.read_cstring()
            value = self.parse_value(bson_type)
            result[key] = value
        
        # Skip END byte
        if self.data[self.pos] == BSONType.END:
            self.pos += 1
        
        return result


# =============================================================================
# Adapter Loader
# =============================================================================

class AdapterLoader:
    """Loads and validates Micronaut adapter configurations"""
    
    @staticmethod
    def load(path: str) -> AdapterConfig:
        """
        Load adapter from file (JSON or BSON)
        
        Args:
            path: Path to .json or .bson file
            
        Returns:
            AdapterConfig object
            
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If parsing fails
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Adapter file not found: {path}")
        
        # Auto-detect format by extension
        if path.suffix == '.json':
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            return AdapterLoader._from_dict(raw)
        elif path.suffix == '.bson':
            with open(path, 'rb') as f:
                data = f.read()
            return AdapterLoader.from_bytes(data)
        else:
            raise ValueError(f"Unsupported file format: {path.suffix}. Use .json or .bson")
    
    @staticmethod
    def from_bytes(data: bytes) -> AdapterConfig:
        """
        Load adapter from bytes
        
        Args:
            data: BSON data bytes
            
        Returns:
            AdapterConfig object
        """
        try:
            from bson import BSON
            raw = BSON(data).decode()
            return AdapterLoader._from_dict(raw)
        except Exception as e:
            raise ValueError(f"Failed to parse BSON: {e}")
    
    @staticmethod
    def _from_dict(raw: Dict[str, Any]) -> AdapterConfig:
        """Convert raw dict to AdapterConfig"""
        # Parse skills
        skills = []
        if 'skills' in raw:
            for skill_data in raw['skills'].values() if isinstance(raw['skills'], dict) else raw['skills']:
                skills.append(Skill(
                    id=skill_data.get('id', ''),
                    enabled=skill_data.get('enabled', False),
                    name=skill_data.get('name', ''),
                    trigger=skill_data.get('trigger', ''),
                    action=skill_data.get('action', ''),
                    priority=skill_data.get('priority', 0.5)
                ))
        
        # Parse experts
        experts = []
        if 'experts' in raw:
            for exp_data in raw['experts'].values() if isinstance(raw['experts'], dict) else raw['experts']:
                experts.append(Expert(
                    id=exp_data.get('id', ''),
                    name=exp_data.get('name', ''),
                    domain=exp_data.get('domain', ''),
                    weights_ref=exp_data.get('weights_ref', ''),
                    trainable=exp_data.get('trainable', False),
                    routing_bias=exp_data.get('routing_bias', 0.0),
                    layer_start=exp_data.get('layer_start'),
                    layer_end=exp_data.get('layer_end')
                ))
        
        # Parse agent
        agent_data = raw.get('agent', {})
        agent = Agent(
            id=agent_data.get('id', ''),
            name=agent_data.get('name', ''),
            persona=agent_data.get('persona', ''),
            system_prompt=agent_data.get('system_prompt', ''),
            interaction_count=agent_data.get('interaction_count', 0),
            temperature=agent_data.get('temperature', 0.7),
            learned_biases=agent_data.get('learned_biases', {}),
            max_tokens=agent_data.get('max_tokens', 2048),
            last_modified=datetime.fromisoformat(agent_data['last_modified']) if agent_data.get('last_modified') else None
        )
        
        # Parse memory
        memory = None
        if 'memory' in raw and raw['memory']:
            mem_data = raw['memory']
            memory = Memory(
                last_topic=mem_data.get('last_topic'),
                preferred_language=mem_data.get('preferred_language'),
                persist_learning=mem_data.get('persist_learning', True),
                name=mem_data.get('name'),
                max_memory_mb=mem_data.get('max_memory_mb', 512),
                description=mem_data.get('description')
            )
        
        # Parse model
        model_data = raw.get('model', {})
        model = ModelConfig(
            id=model_data.get('id', ''),
            num_layers=model_data.get('num_layers', 0),
            path=model_data.get('path', ''),
            num_experts=model_data.get('num_experts', 0),
            vocab_size=model_data.get('vocab_size'),
            hash=model_data.get('hash'),
            hidden_size=model_data.get('hidden_size'),
            gpu_enabled=model_data.get('gpu_enabled', True),
            gpu_backend=model_data.get('gpu_backend', 'cuda'),
            top_k_experts=model_data.get('top_k_experts', 4),
            allow_self_modify=model_data.get('allow_self_modify', False),
            state_file=model_data.get('state_file')
        )
        
        return AdapterConfig(
            version=raw.get('version', '1.0'),
            id=raw.get('id', ''),
            skills=skills,
            experts=experts,
            agent=agent,
            memory=memory,
            model=model
        )
    
    @staticmethod
    def validate(config: AdapterConfig) -> Tuple[bool, Optional[str]]:
        """
        Validate adapter configuration
        
        Returns:
            (is_valid, error_message)
        """
        if not config.experts:
            return False, "Must have at least one expert"
        
        if config.model.num_experts <= 0:
            return False, "Invalid num_experts"
        
        if len(config.experts) != config.model.num_experts:
            return False, f"Expert count mismatch: {len(config.experts)} vs {config.model.num_experts}"
        
        # Validate expert IDs are unique
        expert_ids = [e.id for e in config.experts]
        if len(expert_ids) != len(set(expert_ids)):
            return False, "Duplicate expert IDs"
        
        # Validate learned biases reference valid experts
        for expert_id in config.agent.learned_biases:
            if expert_id not in expert_ids:
                return False, f"Learned bias references unknown expert: {expert_id}"
        
        return True, None
    
    @staticmethod
    def save(config: AdapterConfig, path: str) -> None:
        """
        Save adapter configuration to JSON (for editing)
        
        Note: BSON saving requires external library
        
        Args:
            config: Configuration to save
            path: Output path (.json or .bson)
        """
        path = Path(path)
        
        if path.suffix == '.json':
            # Save as JSON for easy editing
            data = asdict(config)
            with open(path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        else:
            raise ValueError("BSON saving requires pymongo.bson library")


# =============================================================================
# Router - Expert Selection Logic
# =============================================================================

class Router:
    """
    Routes input tokens to appropriate experts based on biases and domain matching
    
    Implements the Micronaut routing algorithm:
    1. Compute base score from learned biases
    2. Add domain matching bonus
    3. Apply softmax normalization
    4. Select top-K experts
    """
    
    # Domain-specific keywords for matching
    DOMAIN_KEYWORDS = {
        'python_code': ['python', 'def ', 'import ', 'pip', 'django', 'flask', 'numpy'],
        'cpp_code': ['C++', '#include', 'std::', 'template', 'namespace', 'vector<', 'cout'],
        'js_code': ['JavaScript', 'function', 'const ', 'let ', '=>', 'console.', 'npm'],
        'mathematics': ['equation', 'formula', 'calculate', 'integral', 'derivative', 'theorem'],
        'debugging': ['error', 'bug', 'crash', 'exception', 'stack trace', 'debug'],
        'general': ['help', 'explain', 'what', 'how'],
        'writing': ['write', 'article', 'email', 'document', 'text'],
        'reasoning': ['why', 'because', 'therefore', 'logic', 'reason']
    }
    
    def __init__(self, config: AdapterConfig):
        """
        Initialize router with adapter configuration
        
        Args:
            config: Loaded adapter configuration
        """
        self.config = config
        self.biases = {}
        
        # Initialize biases from expert config
        for expert in config.experts:
            self.biases[expert.id] = expert.routing_bias
        
        # Override with learned biases (user preferences)
        for expert_id, bias in config.agent.learned_biases.items():
            self.biases[expert_id] = bias
    
    def select_experts(
        self, 
        input_text: str, 
        domain_hint: Optional[str] = None,
        k: Optional[int] = None
    ) -> List[Tuple[str, float]]:
        """
        Select top-K experts for given input
        
        Args:
            input_text: User input text
            domain_hint: Optional domain hint (e.g., "python_code")
            k: Number of experts to select (defaults to model.top_k_experts)
            
        Returns:
            List of (expert_id, weight) pairs, sorted by weight descending
        """
        k = k or self.config.model.top_k_experts
        
        # Compute logits for each expert
        logits = []
        expert_ids = []
        
        for expert in self.config.experts:
            # Base score from learned bias
            score = self.biases.get(expert.id, 0.0)
            
            # Add domain matching bonus
            if domain_hint and expert.domain == domain_hint:
                score += 0.5  # Strong bonus for explicit domain match
            else:
                score += self._compute_domain_score(expert, input_text)
            
            logits.append(score)
            expert_ids.append(expert.id)
        
        # Softmax normalization
        probs = self._softmax(logits)
        
        # Select top-K
        scored = list(zip(expert_ids, probs))
        scored.sort(key=lambda x: x[1], reverse=True)
        
        return scored[:k]
    
    def _compute_domain_score(self, expert: Expert, input_text: str) -> float:
        """
        Compute domain match score using keyword matching
        
        Args:
            expert: Expert configuration
            input_text: User input
            
        Returns:
            Domain match score in [0, 0.5]
        """
        keywords = self.DOMAIN_KEYWORDS.get(expert.domain, [])
        if not keywords:
            return 0.0
        
        score = 0.0
        input_lower = input_text.lower()
        
        for keyword in keywords:
            if keyword.lower() in input_lower:
                score += 0.1
        
        return min(score, 0.5)  # Cap domain bonus
    
    def _softmax(self, logits: List[float]) -> List[float]:
        """
        Compute softmax probabilities
        
        Args:
            logits: Raw scores
            
        Returns:
            Normalized probabilities
        """
        import math
        
        max_logit = max(logits)
        exp_scores = [math.exp(l - max_logit) for l in logits]
        sum_exp = sum(exp_scores)
        
        return [e / sum_exp for e in exp_scores]
    
    def update_bias(self, expert_id: str, reward: float, learning_rate: float = 0.01) -> None:
        """
        Update learned bias for an expert based on feedback
        
        Implements simple reinforcement learning update:
            bias_new = bias_old + lr * reward
        
        Args:
            expert_id: Expert to update
            reward: Positive/negative reward signal (-1 to 1)
            learning_rate: Learning rate (default 0.01)
        """
        if expert_id not in self.biases:
            raise ValueError(f"Unknown expert: {expert_id}")
        
        # Update bias
        self.biases[expert_id] += learning_rate * reward
        
        # Clamp to [-1, 1]
        self.biases[expert_id] = max(-1.0, min(1.0, self.biases[expert_id]))
        
        # Persist to config
        self.config.agent.learned_biases[expert_id] = self.biases[expert_id]
    
    def get_expert_by_id(self, expert_id: str) -> Optional[Expert]:
        """Get expert configuration by ID"""
        for expert in self.config.experts:
            if expert.id == expert_id:
                return expert
        return None
    
    def save_state(self, path: str) -> None:
        """
        Save learned state to file
        
        Args:
            path: Output path for state file
        """
        state = {
            'learned_biases': self.config.agent.learned_biases,
            'interaction_count': self.config.agent.interaction_count,
            'last_modified': datetime.now().isoformat()
        }
        
        with open(path, 'w') as f:
            json.dump(state, f, indent=2)
    
    def load_state(self, path: str) -> None:
        """
        Load learned state from file
        
        Args:
            path: State file path
        """
        with open(path, 'r') as f:
            state = json.load(f)
        
        self.config.agent.learned_biases.update(state.get('learned_biases', {}))
        self.config.agent.interaction_count = state.get('interaction_count', 0)
        
        # Update internal biases
        for expert_id, bias in self.config.agent.learned_biases.items():
            self.biases[expert_id] = bias


# =============================================================================
# Micronaut BSON bundle execution
# =============================================================================

def load_micronaut_bundle(path: Path) -> dict:
    """Decode and verify a Micronaut source bundle; this does not run its entries."""
    from bson import BSON

    data = path.read_bytes()
    if len(data) < 5 or len(data) > 64 * 1024 * 1024:
        raise ValueError("bundle size is outside the supported 5-byte to 64-MiB range")
    if int.from_bytes(data[:4], "little", signed=True) != len(data) or data[-1] != 0:
        raise ValueError("BSON length must match the entire file with no trailing bytes")
    try:
        package = BSON(data).decode()
    except Exception as exc:
        raise ValueError(f"invalid BSON document: {exc}") from exc
    if package.get("format") != "kuhul.micronaut-bundle" or package.get("version") != 1:
        raise ValueError("unsupported Micronaut BSON bundle format/version")
    if package.get("status") != "DATA_ONLY" or package.get("executionAdmission") != "explicit_host_xcfe":
        raise ValueError("bundle is not marked DATA_ONLY with explicit host admission")
    entries = package.get("entries")
    if not isinstance(entries, list) or package.get("entryCount") != len(entries):
        raise ValueError("bundle entryCount mismatch")

    seen = set()
    inventory = []
    for entry in entries:
        name = entry.get("path") if isinstance(entry, dict) else None
        content = entry.get("content") if isinstance(entry, dict) else None
        if not isinstance(name, str) or name in seen:
            raise ValueError(f"invalid or duplicate bundle path: {name!r}")
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or "\\" in name:
            raise ValueError(f"bundle path is not a safe relative path: {name}")
        seen.add(name)
        if not isinstance(content, (bytes, bytearray, memoryview)):
            raise ValueError(f"bundle content is not BSON Binary: {name}")
        payload = bytes(content)
        encoding = entry.get("contentEncoding")
        if encoding == "gzip":
            try:
                payload = gzip.decompress(payload)
            except OSError as exc:
                raise ValueError(f"bundle entry gzip payload is invalid: {name}") from exc
        elif encoding is not None:
            raise ValueError(f"unsupported bundle content encoding {encoding!r}: {name}")
        digest = hashlib.sha256(payload).hexdigest()
        if len(payload) != entry.get("bytes") or digest != entry.get("sha256"):
            raise ValueError(f"bundle entry hash mismatch: {name}")
        inventory.append({"path": name, "bytes": len(payload), "sha256": digest})
    canonical = json.dumps(inventory, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != package.get("bundleSha256"):
        raise ValueError("bundle inventory hash mismatch")
    return package


def run_embedded_program(bundle_path: Path, program_path: str, arguments: list[str], timeout: int = 600) -> int:
    """Stage one source-authorized mu-py entry and run it with the host interpreter."""
    package = load_micronaut_bundle(bundle_path)
    entries = {entry["path"]: entry for entry in package["entries"]}
    normalized = program_path.replace("\\", "/")
    entry = entries.get(normalized)
    if entry is None:
        raise ValueError(f"program is not present in the bundle: {normalized}")
    if not normalized.startswith("mu-py/") or not normalized.endswith(".py"):
        raise ValueError("only Python microprograms under mu-py/ may be launched by this adapter")
    if entry.get("entryType") != "micro_program" or entry.get("entryStatus") != "source":
        raise ValueError("entry is not an admitted source microprogram; candidate entries cannot run")

    with tempfile.TemporaryDirectory(prefix="micronaut-bson-") as temporary:
        root = Path(temporary).resolve()
        for item in package["entries"]:
            relative = PurePosixPath(item["path"])
            target = root.joinpath(*relative.parts).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"bundle entry escapes staging directory: {item['path']}")
            target.parent.mkdir(parents=True, exist_ok=True)
            content = bytes(item["content"])
            if item.get("contentEncoding") == "gzip":
                content = gzip.decompress(content)
            target.write_bytes(content)

        staged_script = root.joinpath(*PurePosixPath(normalized).parts)
        environment = os.environ.copy()
        gguf_path = str(root / "gguf-py")
        environment["PYTHONPATH"] = os.pathsep.join(filter(None, [gguf_path, environment.get("PYTHONPATH", "")]))
        print(f"Launching bundled program: {normalized}")
        print("Execution is performed by the host Python process; temporary staging is not an OS sandbox.")
        try:
            result = subprocess.run(
                [sys.executable, str(staged_script), *arguments],
                cwd=root,
                env=environment,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ValueError(f"embedded program exceeded timeout ({timeout}s)") from exc
        return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Load Micronaut adapter metadata or run an explicitly selected bundled microprogram.")
    parser.add_argument("--micronaut.bson", "--micronaut-bson", dest="bundle", type=Path, help="Micronaut BSON source bundle")
    parser.add_argument("--list-programs", action="store_true", help="list bundled Python microprograms under mu-py/")
    parser.add_argument("--run-script", metavar="BUNDLE_PATH", help="stage and invoke a bundled mu-py Python program")
    parser.add_argument("--execute", action="store_true", help="explicitly authorize launching the selected source program")
    parser.add_argument("--timeout", type=int, default=600, help="maximum program runtime in seconds")
    parser.add_argument("script_args", nargs=argparse.REMAINDER, help="arguments passed to the selected script (put after --)")
    args = parser.parse_args()
    if args.bundle is None:
        parser.error("--micronaut.bson is required for bundle operations")
    if args.timeout < 1 or args.timeout > 3600:
        parser.error("--timeout must be between 1 and 3600 seconds")
    try:
        package = load_micronaut_bundle(args.bundle)
        if args.list_programs:
            for entry in package["entries"]:
                if entry.get("entryType") == "micro_program" and entry.get("path", "").startswith("mu-py/"):
                    print(f"{entry['path']}\t{entry['entryStatus']}\t{entry['bytes']} bytes")
            return 0
        if not args.run_script:
            parser.error("choose --list-programs or --run-script BUNDLE_PATH")
        if not args.execute:
            parser.error("script launch requires the explicit --execute flag")
        return run_embedded_program(args.bundle, args.run_script, args.script_args, args.timeout)
    except (OSError, ValueError) as exc:
        print(f"Micronaut adapter error: {exc}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
