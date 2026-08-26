import logging
import smtplib
import socket
from email.message import EmailMessage

from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)


class MailDeliveryError(RuntimeError):
    pass


def _send_sync(message: EmailMessage, host: str, port: int) -> None:
    with smtplib.SMTP(host, port, timeout=10) as server:
        server.send_message(message)


async def send_message(message: EmailMessage, host: str, port: int) -> None:
    try:
        await run_in_threadpool(_send_sync, message, host, port)
    except (smtplib.SMTPException, OSError) as exc:
        logger.error(
            "Wysylka do %s:%s nie powiodla sie: %s: %s",
            host,
            port,
            type(exc).__name__,
            exc,
        )
        raise MailDeliveryError(f"SMTP {host}:{port} - {exc}") from exc
    logger.info("Wyslano do %s", message["To"])


def _is_reachable_sync(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError as exc:
        logger.warning("SMTP %s:%s nieosiagalny: %s", host, port, exc)
        return False


async def is_reachable(host: str, port: int) -> bool:
    return await run_in_threadpool(_is_reachable_sync, host, port)
