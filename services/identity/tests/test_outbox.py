import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from app.db import NegocioSessionLocal
from app.email import compose_invitation_message, message_id_for_outbox
from app.models import EmailOutbox, EmailOutboxEstado
from app.outbox import process_pending_outbox
from app.security import get_session_secret_env, protect_invitation_token


@pytest.fixture(scope="module")
def db_ready():
    with NegocioSessionLocal() as session:
        session.execute(text("SELECT 1"))
    yield


@pytest.fixture
def clean_outbox(db_ready):
    with NegocioSessionLocal() as session:
        session.query(EmailOutbox).delete()
        session.commit()
    yield
    with NegocioSessionLocal() as session:
        session.query(EmailOutbox).delete()
        session.commit()


class _FakeSender:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def send_invitation(
        self,
        recipient: str,
        link: str,
        establishment_name: str,
        *,
        message_id: str | None = None,
    ) -> None:
        self.calls.append(
            {
                "recipient": recipient,
                "link": link,
                "establishment_name": establishment_name,
                "message_id": message_id,
            }
        )


def _insert(
    *,
    estado: EmailOutboxEstado,
    intentos: int = 0,
    enviando_desde: datetime | None = None,
    worker_id: str | None = None,
) -> EmailOutbox:
    token = f"tok-{uuid.uuid4()}"
    row = EmailOutbox(
        tipo="invitacion_establecimiento",
        destinatario=f"outbox-{uuid.uuid4()}@example.com",
        payload={
            "token_encrypted": protect_invitation_token(token, get_session_secret_env()),
            "invitation_url_base": "http://localhost:8084/invitaciones",
            "establishment_name": "Bar Lease",
        },
        estado=estado,
        intentos=intentos,
        enviando_desde=enviando_desde,
        worker_id=worker_id,
    )
    with NegocioSessionLocal() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def test_message_id_estable_por_uuid():
    outbox_id = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    assert message_id_for_outbox(outbox_id, "Identity <no-reply@siberia.solutions>") == (
        "<outbox-aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee@siberia.solutions>"
    )


def test_compose_invitation_incluye_message_id():
    outbox_id = uuid.uuid4()
    mid = message_id_for_outbox(outbox_id, "no-reply@example.com")
    message = compose_invitation_message(
        sender="no-reply@example.com",
        recipient="ana@example.com",
        link="http://localhost/invitaciones/abc",
        establishment_name="Bar Lease",
        message_id=mid,
    )
    assert message["Message-ID"] == mid
    assert "Bar Lease" in message.get_content()


def test_pendiente_se_envia(clean_outbox, monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "no-reply@example.com")
    monkeypatch.setenv("EMAIL_WORKER_ID", "worker-test")
    fake = _FakeSender()
    monkeypatch.setattr("app.outbox.get_email_sender", lambda: fake)
    row = _insert(estado=EmailOutboxEstado.pendiente)

    with NegocioSessionLocal() as session:
        assert process_pending_outbox(session, limit=5) == 1

    with NegocioSessionLocal() as session:
        saved = session.get(EmailOutbox, row.id)
        assert saved.estado == EmailOutboxEstado.enviado
        assert saved.intentos == 1
        assert saved.worker_id == "worker-test"
        assert saved.enviando_desde is not None
    assert len(fake.calls) == 1
    assert fake.calls[0]["message_id"] == message_id_for_outbox(row.id, "no-reply@example.com")
    assert fake.calls[0]["link"].startswith("http://localhost:8084/invitaciones/")


def test_enviando_huérfano_se_recupera(clean_outbox, monkeypatch, caplog):
    monkeypatch.setenv("EMAIL_FROM", "no-reply@example.com")
    monkeypatch.setenv("EMAIL_WORKER_ID", "worker-vivo")
    fake = _FakeSender()
    monkeypatch.setattr("app.outbox.get_email_sender", lambda: fake)
    stale = datetime.now(UTC) - timedelta(minutes=10)
    row = _insert(
        estado=EmailOutboxEstado.enviando,
        intentos=1,
        enviando_desde=stale,
        worker_id="worker-muerto",
    )

    with caplog.at_level("INFO", logger="app.outbox"), NegocioSessionLocal() as session:
        assert process_pending_outbox(session, limit=5) == 1

    with NegocioSessionLocal() as session:
        saved = session.get(EmailOutbox, row.id)
        assert saved.estado == EmailOutboxEstado.enviado
        assert saved.intentos == 2
        assert saved.worker_id == "worker-vivo"
    assert len(fake.calls) == 1
    assert str(row.id) in caplog.text
    assert "worker-muerto" in caplog.text
    assert saved.destinatario not in caplog.text


def test_enviando_sin_timestamp_se_recupera(clean_outbox, monkeypatch):
    monkeypatch.setenv("EMAIL_FROM", "no-reply@example.com")
    fake = _FakeSender()
    monkeypatch.setattr("app.outbox.get_email_sender", lambda: fake)
    row = _insert(estado=EmailOutboxEstado.enviando, intentos=1, enviando_desde=None)

    with NegocioSessionLocal() as session:
        assert process_pending_outbox(session, limit=5) == 1

    with NegocioSessionLocal() as session:
        saved = session.get(EmailOutbox, row.id)
        assert saved.estado == EmailOutboxEstado.enviado


def test_lease_fresco_no_se_roba(clean_outbox, monkeypatch):
    fake = _FakeSender()
    monkeypatch.setattr("app.outbox.get_email_sender", lambda: fake)
    row = _insert(
        estado=EmailOutboxEstado.enviando,
        intentos=1,
        enviando_desde=datetime.now(UTC),
        worker_id="worker-vivo",
    )

    with NegocioSessionLocal() as session:
        assert process_pending_outbox(session, limit=5) == 0

    with NegocioSessionLocal() as session:
        saved = session.get(EmailOutbox, row.id)
        assert saved.estado == EmailOutboxEstado.enviando
        assert saved.intentos == 1
    assert fake.calls == []


def test_tope_de_intentos_no_reclama_huérfano(clean_outbox, monkeypatch):
    fake = _FakeSender()
    monkeypatch.setattr("app.outbox.get_email_sender", lambda: fake)
    monkeypatch.setenv("EMAIL_MAX_ATTEMPTS", "5")
    row = _insert(
        estado=EmailOutboxEstado.enviando,
        intentos=5,
        enviando_desde=datetime.now(UTC) - timedelta(hours=1),
    )

    with NegocioSessionLocal() as session:
        assert process_pending_outbox(session, limit=5) == 0

    with NegocioSessionLocal() as session:
        saved = session.get(EmailOutbox, row.id)
        assert saved.estado == EmailOutboxEstado.enviando
    assert fake.calls == []
