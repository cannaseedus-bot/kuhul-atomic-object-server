#!/usr/bin/env python3
"""
Qwen2.5 Micronaut Demo

Demonstrates the Micronaut adapter system with Qwen2.5-0.5B-Instruct model.

Usage:
    python demo_qwen_micronaut.py
    
    # Or with custom inputs
    python demo_qwen_micronaut.py "Write a Python function" "Debug this error"
"""

import sys
import json
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from micronaut_adapter import AdapterLoader, Router


def print_header(text: str, char: str = "=", width: int = 80) -> None:
    """Print formatted header"""
    # Use ASCII-safe characters for Windows console compatibility
    print("\n" + char * width)
    print(f" {text}")
    print(char * width)


def print_expert_selection(input_text: str, experts: list, router: Router) -> None:
    """Print expert selection results"""
    print(f"\nInput: \"{input_text}\"")
    print("\nExpert Selection:")
    print(f"{'Expert':<18} {'Domain':<18} {'Probability':>12} {'Confidence'}")
    print("-" * 60)
    
    for expert_id, prob in experts:
        expert = router.get_expert_by_id(expert_id)
        if expert:
            confidence_bar = "#" * int(prob * 20)
            print(f"{expert.name:<18} {expert.domain:<18} {prob:>12.3f} {confidence_bar}")


def demo_routing(router: Router, test_inputs: list[str]) -> None:
    """Demonstrate expert routing"""
    print_header("MICRONAUT EXPERT ROUTING DEMO")
    
    for input_text in test_inputs:
        experts = router.select_experts(input_text)
        print_expert_selection(input_text, experts, router)
    
    print("\n" + "=" * 80)


def demo_learning(router: Router) -> None:
    """Demonstrate preference learning"""
    print_header("PREFERENCE LEARNING DEMO")
    
    # Initial routing
    input_text = "Write a Python script to parse JSON"
    print(f"\n1. Initial routing for: \"{input_text}\"")
    experts_before = router.select_experts(input_text)
    print_expert_selection(input_text, experts_before, router)
    
    # Simulate user feedback (user prefers Python expert)
    print("\n2. User feedback: Python expert was helpful! (+1.0 reward)")
    router.update_bias('exp-1', reward=1.0, learning_rate=0.1)
    
    # Routing after learning
    print("\n3. Routing after learning:")
    experts_after = router.select_experts(input_text)
    print_expert_selection(input_text, experts_after, router)
    
    # Show bias changes
    print("\nLearned Biases:")
    for expert_id, bias in sorted(router.biases.items()):
        if abs(bias) > 0.01:
            expert = router.get_expert_by_id(expert_id)
            print(f"  {expert.name:<15}: {bias:+.3f}")
    
    print("\n" + "=" * 80)


def demo_domain_hints(router: Router) -> None:
    """Demonstrate explicit domain hints"""
    print_header("EXPLICIT DOMAIN HINTS DEMO")
    
    input_text = "Optimize this loop for performance"
    
    # Without domain hint
    print(f"\nInput: \"{input_text}\"")
    print("\n1. Automatic routing (no hint):")
    experts_auto = router.select_experts(input_text)
    print_expert_selection(input_text, experts_auto, router)
    
    # With domain hint
    print(f"\n2. With domain_hint='cpp_code':")
    experts_cpp = router.select_experts(input_text, domain_hint='cpp_code')
    print_expert_selection(input_text, experts_cpp, router)
    
    print(f"\n3. With domain_hint='python_code':")
    experts_python = router.select_experts(input_text, domain_hint='python_code')
    print_expert_selection(input_text, experts_python, router)
    
    print("\n" + "=" * 80)


def demo_skill_triggers(router: Router) -> None:
    """Demonstrate skill trigger matching"""
    print_header("SKILL TRIGGER DEMO")
    
    config = router.config
    skills = config.skills
    
    print("\nAvailable Skills:")
    for skill in skills:
        status = "✅" if skill.enabled else "❌"
        print(f"  {status} {skill.name:<25} Priority: {skill.priority:.2f}")
        print(f"      Triggers: {skill.trigger}")
        print(f"      Action: {skill.action}")
    
    # Test trigger matching
    test_phrases = [
        "Write code for me",
        "I have a bug in my code",
        "Can you explain this?",
        "How can I improve this?",
        "I need unit tests"
    ]
    
    print("\nTrigger Matching:")
    for phrase in test_phrases:
        print(f"\n  Phrase: \"{phrase}\"")
        matched = []
        for skill in skills:
            triggers = skill.trigger.split('|')
            for trigger in triggers:
                if trigger.strip().lower() in phrase.lower():
                    matched.append(skill)
                    break
        
        if matched:
            print(f"  Matched skills: {', '.join(s.name for s in matched)}")
        else:
            print(f"  No direct match (using default routing)")
    
    print("\n" + "=" * 80)


def save_state(router: Router, state_path: Path) -> None:
    """Save learned state"""
    router.save_state(state_path)
    print(f"\nState saved to: {state_path}")


def load_state(router: Router, state_path: Path) -> bool:
    """Load learned state"""
    if state_path.exists():
        router.load_state(state_path)
        print(f"\nState loaded from: {state_path}")
        return True
    return False


def main():
    print_header("QWEN2.5 MICRONAUT ADAPTER DEMO")
    
    # Configuration paths
    adapter_path = Path(__file__).parent / "qwen_micronaut_adapter.json"
    state_path = Path(__file__).parent / "qwen_micronaut_state.json"
    
    # Note: Using JSON config (BSON requires pymongo library)
    # To use BSON: pip install pymongo
    
    # Check if adapter config exists
    if not adapter_path.exists():
        print(f"Adapter config not found: {adapter_path}")
        print("\nRun this first:")
        print("  python -m gguf.micronaut create-adapter --config qwen_micronaut_adapter.json --output qwen_micronaut_adapter.json")
        sys.exit(1)
    
    # Load adapter configuration
    print(f"\nLoading adapter: {adapter_path}")
    config = AdapterLoader.load(adapter_path)
    
    # Validate
    is_valid, errors = AdapterLoader.validate(config)
    if not is_valid:
        print("Validation errors:")
        for error in errors:
            print(f"  - {error}")
        sys.exit(1)
    
    print(f"Adapter loaded successfully!")
    print(f"   ID: {config.id}")
    print(f"   Version: {config.version}")
    print(f"   Experts: {len(config.experts)}")
    print(f"   Skills: {len(config.skills)}")
    print(f"   Agent: {config.agent.name}")
    
    # Create router
    router = Router(config)
    
    # Load previous state if exists
    if load_state(router, state_path):
        print("\n📊 Current learned biases:")
        for expert_id, bias in router.biases.items():
            if abs(bias) > 0.01:
                expert = router.get_expert_by_id(expert_id)
                print(f"   {expert.name}: {bias:+.3f}")
    
    # Get test inputs from command line or use defaults
    if len(sys.argv) > 1:
        test_inputs = sys.argv[1:]
    else:
        test_inputs = [
            "Write a Python function to sort a list",
            "Debug this segmentation fault in C++",
            "Explain how async/await works",
            "How do I create a React component?",
            "Optimize this database query",
            "Write unit tests for this function",
            "What's the time complexity of quicksort?",
            "Help me write a README file"
        ]
    
    # Run demos
    demo_routing(router, test_inputs)
    demo_learning(router)
    demo_domain_hints(router)
    demo_skill_triggers(router)
    
    # Save learned state
    save_state(router, state_path)
    
    # Print summary
    print_header("DEMO SUMMARY")
    print(f"""
Successfully demonstrated:
   - Expert routing with {len(config.experts)} experts
   - Preference learning with reward updates
   - Explicit domain hints
   - Skill trigger matching
   - State persistence

Files:
   - Adapter config: {adapter_path}
   - State file: {state_path}

Next steps:
   - Integrate with llama.cpp for actual inference
   - Add embedding-based routing
   - Implement GPU-accelerated routing
   
Documentation:
   - README: README_MICRONAUT.md
   - Routing: micronaut_routing_algorithm.md
   - Analysis: micronaut_adapter_analysis.md
""")


if __name__ == '__main__':
    main()
