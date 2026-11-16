"""Cleanup shared by the custom MCP and agent-service routers (kept here so neither imports the other's routes)."""

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentServiceAssignment, AgentServiceProvider, AgentServiceResource


async def remove_provider_data(db: AsyncSession, connection_id: str) -> None:
    """Drop the designation, resources and assignments of a connection. Call inside a write transaction."""
    resource_ids = select(AgentServiceResource.id).where(AgentServiceResource.connection_id == connection_id)
    await db.execute(delete(AgentServiceAssignment).where(AgentServiceAssignment.resource_id.in_(resource_ids)))
    await db.execute(delete(AgentServiceResource).where(AgentServiceResource.connection_id == connection_id))
    await db.execute(delete(AgentServiceProvider).where(AgentServiceProvider.connection_id == connection_id))


async def unassigned_providers(db: AsyncSession, agent_id: int, connection_ids: list[str]) -> set[str]:
    """Of these connections, the ones that are mailbox/number providers where the agent has no resource.

    A connection nobody marked as a provider is never in the result. Used at mount time and again on
    every call, so removing an assignment stops a running turn at its next call."""
    if not connection_ids:
        return set()
    providers = set((await db.scalars(select(AgentServiceProvider.connection_id).where(
        AgentServiceProvider.connection_id.in_(connection_ids)))).all())
    if not providers:
        return set()
    assigned = set((await db.scalars(
        select(AgentServiceResource.connection_id)
        .join(AgentServiceAssignment, AgentServiceAssignment.resource_id == AgentServiceResource.id)
        .where(AgentServiceAssignment.agent_id == agent_id, AgentServiceResource.connection_id.in_(providers))
    )).all())
    return providers - assigned
