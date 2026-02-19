#!/usr/bin/env python3
"""
Test script to verify API Key protection functionality

Tests:
A) API_KEY_MODE=enforce with API_KEY set → 401 without key, 200 with correct key
B) /r3 and /static/* are accessible without key
C) Incorrect key → 401
D) API_KEY_MODE=off → key not required for /api/*
"""

import os
import sys
import json
import subprocess
from typing import Dict, Tuple, Any

def run_test_server(env_vars: Dict[str, str], timeout: int = 10) -> Tuple[str, int]:
    """Start Flask server with given environment variables and return output"""
    test_code = f"""
import os
import sys

# Set environment before imports
{chr(10).join([f"os.environ['{k}'] = '{v}'" for k, v in env_vars.items()])}

# Disable access logging
import logging
logging.getLogger('werkzeug').setLevel(logging.ERROR)

from app import app

# Use test client
with app.test_client() as client:
    # Test cases will be performed here
    # We'll use stdout to communicate results
    print("SERVER_READY")
    sys.stdout.flush()

    # Keep server "running" for testing
    import time
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
"""

    # Start server in background
    proc = subprocess.Popen(
        [sys.executable, "-c", test_code],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={**os.environ, **env_vars}
    )

    return proc

def test_api_endpoints() -> bool:
    """Test API endpoints with various API key configurations"""
    print(f"\n{'='*70}")
    print("TEST A: API_KEY_MODE=enforce & API_KEY set")
    print(f"{'='*70}")

    test_code = """
import os
os.environ["API_KEY"] = "test-secret-key-12345"
os.environ["API_KEY_MODE"] = "enforce"
os.environ["API_KEY_HEADER"] = "X-API-Key"

from app import app

client = app.test_client()

# Test 1: No key → 401
resp = client.get("/api/status")
assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
data = resp.get_json()
assert data.get("error") == "unauthorized", f"Expected 'unauthorized', got {data}"
print("✅ /api/status without key → 401")

# Test 2: Correct key → 200
resp = client.get("/api/status", headers={"X-API-Key": "test-secret-key-12345"})
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
data = resp.get_json()
assert "api_key_protection" in data, "Missing api_key_protection in response"
assert data["api_key_protection"]["enabled"] == True, "api_key_protection.enabled should be true"
print("✅ /api/status with correct key → 200")

# Test 3: Wrong key → 401
resp = client.get("/api/status", headers={"X-API-Key": "wrong-key"})
assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"
print("✅ /api/status with wrong key → 401")

print("\\n✅ Test A PASSED")
"""

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"❌ Test failed:\n{result.stderr}")
        return False

    return True

def test_public_paths() -> bool:
    """Test that public paths don't require authentication"""
    print(f"\n{'='*70}")
    print("TEST B: Public paths accessible without key")
    print(f"{'='*70}")

    test_code = """
import os
os.environ["API_KEY"] = "test-secret-key"
os.environ["API_KEY_MODE"] = "enforce"

from app import app

client = app.test_client()

# Test /r3 (PWA page)
resp = client.get("/r3")
assert resp.status_code == 200, f"/r3 should be public, got {resp.status_code}"
print("✅ GET /r3 (no key) → 200")

# Test /health
resp = client.get("/health")
assert resp.status_code == 200, f"/health should be public, got {resp.status_code}"
print("✅ GET /health (no key) → 200")

# Test / (root)
resp = client.get("/", follow_redirects=False)
assert resp.status_code in (200, 302), f"GET / should work, got {resp.status_code}"
print("✅ GET / (no key) → 200/302")

print("\\n✅ Test B PASSED")
"""

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"❌ Test failed:\n{result.stderr}")
        return False

    return True

def test_api_key_mode_off() -> bool:
    """Test that API_KEY_MODE=off disables authentication"""
    print(f"\n{'='*70}")
    print("TEST D: API_KEY_MODE=off (auth disabled)")
    print(f"{'='*70}")

    test_code = """
import os
os.environ["API_KEY"] = ""  # No key set
os.environ["API_KEY_MODE"] = "off"

from app import app

client = app.test_client()

# Test /api/status without key should work in "off" mode
resp = client.get("/api/status")
assert resp.status_code == 200, f"Expected 200 in off mode, got {resp.status_code}"
data = resp.get_json()
assert data["api_key_protection"]["enabled"] == False, "Should be disabled"
print("✅ /api/status without key (mode=off) → 200")

print("\\n✅ Test D PASSED")
"""

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"❌ Test failed:\n{result.stderr}")
        return False

    return True

def test_api_key_protection_status() -> bool:
    """Test that /api/status returns api_key_protection info"""
    print(f"\n{'='*70}")
    print("TEST C: /api/status response includes api_key_protection")
    print(f"{'='*70}")

    test_code = """
import os
os.environ["API_KEY"] = "test-key-xyz"
os.environ["API_KEY_MODE"] = "enforce"
os.environ["API_KEY_HEADER"] = "X-API-Key"

from app import app
import json

client = app.test_client()

# Get status with valid key
resp = client.get("/api/status", headers={"X-API-Key": "test-key-xyz"})
assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"

data = resp.get_json()

# Check api_key_protection structure
assert "api_key_protection" in data, "Missing api_key_protection"
api_protection = data["api_key_protection"]

assert "enabled" in api_protection, "Missing enabled"
assert "mode" in api_protection, "Missing mode"
assert "header" in api_protection, "Missing header"

assert api_protection["enabled"] == True, "Should be enabled"
assert api_protection["mode"] == "enforce", f"Expected enforce, got {api_protection['mode']}"
assert api_protection["header"] == "X-API-Key", f"Expected X-API-Key, got {api_protection['header']}"

# Ensure API key is NOT exposed
response_str = json.dumps(data)
assert "test-key-xyz" not in response_str, "API key should not be exposed!"

print("✅ api_key_protection.enabled = True")
print("✅ api_key_protection.mode = 'enforce'")
print("✅ api_key_protection.header = 'X-API-Key'")
print("✅ API key not exposed in response")

print("\\n✅ Test C PASSED")
"""

    result = subprocess.run(
        [sys.executable, "-c", test_code],
        capture_output=True,
        text=True
    )

    print(result.stdout)
    if result.returncode != 0:
        print(f"❌ Test failed:\n{result.stderr}")
        return False

    return True

def main():
    print("\n" + "="*70)
    print("RECO3 API Key Protection Test Suite")
    print("="*70)

    results = []

    # Run tests
    results.append(("Test A: enforce mode with correct/wrong keys", test_api_endpoints()))
    results.append(("Test B: Public paths without auth", test_public_paths()))
    results.append(("Test C: api_key_protection in response", test_api_key_protection_status()))
    results.append(("Test D: API_KEY_MODE=off", test_api_key_mode_off()))

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
