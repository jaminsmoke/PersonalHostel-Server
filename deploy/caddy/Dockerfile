# Caddy 2.10.2 + mholt/caddy-ratelimit (commit pineado). No sustituye
# /usr/bin/caddy del host: este binario solo vive en el sidecar Identity.
FROM caddy:2.10.2-builder-alpine@sha256:4cff3ae272ea05842adb4546e35961e4947aeea65f80fa1eb62a35b960e84971 AS builder

RUN xcaddy build v2.10.2 \
	--with github.com/mholt/caddy-ratelimit@5625512f24f6f59d6f64fb3aafe5eecff0b286db

FROM caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d

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
