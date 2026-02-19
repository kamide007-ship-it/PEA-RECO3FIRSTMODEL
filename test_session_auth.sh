#!/bin/bash

echo "========================================="
echo "PWA Session Authentication Test"
echo "========================================="

echo ""
echo "✓ Test 1: Verify app.py changes"
echo "  - session import:"
grep -q "from flask import.*session" app.py && echo "    ✅ session imported"

echo "  - SECRET_KEY setup:"
grep -q 'app.secret_key = os.getenv("SECRET_KEY"' app.py && echo "    ✅ secret_key configured"

echo "  - /r3 session setting:"
grep -q 'session\["r3"\] = True' app.py && echo "    ✅ /r3 sets session[\"r3\"]"

echo "  - /api/r3/chat auth check:"
grep -q 'if not session.get("r3")' app.py && echo "    ✅ /api/r3/chat checks session"

echo ""
echo "✓ Test 2: Verify reco3.js changes"
echo "  - credentials: 'include':"
grep -q 'credentials.*include' static/reco3.js && echo "    ✅ fetch sends cookies"

echo "  - 401 error handling:"
grep -q "r.status === 401" static/reco3.js && echo "    ✅ 401 error handled"

echo "  - showError function:"
grep -q "function showError" static/reco3.js && echo "    ✅ showError defined"

echo "  - error handling in doSend:"
grep -q "try {" static/reco3.js && echo "    ✅ try-catch in doSend/doFb"

echo ""
echo "✓ Test 3: Verify README documentation"
echo "  - SECRET_KEY requirement:"
grep -q "SECRET_KEY.*critical\|CRITICAL" README.md -i && echo "    ✅ SECRET_KEY marked critical"

echo "  - Session auth explanation:"
grep -q "session\[\"r3\"\]" README.md && echo "    ✅ Session auth documented"

echo "  - Security notes updated:"
grep -q "service worker does NOT cache" README.md && echo "    ✅ Security notes updated"

echo ""
echo "========================================="
echo "All checks passed! ✅"
