#!/usr/bin/env python3
"""
Micronaut Bundle Creator Tool

Creates self-contained Micronaut BSON bundles with:
- GGUF model reference
- Agent configuration
- Expert system
- Learned adapters
- Tools & permissions

Usage:
    python create_bundle.py --name CoderMicronaut --output bundles/CoderMicronaut.bson
    python create_bundle.py --name ChatMicronaut --output bundles/ChatMicronaut.bson
    python create_bundle.py --name DebugMicronaut --output bundles/DebugMicronaut.bson
"""

import argparse
import bson
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path


# ── Bundle Templates ──────────────────────────────────────────────────────────

BUNDLE_TEMPLATES = {
    'CoderMicronaut': {
        'id': 'coder-micronaut-001',
        'name': 'CodeAssist Pro',
        'description': 'Expert coding assistant for Python, C++, JavaScript, and debugging',
        'persona': 'Expert programmer specializing in multiple languages with strong debugging skills',
        'experts': [
            {
                'id': 'exp-python',
                'name': 'Python Expert',
                'domain': 'python_code',
                'bias': 0.25,
                'trainable': True,
                'keywords': ['python', 'def ', 'import ', 'pip', 'django', 'flask', '.py'],
                'system_prompt': 'You are an expert Python programmer. Write clean, efficient, well-documented code following PEP 8. Include type hints and docstrings.'
            },
            {
                'id': 'exp-cpp',
                'name': 'C/C++ Expert',
                'domain': 'cpp_code',
                'bias': 0.20,
                'trainable': True,
                'keywords': ['c++', 'cpp', '#include', 'std::', 'iostream', 'namespace', 'template'],
                'system_prompt': 'You are an expert C/C++ programmer. Write safe, efficient code with proper memory management. Use modern C++17/20 features when appropriate.'
            },
            {
                'id': 'exp-js',
                'name': 'JavaScript Expert',
                'domain': 'js_code',
                'bias': 0.15,
                'trainable': True,
                'keywords': ['javascript', 'js', 'npm', 'node.js', 'const ', 'let ', '=>', 'function'],
                'system_prompt': 'You are an expert JavaScript developer. Write modern ES6+ code with best practices. Use async/await for asynchronous operations.'
            },
            {
                'id': 'exp-debug',
                'name': 'Debug Expert',
                'domain': 'debugging',
                'bias': 0.30,
                'trainable': True,
                'keywords': ['error', 'bug', 'crash', 'exception', 'debug', 'fix', 'broken', 'not working'],
                'system_prompt': 'You are a debugging expert. Systematically identify and fix errors. Ask clarifying questions about error messages and stack traces.'
            },
            {
                'id': 'exp-general',
                'name': 'General Expert',
                'domain': 'general',
                'bias': 0.0,
                'trainable': False,
                'keywords': ['help', 'question'],
                'system_prompt': 'You are a helpful coding assistant. Provide clear, concise answers.'
            }
        ],
        'skills': [
            {
                'name': 'code_generation',
                'trigger': ['write code', 'create function', 'implement', 'generate'],
                'action': 'generate_code',
                'description': 'Generate code in Python, C++, JavaScript, etc.'
            },
            {
                'name': 'code_review',
                'trigger': ['review', 'improve', 'optimize', 'refactor'],
                'action': 'review_code',
                'description': 'Review and suggest improvements to existing code'
            },
            {
                'name': 'debugging',
                'trigger': ['error', 'bug', 'crash', 'fix', 'debug'],
                'action': 'debug_code',
                'description': 'Identify and fix bugs in code'
            },
            {
                'name': 'explanation',
                'trigger': ['explain', 'what does', 'how does'],
                'action': 'explain_code',
                'description': 'Explain how code works'
            }
        ],
        'tools': {
            'enabled': ['fs_read', 'fs_write', 'terminal'],
            'permissions': {
                'fs_read': {'allowed_paths': ['./*.py', './*.cpp', './*.h', './*.js']},
                'fs_write': {'allowed_paths': ['./*.py', './*.cpp', './*.h', './*.js']},
                'terminal': {'allowed_commands': ['python', 'pip', 'g++', 'node', 'npm', 'git']}
            }
        }
    },
    
    'ChatMicronaut': {
        'id': 'chat-micronaut-001',
        'name': 'ChatAssist',
        'description': 'Friendly conversation assistant for general questions and explanations',
        'persona': 'Friendly, knowledgeable conversationalist who can explain complex topics simply',
        'experts': [
            {
                'id': 'exp-general',
                'name': 'General Expert',
                'domain': 'general',
                'bias': 0.20,
                'trainable': True,
                'keywords': ['help', 'what', 'how', 'when', 'where', 'why'],
                'system_prompt': 'You are a helpful, friendly assistant. Provide clear, accurate information.'
            },
            {
                'id': 'exp-writing',
                'name': 'Writing Expert',
                'domain': 'text',
                'bias': 0.25,
                'trainable': True,
                'keywords': ['write', 'essay', 'article', 'email', 'letter', 'story'],
                'system_prompt': 'You are a writing expert. Produce clear, well-structured, engaging text.'
            },
            {
                'id': 'exp-reasoning',
                'name': 'Reasoning Expert',
                'domain': 'logic',
                'bias': 0.15,
                'trainable': True,
                'keywords': ['why', 'reason', 'logic', 'argument', 'explain why'],
                'system_prompt': 'You are a logic and reasoning expert. Break down arguments systematically.'
            },
            {
                'id': 'exp-teaching',
                'name': 'Teaching Expert',
                'domain': 'education',
                'bias': 0.20,
                'trainable': True,
                'keywords': ['teach', 'learn', 'understand', 'explain'],
                'system_prompt': 'You are a teaching expert. Explain concepts clearly with examples.'
            }
        ],
        'skills': [
            {
                'name': 'conversation',
                'trigger': ['hi', 'hello', 'hey', 'good morning'],
                'action': 'chat',
                'description': 'Engage in natural conversation'
            },
            {
                'name': 'explanation',
                'trigger': ['explain', 'what is', 'how does'],
                'action': 'explain',
                'description': 'Explain concepts clearly'
            },
            {
                'name': 'summarization',
                'trigger': ['summarize', 'summary', 'brief'],
                'action': 'summarize',
                'description': 'Summarize long texts'
            },
            {
                'name': 'teaching',
                'trigger': ['teach', 'learn', 'understand'],
                'action': 'teach',
                'description': 'Teach new concepts'
            }
        ],
        'tools': {
            'enabled': ['web_search', 'knowledge_base'],
            'permissions': {
                'web_search': {'allowed_domains': ['*.wikipedia.org', '*.britannica.com']},
                'knowledge_base': {'categories': ['general', 'science', 'history', 'technology']}
            }
        }
    },
    
    'DebugMicronaut': {
        'id': 'debug-micronaut-001',
        'name': 'DebugPro',
        'description': 'Specialized debugging assistant for finding and fixing errors',
        'persona': 'Systematic debugger who methodically identifies root causes of issues',
        'experts': [
            {
                'id': 'exp-debug',
                'name': 'Debug Expert',
                'domain': 'debugging',
                'bias': 0.40,
                'trainable': True,
                'keywords': ['error', 'bug', 'crash', 'exception', 'traceback', 'stack trace'],
                'system_prompt': 'You are a debugging expert. Ask for error messages, stack traces, and reproduction steps. Systematically isolate the root cause.'
            },
            {
                'id': 'exp-python',
                'name': 'Python Debug Expert',
                'domain': 'python_debug',
                'bias': 0.25,
                'trainable': True,
                'keywords': ['python', 'traceback', 'typeerror', 'valueerror', 'attributeerror'],
                'system_prompt': 'You are a Python debugging expert. Understand Python exceptions and common pitfalls.'
            },
            {
                'id': 'exp-testing',
                'name': 'Testing Expert',
                'domain': 'testing',
                'bias': 0.20,
                'trainable': True,
                'keywords': ['test', 'unittest', 'pytest', 'assertion', 'failing test'],
                'system_prompt': 'You are a testing expert. Help write unit tests and debug failing tests.'
            }
        ],
        'skills': [
            {
                'name': 'error_analysis',
                'trigger': ['error', 'exception', 'traceback'],
                'action': 'analyze_error',
                'description': 'Analyze error messages and stack traces'
            },
            {
                'name': 'fix_generation',
                'trigger': ['fix', 'solve', 'resolve'],
                'action': 'generate_fix',
                'description': 'Generate fixes for identified bugs'
            },
            {
                'name': 'unit_test',
                'trigger': ['test', 'pytest', 'unittest'],
                'action': 'create_test',
                'description': 'Create unit tests to verify fixes'
            }
        ],
        'tools': {
            'enabled': ['terminal', 'debugger', 'test_runner'],
            'permissions': {
                'terminal': {'allowed_commands': ['python', 'pytest', 'gdb', 'lldb']},
                'debugger': {'allowed_languages': ['python', 'cpp', 'js']},
                'test_runner': {'frameworks': ['pytest', 'unittest', 'catch2']}
            }
        }
    },
    
    'MathMicronaut': {
        'id': 'math-micronaut-001',
        'name': 'MathAssist',
        'description': 'Mathematics expert for calculations, proofs, and problem solving',
        'persona': 'Patient mathematics teacher who shows step-by-step solutions',
        'experts': [
            {
                'id': 'exp-math',
                'name': 'Mathematics Expert',
                'domain': 'mathematics',
                'bias': 0.35,
                'trainable': True,
                'keywords': ['calculate', 'equation', 'formula', 'algebra', 'calculus', 'derivative', 'integral'],
                'system_prompt': 'You are a mathematics expert. Show step-by-step solutions with clear explanations. Use LaTeX for mathematical notation.'
            },
            {
                'id': 'exp-physics',
                'name': 'Physics Expert',
                'domain': 'physics',
                'bias': 0.20,
                'trainable': True,
                'keywords': ['physics', 'force', 'energy', 'momentum', 'velocity', 'acceleration'],
                'system_prompt': 'You are a physics expert. Apply physical laws and show calculations.'
            },
            {
                'id': 'exp-stats',
                'name': 'Statistics Expert',
                'domain': 'statistics',
                'bias': 0.20,
                'trainable': True,
                'keywords': ['statistics', 'probability', 'mean', 'median', 'standard deviation', 'distribution'],
                'system_prompt': 'You are a statistics expert. Explain statistical concepts and perform calculations.'
            }
        ],
        'skills': [
            {
                'name': 'calculation',
                'trigger': ['calculate', 'compute', 'solve'],
                'action': 'calculate',
                'description': 'Perform mathematical calculations'
            },
            {
                'name': 'proof',
                'trigger': ['prove', 'theorem', 'lemma'],
                'action': 'prove',
                'description': 'Create mathematical proofs'
            },
            {
                'name': 'visualization',
                'trigger': ['graph', 'plot', 'visualize'],
                'action': 'visualize',
                'description': 'Create mathematical visualizations'
            }
        ],
        'tools': {
            'enabled': ['calculator', 'graphing', 'symbolic_math'],
            'permissions': {
                'calculator': {'precision': 'high', 'modes': ['basic', 'scientific', 'graphing']},
                'graphing': {'types': ['2d', '3d', 'parametric']},
                'symbolic_math': {'operations': ['simplify', 'differentiate', 'integrate', 'solve']}
            }
        }
    },
    
    'GeneralMicronaut': {
        'id': 'general-micronaut-001',
        'name': 'GeneralAssist',
        'description': 'General-purpose assistant for everyday tasks',
        'persona': 'Helpful, versatile assistant for a wide range of tasks',
        'experts': [
            {
                'id': 'exp-general',
                'name': 'General Expert',
                'domain': 'general',
                'bias': 0.25,
                'trainable': True,
                'keywords': ['help', 'question', 'information'],
                'system_prompt': 'You are a helpful general assistant. Provide accurate, useful information.'
            },
            {
                'id': 'exp-research',
                'name': 'Research Expert',
                'domain': 'research',
                'bias': 0.20,
                'trainable': True,
                'keywords': ['research', 'find', 'search', 'look up'],
                'system_prompt': 'You are a research expert. Find and synthesize information from multiple sources.'
            },
            {
                'id': 'exp-planning',
                'name': 'Planning Expert',
                'domain': 'planning',
                'bias': 0.15,
                'trainable': True,
                'keywords': ['plan', 'schedule', 'organize', 'prepare'],
                'system_prompt': 'You are a planning expert. Help organize tasks and create schedules.'
            }
        ],
        'skills': [
            {
                'name': 'qa',
                'trigger': ['what', 'when', 'where', 'who', 'how'],
                'action': 'answer_question',
                'description': 'Answer general questions'
            },
            {
                'name': 'research',
                'trigger': ['research', 'find information', 'look up'],
                'action': 'research',
                'description': 'Research topics and synthesize information'
            },
            {
                'name': 'planning',
                'trigger': ['plan', 'schedule', 'organize'],
                'action': 'create_plan',
                'description': 'Create plans and schedules'
            }
        ],
        'tools': {
            'enabled': ['web_search', 'knowledge_base', 'calendar'],
            'permissions': {
                'web_search': {'allowed_domains': ['*']},
                'knowledge_base': {'categories': ['general']},
                'calendar': {'operations': ['read', 'write', 'remind']}
            }
        }
    }
}


# ── Helper Functions ──────────────────────────────────────────────────────────

def compute_file_hash(filepath):
    """Compute SHA256 hash of a file"""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def get_model_info(model_path):
    """Get GGUF model information"""
    if not os.path.exists(model_path):
        return {
            'path': model_path,
            'exists': False,
            'size_mb': 0,
            'hash': None
        }
    
    size_bytes = os.path.getsize(model_path)
    size_mb = size_bytes / (1024 * 1024)
    
    return {
        'path': model_path,
        'exists': True,
        'size_mb': round(size_mb, 1),
        'hash': compute_file_hash(model_path)
    }


def load_existing_config(config_path):
    """Load existing Micronaut configuration"""
    if not os.path.exists(config_path):
        return None
    
    with open(config_path, 'r') as f:
        return json.load(f)


def load_existing_state(state_path):
    """Load existing learned state"""
    if not os.path.exists(state_path):
        return None
    
    with open(state_path, 'r') as f:
        return json.load(f)


def load_existing_bson(bson_path):
    """Load existing BSON configuration"""
    if not os.path.exists(bson_path):
        return None
    
    with open(bson_path, 'rb') as f:
        return bson.decode(f.read())


# ── Bundle Creation ───────────────────────────────────────────────────────────

def create_bundle(name, output_path, model_path=None, existing_config=None):
    """Create a Micronaut BSON bundle"""
    
    # Get template
    if name not in BUNDLE_TEMPLATES:
        print(f"Error: Unknown bundle type '{name}'")
        print(f"Available types: {', '.join(BUNDLE_TEMPLATES.keys())}")
        return None
    
    template = BUNDLE_TEMPLATES[name].copy()
    
    # Default model path
    if model_path is None:
        model_path = 'src/models/Qwen2.5-0.5B-Instruct-GGUF/qwen2.5-0.5b-instruct-q8_0.gguf'
    
    # Get model info
    model_info = get_model_info(model_path)
    
    # Build bundle
    bundle = {
        'version': '1.0',
        'format': 'micronaut.bundle',
        'id': template['id'],
        'name': template['name'],
        'description': template['description'],
        'created': datetime.utcnow().isoformat() + 'Z',
        
        'model': {
            'type': 'gguf',
            'embedded': False,
            'path': model_path,
            'quantization': 'Q8_0',
            'exists': model_info['exists'],
            'size_mb': model_info['size_mb'],
            'hash': model_info['hash']
        },
        
        'agent': {
            'name': template['name'],
            'persona': template['persona'],
            'temperature': 0.7,
            'max_tokens': 1024,
            'skills': template['skills']
        },
        
        'experts': template['experts'],
        
        'learned': {
            'biases': {e['id']: e.get('bias', 0) for e in template['experts']},
            'interaction_count': 0,
            'last_trained': None,
            'preferences': {}
        },
        
        'adapters': {
            'count': 6,
            'files': [f'fold_{i}.safetensors' for i in range(6)],
            'embedded': False,
            'path': './adapters/'
        },
        
        'memory': {
            'short_term': [],
            'long_term': []
        },
        
        'tools': template['tools']
    }
    
    # Merge existing config if provided
    if existing_config:
        if 'learned' in existing_config:
            bundle['learned'].update(existing_config['learned'])
        if 'memory' in existing_config:
            bundle['memory'].update(existing_config['memory'])
    
    # Create output directory
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # Write bundle
    with open(output_path, 'wb') as f:
        f.write(bson.encode(bundle))
    
    print(f"OK Created bundle: {output_path}")
    print(f"  ID: {bundle['id']}")
    print(f"  Name: {bundle['name']}")
    print(f"  Experts: {len(bundle['experts'])}")
    print(f"  Skills: {len(bundle['agent']['skills'])}")
    print(f"  Model: {model_path} ({model_info['size_mb']} MB)")
    
    return bundle


# ── Migration Functions ───────────────────────────────────────────────────────

def migrate_from_adapter(adapter_path, state_path, bundle_name, output_path):
    """Migrate from old adapter+state format to bundle"""
    
    print(f"\\nMigrating from adapter format...")
    print(f"  Adapter: {adapter_path}")
    print(f"  State: {state_path}")
    
    # Load existing files
    adapter = load_existing_config(adapter_path)
    state = load_existing_state(state_path)
    
    if not adapter:
        print(f"  WARN Adapter not found: {adapter_path}")
        adapter = {}
    
    if not state:
        print(f"  WARN State not found: {state_path}")
        state = {}
    
    # Get template
    if bundle_name not in BUNDLE_TEMPLATES:
        print(f"  WARN Unknown bundle type, using GeneralMicronaut")
        bundle_name = 'GeneralMicronaut'
    
    template = BUNDLE_TEMPLATES[bundle_name]
    
    # Merge learned biases
    learned_biases = {}
    if 'learned_biases' in state:
        learned_biases = state['learned_biases']
        print(f"  OK Migrated {len(learned_biases)} learned biases")
    
    # Merge memory
    memory = {
        'short_term': state.get('memory', [])[:5] if 'memory' in state else [],
        'long_term': []
    }
    
    # Create bundle with migrated data
    bundle = create_bundle(
        name=bundle_name,
        output_path=output_path,
        existing_config={
            'learned': {'biases': learned_biases},
            'memory': memory
        }
    )
    
    if bundle:
        print(f"\\nOK Migration complete: {output_path}")
    
    return bundle


# ── Main Entry Point ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Create Micronaut BSON bundles',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python create_bundle.py --name CoderMicronaut --output bundles/CoderMicronaut.bson
  python create_bundle.py --name ChatMicronaut --output bundles/ChatMicronaut.bson
  python create_bundle.py --name DebugMicronaut --output bundles/DebugMicronaut.bson
  
  # Migrate from existing adapter
  python create_bundle.py --migrate --adapter qwen_micronaut_adapter.json --state qwen_micronaut_state.json --output CoderMicronaut.bson
        '''
    )
    
    parser.add_argument('--name', type=str, 
                        help='Bundle name (CoderMicronaut, ChatMicronaut, DebugMicronaut, MathMicronaut, GeneralMicronaut)')
    parser.add_argument('--output', type=str, 
                        help='Output bundle path')
    parser.add_argument('--model', type=str, 
                        help='GGUF model path (default: src/models/Qwen2.5-0.5B-Instruct-GGUF/qwen2.5-0.5b-instruct-q8_0.gguf)')
    parser.add_argument('--migrate', action='store_true',
                        help='Migrate from existing adapter+state format')
    parser.add_argument('--adapter', type=str,
                        help='Existing adapter config path (for migration)')
    parser.add_argument('--state', type=str,
                        help='Existing state path (for migration)')
    parser.add_argument('--list', action='store_true',
                        help='List available bundle types')
    
    args = parser.parse_args()
    
    # List available types
    if args.list:
        print("\\nAvailable Bundle Types:")
        print("=" * 60)
        for name, template in BUNDLE_TEMPLATES.items():
            print(f"\\n{name}")
            print(f"  ID: {template['id']}")
            print(f"  Description: {template['description']}")
            print(f"  Experts: {len(template['experts'])}")
            print(f"  Skills: {len(template['skills'])}")
        return 0
    
    # Migration mode
    if args.migrate:
        if not args.adapter or not args.output:
            print("Error: --migrate requires --adapter and --output")
            return 1
        
        bundle_name = args.name or 'CoderMicronaut'
        migrate_from_adapter(args.adapter, args.state, bundle_name, args.output)
        return 0
    
    # Create new bundle
    if args.name and args.output:
        create_bundle(args.name, args.output, args.model)
        return 0
    
    # No valid arguments
    parser.print_help()
    return 1


if __name__ == '__main__':
    exit(main())
