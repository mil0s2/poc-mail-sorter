from fastapi.testclient import TestClient

from app.agent.router import RoutingResult
from app.domain.departments import Department
from app.main import app
from app.mail.sender import MailDeliveryError

client = TestClient(app)
PAYLOAD = {"email": "jan.nowak@example.com", "message": "Nie dziala mi komputer"}


def _install_routing(monkeypatch, result=None, error=None):
    async def fake(sender_email, message, ticket_id, subject=None):
        if error:
            raise error
        return result or RoutingResult(
            ticket_id=ticket_id,
            department=Department.HELP_DESK,
            recipient="help-desk@example.com",
            routed_by="llm",
        )

    monkeypatch.setattr("app.api.v1.route_message", fake)


def test_happy_path(monkeypatch):
    _install_routing(monkeypatch)
    response = client.post("/api/v1/route", json=PAYLOAD)
    body = response.json()

    assert response.status_code == 200
    assert body["department"] == "help_desk"
    assert body["recipient"] == "help-desk@example.com"
    assert body["routed_by"] == "llm"
    assert len(body["ticket_id"]) == 8


def test_rejects_bad_input():
    bad = [
        {"message": "brak adresu"},
        {"email": "jan@example.com"},
        {"email": "bez-malpy", "message": "x"},
        {"email": "jan@example.com", "message": ""},
        {"email": "jan@example.com\nBcc: x@y.pl", "message": "x"},
        {"email": "jan@example.com", "message": "x", "subject": "a\r\nBcc: x@y.pl"},
    ]
    for payload in bad:
        assert client.post("/api/v1/route", json=payload).status_code == 422, payload


def test_smtp_failure_gives_502(monkeypatch):
    _install_routing(monkeypatch, error=MailDeliveryError("SMTP padl"))
    response = client.post("/api/v1/route", json=PAYLOAD)
    assert response.status_code == 502
    assert "Traceback" not in response.text


def test_model_failure_gives_503(monkeypatch):
    import httpx

    _install_routing(monkeypatch, error=httpx.ConnectError("Ollama nieosiagalna"))
    assert client.post("/api/v1/route", json=PAYLOAD).status_code == 503


def test_swagger_under_api_v1():
    assert client.get("/api/v1/docs").status_code == 200
    spec = client.get("/api/v1/openapi.json").json()
    assert "/api/v1/route" in spec["paths"]
    assert client.get("/docs").status_code == 404


def test_health_reports_degraded_with_200(monkeypatch):
    async def ollama_down(settings):
        return False, False

    async def smtp_down(host, port):
        return False

    monkeypatch.setattr("app.api.v1.check_ollama", ollama_down)
    monkeypatch.setattr("app.api.v1.smtp_is_reachable", smtp_down)

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "degraded"
