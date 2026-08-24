#!/bin/sh
set -eu

origin_from_url() {
	printf '%s\n' "$1" | sed -E 's#^(https?://[^/?#]+).*#\1#'
}

NEGOCIO_API_URL=${NEGOCIO_API_URL:-http://localhost:8082}
CAMAREROS_API_URL=${CAMAREROS_API_URL:-http://localhost:8080}
WEB_NEGOCIO_UPSTREAM=${WEB_NEGOCIO_UPSTREAM:-web-negocio:8080}
WEB_CAMAREROS_UPSTREAM=${WEB_CAMAREROS_UPSTREAM:-web-camareros:8080}
WEB_CFC_UPSTREAM=${WEB_CFC_UPSTREAM:-web-cfc:8080}

negocio_origin=$(origin_from_url "$NEGOCIO_API_URL")
camareros_origin=$(origin_from_url "$CAMAREROS_API_URL")
api_origins="$negocio_origin"
if [ "$camareros_origin" != "$negocio_origin" ]; then
	api_origins="$negocio_origin $camareros_origin"
fi

export WEB_NEGOCIO_UPSTREAM WEB_CAMAREROS_UPSTREAM WEB_CFC_UPSTREAM
export CSP_HEADER="default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; script-src 'self'; style-src 'self'; font-src 'self'; img-src 'self' data: blob: ${api_origins}; connect-src 'self' ${api_origins}"

if [ "${1:-}" = "print-csp" ]; then
	printf '%s\n' "$CSP_HEADER"
	exit 0
fi

exec "$@"
