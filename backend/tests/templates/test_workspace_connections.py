"""Per-workspace readiness of the connections a template names (`requires`)."""

import dataclasses
import json
import uuid

import httpx
import pytest
from fastapi import FastAPI

from app.core import crypto
from app.core.config import settings
from app.db.models import CommunityMcpConnection, UserCredential
from app.db.session import get_db
from app.routers.templates import router as templates_router
from app.services import workspace_connections
from app.services.thread_runtime import LOCAL_OWNER_ID
from app.templates import catalog

MUAPI_MANIFEST = {"slug": "muapi", "name": "Muapi", "endpoint": "https://api.muapi.ai/mcp", "auth_mode": "bearer_token"}


@pytest.fixture(autouse=True)
def local_enabled(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "FRONTEND_ORIGINS", "http://localhost:3000")
    monkeypatch.setattr(settings, "LOCAL_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")


async def install(db, slug="muapi", manifest=None, token="mu_secret_token"):
    db.add(CommunityMcpConnection(
        id=str(uuid.uuid4()), owner_id=LOCAL_OWNER_ID, slug=slug, section="community",
        manifest=manifest or MUAPI_MANIFEST, manifest_digest="d" * 64,
    ))
    if token is not None:
        db.add(UserCredential(
            user_id=LOCAL_OWNER_ID, provider="integration:community-mcp:" + slug,
            file_path="-", ciphertext=crypto.encrypt(json.dumps(token)),
        ))
    await db.flush()


async def test_nothing_is_ready_in_an_empty_workspace(db_session):
    assert await workspace_connections.ready_connections(db_session) == frozenset()


async def test_muapi_is_ready_once_installed_with_a_token(db_session):
    await install(db_session)
    assert await workspace_connections.ready_connections(db_session) == frozenset({"muapi"})


async def test_an_installed_listing_without_a_token_is_not_ready(db_session):
    await install(db_session, token=None)
    assert await workspace_connections.muapi_ready(db_session) is False


async def test_a_token_without_the_installed_listing_is_not_ready(db_session):
    db_session.add(UserCredential(
        user_id=LOCAL_OWNER_ID, provider="integration:community-mcp:muapi",
        file_path="-", ciphertext=crypto.encrypt(json.dumps("mu_secret_token")),
    ))
    await db_session.flush()
    assert await workspace_connections.muapi_ready(db_session) is False


async def test_a_listing_with_that_slug_but_another_endpoint_is_not_ready(db_session):
    await install(db_session, manifest={**MUAPI_MANIFEST, "endpoint": "https://tools.example.com/mcp"})
    assert await workspace_connections.muapi_ready(db_session) is False


async def test_an_undecryptable_token_is_not_ready(db_session):
    await install(db_session, token=None)
    db_session.add(UserCredential(
        user_id=LOCAL_OWNER_ID, provider="integration:community-mcp:muapi", file_path="-", ciphertext="not-a-valid-ciphertext",
    ))
    await db_session.flush()
    assert await workspace_connections.muapi_ready(db_session) is False


async def test_the_muapi_computer_key_does_not_count(db_session):
    db_session.add(UserCredential(
        user_id=LOCAL_OWNER_ID, provider="muapi", file_path="-", ciphertext=crypto.encrypt(json.dumps("computer_key")),
    ))
    await db_session.flush()
    assert await workspace_connections.muapi_ready(db_session) is False


def needs_muapi(monkeypatch):
    template = dataclasses.replace(catalog.get("everyday-helper"), id="work-needs-muapi", requires=("muapi",))
    monkeypatch.setattr(catalog, "TEMPLATES", catalog.TEMPLATES + (template,))
    monkeypatch.setattr(catalog, "_BY_ID", {**catalog._BY_ID, template.id: template})
    return template


def test_a_role_that_needs_only_muapi_can_be_added_before_it_is_connected(monkeypatch):
    template = needs_muapi(monkeypatch)
    assert template.is_available(frozenset())
    assert template.missing(frozenset()) == ("muapi",)
    assert template.missing(frozenset({"muapi"})) == ()


def test_a_role_that_needs_an_unconnectable_app_stays_unavailable():
    mailroom = catalog.get("work-mailroom")
    assert not mailroom.is_available(frozenset())
    assert mailroom.missing(frozenset()) == ("email",)
    assert not mailroom.is_available(frozenset({"muapi"}))
    assert catalog.get("everyday-helper").missing(frozenset()) == ()


def test_ready_roles_sort_before_roles_that_still_need_a_connection(monkeypatch):
    template = needs_muapi(monkeypatch)
    ids = [t.id for t in catalog.search(None, None, frozenset())]
    assert ids.index("everyday-helper") < ids.index(template.id) < ids.index("work-mailroom")
    ids_ready = [t.id for t in catalog.search(None, None, frozenset({"muapi"}))]
    assert ids_ready.index(template.id) < ids_ready.index("work-mailroom")


def client(db):
    app = FastAPI()
    app.include_router(templates_router, prefix="/api/v1")

    async def override():
        yield db

    app.dependency_overrides[get_db] = override
    return httpx.AsyncClient(transport=httpx.ASGITransport(app, client=("127.0.0.1", 50000)), base_url="http://localhost")


async def test_the_list_route_reports_missing_connections_per_workspace(db_session, monkeypatch):
    template = needs_muapi(monkeypatch)
    async with client(db_session) as http:
        body = (await http.get("/api/v1/templates")).json()
        by_id = {t["id"]: t for t in body["templates"]}
        assert by_id[template.id]["available"] is True
        assert by_id[template.id]["missing"] == ["muapi"]
        assert by_id["work-mailroom"]["available"] is False
        assert by_id["work-mailroom"]["missing"] == ["email"]
        assert by_id["everyday-helper"]["missing"] == []

        await install(db_session)
        body = (await http.get("/api/v1/templates")).json()
        assert {t["id"]: t for t in body["templates"]}[template.id]["missing"] == []


async def test_the_single_template_route_reports_missing_connections(db_session, monkeypatch):
    template = needs_muapi(monkeypatch)
    async with client(db_session) as http:
        found = (await http.get(f"/api/v1/templates/{template.id}")).json()
        assert found["available"] is True and found["missing"] == ["muapi"]
        assert (await http.get("/api/v1/templates/everyday-helper")).json()["missing"] == []
        assert (await http.get("/api/v1/templates/nope-missing")).status_code == 404
