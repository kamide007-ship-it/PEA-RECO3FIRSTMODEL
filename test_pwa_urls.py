#!/usr/bin/env python3
"""Test script to verify all PWA-related URLs return 200"""

import os
import sys

# Set minimal env for testing
os.environ["API_KEY_MODE"] = "off"

from app import app

def test_pwa_urls():
    """Test all required PWA URLs return 200"""
    client = app.test_client()

    test_urls = [
        # Pages
        ("/r3", "PWA main page"),
        ("/", "Root redirect"),

        # Root-level PWA files
        ("/manifest.webmanifest", "Manifest from root"),
        ("/service-worker.js", "Service Worker from root"),
        ("/favicon.ico", "Favicon from root"),

        # Static-level PWA files (backward compatibility)
        ("/static/manifest.webmanifest", "Manifest from static"),
        ("/static/service-worker.js", "Service Worker from static"),

        # Icons
        ("/static/icons/icon-192.png", "Icon 192x192"),
        ("/static/icons/icon-512.png", "Icon 512x512"),

        # Static CSS/JS
        ("/static/base.css", "Base CSS"),
        ("/static/reco3.css", "RECO3 CSS"),
        ("/static/reco3.js", "RECO3 JS"),

        # Health
        ("/health", "Health check"),
    ]

    results = []
    max_len = max(len(url) for url, _ in test_urls)

    print(f"\n{'='*70}")
    print("PWA URLs Test")
    print(f"{'='*70}\n")

    for url, description in test_urls:
        response = client.get(url, follow_redirects=False)
        status = response.status_code

        # 200 or 302 (redirect) is acceptable
        is_ok = status in (200, 302)
        symbol = "✅" if is_ok else "❌"

        results.append((url, status, is_ok))

        print(f"{symbol} {status:3d} | {url:<{max_len}} | {description}")

    # Summary
    passed = sum(1 for _, _, ok in results if ok)
    total = len(results)

    print(f"\n{'='*70}")
    print(f"Result: {passed}/{total} URLs working")
    print(f"{'='*70}\n")

    if passed == total:
        print("🎉 All PWA URLs are accessible!")
        return 0
    else:
        print("❌ Some URLs failed:")
        for url, status, ok in results:
            if not ok:
                print(f"   {status:3d} {url}")
        return 1

if __name__ == "__main__":
    sys.exit(test_pwa_urls())
