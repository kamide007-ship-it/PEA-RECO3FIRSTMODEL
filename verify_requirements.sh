#!/bin/bash

echo "========================================="
echo "PWA Requirements Verification"
echo "========================================="

# 1) Check if all required files exist
echo ""
echo "✓ 1) Required Files:"
files=(
    "static/manifest.webmanifest"
    "static/service-worker.js"
    "static/icons/icon-192.png"
    "static/icons/icon-512.png"
    "static/favicon.ico"
)
for f in "${files[@]}"; do
    if [ -f "$f" ]; then
        echo "  ✅ $f"
    else
        echo "  ❌ $f MISSING"
    fi
done

# 2) Check app.py for required routes
echo ""
echo "✓ 2) app.py Routes:"
routes=(
    '/manifest.webmanifest'
    '/service-worker.js'
    '/favicon.ico'
)
for route in "${routes[@]}"; do
    if grep -q "def pwa.*:.*$route\|@app.get(\"$route\")" app.py; then
        echo "  ✅ Route $route exists"
    else
        echo "  ❌ Route $route MISSING"
    fi
done

# 3) Check reco3.html for manifest and theme-color
echo ""
echo "✓ 3) templates/reco3.html:"
if grep -q 'rel="manifest" href="/manifest.webmanifest"' templates/reco3.html; then
    echo "  ✅ Manifest link correct"
else
    echo "  ❌ Manifest link incorrect"
fi

if grep -q 'meta name="theme-color"' templates/reco3.html; then
    echo "  ✅ theme-color meta tag present"
else
    echo "  ❌ theme-color meta tag missing"
fi

# 4) Check service-worker registration
echo ""
echo "✓ 4) Service Worker Registration:"
if grep -q 'register("/service-worker.js")' templates/reco3.html; then
    echo "  ✅ Service worker registered from /service-worker.js"
else
    echo "  ❌ Service worker registration incorrect"
fi

echo ""
echo "========================================="
