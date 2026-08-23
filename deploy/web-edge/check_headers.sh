#!/usr/bin/env bash
# Comprueba CSP/cabeceras del sidecar web-edge contra stubs nginx.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
IMAGE="${WEB_EDGE_IMAGE:-personalhostel/web-edge:ci}"
NET="web-edge-ci-$$"
EDGE="${NET}-edge"
WN="${NET}-wn"
WC="${NET}-wc"
WM="${NET}-wm"

cleanup() {
  docker rm -f "$EDGE" "$WN" "$WC" "$WM" >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
}
trap cleanup EXIT

assert_has() {
  local haystack=$1 needle=$2
  if ! grep -Fiq -- "$needle" <<<"$haystack"; then
    echo "FAIL: falta '$needle'" >&2
    printf '%s\n' "$haystack" >&2
    exit 1
  fi
}

assert_missing() {
  local haystack=$1 needle=$2
  if grep -Fiq -- "$needle" <<<"$haystack"; then
    echo "FAIL: no debía aparecer '$needle'" >&2
    printf '%s\n' "$haystack" >&2
    exit 1
  fi
}

docker build --tag "$IMAGE" "$ROOT"

csp="$(docker run --rm \
  -e NEGOCIO_API_URL='https://negocio.siberia.solutions/v1' \
  -e CAMAREROS_API_URL='https://camareros.siberia.solutions' \
  "$IMAGE" print-csp)"
assert_has "$csp" "https://negocio.siberia.solutions"
assert_has "$csp" "https://camareros.siberia.solutions"
assert_missing "$csp" "/v1"

docker network create "$NET" >/dev/null
docker run -d --name "$WN" --network "$NET" --network-alias web-negocio nginx:1.27-alpine >/dev/null
docker run -d --name "$WC" --network "$NET" --network-alias web-camareros nginx:1.27-alpine >/dev/null
docker run -d --name "$WM" --network "$NET" --network-alias web-cfc nginx:1.27-alpine >/dev/null

docker run -d --name "$EDGE" --network "$NET" -p 19083:9083 \
  -e WEB_NEGOCIO_UPSTREAM=web-negocio:80 \
  -e WEB_CAMAREROS_UPSTREAM=web-camareros:80 \
  -e WEB_CFC_UPSTREAM=web-cfc:80 \
  -e NEGOCIO_API_URL=http://localhost:8082 \
  -e CAMAREROS_API_URL=http://localhost:8080 \
  "$IMAGE" >/dev/null

for _ in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:19083/health" >/dev/null; then
    break
  fi
  sleep 0.2
done
curl -sf "http://127.0.0.1:19083/health" >/dev/null

http_headers="$(curl -sI "http://127.0.0.1:19083/")"
assert_has "$http_headers" "X-Content-Type-Options: nosniff"
assert_has "$http_headers" "X-Frame-Options: DENY"
assert_has "$http_headers" "Referrer-Policy: strict-origin-when-cross-origin"
assert_has "$http_headers" "Permissions-Policy:"
assert_has "$http_headers" "Content-Security-Policy:"
assert_has "$http_headers" "http://localhost:8082"
assert_missing "$http_headers" "Strict-Transport-Security"

https_headers="$(curl -sI -H "X-Forwarded-Proto: https" "http://127.0.0.1:19083/")"
assert_has "$https_headers" "Strict-Transport-Security: max-age=31536000"
assert_missing "$https_headers" "includeSubDomains"

echo "web-edge headers OK"
