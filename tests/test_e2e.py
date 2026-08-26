import time

import httpx
import pytest

from app.domain.departments import DEPARTMENT_EMAILS

pytestmark = pytest.mark.e2e

API = "http://localhost:8000"
MAILHOG = "http://localhost:8025"
SENDER = "jan.nowak@example.com"


def test_request_produces_mail_with_reply_to():
    httpx.delete(f"{MAILHOG}/api/v1/messages", timeout=5)

    response = httpx.post(
        f"{API}/api/v1/route",
        json={"email": SENDER, "message": "Nie dziala mi komputer, nie chce sie wlaczyc"},
        timeout=180,
    )
    assert response.status_code == 200
    ticket_id = response.json()["ticket_id"]

    for _ in range(10):
        items = httpx.get(f"{MAILHOG}/api/v2/messages", timeout=5).json()["items"]
        if items:
            break
        time.sleep(0.5)
    else:
        pytest.fail("Brak wiadomosci w MailHogu")

    headers = items[0]["Content"]["Headers"]
    assert headers["Reply-To"][0] == SENDER
    assert headers["To"][0] in DEPARTMENT_EMAILS.values()
    assert headers["X-Ticket-Id"][0] == ticket_id
