from dataclasses import dataclass

import pytest

from app.agent.router import RoutingContext


@dataclass
class FakeRunContext:
    deps: RoutingContext


@pytest.fixture
def ctx() -> FakeRunContext:
    return FakeRunContext(
        deps=RoutingContext(
            sender_email="jan.nowak@example.com",
            subject="Nie dziala mi komputer",
            full_message="Nie dziala mi komputer",
            ticket_id="a3f9c2e1",
        )
    )


@pytest.fixture
def sent(monkeypatch) -> list:
    captured = []

    async def fake_send(message, host, port):
        captured.append(message)

    monkeypatch.setattr("app.agent.router.send_message", fake_send)
    return captured
