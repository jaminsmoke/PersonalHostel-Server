# web-edge — cabeceras de las webs públicas

Sidecar Caddy **vanilla** (sin módulos extra) delante de `web-negocio`,
`web-camareros` y `web-cfc`. El Caddy del host sigue sin plugins: solo cambia
el `reverse_proxy` a loopback `9083` / `9084` / `9085`.

No confundir con `deploy/caddy/` (`identity-edge`, rate_limit de las APIs).

## Flujo

```
cliente HTTPS
  → Caddy host vanilla (:443)
  → 127.0.0.1:9083 / :9084 / :9085  (web-edge, CSP + cabeceras)
  → web-negocio|web-camareros|web-cfc:8080
```

En Compose local, `localhost:8083/8084/8085` publica **web-edge** (mismo DX).
En prod, nginx sigue en `127.0.0.1:8083-8085` (rollback) y el borde en
`127.0.0.1:9083-9085`.

HSTS solo si llega `X-Forwarded-Proto: https`. HTTP local no lo emite.
`includeSubDomains` no se usa (el host es `web.*`, no el apex).

La CSP se arma en `entrypoint.sh` con los orígenes de `NEGOCIO_API_URL` y
`CAMAREROS_API_URL` (las mismas env que `config.js`).

## Caddyfile del host (Changelog)

En los site blocks de las webs, apuntar el proxy al sidecar (no a 8083-8085):

```
# web.negocio.siberia.solutions
reverse_proxy 127.0.0.1:9083

# web.camareros.siberia.solutions
reverse_proxy 127.0.0.1:9084

# web.mesa.siberia.solutions
reverse_proxy 127.0.0.1:9085
```

Validar y recargar **sin** reconstruir el binario del host:

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

`deploy_staging.py --validate-only` **no** cambia el Caddy del host.

## Rollback

1. Devolver `reverse_proxy` a `127.0.0.1:8083`, `:8084` y `:8085`.
2. `caddy validate` + `systemctl reload caddy`.
3. Opcional: `docker compose -f docker-compose.yml -f docker-compose.prod.yml stop web-edge`.

La landing no se toca.

## Imagen

`deploy/web-edge/Dockerfile`: Caddy 2.10.2 alpine pineada por digest. UID 10001.
CI: job `web-edge` (build + `caddy validate` + `check_headers.sh`).
