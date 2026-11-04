#!/usr/bin/env python3
"""
Micronaut Adapter Integration for GGUF

Provides tools to:
1. Embed Micronaut adapter metadata in GGUF files
2. Create/modify Micronaut adapter sidecar files
3. Load and validate adapter configurations
4. Route inference requests to appropriate experts

Usage:
    # Add Micronaut metadata to existing GGUF
    python -m gguf.micronaut add-metadata model.gguf --adapter micronaut_demo.bson
    
    # Create new adapter sidecar
    python -m gguf.micronaut create-adapter --config config.json --output adapter.bson
    
    # Validate adapter configuration
    python -m gguf.micronaut validate adapter.bson
    
    # Show routing analysis
    python -m gguf.micronaut analyze adapter.bson "Write Python code"
"""

import argparse
import json
import logging
import sys
import struct
import re
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

# Import gguf-py
import gguf
from gguf import GGUFReader, GGUFWriter

logger = logging.getLogger("micronaut")


# =============================================================================
# Micronaut GGUF Metadata Keys
# =============================================================================

class MicronautKeys:
    """Micronaut-specific GGUF metadata keys"""
    
    # Adapter identification
    ADAPTER_VERSION = "micronaut.adapter_version"
    ADAPTER_ID = "micronaut.id"
    ADAPTER_TYPE = "micronaut.type"  # "moe_adapter"
    
    # Expert configuration
    EXPERT_COUNT = "micronaut.expert_count"
    EXPERT_USED_COUNT = "micronaut.expert_used_count"
    EXPERT_DOMAINS = "micronaut.expert_domains"
    
    # Routing configuration
    ROUTING_MODE = "micronaut.routing_mode"  # "bias_weighted", "domain_only", "hybrid"
    ROUTING_TEMPERATURE = "micronaut.routing_temperature"
    
    # State persistence
    STATE_FILE = "micronaut.state_file"
    STATE_FILE_HASH = "micronaut.state_file_hash"
    
    # GPU configuration
    GPU_BACKEND = "micronaut.gpu_backend"
    GPU_ENABLED = "micronaut.gpu_enabled"
    
    # Learning configuration
    ALLOW_SELF_MODIFY = "micronaut.allow_self_modify"
    PERSIST_LEARNING = "micronaut.persist_learning"
    
    # Skill layer
    SKILL_COUNT = "micronaut.skill_count"
    SKILLS = "micronaut.skills"  # JSON array

    # Declarative programmable-agent payloads. These are custom keys; ordinary
    # GGUF consumers may ignore them and do not execute the referenced program.
    SCHEMA_VERSION = "micronaut.schema_version"
    MANIFEST = "micronaut.manifest"
    MML = "micronaut.mml"
    PROGRAM_REF = "micronaut.program_ref"
    FIELD_REF = "micronaut.field_ref"
    MEMORY_SCHEMA = "micronaut.memory_schema"
    EXECUTION_CONTRACT = "micronaut.xcfe"


def read_micronaut_manifest(gguf_path: Path) -> dict[str, Any]:
    """Read declarative Micronaut metadata from GGUF without activating it.

    ``micronaut.manifest`` and ``micronaut.mml`` are non-standard custom
    metadata keys. The result remains untrusted input for host validation.
    """
    from xml.etree import ElementTree as ET

    reader = GGUFReader(gguf_path, "r")
    raw = None
    for key in (MicronautKeys.MANIFEST, MicronautKeys.MML):
        field = reader.get_field(key)
        if field is not None:
            raw = field.contents()
            break
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("GGUF has no non-empty micronaut.manifest or micronaut.mml string")
    text = raw.strip()
    if text.startswith("{"):
        manifest = json.loads(text)
        if not isinstance(manifest, dict):
            raise ValueError("Micronaut JSON manifest must be an object")
        return manifest
    if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.IGNORECASE):
        raise ValueError("MML DTDs and entities are not accepted")
    element = ET.fromstring(text)
    if element.tag != "micronaut":
        raise ValueError("Micronaut XML metadata must have a <micronaut> root")
    return {"format": "kuhul.mml", "id": element.get("id"), "version": element.get("version"),
            "xml": text, "status": "declarative_unadmitted"}


# =============================================================================
# Adapter Metadata Embedding
# =============================================================================

def embed_adapter_metadata(
    gguf_path: Path,
    adapter_config: dict,
    output_path: Optional[Path] = None,
    dry_run: bool = False
) -> None:
    """
    Embed Micronaut adapter metadata into GGUF file
    
    Args:
        gguf_path: Path to GGUF model file
        adapter_config: Adapter configuration dict
        output_path: Output path (None to overwrite)
        dry_run: Show what would be changed without modifying
    """
    output_path = output_path or gguf_path
    
    logger.info(f"Loading GGUF file: {gguf_path}")
    reader = GGUFReader(gguf_path, 'r')
    
    logger.info(f"Creating new GGUF with Micronaut metadata")
    writer = GGUFWriter(
        path=None if dry_run else str(output_path),
        arch=reader.fields.get('general.architecture', 'unknown'),
        dry_run=dry_run
    )
    
    # Copy all existing metadata
    for field in reader.fields.values():
        key = field.name
        value = field.parts[field.data[0]] if field.data else None
        
        if value is not None:
            try:
                # Add with appropriate type
                if hasattr(value, 'dtype'):
                    if value.dtype == 'uint32':
                        writer.add_uint32(key, int(value))
                    elif value.dtype == 'uint64':
                        writer.add_uint64(key, int(value))
                    elif value.dtype == 'float32':
                        writer.add_float32(key, float(value))
                    elif value.dtype == 'float64':
                        writer.add_float64(key, float(value))
                    elif value.dtype.kind == 'U':
                        writer.add_string(key, str(value))
                    elif value.dtype == 'bool':
                        writer.add_bool(key, bool(value))
                else:
                    writer.add_string(key, str(value))
            except Exception as e:
                logger.warning(f"Skipping field {key}: {e}")
    
    # Add Micronaut-specific metadata
    model_config = adapter_config.get('model', {})
    agent_config = adapter_config.get('agent', {})
    
    writer.add_string(MicronautKeys.ADAPTER_VERSION, adapter_config.get('version', '1.0'))
    writer.add_string(MicronautKeys.ADAPTER_ID, adapter_config.get('id', 'micronaut-default'))
    writer.add_string(MicronautKeys.ADAPTER_TYPE, 'moe_adapter')
    writer.add_uint32(MicronautKeys.EXPERT_COUNT, model_config.get('num_experts', len(adapter_config.get('experts', []))))
    writer.add_uint32(MicronautKeys.EXPERT_USED_COUNT, model_config.get('top_k_experts', 4))
    
    # Expert domains as JSON array
    domains = [exp['domain'] for exp in adapter_config.get('experts', [])]
    writer.add_string(MicronautKeys.EXPERT_DOMAINS, json.dumps(domains))
    
    # Routing configuration
    writer.add_string(MicronautKeys.ROUTING_MODE, 'hybrid')
    writer.add_float32(MicronautKeys.ROUTING_TEMPERATURE, agent_config.get('temperature', 0.7))
    
    # State persistence
    if model_config.get('state_file'):
        writer.add_string(MicronautKeys.STATE_FILE, model_config['state_file'])
    
    # GPU configuration
    writer.add_string(MicronautKeys.GPU_BACKEND, model_config.get('gpu_backend', 'cuda'))
    writer.add_bool(MicronautKeys.GPU_ENABLED, model_config.get('gpu_enabled', True))
    
    # Learning configuration
    writer.add_bool(MicronautKeys.ALLOW_SELF_MODIFY, model_config.get('allow_self_modify', False))
    writer.add_bool(MicronautKeys.PERSIST_LEARNING, adapter_config.get('memory', {}).get('persist_learning', True))
    
    # Skill layer
    skills = adapter_config.get('skills', [])
    writer.add_uint32(MicronautKeys.SKILL_COUNT, len(skills))
    writer.add_string(MicronautKeys.SKILLS, json.dumps(skills))
    
    # Copy tensors
    for tensor in reader.tensors:
        writer.add_tensor_info(tensor.name, tensor.shape, tensor.dtype, tensor.nbytes, tensor.data)
    
    if not dry_run:
        logger.info(f"Writing GGUF file with Micronaut metadata: {output_path}")
        writer.write_header()
        writer.write_data()
        logger.info("✓ Successfully embedded Micronaut adapter metadata")
    else:
        logger.info("Dry run - no file written")
        logger.info("Metadata that would be added:")
        for key in [
            MicronautKeys.ADAPTER_VERSION,
            MicronautKeys.ADAPTER_ID,
            MicronautKeys.ADAPTER_TYPE,
            MicronautKeys.EXPERT_COUNT,
            MicronautKeys.EXPERT_USED_COUNT,
        ]:
            logger.info(f"  {key}")


# =============================================================================
# Adapter Sidecar Creation
# =============================================================================

def create_adapter_sidecar(
    config_path: Path,
    output_path: Path,
    format: str = 'json'
) -> None:
    """
    Create Micronaut adapter sidecar file
    
    Args:
        config_path: Path to configuration JSON
        output_path: Output path for sidecar
        format: Output format ('json' or 'bson')
    """
    logger.info(f"Loading configuration: {config_path}")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    if format == 'json':
        # Save as JSON (human-readable)
        with open(output_path, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"✓ Created JSON adapter sidecar: {output_path}")
    
    elif format == 'bson':
        # Save as BSON (compact binary)
        # Note: Requires pymongo.bson or similar
        try:
            import bson
            with open(output_path, 'wb') as f:
                f.write(bson.encode(config))
            logger.info(f"✓ Created BSON adapter sidecar: {output_path}")
        except ImportError:
            logger.error("BSON format requires 'pymongo' or 'bson' package")
            logger.info("Install with: pip install pymongo")
            # Fallback to JSON
            with open(output_path.with_suffix('.json'), 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"✓ Created JSON adapter sidecar instead: {output_path.with_suffix('.json')}")


# =============================================================================
# Adapter Validation
# =============================================================================

def validate_adapter(adapter_path: Path) -> tuple[bool, list[str]]:
    """
    Validate Micronaut adapter configuration
    
    Returns:
        (is_valid, list of error messages)
    """
    errors = []
    
    logger.info(f"Validating adapter: {adapter_path}")
    
    # Load adapter
    if adapter_path.suffix == '.json':
        with open(adapter_path, 'r') as f:
            config = json.load(f)
    else:
        try:
            import bson
            with open(adapter_path, 'rb') as f:
                config = bson.decode(f.read())
        except ImportError:
            errors.append("Cannot load BSON without 'pymongo' or 'bson' package")
            return False, errors
    
    # Validate required fields
    required = ['version', 'id', 'experts', 'agent', 'model']
    for field in required:
        if field not in config:
            errors.append(f"Missing required field: {field}")
    
    if errors:
        return False, errors
    
    # Validate experts
    experts = config.get('experts', [])
    if not experts:
        errors.append("Must have at least one expert")
    
    expert_ids = set()
    for i, expert in enumerate(experts):
        if 'id' not in expert:
            errors.append(f"Expert {i} missing 'id'")
        else:
            if expert['id'] in expert_ids:
                errors.append(f"Duplicate expert ID: {expert['id']}")
            expert_ids.add(expert['id'])
        
        if 'domain' not in expert:
            errors.append(f"Expert {expert.get('id', i)} missing 'domain'")
        
        if 'weights_ref' not in expert:
            errors.append(f"Expert {expert.get('id', i)} missing 'weights_ref'")
    
    # Validate model config
    model = config.get('model', {})
    if model.get('num_experts', 0) != len(experts):
        errors.append(f"Model num_experts ({model.get('num_experts')}) != actual expert count ({len(experts)})")
    
    if not model.get('path', '').endswith('.gguf'):
        errors.append("Model path must point to .gguf file")
    
    # Validate agent config
    agent = config.get('agent', {})
    if 'system_prompt' not in agent:
        errors.append("Agent missing 'system_prompt'")
    
    if 'persona' not in agent:
        errors.append("Agent missing 'persona'")
    
    # Validate learned biases reference valid experts
    learned_biases = agent.get('learned_biases', {})
    for expert_id in learned_biases:
        if expert_id not in expert_ids:
            errors.append(f"Learned bias references unknown expert: {expert_id}")
    
    # Validate skills
    skills = config.get('skills', [])
    for i, skill in enumerate(skills):
        if 'trigger' not in skill:
            errors.append(f"Skill {i} missing 'trigger'")
        if 'action' not in skill:
            errors.append(f"Skill {i} missing 'action'")
    
    is_valid = len(errors) == 0
    if is_valid:
        logger.info("✓ Adapter validation passed")
    else:
        logger.error(f"✗ Adapter validation failed with {len(errors)} error(s)")
        for error in errors:
            logger.error(f"  - {error}")
    
    return is_valid, errors


# =============================================================================
# Routing Analysis
# =============================================================================

def analyze_routing(adapter_path: Path, test_inputs: list[str]) -> None:
    """
    Analyze expert routing for sample inputs
    
    Args:
        adapter_path: Path to adapter configuration
        test_inputs: List of test input strings
    """
    logger.info(f"Analyzing routing for: {adapter_path}")
    
    # Load adapter
    if adapter_path.suffix == '.json':
        with open(adapter_path, 'r') as f:
            config = json.load(f)
    else:
        import bson
        with open(adapter_path, 'rb') as f:
            config = bson.decode(f.read())
    
    # Build domain keywords
    domain_keywords = {
        'python_code': ['python', 'def ', 'import ', 'pip', 'django'],
        'cpp_code': ['C++', '#include', 'std::', 'template'],
        'js_code': ['JavaScript', 'function', 'const ', '=>'],
        'mathematics': ['equation', 'formula', 'calculate'],
        'debugging': ['error', 'bug', 'crash', 'exception'],
        'general': ['help', 'explain', 'what', 'how'],
    }
    
    # Get learned biases
    learned_biases = config.get('agent', {}).get('learned_biases', {})
    
    print("\n" + "=" * 80)
    print("MICRONAUT ROUTING ANALYSIS")
    print("=" * 80)
    
    for input_text in test_inputs:
        print(f"\nInput: \"{input_text}\"")
        print("-" * 80)
        
        # Compute scores for each expert
        scores = []
        for expert in config.get('experts', []):
            expert_id = expert['id']
            domain = expert['domain']
            
            # Base score from learned bias
            score = learned_biases.get(expert_id, expert.get('routing_bias', 0.0))
            
            # Domain keyword matching
            keywords = domain_keywords.get(domain, [])
            for keyword in keywords:
                if keyword.lower() in input_text.lower():
                    score += 0.1
            score = min(score, 1.0)  # Cap at 1.0
            
            scores.append((expert['name'], domain, score))
        
        # Softmax
        import math
        max_score = max(s[2] for s in scores)
        exp_scores = [(name, domain, math.exp(s - max_score)) for name, domain, s in scores]
        sum_exp = sum(s[2] for s in exp_scores)
        probs = [(name, domain, p / sum_exp) for name, domain, p in exp_scores]
        
        # Sort by probability
        probs.sort(key=lambda x: x[2], reverse=True)
        
        # Display top experts
        print(f"{'Expert':<20} {'Domain':<20} {'Probability':>12}")
        for name, domain, prob in probs[:5]:
            bar = '█' * int(prob * 20)
            print(f"{name:<20} {domain:<20} {prob:>12.3f} {bar}")


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Micronaut Adapter Tools for GGUF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Embed adapter metadata in GGUF
  python -m gguf.micronaut add-metadata model.gguf --adapter config.json
  
  # Create adapter sidecar
  python -m gguf.micronaut create-adapter --config config.json --output adapter.json
  
  # Validate adapter
  python -m gguf.micronaut validate adapter.json
  
  # Analyze routing
  python -m gguf.micronaut analyze adapter.json "Write Python code" "Debug C++ crash"
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to run')
    
    # add-metadata command
    p_add = subparsers.add_parser('add-metadata', help='Embed Micronaut metadata in GGUF')
    p_add.add_argument('model', type=Path, help='GGUF model file')
    p_add.add_argument('--adapter', type=Path, required=True, help='Adapter config JSON')
    p_add.add_argument('--output', type=Path, help='Output GGUF file (default: overwrite)')
    p_add.add_argument('--dry-run', action='store_true', help='Show changes without modifying')
    
    # create-adapter command
    p_create = subparsers.add_parser('create-adapter', help='Create adapter sidecar file')
    p_create.add_argument('--config', type=Path, required=True, help='Configuration JSON')
    p_create.add_argument('--output', type=Path, required=True, help='Output sidecar file')
    p_create.add_argument('--format', choices=['json', 'bson'], default='json', help='Output format')
    
    # validate command
    p_validate = subparsers.add_parser('validate', help='Validate adapter configuration')
    p_validate.add_argument('adapter', type=Path, help='Adapter sidecar file')
    
    # analyze command
    p_analyze = subparsers.add_parser('analyze', help='Analyze expert routing')
    p_analyze.add_argument('adapter', type=Path, help='Adapter sidecar file')
    p_analyze.add_argument('inputs', nargs='+', help='Test input strings')
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s'
    )
    
    if args.command == 'add-metadata':
        with open(args.adapter, 'r') as f:
            config = json.load(f)
        embed_adapter_metadata(args.model, config, args.output, args.dry_run)
    
    elif args.command == 'create-adapter':
        create_adapter_sidecar(args.config, args.output, args.format)
    
    elif args.command == 'validate':
        is_valid, errors = validate_adapter(args.adapter)
        sys.exit(0 if is_valid else 1)
    
    elif args.command == 'analyze':
        analyze_routing(args.adapter, args.inputs)
    
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == '__main__':
    main()
