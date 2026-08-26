from email.message import EmailMessage

from app.domain.departments import Department


def derive_subject(message: str, limit: int = 70) -> str:
    text = " ".join(message.split())
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return f"{cut}\u2026"


def _department_label(department: Department) -> str:
    return department.value.upper().replace("_", "-")


def build_message(
    *,
    sender_email: str,
    recipient: str,
    department: Department,
    original_message: str,
    ticket_id: str,
    routed_by: str,
    subject: str,
    mail_from: str,
) -> EmailMessage:
    label = _department_label(department)

    msg = EmailMessage()
    msg["From"] = mail_from
    msg["To"] = recipient
    msg["Reply-To"] = sender_email
    msg["Subject"] = f"[{label}] - {ticket_id} - {subject}"
    msg["X-Ticket-Id"] = ticket_id
    msg["X-Routed-By"] = routed_by
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(
        "=== ZGLOSZENIE ===\n"
        f"Od:     {sender_email}\n"
        f"Ticket: {ticket_id}\n"
        "\n"
        f"{original_message}\n"
    )
    return msg
