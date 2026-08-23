"""Pack de contrato del servicio identity (APIs camareros + negocio).

El producto es el Server. Este módulo valida fixtures JSON contra el OpenAPI
del servicio identity: request, respuesta 2xx y un error ``identity.*`` cuando
la operación declara ErrorResponse. También comprueba pistas de Bearer y que
las claves required del request aparezcan en el fuente del cliente.

No ejecuta Kotlin/JS ni sustituye el smoke E2E.
"""

from __future__ import annotations

import copy
import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jsonschema.exceptions import ValidationError
from jsonschema.validators import Draft202012Validator

NormalizeFn = Callable[[str], str]

HTTP_METHODS = frozenset({"get", "put", "post", "delete", "patch", "options", "head", "trace"})
IDENTITY_CODE_RE = re.compile(r"^identity\.[a-z0-9_]+$")
BEARER_HINT_RE = re.compile(r"Authorization|Bearer|IdentityHttp\.", re.I)
ERROR_STATUSES = ("400", "401", "403", "404", "409", "410", "429", "503")
SUCCESS_STATUSES = ("200", "201")
SKIP_SCHEMA_KEYS = {
    "example",
    "examples",
    "discriminator",
    "xml",
    "deprecated",
    "readOnly",
    "writeOnly",
    "externalDocs",
    "contentMediaType",
    "contentEncoding",
}
GENERIC_REQUIRED_SKIP = frozenset({"id"})
ERROR_FIXTURE = {
    "code": "identity.credenciales_invalidas",
    "detail": "Email o contraseña incorrectos",
}
UUID_EXAMPLE = "3fa85f64-5717-4562-b3fc-2c963f66afa6"


def _deref(spec: dict[str, Any], ref: str) -> Any:
    node: Any = spec
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def _deep_merge(base: Any, overlay: Any) -> Any:
    if isinstance(base, dict) and isinstance(overlay, dict):
        out = dict(base)
        for key, value in overlay.items():
            out[key] = _deep_merge(out[key], value) if key in out else value
        return out
    return overlay


def resolve_refs(node: Any, spec: dict[str, Any], seen: tuple[str, ...] = ()) -> Any:
    if isinstance(node, list):
        return [resolve_refs(item, spec, seen) for item in node]
    if not isinstance(node, dict):
        return node
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith("#/"):
        if ref in seen:
            return {"type": "object"}
        target = resolve_refs(_deref(spec, ref), spec, (*seen, ref))
        rest = {k: resolve_refs(v, spec, seen) for k, v in node.items() if k != "$ref"}
        return _deep_merge(target, rest) if rest else target
    return {k: resolve_refs(v, spec, seen) for k, v in node.items() if k not in SKIP_SCHEMA_KEYS}


def json_schema_from_content(content: dict[str, Any] | None) -> dict[str, Any] | None:
    if not content:
        return None
    for key, body in content.items():
        if key.split(";")[0].strip() == "application/json" and isinstance(body, dict):
            schema = body.get("schema")
            return schema if isinstance(schema, dict) else None
    return None


def request_schema(op: dict[str, Any]) -> dict[str, Any] | None:
    body = op.get("requestBody")
    if not isinstance(body, dict):
        return None
    return json_schema_from_content(body.get("content"))


def response_schema(op: dict[str, Any], *statuses: str) -> dict[str, Any] | None:
    responses = op.get("responses")
    if not isinstance(responses, dict):
        return None
    for status in statuses:
        item = responses.get(status)
        if not isinstance(item, dict):
            continue
        schema = json_schema_from_content(item.get("content"))
        if schema is not None:
            return schema
    return None


def error_schema(op: dict[str, Any]) -> dict[str, Any] | None:
    responses = op.get("responses")
    if not isinstance(responses, dict):
        return None
    for status in ERROR_STATUSES:
        item = responses.get(status)
        if not isinstance(item, dict):
            continue
        schema = json_schema_from_content(item.get("content"))
        if not isinstance(schema, dict):
            continue
        ref = schema.get("$ref", "")
        if isinstance(ref, str) and ref.endswith("/ErrorResponse"):
            return schema
        props = schema.get("properties")
        if isinstance(props, dict) and "code" in props and "detail" in props:
            return schema
    return None


def op_security_names(spec: dict[str, Any], op: dict[str, Any]) -> list[str]:
    security = op["security"] if "security" in op else spec.get("security")
    if not security:
        return []
    names: list[str] = []
    for item in security:
        if isinstance(item, dict):
            names.extend(item.keys())
    return names


def requires_bearer(spec: dict[str, Any], op: dict[str, Any]) -> bool:
    schemes = spec.get("components", {}).get("securitySchemes", {})
    for name in op_security_names(spec, op):
        scheme = schemes.get(name, {}) if isinstance(schemes, dict) else {}
        if (
            isinstance(scheme, dict)
            and scheme.get("type") == "http"
            and str(scheme.get("scheme", "")).lower() == "bearer"
        ):
            return True
        if name.lower() in {"httpbearer", "bearer"}:
            return True
    return False


def example_from_schema(schema: dict[str, Any], spec: dict[str, Any]) -> Any:
    return _example(resolve_refs(schema, spec))


def _example(schema: dict[str, Any]) -> Any:
    if not isinstance(schema, dict):
        return "x"
    if "const" in schema:
        return schema["const"]
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema or "oneOf" in schema:
        alts = schema.get("anyOf") or schema.get("oneOf") or []
        non_null = [alt for alt in alts if isinstance(alt, dict) and alt.get("type") != "null"]
        pick = non_null[0] if non_null else (alts[0] if alts else {"type": "string"})
        return _example(pick) if isinstance(pick, dict) else pick
    if "allOf" in schema:
        acc: dict[str, Any] = {}
        last: Any = None
        for part in schema["allOf"]:
            val = _example(part) if isinstance(part, dict) else part
            last = val
            if isinstance(val, dict):
                acc.update(val)
            else:
                acc = val  # type: ignore[assignment]
        return acc if acc else last
    types = schema.get("type")
    if isinstance(types, list):
        types = next((t for t in types if t != "null"), types[0] if types else "string")
    if types is None and ("properties" in schema or "required" in schema):
        types = "object"
    if types == "object" or (types is None and "properties" in schema):
        props = schema.get("properties") or {}
        required = list(schema.get("required") or [])
        obj: dict[str, Any] = {}
        for key in required:
            prop = props.get(key, {"type": "string"})
            obj[key] = _example(prop) if isinstance(prop, dict) else prop
        return obj
    if types == "array":
        items = schema.get("items") or {}
        min_items = int(schema.get("minItems") or 0)
        if min_items <= 0:
            return []
        item = _example(items) if isinstance(items, dict) else items
        return [item] * min_items
    if types in {"integer", "number"}:
        minimum = schema.get("minimum", 0)
        return int(minimum) if types == "integer" else float(minimum)
    if types == "boolean":
        return False
    if types == "null":
        return None
    fmt = schema.get("format")
    if fmt == "uuid":
        return UUID_EXAMPLE
    if fmt == "email":
        return "ana@example.com"
    if fmt in {"date-time", "datetime"}:
        return "2026-08-23T12:00:00Z"
    if fmt == "date":
        return "2026-08-23"
    if fmt in {"uri", "url"}:
        return "https://example.com/"
    patterned = _example_from_pattern(schema.get("pattern"))
    if patterned is not None:
        return patterned
    min_length = int(schema.get("minLength") or 0)
    if min_length:
        return "x" * min_length
    return "x"


def _example_from_pattern(pattern: Any) -> str | None:
    if not isinstance(pattern, str):
        return None
    inner = pattern
    if inner.startswith("^") and inner.endswith("$"):
        inner = inner[1:-1]
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    parts = inner.split("|")
    if parts and all(re.fullmatch(r"[A-Za-z0-9_\-]+", part) for part in parts):
        return parts[0]
    return None


def validate_instance(instance: Any, schema: dict[str, Any], spec: dict[str, Any]) -> str | None:
    resolved = resolve_refs(schema, spec)
    try:
        Draft202012Validator(resolved).validate(instance)
    except ValidationError as exc:
        return exc.message
    return None


def required_request_keys(schema: dict[str, Any], spec: dict[str, Any]) -> list[str]:
    resolved = resolve_refs(schema, spec)
    return [k for k in resolved.get("required") or [] if k not in GENERIC_REQUIRED_SKIP]


def find_operation(
    spec: dict[str, Any], method: str, norm_path: str, normalize: NormalizeFn
) -> tuple[str, dict[str, Any]] | None:
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return None
    method_l = method.lower()
    for raw, item in paths.items():
        if not isinstance(item, dict):
            continue
        if normalize(raw) != norm_path:
            continue
        op = item.get(method_l)
        if isinstance(op, dict):
            return raw, op
    return None


def pack_entry_for_op(spec: dict[str, Any], op: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {}
    req = request_schema(op)
    if req is not None:
        entry["request"] = example_from_schema(req, spec)
    resp = response_schema(op, *SUCCESS_STATUSES)
    if resp is not None:
        entry["response_200"] = example_from_schema(resp, spec)
    if error_schema(op) is not None:
        entry["error"] = dict(ERROR_FIXTURE)
    if requires_bearer(spec, op):
        entry["security"] = ["HTTPBearer"]
    return entry


def build_pack(spec: dict[str, Any]) -> dict[str, Any]:
    pack: dict[str, Any] = {}
    paths = spec.get("paths")
    if not isinstance(paths, dict):
        return pack
    for raw, item in paths.items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method.lower() not in HTTP_METHODS or not isinstance(op, dict):
                continue
            pack[f"{method.upper()} {raw}"] = pack_entry_for_op(spec, op)
    return pack


def load_packs(contracts_dir: Path) -> dict[str, dict[str, Any]]:
    index = json.loads((contracts_dir / "index.json").read_text(encoding="utf-8"))
    packs_meta = index.get("packs") or {}
    out: dict[str, dict[str, Any]] = {}
    for name, rel in packs_meta.items():
        out[name] = json.loads((contracts_dir / rel).read_text(encoding="utf-8"))
    return out


def _assert_pack_valid(spec: dict[str, Any], pack: dict[str, Any]) -> None:
    for key, entry in pack.items():
        method, _, raw = key.partition(" ")
        paths = spec.get("paths") or {}
        item = paths.get(raw) if isinstance(paths, dict) else None
        op = item.get(method.lower()) if isinstance(item, dict) else None
        if not isinstance(op, dict) or not isinstance(entry, dict):
            raise ValueError(f"pack inconsistente: {key}")
        fallos = validate_entry_against_op(spec, op, entry, key)
        if fallos:
            raise ValueError("; ".join(fallos))


def write_pack(contracts_dir: Path, camareros: dict[str, Any], negocio: dict[str, Any]) -> None:
    contracts_dir.mkdir(parents=True, exist_ok=True)
    cam_pack = build_pack(camareros)
    neg_pack = build_pack(negocio)
    _assert_pack_valid(camareros, cam_pack)
    _assert_pack_valid(negocio, neg_pack)
    (contracts_dir / "camareros.ops.json").write_text(
        json.dumps(cam_pack, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (contracts_dir / "negocio.ops.json").write_text(
        json.dumps(neg_pack, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    index = {
        "version": 1,
        "product": "PersonalHostel Server",
        "service": "identity",
        "packs": {
            "camareros": "camareros.ops.json",
            "negocio": "negocio.ops.json",
        },
    }
    (contracts_dir / "index.json").write_text(
        json.dumps(index, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _lookup_entry(
    packs: dict[str, dict[str, Any]], method: str, norm_path: str, normalize: NormalizeFn
) -> tuple[str, dict[str, Any]] | None:
    method_u = method.upper()
    for pack in packs.values():
        for key, entry in pack.items():
            meth, _, raw = key.partition(" ")
            if meth == method_u and normalize(raw) == norm_path and isinstance(entry, dict):
                return key, entry
    return None


def _validate_error_fixture(
    entry: dict[str, Any], schema: dict[str, Any], spec: dict[str, Any]
) -> list[str]:
    fallos: list[str] = []
    err = entry.get("error")
    if not isinstance(err, dict):
        fallos.append("falta fixture de error identity.*")
        return fallos
    code = err.get("code")
    if not isinstance(code, str) or not IDENTITY_CODE_RE.match(code):
        fallos.append(f"error.code no es identity.*: {code!r}")
    msg = validate_instance(err, schema, spec)
    if msg:
        fallos.append(f"fixture error inválido: {msg}")
    return fallos


def validate_entry_against_op(
    spec: dict[str, Any],
    op: dict[str, Any],
    entry: dict[str, Any],
    label: str,
) -> list[str]:
    fallos: list[str] = []
    req = request_schema(op)
    if req is not None:
        if "request" not in entry:
            fallos.append(f"{label}: falta fixture request")
        else:
            msg = validate_instance(entry["request"], req, spec)
            if msg:
                fallos.append(f"{label}: request inválido: {msg}")
    resp = response_schema(op, *SUCCESS_STATUSES)
    if resp is not None:
        if "response_200" not in entry:
            fallos.append(f"{label}: falta fixture response_200")
        else:
            msg = validate_instance(entry["response_200"], resp, spec)
            if msg:
                fallos.append(f"{label}: response_200 inválido: {msg}")
    err_s = error_schema(op)
    if err_s is not None:
        for item in _validate_error_fixture(entry, err_s, spec):
            fallos.append(f"{label}: {item}")
    bearer_spec = requires_bearer(spec, op)
    bearer_pack = "HTTPBearer" in (entry.get("security") or [])
    if bearer_spec != bearer_pack:
        fallos.append(
            f"{label}: security del pack ({bearer_pack}) no coincide con OpenAPI ({bearer_spec})"
        )
    return fallos


def client_has_bearer_hint(sources: list[str]) -> bool:
    return bool(BEARER_HINT_RE.search("\n".join(sources)))


def missing_required_in_sources(keys: list[str], sources: list[str]) -> list[str]:
    blob = "\n".join(sources)
    return [key for key in keys if key not in blob]


def comprobar_pack(
    camareros_spec: dict[str, Any],
    negocio_spec: dict[str, Any],
    packs: dict[str, dict[str, Any]],
    usadas_por_cliente: dict[str, set[tuple[str, str]]],
    fuentes_por_cliente: dict[str, list[str]],
    normalize: NormalizeFn,
) -> tuple[list[str], list[str]]:
    """Valida fixtures del pack para cada operación usada por un cliente.

    Las claves required ausentes en Bar/Commander son aviso: el sparse-checkout
    no trae data classes Kotlin. En las webs de este repo siguen siendo rojo.
    """
    fallos: list[str] = []
    avisos: list[str] = []
    specs = (camareros_spec, negocio_spec)
    bearer_clients: dict[str, bool] = {}

    for cliente, ops in usadas_por_cliente.items():
        fuentes = fuentes_por_cliente.get(cliente, [])
        for method, norm_path in sorted(ops):
            found: tuple[str, dict[str, Any], dict[str, Any]] | None = None
            for spec in specs:
                hit = find_operation(spec, method, norm_path, normalize)
                if hit is None:
                    continue
                raw, op = hit
                found = (raw, op, spec)
                break
            if found is None:
                continue
            raw, op, spec = found
            label = f"{cliente} {method.upper()} {raw}"
            lookup = _lookup_entry(packs, method, norm_path, normalize)
            if lookup is None:
                fallos.append(f"{label}: el pack no tiene fixture")
                continue
            _key, entry = lookup
            fallos.extend(validate_entry_against_op(spec, op, entry, label))
            if requires_bearer(spec, op):
                bearer_clients[cliente] = True
            req = request_schema(op)
            if req is not None and fuentes:
                keys = required_request_keys(req, spec)
                missing = missing_required_in_sources(keys, fuentes)
                if missing:
                    msg = f"{label}: el fuente no menciona required {missing}"
                    if cliente in {"Bar", "Commander"}:
                        avisos.append(msg)
                    else:
                        fallos.append(msg)

    for cliente, needs in bearer_clients.items():
        if needs and not client_has_bearer_hint(fuentes_por_cliente.get(cliente, [])):
            fallos.append(
                f"{cliente}: operaciones con HTTPBearer y el fuente no menciona "
                "Authorization/Bearer/IdentityHttp"
            )
    return fallos, avisos


def selftest_mutations() -> list[str]:
    """Mutaciones sintéticas: el checker debe ponerse rojo."""
    spec = {
        "components": {
            "schemas": {
                "LoginRequest": {
                    "type": "object",
                    "required": ["email", "password"],
                    "properties": {
                        "email": {"type": "string"},
                        "password": {"type": "string"},
                        "rol": {"type": "string", "enum": ["camarero", "negocio"]},
                    },
                },
                "LoginResponse": {
                    "type": "object",
                    "required": ["token"],
                    "properties": {"token": {"type": "string"}},
                },
                "ErrorResponse": {
                    "type": "object",
                    "required": ["code", "detail"],
                    "properties": {
                        "code": {"type": "string"},
                        "detail": {"type": "string"},
                    },
                },
            },
            "securitySchemes": {
                "HTTPBearer": {"type": "http", "scheme": "bearer"},
            },
        },
        "paths": {
            "/v1/auth/login": {
                "post": {
                    "security": [{"HTTPBearer": []}],
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/LoginRequest"}
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/LoginResponse"}
                                }
                            }
                        },
                        "401": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ErrorResponse"}
                                }
                            }
                        },
                    },
                }
            }
        },
    }
    good = {
        "request": {"email": "a@b.c", "password": "secret", "rol": "camarero"},
        "response_200": {"token": "t"},
        "error": {"code": "identity.x", "detail": "no"},
        "security": ["HTTPBearer"],
    }
    op = spec["paths"]["/v1/auth/login"]["post"]
    if validate_entry_against_op(spec, op, good, "ok"):
        return ["SELFTEST pack: fixture buena debía pasar"]

    fallos: list[str] = []

    missing_req = copy.deepcopy(good)
    del missing_req["request"]["email"]
    if not validate_entry_against_op(spec, op, missing_req, "mut"):
        fallos.append("quitar required no puso rojo")

    type_change = copy.deepcopy(spec)
    type_change["components"]["schemas"]["LoginResponse"]["properties"]["token"]["type"] = "integer"
    if not validate_entry_against_op(type_change, op, good, "mut"):
        fallos.append("cambiar tipo no puso rojo")

    enum_cut = copy.deepcopy(spec)
    enum_cut["components"]["schemas"]["LoginRequest"]["properties"]["rol"]["enum"] = ["negocio"]
    if not validate_entry_against_op(enum_cut, op, good, "mut"):
        fallos.append("recortar enum no puso rojo")

    no_sec = copy.deepcopy(spec)
    no_sec["paths"]["/v1/auth/login"]["post"]["security"] = []
    if not validate_entry_against_op(
        no_sec, no_sec["paths"]["/v1/auth/login"]["post"], good, "mut"
    ):
        fallos.append("quitar HTTPBearer del spec no puso rojo")

    packs = {"cam": {"POST /v1/auth/login": good}}
    usadas = {"Web": {("post", "/v1/auth/login")}}
    fuentes = {
        "Web": [
            'fetch("/v1/auth/login", {method: "POST", '
            'body: JSON.stringify({email, password, rol: "camarero"})})'
        ]
    }
    got, _avisos = comprobar_pack(spec, {"paths": {}}, packs, usadas, fuentes, lambda r: r)
    if not any("HTTPBearer" in f or "Authorization" in f for f in got):
        fallos.append("cliente sin Authorization no puso rojo")

    fuentes_ok = {
        "Web": [
            'fetch("/v1/auth/login", {headers: {Authorization: "Bearer x"}, '
            'method: "POST", body: JSON.stringify({email: "a", password: "b", rol: "camarero"})})'
        ]
    }
    got_ok, avisos_ok = comprobar_pack(spec, {"paths": {}}, packs, usadas, fuentes_ok, lambda r: r)
    if got_ok:
        fallos.append(f"cliente con Bearer debía pasar: {got_ok}")
    if avisos_ok:
        fallos.append(f"cliente con Bearer no debía avisar: {avisos_ok}")

    return fallos
