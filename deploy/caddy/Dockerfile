# Caddy 2.10.2 + mholt/caddy-ratelimit (commit pineado). No sustituye
# /usr/bin/caddy del host: este binario solo vive en el sidecar Identity.
FROM caddy:2.11.4-builder-alpine@sha256:7bac9be4072f7c4db2ccc7350750e0705004bf02da2ac7d96b1469ca4f28bb7c AS builder

RUN xcaddy build v2.10.2 \
	--with github.com/mholt/caddy-ratelimit@5625512f24f6f59d6f64fb3aafe5eecff0b286db

FROM caddy:2.11.4-alpine@sha256:5f5c8640aae01df9654968d946d8f1a56c497f1dd5c5cda4cf95ab7c14d58648

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
