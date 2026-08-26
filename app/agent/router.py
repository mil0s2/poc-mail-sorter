import logging
from dataclasses import dataclass
from functools import lru_cache

import httpx
from pydantic_ai import Agent, RunContext
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from app.agent.prompt import build_system_prompt
from app.config import Settings, get_settings
from app.domain.departments import Department, resolve_email
from app.mail.builder import build_message, derive_subject
from app.mail.sender import send_message

logger = logging.getLogger(__name__)


def _summarize_model_turn(result) -> str:
    bits: list[str] = []
    for message in result.new_messages():
        if not isinstance(message, ModelResponse):
            continue
        for part in message.parts:
            if isinstance(part, ToolCallPart):
                bits.append(f"{part.tool_name}({part.args_as_dict()})")
            elif isinstance(part, TextPart) and part.content.strip():
                bits.append(part.content.strip())
    output = result.output.strip() if isinstance(result.output, str) else ""
    if output and output not in bits:
        bits.append(output)
    return " | ".join(bits)


async def check_ollama(settings: Settings) -> tuple[bool, bool]:
    try:
        async with httpx.AsyncClient(timeout=2) as client:
            response = await client.get(f"{settings.ollama_base_url}/api/tags")
            response.raise_for_status()
            models = response.json().get("models", [])
        names = {m.get("name") or m.get("model") for m in models}
        return True, settings.ollama_model in names
    except Exception as exc:
        logger.warning(
            "Ollama (%s) niedostepna: %s: %s",
            settings.ollama_base_url,
            type(exc).__name__,
            exc,
        )
        return False, False


@dataclass
class RoutingContext:
    sender_email: str
    subject: str
    full_message: str
    ticket_id: str
    emails_sent: int = 0
    chosen_department: Department | None = None


@dataclass
class RoutingResult:
    ticket_id: str
    department: Department
    recipient: str
    routed_by: str


@lru_cache
def get_agent() -> Agent[RoutingContext, str]:
    settings = get_settings()
    model = OpenAIChatModel(
        model_name=settings.ollama_model,
        provider=OpenAIProvider(
            base_url=f"{settings.ollama_base_url}/v1",
            api_key="ollama",
        ),
    )
    agent = Agent(
        model,
        deps_type=RoutingContext,
        retries=3,
        instructions=build_system_prompt(),
        model_settings=ModelSettings(
            temperature=0.0,
            seed=0,
            timeout=settings.llm_timeout_seconds,
            # tool_choice="required" konczy sie nieskonczona petla w pydantic-ai:
            # model nigdy nie moze odpowiedziec tekstem, a petla konczy sie
            # wlasnie tekstowa odpowiedzia po wykonaniu narzedzia.
            parallel_tool_calls=False,
        ),
    )
    agent.tool(send_email)
    return agent


async def send_email(
    ctx: RunContext[RoutingContext], department: Department
) -> str:
    """Wysyła zgłoszenie mailem do wskazanego działu.

    Wywołaj dokładnie raz. Jedyny argument to `department`.
    """
    if ctx.deps.emails_sent >= 1:
        logger.warning("Model probowal wyslac drugi raz - zignorowano")
        return "Wiadomosc dla tego zgloszenia zostala juz wyslana. Zakoncz."

    settings = get_settings()
    recipient = resolve_email(department)
    message = build_message(
        sender_email=ctx.deps.sender_email,
        recipient=recipient,
        department=department,
        original_message=ctx.deps.full_message,
        ticket_id=ctx.deps.ticket_id,
        routed_by="llm",
        subject=ctx.deps.subject,
        mail_from=settings.mail_from,
    )
    await send_message(message, settings.smtp_host, settings.smtp_port)

    ctx.deps.emails_sent += 1
    ctx.deps.chosen_department = department
    logger.info("Zgloszenie przypisane do %s -> %s", department.value, recipient)
    return f"Wyslano do dzialu {department.value}."


_RETRY_HINT = (
    "Nie wywolales narzedzia send_email. Zrob to teraz: wybierz dzial "
    "najlepiej pasujacy do ponizszego zgloszenia. Jesli zaden nie pasuje, "
    "wybierz 'other'."
)


async def _send_fallback(ctx: RoutingContext, model_output: str = "") -> RoutingResult:
    settings = get_settings()
    recipient = resolve_email(Department.OTHER)
    logger.warning("Model nie wybral dzialu - wysylam awaryjnie na %s", recipient)

    message = build_message(
        sender_email=ctx.sender_email,
        recipient=recipient,
        department=Department.OTHER,
        original_message=ctx.full_message,
        ticket_id=ctx.ticket_id,
        routed_by="fallback",
        subject=ctx.subject,
        mail_from=settings.mail_from,
    )
    await send_message(message, settings.smtp_host, settings.smtp_port)
    ctx.emails_sent += 1

    return RoutingResult(
        ticket_id=ctx.ticket_id,
        department=Department.OTHER,
        recipient=recipient,
        routed_by="fallback",
    )


async def route_message(
    sender_email: str,
    message: str,
    ticket_id: str,
    subject: str | None = None,
) -> RoutingResult:
    settings = get_settings()
    agent = get_agent()
    head = message[: settings.classify_head_chars]
    if len(message) > settings.classify_head_chars:
        logger.debug(
            "Klasyfikacja na %s z %s znakow",
            settings.classify_head_chars,
            len(message),
        )

    ctx = RoutingContext(
        sender_email=sender_email,
        subject=subject or derive_subject(message),
        full_message=message,
        ticket_id=ticket_id,
    )
    limits = UsageLimits(
        request_limit=settings.agent_max_steps,
        tool_calls_limit=settings.agent_max_steps,
    )

    model_output = ""
    try:
        result = await agent.run(head, deps=ctx, usage_limits=limits)
        model_output = _summarize_model_turn(result)
        logger.info("Model odpowiedzial: %s", model_output or "(cisza)")
    except UsageLimitExceeded:
        logger.warning("Przekroczony limit krokow agenta")
    except UnexpectedModelBehavior as exc:
        logger.warning("Model nie potrafil poprawnie wywolac narzedzia: %s", exc)

    if ctx.emails_sent == 0:
        logger.warning("Brak wywolania narzedzia - ponawiam z ostrzejsza instrukcja")
        try:
            result = await agent.run(
                f"{_RETRY_HINT}\n\nZgloszenie:\n{head}", deps=ctx, usage_limits=limits
            )
            model_output = _summarize_model_turn(result) or model_output
            logger.info("Model po ponowieniu: %s", model_output or "(cisza)")
        except (UsageLimitExceeded, UnexpectedModelBehavior) as exc:
            logger.warning("Ponowienie tez sie nie powiodlo: %s", type(exc).__name__)

    if ctx.emails_sent == 0:
        return await _send_fallback(ctx, model_output=model_output)

    department = ctx.chosen_department
    return RoutingResult(
        ticket_id=ticket_id,
        department=department,
        recipient=resolve_email(department),
        routed_by="llm",
    )
