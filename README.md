# PersonalHostel Server

Servidor de **identidad** de la familia **PersonalHostel**.  
Repo: https://github.com/jaminsmoke/PersonalHostel-Server  
Carpeta local: `PersonalHosteleriaServer`

No es el nodo de sala: eso es [Personal Bar](https://github.com/jaminsmoke/PersonalBar).

Release actual: **[v0.2](https://github.com/jaminsmoke/PersonalHostel-Server/releases/latest)** (`0.2.0` en OpenAPI). Changelog: [`docs/changelog.md`](docs/changelog.md).

Mapa de producto y **flujo kanban completo** (Detectado → Changelog, Debate, CLI): [`AGENTS.md`](AGENTS.md). Setup corto de la CLI: [`tools/README.md`](tools/README.md).

## Dos servicios, dos bases de datos

Desde el split de dominios, Identity se despliega como **dos servicios** con **bases de datos separadas**:

| Servicio | Puerto | BD | Dominio |
|---|---|---|---|
| `identity-camareros` | **8080** | `identity_camareros` | Identidad profesional: `camareros`, `credenciales`, `app_config` |
| `identity-negocio` | **8082** | `identity_negocio` | Negocio: cuentas, establecimientos, catálogo, sync/conflictos, membresías, invitaciones y outbox |

Ambos comparten dos secretos inyectados por la orquestación (`SESSION_SECRET` y
`QR_SIGNING_KEY`) para que los JWT y el QR `phid1` funcionen entre servicios. Las
consultas que cruzan la frontera (buscar/verificar camarero, establecimientos de
un camarero) van por un **cliente interno** (`/internal/*` en `:8081`) con dos transportes:
`direct` (tests) y `http` (Compose/VPS).

- Camareros (identidad profesional): rutas `/v1/camareros/*`, `/v1/auth/login`, `/v1/keys/qr` → `:8080`.
- Negocio: rutas `/v1/auth/negocio/*`, `/v1/establecimientos/*`, `/v1/invitaciones/*` → `:8082`.
- `GET /health` y `GET /v1/meta` existen en ambos.

## Levantar en local (Docker) — DEPRECADO

> **El flujo de desarrollo Docker local ya no es soportado.** La verificación
> oficial de ítems es `deploy_staging.py --validate-only` en el Docker del VPS y
> la validación de calidad/migraciones corre en CI (GitHub Actions). El Compose
> sigue vivo como **orquestación de CI y del VPS**, no como vía de desarrollo.
> La sección se conserva solo para experimentación aislada; cualquier uso
> productivo o de verificación debe pasar por el VPS.

```bash
cd PersonalHosteleriaServer
copy .env.example .env
docker compose up --build
```

- Camareros (API profesionales): http://localhost:8080/health
- Negocio (cuentas y establecimientos): http://localhost:8082/health
- Web del profesional: http://localhost:8084 (ficha pública por QR, login y bandeja de invitaciones; el magic-link vive en /invitaciones/<token>)
- CFC (pedido en mesa): http://localhost:8085 (`/m/<token>`; `/m/demo` es demostración local)
- Postgres: `localhost:5432` (usuario `hosteleria`; bases `identity_camareros` y `identity_negocio`)
- Redis: `localhost:6379` (cuotas; en prod no se publica)
- Esquema: aplicado por Alembic al arrancar; una cadena por BD (`alembic` para camareros, `alembic_negocio` para negocio)

## Despliegue en staging (VPS)

El staging es producción en configuración (HTTPS, secretos reales, datos borrables). Corre en el VPS de Hostinger (la IP vive en `.env`, no en este README), detrás del **Caddy** ya instalado (que también sirve la landing `siberia.solutions`).

El cliente de despliegue usa una dependencia fijada: `pip install -r
services/identity/requirements-deploy.txt`.

- Subdominios: `camareros.siberia.solutions` (API `:8080` vía borde `:9080`), `negocio.siberia.solutions` (API `:8082` vía borde `:9082`), `ficha.siberia.solutions` (histórico con 301), `web.negocio.siberia.solutions` (:8083, web pública de negocios: plantilla Estate Hospitality por slug), `web.camareros.siberia.solutions` (:8084, web del profesional: credencial, login e invitaciones) y `web.mesa.siberia.solutions` (:8085, CFC: pedir desde el QR de mesa).
- `docker-compose.prod.yml` es un override que publica las APIs/web solo en `127.0.0.1` y deja Postgres y Redis sin puerto externo (Caddy expone 80/443; UFW solo abre 22/80/443).
- Recorte de abuso en el borde: sidecar `identity-edge` ([`deploy/caddy/`](deploy/caddy/rate-limit.md)). El Caddy del host sigue vanilla; en Changelog el `reverse_proxy` de las APIs apunta a `127.0.0.1:9080` / `:9082`. `--validate-only` no cambia el Caddyfile del host.
- El `.env` de producción vive en `/opt/identity/.env` (gitignored, `root:root`
  y modo `0600`): secretos reales + `ALLOW_NON_REAL_DATA=false` + URLs públicas.
  El override productivo no admite fallbacks secretos y el despliegue ejecuta
  un preflight sanitizado antes de fetch/build/migraciones. Inventario,
  recuperación y rotación: [`security/secrets.md`](security/secrets.md).

```bash
# Solo secretos/configuración remota: no hace fetch, build ni cambios en VPS
python services/identity/scripts/deploy_staging.py --preflight-only

# Validación oficial: Docker del VPS + BD `_test`, sin recrear el stack activo
python services/identity/scripts/deploy_staging.py --ref feature/mi-rama --validate-only

# Deploy tras una validación verde
python services/identity/scripts/deploy_staging.py --ref feature/mi-rama

# E2E público desde Docker del VPS; crea y elimina su propia cuenta sintética
python services/identity/scripts/deploy_staging.py --ref feature/mi-rama --smoke-profile
```

Los agentes no usan Docker local para verificar ítems. `--validate-only` ejecuta
Ruff, formato, contrato OpenAPI, los tests con cobertura y el ciclo reversible
de ambas cadenas Alembic dentro del VPS. También ejecuta el self-test del
detector de contratos de familia. El runner no se rompe por `__pycache__` root
en el checkout: Python no escribe bytecode (guarda `PYTHONDONTWRITEBYTECODE=1`
en el Dockerfile, `backup_staging.sh` y los comandos host-side de
`deploy_staging.py` — ítem #112, cerrado), porque un `__pycache__` con permisos
de root rompía `ruff format --check` del runner aislado. Las bases activas no se
modifican en esta fase. El despliegue normal fija las URLs públicas canónicas de ficha/carta
en el `.env` remoto sin mostrar secretos, crea un backup de ambas BD antes de
migrar y termina comprobando health/meta de los dos servicios.

- Backup diario: `services/identity/scripts/backup_staging.sh` crea en
  `/opt/identity/backups` un conjunto atómico con dumps custom de ambas BD,
  fotos y manifiesto SHA-256; conserva siete días sin borrar nunca el último
  conjunto válido. `backup_restore.py restore-drill` solo admite bases con
  sufijo `_restore_test`, valida referencias/fotos y elimina las copias al
  terminar. La copia externa aprobada usa Cloudflare R2 + restic, pero permanece
  apagada hasta completar el bootstrap, la descarga verificada y la custodia
  separada de la clave (ver `security/backups.md`).
- Caddyfile del host: bloques `reverse_proxy` en `/etc/caddy/Caddyfile` (la landing queda intacta). Tras #182 las APIs van a `:9080`/`:9082` (`identity-edge`); rollback a `:8080`/`:8082`. Webs: `:8083` `web.negocio`, `:8084` `web.camareros`, `:8085` `web.mesa`. Los dominios históricos `ficha.siberia.solutions` y `carta.siberia.solutions` responden 301 (`/ficha?qr=` → `web.camareros…/camareros?qr=`; `/negocio` y `/carta` → `web.negocio`). El bloque de `web.mesa` se añade en el VPS al publicar CFC; no reutilizar `carta.siberia.solutions` ni `pedir.*`.

### Observabilidad en el VPS (staging/producción)

Las APIs exponen `/metrics` en el listener interno `:8081` (Prometheus lo raspa
por la red Docker; Caddy no publica ese puerto) y un access log JSON por request. El stack de observabilidad se levanta **solo** en el VPS, apilando un tercer fichero. El deploy (`deploy_staging.py` sin `--validate-only`) lo restaura al final con el wrapper; `validate-only` **no** lo toca.

```bash
# En el VPS (/opt/identity) — preferir el wrapper (anti-orphan)
bash services/identity/scripts/obs_up.sh up

# Equivalente explícito
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  -f docker-compose.observability.yml up -d \
  prometheus alertmanager grafana loki alloy \
  node-exporter postgres-exporter

# Restore servicio a servicio (si se reintrodujo tras un borrado)
bash services/identity/scripts/obs_up.sh up prometheus
bash services/identity/scripts/obs_up.sh up node-exporter postgres-exporter
bash services/identity/scripts/obs_up.sh up alertmanager
bash services/identity/scripts/obs_up.sh up loki alloy
bash services/identity/scripts/obs_up.sh up grafana
```

**Anti-orphan:** no ejecutes `docker compose down` ni limpies “orphans” con solo `docker-compose.yml` + `docker-compose.prod.yml`. Sin el tercer `-f`, Docker marca la pila de obs como huérfana y un down la borra (los volúmenes `prometheus-data` / `grafana-data` / `loki-data` se conservan si no pasas `-v`). Usa siempre `obs_up.sh` o los tres `-f`.

- Piezas: **Prometheus** (métricas + reglas de alerta), **Grafana** (dashboards), **Loki + Alloy** (logs de contenedores), **node_exporter** (host), **postgres_exporter** (BD) y **Alertmanager** (email).
- Acceso: Grafana en `https://grafana.siberia.solutions` con `basic_auth` de Caddy + login propio (`127.0.0.1:3001` en el host). `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` viven en `.env`.
- **UIs internas (admin)**: Prometheus (`:9090`), Alertmanager (`:9093`) y Grafana (`:3001`) solo escuchan en `127.0.0.1` del VPS. Para navegarlas desde tu máquina sin abrir puertos públicos, usar el lanzador de túnel SSH:
  ```bash
  python services/identity/scripts/obs_tunnel.py        # abre túnel + navegador
  python services/identity/scripts/obs_tunnel.py --no-browser
  ```
  Lee `.env` (misma clave pinned anti-MITM que `deploy_staging.py`). Pulsa Ctrl+C para cortar.
- Alertas: `up == 0`, 5xx, Postgres caído, CPU alta, disco bajo y backup R2 ausente/antiguo → email a `ALERTMANAGER_ROUTE_TO` (usa el SMTP de `EMAIL_*`).
- Comprobaciones rápidas: `curl -sf 127.0.0.1:9090/-/healthy`, `127.0.0.1:9093/-/healthy`, `127.0.0.1:3001/api/health`; targets Prometheus UP; `curl -I https://grafana.siberia.solutions` → 401 sin auth.
- Smoke sintético (no load test):
  ```bash
  CAMAREROS_API_URL=https://camareros.siberia.solutions \
  NEGOCIO_API_URL=https://negocio.siberia.solutions \
  k6 run services/identity/scripts/k6/smoke.js
  ```
- Fuera de alcance por ahora: cadvisor (evita montar `/var/run/docker.sock`) y tracing distribuido OTel.

## Cuentas de prueba canónicas (seed)

Para probar login y flujos cross de la familia se usan dos cuentas canónicas con `data_origin=real` (staging rechaza test/demo):

- Camarero: `camarero.test@example.com` (nick `camarero_test`)
- Negocio: `negocio.test@example.com` (`Negocio Test`, tipo `bar`)

```bash
# Staging (vía recomendada): apuntando a los subdominios HTTPS
CAMAREROS_API_URL=https://camareros.siberia.solutions \
NEGOCIO_API_URL=https://negocio.siberia.solutions \
python services/identity/scripts/seed_test_accounts.py

# Dev local (legacy, solo experimentación aislada): alta idempotente de las dos cuentas
python services/identity/scripts/seed_test_accounts.py
```

Las contraseñas viven en `.env` (gitignored); re-ejecutar el seed es seguro (409 → se omite).

## Seguridad de CI y cadena de suministro

Los PR y `main` ejecutan tres checks requeridos: `quality`, `integration` y
`security`. El tercero audita dependencias Python, workflows, Dockerfiles,
configuración e imágenes; genera SARIF y un SBOM SPDX por runtime Identity y
PostgreSQL. Las acciones se fijan por SHA, las bases Docker por
digest y los servicios de aplicación se ejecutan sin root.

La política, los umbrales y el formato de excepciones con caducidad están en
[`security/README.md`](security/README.md). Dependabot cubre pip, Docker, Compose
y GitHub Actions. CodeQL usa el default setup de GitHub para Python. En local,
la ruta soportada sigue siendo `docker compose up --build`.

Para migrar volúmenes `fotos` creados por versiones antiguas, Compose ejecuta
una tarea efímera `fotos-permissions` como root que solo ajusta ownership y
termina. Las APIs nunca heredan ese usuario: arrancan después como UID/GID 10001.

## API v1

### OpenAPI y contrato versionado

- Camareros (staging): https://camareros.siberia.solutions/docs · https://camareros.siberia.solutions/openapi.json
- Negocio (staging): https://negocio.siberia.solutions/docs · https://negocio.siberia.solutions/openapi.json
- Local legacy (solo experimentación): http://localhost:8080/docs · http://localhost:8082/docs
- `info.version` = `0.2.0` en ambos (tag GitHub **v0.2**).
- Specs versionados en git: [`docs/openapi-camareros.json`](docs/openapi-camareros.json) y [`docs/openapi-negocio.json`](docs/openapi-negocio.json). Se regeneran con:

  ```bash
  python services/identity/scripts/export_openapi.py          # escribe docs/openapi-*.json
  python services/identity/scripts/export_openapi.py --check  # falla si difieren del vivo
  ```

- El job requerido `quality` de `.github/workflows/quality-check.yml` falla si
  algún spec commiteado no coincide con el generado (anti-drift).

### Errores y códigos estables

Toda respuesta de error lleva `detail` (mensaje en español) y `code` (código estable para que los clientes ramifiquen sin parsear el mensaje):

```json
{ "detail": "Clave revocada. Renueva la clave", "code": "identity.credential_revoked" }
```

| HTTP | `code` | Cuándo |
|---|---|---|
| 401 | `identity.credenciales_invalidas` | Login con email/password incorrectos |
| 401 | `identity.token_invalido` | Bearer faltante, inválido o caducado |
| 409 | `identity.email_ya_registrado` | Registro con email ya existente |
| 409 | `identity.credential_revoked` | Cuenta sin credencial activa |
| 422 | `identity.validation_error` | Cuerpo inválido (`detail` es lista de mensajes) |
| 422 | `identity.procedencia_no_permitida` | El entorno bloquea altas `test/demo` |
| 422 | `identity.procedencia_incompatible` | Un vínculo mezclaría raíces de distinta procedencia |
| 429 | `identity.rate_limited` | Cuota de login, registro, upload o POST CFC superada (`Retry-After`) |
| 503 | `identity.rate_limit_unavailable` | Redis caído en una ruta con cuota |

### Registro de profesional

`POST /v1/camareros/registro` (servicio `:8080`)

```json
{
  "nombre": "Ana",
  "apellidos": "García",
  "email": "ana@example.com",
  "telefono": "+34600000000",
  "password": "contraseña-mín-8",
  "nick": "Anita",
  "data_origin": "real"
}
```

`telefono` y `nick` son opcionales (`nick`: 1–40 caracteres; mote visible en barra/colas). Commander lo exige en el alta; Bar lo consume y no lo edita. `password` es obligatoria (mín. 8 caracteres); solo se guarda su hash argon2 con salt, nunca en claro ni en las respuestas. Respuesta `201`:

```json
{
  "id": "<uuid del camarero>",
  "data_origin": "real",
  "qr": "phid1:<camarero_id>:<credencial_id>:<firma-ed25519>",
  "ficha_url": "https://ficha.example/camareros?qr=phid1:..."
}
```

- `ficha_url` es la URL pública de la credencial del camarero (configurable con `FICHA_URL_BASE`; en el VPS apunta a `web.camareros.siberia.solutions`); los clientes pueden emitir el QR como esta URL para que escanearlo abra la web.
- La verificación del QR acepta tanto `phid1:...` como `https://...?qr=phid1:...`.
- `data_origin` es opcional y vale `real` por defecto. `test` y `demo` solo se
  admiten cuando el servidor tiene `ALLOW_NON_REAL_DATA=true`; en el VPS debe
  permanecer `false`. Es linaje inmutable, no un rol ni una autorización.
- `409` si el email ya está registrado; `422` con mensajes en español si hay campos inválidos.
- El `qr` se liga a la **credencial activa**: formato `phid1` (versionado), firmado con Ed25519 sobre `phid1:<camarero_id>:<credencial_id>`. Bar verifica offline con la clave pública; el secreto real de la credencial vive en Postgres (`credenciales.secreto`), no en el QR.
- Clave de firma: `QR_SIGNING_KEY` (base64) si existe; si no, se genera y persiste en `app_config` (local).

### Login (recupera la misma identidad y el mismo QR)

`POST /v1/auth/login` (servicio `:8080`)

```json
{
  "email": "ana@example.com",
  "password": "contraseña-mín-8"
}
```

Respuesta `200`:

```json
{
  "token": "<jwt>",
  "camarero": {
    "id": "<uuid>",
    "nombre": "Ana",
    "apellidos": "García",
    "email": "ana@example.com",
    "telefono": "+34600000000",
    "nick": "Anita",
    "data_origin": "real"
  },
  "qr": "phid1:<camarero_id>:<credencial_id>:<firma-ed25519>",
  "ficha_url": "https://ficha.example/camareros?qr=phid1:..."
}
```

- El `qr` es el de la **credencial activa**: tras reinstalar (sin renovar), login → misma identidad y mismo QR. `ficha_url` acompaña siempre al `qr`.
- `401` con `Email o contraseña incorrectos` si el email no existe, la password no cuadra o el camarero aún no tiene password.
- `409` con `Clave revocada. Renueva la clave` si la cuenta no tiene credencial activa.
- `429` `identity.rate_limited` si se supera el cupo por IP o por email (`Retry-After`).
- Login y registro devuelven `token` (JWT access, 12 h por defecto), `refresh_token`, `expires_in` y `sesion_id`. `POST /v1/auth/refresh` rota el refresh.
- `GET /v1/camareros/me/sesiones` lista las sesiones; `POST .../sesiones/{id}/revocar` cierra una; `POST .../sesiones/revocar` cierra las demás. Homólogos en `/v1/auth/negocio/...`.
- JWT HS256 con `jti`. Access: `SESSION_ACCESS_HOURS` (default 12) o fallback `SESSION_TTL_DAYS`. Refresh: `SESSION_REFRESH_DAYS` (default 30). Secreto `SESSION_SECRET`.

### Perfil y QR de la sesión

- `GET /v1/camareros/me` → perfil del camarero (`Authorization: Bearer <token>`). Incluye `nick`, `direccion` y `ciudad` (`null` si no informados).
- `PATCH /v1/camareros/me` (body parcial, p. ej. `{ "nick": "Anita", "direccion": "Calle Mayor 1", "ciudad": "Madrid" }`) → actualiza los campos enviados (al menos uno). Solo la sesión del profesional.
- `GET /v1/camareros/me/qr` → `{ "qr": "phid1:..." }` (QR de la credencial activa).
- `GET /v1/camareros/me/establecimientos` → establecimientos activos del profesional (el servicio de camareros consulta al de negocio internamente).
- `GET /v1/camareros/me/invitaciones` → bandeja de invitaciones dirigidas al email del profesional (estado derivado `expirada` para pendientes vencidas).
- `POST /v1/camareros/me/invitaciones/{id}/aceptar` → acepta una invitación por id (verifica titularidad).
- `POST /v1/camareros/me/invitaciones/{id}/rechazar` → rechaza una invitación pendiente propia; el negocio la ve como `rechazada` al instante.
- `/me/qr` devuelve `409` si no hay credencial activa.

### Visibilidad y ficha pública por QR

Cada camarero controla qué campos de su ficha son **públicos**. Por defecto solo
`nombre`, `apellidos` y `nick` son visibles; `email`, `telefono`, `direccion`,
`ciudad` y `foto` son privados (opt-in).

- `GET /v1/camareros/me/visibilidad` (`Authorization: Bearer <token>`) →
  `{ "nombre": true, "apellidos": true, "nick": true, "email": false, "telefono": false, "direccion": false, "ciudad": false, "foto": false }`.
- `PUT /v1/camareros/me/visibilidad` (body parcial, p. ej. `{ "email": true }`) →
  actualiza solo los campos enviados; el resto queda igual.
- `PUT /v1/camareros/me/visibilidad-establecimientos` (body `{ "visible": "..." }`)
  → preferencia del camarero sobre **aparecer en el directorio de otros
  establecimientos** (para invitación): `siempre | solo_libre | nunca` (default
  `nunca`, privacidad segura). Se gestiona desde Commander.
- `GET /v1/camareros/ficha?qr=<phid1>` → ficha **pública, sin token**: el QR
  verificado (firma Ed25519 + credencial activa) es la llave. Devuelve solo los
  campos visibles. `422 identity.qr_invalido` si el QR no es válido; `409
  identity.credencial_inactiva` si la credencial está revocada. Incluye
  `foto_url` (relativa) solo si `foto=true` y existe foto.
- `GET /v1/camareros/ficha/foto?qr=<phid1>` → sirve la foto **pública** (WebP)
  solo si `foto=true` y existe, con `Cache-Control: public` + `ETag`. Sin token;
  el QR es la llave. `404 identity.foto_inexistente` si no hay foto o no es
  visible; `422`/`409` igual que la ficha.
- La verificación del QR acepta tanto `phid1:...` como la URL
  `https://...?qr=phid1:...` (extrae el parámetro `qr`).

### Web pública del profesional (`web-camareros`)

`web-camareros` (SPA vanilla, nginx, puerto dev `:8084`) es la web pública del
profesional en `web.camareros.siberia.solutions/camareros?qr=`. Renderiza la
credencial del camarero (avatar/foto, nombre y apellidos, nick y campos de
contacto visibles) con una sola llamada al servicio de camareros
(`CAMAREROS_API_URL`):

- `GET /v1/camareros/ficha?qr=<phid1>` → ficha pública **sin token**, solo
  campos visibles (`visibilidad`): `nombre`, `apellidos`, y `nick`, `email`,
  `telefono`, `direccion`, `ciudad` y `foto_url` si son visibles. QR inválido →
  `422`, credencial revocada/renovada → `409`. Origen autorizado por CORS en el
  servicio de camareros (`IDENTITY_WEB_ORIGIN`); la URL canónica la fija
  `FICHA_URL_BASE` en `.env` (respuestas de registro/login/me/qr).

`web-camareros` (SPA vanilla, nginx, puerto dev `:8084`) sirve la web personal
del profesional: ficha pública por QR, login (JWT) y bandeja de invitaciones.
El magic-link `/invitaciones/<token>` (aceptar/rechazar sin JWT) llama al
servicio de negocio (`NEGOCIO_API_URL`; staging:
`https://web.camareros.siberia.solutions/invitaciones`).

Compatibilidad con los dominios históricos: `ficha.siberia.solutions` responde
**301** a la superficie canónica (`/ficha?qr=` → `web.camareros.siberia.solutions/camareros?qr=`; `/negocio` → `web.negocio.siberia.solutions`) y `carta.siberia.solutions` → `web.negocio` para que los QR emitidos antes de la migración sigan funcionando; el plazo de convivencia es de 6 meses desde el despliegue o hasta confirmar que no quedan QR impresos en uso.

### Web pública de negocios (`web-negocio`)

`web-negocio` (React + Vite + Tailwind compilado, nginx, puerto dev `:8083`) es la
web pública del establecimiento en `web.negocio.siberia.solutions/negocios/<slug>`.
Una sola plantilla Estate Hospitality para todos los locales; los datos salen
del slug. Páginas reales (no un one-pager con hashes):

- `/negocios/<slug>` — inicio (hero + nosotros)
- `/negocios/<slug>/horario`
- `/negocios/<slug>/carta` — tabs Cocina/Barra si hay ambos destinos
- `/negocios/<slug>/equipo`
- `/negocios/<slug>/contacto` — mapa de plantilla (stub) + datos reales si existen
- `/negocios/<slug>/galeria`

Nav y páginas están **siempre** visibles. Cada sección (`inicio`, `horario`,
`carta`, `equipo`, `contacto`) tiene su propio plano de ambiente: catálogo
Estate en `/stubs/fondos/` o foto subida. La galería sigue siendo un álbum, no
un fondo. Los stubs no sustituyen datos: no hay platos, horarios, bios ni
direcciones inventados. Un mapa OSM real queda fuera de este entregable.
`index.html` y `config.js` se sirven con `Cache-Control: no-store` para que un
QR de Bar no pinte un bundle hashed anterior; `/assets/` sigue `immutable`.

Los query/hash legacy (`?seccion=carta`, `#carta`) redirigen a la ruta nueva.
La SPA carga `GET /v1/negocio/web` y refetch (polling ~60 s y
`visibilitychange`) con `If-None-Match` contra el servicio de negocio
(`NEGOCIO_API_URL`, variable runtime inyectada por `20-web-negocio.sh`):

- `GET /v1/negocio/web?slug=<enlace>` → datos públicos agregados **sin token**:
  `establecimiento_id`, `nombre`, `tipo_establecimiento`, `logo_url`,
  `organizacion_nombre`, `plantilla`, `color_primario`, `perfil`, `contacto`,
  `hero`, `galeria`, `abierto_ahora`, `horario`, `equipo`, `categorias` (carta
  con `precio_centimos`, `moneda`, `destino` y `descripcion` opcional) y
  `fondos` (por slot: `fuente` `catalogo|upload|hero`, `id` de catálogo y `url`).
  El slug resuelve un enlace `web` o `carta` (slugs históricos `ficha_negocio`
  siguen sirviendo en GET); inexistente → `404`, revocado → `410`.
  `Cache-Control: public, max-age=0, must-revalidate` y `ETag`; si el cliente
  reenvía el mismo ETag → `304`. `GET /v1/negocio/ficha` se retiró.
- `GET /v1/negocio/web/logo?slug=<enlace>` → logo efectivo (WebP) público con
  cache `max-age=86400` + `ETag`, resoluble por cualquier slug del local.
- `GET /v1/negocio/web/hero?slug=<enlace>` y
  `GET /v1/negocio/web/galeria/{imagen_id}?slug=<enlace>` → hero y galería
  públicas (WebP) con cache `max-age=300`; `410 identity.web_privada` si la web
  está apagada.
- `GET /v1/negocio/web/fondo/{slot}?slug=<enlace>` → foto de fondo **subida**
  (`inicio|horario|carta|equipo|contacto`); el catálogo se sirve como estático
  en `web-negocio` (`/stubs/fondos/{id}.webp`).
- Si el establecimiento tiene `web_publica=false`, toda la superficie responde
  `410 identity.web_privada` con `Cache-Control: no-store`; el logo del local es
  branding público por diseño y se sirve siempre.

Ficha y carta llaman al servicio de negocio (`NEGOCIO_API_URL`); el origen web se
autoriza por CORS (`IDENTITY_WEB_ORIGIN`).

### Pedido en mesa (`web-cfc`)

`web-cfc` (React + Vite + Tailwind, nginx, puerto dev `:8085`) es la SPA del
comensal en `web.mesa.siberia.solutions/m/<token>`. Una sola implementación; el
token del QR identifica la mesa (la etiqueta B1/T3 es título, no credencial).
Diseño mobile-first vertical (Carta / Pedido / Cuenta) y parser de voz en
español al estilo Commander. El audio del micrófono no pasa por Identity: usa
la Web Speech API del navegador (en Chrome suele ser el motor del sistema; iOS
puede no tenerla — el tacto es el camino canónico).

Hasta que Bar abra jornada, `web-cfc` muestra carta y rechaza el POST con
`identity.cfc_cerrado`. Con jornada abierta consume `GET /v1/cfc/mesa/{token}/carta`,
`POST .../pedidos` y `GET .../cuenta`. `/m/demo` sigue siendo un catálogo local.
`WEB_CFC_URL_BASE` (VPS:
`https://web.mesa.siberia.solutions`) es la base de `url_publica`
(`…/m/<token>`). CORS incluye `http://localhost:8085` y
`https://web.mesa.siberia.solutions`.

### Foto de perfil

La foto se guarda normalizada a un único avatar **256×256 WebP** en un volumen Docker (`fotos`), con la metadata en `camareros`.

- `POST /v1/camareros/me/foto` (multipart, campo `foto`) → sube/reemplaza. JPEG/PNG/WebP, máx. 2 MB. Respuesta `200`: `{ "foto_url": "/v1/camareros/me/foto" }`. `422 identity.foto_invalida` si no es válido.
- `GET /v1/camareros/me/foto` → sirve WebP con `Cache-Control: private` y `ETag`. `404 identity.foto_inexistente` si no hay.
- `DELETE /v1/camareros/me/foto` → borra. Idempotente.
- La foto **no** viaja en el QR.

### Renovar y revocar la clave/QR

- `POST /v1/camareros/me/renovar` → revoca las credenciales activas y crea una nueva. Respuesta `200`: `{ "qr": "phid1:..." }`.
- `POST /v1/camareros/me/revocar` (body opcional `{ "motivo": "..." }`) → revoca la credencial activa **sin** crear otra. Respuesta `200`: `{ "status": "revocada" }`.

### Cambiar la contraseña

- `POST /v1/camareros/me/password` (body `{ "password_actual": "...", "password_nueva": "..." }`, mín. 8 máx. 128) → sustituye la contraseña de login. Respuesta `200`: `{ "status": "cambiada" }`. `401 identity.password_incorrecta` si la actual no cuadra.
- `POST /v1/auth/negocio/me/password` (mismo body) → cambio de contraseña de la cuenta de negocio. `401 identity.negocio_credenciales_invalidas` si la actual no cuadra.
- La credencial/QR **no** se ve afectada. Los JWT ya emitidos siguen siendo válidos hasta expirar (TTL 30 días); la sesión nueva se obtiene re-logando.

### Borrar cuenta (derecho de supresión)

- `DELETE /v1/camareros/me` (body `{ "password": "..." }`) → borra la cuenta de forma **irreversible**: camarero + credenciales (cascada) + foto. Respuesta `200`: `{ "status": "borrada" }`.
- Requiere re-autenticación: `401 identity.password_incorrecta` si la password no cuadra.

### Cuentas de negocio y establecimientos (v0.2, servicio `:8082`)

- `cuentas_negocio`: identidad y credencial de la organización propietaria.
- `establecimientos`: UUID canónico y perfil operativo/público de cada local.
  Nombre, tipo y logo pueden ser distintos entre locales del mismo titular; sin
  logo propio se hereda el logo corporativo.
- `membresias`: relación N:N entre camareros y establecimientos, con rol `dueno` o `staff`. El `camarero_id` es un **UUID plano** (la FK real vive en la otra BD).

Rutas principales:

- `POST /v1/auth/negocio/registro` y `POST /v1/auth/negocio/login` → alta y sesión de la cuenta de negocio. El registro acepta `tipo_establecimiento` opcional del catálogo `bar | restaurante | cafeteria | pub | copas`, `camarero_vinculado_id` (validado contra el servicio de camareros) y `data_origin` opcional (`real` por defecto). El login devuelve `cuenta` con `tipo_establecimiento`, `logo_url` y procedencia.
- `GET/PATCH /v1/auth/negocio/me` → consulta/edita el nombre de la organización.
  El tipo legado de la cuenta se conserva como default compatible; Bar edita el
  tipo real en el establecimiento.
- `POST /v1/auth/negocio/me/logo` (multipart, campo `logo`) → sube/reemplaza el logo (256×256 WebP, máx. 2 MB). `GET`/`DELETE` lo sirven/borran.
- `DELETE /v1/auth/negocio/me` → supresión de cuenta y establecimientos, sin borrar camareros.
- `POST /v1/establecimientos` y `GET /v1/establecimientos/mios` → crear y listar establecimientos propios; el alta acepta `tipo_establecimiento` y usa el default legado de la cuenta si se omite.
- `GET /v1/establecimientos/{id}` → consulta para la cuenta titular o un miembro activo. `PATCH` (solo titular) edita nombre/tipo/`visible_directorio` (opt-in del directorio de establecimientos, default `false`).
- `POST/GET/DELETE /v1/establecimientos/{id}/logo` → sobrescritura de logo por local. Al borrarla vuelve a heredarse el logo corporativo.
- `POST/GET/DELETE /v1/establecimientos/{id}/miembros...` → gestionar membresías.
- `GET /v1/keys/qr` → clave pública Ed25519 (en el servicio de camareros, `:8080`).
- `POST /v1/establecimientos/{id}/miembros/qr` → valida un QR (delegado al servicio de camareros) y crea la membresía.
- `GET /v1/establecimientos/{id}/camareros/buscar?email=...` → búsqueda exacta autorizada.
- `GET /v1/establecimientos/{id}/camareros/directorio?q=&limit=` → **directorio de
  camareros visibles para invitar**, **sin email** (privacidad). Solo camareros
  que han optado por ser vistos (`siempre` o `solo_libre`); **los dueños de
  establecimiento nunca aparecen** (pertenecen al dominio de establecimientos),
  y se excluyen los miembros del propio establecimiento y los de distinta
  `data_origin`. `libre` indica si el camarero no tiene membresía activa en
  ningún establecimiento; `foto_url` solo si la foto es pública (opt-in).
- `POST /v1/establecimientos/{id}/invitaciones` → crea una invitación. Acepta
  `email` (flujo clásico) **o** `camarero_id` (flujo por directorio: el email se
  resuelve en servidor y nunca se expone).
- `POST /v1/invitaciones/{token}/aceptar` → acepta con el JWT del camarero cuyo email coincide, **o** sin JWT (magic-link desde el email): token one-time + TTL 72h.
- `PUT/GET /v1/establecimientos/{id}/layout` → **copia de respaldo opaca del layout** del mapa que Bar sube y restaura en un dispositivo nuevo. Solo la cuenta de negocio dueña. El PUT exige `salas` y `mesas`; cualquier clave adicional (p. ej. `zonas`) se guarda en `documento` JSONB y se devuelve en el GET sin validar la forma. El PUT sustituye el snapshot completo.
- `PUT/GET /v1/establecimientos/{id}/mesas-cfc` y `POST .../mesas-cfc/{mesa_uuid}/rotar` → registro canónico de mesas públicas (cuenta titular). Bar envía el conjunto `{ mesa_uuid, etiqueta }`; Identity emite o revoca tokens. Idempotente: el mismo conjunto no rota. Cambiar etiqueta no rota. Baja = `410` inmediato; re-alta = token nuevo. `url_publica` usa `WEB_CFC_URL_BASE` (`…/m/<token>`).
- `GET /v1/cfc/mesa/{token}` → resolución pública **sin JWT**: `{ establecimiento_id, establecimiento_nombre, mesa_uuid, etiqueta, admite_pedidos, bar_en_linea }`. Inexistente → `404 identity.mesa_token_invalido`, revocado → `410 identity.mesa_token_revocado`. `Cache-Control: no-store`.
- `GET /v1/cfc/mesa/{token}/carta` y `GET .../cuenta` → carta (con `id` de producto) y líneas de la mesa en la jornada abierta. `POST .../pedidos` crea el pedido con snapshot de catálogo e idempotencia. Sin jornada, o con nodo ausente fuera de horario → `409 identity.cfc_cerrado`.
- `POST /v1/establecimientos/{id}/cfc/jornada/abrir|cerrar`, `PUT .../cfc/heartbeat`, `GET .../cfc/pedidos?cursor=`, `POST .../cfc/pedidos/{id}/ack` → bandeja autenticada de Bar (cuenta titular). Cerrar jornada caduca los `pendiente`. Identity no crea rondas.
- `POST/GET /v1/establecimientos/{id}/enlaces` y `POST .../enlaces/{enlace_id}/revocar|rotar` → enlaces públicos del establecimiento (solo la cuenta titular): `tipo` (`web | carta`) y `slug` opcional. `ficha_negocio` ya no se acepta en POST (422). Solo puede existir uno activo por tipo; crear es idempotente y rotar revoca el anterior. La respuesta incluye `url_publica`, construida con `WEB_NEGOCIO_URL_BASE` (`…/negocios/<slug>`, carta en `…/negocios/<slug>/carta`) para que Bar no hardcodee dominios.
- `GET /v1/establecimientos/{id}/fondos/catalogo` → catálogo Estate (`id`, `seccion`, `url` absoluta vía `WEB_NEGOCIO_URL_BASE`). `GET/PUT …/fondos` asigna por slot (`catalogo` o `null` para el default). `POST/GET/DELETE …/fondos/{slot}` sube, sirve o borra una foto propia. La UI del picker vive en Personal Bar.
- `GET /v1/enlaces/{slug}` → resolución pública **sin token**: devuelve `{ tipo, establecimiento_id }` con cache pública (`max-age=300`). Slug inexistente → `404`, revocado → `410`.
- `GET /v1/negocio/carta?slug=<enlace>` → carta pública **sin token**: productos disponibles agrupados por categoría, con `precio_centimos`, `moneda`, `destino` y `descripcion` opcional. Solo lectura; no expone `revision`. Enlace que no sea `carta` o inexistente → `404`, revocado → `410`.
- `GET /v1/negocio/web?slug=<enlace>` → datos agregados de la web pública **sin token** (perfil, carta y el resto de secciones en una llamada). El slug resuelve enlaces `web` o `carta` (y residuales `ficha_negocio`). Inexistente → `404`, revocado → `410`; cache `max-age=300`. `GET /v1/negocio/ficha` se retiró.
- `GET /v1/negocio/web/logo?slug=<enlace>` → logo efectivo público (WebP) por cualquier slug del local, cache `max-age=86400` + `ETag`.

El QR `phid1` no incorpora establecimientos. Las salas, el mapa y la lista blanca siguen siendo responsabilidad de Personal Bar.

### Catálogo canónico y mirrors offline

Identity es la fuente de verdad del catálogo. Room/SQLite en Bar, Commander y
clientes futuros son mirrors: sirven la última revisión confirmada cuando no hay
Internet y mantienen un outbox local para las intenciones creadas offline. Una
operación no puede aparecer en Identity hasta que el dispositivo recupere la red.

- `GET /v1/establecimientos/{id}/catalogo` → snapshot de productos activos +
  revisión global. La cuenta titular y los miembros activos pueden leerlo.
- `GET /v1/establecimientos/{id}/sync/cambios?desde=N` → change feed ordenado
  con snapshots y tombstones para actualizar el mirror.
- `POST /v1/establecimientos/{id}/sync/operaciones` → entrega una intención
  idempotente (`operation_id`, `device_id`, `base_revision`, timestamp cliente).
  En v0.2 implementa `producto` con `crear | actualizar | archivar`; solo la
  cuenta titular puede escribir.
- `GET /v1/establecimientos/{id}/sync/conflictos` y `POST .../{id}/resolver` →
  muestran estado base, estado canónico y propuesta; aceptar/rechazar vuelve a
  comprobar la revisión para no pisar cambios posteriores.
- `GET /v1/establecimientos/{id}/notificaciones` y `POST .../{id}/leer` → inbox
  durable para modal/bandeja de negocio. El payload incluye un deep-link lógico;
  FCM/APNs y la UI Android pertenecen a los repos de las apps.

El orden canónico se basa en revisiones asignadas por PostgreSQL y en el tiempo
de recepción del servidor. `client_created_at` se conserva para auditoría, pero
no gana conflictos por sí solo porque el reloj del dispositivo puede estar
desfasado. Los productos usan UUID estable, precio entero en céntimos, destino
explícito `barra | cocina` y archivado lógico.

La procedencia del establecimiento se hereda de su cuenta y la del producto se
hereda del establecimiento. Los clientes no pueden contradecirla ni cambiarla:
Bar/Commander solo declaran procedencia al crear la entidad raíz correspondiente.

### Invitaciones por navegador (magic-link)

El magic-link de invitación vive en `web-camareros` (`/invitaciones/<token>`): acepta o rechaza la invitación llamando al **servicio de negocio** (`NEGOCIO_API_URL`, default `http://localhost:8082`) con `POST /v1/invitaciones/{token}/aceptar` o `POST /v1/invitaciones/{token}/rechazar` (sin JWT). La bandeja autenticada (`GET /v1/camareros/me/invitaciones` + aceptar/rechazar por id) está en la misma web tras iniciar sesión.

## Tests

Los tests corren contra **bases de datos de prueba separadas** (`identity_camareros_test` y `identity_negocio_test`, creadas por `db-init`), no contra las de desarrollo. La verificación oficial es la validación remota (`deploy_staging.py --validate-only`) y el job `integration` de CI; el comando siguiente es solo una **reproducción local opcional** del runner:

```bash
docker compose run --rm identity-tests
```

El runner usa la etapa Docker `test`; las imágenes de ejecución usan `runtime` y
no contienen pytest, Ruff, informes ni el árbol `tests/`. Genera JUnit, cobertura
de ramas XML/HTML y un resumen Markdown en `build/reports/`. El umbral base es
**82%** y la cobertura actual es **82,71%**.

Hay health, esquema Postgres (dos BD), registro/login de camarero, perfil/QR,
foto de perfil, renovar, revocar, supresión GDPR, cuentas de negocio,
establecimientos, catálogo canónico, sync/conflictos, notificaciones,
membresías, clave pública QR, invitaciones (magic-link + CORS), espejo del
layout, outbox y OpenAPI (dos specs).

## Calidad y CI

El contrato común vive en `services/identity/pyproject.toml` y fija Python 3.14,
Ruff, pytest y cobertura. Reproducción local opcional del job `quality`
(la vía oficial es CI/VPS):

```bash
docker compose run --rm identity-tests ruff check app tests scripts
docker compose run --rm identity-tests ruff format --check app tests scripts
docker compose run --rm identity-tests python scripts/export_openapi.py --check
```

GitHub Actions ejecuta los checks tanto en pull requests como en `main`, cancela
ejecuciones obsoletas de la misma rama y usa permisos de solo lectura:

- `quality`: Ruff (lint y formato) + anti-drift OpenAPI.
- `integration`: Compose con PostgreSQL 16 + tests + cobertura de ramas +
  auditoría de procedencia. Conserva los informes 14 días.
- `family-contracts`: comprueba que los clientes de la familia (Bar,
  Commander, web-camareros, web-negocio y web-cfc) no piden operaciones (`método +
  path`) que Identity ya no expone. Sparse-checkout de los repos públicos Bar
  y Commander (refs `bar_ref`/`commander_ref`, default `main`; no ejecuta su
  código), barrido de `app.js`, `services/web-negocio/src` y
  `services/web-cfc/src`, e informe en el
  summary con las operaciones usadas, las públicas sin consumidor (aviso, no
  rojo) y los SHAs de la combinación. El job falla si un cliente llama un
  path ausente o un verbo no declarado. La normalización canónica es
  `normalize() → *` (`{param}`, `$var`, `${var}`). Artifact `family-manifest` (14 días). Reproducción local
  opcional:

  ```bash
  docker compose run --rm identity-tests python scripts/check_family_contracts.py --selftest
  ```
- `migrations-check`: valida la reversibilidad de ambas cadenas Alembic con
  el ciclo `upgrade head → downgrade base → upgrade head` sobre Postgres
  efímero. Reproducción local opcional:

  ```bash
  docker compose run --rm --entrypoint python identity-tests scripts/check_migrations.py
  ```

## Auditoría de procedencia (solo lectura)

Identity conserva `data_origin = real|test|demo` en camareros, cuentas,
establecimientos y productos. Las filas existentes se migran a `real`; el
sufijo histórico `Test` se usa solo para avisar de posibles incoherencias.

```bash
docker compose exec identity-camareros python -m app.data_audit
docker compose exec identity-camareros python -m app.data_audit --format json --fail-on-detected
```

El auditor consulta ambas BDs en transacciones read-only, redacta nombres y
emails, cuenta datos por procedencia y detecta linaje inconsistente o referencias
cross-DB huérfanas. Sale con `1` ante error y, con `--fail-on-detected`, con `2`
si encuentra datos no reales o incoherencias. `--show-pii` queda reservado para
revisión manual consciente y no se usa en CI. GitHub Actions valida el auditor
sobre PostgreSQL efímero; no tiene acceso al volumen local ni al VPS.

> Reproducción local opcional del job `integration` (vía oficial: CI/VPS):
>
> ```bash
> docker compose exec identity-camareros python -m app.data_audit
> docker compose exec identity-camareros python -m app.data_audit --format json --fail-on-detected
> ```
