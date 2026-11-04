#!/usr/bin/env python3
"""
Export Python Micronaut router state to XJSON for C++ runtime

This bridges the Python routing algorithm with your C++ ASX runtime.
"""

from micronaut_adapter import AdapterLoader, Router
import json
from datetime import datetime
from pathlib import Path

def export_router_to_xjson(adapter_path: str = "qwen_micronaut_adapter.json",
                           state_path: str = "qwen_micronaut_state.json",
                           output_path: str = "src/models/micronaut_runtime.xjson"):
    """
    Export Python router state to XJSON format for C++ runtime
    """
    
    print("="*70)
    print("MICRONAUT PYTHON → C++ XJSON EXPORTER")
    print("="*70)
    
    # Load adapter
    print(f"\nLoading adapter: {adapter_path}")
    config = AdapterLoader.load(adapter_path)
    
    # Create router
    print(f"Creating router for: {config.agent.name}")
    router = Router(config)
    
    # Load learned state
    if Path(state_path).exists():
        print(f"Loading learned state: {state_path}")
        router.load_state(state_path)
        print(f"  Loaded {len(router.biases)} bias values")
    else:
        print("No learned state found, using defaults")
    
    # Build XJSON structure matching your micronaut_demo.xjson format
    xjson = {
        "@version": "1.0",
        "@format": "micronaut.xjson",
        "@control": "horizontal-fold",
        
        "@meta": {
            "id": config.id,
            "name": config.agent.name,
            "description": config.memory.description if config.memory else "Micronaut adapter runtime",
            "created": datetime.now().isoformat(),
            "exported_from": "python_micronaut_adapter"
        },
        
        "@model.ref": {
            "id": config.model.id,
            "path": config.model.path,
            "hash": config.model.hash or "sha256:pending",
            "format": "gguf",
            "num_experts": config.model.num_experts,
            "num_layers": config.model.num_layers,
            "hidden_size": config.model.hidden_size or 896,
            "vocab_size": config.model.vocab_size or 151936
        },
        
        "@experts": {}
    }
    
    # Add experts with current learned biases
    print(f"\nExporting {len(config.experts)} experts:")
    for expert in config.experts:
        # Get current bias (learned or default)
        learned_bias = router.biases.get(expert.id, expert.routing_bias)
        
        xjson["@experts"][expert.id] = {
            "name": expert.name,
            "domain": expert.domain,
            "routing_bias": round(float(learned_bias), 4),
            "trainable": expert.trainable,
            "layer_start": expert.layer_start,
            "layer_end": expert.layer_end
        }
        
        bias_indicator = "↑" if learned_bias > expert.routing_bias else ("↓" if learned_bias < expert.routing_bias else "•")
        print(f"  {bias_indicator} {expert.name:15} ({expert.domain:15}): {learned_bias:+.4f}")
    
    # Add skills
    print(f"\nExporting {len(config.skills)} skills:")
    for skill in config.skills:
        key = f"@skills.{skill.id.replace('skill-', '')}"
        xjson[key] = {
            "id": skill.id,
            "name": skill.name,
            "enabled": skill.enabled,
            "priority": round(skill.priority, 2),
            "trigger": skill.trigger,
            "action": skill.action,
            "experts": [
                expert.id for expert in config.experts 
                if expert.trainable or any(kw in expert.domain for kw in skill.trigger.lower().split('|'))
            ]
        }
        status = "✓" if skill.enabled else "✗"
        print(f"  {status} {skill.name:25} priority={skill.priority:.2f}")
    
    # Add agent configuration
    xjson["@agent.main"] = {
        "id": config.agent.id,
        "name": config.agent.name,
        "persona": config.agent.persona,
        "system_prompt": config.agent.system_prompt,
        "temperature": config.agent.temperature,
        "max_tokens": config.agent.max_tokens,
        "active_skills": [s.id for s in config.skills if s.enabled],
        "preferred_experts": [
            e.id for e in sorted(
                config.experts, 
                key=lambda e: abs(router.biases.get(e.id, 0)), 
                reverse=True
            )[:3]
        ]
    }
    
    # Add memory
    if config.memory:
        xjson["@agent.main.memory"] = {
            "preferred_language": config.memory.preferred_language,
            "last_topic": config.memory.last_topic,
            "user_style": "concise",
            "persist_learning": config.memory.persist_learning
        }
    
    # Add learned biases
    learned = {
        expert_id: round(float(bias), 4) 
        for expert_id, bias in router.biases.items() 
        if abs(bias) > 0.001
    }
    xjson["@agent.main.learned"] = learned
    print(f"\nLearned biases: {len(learned)} values")
    for expert_id, bias in sorted(learned.items(), key=lambda x: abs(x[1]), reverse=True):
        expert = router.get_expert_by_id(expert_id)
        print(f"  {expert.name:15}: {bias:+.4f}")
    
    # Add state
    xjson["@agent.main.state"] = {
        "interaction_count": config.agent.interaction_count,
        "last_modified": datetime.now().isoformat(),
        "export_version": "1.0"
    }
    
    # Add routing config
    xjson["@moe.router"] = {
        "mode": "hybrid",
        "top_k": config.model.top_k_experts,
        "temperature": config.agent.temperature,
        "domain_keywords": Router.DOMAIN_KEYWORDS
    }
    
    # Write XJSON
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(xjson, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*70}")
    print(f"✓ Exported to: {output}")
    print(f"  Size: {output.stat().st_size / 1024:.1f} KB")
    print(f"  Experts: {len(config.experts)}")
    print(f"  Skills: {len(config.skills)}")
    print(f"  Learned biases: {len(learned)}")
    print(f"{'='*70}")
    
    # Show how to use it
    print(f"\nNext steps:")
    print(f"  1. Run C++ runtime: micronaut.exe --config {output}")
    print(f"  2. Or test with: atomizer.exe --input \"Your query here\"")
    print(f"  3. Or use unified pipeline: python micronaut_inference.py \"Your query\"")
    
    return xjson


if __name__ == '__main__':
    import sys
    
    # Default paths
    adapter = "qwen_micronaut_adapter.json"
    state = "qwen_micronaut_state.json"
    output = "src/models/micronaut_runtime.xjson"
    
    # Override from command line
    if len(sys.argv) > 1:
        adapter = sys.argv[1]
    if len(sys.argv) > 2:
        state = sys.argv[2]
    if len(sys.argv) > 3:
        output = sys.argv[3]
    
    export_router_to_xjson(adapter, state, output)
