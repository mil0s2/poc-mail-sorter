import pytest

from app.domain.departments import DEPARTMENT_EMAILS, Department
from app.mail.builder import build_message, derive_subject

SENDER = "jan.nowak@example.com"
MAIL_FROM = "mail-sorter@example.com"


def make(**overrides):
    args = dict(
        sender_email=SENDER,
        recipient="help-desk@example.com",
        department=Department.HELP_DESK,
        original_message="Nie dziala mi komputer, nie chce sie wlaczyc",
        ticket_id="a3f9c2e1",
        routed_by="llm",
        subject="Nie dziala mi komputer",
        mail_from=MAIL_FROM,
    )
    args.update(overrides)
    return build_message(**args)


def test_reply_to_is_original_sender():
    msg = make()
    assert msg["Reply-To"] == SENDER
    assert msg["To"] == DEPARTMENT_EMAILS[Department.HELP_DESK]
    assert msg["From"] == MAIL_FROM
    assert msg["From"] != msg["Reply-To"]


def test_subject_is_department_ticket_and_title():
    assert make()["Subject"] == "[HELP-DESK] - a3f9c2e1 - Nie dziala mi komputer"


def test_derive_subject_uses_message_when_sender_omitted_title():
    assert derive_subject("Nie dziala mi komputer") == "Nie dziala mi komputer"
    long = "slowo " * 40
    derived = derive_subject(long, limit=70)
    assert len(derived) <= 71
    assert derived.endswith("\u2026")


def test_body_has_ticket_and_full_message():
    long = "Zazolc gesla jazn. " * 200
    body = make(original_message=long).get_content()
    assert "a3f9c2e1" in body
    assert long in body
    assert make().get_content_type() == "text/plain"


def test_email_message_rejects_newlines_in_headers():
    with pytest.raises(ValueError):
        make(sender_email="a@b.c\r\nBcc: ofiara@example.com")
