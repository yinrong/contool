#!/bin/bash
# Local end-to-end test: starts mock LLM, relay server, and tunnel client,
# then sends a test request through the full chain.
set -e

export RELAY_PORT=8443
export RELAY_ADDR=127.0.0.1
export RELAY_TLS=true

cd "$(dirname "$0")"

# 确保证书存在
if [ ! -f certs/server.crt ]; then
    echo "生成测试证书..."
    python gen_cert.py
fi

cleanup() {
    echo "Cleaning up..."
    kill $PID_MOCK $PID_RELAY $PID_TUNNEL 2>/dev/null || true
    wait $PID_MOCK $PID_RELAY $PID_TUNNEL 2>/dev/null || true
}
trap cleanup EXIT

echo "=== Starting mock LLM server (port 9000) ==="
python mock_llm.py &
PID_MOCK=$!
sleep 1

echo "=== Starting relay server (port 8443, TLS) ==="
python relay_server.py &
PID_RELAY=$!
sleep 2

echo "=== Starting tunnel client ==="
python tunnel_client.py &
PID_TUNNEL=$!
sleep 3

echo ""
echo "=== Test 1: Camouflage website ==="
echo "GET / should return the static site:"
curl -sk https://127.0.0.1:8443/ | head -5
echo ""

echo "=== Test 2: Unauthenticated API (should get 404) ==="
HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" -X POST https://127.0.0.1:8443/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"hello"}]}')
echo "HTTP status: $HTTP_CODE (expect 404)"

echo ""
echo "=== Test 3: Authenticated non-stream request ==="
curl -sk https://127.0.0.1:8443/v1/chat/completions \
  -H "Authorization: Bearer sk-contool-default-token-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"hello world"}]}'
echo ""

echo ""
echo "=== Test 4: Authenticated stream request ==="
curl -sk https://127.0.0.1:8443/v1/chat/completions \
  -H "Authorization: Bearer sk-contool-default-token-change-me" \
  -H "Content-Type: application/json" \
  -d '{"model":"test","messages":[{"role":"user","content":"hello stream"}],"stream":true}'
echo ""

echo ""
echo "=== All tests complete ==="
