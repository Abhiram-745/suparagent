"""Spending limits for paid marketplace tools.

A marketplace tool is paid when its input takes `max_cost_usd`, the cap the caller sets for one call. Before such a
call goes out, the cap is reserved against three owner limits: per call, per run (a scheduled run or one chat turn),
and per worker per calendar month (UTC). The limits are settings only the owner changes; no agent tool reads or
writes them. The amounts are quotes, not invoices: a call settles at the cost the service reports, or at its cap when
the service reports none.
"""
import json
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, InvalidOperation

from sqlalchemy import func, select

from app.core import app_settings
from app.db.models.agent import Agent
from app.db.models.routine import Routine
from app.db.models.spend_ledger import SpendLedger

GUARD_ARGUMENT = "max_cost_usd"
LIMIT_KEYS = {
    "per_call": "SPEND_PER_CALL_CENTS",
    "per_run": "SPEND_PER_RUN_CENTS",
    "monthly": "SPEND_PER_WORKER_MONTH_CENTS",
}
REFUSAL_TEXT = {
    "per_call": "This call's cost cap is above the per-call spending limit.",
    "per_run": "This run would go over its spending limit.",
    "monthly": "This worker would go over its monthly spending limit.",
    "no_cap": "A paid call needs a cost cap greater than zero.",
}
PAUSE_REASON = "spend_limit"


def is_guarded(input_schema: dict | None) -> bool:
    properties = (input_schema or {}).get("properties")
    return isinstance(properties, dict) and GUARD_ARGUMENT in properties


def to_cents(value) -> int | None:
    """Round a dollar amount up to whole cents; None when it is not a usable non-negative number."""
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0:
        return None
    return int((amount * 100).to_integral_value(rounding=ROUND_CEILING))


def limits() -> dict[str, int]:
    return {name: int(app_settings.get(key, live=True)) for name, key in LIMIT_KEYS.items()}


def month_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _counted():
    return func.coalesce(SpendLedger.settled_cents, SpendLedger.cap_cents)


async def run_spent(db, run_key: str) -> int:
    total = await db.scalar(select(func.coalesce(func.sum(_counted()), 0)).where(
        SpendLedger.run_key == run_key, SpendLedger.status.in_(("reserved", "settled"))))
    return int(total or 0)


async def month_spent(db, owner_id: str, agent_id: int, now: datetime | None = None) -> int:
    total = await db.scalar(select(func.coalesce(func.sum(_counted()), 0)).where(
        SpendLedger.owner_id == owner_id, SpendLedger.agent_id == agent_id,
        SpendLedger.status.in_(("reserved", "settled")), SpendLedger.created_at >= month_start(now)))
    return int(total or 0)


async def reserve(db, *, owner_id: str, agent_id: int, run_key: str, routine_run_id: int | None, tool: str,
                  cap_cents: int | None) -> tuple[SpendLedger, str | None]:
    """Record a call against the limits. Returns the ledger row and a refusal reason (None when it may go out).

    A refusal is recorded too, so a run can show what stopped it. The caller commits."""
    reason = None
    if cap_cents is None or cap_cents <= 0:
        reason = "no_cap"
    else:
        current = limits()
        if cap_cents > current["per_call"]:
            reason = "per_call"
        elif await run_spent(db, run_key) + cap_cents > current["per_run"]:
            reason = "per_run"
        elif await month_spent(db, owner_id, agent_id) + cap_cents > current["monthly"]:
            reason = "monthly"
    row = SpendLedger(owner_id=owner_id, agent_id=agent_id, run_key=run_key, routine_run_id=routine_run_id, tool=tool,
                      status="refused" if reason else "reserved", cap_cents=cap_cents or 0, reason=reason)
    db.add(row)
    await db.flush()
    return row, reason


def _find_cost(result) -> int | None:
    """The cost a service reports for a finished call, in cents, or None when it reports none."""
    if isinstance(result, dict):
        for key in ("estimated_cost_usd", "cost_usd", "charged_usd"):
            if key in result:
                found = to_cents(result[key])
                if found is not None:
                    return found
        for value in result.values():
            if isinstance(value, (dict, list)):
                found = _find_cost(value)
                if found is not None:
                    return found
    elif isinstance(result, list):
        for value in result:
            found = _find_cost(value)
            if found is not None:
                return found
    return None


def reported_cost(result) -> int | None:
    """Cost in cents from structured content, or from a JSON text block of a tool result."""
    found = _find_cost(result.get("structuredContent")) if isinstance(result, dict) else None
    if found is not None or not isinstance(result, dict):
        return found
    for item in result.get("content", []) if isinstance(result.get("content"), list) else []:
        text = item.get("text") if isinstance(item, dict) else None
        if isinstance(text, str) and text.lstrip().startswith("{"):
            try:
                found = _find_cost(json.loads(text))
            except ValueError:
                continue
            if found is not None:
                return found
    return None


async def settle(db, ledger_id: int, cost_cents: int | None) -> None:
    row = await db.get(SpendLedger, ledger_id)
    if row is None or row.status != "reserved":
        return
    row.status, row.settled_at = "settled", datetime.now(UTC)
    # No reported cost: keep the reserved cap, the safe side of an unknown charge.
    row.settled_cents = row.cap_cents if cost_cents is None else cost_cents


async def release(db, ledger_id: int) -> None:
    row = await db.get(SpendLedger, ledger_id)
    if row is not None and row.status == "reserved":
        row.status, row.settled_at, row.settled_cents = "released", datetime.now(UTC), 0


async def run_summary(db, run_key: str) -> dict | None:
    rows = (await db.scalars(select(SpendLedger).where(SpendLedger.run_key == run_key).order_by(SpendLedger.id))).all()
    if not rows:
        return None
    spent = sum((r.settled_cents if r.settled_cents is not None else r.cap_cents)
                for r in rows if r.status in ("reserved", "settled"))
    return {"cents": int(spent), "calls": sum(1 for r in rows if r.status in ("reserved", "settled")),
            "refused": [r.reason for r in rows if r.status == "refused" and r.reason]}


async def worker_month(db, owner_id: str, agent_id: int) -> dict:
    return {"agent_id": agent_id, "month_cents": await month_spent(db, owner_id, agent_id)}


async def pause_for_month_limit(db, routine: Routine) -> None:
    routine.paused, routine.paused_reason, routine.next_run_at = True, PAUSE_REASON, None


async def scheduled_paid_use(db, agent_id: int) -> bool:
    agent = await db.get(Agent, agent_id)
    return bool(agent is not None and agent.scheduled_paid_use)
