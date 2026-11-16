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
