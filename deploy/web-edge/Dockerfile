# Caddy vanilla (sin xcaddy). No sustituye /usr/bin/caddy del host.
FROM caddy:2.10.2-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d

COPY Caddyfile /etc/caddy/Caddyfile
COPY entrypoint.sh /entrypoint.sh

RUN apk add --no-cache wget \
	&& addgroup -g 10001 -S webedge \
	&& adduser -u 10001 -S -G webedge webedge \
	&& chmod 0755 /entrypoint.sh \
	&& mkdir -p /data /config \
	&& chown -R webedge:webedge /etc/caddy /data /config /entrypoint.sh

USER 10001:10001

ENV WEB_NEGOCIO_UPSTREAM=web-negocio:8080 \
	WEB_CAMAREROS_UPSTREAM=web-camareros:8080 \
	WEB_CFC_UPSTREAM=web-cfc:8080 \
	NEGOCIO_API_URL=http://localhost:8082 \
	CAMAREROS_API_URL=http://localhost:8080 \
	CSP_HEADER=default-src\ \'self\'

EXPOSE 9083 9084 9085

ENTRYPOINT ["/entrypoint.sh"]
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
