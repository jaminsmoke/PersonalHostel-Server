"""Test del transporte ``http`` del cliente interno (httpx2).

Solo el transporte ``direct`` estaba cubierto. Aquí se ejercita
``HttpCamarerosInternal``/``HttpNegocioInternal`` contra un servidor HTTP
dummy real, verificando 200, 404 y el fallback 503.
"""

import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from app.errors import ApiError
from app.internal import HttpCamarerosInternal, HttpNegocioInternal

PERFIL = {
    "id": "00000000-0000-0000-0000-000000000001",
    "nombre": "Ana",
    "apellidos": "García",
    "email": "ana@example.com",
    "nick": "ana",
    "data_origin": "real",
}


class _Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict | list) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # silencio en los tests
        pass

    def do_GET(self) -> None:
        path = self.path
        if path.startswith("/internal/camareros/buscar"):
            if "missing" in path:  # el @ llega URL-encoded (%40)
                self._json(404, {"code": "identity.camarero_no_encontrado"})
            else:
                self._json(200, PERFIL)
        elif "/establecimientos" in path:
            self._json(200, [{"id": "es-1", "nombre": "Bar", "rol": "miembro"}])
        elif "/invitaciones" in path:
            self._json(200, [{"id": "inv-1", "estado": "pendiente"}])
        else:
            self._json(200, PERFIL)

    def do_POST(self) -> None:
        if "/qr/verify" in self.path:
            self._json(200, {"camarero_id": "00000000-0000-0000-0000-000000000001"})
        elif "/sesiones/validar" in self.path:
            self._json(200, {"ok": True})
        else:
            self._json(200, {"membresia": {"camarero_id": PERFIL["id"], "rol": "miembro"}})


@pytest.fixture(scope="module")
def dummy_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    yield f"http://{host}:{port}"
    server.shutdown()
    server.server_close()


def test_transporte_http_buscar_y_perfil(dummy_server):
    cliente = HttpCamarerosInternal(dummy_server)
    perfil = cliente.buscar_por_email("ana@example.com")
    assert perfil is not None
    assert perfil["nombre"] == "Ana"
    assert cliente.perfil(uuid.UUID(PERFIL["id"]))["nick"] == "ana"


def test_transporte_http_buscar_404_devuelve_none(dummy_server):
    cliente = HttpCamarerosInternal(dummy_server)
    assert cliente.buscar_por_email("missing@example.com") is None


def test_transporte_http_sesion_valida(dummy_server):
    cliente = HttpCamarerosInternal(dummy_server)
    assert cliente.sesion_valida(uuid.UUID(PERFIL["id"]), uuid.uuid4(), None) is True
    cliente = HttpCamarerosInternal(dummy_server)
    camarero_id = cliente.verificar_qr("phid1:noimporta")
    assert camarero_id == uuid.UUID(PERFIL["id"])


def test_transporte_http_negocio(dummy_server):
    cliente = HttpNegocioInternal(dummy_server)
    establecimientos = cliente.establecimientos_de(uuid.UUID(PERFIL["id"]))
    assert establecimientos[0]["nombre"] == "Bar"
    invitaciones = cliente.invitaciones_de(uuid.UUID(PERFIL["id"]))
    assert invitaciones[0]["estado"] == "pendiente"
    aceptada = cliente.aceptar_invitacion(uuid.UUID(PERFIL["id"]), uuid.UUID(int=9))
    assert aceptada["membresia"]["camarero_id"] == PERFIL["id"]


def test_transporte_http_indisponible_devuelve_503():
    # Se arranca un server para reservar un puerto libre y se apaga antes de
    # usarlo, de modo que la conexión sea rechazada (refused).
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    host, port = server.server_address
    server.server_close()
    cliente = HttpCamarerosInternal(f"http://{host}:{port}")
    with pytest.raises(ApiError) as exc:
        cliente.buscar_por_email("ana@example.com")
    assert exc.value.status_code == 503
    assert exc.value.code == "identity.internal_unavailable"
