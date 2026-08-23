"""Sesiones de cuenta: jti, refresh, revocación y corte por password."""

import uuid
from datetime import UTC, datetime, timedelta

from app.auth import create_access_token
from app.db import CamareroSessionLocal
from app.models import Camarero
from app.security import get_session_secret


def _email(prefix: str = "ses") -> str:
    return f"{prefix}-{uuid.uuid4()}@example.com"


def _registro_cam(client, email: str) -> dict:
    resp = client.post(
        "/v1/camareros/registro",
        json={
            "nombre": "Ana",
            "apellidos": "García",
            "email": email,
            "password": "pass-12345678",
            "dispositivo": "test-cam",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def _login_cam(client, email: str, dispositivo: str = "test-login") -> dict:
    resp = client.post(
        "/v1/auth/login",
        json={"email": email, "password": "pass-12345678", "dispositivo": dispositivo},
    )
    assert resp.status_code == 200
    return resp.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_login_emite_sesion_y_refresh(db_ready, camarero_client):
    email = _email()
    _registro_cam(camarero_client, email)
    body = _login_cam(camarero_client, email)
    assert body["refresh_token"]
    assert body["expires_in"] > 0
    uuid.UUID(body["sesion_id"])
    me = camarero_client.get("/v1/camareros/me", headers=_auth(body["token"]))
    assert me.status_code == 200


def test_revocar_una_sesion_deja_la_otra(db_ready, camarero_client):
    email = _email()
    _registro_cam(camarero_client, email)
    a = _login_cam(camarero_client, email, "disp-a")
    b = _login_cam(camarero_client, email, "disp-b")
    listed = camarero_client.get("/v1/camareros/me/sesiones", headers=_auth(b["token"]))
    assert listed.status_code == 200
    assert len(listed.json()) >= 2
    resp = camarero_client.post(
        f"/v1/camareros/me/sesiones/{a['sesion_id']}/revocar",
        headers=_auth(b["token"]),
        json={"motivo": "tablet perdido"},
    )
    assert resp.status_code == 200
    assert resp.json()["revocadas"] == 1
    assert camarero_client.get("/v1/camareros/me", headers=_auth(a["token"])).status_code == 401
    assert camarero_client.get("/v1/camareros/me", headers=_auth(b["token"])).status_code == 200


def test_revocar_otras_conserva_la_actual(db_ready, camarero_client):
    email = _email()
    _registro_cam(camarero_client, email)
    a = _login_cam(camarero_client, email, "a")
    b = _login_cam(camarero_client, email, "b")
    resp = camarero_client.post("/v1/camareros/me/sesiones/revocar", headers=_auth(b["token"]))
    assert resp.status_code == 200
    assert resp.json()["revocadas"] >= 1
    assert camarero_client.get("/v1/camareros/me", headers=_auth(a["token"])).status_code == 401
    assert camarero_client.get("/v1/camareros/me", headers=_auth(b["token"])).status_code == 200


def test_password_cierra_todas_y_devuelve_par_nuevo(db_ready, camarero_client):
    email = _email()
    _registro_cam(camarero_client, email)
    old = _login_cam(camarero_client, email)
    qr_antes = camarero_client.get("/v1/camareros/me/qr", headers=_auth(old["token"])).json()["qr"]
    changed = camarero_client.post(
        "/v1/camareros/me/password",
        headers=_auth(old["token"]),
        json={"password_actual": "pass-12345678", "password_nueva": "nueva-87654321"},
    )
    assert changed.status_code == 200
    body = changed.json()
    assert body["status"] == "cambiada"
    assert body["token"] != old["token"]
    assert camarero_client.get("/v1/camareros/me", headers=_auth(old["token"])).status_code == 401
    me = camarero_client.get("/v1/camareros/me", headers=_auth(body["token"]))
    assert me.status_code == 200
    qr_despues = camarero_client.get("/v1/camareros/me/qr", headers=_auth(body["token"])).json()[
        "qr"
    ]
    assert qr_despues == qr_antes


def test_refresh_rota_y_el_viejo_muere(db_ready, camarero_client):
    email = _email()
    _registro_cam(camarero_client, email)
    login = _login_cam(camarero_client, email)
    first = camarero_client.post("/v1/auth/refresh", json={"refresh_token": login["refresh_token"]})
    assert first.status_code == 200
    reused = camarero_client.post(
        "/v1/auth/refresh", json={"refresh_token": login["refresh_token"]}
    )
    assert reused.status_code == 401
    me = camarero_client.get("/v1/camareros/me", headers=_auth(first.json()["token"]))
    assert me.status_code == 200


def test_jwt_sin_jti_vale_hasta_el_corte(db_ready, camarero_client):
    email = _email()
    created = _registro_cam(camarero_client, email)
    camarero_id = uuid.UUID(created["id"])
    with CamareroSessionLocal() as db:
        secret = get_session_secret(db)
        legacy = create_access_token(camarero_id, secret)
    assert camarero_client.get("/v1/camareros/me", headers=_auth(legacy)).status_code == 200
    with CamareroSessionLocal() as db:
        cam = db.get(Camarero, camarero_id)
        cam.sesiones_validas_desde = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    assert camarero_client.get("/v1/camareros/me", headers=_auth(legacy)).status_code == 200
    with CamareroSessionLocal() as db:
        cam = db.get(Camarero, camarero_id)
        cam.sesiones_validas_desde = datetime.now(UTC) + timedelta(hours=1)
        db.commit()
    assert camarero_client.get("/v1/camareros/me", headers=_auth(legacy)).status_code == 401


def test_negocio_refresh_y_actor_con_sesion_revocada(db_ready, camarero_client, negocio_client):
    email_neg = _email("neg")
    reg = negocio_client.post(
        "/v1/auth/negocio/registro",
        json={
            "nombre_mostrar": "Bar Sesiones",
            "email": email_neg,
            "password": "negocio-12345678",
            "dispositivo": "bar-test",
        },
    )
    assert reg.status_code == 201
    login = negocio_client.post(
        "/v1/auth/negocio/login",
        json={"email": email_neg, "password": "negocio-12345678", "dispositivo": "bar-2"},
    )
    assert login.status_code == 200
    token_a = login.json()["token"]
    otras = negocio_client.post("/v1/auth/negocio/me/sesiones/revocar", headers=_auth(token_a))
    assert otras.status_code == 200
    # el token actual sigue; el de registro (otra sesión) no
    assert negocio_client.get("/v1/auth/negocio/me", headers=_auth(token_a)).status_code == 200
    assert (
        negocio_client.get("/v1/auth/negocio/me", headers=_auth(reg.json()["token"])).status_code
        == 401
    )

    email_cam = _email("cam-act")
    cam = _registro_cam(camarero_client, email_cam)
    # JWT de camarero contra ruta de negocio que usa get_current_actor
    est = negocio_client.post(
        "/v1/establecimientos",
        headers=_auth(token_a),
        json={"nombre": "Local actor"},
    )
    assert est.status_code == 201
    catalogo = negocio_client.get(
        f"/v1/establecimientos/{est.json()['id']}/catalogo",
        headers=_auth(cam["token"]),
    )
    # miembro no activo: 403 o 404 de membresía, no 401 de sesión
    assert catalogo.status_code != 401

    camarero_client.post(
        f"/v1/camareros/me/sesiones/{cam['sesion_id']}/revocar",
        headers=_auth(cam["token"]),
    )
    catalogo_rev = negocio_client.get(
        f"/v1/establecimientos/{est.json()['id']}/catalogo",
        headers=_auth(cam["token"]),
    )
    assert catalogo_rev.status_code == 401


def test_internal_validar_sesion(db_ready, camarero_client, camarero_internal_client):
    email = _email("int")
    created = _registro_cam(camarero_client, email)
    ok = camarero_internal_client.post(
        "/internal/sesiones/validar",
        json={"camarero_id": created["id"], "jti": created["sesion_id"]},
    )
    assert ok.status_code == 200
    fake = camarero_internal_client.post(
        "/internal/sesiones/validar",
        json={
            "camarero_id": created["id"],
            "jti": str(uuid.uuid4()),
        },
    )
    assert fake.status_code == 401
