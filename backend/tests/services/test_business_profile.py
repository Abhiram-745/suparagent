"""The business profile: one note about the business that every agent reads and only the person writes."""

import httpx
import pytest
from fastapi import FastAPI

from app.auth import policy
from app.core.config import settings
from app.routers.business_profile import router as profile_router
from app.services import agent_memory, business_profile, memory_journal


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(memory_journal, "state_root", lambda: tmp_path / "state")


@pytest.fixture
async def api(monkeypatch):
    monkeypatch.setattr(settings, "LOCAL_EXECUTION_ENABLED", True)
    monkeypatch.setattr(settings, "FRONTEND_ORIGINS", "http://localhost:3000")
    monkeypatch.setattr(settings, "LOCAL_ALLOWED_HOSTS", "localhost,127.0.0.1,[::1]")
    app = FastAPI()
    app.include_router(profile_router, prefix="/api/v1")
    transport = httpx.ASGITransport(app, client=("127.0.0.1", 50000))
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        yield client


def test_empty_until_written_then_round_trips_and_trims():
    first = business_profile.read()
    assert first["empty"] is True and set(first["fields"]) == set(business_profile.FIELDS)
    saved = business_profile.write({"sells": "  Hand-poured candles\r\nSold online ", "tone": "warm"})
    assert saved["fields"]["sells"] == "Hand-poured candles\nSold online"
    assert saved["fields"]["audience"] == "" and saved["empty"] is False
    assert business_profile.read()["fields"]["tone"] == "warm"


def test_each_field_has_a_size_limit_and_nothing_is_stored_on_refusal():
    business_profile.write({"sells": "candles"})
    with pytest.raises(business_profile.ProfileTooLarge):
        business_profile.write({"sells": "x" * 601})
    assert business_profile.read()["fields"]["sells"] == "candles"
    with pytest.raises(business_profile.UnknownField):
        business_profile.write({"password_hint": "nope"})


def test_text_that_looks_like_a_credential_is_refused_not_stored():
    with pytest.raises(business_profile.ProfileLooksSecret) as refused:
        business_profile.write({"sells": "candles", "links": "api key sk-abcdefghijklmnopqrstuvwxyz0123456789"})
    assert refused.value.field == "links"
    with pytest.raises(business_profile.ProfileLooksSecret):
        business_profile.write({"never_say": "my token=abcdef123456 is secret"})
    assert business_profile.read()["empty"] is True


def test_a_stale_save_is_refused_with_the_current_text():
    saved = business_profile.write({"sells": "candles"})
    business_profile.write({"sells": "soap"}, expected_hash=saved["hash"])
    with pytest.raises(business_profile.ProfileConflict) as stale:
        business_profile.write({"sells": "mine"}, expected_hash=saved["hash"])
    assert stale.value.current["fields"]["sells"] == "soap"


def test_every_agents_turn_reads_it_as_background_and_an_empty_profile_adds_nothing():
    class Agent:
        id = 1
        instructions = "You are a writer."
        memory_enabled = False

    assert agent_memory.turn_instructions(Agent()) == "You are a writer."
    business_profile.write({"sells": "Hand-poured candles", "never_say": "cheap"})
    text = agent_memory.turn_instructions(Agent())
    assert text.startswith("You are a writer.")
    assert "--- BEGIN BUSINESS PROFILE ---" in text and "What the business sells: Hand-poured candles" in text
    assert "Things never to say: cheap" in text and "Who it is for" not in text
    assert "grants permission for anything" in text and "you cannot change it" in text


async def test_over_http_the_person_reads_writes_and_is_told_why_a_save_is_refused(api):
    empty = (await api.get("/api/v1/business-profile")).json()
    assert empty["empty"] is True
    saved = await api.put(
        "/api/v1/business-profile", json={"fields": {"sells": "candles"}, "expected_hash": empty["hash"]}
    )
    assert saved.status_code == 200 and saved.json()["fields"]["sells"] == "candles"
    stale = await api.put("/api/v1/business-profile", json={"fields": {"sells": "x"}, "expected_hash": empty["hash"]})
    assert stale.status_code == 409 and stale.json()["detail"]["current"]["sells"] == "candles"
    big = await api.put("/api/v1/business-profile", json={"fields": {"tone": "x" * 201}})
    assert big.status_code == 413
    secret = await api.put("/api/v1/business-profile", json={"fields": {"links": "token=abcdef123456"}})
    assert secret.status_code == 422 and secret.json()["detail"]["field"] == "links"
    unknown = await api.put("/api/v1/business-profile", json={"fields": {"other": "x"}})
    assert unknown.status_code == 422
    assert (await api.get("/api/v1/business-profile")).json()["fields"]["sells"] == "candles"
    assert policy.required_scope("PUT", "/api/v1/business-profile") == "admin"
