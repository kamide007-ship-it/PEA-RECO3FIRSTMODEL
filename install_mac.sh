#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

echo "[1/10] Python3 check"
command -v python3 >/dev/null 2>&1 || { echo "python3 not found"; exit 1; }

echo "[2/10] venv"
python3 -m venv .venv
source .venv/bin/activate

echo "[3/10] install deps"
pip install -U pip
pip install -r requirements.txt

echo "[4/10] permissions"
mkdir -p instance
chmod 700 instance || true

mkdir -p "$HOME/.reco3"
chmod 700 "$HOME/.reco3" || true

echo "[5/10] .env + api key"
API_KEY="reco3_$(python - <<'PY'
import secrets
print(secrets.token_hex(24))
PY
)"
cat > .env <<EOF
RECO3_ENABLED=1
RECO3_APP_URL=http://127.0.0.1:5001
RECO3_TARGET=https://api.openai.com
RECO3_PROXY_PORT=8100
RECO3_API_KEY=${API_KEY}
EOF
chmod 600 .env || true

echo "[6/10] certs (optional)"
mkdir -p certs
chmod 700 certs || true
if command -v openssl >/dev/null 2>&1; then
  openssl req -x509 -newkey rsa:2048 -keyout certs/key.pem -out certs/cert.pem -days 365 -nodes -subj "/CN=localhost" >/dev/null 2>&1 || true
  chmod 600 certs/*.pem || true
fi

echo "[7/10] run tests"
pytest tests/ -q

echo "[8/10] start scripts"
cat > start.sh <<'EOF'
#!/bin/bash
set -euo pipefail
source .venv/bin/activate
python app.py
EOF
chmod +x start.sh

cat > start_agent.sh <<'EOF'
#!/bin/bash
set -euo pipefail
source .venv/bin/activate
python -m reco3_agent daemon start --port 8100 --bind 127.0.0.1
echo "Agent started. Use: python -m reco3_agent daemon status"
EOF
chmod +x start_agent.sh

echo "[9/10] done"
echo "Run: ./start.sh   (App: http://localhost:5001, RECO3: http://localhost:5001/r3)"
echo "Run: ./start_agent.sh (Agent proxy on 8100)"
