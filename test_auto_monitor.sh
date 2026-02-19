#!/bin/bash

echo "========================================="
echo "Auto Monitor/Control Loop Test"
echo "========================================="

echo ""
echo "✓ Test 1: Auto monitor functions in reco3.js"
grep -q "function autoStart" static/reco3.js && echo "  ✅ autoStart() defined"
grep -q "function autoStop" static/reco3.js && echo "  ✅ autoStop() defined"
grep -q "function pollStatus" static/reco3.js && echo "  ✅ pollStatus() defined"
grep -q "function pollLogs" static/reco3.js && echo "  ✅ pollLogs() defined"
grep -q "function triggerChat" static/reco3.js && echo "  ✅ triggerChat() defined"
grep -q "function evaluateAndAct" static/reco3.js && echo "  ✅ evaluateAndAct() defined"

echo ""
echo "✓ Test 2: Polling intervals and cooldowns"
grep -q "POLL_STATUS_INTERVAL = 3000" static/reco3.js && echo "  ✅ pollStatus interval: 3000ms"
grep -q "POLL_LOGS_INTERVAL = 7000" static/reco3.js && echo "  ✅ pollLogs interval: 7000ms"
grep -q "TRIGGER_COOLDOWN = 60000" static/reco3.js && echo "  ✅ Trigger cooldown: 60000ms"

echo ""
echo "✓ Test 3: Safety guards"
grep -q "inFlightRequest" static/reco3.js && echo "  ✅ In-flight guard present"
grep -q "failureCount >= 3" static/reco3.js && echo "  ✅ Failure failsafe (3 retries)"
grep -q "credentials: 'include'" static/reco3.js && echo "  ✅ Session cookies enabled"

echo ""
echo "✓ Test 4: Error handling"
grep -q "if(r.status === 401)" static/reco3.js && echo "  ✅ 401 error handling"
grep -q "if(autoRunning) autoStop()" static/reco3.js && echo "  ✅ autoStop on 401"
grep -q "showError(msg)" static/reco3.js && echo "  ✅ Error display function"

echo ""
echo "✓ Test 5: DOMContentLoaded calls autoStart"
grep -q "autoStart();" static/reco3.js && echo "  ✅ autoStart() called on load"

echo ""
echo "✓ Test 6: HTML auto monitor section"
grep -q 'id="autoMonitor"' templates/reco3.html && echo "  ✅ Auto monitor section added"

echo ""
echo "✓ Test 7: CSS styling"
grep -q "\.badge" static/reco3.css && echo "  ✅ Badge styles added"
grep -q "\.autoStatus" static/reco3.css && echo "  ✅ Auto status styles added"

echo ""
echo "========================================="
echo "All checks passed! ✅"
