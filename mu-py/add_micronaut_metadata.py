#!/usr/bin/env python3
"""
Add Micronaut metadata to existing GGUF file

This script adds new Micronaut adapter metadata fields to an existing GGUF model file
without modifying the tensors.

Usage:
    python add_micronaut_metadata.py input.gguf adapter.json output.gguf
"""

import sys
import json
import struct
import mmap
from pathlib import Path
from typing import Any


def add_metadata_to_gguf(input_path: Path, metadata: dict[str, Any], output_path: Path):
    """
    Add metadata fields to existing GGUF file by rewriting the header
    
    This is a low-level operation that:
    1. Reads the original GGUF header
    2. Adds new metadata fields
    3. Rewrites the file with updated header
    4. Preserves all tensors (no copying needed)
    """
    
    print(f"Reading GGUF file: {input_path}")
    
    with open(input_path, 'r+b') as f:
        # Memory map the file for efficient access
        mm = mmap.mmap(f.fileno(), 0)
        
        # Read GGUF header
        magic = mm[0:4]
        if magic != b'GGUF':
            print(f"Error: Not a valid GGUF file (magic: {magic})")
            return False
        
        version = struct.unpack('<I', mm[4:8])[0]
        tensor_count = struct.unpack('<Q', mm[8:16])[0]
        kv_count = struct.unpack('<Q', mm[16:24])[0]
        
        print(f"GGUF version: {version}")
        print(f"Tensor count: {tensor_count}")
        print(f"KV count: {kv_count}")
        
        # Parse existing metadata to find where it ends
        pos = 24  # Start after header
        for i in range(kv_count):
            # Read key (string)
            key_len = struct.unpack('<Q', mm[pos:pos+8])[0]
            pos += 8 + key_len  # Skip key length + key data
            
            # Read value type
            value_type = struct.unpack('<I', mm[pos:pos+4])[0]
            pos += 4
            
            # Skip value based on type
            if value_type == 0:  # UINT8
                pos += 1
            elif value_type == 1:  # INT8
                pos += 1
            elif value_type == 2:  # UINT16
                pos += 2
            elif value_type == 3:  # INT16
                pos += 2
            elif value_type == 4:  # UINT32
                pos += 4
            elif value_type == 5:  # INT32
                pos += 4
            elif value_type == 6:  # FLOAT32
                pos += 4
            elif value_type == 7:  # BOOL
                pos += 1
            elif value_type == 8:  # STRING
                str_len = struct.unpack('<Q', mm[pos:pos+8])[0]
                pos += 8 + str_len
            elif value_type == 9:  # ARRAY
                arr_len = struct.unpack('<Q', mm[pos:pos+8])[0]
                pos += 8
                # Skip array elements (simplified - assumes simple types)
                arr_type = struct.unpack('<I', mm[pos:pos+4])[0]
                pos += 4
                if arr_type == 8:  # String array
                    for j in range(arr_len):
                        str_len = struct.unpack('<Q', mm[pos:pos+8])[0]
                        pos += 8 + str_len
                else:
                    elem_size = {0:1, 1:1, 2:2, 3:2, 4:4, 5:4, 6:4, 7:1, 10:8, 11:8, 12:8}.get(arr_type, 4)
                    pos += arr_len * elem_size
            elif value_type == 10:  # UINT64
                pos += 8
            elif value_type == 11:  # INT64
                pos += 8
            elif value_type == 12:  # FLOAT64
                pos += 8
        
        # Align to 8 bytes
        header_end = (pos + 7) & ~7
        
        print(f"Original header size: {header_end} bytes")
        
        # Build new metadata bytes
        new_kv_data = bytearray()
        new_kv_count = 0
        
        for key, value in metadata.items():
            # Encode key
            key_bytes = key.encode('utf-8')
            new_kv_data += struct.pack('<Q', len(key_bytes))
            new_kv_data += key_bytes
            
            # Encode value
            if isinstance(value, str):
                value_bytes = value.encode('utf-8')
                new_kv_data += struct.pack('<I', 8)  # STRING type
                new_kv_data += struct.pack('<Q', len(value_bytes))
                new_kv_data += value_bytes
            elif isinstance(value, int):
                if 0 <= value <= 0xFFFFFFFF:
                    new_kv_data += struct.pack('<I', 4)  # UINT32 type
                    new_kv_data += struct.pack('<I', value)
                else:
                    new_kv_data += struct.pack('<I', 10)  # UINT64 type
                    new_kv_data += struct.pack('<Q', value)
            elif isinstance(value, float):
                new_kv_data += struct.pack('<I', 6)  # FLOAT32 type
                new_kv_data += struct.pack('<f', value)
            elif isinstance(value, bool):
                new_kv_data += struct.pack('<I', 7)  # BOOL type
                new_kv_data += struct.pack('<B', 1 if value else 0)
            
            new_kv_count += 1
            print(f"  + {key} = {value}")
        
        # Align new KV data
        while len(new_kv_data) % 8 != 0:
            new_kv_data += b'\x00'
        
        new_header_size = header_end + len(new_kv_data)
        
        # Calculate tensor info offset shift
        shift = len(new_kv_data)
        
        print(f"New header size: {new_header_size} bytes")
        print(f"Adding {new_kv_count} new metadata fields")
        
        # Create output file
        print(f"Writing output: {output_path}")
        with open(output_path, 'wb') as out_f:
            # Write original header with updated KV count
            out_f.write(mm[:16])  # Magic + version
            out_f.write(struct.pack('<Q', tensor_count))  # Tensor count (unchanged)
            out_f.write(struct.pack('<Q', kv_count + new_kv_count))  # New KV count
            out_f.write(mm[24:header_end])  # Rest of original header
            
            # Write new metadata
            out_f.write(new_kv_data)
            
            # Copy tensor info section (need to update offsets)
            tensor_info_start = header_end
            mm.seek(tensor_info_start)
            
            for i in range(tensor_count):
                # Read tensor name
                name_len = struct.unpack('<Q', mm[tensor_info_start:tensor_info_start+8])[0]
                tensor_data = mm[tensor_info_start:tensor_info_start+8+name_len]
                
                # Read dimensions
                pos = tensor_info_start + 8 + name_len
                n_dims = struct.unpack('<I', mm[pos:pos+4])[0]
                pos += 4
                
                tensor_data += struct.pack('<I', n_dims)
                
                for j in range(n_dims):
                    dim = struct.unpack('<Q', mm[pos:pos+8])[0]
                    tensor_data += struct.pack('<Q', dim)
                    pos += 8
                
                # Read type
                tensor_type = struct.unpack('<I', mm[pos:pos+4])[0]
                tensor_data += struct.pack('<I', tensor_type)
                pos += 4
                
                # Read offset and add shift
                offset = struct.unpack('<Q', mm[pos:pos+8])[0]
                tensor_data += struct.pack('<Q', offset + shift)
                
                # Write updated tensor info
                out_f.write(tensor_data)
                
                tensor_info_start = pos + 8
            
            # Copy tensor data (everything after tensor info)
            mm.seek(tensor_info_start)
            remaining = mm.read()
            out_f.write(remaining)
        
        mm.close()
        
        print(f"\n✓ Successfully created: {output_path}")
        print(f"  Original size: {input_path.stat().st_size / 1024 / 1024:.1f} MB")
        print(f"  New size: {output_path.stat().st_size / 1024 / 1024:.1f} MB")
        print(f"  Size increase: {(output_path.stat().st_size - input_path.stat().st_size) / 1024:.1f} KB (metadata)")
        
        return True


def main():
    if len(sys.argv) != 4:
        print("Usage: python add_micronaut_metadata.py <input.gguf> <adapter.json> <output.gguf>")
        print("\nExample:")
        print("  python add_micronaut_metadata.py qwen2.5-0.5b-instruct-q8_0.gguf qwen_micronaut_adapter.json qwen2.5-0.5b-micronaut.gguf")
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
    
    # Load adapter config
    with open(adapter_path, 'r') as f:
        adapter_config = json.load(f)
    
    # Build metadata dict
    model_config = adapter_config.get('model', {})
    agent_config = adapter_config.get('agent', {})
    
    metadata = {
        'micronaut.adapter_version': adapter_config.get('version', '1.0'),
        'micronaut.id': adapter_config.get('id', 'micronaut-default'),
        'micronaut.type': 'moe_adapter',
        'micronaut.expert_count': model_config.get('num_experts', 8),
        'micronaut.expert_used_count': model_config.get('top_k_experts', 4),
        'micronaut.routing_mode': 'hybrid',
        'micronaut.routing_temperature': agent_config.get('temperature', 0.7),
        'micronaut.gpu_backend': model_config.get('gpu_backend', 'cuda'),
        'micronaut.gpu_enabled': model_config.get('gpu_enabled', True),
        'micronaut.allow_self_modify': model_config.get('allow_self_modify', False),
    }
    
    if model_config.get('state_file'):
        metadata['micronaut.state_file'] = model_config['state_file']
    
    # Add metadata to GGUF
    success = add_metadata_to_gguf(input_path, metadata, output_path)
    
    if success:
        print("\n✓ Micronaut metadata successfully added!")
        print("\nTo verify:")
        print(f"  python -c \"from gguf import GGUFReader; r=GGUFReader('{output_path}', 'r'); print([k for k in r.fields if 'micronaut' in k])\"")
    else:
        print("\n✗ Failed to add metadata")
        sys.exit(1)


if __name__ == '__main__':
    main()
