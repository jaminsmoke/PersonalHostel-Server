# Caddy 2.10.2 + mholt/caddy-ratelimit (commit pineado). No sustituye
# /usr/bin/caddy del host: este binario solo vive en el sidecar Identity.
FROM caddy:2.11.9-builder-alpine@sha256:646fee578e680989ca5c7fd1ce6f1de574d19fd71ef2221810cc0510a9f40c86 AS builder

RUN xcaddy build v2.10.2 \
	--with github.com/mholt/caddy-ratelimit@5625512f24f6f59d6f64fb3aafe5eecff0b286db

FROM caddy:2.11.8-alpine@sha256:f6228111e5fafa1a5238258d0858e103f10599b8d1659a146e7726681a002bb9

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
COPY Caddyfile identity-rate-limit.caddy /etc/caddy/

RUN apk add --no-cache wget \
	&& addgroup -g 10001 -S identity \
	&& adduser -u 10001 -S -G identity identity \
	&& mkdir -p /data /config \
	&& chown -R identity:identity /etc/caddy /data /config

USER 10001:10001

EXPOSE 9080 9082

CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
