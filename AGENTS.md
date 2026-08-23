# AGENTS.md — PersonalHostel Server

## Project

**PersonalHostel Server** is the **organization identity** server of the **PersonalHostel** family (Comander, Bar, Kitchen, TPV, this server). It stores the **permanent professional identity** (waiter / bar / kitchen): name, photo, QR/key. **It is not the LAN room node.** The host for tables and rounds is **Personal Bar**.

- GitHub repo: `jaminsmoke/PersonalHostel-Server`
- Local folder: `AndroidStudioProjects/PersonalHosteleriaServer` (sibling of `PersonalComander` and `PersonalBar`)
- Version target: **v0.3** (latest release **v0.2**, 2026-08-21 — `gh release list`; next version must be > latest)
- Verificación oficial: **Docker Compose en el VPS de staging**, con bases
  `identity_camareros_test` e `identity_negocio_test` aisladas. No levantar
  Docker local para validar ítems. Staging/producción: VPS de Hostinger (Caddy +
  subdominios `siberia.solutions`).

If you are the agent continuing here: read this **entire** file before writing code. Do not implement rankings, marketplace, or table/round sync.

## Familia PersonalHostel

Familia de producto de hostelería. Owner GitHub: [`jaminsmoke`](https://github.com/jaminsmoke) (cuenta personal). **No** es [SiberIA-Solutions](https://github.com/SiberIA-Solutions) (empresa de desarrollo). No hay organización GitHub de producto: los repos se agrupan con **esta tabla**.

**Al nacer un miembro nuevo** (Kitchen, TPV, …) se añade una fila aquí **en todos** los `AGENTS.md` de la familia.

| App | Repo | Oficio | Kanban |
|---|---|---|---|
| **Personal Comander** | [`jaminsmoke/PersonalComander`](https://github.com/jaminsmoke/PersonalComander) | App del camarero (móvil vertical): mesas, comanda, cuenta profesional | [Project 9](https://github.com/users/jaminsmoke/projects/9) |
| **Personal Bar** | [`jaminsmoke/PersonalBar`](https://github.com/jaminsmoke/PersonalBar) | Puesto del negocio (tablet apaisada): nodo LAN `:8787`, colas, lista blanca, mapa | [Project 11](https://github.com/users/jaminsmoke/projects/11) |
| **PersonalHostel Server** (este) | [`jaminsmoke/PersonalHostel-Server`](https://github.com/jaminsmoke/PersonalHostel-Server) | Registro canónico (Docker/VPS): camareros `:8080`, negocio `:8082` | [Project 10](https://github.com/users/jaminsmoke/projects/10) |

Kanban: cada app tiene el suyo. Cambio que necesite al otro lado → Detectado en **su** Project. Commander no llama a `:8082`.

## Stack (scaffold; the team may change it in Debate)

| Layer | Technology |
|---|---|
| API | Python 3.14 + FastAPI + Uvicorn |
| DB | PostgreSQL 16 |
| Cuotas | Redis 7 (sin persistencia; no se publica en prod) |
| Orchestration | Docker Compose |
| API ports | **8080** (camareros, API) · **8082** (negocio, API) · **8081** interno de cada contenedor (`/internal`, `/metrics`; no Caddy) · **9080/9082** loopback del sidecar `identity-edge` (prod; el host Caddy vanilla hace TLS) |
| Web ports | **8083** (web-negocio) · **8084** (web-camareros) · **8085** (web-cfc / mesa) · **9083/9084/9085** loopback del sidecar `web-edge` (prod; el host Caddy vanilla hace TLS; local Compose publica 8083-8085 en el borde) |
| Postgres port | **5432** (dev machine only) |
| Redis port | **6379** (dev machine only; prod solo red Docker) |

El Compose local sigue siendo reproducible para desarrollo manual, pero los
agentes validan mediante `deploy_staging.py --validate-only` en el VPS.

## Relación con el resto

```
[Identidad — este repo]          cuentas, QR permanente, foto, revocación
        ▲
        │ HTTPS (login / alta)
        │
[Personal Bar]  ◄──LAN──►  [Personal Comander…]
  nodo de sala                 clientes de mapa + comandas
  lista blanca del local       (hace falta QR dado de alta en Bar)
```

| Repo | Oficio | Red |
|---|---|---|
| **PersonalHostel-Server** (este) | Identidad de profesionales (y luego org/establecimiento) | Internet / VPS |
| Personal Bar | Expo barra + **nodo LAN** (mapa, rondas, tickets) | LAN del local |
| Personal Comander | Puesto de sala: mapa, tomar comanda, recoger | Cliente LAN de Bar; login contra este servidor |
| Personal Kitchen (futuro) | Tickets de comida | Cliente del nodo; login aquí |
| Personal TPV (futuro) | Cobro / contabilidad; puede heredar el nodo LAN | Login aquí |

Kanban de producto (Commander): ítem Detectado *Sala LAN: Personal Bar como nodo…* (`PVTI_lAHOBM87Yc4BgJWOzg2ZsaU`). Este servidor responde a la decisión: **QR permanente en base de datos de la org, no clave transitoria de dispositivo.** No reabrir ese ítem desde aquí.

## Esquema local de arquitectura (no versionado)

Si en este checkout existe `.architectureschema/`, es un grafo vivo **local**
(`graph.json` + visor). Está en `.gitignore` a propósito: no se sube hasta que
el modelo esté sólido. **Ilustra** nodos y aristas; **no sustituye** este
archivo ni el `README.md`. Si la carpeta no está, ignórala y sigue este
`AGENTS.md`. No commitear esa carpeta. No inventar sync de mesas/rondas ni
tratar el SQLite de las apps como fuente de verdad.

## Modelo de identidad (acordado)

1. El profesional **se registra** con nombre, apellidos, **nick** (mote visible en barra/colas), foto y otros datos. El nick lo gestiona Commander; Bar lo consume en referencias coloquiales y puede mostrar el resto de la ficha en la gestión del negocio.
2. El servidor emite una **clave / QR permanente** (equivalente a un DNI de oficio). Vive en **nuestra** base de datos, no solo en el móvil.
3. Desinstalar e instalar Commander o Bar + **login** recupera la misma identidad y el mismo QR.
4. **Revocación / renovación** posibles; si no, la clave no cambia.
5. En el local: el camarero enseña o pasa el QR a **Personal Bar** → Bar lo añade a la lista blanca de **esa** red. Sin alta, estar en el Wi‑Fi no basta para tomar pedidos.
6. Más adelante (otro ítem, no este scaffold): rankings por establecimiento, dueños que ven profesionales, contacto. La identidad fija es el cimiento; **no** diseñes UUIDs de usar-y-tirar.

PII: nombre, foto, identificador. GDPR, retención y borrado hay que pensarlo antes de producción. En Docker local no hay autenticación dura ni HTTPS.

## Qué hay ahora (v0.2)

```
PersonalHosteleriaServer/
├── AGENTS.md                 # este archivo (léelo primero)
├── README.md                 # cómo verificar en el VPS y contrato /v1
├── docker-compose.yml
├── deploy/caddy/             # sidecar identity-edge (rate_limit) + runbook del proxy del host
├── deploy/web-edge/          # sidecar web-edge (CSP y cabeceras; Caddy vanilla)
├── .env.example
├── .gitignore
├── .kanbanrc.json.template
├── docs/
│   ├── changelog.md          # changelog (v0.2 actual)
│   ├── openapi-camareros.json
│   └── openapi-negocio.json  # contratos OpenAPI versionados
├── .github/workflows/        # checks requeridos quality + integration + security
├── security/                 # política, excepciones caducables y documentación SBOM
├── services/identity/        # API FastAPI (identidad, QR, foto, OpenAPI)
│   ├── Dockerfile            # etapas runtime/test; producción sin tooling dev
│   ├── requirements.txt      # dependencias de ejecución
│   ├── requirements-dev.txt  # pytest, cobertura y Ruff
│   ├── pyproject.toml        # contrato Python 3.14, lint, formato y cobertura
│   ├── alembic/              # migraciones BD profesionales (incluye procedencia real/test/demo)
│   ├── alembic_negocio/      # migraciones BD negocio (incluye procedencia heredada y catálogo/sync)
│   ├── app/                  # main, auth, models, schemas, routes, storage, images
│   ├── scripts/              # export_openapi.py
│   └── tests/
├── services/web-negocio/     # web pública de negocios (React + Vite + Tailwind, nginx, :8083)
│   ├── Dockerfile            # multi-stage: node build → nginx estático
│   ├── nginx.conf
│   ├── 20-web-negocio.sh     # genera config.js en runtime (NEGOCIO_API_URL)
│   ├── package.json          # Vite/React/Tailwind; build = tsc --noEmit && vite build
│   └── src/                  # App, componentes, tipos y estilos (@fontsource, sin CDNs)
├── services/web-camareros/   # web del profesional: ficha, login e invitaciones (nginx + SPA vanilla, :8084)
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── 20-web-camareros.sh   # genera config.js en runtime (CAMAREROS_API_URL, NEGOCIO_API_URL)
│   └── static/               # index.html, style.css, app.js
├── services/web-cfc/         # CFC: pedir desde el QR de mesa (React + Vite + Tailwind, nginx, :8085)
│   ├── Dockerfile            # multi-stage: node build → nginx estático
│   ├── nginx.conf
│   ├── 20-web-cfc.sh         # genera config.js en runtime (NEGOCIO_API_URL)
│   ├── package.json          # Vite/React/Tailwind; test = vitest; build = tsc --noEmit && vite build
│   └── src/                  # App /m/:token, api de resolve, parser de voz, estilos mobile-first
└── tools/
    ├── README.md
    ├── kanban-cli/
    └── agent-skills/
```

`docker compose` es la **orquestación** de CI (GitHub Actions) y del VPS de
staging (`deploy_staging.py`): no es la vía de desarrollo. El flujo Docker local
está **deprecado** (ver `README.md`); la verificación oficial es
`deploy_staging.py --validate-only` en el Docker del VPS.

CI fija acciones por SHA e imágenes base por digest. El job `security` aplica
`pip-audit`, `actionlint`, `zizmor` y Trivy, y publica SARIF + SBOM SPDX durante
30 días. Sus umbrales y excepciones caducables viven en `security/`; no se deben
suprimir hallazgos directamente en el workflow. CodeQL usa default setup para
Python y Dependabot mantiene pip, Docker, Compose y Actions.

El job `family-contracts` comprueba que los clientes de la familia (Bar,
Commander, web-camareros, web-negocio y web-cfc) no piden **operaciones**
(`método + path`) que el Server ya no expone, y que los payloads de esas
operaciones validan contra el OpenAPI del **servicio identity** más fixtures
en `docs/contracts/` (request, 2xx y un error `identity.*` cuando aplica).
Hace sparse-checkout de los repos públicos Bar y Commander (solo fuentes; no
ejecuta su código). En Commander incluye `IdentityCliente.kt` (HTTP) e
`IdentityJson.kt` (cuerpos JSON: las claves `required` viven ahí, no en el
cliente HTTP). Barre `app.js`, `services/web-negocio/src` y
`services/web-cfc/src`, y publica en el summary las operaciones usadas por
cada cliente y las rutas públicas sin consumidor (aviso, no rojo). Falla si un
cliente llama un path ausente, un verbo que ese path no declara, o un schema
que las fixtures ya no cumplen (required quitado, tipo cambiado, enum recortado,
Bearer ausente en ops con `security`, o claves `required` ausentes en el fuente). La
normalización canónica es `normalize() → *` (cualquier `{param}`, `$var` o
`${var}` de segmento; el query y el sufijo `$q` no son segmento). Bar debe copiar esa
regla en su checker para el falso positivo `$imagenId`
(`PVTI_lAHOBM87Yc4BgQqazg3Tpcs`). `workflow_dispatch` admite `bar_ref` y
`commander_ref` (default `main` en PR/push) para validar una combinación
candidata; el job escribe un manifiesto `{server, identity, bar, commander, refs, at}`
(`identity` es alias legado del SHA del Server) en el summary y como artifact
`family-manifest` (14 días). Es el espejo del check de familia de Commander:
cada miembro cuida sus propias integraciones. Identity nombra solo el servicio
de APIs, no el producto Server.

El job `migrations-check` valida la reversibilidad de ambas cadenas Alembic
(`alembic/` y `alembic_negocio/`) con el ciclo `upgrade head → downgrade base
→ upgrade head` sobre Postgres efímero; una migración no reversible hace fallar
el job. La suite de sync offline (`tests/test_catalog_sync.py`) cubre la matriz
de conflictos: orden invertido, duplicados con reloj atrasado, modificación vs
borrado y decisiones repetidas.

Los servicios de API y tests usan UID/GID 10001 y las webs estáticas
(`web-negocio`, `web-camareros`, `web-cfc`) usan `nginx` (101). Las tareas Compose `fotos-permissions` y `reports-permissions` son las
únicas excepciones root: son efímeras e idempotentes, solo hacen `chown` de su
volumen o bind mount heredado y deben completar antes del consumidor. La segunda
permite que la validación Docker del VPS escriba JUnit y cobertura sin ejecutar
la suite como root.

Python tampoco escribe `__pycache__` en el checkout (ítem #112, cerrado): la
guarda `PYTHONDONTWRITEBYTECODE=1` está en el Dockerfile (contenedor, cualquier
usuario), en `backup_staging.sh` (python3 del host: backup/offsite) y en los
comandos host-side de `deploy_staging.py` (`--backup-restore-drill`,
`--quarantine-orphan-photos`). Un `__pycache__` con permisos de root en el
checkout del VPS rompía `ruff format --check` del runner aislado porque
`identity-tests` monta `./services/identity:/app` como bind mount.

- `GET /health` → `{ "ok": true }`
- `GET /v1/meta` → servicio, rol `identity`, `status: schema`
- `GET /openapi.json` y `/docs` → spec del contrato `/v1`
- La API registra camareros, emite QR, hace login y gestiona la foto de perfil (ver `README.md`).

## Contrato API (implementado en v0.2)

Prefijo `/v1`. JSON. Español en mensajes de error de cara a apps. Los errores llevan además un `code` estable (`identity.*`). Login, registro, uploads y `POST /v1/cfc/mesa/{token}/pedidos` aplican cuotas en Redis: **429** `identity.rate_limited` + `Retry-After`, o **503** `identity.rate_limit_unavailable` si el contador no responde. Claves: IP (tras `X-Forwarded-For` de Caddy), email, cuenta JWT y SHA-256 del token de mesa. Recorte grosero por IP en el sidecar `identity-edge` (`deploy/caddy/`; 9080/9082). El Caddy del host permanece vanilla.

| Método | Ruta | Qué hace |
|---|---|---|
| POST | `/v1/camareros/registro` | Alta: nombre, apellidos, email, password. Devuelve `id` + `qr` (payload firmado `phid1:...`) |
| POST | `/v1/auth/login` | Recupera sesión (JWT + refresh), perfil y el QR tras reinstalar |
| POST | `/v1/auth/refresh` | Rota el refresh; el anterior deja de valer |
| GET | `/v1/camareros/me` | Perfil de la sesión (incluye `foto_url`) |
| GET | `/v1/camareros/me/sesiones` | Lista sesiones de cuenta (no el QR) |
| POST | `/v1/camareros/me/sesiones/revocar` | Cierra las demás sesiones; la actual sigue |
| POST | `/v1/camareros/me/sesiones/{id}/revocar` | Cierra una sesión (p. ej. dispositivo perdido) |
| GET | `/v1/camareros/me/qr` | Payload del QR permanente |
| POST | `/v1/camareros/me/renovar` | Nueva credencial; la anterior deja de valer |
| POST | `/v1/camareros/me/revocar` | Invalida la credencial activa |
| POST | `/v1/camareros/me/password` | Cambia la contraseña de login (la credencial/QR no cambia; cierra las sesiones y emite un par nuevo) |
| POST | `/v1/auth/negocio/me/password` | Cambia la contraseña de la cuenta de negocio (cierra sesiones y emite par nuevo) |
| GET | `/v1/camareros/me/visibilidad` | Visibilidad pública por campo (default: sensibles privados) |
| PUT | `/v1/camareros/me/visibilidad` | Actualiza la visibilidad (body parcial) |
| PUT | `/v1/camareros/me/visibilidad-establecimientos` | Preferencia del camarero para el directorio de otros establecimientos: `siempre \| solo_libre \| nunca` (default `nunca`) |
| GET | `/v1/camareros/ficha/foto/{id}` | Foto pública por id (directorio) solo si `foto=true` y existe |
| GET | `/v1/camareros/ficha` | Ficha pública por `?qr=` verificado (sin token; solo campos visibles) |
| GET | `/v1/camareros/ficha/foto` | Foto pública por `?qr=` (solo si `foto=true` y existe; cache pública) |
| POST | `/v1/camareros/me/foto` | Sube/reemplaza la foto de perfil (multipart) |
| GET | `/v1/camareros/me/foto` | Sirve la foto (WebP) |
| DELETE | `/v1/camareros/me/foto` | Borra la foto |

El QR es un payload firmado Ed25519 `phid1:<camarero_id>:<credencial_id>:<firma>`, **estable** entre reinstalaciones. La foto no viaja en el QR. Las **sesiones de cuenta** son otro objeto: cada login crea una fila (`jti` en el JWT + refresh opaco rotado). Access por defecto 12 h (`SESSION_ACCESS_HOURS`; `SESSION_TTL_DAYS` como fallback). Refresh 30 d. Cambio de contraseña o `POST .../sesiones/revocar` invalidan JWT previos; el QR no se toca. JWT sin `jti` (emitidos antes) valen hasta `exp` salvo `sesiones_validas_desde`. El servicio de negocio valida el JWT de camarero vía `POST /internal/sesiones/validar` (`:8081`). Las respuestas que devuelven `qr` incluyen también `ficha_url` (`FICHA_URL_BASE` + `/camareros?qr=`), y la verificación acepta tanto `phid1:...` como la URL `https://...?qr=phid1:...`. La web pública del profesional es **`web-camareros`** (`web.camareros.siberia.solutions/camareros?qr=`, SPA vanilla en `services/web-camareros`, puerto dev `:8084`): renderiza la credencial del camarero con `GET /v1/camareros/ficha?qr=` (sin token, solo campos visibles), permite iniciar sesión (JWT + refresh), gestiona la bandeja de invitaciones, el estado «trabajador de X» y las sesiones de cuenta. El servicio de camareros autoriza el origen por CORS (`IDENTITY_WEB_ORIGIN`).

El magic-link de invitación (`/invitaciones/<token>`, aceptar o rechazar sin JWT) vive en `web-camareros`; ya no hay un servicio `identity-web` aparte. La superficie pública del establecimiento es **`web-negocio`** (`web.negocio.siberia.solutions/negocios/<slug>`, React + Vite + Tailwind en `services/web-negocio`, puerto dev `:8083`): plantilla Estate Hospitality para todos los locales, con rutas reales (`/carta`, `/horario`, `/equipo`, `/contacto`, `/galeria`) siempre visibles (stubs de cromado si el local no ha subido media; sin inventar datos). La SPA llama `GET /v1/negocio/web?slug=` al servicio de negocio (`NEGOCIO_API_URL`) sin token: la primera carga trae el JSON; los refetch (polling ~60 s y `visibilitychange`) envían `If-None-Match` y reciben `200` o `304` (`Cache-Control: public, max-age=0, must-revalidate`). El logo efectivo del local es público por diseño y el precio de la carta siempre visible. **Compatibilidad**: los dominios históricos `ficha.siberia.solutions` y `carta.siberia.solutions` responden 301 a sus superficies canónicas (`/negocio` y `/carta` → `web.negocio`; `/ficha?qr=` → `web.camareros`), con plazo de convivencia 6 meses o hasta confirmar que no hay QR impresos. Los query/hash legacy (`?seccion=carta`, `#carta`) redirigen a `/negocios/<slug>/carta`.

La cuenta de negocio representa a la **organización propietaria**; cada entidad
`Establecimiento` representa un local y posee nombre, tipo y logo opcional. Si
no hay logo local, hereda el corporativo. `GET/PATCH /v1/auth/negocio/me` edita
la organización; `PATCH /v1/establecimientos/{id}` y
`POST/GET/DELETE .../{id}/logo` editan el local. No volver a colocar tipo/branding
operativo únicamente en la cuenta: una organización puede tener locales distintos.

La web pública de negocios es **`web-negocio`**
(`web.negocio.siberia.solutions/negocios/<slug>`, **React + Vite + Tailwind
compilado** en `services/web-negocio`, puerto dev `:8083`): una plantilla
Estate Hospitality para todos los locales, con páginas en rutas reales
(`/`, `/horario`, `/carta`, `/equipo`, `/contacto`, `/galeria`) y rebranding
del logo/colores del local. El cromado visual (fondos WebP, iconos SVG, glass,
nav completa) se interpone siempre; si el local no ha subido media se usan
stubs self-hosted en `/stubs/`. No se inventa copy ni datos del establecimiento.
`GET /v1/negocio/web?slug=` (`NEGOCIO_API_URL`, runtime en `config.js`) sin token:
carga inicial más refetch con `If-None-Match` (`200` o `304`;
`Cache-Control: public, max-age=0, must-revalidate`). El contrato público
incluye `perfil`, `contacto`, `hero`, `galeria`, `horario`, `abierto_ahora`,
`equipo` (matriz AND: el local muestra el equipo solo si `mostrar_equipo` y el
camarero `aparecer_web_negocio`), `categorias` con `destino` y `descripcion`
opcional, y `fondos` por sección (`inicio|horario|carta|equipo|contacto`:
catálogo Estate o upload). La galería es álbum, no un slot de fondo. Bar pinta
el picker; Identity guarda. Con `web_publica=false` toda la superficie responde
`410 identity.web_privada` (`Cache-Control: no-store`). El logo efectivo
del local es público por diseño y el precio de la carta siempre visible.
`GET /v1/negocio/ficha` se retiró: la lectura pública canónica es `/v1/negocio/web`.
**Compatibilidad**: los dominios históricos `ficha.siberia.solutions` y
`carta.siberia.solutions` responden 301 a sus superficies canónicas (`/negocio`
y `/carta` → `web.negocio`; `/ficha?qr=` → `web.camareros`), con plazo de
convivencia 6 meses o hasta confirmar que no hay QR impresos. La SPA redirige
`?seccion=` y hashes `#carta`/`#horario`/… a las rutas nuevas.

La web de pedido en mesa es **`web-cfc`** (`web.mesa.siberia.solutions/m/<token>`,
React + Vite + Tailwind, nginx, puerto dev `:8085`): una sola SPA; el token opaco
discrimina la mesa (el comensal no elige B1). Mobile-first vertical, cuenta de
mesa (no login de cliente) y parser de voz al estilo Commander. El origen entra
en CORS (`IDENTITY_WEB_ORIGIN`). Identity emite `url_publica` con
`WEB_CFC_URL_BASE` + `/m/{token}`. `GET /v1/cfc/mesa/{token}` (sin JWT) resuelve
el token a `{ establecimiento_id, establecimiento_nombre, mesa_uuid, etiqueta, admite_pedidos, bar_en_linea }`
(`404` inválido, `410` revocado, `Cache-Control: no-store`). `/m/demo` sigue
siendo un catálogo local. Carta, pedidos y cuenta de mesa: `GET/POST
/v1/cfc/mesa/{token}/carta|pedidos|cuenta`. La admisión es jornada de **local**
+ heartbeat (~90 s) + horario: jornada cerrada o nodo ausente fuera de horario
→ `409 identity.cfc_cerrado` (no encola); nodo ausente con horario abierto
encola. Bar: `POST .../cfc/jornada/abrir|cerrar`, `PUT .../cfc/heartbeat`,
`GET .../cfc/pedidos`, `POST .../cfc/pedidos/{id}/ack`. No mezclar con
`web-negocio` ni `web-camareros`. No reutilizar las jornadas de oficio.

Fuera de v1: rankings. En v0.2, Identity incorpora la entidad de establecimiento, cuenta de negocio, membresías e invitaciones (con invitación por magic-link sin JWT); el mapa, las salas y la lista blanca LAN siguen siendo responsabilidad de Bar. Identity solo guarda un **espejo de respaldo** del layout de Bar (`PUT/GET /v1/establecimientos/{id}/layout`, tabla `layouts_establecimiento.documento` JSONB opaco) para restaurar el mapa en un dispositivo nuevo; no lo interpreta ni lo sirve a Commander. `salas` y `mesas` siguen requeridas en el PUT (convivencia); cualquier clave extra (`zonas`, futuras capas) se persiste y se devuelve tal cual.

Las mesas públicas CFC **no** se extraen del layout. Bar envía el conjunto a
`PUT /v1/establecimientos/{id}/mesas-cfc` (`mesa_uuid` + `etiqueta`); Identity
emite el token (`secrets.token_urlsafe(32)`), lo guarda como SHA-256 + SecretBox
y construye `url_publica`. `GET` lista las activas; `POST .../{mesa_uuid}/rotar`
invalida el token anterior. Ausente del conjunto = revocación inmediata; re-alta
= token nuevo. Cambiar la etiqueta no rota. Tabla `mesas_cfc`. No parsear el
documento de layout para este fin.

La bandeja de pedidos CFC vive en `jornadas_cfc` y `pedidos_cfc` (migración
`0015_cfc_inbox`). Identity no crea rondas: Bar hace ACK y convierte. El
snapshot de precio sale del catálogo canónico, no del cliente.

El **directorio de camareros** para invitar (`GET /v1/establecimientos/{id}/camareros/directorio`) devuelve un DTO **sin email** (privacidad/PII). Solo aparecen camareros que han optado por ser vistos (`siempre` o `solo_libre`); **los dueños de establecimiento nunca aparecen** (pertenecen al dominio de establecimientos, dominio de Bar — otro ítem). `libre` = sin membresía activa en ningún establecimiento (computable en BD negocio). La invitación acepta `camarero_id` (el email se resuelve en servidor) o `email` (flujo clásico).

Bar y Commander **no** copian usuarios a SQLite como fuente de verdad. Cachean la sesión. La verdad está aquí.

El transporte interno entre servicios (`INTERNAL_TRANSPORT=http`, rutas `/internal/*` en el listener `:8081`) usa **`httpx2`** (fork mantenido por Pydantic; `httpx` quedó sin mantenimiento en 2024). No reintroducir `httpx`. El status 422 se referencia como `HTTP_422_UNPROCESSABLE_CONTENT` (el nombre anterior está deprecado).

La procedencia de datos también es canónica aquí: camareros y cuentas aceptan
`data_origin = real|test|demo` al registrarse (`real` por defecto); establecimiento
y producto la heredan en servidor. `test/demo` requieren `ALLOW_NON_REAL_DATA=true`
(solo desarrollo); producción/VPS usa el default seguro `false`. El auditor
`python -m app.data_audit` es read-only y redacta PII por defecto.

### Catálogo y sincronización offline (v0.2)

Identity es también la fuente canónica del catálogo por establecimiento. Bar y
Commander mantienen mirrors Room/SQLite. Las escrituras offline nacen en un
outbox local y, al reconectar, se entregan mediante
`POST /v1/establecimientos/{id}/sync/operaciones` con UUID idempotente y revisión
base. PostgreSQL asigna la revisión global; el timestamp del cliente se audita
pero no decide conflictos.

La primera vertical soportada es `producto`: UUID estable, precio en céntimos,
categoría visible, destino explícito `barra|cocina`, `descripcion` opcional
(texto del plato en la carta pública), disponibilidad y tombstone.
`GET .../catalogo` entrega snapshot, `GET .../sync/cambios` entrega deltas,
`GET/POST .../sync/conflictos` permite revisar y resolver, y
`GET/POST .../notificaciones` mantiene el aviso durable. La cuenta titular
escribe/resuelve; miembros activos solo leen catálogo y cambios. FCM/APNs, los
modales y el outbox Room se implementan en los repos Android sin cambiar este
contrato. No extender este mecanismo a salas, mesas, rondas o colas dentro del
ítem de catálogo.

### Enlaces públicos (v0.2)

Identity emite **enlaces públicos revocables** para las superficies compartibles
del negocio (web, carta, futuros). Son públicos por diseño: sin firma, se
resuelven por `slug` opaco y se revocan con un toggle. La tabla `enlaces_publicos`
vive en la BD de negocio. `POST/GET /v1/establecimientos/{id}/enlaces` (cuenta
titular) crean/listan; `POST .../enlaces/{enlace_id}/revocar` revoca;
`POST .../enlaces/{enlace_id}/rotar` lo sustituye; hay como máximo uno activo
por establecimiento/tipo. El tipo canónico de la web del local es `web`
(`carta` para la carta JSON). `POST` ya no acepta `ficha_negocio` (422).
GET `/v1/negocio/web` sigue resolviendo slugs históricos de ese tipo.
Las respuestas incluyen `url_publica` a partir de `WEB_NEGOCIO_URL_BASE`
(`…/negocios/<slug>`, carta en `…/negocios/<slug>/carta`), nunca dominios
hardcodeados en Bar.
`GET /v1/enlaces/{slug}` (sin token) resuelve a `{ tipo, establecimiento_id }`
con cache pública de TTL corto. La web que renderiza esas rutas vive en
`services/web-negocio` (`web.negocio.siberia.solutions`).
La lectura pública canónica es `GET /v1/negocio/web?slug=` y
`GET /v1/negocio/web/logo?slug=` (sin token; el slug resuelve enlaces `web`,
el alias histórico `ficha_negocio` o `carta`). `GET /v1/negocio/web` incluye
`fondos` resueltos; un upload se sirve en `GET /v1/negocio/web/fondo/{slot}?slug=`.
La cuenta titular gestiona con `GET/PUT /v1/establecimientos/{id}/fondos` y
`POST/DELETE …/fondos/{slot}`.
La carta JSON sigue en `GET /v1/negocio/carta?slug=` (sin token, solo lectura,
agrupada por categoría, con precio, `destino` y `descripcion` opcional).
`GET /v1/negocio/ficha` se retiró.

## Qué no hacer

- No implementar sync de mesas, rondas ni colas de barra (eso es Bar + Commander).
- No mezclar este proceso con el nodo LAN (no abrir puertos de sala aquí).
- No rankings / marketplace en el primer entregable.
- No exigir este servidor en Commander para un solo tablet offline (regla de oro: no recortar Commander hasta que el otro lado exista).
- No subir secretos ni fotos reales de prueba al git.
- No saltarse Debate ni convertir draft→issue antes de Ejecutando.

## 🎯 Kanban workflow — GitHub Project

El trabajo se rastrea **solo** en el Project de este repo: [github.com/users/jaminsmoke/projects/10](https://github.com/users/jaminsmoke/projects/10) (`PVT_kwHOBM87Yc4BgQqZ`). **No** uses el kanban de Commander ni el de Bar.

Antes de crear, mover o cerrar ítems, lee:

- `tools/agent-skills/jarvis-github-kanban/SKILL.md`
- `tools/agent-skills/jarvis-github-agentuse/SKILL.md`

### Lifecycle

```
Detectado → Debate → Roadmap → Ejecutando → Verificando → Changelog
  Draft      Draft     Draft     Issue OPEN    Issue OPEN    Issue CLOSED
```

**Drafts** until `Ejecutando` — NEVER convert to issue before that.

**No skipping**: every item advances in order. Exception: `Cancelado` → Changelog.

**Version always > latest release**: consult `gh release list`. Tras publicar **v0.2**, los ítems nuevos van a **v0.3**.

Bodies in UTF-8. On Windows do **not** pipe PowerShell `Get-Content` into the CLI (mojibake). Prefer Python or `--body-file` / `gh issue edit --body-file`.

#### 1. Detectado — Describir el problema a fondo

El body debe contener una descripción **muy completa** del item y del problema detectado. No perder contexto: cuanta más información se documente aquí, más fácil será retomarlo en el futuro.

- Rellenar TODAS las secciones de la plantilla con contenido específico, no placeholders.
- Incluir: archivos exactos, líneas de código, trazas, versiones, métricas, capturas si aplica.
- Describir el impacto real en el usuario/producto, no solo el síntoma técnico.

#### 2. Debate — Preguntar al usuario, NO decidir solo

**Regla de oro**: NUNCA pasar de Debate a Roadmap sin preguntar al usuario y recibir su aprobación explícita.

**Investigación previa (obligatoria al entrar en Debate, antes de listar opciones)**:

Al pasar a Debate — y **antes** de redactar `Alternativas` — investigar a fondo la causa y el espacio de soluciones. Documentar en el body la sección `Investigación previa`:

- Archivos, flujos y dependencias leídos (con rutas concretas: `docker-compose.yml`, `services/identity/app/main.py`, `requirements.txt`).
- Hipótesis de causa(s): los ítems suelen ser **multicausales**; no quedarse en el síntoma superficial.
- Patrones del proyecto / ecosistema relevantes (FastAPI, Postgres, Alembic, PII/GDPR, OpenAPI).
- Restricciones reales (Docker local sin HTTPS, PII, alcance de versión, contrato con Bar/Commander).
- Qué se descartó y por qué (aunque sea breve).
- **Estrategia de rama / integración**: ¿el cambio justifica rama dedicada (`feature/...`) vs trabajo en `main`? Anotar propuesta (nombre de rama, merge a `main` al Changelog, PRs si aplica). En cambios grandes (esquema, auth, migraciones, features transversales) la rama dedicada es la opción por defecto a contemplar.

Sin esta sección no se presentan las opciones. La investigación vive en Debate (no hincha Detectado); Detectado aporta el problema, Debate aporta el mapa de soluciones.

**Formato fijo de alternativas** — siempre presentar exactamente estas **4** opciones (en este orden):

1. **Solución raíz** 🌳 — va al origen del problema (modelo, arquitectura, contrato de datos, identidad de producto…). No se limita a “hacerlo bien dentro de lo que hay”; puede proponer rediseño o cambio de enfoque. Exige basarse en la `Investigación previa`. Si el problema es genuinamente superficial y no hay causa estructural, indicar **"no aplica"** con una frase de justificación (casi siempre sí conviene explorarla: un bug “simple” puede esconder una solución más robusta).
2. **Opción sólida** 🏗️ — la más correcta y robusta **dentro del diseño actual** (o con cambios acotados). Mejor arquitectura/mantenibilidad/escalabilidad sin replantear el sistema entero.
3. **Opción rápida** ⚡ — la más rápida de implementar. Puede coincidir o no con la sólida/raíz. Prioriza velocidad sobre perfección.
4. **Opción intermedia** ⚖️ — equilibrio entre profundidad y velocidad. Solo cuando exista un punto medio real; si no hay, indicar "no aplica".

Cada opción debe llevar:
- Descripción clara de la solución
- Número estimado de líneas/cambios
- Pros (✅) y contras (⚠️)

**Recomendación situacional (revisar por ítem)**: al final, recomendar una opción **según el contexto concreto de ese ítem**, no por regla mecánica. Orientaciones de partida (siempre contrastarlas con lo hallado en la investigación):

- Bug crítico en producción → suele favorecer la **rápida** (mitigar ya), sin ocultar si la raíz merece un follow-up.
- Mejora sin urgencia → suele favorecer la **sólida** o la **raíz**, según si el diseño actual basta o hay que replantear.
- Deuda técnica acumulada → suele favorecer la **intermedia** o la **raíz** si la deuda es estructural.
- Rediseño / identidad de producto / problema multicausal profundo → valorar explícitamente la **raíz**.

La recomendación debe citar **por qué** encaja este ítem (1–3 frases), no solo etiquetar el tipo.

**Proceso**:
- Añadir secciones `Investigación previa`, `Análisis`, `Alternativas` (con las 4 opciones) y `Recomendación` al body.
- **Parar y preguntar** al usuario. Solo cuando él decida, marcar `Decision: Aprobado` y mover a Roadmap.
- Si `Decision: Cancelado` → documentar motivo, convertir a issue, cerrar, mover a Changelog.
- Si `Decision: Diferido` → documentar motivo y condición, devolver a Detectado.

#### 3. Roadmap — Planificar en profundidad antes de tocar código

Con la decisión ya tomada y acordada en la fase anterior, detallar **mucho más** el plan de implementación.

- Investigar a fondo: leer archivos relacionados, dependencias, migraciones, efectos colaterales en Bar/Commander (solo contrato; no implementes esas apps aquí).
- Revisar si el plan acordado en Debate se queda corto — añadir lo que falte.
- Documentar: `Decisión acordada`, `Plan aprobado` (paso a paso), `Criterios de aceptación`, `Plan de verificación`, `Riesgos y recuperación`.
- Solo cuando el plan sea sólido y completo, mover a Ejecutando.

#### 4. Ejecutando — Implementar el plan

- Al entrar: convertir draft → issue, añadir labels (1 Tipo + 1 Área). **Aquí empieza el código.**
- **Crear rama `feature/...`** desde `main` antes de tocar código. Todos los commits van en esta rama, nunca directamente en `main`.
- Implementar siguiendo el plan detallado de Roadmap.
- Si algo difiere del plan original, **documentarlo** en el body (sección `Implementación`) explicando el porqué del cambio.
- Hacer commits locales con mensajes descriptivos en la rama feature.

#### 5. Verificando — Tests y comprobaciones exhaustivas

**No es solo ejecutar la validación remota.** Es verificar que el cambio funciona, no rompe nada y cumple estándares de calidad.

**`--validate-only` es solo validación: NO despliega nada en producción.** Ejecuta Docker sobre las BD `_test` del VPS, corre la suite, verifica migraciones y calidad. El deploy real se hace en Changelog (paso 7) tras merge a `main`.

**Checklist obligatorio** (siempre ejecutar TODO lo aplicable):

1. **Validación aislada en VPS**: `python services/identity/scripts/deploy_staging.py --ref <rama> --validate-only`; usa Docker y solo las BD `_test`, sin recrear las APIs activas. **Esto es validación, no deploy.**
2. **Health en staging desplegado**: `GET /health` → `{"ok": true}`; `GET /v1/meta` → `status: schema` coherente
3. **Tests en VPS**: el runner remoto debe pasar completo y la cobertura de ramas no puede bajar del 82%. Crear tests para rutas nuevas (registro, login, QR, revocar)
4. **Contrato**: las rutas nuevas responden JSON documentado; errores de cara a apps en español
5. **Secretos**: `.env` no está en git; no hay fotos reales ni dumps con PII

**Validaciones adicionales según el área**:

- API → requests a `/v1/...`, códigos de error estables, OpenAPI si el ítem lo pide
- Datos → esquema aplicado, migraciones reversibles o documentadas, ping a Postgres
- Infra → Compose, volúmenes, puertos; no mezclar con el puerto de sala de Bar
- Docs → README y este archivo siguen siendo verdad
- Build/CI → imagen Docker construye en limpio; `quality` (Ruff + OpenAPI) e
  `integration` (tests + cobertura + auditoría) pasan

**Antes de pasar a Changelog**:
- Documentar TODO en el body: sección `Verificación` con checklist de lo ejecutado y resultados
- Si se encontraron y corrigieron errores preexistentes, documentarlos
- Hacer commit con los fixes de verificación
- Solo cuando todo esté verificado, pasar a Changelog

No aplica `./gradlew` (eso es Bar/Commander).

#### 6. Changelog — Cerrar, fechar y publicar

1. **Commit final** con mensaje descriptivo (si no se hizo ya en Verificando).
2. Anotar el **SHA del commit** en el body (sección `Commit`).
3. Mover status a `Changelog`.
4. Setear `Completado` (fecha) y `Completado exacto` (ISO-8601).
5. Añadir ✅ al título del issue.
6. Cerrar el issue (`gh issue close -r completed`).
7. **Crear PR** de la rama `feature/...` → `main`, mergear (con `--admin` si hay branch protection).
8. **Deploy real**: `python services/identity/scripts/deploy_staging.py --ref main` (sin `--validate-only`). Este es el único momento en que se despliega a producción.
9. Verificar `GET /health` y `GET /v1/meta` en staging tras el deploy.
10. **Push** de la rama `main` actualizada.

### CLI (all commands from this folder: PersonalHosteleriaServer)

```bash
KANBAN="bun run tools/kanban-cli/cli.ts"

# Primera vez en la máquina
cd tools/kanban-cli && bun install && cd ../..
copy .kanbanrc.json.template .kanbanrc.json   # Windows
# cp .kanbanrc.json.template .kanbanrc.json
$KANBAN config validate

# Create item
$KANBAN create --title "..." --tipo Feature --area API --priority Alta --version "v0.3"

# List
$KANBAN list

# Show item
$KANBAN show <itemId>

# Read/set body
$KANBAN body <itemId>              # read
$KANBAN body <itemId> --set "..."  # replace
$KANBAN body <itemId> --append "Investigación previa" --content "..."

# Change status (use set-field, NOT move)
$KANBAN set-field <itemId> --field "Status" --option "Debate"

# Convert draft → issue (only at Ejecutando)
$KANBAN convert-draft <itemId>
gh issue edit <N> --repo jaminsmoke/PersonalHostel-Server --add-label "tipo:feature,area:api"

# Ejecutando: crear rama feature ANTES de commitear
git checkout -b feature/<nombre-del-cambio>
# ... implementar y commitear en la rama feature ...

# Verificando: --validate-only es SOLO validación (NO deploy)
python services/identity/scripts/deploy_staging.py --ref <rama> --validate-only
# El deploy real se hace en Changelog, no aquí.

# Changelog: PR + merge + deploy real
git add <files> && git commit -m "..."
$KANBAN body <itemId> --append "Commit" --content "SHA: \`$(git rev-parse --short HEAD)\`"
$KANBAN set-field <itemId> --field "Status" --option "Changelog"
$KANBAN set-field <itemId> --field "Completado" --date "YYYY-MM-DD"
$KANBAN set-field <itemId> --field "Completado exacto" --text "YYYY-MM-DDTHH:MM:SSZ"
gh pr create --repo jaminsmoke/PersonalHostel-Server --base main --head feature/<nombre> --title "..." --body "..."
gh pr merge <PR> --repo jaminsmoke/PersonalHostel-Server --merge --admin
gh issue edit <N> --repo jaminsmoke/PersonalHostel-Server --title "✅ ..."
gh issue close <N> --repo jaminsmoke/PersonalHostel-Server -r completed
# Deploy real (único momento en que se despliega)
python services/identity/scripts/deploy_staging.py --ref main
git checkout main && git pull

# Delete (IRREVERSIBLE, requires --yes)
$KANBAN delete <itemId> --yes
```

Áreas válidas en `--area` de **este** Project: `API`, `Datos`, `Build/CI`, `Docs`, `Infra`.

### Body sections by phase

Each item's body evolves through the lifecycle. The CLI generates a template at creation — **always fill it with specific content**, never leave the placeholders.

| Phase | Body sections | Reglas |
|---|---|---|
| **Detectado** | Contexto, Hallazgo y evidencia, Impacto, Alcance a debatir, Preguntas para Debate, Criterio para avanzar, Clasificación preliminar | Descripción MUY completa. No perder contexto. |
| **Debate** | + Investigación previa, Análisis, Alternativas (4: raíz / sólida / rápida / intermedia), Recomendación | Investigar antes de opciones. **PARAR y preguntar.** No avanzar sin aprobación explícita. |
| **Roadmap** | + Decisión acordada, Plan aprobado, Criterios de aceptación, Plan de verificación, Riesgos y recuperación | Investigar a fondo. Añadir lo que falte al plan. |
| **Ejecutando** | + Implementación (qué se hizo realmente, diferencias con el plan si las hay) | Convertir draft→issue al ENTRAR. Documentar cambios sobre el plan. |
| **Verificando** | + Verificación (Compose, health, tests, PII, comprobaciones específicas) | Ejecutar TODO lo aplicable. Arreglar errores preexistentes si se encuentran. |
| **Changelog** | + Commit (SHA). Setear `Completado`, `Completado exacto`. ✅ en título. | Commit → SHA al body → cerrar issue → push a main. |

### Fields reference

| Field | Type | Purpose |
|---|---|---|
| Status | SingleSelect | Detectado → ... → Changelog |
| Prioridad | SingleSelect | Alta, Media, Baja |
| Tipo | SingleSelect | Bug, Feature, Mejora, Tarea |
| Área principal | SingleSelect | API, Datos, Build/CI, Docs, Infra |
| Versión | SingleSelect | Sin asignar, v0.1, v0.2, v0.3… |
| Decision | SingleSelect | Pendiente, Aprobado, Diferido, Cancelado |
| HighLighted | SingleSelect | Yes, No (for changelog highlights) |
| Inicio exacto | Text | ISO-8601 UTC timestamp |
| Inicio | Date | YYYY-MM-DD |
| Completado exacto | Text | ISO-8601 UTC (set on Changelog) |
| Completado | Date | YYYY-MM-DD (set on Changelog) |

### Labels canónicas

Cada Issue debe tener exactamente **1 label de Tipo + 1 label de Área**. Status,
Prioridad y Versión viven exclusivamente en campos del Project y no se duplican
como labels.

| Campo Tipo | Label | Uso |
|---|---|---|
| Bug | `tipo:bug` | Comportamiento incorrecto o regresión verificable |
| Feature | `tipo:feature` | Capacidad nueva observable para usuario o producto |
| Mejora | `tipo:mejora` | Calidad, rendimiento o mantenibilidad |
| Tarea | `tipo:tarea` | Trabajo operativo o técnico acotado |

| Área principal | Label | Incluye |
|---|---|---|
| API | `area:api` | HTTP, FastAPI, contratos `/v1`, OpenAPI |
| Datos | `area:datos` | Postgres, migraciones, fotos, integridad |
| Build/CI | `area:build-ci` | Docker, CI, deploys |
| Docs | `area:docs` | Documentación y contratos para agentes |
| Infra | `area:infra` | VPS, red, secretos, HTTPS |

Labels auxiliares permitidas cuando correspondan: `security`, `dependencies`,
`duplicate`, `invalid`, `wontfix`, `question`, `good first issue` y `help wanted`.
No usar los aliases antiguos `bug`, `enhancement` o `documentation`.

### Configuración local del Kanban

`.kanbanrc.json` contiene IDs específicos del Project y permanece gitignored.
`.kanbanrc.json.template` se versiona como referencia reproducible.

Tras crear, borrar o modificar opciones de un campo SingleSelect, todos sus IDs
pueden cambiar. Regenerar y validar inmediatamente:

```bash
$KANBAN config generate --project PVT_kwHOBM87Yc4BgQqZ
# El generador deja estos valores como REPLACE_ME; restaurarlos antes de continuar:
# repoId: R_kgDOT3ZYEg
# repo: jaminsmoke/PersonalHostel-Server
$KANBAN config validate
```

Después, comprobar que ningún ítem perdió el valor del campo modificado, reponerlo
por nombre si fuera necesario y actualizar `.kanbanrc.json.template` con los IDs
nuevos. Nunca ejecutar `convert-draft` mientras `repoId` sea `REPLACE_ME`.

## Backlog (deriva de arranque — completado en v0.1)

El backlog de arranque quedó **completo y cerrado** en la release **v0.1** (2026-08-13). Los 6 ítems recorrieron el ciclo completo (Detectado → … → Changelog) y sus issues están cerrados:

| Pri | Área | Título | Issue |
|---|---|---|---|
| Alta | Datos | Esquema Postgres: camareros, credenciales/QR y revocaciones | [#1](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/1) |
| Alta | API | Registro de profesional y emisión de QR/clave permanente | [#2](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/2) |
| Alta | API | Login que recupera la misma identidad y el mismo QR tras reinstalar | [#3](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/3) |
| Media | API | Revocar y renovar la clave/QR permanente | [#4](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/4) |
| Media | Docs | OpenAPI de /v1: spec versionada y códigos de error estables | [#5](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/5) |
| Media | Datos | Foto de perfil del profesional (almacenamiento Docker local) | [#6](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/6) |

Detalle en [`docs/changelog.md`](docs/changelog.md). Los ítems nuevos entran por `Detectado` en el Project #10, con la misma regla: investigar, presentar las 4 alternativas y **parar a preguntar**.

## Code conventions

- **Language**: Spanish for user-facing API error messages; English for code symbols
- JSON `/v1`; do not invent a second prefix
- Persist identity in Postgres, not in app Room as source of truth
- Do not commit `.env`, real photos, or DB dumps with PII

## Keys & security

- `.env` gitignored; start from `.env.example`
- La verificación automatizada se ejecuta en el Docker del VPS; staging usa HTTPS.
- GraphQL token for kanban CLI: `GH_TOKEN` / `GITHUB_TOKEN` from `gh auth`

## License & business model

Same family as Commander: public MIT. Do not put paid premium code in this public repo.

## Cómo probar

Ver `README.md`. Desde esta carpeta, la verificación oficial es
`python services/identity/scripts/deploy_staging.py --ref <rama> --validate-only`;
ejecuta calidad, contrato, suite y migraciones reversibles en Docker sobre las
BD `_test` del VPS, sin usar Docker local ni las BD activas. El runner no falla
por `__pycache__` root: la guarda `PYTHONDONTWRITEBYTECODE` está completa
(Dockerfile, `backup_staging.sh` y `deploy_staging.py`; ítem #112).

## Observabilidad (solo staging/producción)

Las APIs exponen `/metrics` en `:8081` (Prometheus, red Docker; Caddy no lo publica) y un access log JSON.
El stack de observabilidad vive en `docker-compose.observability.yml` (Prometheus,
Grafana, Loki, Alloy, node_exporter, postgres_exporter y Alertmanager) y **no**
forma parte del `up` de desarrollo. En el VPS se gestiona con
`bash services/identity/scripts/obs_up.sh` (apila siempre los 3 compose). El deploy
(`deploy_staging.py` sin `--validate-only`) invoca `obs_up.sh up` tras el core;
`validate-only` no toca observabilidad. **Nunca** hagas `compose down`/limpieza de
orphans con solo 2 ficheros: Docker borra la pila de obs. Grafana:
`grafana.siberia.solutions` con `basic_auth` de Caddy. Ver
`README.md → Observabilidad en el VPS`. Smoke sintético: `k6`
(`services/identity/scripts/k6/smoke.js`). Para navegar las UIs internas
(Prometheus :9090, Alertmanager :9093, Grafana :3001) desde la máquina de un
admin, usar `python services/identity/scripts/obs_tunnel.py` (túnel SSH, no
abre puertos públicos).

## Dev tools

```
tools/kanban-cli/          # bun install; CLI = bun run tools/kanban-cli/cli.ts
tools/agent-skills/        # jarvis-github-kanban + jarvis-github-agentuse
.kanbanrc.json             # local Project IDs (gitignored)
.kanbanrc.json.template    # versioned reproducible reference
services/identity/pyproject.toml  # Ruff + pytest + cobertura de ramas (mínimo 82%)
```
