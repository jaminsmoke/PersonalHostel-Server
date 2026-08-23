"""Entrega de correo desacoplada del dominio de invitaciones."""

from __future__ import annotations

import logging
import os
import smtplib
import uuid
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    def send_invitation(
        self,
        recipient: str,
        link: str,
        establishment_name: str,
        *,
        message_id: str | None = None,
    ) -> None: ...


def message_id_for_outbox(outbox_id: uuid.UUID, from_addr: str) -> str:
    _, addr = parseaddr(from_addr)
    domain = addr.rsplit("@", 1)[-1] if addr and "@" in addr else "localhost"
    return f"<outbox-{outbox_id}@{domain}>"


def compose_invitation_message(
    *,
    sender: str,
    recipient: str,
    link: str,
    establishment_name: str,
    message_id: str,
) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = f"Invitación a {establishment_name}"
    message["From"] = sender
    message["To"] = recipient
    message["Message-ID"] = message_id
    message.set_content(
        f"Has recibido una invitación para trabajar en {establishment_name}.\n\n"
        f"Acepta la invitación desde este enlace: {link}\n"
    )
    return message


class ConsoleEmailSender:
    def send_invitation(
        self,
        recipient: str,
        link: str,
        establishment_name: str,
        *,
        message_id: str | None = None,
    ) -> None:
        logger.info(
            "Invitación preparada para %s en establecimiento %s (enlace omitido)",
            recipient,
            establishment_name,
        )


class SmtpEmailSender:
    def __init__(self) -> None:
        self.host = os.environ["EMAIL_HOST"]
        self.port = int(os.environ.get("EMAIL_PORT", "587"))
        self.username = os.environ["EMAIL_USERNAME"]
        self.password = os.environ["EMAIL_PASSWORD"]
        self.sender = os.environ["EMAIL_FROM"]
        self.use_tls = os.environ.get("EMAIL_USE_TLS", "true").lower() == "true"

    def send_invitation(
        self,
        recipient: str,
        link: str,
        establishment_name: str,
        *,
        message_id: str | None = None,
    ) -> None:
        mid = message_id or message_id_for_outbox(uuid.uuid4(), self.sender)
        message = compose_invitation_message(
            sender=self.sender,
            recipient=recipient,
            link=link,
            establishment_name=establishment_name,
            message_id=mid,
        )
        with smtplib.SMTP(self.host, self.port, timeout=20) as smtp:
            if self.use_tls:
                smtp.starttls()
            smtp.login(self.username, self.password)
            smtp.send_message(message)


def get_email_sender() -> EmailSender:
    provider = os.environ.get("EMAIL_PROVIDER", "console").lower()
    if provider == "console":
        return ConsoleEmailSender()
    if provider == "smtp":
        return SmtpEmailSender()
    raise RuntimeError(f"Proveedor de email no soportado: {provider}")
