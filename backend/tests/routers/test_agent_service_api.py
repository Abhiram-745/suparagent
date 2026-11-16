"""/api/v1/integrations/agent-services: provider designation, resources and agent assignment.

Everything starts empty: a provider has no resources, a resource has no agents, and an assignment
alone grants no tool."""
import pytest
from sqlalchemy import select

from app.db.models import Agent, AgentServiceAssignment, AgentServiceProvider, AgentServiceResource, CustomMcpToolGrant
from tests.routers.test_custom_mcp_api import (  # noqa: F401
    PATH, admin, agent_id, app, auth_settings, client, code_of, factory, login, make, owner, pairing_code,
    server, set_owner,
)

API = "/api/v1/integrations/agent-services"


async def named_agent(factory, owner, name) -> int:
    async with factory() as db:
        agent = Agent(owner_id=owner, name=name, instructions="help", provider="claude", approval_mode="ask")
        db.add(agent)
        await db.commit()
        return agent.id


async def provider(admin, name="Mail", kind="agentmail", limit=3):
    conn = await make(admin, name=name)
    put = await admin.put(f"{API}/providers/{conn['id']}", json={"provider": kind, "resource_limit": limit})
    assert put.status_code == 200, put.text
    return conn


async def resource(admin, conn, address="helper@agentmail.to", kind="email", **body):
    return await admin.post(f"{API}/resources", json={
        "connection_id": conn["id"], "kind": kind, "address": address, "label": "Helper inbox", **body})


async def test_a_new_provider_has_no_resources_and_a_new_resource_has_no_agents(admin):
    conn = await provider(admin)
    listed = (await admin.get(f"{API}/providers")).json()
    assert [(p["connection_id"], p["resource_count"], p["resource_limit"]) for p in listed] == [(conn["id"], 0, 3)]
    created = await resource(admin, conn)
    assert created.status_code == 201 and created.json()["agent_ids"] == []


async def test_only_an_existing_connection_can_become_a_provider(admin):
    missing = await admin.put(f"{API}/providers/nope", json={"provider": "agentmail"})
    assert missing.status_code == 404 and code_of(missing) == "connection_not_found"
    assert (await admin.get(f"{API}/providers")).json() == []


async def test_resource_needs_a_provider_and_fits_its_kind(admin):
    plain = await make(admin)
    refused = await resource(admin, plain)
    assert refused.status_code == 404 and code_of(refused) == "provider_not_found"
    mail = await provider(admin)
    wrong = await resource(admin, mail, address="+14155550100", kind="phone")
    assert wrong.status_code == 422 and code_of(wrong) == "kind_not_supported_by_provider"


@pytest.mark.parametrize("kind,address", [
    ("email", "not-an-address"), ("email", "a@b"), ("email", "a b@example.com"),
    ("phone", "4155550100"), ("phone", "+0123456789"), ("phone", "+1 415 555 0100"), ("phone", "+123"),
])
async def test_addresses_must_be_well_formed(admin, kind, address):
    conn = await provider(admin, kind="other")
    refused = await resource(admin, conn, address=address, kind=kind)
    assert refused.status_code == 422 and code_of(refused) == "invalid_address"


async def test_email_is_stored_lowercase_and_not_added_twice(admin):
    conn = await provider(admin)
    first = await resource(admin, conn, address="  Helper@AgentMail.to ")
    assert first.json()["address"] == "helper@agentmail.to"
    again = await resource(admin, conn, address="helper@agentmail.to")
    assert again.status_code == 409 and code_of(again) == "resource_exists"


async def test_the_owner_set_limit_caps_resources_and_cannot_drop_below_what_exists(admin):
    conn = await provider(admin, limit=2)
    assert (await resource(admin, conn, address="a@agentmail.to")).status_code == 201
    assert (await resource(admin, conn, address="b@agentmail.to")).status_code == 201
    full = await resource(admin, conn, address="c@agentmail.to")
    assert full.status_code == 409 and code_of(full) == "resource_limit_reached"
    lower = await admin.put(f"{API}/providers/{conn['id']}", json={"provider": "agentmail", "resource_limit": 1})
    assert lower.status_code == 409 and code_of(lower) == "limit_below_existing"
    raised = await admin.put(f"{API}/providers/{conn['id']}", json={"provider": "agentmail", "resource_limit": 3})
    assert raised.json()["resource_limit"] == 3 and raised.json()["resource_count"] == 2


async def test_a_phone_number_is_kept_in_one_form(admin):
    conn = await provider(admin, name="Phone", kind="agentphone")
    created = await resource(admin, conn, address="+14155550100", kind="phone", provider_resource_id=" num_1 ")
    assert created.status_code == 201
    assert created.json()["address"] == "+14155550100" and created.json()["provider_resource_id"] == "num_1"


async def test_assigning_replaces_the_set_and_an_empty_list_removes_everyone(admin, factory, owner):
    conn = await provider(admin)
    res = (await resource(admin, conn)).json()
    first, second = await named_agent(factory, owner, "One"), await named_agent(factory, owner, "Two")
    both = await admin.put(f"{API}/resources/{res['id']}/agents", json={"agent_ids": [second, first, first]})
    assert both.json()["agent_ids"] == sorted([first, second])
    only = await admin.put(f"{API}/resources/{res['id']}/agents", json={"agent_ids": [second]})
    assert only.json()["agent_ids"] == [second]
    assert [r["id"] for r in (await admin.get(f"{API}/agents/{second}/resources")).json()] == [res["id"]]
    assert (await admin.get(f"{API}/agents/{first}/resources")).json() == []
    none = await admin.put(f"{API}/resources/{res['id']}/agents", json={"agent_ids": []})
    assert none.json()["agent_ids"] == []


async def test_an_assignment_grants_no_tool(admin, factory, owner):
    conn = await provider(admin)
    res = (await resource(admin, conn)).json()
    agent = await agent_id(factory, owner)
    await admin.put(f"{API}/resources/{res['id']}/agents", json={"agent_ids": [agent]})
    async with factory() as db:
        assert (await db.scalars(select(CustomMcpToolGrant))).all() == []


async def test_an_unknown_agent_is_refused_and_changes_nothing(admin, factory, owner):
    conn = await provider(admin)
    res = (await resource(admin, conn)).json()
    agent = await agent_id(factory, owner)
    await admin.put(f"{API}/resources/{res['id']}/agents", json={"agent_ids": [agent]})
    refused = await admin.put(f"{API}/resources/{res['id']}/agents", json={"agent_ids": [agent, 999999999]})
    assert refused.status_code == 404 and code_of(refused) == "agent_not_found"
    assert (await admin.get(f"{API}/resources")).json()[0]["agent_ids"] == [agent]


async def test_deleting_a_resource_removes_its_assignments(admin, factory, owner):
    conn = await provider(admin)
    res = (await resource(admin, conn)).json()
    agent = await agent_id(factory, owner)
    await admin.put(f"{API}/resources/{res['id']}/agents", json={"agent_ids": [agent]})
    assert (await admin.delete(f"{API}/resources/{res['id']}")).status_code == 204
    assert (await admin.get(f"{API}/resources")).json() == []
    async with factory() as db:
        assert (await db.scalars(select(AgentServiceAssignment))).all() == []
    assert (await admin.delete(f"{API}/resources/{res['id']}")).status_code == 404


async def test_removing_the_provider_designation_removes_resources_but_not_the_connection(admin, factory, owner):
    conn = await provider(admin)
    res = (await resource(admin, conn)).json()
    await admin.put(f"{API}/resources/{res['id']}/agents", json={"agent_ids": [await agent_id(factory, owner)]})
    assert (await admin.delete(f"{API}/providers/{conn['id']}")).status_code == 204
    async with factory() as db:
        assert (await db.scalars(select(AgentServiceProvider))).all() == []
        assert (await db.scalars(select(AgentServiceResource))).all() == []
        assert (await db.scalars(select(AgentServiceAssignment))).all() == []
    assert [c["id"] for c in (await admin.get(f"{PATH}/connections")).json()] == [conn["id"]]


async def test_deleting_the_connection_removes_everything_held_under_it(admin, factory, owner):
    conn = await provider(admin)
    res = (await resource(admin, conn)).json()
    await admin.put(f"{API}/resources/{res['id']}/agents", json={"agent_ids": [await agent_id(factory, owner)]})
    assert (await admin.delete(f"{PATH}/connections/{conn['id']}")).status_code == 204
    async with factory() as db:
        assert (await db.scalars(select(AgentServiceProvider))).all() == []
        assert (await db.scalars(select(AgentServiceResource))).all() == []
        assert (await db.scalars(select(AgentServiceAssignment))).all() == []
