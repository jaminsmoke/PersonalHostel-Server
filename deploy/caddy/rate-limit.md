# Rate limit en Caddy (borde Identity)

El Caddyfile de **TLS** vive en el VPS (`/etc/caddy/Caddyfile`) junto a la
landing `siberia.solutions`. Ese binario es **vanilla**: no se instala
`rate_limit` ahí.

El recorte de abuso lo aplica el sidecar `identity-edge` (Compose de
producción): Caddy 2.10 + módulo `github.com/mholt/caddy-ratelimit`, puertos
loopback `127.0.0.1:9080` (camareros) y `127.0.0.1:9082` (negocio). Bar,
Commander y las webs siguen usando `https://camareros.siberia.solutions` y
`https://negocio.siberia.solutions`.

`deploy_staging.py --validate-only` **no** cambia el Caddy del host. El
sidecar se levanta con el deploy real (`compose up` de prod). El `reverse_proxy`
del host se cambia a mano en Changelog.

## Flujo

```
cliente HTTPS
  → Caddy host vanilla (:443)
  → 127.0.0.1:9080 / :9082  (identity-edge, rate_limit)
  → identity-camareros:8080 / identity-negocio:8080
```

`:8080` / `:8082` en loopback siguen siendo las APIs (health de
`deploy_staging.py`, rollback). `:8081` interno no pasa por el borde.

## Caddyfile del host (Changelog)

En los site blocks de `camareros.siberia.solutions` y
`negocio.siberia.solutions`, apuntar el proxy al sidecar (no a 8080/8082):

```
# camareros.siberia.solutions
reverse_proxy 127.0.0.1:9080

# negocio.siberia.solutions
reverse_proxy 127.0.0.1:9082
```

Validar y recargar **sin** reconstruir el binario del host:

```bash
caddy validate --config /etc/caddy/Caddyfile
systemctl reload caddy
```

## Rollback

1. Devolver `reverse_proxy` a `127.0.0.1:8080` y `127.0.0.1:8082`.
2. `caddy validate` + `systemctl reload caddy`.
3. Opcional: `docker compose -f docker-compose.yml -f docker-compose.prod.yml stop identity-edge`.

La landing no se toca.

## Umbrales de borde (por `{client_ip}`, más holgados que Redis)

| Matcher | Eventos | Ventana |
|---|---|---|
| login (ambos oficios) | 20 | 1 min |
| registro (ambos oficios) | 10 | 1 min |
| refresh (ambos oficios) | 20 | 1 min |

No hay zona CFC: el NAT de terraza comparte IP; el cupo real es Redis por
token de mesa (30 / 10 min).

El 429 del sidecar es JSON `identity.rate_limited` + `Retry-After` (mismo
`detail` que la API).

## Imagen

`deploy/caddy/Dockerfile`: xcaddy `v2.10.2` + commit pineado del módulo.
UID 10001. CI: job `identity-edge` (build + `caddy validate`).
