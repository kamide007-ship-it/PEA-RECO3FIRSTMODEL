#!/usr/bin/env python3
"""
Test script to verify LLM adapter and model selection logic
Tests environment variable priority, AUTO_PREFERENCE, and /api/status response
"""

import os
import sys
import json
import subprocess
from typing import Dict, Any

def test_case(name: str, env_vars: Dict[str, str], expected_adapter: str, expected_model: str = None) -> bool:
    """Test a single configuration case"""
    print(f"\n{'='*70}")
    print(f"TEST: {name}")
    print(f"{'='*70}")

    # Build environment
    test_env = os.environ.copy()
    # Clear all relevant env vars first
    for key in ["LLM_ADAPTER", "OPENAI_API_KEY", "ANTHROPIC_API_KEY",
                "OPENAI_MODEL", "ANTHROPIC_MODEL", "AUTO_PREFERENCE"]:
        test_env.pop(key, None)

    # Set test variables
    for k, v in env_vars.items():
        test_env[k] = v
        print(f"  {k}={v}")

    # Run Python to import and test
    test_code = f"""
import os
import sys

# Set environment before any imports
{chr(10).join([f"os.environ['{k}'] = '{v}'" for k, v in env_vars.items()])}

# Now import modules
from reco2.orchestrator import get_orchestrator
from reco2.llm_adapter import _resolve_auto, create_adapter

# Get the orchestrator
orch = get_orchestrator()
adapter = orch.get_active_adapter()
model = orch.get_active_model()

print(f"active_llm_adapter={{adapter}}")
print(f"active_llm_model={{model}}")
"""

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True,
        env=test_env
    )

    output = result.stdout + result.stderr
    print("Output:")
    print(output)

    # Parse results
    success = True
    if f"active_llm_adapter={expected_adapter}" not in output:
        print(f"❌ FAILED: Expected adapter={expected_adapter}")
        success = False
    else:
        print(f"✅ Adapter: {expected_adapter}")

    if expected_model and f"active_llm_model={expected_model}" not in output:
        print(f"❌ FAILED: Expected model={expected_model}")
        success = False
    elif expected_model:
        print(f"✅ Model: {expected_model}")

    if result.returncode != 0:
        print(f"❌ Script failed with return code {result.returncode}")
        success = False

    return success


def test_api_status() -> bool:
    """Test /api/status endpoint returns correct LLM info"""
    print(f"\n{'='*70}")
    print("TEST: /api/status endpoint")
    print(f"{'='*70}")

    test_code = """
import os
os.environ["OPENAI_API_KEY"] = "test-openai-key-12345"
os.environ["ANTHROPIC_API_KEY"] = "test-anthropic-key-67890"
os.environ["LLM_ADAPTER"] = "anthropic"
os.environ["ANTHROPIC_MODEL"] = "claude-test-model"

from reco2.engine import get_status

status = get_status()

print("Status fields:")
print(f"  active_llm_adapter: {status.get('active_llm_adapter')}")
print(f"  active_llm_model: {status.get('active_llm_model')}")
print(f"  dual_keys: {status.get('dual_keys')}")

# Check that keys are not exposed
import json
status_json = json.dumps(status)

if 'test-openai-key-12345' in status_json or 'test-anthropic-key-67890' in status_json:
    print("\\n❌ FAILED: API keys exposed in status!")
    exit(1)

if 'has_openai_key' not in status_json or 'has_anthropic_key' not in status_json:
    print("\\n❌ FAILED: dual_keys not in status!")
    exit(1)

print("\\n✅ API keys properly hidden, dual_keys info present")
"""

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True
    )

    output = result.stdout + result.stderr
    print("Output:")
    print(output)

    if result.returncode != 0:
        print(f"❌ Test failed with return code {result.returncode}")
        return False

    return "✅ API keys properly hidden" in output


def main():
    print("\n" + "="*70)
    print("RECO3 LLM Configuration Test Suite")
    print("="*70)

    results = []

    # Test 1: OPENAI_API_KEY only
    results.append(("Test 1: OPENAI_API_KEY only", test_case(
        "OPENAI_API_KEY only",
        {"OPENAI_API_KEY": "test-key"},
        "openai",
        "gpt-4o"
    )))

    # Test 2: ANTHROPIC_API_KEY only
    results.append(("Test 2: ANTHROPIC_API_KEY only", test_case(
        "ANTHROPIC_API_KEY only",
        {"ANTHROPIC_API_KEY": "test-key"},
        "claude",  # "anthropic" normalizes to "claude"
        "claude-sonnet-4-5-20250929"
    )))

    # Test 3: Both keys + auto + AUTO_PREFERENCE=openai_first
    results.append(("Test 3: Both keys + openai_first", test_case(
        "Both keys + auto + AUTO_PREFERENCE=openai_first",
        {
            "OPENAI_API_KEY": "test-openai",
            "ANTHROPIC_API_KEY": "test-anthropic",
            "LLM_ADAPTER": "auto",
            "AUTO_PREFERENCE": "openai_first"
        },
        "openai"
    )))

    # Test 4: Both keys + auto + AUTO_PREFERENCE=anthropic_first (or default)
    results.append(("Test 4: Both keys + anthropic_first", test_case(
        "Both keys + auto + AUTO_PREFERENCE=anthropic_first",
        {
            "OPENAI_API_KEY": "test-openai",
            "ANTHROPIC_API_KEY": "test-anthropic",
            "LLM_ADAPTER": "auto",
            "AUTO_PREFERENCE": "anthropic_first"
        },
        "claude"  # "anthropic" normalizes to "claude"
    )))

    # Test 5: Explicit LLM_ADAPTER override
    results.append(("Test 5: Explicit LLM_ADAPTER=openai", test_case(
        "LLM_ADAPTER=openai with custom model",
        {
            "OPENAI_API_KEY": "test-key",
            "LLM_ADAPTER": "openai",
            "OPENAI_MODEL": "gpt-4o-mini"
        },
        "openai",
        "gpt-4o-mini"
    )))

    # Test 6: Explicit LLM_ADAPTER=anthropic with custom model
    results.append(("Test 6: Explicit LLM_ADAPTER=anthropic", test_case(
        "LLM_ADAPTER=anthropic with custom model",
        {
            "ANTHROPIC_API_KEY": "test-key",
            "LLM_ADAPTER": "anthropic",
            "ANTHROPIC_MODEL": "claude-3-opus-latest"
        },
        "claude",  # "anthropic" normalizes to "claude"
        "claude-3-opus-latest"
    )))

    # Test 7: /api/status endpoint
    results.append(("Test 7: /api/status endpoint", test_api_status()))

    # Summary
    print(f"\n{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}")

    for name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status}: {name}")

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    print(f"\n{passed_count}/{total_count} tests passed")

    if passed_count == total_count:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print("\n❌ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
