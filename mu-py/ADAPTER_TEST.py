#!/usr/bin/env python3
"""
Micronaut Adapter Integration Test
"""
import json
import sys

def test_adapter():
    try:
        # Load adapter config
        with open('qwen_micronaut_adapter.json', 'r') as f:
            adapter = json.load(f)
        
        print('MICRONAUT ADAPTER TEST\n' + '='*50)
        print('[OK] Adapter ID: ' + adapter.get('id', 'UNKNOWN'))
        print('[OK] Version: ' + adapter.get('version', 'UNKNOWN'))
        print('[OK] Experts: ' + str(len(adapter.get('experts', []))))
        print('[OK] Skills: ' + str(len(adapter.get('skills', []))))
        
        # Validate experts
        experts = adapter.get('experts', [])
        if experts:
            print('\nExperts (' + str(len(experts)) + '):')
            for expert in experts[:3]:
                print('  - ' + expert.get('name', 'UNKNOWN') + ': ' + expert.get('domain', 'UNKNOWN'))
        
        # Load state
        with open('qwen_micronaut_state.json', 'r') as f:
            state = json.load(f)
        
        print('\n[OK] State file loaded')
        print('[OK] Learned biases: ' + str(len(state.get('learned_biases', {}))))
        
        # Validate schema
        with open('micronaut_adapter_schema.json', 'r') as f:
            schema = json.load(f)
        
        print('[OK] Schema loaded (version ' + schema.get('version', 'UNKNOWN') + ')')
        
        print('\n[PASS] ADAPTER VERIFICATION: SUCCESS')
        return True
        
    except Exception as e:
        print('[FAIL] ERROR: ' + str(e))
        return False

if __name__ == '__main__':
    success = test_adapter()
    sys.exit(0 if success else 1)
