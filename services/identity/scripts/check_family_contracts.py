#!/usr/bin/env python3
"""Comprueba que los clientes de la familia no piden operaciones que el Server
ya no expone y deja un informe de aprovechamiento (summary de Actions / stdout).

Compara ``(método, path)`` contra ``paths.<ruta>.<método>`` del OpenAPI del
servicio identity, y valida fixtures JSON Schema del pack en ``docs/contracts/``.
La normalización canónica es ``normalize() -> *`` (cualquier ``{param}`` o
``$var`` de segmento).

Es el espejo de ``PersonalComander/scripts/check_family_contracts.py``: cada
miembro de PersonalHostel cuida sus propias integraciones con el resto.

Uso:
    python scripts/check_family_contracts.py \\
        --camareros-openapi docs/openapi-camareros.json \\
        --negocio-openapi docs/openapi-negocio.json \\
        --bar-src path/IdentityNegocioClient.kt \\
        --commander-src path/IdentityCliente.kt \\
        --web-src services/web-camareros/static/app.js \\
        --web-src services/web-negocio/src \\
        --web-src services/web-cfc/src

    python scripts/check_family_contracts.py --selftest
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import family_contract_pack as contract_pack


def _repo_root() -> Path:
    """Raíz del checkout del Server, o /app en la imagen identity-tests."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docs" / "openapi-camareros.json").is_file():
            return parent
    return here.parent.parent


REPO_ROOT = _repo_root()
DEFAULT_CONTRACTS_DIR = REPO_ROOT / "docs" / "contracts"

# Captura rutas del servicio identity en literales: /v1/..., /internal/... y /health.
RUTA_RE = re.compile(r'"((?:/v1/|/internal/|/health)[^"]*)"')
TEMPLATE_PATH_RE = re.compile(r"`[^`]*?((?:/v1/|/internal/|/health)[^`?\s]*)")

PARAM_RE = re.compile(r"\$\{[^}]+\}|\{[^}]+\}|\$[A-Za-z_][A-Za-z0-9_]*")
QUERY_SUFFIX_VAR_RE = re.compile(r"(?<!/)\$[A-Za-z_][A-Za-z0-9_]*$")

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "options", "head", "trace"})
METHOD_LITERAL_RE = re.compile(r'\bmethod\s*:\s*["\'](GET|POST|PUT|PATCH|DELETE)["\']', re.I)

BAR_REQUEST_RE = re.compile(
    r"IdentityHttp\.(?:request|requestBytes)\(\s*[^,]+,\s*"
    r'"(GET|POST|PUT|PATCH|DELETE)"\s*,\s*'
    r'(?:"((?:/v1/|/internal/|/health)[^"]*)"|([A-Za-z_][A-Za-z0-9_]*))',
    re.DOTALL,
)
BAR_UPLOAD_RE = re.compile(
    r"IdentityHttp\.uploadMultipart\(\s*[^,]+,\s*"
    r'(?:"((?:/v1/|/internal/|/health)[^"]*)"|([A-Za-z_][A-Za-z0-9_]*))',
    re.DOTALL,
)
KOTLIN_PATH_ASSIGN_RE = re.compile(
    r"(?:const val|val)\s+([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]+)?=\s*"
    r'"((?:/v1/|/internal/|/health)[^"?]*)'
)

COMMANDER_CONST_RE = re.compile(
    r'const val\s+([A-Z0-9_]+)\s*=\s*"((?:/v1/|/internal/|/health)[^"]*)"'
)
COMMANDER_CALL_RE = re.compile(
    r"\b(get|post|put|patch|delete)\(\s*(?:conVentana\(\s*)?Rutas\.([A-Za-z0-9_]+)"
)
COMMANDER_OPEN_RE = re.compile(r"open\(\s*Rutas\.([A-Z0-9_]+)\s*\)")
COMMANDER_REQUEST_METHOD_RE = re.compile(r'requestMethod\s*=\s*"(GET|POST|PUT|PATCH|DELETE)"')
COMMANDER_HELPERS = {
    "invitacionAceptar": "ME_INVITACIONES_ACEPTAR",
    "invitacionRechazar": "ME_INVITACIONES_RECHAZAR",
}

WEB_SRC_GLOBS = ("*.ts", "*.tsx", "*.js")


def openapi_ops(path: Path) -> dict[str, set[str]]:
    spec = json.loads(path.read_text(encoding="utf-8"))
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        raise ValueError(f"{path} no tiene objeto paths")
    ops: dict[str, set[str]] = {}
    for raw, item in paths.items():
        if not isinstance(item, dict):
            continue
        methods = {k.lower() for k in item if k.lower() in HTTP_METHODS}
        key = normalize(raw)
        ops.setdefault(key, set()).update(methods)
    return ops


def fusionar_concatenadas(src: str) -> str:
    """Une literales de ruta partidos por concatenación JS: `"/v1/x/" + tok + "/y"`
    -> `"/v1/x/*/y"`, para que la ruta completa sea comparable."""

    def _repl(m: re.Match) -> str:
        a, b = m.group(1), m.group(2)
        inner = a[1:-1] + "*" + b[1:-1]
        return '"' + inner + '"'

    return re.sub(
        r'("(?:/v1/|/internal/|/health)[^"]*")\s*\+\s*[^\"+\n]+\s*\+\s*("[^"]*")',
        _repl,
        src,
    )


def normalize(ruta: str) -> str:
    """Deja la ruta comparable: sin query, sin parámetros con nombre, sin slash final."""
    base = ruta.split("?", 1)[0].strip().rstrip("/")
    # Kotlin puede anexar una variable que contiene el query opcional:
    # ``/invitaciones$q``. No es otro segmento de ruta y no debe convertirse en ``*``.
    base = QUERY_SUFFIX_VAR_RE.sub("", base)
    return PARAM_RE.sub("*", base)


def es_interna(ruta: str) -> bool:
    return normalize(ruta).startswith("/internal")


def bullets(rutas: list[str], vacio: str = "_Ninguna._") -> str:
    if not rutas:
        return vacio
    return "\n".join(f"- `{r}`" for r in rutas)


def _fmt_op(method: str, ruta: str) -> str:
    return f"{method.upper()} {ruta}"


def _add_op(ops: set[tuple[str, str]], method: str, ruta: str) -> None:
    ops.add((method.lower(), normalize(ruta)))


def _kotlin_paths(src: str) -> dict[str, str]:
    return {m.group(1): m.group(2) for m in KOTLIN_PATH_ASSIGN_RE.finditer(src)}


def ops_bar(src: str) -> set[tuple[str, str]]:
    consts = _kotlin_paths(src)
    ops: set[tuple[str, str]] = set()
    for m in BAR_REQUEST_RE.finditer(src):
        method, literal, ident = m.group(1), m.group(2), m.group(3)
        ruta = literal or consts.get(ident or "", "")
        if ruta:
            _add_op(ops, method, ruta)
    for m in BAR_UPLOAD_RE.finditer(src):
        literal, ident = m.group(1), m.group(2)
        ruta = literal or consts.get(ident or "", "")
        if ruta:
            _add_op(ops, "post", ruta)
    return ops


def ops_commander(src: str) -> set[tuple[str, str]]:
    consts = {m.group(1): m.group(2) for m in COMMANDER_CONST_RE.finditer(src)}
    ops: set[tuple[str, str]] = set()
    for m in COMMANDER_CALL_RE.finditer(src):
        method, name = m.group(1), m.group(2)
        key = COMMANDER_HELPERS.get(name, name)
        ruta = consts.get(key, "")
        if ruta:
            _add_op(ops, method, ruta)
    for m in COMMANDER_OPEN_RE.finditer(src):
        ruta = consts.get(m.group(1), "")
        if not ruta:
            continue
        nearby = src[m.end() : m.end() + 400]
        method_m = COMMANDER_REQUEST_METHOD_RE.search(nearby)
        if method_m:
            _add_op(ops, method_m.group(1), ruta)
    return ops


FETCH_START_RE = re.compile(r"\b(?:fetchJson|fetch)\s*\(")
JS_ASSIGN_RE = re.compile(r"(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^;]+);")


def _paths_in(text: str) -> list[str]:
    fused = fusionar_concatenadas(text)
    return [m.group(1) for m in RUTA_RE.finditer(fused)] + [
        m.group(1) for m in TEMPLATE_PATH_RE.finditer(fused)
    ]


def _scan_js(chunk: str, until_fetch_end: bool) -> int:
    """Índice donde termina el fetch o el primer argumento, ignorando strings."""
    depth = 0
    in_str: str | None = None
    for i, ch in enumerate(chunk):
        if in_str:
            if ch == in_str and (i == 0 or chunk[i - 1] != "\\"):
                in_str = None
            continue
        if ch in "\"'`":
            in_str = ch
            continue
        if ch in "([{":
            depth += 1
        elif ch == ")" and depth == 0 and until_fetch_end:
            return i
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0 and not until_fetch_end:
            return i
    return len(chunk)


def _split_fetch_args(chunk: str) -> tuple[str, str]:
    """Separa el primer argumento de fetch(...) del resto (options)."""
    inside = chunk[: _scan_js(chunk, until_fetch_end=True)]
    comma = _scan_js(inside, until_fetch_end=False)
    if comma < len(inside):
        return inside[:comma], inside[comma + 1 :]
    return inside, ""


def ops_web(src: str) -> set[tuple[str, str]]:
    fused = fusionar_concatenadas(src)
    assigns = {m.group(1): m.group(2) for m in JS_ASSIGN_RE.finditer(fused)}
    ops: set[tuple[str, str]] = set()
    for m in FETCH_START_RE.finditer(fused):
        first, rest = _split_fetch_args(fused[m.end() :])
        rutas = _paths_in(first)
        ident = first.strip()
        if not rutas and ident in assigns:
            rutas = _paths_in(assigns[ident])
        method_m = METHOD_LITERAL_RE.search(rest)
        method = method_m.group(1).lower() if method_m else "get"
        for ruta in rutas:
            _add_op(ops, method, ruta)
    return ops


def client_ops(fuentes: list[str], dialect: str) -> set[tuple[str, str]]:
    ops: set[tuple[str, str]] = set()
    for fuente in fuentes:
        if dialect == "bar":
            ops.update(ops_bar(fuente))
        elif dialect == "commander":
            ops.update(ops_commander(fuente))
        else:
            ops.update(ops_web(fuente))
    return ops


def expand_srcs(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for path in paths:
        if path.is_dir():
            for glob in WEB_SRC_GLOBS:
                out.extend(sorted(path.rglob(glob)))
        else:
            out.append(path)
    return out


@dataclass
class Informe:
    markdown: str
    fallos: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _comprobar_cliente(
    nombre: str,
    ops: set[tuple[str, str]],
    spec: dict[str, set[str]],
    fallos: list[str],
) -> list[str]:
    usadas: list[str] = []
    for method, ruta in sorted(ops, key=lambda item: (item[1], item[0])):
        if ruta not in spec:
            fallos.append(f"{nombre} pide {_fmt_op(method, ruta)} que el Server ya no expone")
            continue
        if method not in spec[ruta]:
            fallos.append(
                f"{nombre} pide {_fmt_op(method, ruta)} pero el spec no declara {method.upper()}"
            )
            continue
        usadas.append(_fmt_op(method, ruta))
    return usadas


def comprobar(
    camareros_openapi: Path,
    negocio_openapi: Path,
    bar_srcs: list[str],
    commander_srcs: list[str],
    web_srcs: list[str],
    combinacion: dict[str, str] | None = None,
    contracts_dir: Path | None = None,
) -> Informe:
    spec: dict[str, set[str]] = {}
    for fuente in (openapi_ops(camareros_openapi), openapi_ops(negocio_openapi)):
        for ruta, methods in fuente.items():
            spec.setdefault(ruta, set()).update(methods)

    bar = client_ops(bar_srcs, "bar")
    commander = client_ops(commander_srcs, "commander")
    web = client_ops(web_srcs, "web")

    fallos: list[str] = []
    warnings: list[str] = []

    usadas_bar = _comprobar_cliente("Bar", bar, spec, fallos)
    usadas_commander = _comprobar_cliente("Commander", commander, spec, fallos)
    usadas_web = _comprobar_cliente(
        "Webs (web-camareros + web-negocio + web-cfc)", web, spec, fallos
    )

    if contracts_dir is not None:
        camareros_spec = json.loads(camareros_openapi.read_text(encoding="utf-8"))
        negocio_spec = json.loads(negocio_openapi.read_text(encoding="utf-8"))
        packs = contract_pack.load_packs(contracts_dir)
        fallos.extend(
            contract_pack.comprobar_pack(
                camareros_spec,
                negocio_spec,
                packs,
                {
                    "Bar": bar,
                    "Commander": commander,
                    "Webs": web,
                },
                {
                    "Bar": bar_srcs,
                    "Commander": commander_srcs,
                    "Webs": web_srcs,
                },
                normalize,
            )
        )

    usadas_por_cliente = {ruta for _, ruta in bar | commander | web}
    internas = sorted(r for r in spec if es_interna(r))
    nadie = sorted(r for r in spec if r not in usadas_por_cliente and not es_interna(r))

    for ruta in nadie:
        warnings.append(f"Ruta pública sin consumidor de familia: {ruta}")

    combinacion_md = ""
    if combinacion:
        server_sha = combinacion.get("server") or combinacion.get("identity", "")
        combinacion_md = f"""## Combinación verificada

- Server: `{server_sha}`
- Bar (`{combinacion.get("bar_ref", "main")}`): `{combinacion.get("bar", "")}`
- Commander (`{combinacion.get("commander_ref", "main")}`): `{combinacion.get("commander", "")}`

"""

    markdown = f"""# Family contracts — informe (Server)

Rojo si un cliente pide un path que el Server ya no expone, un verbo que ese
path no declara, o un payload que no valida contra el pack OpenAPI + fixtures
del servicio identity. Lo no usado no falla el job: es señal para decidir ítem o deuda.
La normalización canónica es `normalize() -> *` (`{{param}}` y `$var` de segmento).

{combinacion_md}## Operaciones usadas por Bar

{bullets(usadas_bar)}

## Operaciones usadas por Commander

{bullets(usadas_commander)}

## Operaciones usadas por las webs (web-camareros + web-negocio + web-cfc)

{bullets(usadas_web)}

## Rutas internas (auto-llamadas entre servicios)

{bullets(internas)}

## Rutas públicas sin consumidor de familia (aviso)

{bullets(nadie)}

## Error

{bullets(fallos, "_Ninguno._")}
"""
    return Informe(markdown=markdown.strip() + "\n", fallos=fallos, warnings=warnings)


def escribir_informe(informe: Informe) -> None:
    sys.stdout.write(informe.markdown)
    if not informe.markdown.endswith("\n"):
        sys.stdout.write("\n")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(informe.markdown)
            if not informe.markdown.endswith("\n"):
                fh.write("\n")
    for msg in informe.warnings:
        print(f"::warning::{msg}")


def escribir_manifiesto(path: Path, combinacion: dict[str, str]) -> None:
    server = combinacion.get("server") or combinacion.get("identity", "")
    payload = {
        "server": server,
        "identity": server,
        "bar": combinacion.get("bar", ""),
        "commander": combinacion.get("commander", ""),
        "refs": {
            "bar": combinacion.get("bar_ref", "main"),
            "commander": combinacion.get("commander_ref", "main"),
        },
        "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _fixtures_ok() -> tuple[dict, dict, str, str, str]:
    camareros = {
        "paths": {
            "/v1/auth/login": {"post": {}},
            "/v1/camareros/me": {"get": {}, "patch": {}, "delete": {}},
            "/v1/camareros/me/qr": {"get": {}},
            "/v1/camareros/me/renovar": {"post": {}},
            "/v1/camareros/me/revocar": {"post": {}},
            "/v1/camareros/me/foto": {"get": {}, "post": {}, "delete": {}},
            "/v1/camareros/me/establecimientos": {"get": {}},
            "/v1/camareros/me/visibilidad": {"get": {}, "put": {}},
            "/v1/camareros/registro": {"post": {}},
            "/v1/camareros/ficha": {"get": {}},
            "/v1/keys/qr": {"get": {}},
            "/v1/meta": {"get": {}},
            "/health": {"get": {}},
            "/internal/camareros/buscar": {"get": {}},
        }
    }
    negocio = {
        "paths": {
            "/v1/auth/negocio/login": {"post": {}},
            "/v1/auth/negocio/registro": {"post": {}},
            "/v1/auth/negocio/me/logo": {"get": {}, "post": {}},
            "/v1/establecimientos": {"post": {}},
            "/v1/establecimientos/mios": {"get": {}},
            "/v1/establecimientos/{establecimiento_id}/camareros/buscar": {"get": {}},
            "/v1/establecimientos/{establecimiento_id}/miembros": {"get": {}},
            "/v1/establecimientos/{establecimiento_id}/miembros/qr": {"post": {}},
            "/v1/establecimientos/{establecimiento_id}/miembros/{camarero_id}": {"delete": {}},
            "/v1/establecimientos/{establecimiento_id}/invitaciones": {"get": {}, "post": {}},
            "/v1/establecimientos/{establecimiento_id}/invitaciones/{invitacion_id}/revocar": {
                "post": {}
            },
            "/v1/establecimientos/{establecimiento_id}/layout": {"get": {}, "put": {}},
            "/v1/establecimientos/{establecimiento_id}/galeria/{imagen_id}": {
                "get": {},
                "delete": {},
            },
            "/v1/establecimientos/{establecimiento_id}/fondos/{slot}": {
                "get": {},
                "post": {},
                "delete": {},
            },
            "/v1/negocio/carta": {"get": {}},
            "/v1/negocio/web": {"get": {}},
            "/v1/invitaciones/{token}/aceptar": {"post": {}},
            "/v1/invitaciones/{token}/rechazar": {"post": {}},
        }
    }
    bar = """
        const val LOGO_PATH: String = "/v1/auth/negocio/me/logo"
        IdentityHttp.request(baseUrl, "POST", "/v1/auth/negocio/registro", ...)
        IdentityHttp.request(baseUrl, "POST", "/v1/auth/negocio/login", ...)
        IdentityHttp.uploadMultipart(baseUrl, LOGO_PATH, "logo", "logo.webp", bytes, mimetype, token)
        IdentityHttp.requestBytes(baseUrl, "GET", LOGO_PATH, token)
        IdentityHttp.request(baseUrl, "GET", "/v1/establecimientos/mios", ...)
        IdentityHttp.request(baseUrl, "POST", "/v1/establecimientos", ...)
        IdentityHttp.request(baseUrl, "POST", "/v1/establecimientos/$id/miembros/qr", ...)
        IdentityHttp.request(baseUrl, "GET", "/v1/establecimientos/$id/camareros/buscar?email=$q", ...)
        val q = estado?.let { "?estado=$it" } ?: ""
        IdentityHttp.request(baseUrl, "GET", "/v1/establecimientos/$id/invitaciones$q", ...)
        IdentityHttp.request(baseUrl, "POST", "/v1/establecimientos/$id/invitaciones", ...)
        IdentityHttp.request(baseUrl, "POST", "/v1/establecimientos/$id/invitaciones/$invitacionId/revocar", ...)
        IdentityHttp.request(baseUrl, "GET", "/v1/establecimientos/$id/miembros", ...)
        IdentityHttp.request(baseUrl, "DELETE", "/v1/establecimientos/$id/miembros/$camareroId", ...)
        IdentityHttp.request(baseUrl, "PUT", "/v1/establecimientos/$id/layout", ...)
        IdentityHttp.requestBytes(
            baseUrl, "GET", "/v1/establecimientos/$id/galeria/$imagenId", token,
        )
        IdentityHttp.request(baseUrl, "DELETE", "/v1/establecimientos/$id/galeria/$imagenId", ...)
        IdentityHttp.uploadMultipart(baseUrl, "/v1/establecimientos/$id/fondos/${slot}", ...)
        IdentityHttp.request(baseUrl, "DELETE", "/v1/establecimientos/$id/fondos/${slot}", ...)
    """
    commander = """
        object Rutas {
            const val REGISTRO = "/v1/camareros/registro"
            const val LOGIN = "/v1/auth/login"
            const val ME = "/v1/camareros/me"
            const val ME_QR = "/v1/camareros/me/qr"
            const val ME_RENOVAR = "/v1/camareros/me/renovar"
            const val ME_REVOCAR = "/v1/camareros/me/revocar"
            const val ME_FOTO = "/v1/camareros/me/foto"
            const val ME_ESTABLECIMIENTOS = "/v1/camareros/me/establecimientos"
            const val ME_VISIBILIDAD = "/v1/camareros/me/visibilidad"
        }
        post(Rutas.REGISTRO, body)
        post(Rutas.LOGIN, body)
        get(Rutas.ME, token)
        get(Rutas.ME_QR, token)
        post(Rutas.ME_RENOVAR, "{}", token)
        post(Rutas.ME_REVOCAR, body, token)
        get(Rutas.ME_ESTABLECIMIENTOS, token)
        get(Rutas.ME_VISIBILIDAD, token)
        put(Rutas.ME_VISIBILIDAD, body, token)
        val conexion = open(Rutas.ME_FOTO)
        conexion.requestMethod = "GET"
        val upload = open(Rutas.ME_FOTO)
        upload.requestMethod = "POST"
        delete(Rutas.ME_FOTO, token)
    """
    web = """
        fetchJson(camarerosApiBase + "/v1/camareros/ficha?qr=" + encodeURIComponent(qr), {
          headers: { "Accept": "application/json" },
        })
        const url = `${API_BASE}/v1/negocio/web?slug=${encodeURIComponent(slug)}`;
        const res = await fetch(url, { headers: { Accept: "application/json" } });
        fetch(negocioApiBase + "/v1/negocio/carta?slug=" + ...)
        fetchJson(negocioApiBase + "/v1/invitaciones/" + token + "/aceptar", {
          method: "POST",
        })
        fetchJson(negocioApiBase + "/v1/invitaciones/" + token + "/rechazar", {
          method: "POST",
        })
    """
    return camareros, negocio, bar, commander, web


def selftest() -> int:
    camareros, negocio, bar, commander, web = _fixtures_ok()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cam = tmp_path / "camareros.json"
        neg = tmp_path / "negocio.json"
        cam.write_text(json.dumps(camareros), encoding="utf-8")
        neg.write_text(json.dumps(negocio), encoding="utf-8")

        informe = comprobar(cam, neg, [bar], [commander], [web])
        if informe.fallos:
            print("SELFTEST FAIL: fixtures completas deberían pasar", file=sys.stderr)
            print("\n".join(informe.fallos), file=sys.stderr)
            return 1
        md = informe.markdown
        if "/v1/meta" not in md or "/v1/keys/qr" not in md:
            print("SELFTEST FAIL: el informe debía listar públicas no usadas", file=sys.stderr)
            return 1
        if "/internal/camareros/buscar" not in md:
            print("SELFTEST FAIL: el informe debía listar internas", file=sys.stderr)
            return 1
        if not any("/v1/establecimientos/*/miembros/qr" in line for line in md.splitlines()):
            print("SELFTEST FAIL: debía normalizar $id en /miembros/qr", file=sys.stderr)
            return 1
        if not any("/v1/establecimientos/*/camareros/buscar" in line for line in md.splitlines()):
            print("SELFTEST FAIL: debía normalizar query ?email= y $id", file=sys.stderr)
            return 1
        if not any("/v1/establecimientos/*/galeria/*" in line for line in md.splitlines()):
            print(
                "SELFTEST FAIL: debía normalizar $id/galeria/$imagenId a */galeria/*",
                file=sys.stderr,
            )
            return 1
        if not any("/v1/establecimientos/*/fondos/*" in line for line in md.splitlines()):
            print(
                "SELFTEST FAIL: debía normalizar fondos/${slot} a */fondos/* (no */fondos/$*)",
                file=sys.stderr,
            )
            return 1
        if not any("`GET /v1/negocio/web`" in line for line in md.splitlines()):
            print("SELFTEST FAIL: web-negocio debía contar GET /v1/negocio/web", file=sys.stderr)
            return 1
        if any(
            w.startswith("Ruta pública sin consumidor") and "/v1/negocio/web" in w
            for w in informe.warnings
        ):
            print("SELFTEST FAIL: /v1/negocio/web no debía quedar sin consumidor", file=sys.stderr)
            return 1
        if not any(
            w.startswith("Ruta pública sin consumidor") and "/v1/meta" in w
            for w in informe.warnings
        ):
            print("SELFTEST FAIL: debía avisar de /v1/meta sin consumidor", file=sys.stderr)
            return 1
        if any(es_interna(w.split(": ", 1)[-1]) for w in informe.warnings):
            print("SELFTEST FAIL: no debe avisar de rutas internas", file=sys.stderr)
            return 1

        # Ruta que un cliente pide pero el spec ya no tiene -> ROJO.
        broken = dict(camareros)
        broken["paths"] = dict(camareros["paths"])
        del broken["paths"]["/v1/auth/login"]
        cam.write_text(json.dumps(broken), encoding="utf-8")
        fallos = comprobar(cam, neg, [bar], [commander], [web]).fallos
        if not any("Commander" in f and "login" in f for f in fallos):
            print("SELFTEST FAIL: debía detectar /v1/auth/login ausente", file=sys.stderr)
            return 1

        # Verbo que el path no declara (GET a un path solo-POST) -> ROJO.
        cam.write_text(json.dumps(camareros), encoding="utf-8")
        mal_metodo = commander + "\n        get(Rutas.LOGIN, token)\n"
        fallos_metodo = comprobar(cam, neg, [bar], [mal_metodo], [web]).fallos
        if not any("GET /v1/auth/login" in f and "no declara GET" in f for f in fallos_metodo):
            print("SELFTEST FAIL: debía detectar GET a un path solo-POST", file=sys.stderr)
            return 1

        # Ruta de Bar que ya no existe -> ROJO.
        broken2 = dict(negocio)
        broken2["paths"] = dict(negocio["paths"])
        del broken2["paths"]["/v1/establecimientos/{establecimiento_id}/layout"]
        neg.write_text(json.dumps(broken2), encoding="utf-8")
        fallos2 = comprobar(cam, neg, [bar], [commander], [web]).fallos
        if not any("Bar" in f and "layout" in f for f in fallos2):
            print("SELFTEST FAIL: debía detectar layout ausente para Bar", file=sys.stderr)
            return 1

        # Template Kotlin ${...}: si falta la ruta en OpenAPI -> ROJO.
        # Confirma que fondos/${slot} se normaliza a fondos/* (no a fondos/$*)
        # y que la ruta normalizada se valida contra OpenAPI.
        broken3 = dict(negocio)
        broken3["paths"] = dict(negocio["paths"])
        del broken3["paths"]["/v1/establecimientos/{establecimiento_id}/fondos/{slot}"]
        neg.write_text(json.dumps(broken3), encoding="utf-8")
        fallos3 = comprobar(cam, neg, [bar], [commander], [web]).fallos
        if not any("Bar" in f and "fondos" in f for f in fallos3):
            print(
                "SELFTEST FAIL: debía detectar fondos/${slot} sin ruta en OpenAPI"
                " (no produce $* residual)",
                file=sys.stderr,
            )
            return 1

        mut = contract_pack.selftest_mutations()
        if mut:
            print("SELFTEST FAIL: mutaciones del pack", file=sys.stderr)
            print("\n".join(mut), file=sys.stderr)
            return 1

        print("SELFTEST OK")
        return 0


def _combinacion_desde_args(args: argparse.Namespace) -> dict[str, str] | None:
    server = (getattr(args, "server_sha", "") or args.identity_sha) or ""
    if not any((server, args.bar_sha, args.commander_sha, args.manifest_out)):
        return None
    return {
        "server": server,
        "identity": server,
        "bar": args.bar_sha or "",
        "commander": args.commander_sha or "",
        "bar_ref": args.bar_ref,
        "commander_ref": args.commander_ref,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camareros-openapi", type=Path)
    parser.add_argument("--negocio-openapi", type=Path)
    parser.add_argument("--bar-src", action="append", default=[])
    parser.add_argument("--commander-src", action="append", default=[])
    parser.add_argument("--web-src", action="append", default=[])
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--write-pack", action="store_true")
    parser.add_argument("--contracts-dir", type=Path, default=DEFAULT_CONTRACTS_DIR)
    parser.add_argument("--manifest-out", type=Path)
    parser.add_argument("--server-sha", default="")
    parser.add_argument(
        "--identity-sha",
        default="",
        help="Alias legado de --server-sha (SHA del Server, no del servicio)",
    )
    parser.add_argument("--bar-sha", default="")
    parser.add_argument("--commander-sha", default="")
    parser.add_argument("--bar-ref", default="main")
    parser.add_argument("--commander-ref", default="main")
    args = parser.parse_args()

    if args.selftest:
        return selftest()

    if args.write_pack:
        if not args.camareros_openapi or not args.negocio_openapi:
            parser.error("--write-pack requiere --camareros-openapi y --negocio-openapi")
        camareros = json.loads(args.camareros_openapi.read_text(encoding="utf-8"))
        negocio = json.loads(args.negocio_openapi.read_text(encoding="utf-8"))
        contract_pack.write_pack(args.contracts_dir, camareros, negocio)
        print(f"Pack escrito en {args.contracts_dir}", file=sys.stderr)
        return 0

    if not all(
        (
            args.camareros_openapi,
            args.negocio_openapi,
            args.bar_src,
            args.commander_src,
            args.web_src,
        )
    ):
        parser.error(
            "Se requieren --camareros-openapi, --negocio-openapi, "
            "--bar-src (1+), --commander-src (1+) y --web-src (1+)"
        )

    bar_srcs = [Path(p).read_text(encoding="utf-8") for p in args.bar_src]
    commander_srcs = [Path(p).read_text(encoding="utf-8") for p in args.commander_src]
    web_paths = expand_srcs([Path(p) for p in args.web_src])
    if not web_paths:
        parser.error("Ningún fichero web coincidió con --web-src")
    web_srcs = [p.read_text(encoding="utf-8") for p in web_paths]
    combinacion = _combinacion_desde_args(args)

    informe = comprobar(
        args.camareros_openapi,
        args.negocio_openapi,
        bar_srcs,
        commander_srcs,
        web_srcs,
        combinacion=combinacion,
        contracts_dir=args.contracts_dir,
    )
    escribir_informe(informe)
    if args.manifest_out and combinacion:
        escribir_manifiesto(args.manifest_out, combinacion)
    if informe.fallos:
        for f in informe.fallos:
            print(f"::error::{f}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
