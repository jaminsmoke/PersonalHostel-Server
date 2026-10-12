# Caddy 2.10.2 + mholt/caddy-ratelimit (commit pineado). No sustituye
# /usr/bin/caddy del host: este binario solo vive en el sidecar Identity.
FROM caddy:2.11.6-builder-alpine@sha256:096ec6e825e219175bd5be64b5e7a4000977f701a2bcaab825621d9fb1e1154b AS builder

RUN xcaddy build v2.10.2 \
	--with github.com/mholt/caddy-ratelimit@5625512f24f6f59d6f64fb3aafe5eecff0b286db

FROM caddy:2.11.7-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f

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
