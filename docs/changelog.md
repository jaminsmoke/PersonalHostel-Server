# Changelog

Todos los cambios notables de **PersonalHostel Server** (el servidor de identidad
de la familia PersonalHostel) se documentan aquí.

El formato sigue [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/)
y el versionado sigue [SemVer](https://semver.org/lang/es/).

## [Unreleased]

### Corregido

- **Outbox de email huérfana en `enviando`**: lease (`enviando_desde` + `worker_id`),
  recuperación de claims vencidos o nulos, `Message-ID` SMTP estable por fila y
  log de leases recuperados sin PII. SMTP sigue siendo at-least-once.
  ([#186](https://github.com/jaminsmoke/PersonalHostel-Server/issues/186), Datos)

### Añadido

- **Borde Caddy Identity (`identity-edge`)**: sidecar Compose con
  `caddy-ratelimit` (binario pineado). El Caddy del host sigue vanilla. Login,
  registro y refresh por `{client_ip}`; sin CFC en el borde. 429 JSON
  `identity.rate_limited`. Loopback `9080`/`9082`; las APIs siguen en `8080`/`8082`.
  ([#182](https://github.com/jaminsmoke/PersonalHostel-Server/issues/182), Infra)


### Añadido

- **Sesiones de cuenta revocables**: JWT con `jti`, refresh opaco rotado, listar
  y revocar por dispositivo. Cambio de contraseña cierra todas y emite un par
  nuevo; el QR de oficio no cambia. Access 12 h (`SESSION_ACCESS_HOURS`),
  refresh 30 d. `POST /v1/auth/refresh` y homólogo de negocio. web-camareros
  guarda el refresh y muestra las sesiones.
  ([#180](https://github.com/jaminsmoke/PersonalHostel-Server/issues/180), API)

- **Límites de abuso**: Redis en Compose (sin persistencia ni puerto público en
  prod) y cuotas en la API. Login por IP+email, registro por IP, uploads por
  cuenta JWT, POST CFC por hash del token de mesa. `429 identity.rate_limited`
  + `Retry-After`; Redis caído → `503 identity.rate_limit_unavailable` en esas
  rutas (`/health` no depende de Redis). Recorte grosero por IP en Caddy:
  `deploy/caddy/`. web-cfc y web-camareros muestran el 429.
  ([#177](https://github.com/jaminsmoke/PersonalHostel-Server/issues/177), API)

### Corregido

- **Listener interno `:8081`**: `/internal/*` y `/metrics` salen de la app que
  Caddy publica (`:8080`). Un proceso, dos sockets; Prometheus y el HTTP entre
  servicios usan `:8081` (no se publica en el host). OpenAPI público ya no
  documenta `/internal`.
  ([#175](https://github.com/jaminsmoke/PersonalHostel-Server/issues/175), Infra)

### Añadido

- **Inbox CFC**: jornada de local, heartbeat, carta/cuenta/pedido por token de
  mesa y bandeja autenticada para Bar. `POST /v1/establecimientos/{id}/cfc/jornada/abrir|cerrar`,
  `PUT .../cfc/heartbeat`, `GET .../cfc/pedidos`, `POST .../ack`. Público:
  `GET/POST /v1/cfc/mesa/{token}/carta|cuenta|pedidos`. Admisión = jornada +
  heartbeat (~90 s) + horario (`409 identity.cfc_cerrado` si no admite; encola
  si el nodo cae con el local abierto). Snapshot de precio del catálogo.
  Migración `0015_cfc_inbox`. web-cfc envía el pedido real; `/m/demo` sigue
  local. ([#173](https://github.com/jaminsmoke/PersonalHostel-Server/issues/173), API)

- **Mesas CFC y tokens opacos**: `PUT/GET /v1/establecimientos/{id}/mesas-cfc`
  y `POST .../{mesa_uuid}/rotar` (cuenta titular). Bar envía el conjunto;
  Identity emite el token, lo busca por SHA-256 y reconstruye `url_publica`
  con SecretBox. `GET /v1/cfc/mesa/{token}` identifica la mesa (`404`/`410`,
  `no-store`). web-cfc consume ese GET; `/m/demo` sigue local. Migración
  `0014_mesas_cfc`. No se parsea el layout.
  ([#171](https://github.com/jaminsmoke/PersonalHostel-Server/issues/171), API)

- **Web CFC (`web-cfc`)**: SPA React en `:8085` / `web.mesa.siberia.solutions`
  para pedir desde el QR de mesa (`/m/<token>`). Mobile-first vertical, cuenta
  de mesa, parser de voz y andamiaje Compose/CORS/`WEB_CFC_URL_BASE`. El
  contrato de tokens e inbox sigue en ítems hermanos.
  ([#165](https://github.com/jaminsmoke/PersonalHostel-Server/issues/165), API)

- **Espejo de layout opaco**: `PUT/GET /v1/establecimientos/{id}/layout` deja de
  guardar columnas `salas`/`mesas` y persiste un documento JSONB único. El PUT
  sigue exigiendo esas dos capas (convivencia con Bar); cualquier extra (`zonas`
  y capas futuras) se guarda y se devuelve sin interpretar. Migración
  `0013_layout_documento`.
  ([#163](https://github.com/jaminsmoke/PersonalHostel-Server/issues/163), API)

## [v0.2] - 2026-08-21

Corte del servidor de identidad: cuentas de establecimiento, webs públicas,
catálogo, oficio y operación en el VPS. El tag GitHub es **v0.2**; FastAPI,
OpenAPI y `web-negocio` siguen en `0.2.0`.

### Destacados

- Cuentas de **negocio** distintas de camareros, establecimientos, membresías e
  invitaciones (magic-link, bandeja, directorio).
- **Web pública Estate** (`web.negocio.siberia.solutions`) y **web del
  profesional** (`web.camareros.siberia.solutions`: ficha, login, invitaciones).
- Catálogo canónico, horario, espejo de layout, fondos por sección y frescura
  ETag/304 de `GET /v1/negocio/web`.
- Oficio (horas / rondas), observabilidad en el VPS y cadena de suministro de CI.

### Añadido

- **Frescura de la web pública**: `GET /v1/negocio/web` emite `ETag` (SHA-256
  del JSON canónico) y `Cache-Control: public, max-age=0, must-revalidate`.
  La SPA refetch (polling ~60 s y `visibilitychange`) con `If-None-Match`.
  ([#147](https://github.com/jaminsmoke/PersonalHostel-Server/issues/147), API)

- **Fondos por sección en la web pública**: cada página (`inicio`, `horario`,
  `carta`, `equipo`, `contacto`) tiene su propio plano de ambiente — catálogo
  Estate o foto subida. Identity guarda (`GET/PUT …/fondos`, `POST/DELETE
  …/fondos/{slot}`, migración `0012`); `GET /v1/negocio/web` expone `fondos`
  resueltos. La galería sigue siendo álbum. El picker de UI vive en Personal
  Bar. ([#139](https://github.com/jaminsmoke/PersonalHostel-Server/issues/139), API)

- **Web pública Estate Hospitality con rutas reales**: `web-negocio` deja el
  one-pager con hashes y sirve páginas `/negocios/<slug>` (inicio, horario,
  carta, equipo, contacto, galería). La carta pública expone `destino`
  (tabs Cocina/Barra) y `descripcion` opcional del plato (migración `0010`).
  El tipo de enlace canónico pasa a `web` (`ficha_negocio` queda como alias);
  `url_publica` apunta a `/negocios/<slug>` y `/negocios/<slug>/carta`.
  Se retira `GET /v1/negocio/ficha`: la lectura canónica es `/v1/negocio/web`.
  ([#130](https://github.com/jaminsmoke/PersonalHostel-Server/issues/130), API)

- **Política raíz de seguridad de CI y cadena de suministro**: CodeQL y
  Dependabot, auditoría Python/workflows/contenedores con `pip-audit`,
  `actionlint`, `zizmor` y Trivy, SBOM SPDX por imagen, pines inmutables y
  excepciones justificadas con caducidad. Los runtimes Identity y Web pasan a
  usuarios no privilegiados. ([#25](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/25), Build/CI)

- **Procedencia canónica de datos** `real|test|demo` para camareros y cuentas,
  heredada de forma inmutable por establecimientos y productos. Incluye política
  segura por entorno, auditor read-only con PII redactada, diagnóstico cross-DB y
  CI sobre PostgreSQL efímero. ([#21](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/21), Build/CI)

- **Catálogo canónico por establecimiento** con UUID estable, dinero en céntimos,
  destino `barra|cocina`, archivado lógico y lectura para miembros activos.
  Incluye protocolo reutilizable para mirrors offline: operaciones idempotentes,
  revisiones globales, deltas, conflictos con decisión humana y notificaciones
  durables. ([#19](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/19), Datos)
- Campo **`nick`** en `camareros` (migración `0008`): mote visible en barra/colas,
  distinto del nombre legal. Opcional en `POST /v1/camareros/registro` (compatibilidad);
  Commander lo exige en el alta. `PATCH /v1/camareros/me` lo actualiza. Login, `/me`
  y búsqueda por email lo exponen.

- **Horario semanal del establecimiento** (fuente canónica para la web): tabla
  `horarios_establecimiento` (un día por fila, `cerrado` y turnos `{abre, cierra}`),
  `GET/PATCH /v1/establecimientos/{id}/horario` con JWT de negocio y validación
  estricta (HH:MM, `abre < cierra`, sin solapamientos, días no repetidos), y
  exposición en `GET /v1/negocio/web`. La sincronización con Bar queda diferida
  a su ítem (protocolo `OperacionSync` existente).
  ([#109](https://github.com/jaminsmoke/PersonalHostel-Server/issues/109), API)

- **Horario en la web pública de cada negocio**: la plantilla de `web-negocio`
  muestra la sección "Horario" con agrupación de días contiguos ("Lunes a Viernes
  10:00–16:00"), turnos múltiples separados con "y", "Cerrado" en días cerrados y
  sin sección cuando el negocio no tiene horario. Accesible (`time` + `aria-label`)
  y con ancla `?seccion=horario`.
  ([#110](https://github.com/jaminsmoke/PersonalHostel-Server/issues/110), API)

- **Negocio, altas y webs** (resumen): cuentas de establecimiento ([#8](https://github.com/jaminsmoke/PersonalHostel-Server/issues/8),
  [#13](https://github.com/jaminsmoke/PersonalHostel-Server/issues/13)); invitaciones
  y bandeja ([#9](https://github.com/jaminsmoke/PersonalHostel-Server/issues/9),
  [#34](https://github.com/jaminsmoke/PersonalHostel-Server/issues/34),
  [#36](https://github.com/jaminsmoke/PersonalHostel-Server/issues/36),
  [#93](https://github.com/jaminsmoke/PersonalHostel-Server/issues/93)); directorio
  ([#69](https://github.com/jaminsmoke/PersonalHostel-Server/issues/69)); espejo de
  layout ([#11](https://github.com/jaminsmoke/PersonalHostel-Server/issues/11));
  ficha y visibilidad del camarero ([#45](https://github.com/jaminsmoke/PersonalHostel-Server/issues/45),
  [#47](https://github.com/jaminsmoke/PersonalHostel-Server/issues/47),
  [#85](https://github.com/jaminsmoke/PersonalHostel-Server/issues/85),
  [#91](https://github.com/jaminsmoke/PersonalHostel-Server/issues/91)); enlaces
  públicos del negocio ([#51](https://github.com/jaminsmoke/PersonalHostel-Server/issues/51),
  [#71](https://github.com/jaminsmoke/PersonalHostel-Server/issues/71)); oficio
  ([#102](https://github.com/jaminsmoke/PersonalHostel-Server/issues/102));
  contraseña y dirección ([#79](https://github.com/jaminsmoke/PersonalHostel-Server/issues/79),
  [#81](https://github.com/jaminsmoke/PersonalHostel-Server/issues/81));
  observabilidad VPS ([#59](https://github.com/jaminsmoke/PersonalHostel-Server/issues/59),
  [#115](https://github.com/jaminsmoke/PersonalHostel-Server/issues/115));
  backups ([#106](https://github.com/jaminsmoke/PersonalHostel-Server/issues/106)).

### Corregido

- **`If-None-Match` no enlazaba en `GET /v1/negocio/web`**: FastAPI declaraba
  el header con `convert_underscores=False`, así que el refetch de la SPA
  nunca recibía `304` (siempre `200` + body). Ahora el parámetro usa
  `alias="If-None-Match"`, el `304` reenvía `ETag` y `Cache-Control`, y hay
  tests de coincidencia y mismatch.
  ([#149](https://github.com/jaminsmoke/PersonalHostel-Server/issues/149), API)

- **Validación aislada en VPS** desbloqueada: `ruff format --check` fallaba por
  `__pycache__` con permisos de root en el checkout del VPS (bind mount de
  `identity-tests`). Se añade `PYTHONDONTWRITEBYTECODE=1` al Dockerfile para
  impedir la generación de `__pycache__` en runtime.
  ([#112](https://github.com/jaminsmoke/PersonalHostel-Server/issues/112), Build/CI)

- **`/config.js` runtime en Vite 8**: el script clásico de `web-negocio` lleva
  `vite-ignore` para no empaquetarlo (`type=module` lo rompería).
  ([#158](https://github.com/jaminsmoke/PersonalHostel-Server/issues/158), Build/CI)

### Cambiado

- **Family contracts compara operaciones, no solo paths**: el job cruza
  `(método, path)` con OpenAPI, incluye `web-negocio`, admite refs candidatas
  (`bar_ref`/`commander_ref`) y publica un manifiesto de SHAs (summary +
  artifact 14 días). Falla si un cliente pide un path ausente o un verbo no
  declarado. ([#141](https://github.com/jaminsmoke/PersonalHostel-Server/issues/141), Build/CI)

- **Base de calidad CI** con contrato único en `pyproject.toml`, Ruff, cobertura
  de ramas mínima del 82%, runner Docker aislado y checks requeribles `quality`
  e `integration`. Las imágenes runtime ya no incluyen pytest ni los tests y CI
  cancela ejecuciones obsoletas, publica informes durante 14 días y conserva el
  anti-drift OpenAPI y la auditoría de procedencia. ([#23](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/23), Build/CI)

- **Runtime Python 3.14**, dos BD (camareros / negocio) y despliegue VPS como
  vía oficial (Docker local deprecado). Recolector de logs: Grafana Alloy;
  Loki 3.7.6 y Grafana 13.1.4.

## [v0.1] - 2026-08-13

Primer entregable: identidad permanente del profesional — registro, QR firme,
login, revocación/renovación y foto de perfil — con contrato HTTP documentado.

### Añadido

- **Esquema Postgres** de `camareros`, `credenciales` y `app_config` con Alembic.
  ([#1](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/1), `66569f1`, Datos)
- **Registro de profesional** y emisión de **QR/clave permanente** firmado con
  Ed25519 (`phid1:<id>:<credencial>:<firma>`).
  ([#2](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/2), `f379f5f`, API)
- **Login** (email + password, JWT) que recupera la misma identidad y el mismo
  QR tras reinstalar.
  ([#3](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/3), `745920c`, API)
- **Revocar y renovar** la clave/QR: revocar invalida la credencial activa sin
  crear otra; renovar emite una credencial nueva y revoca las anteriores.
  ([#4](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/4), `5565b0c`, API)
- **Foto de perfil** autenticada (subir / servir / borrar), normalizada a un
  único avatar 256×256 WebP en volumen Docker, con abstracción `FotoStorage`
  lista para migrar a object storage.
  ([#6](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/6), `c6f177c`, Datos)

### Documentación

- **OpenAPI de /v1** versionado: spec enriquecida con ejemplos y códigos de error
  estables (`identity.*`), `docs/openapi.json` en git y gate de CI anti-drift.
  ([#5](https://github.com/jaminsmoke/PersonalHostel-Identity/issues/5), `9bf6681`, Docs)

[Unreleased]: https://github.com/jaminsmoke/PersonalHostel-Server/compare/v0.2...HEAD
[v0.2]: https://github.com/jaminsmoke/PersonalHostel-Server/releases/tag/v0.2
[v0.1]: https://github.com/jaminsmoke/PersonalHostel-Server/releases/tag/v0.1
