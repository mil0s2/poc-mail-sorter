import pytest
from pydantic import ValidationError

from app.schemas import RouteRequest

_OK = "Nie dziala mi komputer"


def test_rejects_header_injection_in_email():
    for email in (
        "jan@example.com\nBcc: ofiara@example.com",
        "jan@example.com\r\nBcc: ofiara@example.com",
        "jan@example.com\n",
    ):
        with pytest.raises(ValidationError):
            RouteRequest(email=email, message=_OK)


def test_rejects_control_characters_in_subject():
    with pytest.raises(ValidationError):
        RouteRequest(
            email="jan@example.com",
            message=_OK,
            subject="Awaria\r\nBcc: ofiara@example.com",
        )


def test_blank_subject_becomes_none():
    req = RouteRequest(email="jan@example.com", message=_OK, subject="   ")
    assert req.subject is None


def test_strips_email_and_accepts_valid():
    req = RouteRequest(email="  jan@example.com  ", message=_OK)
    assert req.email == "jan@example.com"


def test_subject_is_optional():
    assert RouteRequest(email="jan@example.com", message=_OK).subject is None
    req = RouteRequest(email="jan@example.com", message=_OK, subject="Awaria laptopa")
    assert req.subject == "Awaria laptopa"
