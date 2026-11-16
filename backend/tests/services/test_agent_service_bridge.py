"""A mailbox/number provider's tools reach an agent only while one of its resources is assigned to it."""
from uuid import uuid4

import pytest
from sqlalchemy import delete

from app.db.models import Agent, AgentServiceAssignment, AgentServiceProvider, AgentServiceResource
from app.services.agent_service_store import remove_provider_data
from app.services.community_mcp_bridge import CommunityMcpBridge
from tests.services.test_custom_mcp_bridge import FakeRemote, mounted, remote, world  # noqa: F401
from tests.services.thread_harness import cleanup, owner, sessions  # noqa: F401


@pytest.fixture
async def provider(world, sessions, owner):
    """The world's connection, marked as a provider holding one resource that no agent has yet."""
    connection = world[3]
    resource_id = uuid4().hex
    async with sessions() as db:
        db.add(AgentServiceProvider(connection_id=connection.id, provider="agentmail", resource_limit=3))
        await db.flush()
        db.add(AgentServiceResource(id=resource_id, owner_id=owner, connection_id=connection.id, kind="email",
                                    address="helper@agentmail.to", label="Helper inbox"))
        await db.commit()
    yield resource_id
    async with sessions() as db:
        await remove_provider_data(db, connection.id)
        await db.commit()


async def assign(sessions, agent_id, resource_id):
    async with sessions() as db:
        db.add(AgentServiceAssignment(agent_id=agent_id, resource_id=resource_id))
        await db.commit()


async def test_a_provider_with_nothing_assigned_to_the_agent_is_not_mounted(world, provider):
    assert await mounted(world) == []


async def test_a_resource_assigned_to_another_agent_does_not_mount_it_here(world, provider, sessions, owner):
    async with sessions() as db:
        other = Agent(owner_id=owner, name="Someone else")
        db.add(other)
        await db.commit()
    try:
        await assign(sessions, other.id, provider)
        assert await mounted(world) == []
    finally:
        async with sessions() as db:
            await db.execute(delete(AgentServiceAssignment).where(AgentServiceAssignment.agent_id == other.id))
            await db.delete(await db.get(Agent, other.id))
            await db.commit()


async def test_an_assigned_resource_mounts_the_providers_granted_tools(world, provider, sessions):
    await assign(sessions, world[4].id, provider)
    [item] = await mounted(world)
    assert item["kind"] == "custom" and item["grant"]["tool_name"] == "lookup"


async def test_an_ordinary_connection_is_unaffected(world):
    assert len(await mounted(world)) == 1


async def test_removing_the_assignment_stops_a_running_turn_before_its_next_call(world, provider, sessions, remote):
    await assign(sessions, world[4].id, provider)
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        async with sessions() as db:
            await db.execute(delete(AgentServiceAssignment).where(AgentServiceAssignment.agent_id == world[4].id))
            await db.commit()
        result = await bridge.execute(alias, {"q": "x"})
        assert result["code"] == "revoked"
        assert remote.built == [] and remote.calls == []
    finally:
        await bridge.close()
