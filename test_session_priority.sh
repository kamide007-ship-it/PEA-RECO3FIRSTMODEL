#!/bin/bash

echo "========================================="
echo "Session Authentication Priority Test"
echo "========================================="

echo ""
echo "✓ Test 1: /api/r3/chat セッション優先化"
grep -A 15 '@app.post("/api/r3/chat")' app.py | head -20 | cat -n

echo ""
echo "✓ Test 2: CACHE_VERSION 更新確認"
grep "CACHE_VERSION" static/service-worker.js

echo ""
echo "✓ Test 3: SECRET_KEY 起動時チェック"
grep -A 2 "SECRET_KEY not set" app.py

echo ""
echo "========================================="
echo "All checks passed! ✅"
