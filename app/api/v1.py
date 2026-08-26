from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic_ai.exceptions import ModelAPIError

from app.agent.router import check_ollama, route_message
from app.config import Settings, get_settings
from app.logging_setup import get_logger, request_id_var
from app.mail.sender import MailDeliveryError
from app.mail.sender import is_reachable as smtp_is_reachable
from app.schemas import HealthResponse, RouteRequest, RouteResponse

API_PREFIX = "/api/v1"
router = APIRouter(prefix=API_PREFIX)
logger = get_logger(__name__)


@router.get(
    "/health",
    response_model=HealthResponse,
    status_code=200,
    tags=["health"],
    summary="Stan srodowiska: Ollama, model, SMTP",
)
async def health(settings: Settings = Depends(get_settings)) -> HealthResponse:
    ollama_reachable, model_ready = await check_ollama(settings)
    smtp_reachable = await smtp_is_reachable(settings.smtp_host, settings.smtp_port)
    everything_ok = ollama_reachable and model_ready and smtp_reachable
    return HealthResponse(
        status="ok" if everything_ok else "degraded",
        ollama_reachable=ollama_reachable,
        model=settings.ollama_model,
        model_ready=model_ready,
        smtp_reachable=smtp_reachable,
    )


@router.post(
    "/route",
    response_model=RouteResponse,
    tags=["routing"],
    summary="Analizuje zgloszenie i przekazuje je do wlasciwego dzialu",
    responses={
        422: {"description": "Niepoprawny adres e-mail albo pusta wiadomosc"},
        502: {"description": "Nie udalo sie dostarczyc wiadomosci"},
        503: {"description": "Model jezykowy niedostepny"},
    },
)
async def route(payload: RouteRequest) -> RouteResponse:
    ticket_id = uuid4().hex[:8]
    request_id_var.set(ticket_id)
    logger.info("Zgloszenie od %s, %d znakow", payload.email, len(payload.message))

    try:
        result = await route_message(
            payload.email, payload.message, ticket_id, payload.subject
        )
    except MailDeliveryError as exc:
        raise HTTPException(502, "Nie udalo sie dostarczyc wiadomosci.") from exc
    except (ModelAPIError, httpx.HTTPError) as exc:
        logger.error("Model niedostepny: %s: %s", type(exc).__name__, exc)
        raise HTTPException(503, "Model jezykowy jest chwilowo niedostepny.") from exc

    return RouteResponse(
        ticket_id=result.ticket_id,
        department=result.department,
        recipient=result.recipient,
        routed_by=result.routed_by,
    )
