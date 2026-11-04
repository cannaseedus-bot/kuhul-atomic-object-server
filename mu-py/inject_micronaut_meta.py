#!/usr/bin/env python3
"""
Simple Micronaut metadata injector for GGUF files

Usage:
    python inject_micronaut_meta.py model.gguf qwen_micronaut_adapter.json output.gguf
"""

import sys
import json
import struct
from pathlib import Path
from gguf import GGUFReader, GGUFWriter, GGUFValueType


def inject_micronaut_metadata(input_path: Path, adapter_config: dict, output_path: Path):
    """Inject Micronaut metadata into existing GGUF file"""
    
    print(f"Loading GGUF: {input_path}")
    reader = GGUFReader(input_path, 'r')
    
    print(f"Creating output: {output_path}")
    writer = GGUFWriter(path=str(output_path), arch='qwen2')
    
    # Copy all existing metadata
    print("Copying existing metadata...")
    for field_name, field in reader.fields.items():
        if not field.data:
            continue
            
        try:
            value_part = field.parts[field.data[0]]
            value_type = field.types[0] if field.types else None
            
            # Handle different value types
            if value_type == GGUFValueType.STRING:
                value = str(value_part.tobytes().decode('utf-8'))
                writer.add_string(field_name, value)
            elif value_type == GGUFValueType.UINT32:
                value = int(value_part[0])
                writer.add_uint32(field_name, value)
            elif value_type == GGUFValueType.UINT64:
                value = int(value_part[0])
                writer.add_uint64(field_name, value)
            elif value_type == GGUFValueType.FLOAT32:
                value = float(value_part[0])
                writer.add_float32(field_name, value)
            elif value_type == GGUFValueType.BOOL:
                value = bool(value_part[0])
                writer.add_bool(field_name, value)
            elif value_type == GGUFValueType.ARRAY:
                # Skip complex arrays for now
                print(f"  Skipping array field: {field_name}")
                continue
            else:
                print(f"  Skipping unknown type {value_type}: {field_name}")
                continue
                
        except Exception as e:
            print(f"  Warning: Could not copy {field_name}: {e}")
            continue
    
    # Add Micronaut metadata
    print("\nAdding Micronaut adapter metadata...")
    model_config = adapter_config.get('model', {})
    agent_config = adapter_config.get('agent', {})
    
    micronaut_fields = [
        ('micronaut.adapter_version', adapter_config.get('version', '1.0'), 'string'),
        ('micronaut.id', adapter_config.get('id', 'micronaut-default'), 'string'),
        ('micronaut.type', 'moe_adapter', 'string'),
        ('micronaut.expert_count', model_config.get('num_experts', 8), 'uint32'),
        ('micronaut.expert_used_count', model_config.get('top_k_experts', 4), 'uint32'),
        ('micronaut.routing_mode', 'hybrid', 'string'),
        ('micronaut.routing_temperature', agent_config.get('temperature', 0.7), 'float32'),
        ('micronaut.gpu_backend', model_config.get('gpu_backend', 'cuda'), 'string'),
        ('micronaut.gpu_enabled', model_config.get('gpu_enabled', True), 'bool'),
        ('micronaut.allow_self_modify', model_config.get('allow_self_modify', False), 'bool'),
    ]
    
    if model_config.get('state_file'):
        micronaut_fields.append(('micronaut.state_file', model_config['state_file'], 'string'))
    
    for field_name, value, field_type in micronaut_fields:
        try:
            if field_type == 'string':
                writer.add_string(field_name, str(value))
            elif field_type == 'uint32':
                writer.add_uint32(field_name, int(value))
            elif field_type == 'float32':
                writer.add_float32(field_name, float(value))
            elif field_type == 'bool':
                writer.add_bool(field_name, bool(value))
            print(f"  + {field_name} = {value}")
        except Exception as e:
            print(f"  Error adding {field_name}: {e}")
    
    # Copy tensors
    print(f"\nCopying {len(reader.tensors)} tensors...")
    for tensor in reader.tensors:
        try:
            writer.add_tensor_info(
                name=tensor.name,
                shape=list(tensor.shape),
                dtype=tensor.tensor_type,
                nbytes=tensor.nbytes,
                tensor=tensor.data
            )
        except Exception as e:
            print(f"  Warning: Could not copy tensor {tensor.name}: {e}")
    
    # Write output
    print("\nWriting output file...")
    writer.write_header()
    writer.write_data()
    
    print(f"\n✓ Successfully created: {output_path}")
    print(f"  Original size: {input_path.stat().st_size / 1024 / 1024:.1f} MB")
    print(f"  New size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")


def main():
    if len(sys.argv) != 4:
        print("Usage: python inject_micronaut_meta.py <input.gguf> <adapter.json> <output.gguf>")
        sys.exit(1)
    
    input_path = Path(sys.argv[1])
    adapter_path = Path(sys.argv[2])
    output_path = Path(sys.argv[3])
    
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}")
        sys.exit(1)
    
    if not adapter_path.exists():
        print(f"Error: Adapter config not found: {adapter_path}")
        sys.exit(1)
    
    with open(adapter_path, 'r') as f:
        adapter_config = json.load(f)
    
    inject_micronaut_metadata(input_path, adapter_config, output_path)


if __name__ == '__main__':
    main()
