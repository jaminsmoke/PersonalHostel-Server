import uuid

from app.main import app as camareros_app
from app.main_negocio import app as negocio_app

CAMAREROS_RUTAS = [
    "/v1/camareros/registro",
    "/v1/auth/login",
    "/v1/auth/refresh",
    "/v1/camareros/me",
    "/v1/camareros/me/qr",
    "/v1/camareros/me/renovar",
    "/v1/camareros/me/revocar",
    "/v1/camareros/me/password",
    "/v1/camareros/me/sesiones",
    "/v1/camareros/me/visibilidad",
    "/v1/camareros/ficha",
    "/v1/camareros/ficha/foto",
    "/v1/camareros/me/establecimientos",
    "/v1/camareros/me/invitaciones",
    "/v1/camareros/me/invitaciones/{invitacion_id}/aceptar",
    "/v1/camareros/me/pagina-publica",
    "/v1/keys/qr",
]

NEGOCIO_RUTAS = [
    "/v1/auth/negocio/registro",
    "/v1/auth/negocio/login",
    "/v1/auth/negocio/refresh",
    "/v1/auth/negocio/me",
    "/v1/auth/negocio/me/sesiones",
    "/v1/negocio/carta",
    "/v1/establecimientos",
    "/v1/establecimientos/mios",
    "/v1/establecimientos/{establecimiento_id}",
    "/v1/establecimientos/{establecimiento_id}/logo",
    "/v1/establecimientos/{establecimiento_id}/miembros",
    "/v1/establecimientos/{establecimiento_id}/miembros/qr",
    "/v1/establecimientos/{establecimiento_id}/camareros/buscar",
    "/v1/establecimientos/{establecimiento_id}/invitaciones",
    "/v1/establecimientos/{establecimiento_id}/catalogo",
    "/v1/establecimientos/{establecimiento_id}/horario",
    "/v1/establecimientos/{establecimiento_id}/enlaces",
    "/v1/establecimientos/{establecimiento_id}/enlaces/{enlace_id}/revocar",
    "/v1/establecimientos/{establecimiento_id}/enlaces/{enlace_id}/rotar",
    "/v1/enlaces/{slug}",
    "/v1/establecimientos/{establecimiento_id}/sync/cambios",
    "/v1/establecimientos/{establecimiento_id}/sync/operaciones",
    "/v1/establecimientos/{establecimiento_id}/sync/conflictos",
    "/v1/establecimientos/{establecimiento_id}/sync/conflictos/{conflicto_id}/resolver",
    "/v1/establecimientos/{establecimiento_id}/notificaciones",
    "/v1/establecimientos/{establecimiento_id}/notificaciones/{notificacion_id}/leer",
    "/v1/establecimientos/{establecimiento_id}/perfil-web",
    "/v1/establecimientos/{establecimiento_id}/hero",
    "/v1/establecimientos/{establecimiento_id}/galeria",
    "/v1/establecimientos/{establecimiento_id}/galeria/{imagen_id}",
    "/v1/establecimientos/{establecimiento_id}/fondos",
    "/v1/establecimientos/{establecimiento_id}/fondos/catalogo",
    "/v1/establecimientos/{establecimiento_id}/fondos/{slot}",
    "/v1/invitaciones/{token}/aceptar",
    "/v1/negocio/web",
    "/v1/negocio/web/logo",
    "/v1/negocio/web/hero",
    "/v1/negocio/web/galeria/{imagen_id}",
    "/v1/negocio/web/fondo/{slot}",
]


def test_openapi_camareros_documenta_rutas_y_version(camarero_client):
    resp = camarero_client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["version"] == "0.2.0"
    paths = spec["paths"]
    for ruta in CAMAREROS_RUTAS:
        assert ruta in paths, f"Falta {ruta} en el spec de camareros"
    assert "ErrorResponse" in spec["components"]["schemas"]
    assert not any(ruta.startswith("/internal") for ruta in paths)
    assert "/metrics" not in paths


def test_openapi_negocio_documenta_rutas_y_version(negocio_client):
    resp = negocio_client.get("/openapi.json")
    assert resp.status_code == 200
    spec = resp.json()
    assert spec["info"]["version"] == "0.2.0"
    paths = spec["paths"]
    for ruta in NEGOCIO_RUTAS:
        assert ruta in paths, f"Falta {ruta} en el spec de negocio"
    assert not any(ruta.startswith("/internal") for ruta in paths)
    assert "/metrics" not in paths
    assert "/v1/negocio/ficha" not in paths
    assert "/v1/negocio/ficha/logo" not in paths
    assert "get" in paths["/v1/auth/negocio/me"]
    assert "patch" in paths["/v1/auth/negocio/me"]
    assert "patch" in paths["/v1/establecimientos/{establecimiento_id}"]
    assert "ErrorResponse" in spec["components"]["schemas"]


def test_openapi_es_determinista():
    assert camareros_app.openapi() == camareros_app.openapi()
    assert negocio_app.openapi() == negocio_app.openapi()


def test_validacion_devuelve_code(camarero_client):
    resp = camarero_client.post(
        "/v1/camareros/registro",
        json={
            "nombre": "Ana",
            "apellidos": "García",
            "email": "no-es-email",
            "password": "pass-12345678",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "identity.validation_error"
    assert isinstance(body["detail"], list)


def test_login_inexistente_devuelve_code(camarero_client):
    resp = camarero_client.post(
        "/v1/auth/login",
        json={"email": f"no-existe-{uuid.uuid4()}@example.com", "password": "pass-12345678"},
    )
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "identity.credenciales_invalidas"
    assert "incorrectos" in body["detail"]
