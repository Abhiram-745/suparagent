"""A mailbox/number provider's tools reach an agent only while one of its resources is assigned to it."""
from types import SimpleNamespace as NS
from uuid import uuid4

import pytest
from sqlalchemy import delete, select

from app import community_mcp
from app.db.models import (
    Agent, AgentServiceAssignment, AgentServiceAudit, AgentServiceProvider, AgentServiceResource,
)
from app.services import approval_modes, thread_store, tool_policy
from app.services.agent_service_store import remove_provider_data
from app.services.community_mcp_bridge import PREFIX, CommunityMcpBridge
from tests.services.test_custom_mcp_bridge import FakeRemote, approve, mounted, remote, world  # noqa: F401
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


async def test_the_approval_card_names_the_agent_owned_address_that_would_act(world, provider, sessions):
    await assign(sessions, world[4].id, provider)
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        summary = bridge.approval_summary(alias, {"q": "x"})
        assert summary == "Custom MCP My server (tools.example.com): lookup | agent address: helper@agentmail.to"
    finally:
        await bridge.close()


async def test_an_ordinary_connections_card_does_not_mention_an_agent_address(world):
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        assert "agent address" not in bridge.approval_summary(alias, {"q": "x"})
    finally:
        await bridge.close()


@pytest.mark.parametrize("mode", approval_modes.MODES)
async def test_no_approval_mode_lets_a_provider_tool_run_without_a_card(world, provider, sessions, mode):
    await assign(sessions, world[4].id, provider)
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        run = NS(ctx=NS(media_review_only=False, draft_only=False, community_tools=[alias]))
        decision = tool_policy.automatic(PREFIX + alias, mode, run, {"q": "x"})
        assert decision is None or decision[0] == "denied"
    finally:
        await bridge.close()


async def test_an_approval_for_one_recipient_does_not_cover_another(world, provider, sessions, remote):
    await assign(sessions, world[4].id, provider)
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        await approve(sessions, world[1], alias, {"q": "alice@example.com"})
        assert (await bridge.execute(alias, {"q": "bob@example.com"}))["code"] == "not_approved"
        assert remote.calls == []
    finally:
        await bridge.close()


async def test_a_denied_approval_never_reaches_the_provider(world, provider, sessions, remote):
    await assign(sessions, world[4].id, provider)
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        async with sessions() as db:
            row = await thread_store.create_approval(
                db, thread_id=world[1].thread_id, turn_id=world[1].turn_id, request_id="d1", tool=PREFIX + alias,
                input={"q": "x"}, summary="x", kind="other", owner_token=world[1].owner_token)
            await thread_store.decide_approval(db, row.id, "denied", by={"by": "person"})
        assert (await bridge.execute(alias, {"q": "x"}))["code"] == "not_approved"
        assert remote.calls == []
    finally:
        await bridge.close()


@pytest.fixture
async def audit_rows(sessions, owner):
    async def rows():
        async with sessions() as db:
            return (await db.scalars(select(AgentServiceAudit).where(AgentServiceAudit.owner_id == owner))).all()
    yield rows
    async with sessions() as db:
        await db.execute(delete(AgentServiceAudit).where(AgentServiceAudit.owner_id == owner))
        await db.commit()


async def test_an_approved_provider_call_is_recorded_without_its_arguments(world, provider, sessions, remote, audit_rows):
    await assign(sessions, world[4].id, provider)
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        await approve(sessions, world[1], alias, {"q": "the private message body"})
        assert (await bridge.execute(alias, {"q": "the private message body"}))["content"][0]["text"] == "ok"
        [row] = await audit_rows()
        assert (row.agent_id, row.agent_name, row.provider, row.tool_name) == (world[4].id, "Tools", "agentmail", "lookup")
        assert row.resources == ["helper@agentmail.to"] and row.outcome == "completed"
        assert row.connection_id == world[3].id and row.thread_id == world[1].thread_id
        stored = " ".join(str(getattr(row, column.name)) for column in AgentServiceAudit.__table__.columns)
        assert "private message body" not in stored and "sk_custom_SECRET_value" not in stored
    finally:
        await bridge.close()


async def test_a_call_that_was_not_approved_leaves_no_record(world, provider, sessions, remote, audit_rows):
    await assign(sessions, world[4].id, provider)
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        assert (await bridge.execute(alias, {"q": "x"}))["code"] == "not_approved"
        assert await audit_rows() == []
    finally:
        await bridge.close()


async def test_an_uncertain_outcome_is_recorded_as_such(world, provider, sessions, monkeypatch, audit_rows):
    class Flaky(FakeRemote):
        async def call_tool(self, name, arguments):
            raise community_mcp.McpError("remote_unavailable", "lost", 502)

    monkeypatch.setattr(community_mcp, "RemoteMcpSession", Flaky)
    await assign(sessions, world[4].id, provider)
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        await approve(sessions, world[1], alias, {"q": "x"})
        assert (await bridge.execute(alias, {"q": "x"}))["code"] == "outcome_unknown"
        [row] = await audit_rows()
        assert row.outcome == "outcome_unknown"
    finally:
        await bridge.close()


async def test_an_ordinary_connection_call_is_not_recorded(world, sessions, remote, audit_rows):
    bridge = CommunityMcpBridge(world[0], world[1], await mounted(world))
    try:
        [alias] = bridge.aliases_allowed
        await approve(sessions, world[1], alias, {"q": "x"})
        assert (await bridge.execute(alias, {"q": "x"}))["content"][0]["text"] == "ok"
        assert await audit_rows() == []
    finally:
        await bridge.close()
