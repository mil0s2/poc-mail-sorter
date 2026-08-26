import logging
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.departments import Department


_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
logger = logging.getLogger(__name__)


class RouteRequest(BaseModel):
    email: str = Field(min_length=1, max_length=254)
    message: str = Field(min_length=1, max_length=20_000)
    subject: str | None = Field(default=None, max_length=200)

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "email": "jan.kowalski@example.com",
        "message": "No tata, znów nie działa to wideło. Nie chce się włączyć.",
    }]})

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            logger.warning(
                "Rejected email address with control characters "
                "(possible SMTP header injection): %r",
                v,
            )
            raise ValueError("Email address may contain control characters.")
        v = v.strip()
        if _EMAIL_RE.fullmatch(v) is None:
            raise ValueError("Invalid email address.")
        return v

    @field_validator("subject")
    @classmethod
    def validate_subject(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if any(ord(c) < 32 or ord(c) == 127 for c in v):
            raise ValueError("Subject may contain control characters.")
        v = v.strip()
        return v or None

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Message cannot be empty.")
        if any(ord(c) < 32 and c not in "\n\r\t" for c in v):
            raise ValueError("Message must not contain control characters.")
        return v


class RouteResponse(BaseModel):
    ticket_id: str
    department: Department
    recipient: str
    routed_by: Literal["llm", "fallback"]

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "ticket_id": "a3f9c2e1",
        "department": "help_desk",
        "recipient": "help-desk@example.com",
        "routed_by": "llm",
    }]})


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    ollama_reachable: bool
    model: str
    model_ready: bool
    smtp_reachable: bool

    model_config = ConfigDict(json_schema_extra={"examples": [{
        "status": "ok",
        "ollama_reachable": True,
        "model": "qwen2.5:3b",
        "model_ready": True,
        "smtp_reachable": True,
    }]})
