import inspect

from app.agent.router import _send_fallback, send_email
from app.domain.departments import DEPARTMENT_EMAILS, Department


async def test_second_call_does_not_send(ctx, sent):
    await send_email(ctx, Department.HELP_DESK)
    result = await send_email(ctx, Department.IT)

    assert len(sent) == 1
    assert ctx.deps.emails_sent == 1
    assert isinstance(result, str)
    assert sent[0]["To"] == DEPARTMENT_EMAILS[Department.HELP_DESK]


async def test_fallback_sends_to_other(ctx, sent):
    result = await _send_fallback(ctx.deps)

    assert len(sent) == 1
    assert result.recipient == DEPARTMENT_EMAILS[Department.OTHER]
    assert result.routed_by == "fallback"
    assert sent[0]["X-Routed-By"] == "fallback"
    assert sent[0]["Reply-To"] == ctx.deps.sender_email


def test_tool_has_no_parameter_for_the_address():
    """Model podaje wylacznie dzial. Gdyby ktos dodal do narzedzia parametr
    z adresem, tematem albo trescia, model moglby je nadpisac - i caly model
    bezpieczenstwa tego projektu przestalby dzialac."""
    params = set(inspect.signature(send_email).parameters)
    assert params == {"ctx", "department"}
