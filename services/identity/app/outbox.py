"""Procesador pequeño y reintentable de la outbox de email."""

import logging
import os
import socket
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.email import get_email_sender, message_id_for_outbox
from app.models import EmailOutbox, EmailOutboxEstado
from app.security import get_session_secret_env, unprotect_invitation_token

logger = logging.getLogger(__name__)

DEFAULT_CLAIM_TTL_SECONDS = 120


def claim_ttl_seconds() -> int:
    return int(os.environ.get("EMAIL_CLAIM_TTL_SECONDS", str(DEFAULT_CLAIM_TTL_SECONDS)))


def current_worker_id() -> str:
    return (os.environ.get("EMAIL_WORKER_ID") or socket.gethostname())[:80]


def _stale_enviando(now: datetime):
    stale_before = now - timedelta(seconds=claim_ttl_seconds())
    return and_(
        EmailOutbox.estado == EmailOutboxEstado.enviando,
        or_(
            EmailOutbox.enviando_desde.is_(None),
            EmailOutbox.enviando_desde < stale_before,
        ),
    )


def process_pending_outbox(db: Session, limit: int = 20) -> int:
    processed = 0
    max_attempts = int(os.environ.get("EMAIL_MAX_ATTEMPTS", "5"))
    worker = current_worker_id()
    from_addr = os.environ.get("EMAIL_FROM", "no-reply@localhost")
    for _ in range(limit):
        now = datetime.now(UTC)
        row = (
            db.query(EmailOutbox)
            .filter(
                or_(
                    EmailOutbox.estado == EmailOutboxEstado.pendiente,
                    EmailOutbox.estado == EmailOutboxEstado.fallido,
                    _stale_enviando(now),
                ),
                EmailOutbox.intentos < max_attempts,
            )
            .order_by(EmailOutbox.creado_en)
            .with_for_update(skip_locked=True)
            .first()
        )
        if row is None:
            break
        recovered = row.estado == EmailOutboxEstado.enviando
        previous_worker = row.worker_id
        previous_since = row.enviando_desde
        row.estado = EmailOutboxEstado.enviando
        row.enviando_desde = now
        row.worker_id = worker
        row.intentos += 1
        db.commit()
        if recovered:
            age_s = None
            if previous_since is not None:
                since = previous_since
                if since.tzinfo is None:
                    since = since.replace(tzinfo=UTC)
                age_s = int((now - since).total_seconds())
            logger.info(
                "outbox lease recuperado id=%s worker_anterior=%s worker=%s edad_s=%s intentos=%s",
                row.id,
                previous_worker,
                worker,
                age_s,
                row.intentos,
            )
        try:
            token = unprotect_invitation_token(
                row.payload["token_encrypted"], get_session_secret_env()
            )
            base_url = row.payload["invitation_url_base"].rstrip("/")
            link = f"{base_url}/{token}"
            row.enviando_desde = datetime.now(UTC)
            db.commit()
            get_email_sender().send_invitation(
                row.destinatario,
                link,
                row.payload["establishment_name"],
                message_id=message_id_for_outbox(row.id, from_addr),
            )
            row.estado = EmailOutboxEstado.enviado
            row.enviado_en = datetime.now(UTC)
            row.ultimo_error = None
        except Exception as exc:  # sender failures must remain retryable
            row.estado = EmailOutboxEstado.fallido
            row.ultimo_error = str(exc)[:1000]
        db.commit()
        processed += 1
    return processed
