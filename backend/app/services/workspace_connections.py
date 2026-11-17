"""Which named connections this workspace can use right now.

A template names the connections a role is built around (`requires`). This
module answers, from local state only, which of those are ready: it makes no
network call and reads no secret value beyond checking one decrypts.

"muapi" is ready only when the person has installed the Muapi listing from the
marketplace (a pinned `community_mcp_connection` row for the Muapi MCP
endpoint) and saved its bearer token. The hosted preview's Muapi model
provider and the Muapi cloud-computer key are separate things and never count.
"""

import json
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CommunityMcpConnection
from app.db.transactions import release_snapshot
from app.services import user_credential_service
from app.services.thread_runtime import LOCAL_OWNER_ID

MUAPI_SLUG = "muapi"
_MUAPI_HOST = "muapi.ai"
_COMMUNITY_CREDENTIAL_PREFIX = "integration:community-mcp:"


def _is_muapi_endpoint(manifest: dict) -> bool:
    endpoint = manifest.get("endpoint") if isinstance(manifest, dict) else None
    host = urlparse(endpoint).hostname if isinstance(endpoint, str) else None
    return bool(host) and (host == _MUAPI_HOST or host.endswith("." + _MUAPI_HOST))


async def _has_token(db: AsyncSession, slug: str) -> bool:
    try:
        found = await user_credential_service.get_decrypted(db, LOCAL_OWNER_ID, _COMMUNITY_CREDENTIAL_PREFIX + slug)
        return found is not None and isinstance(json.loads(found[0]), str) and bool(json.loads(found[0]))
    except Exception:  # noqa: BLE001 - an undecryptable secret is treated as absent
        return False
    finally:
        await release_snapshot(db)


async def muapi_ready(db: AsyncSession) -> bool:
    row = await db.scalar(select(CommunityMcpConnection).where(
        CommunityMcpConnection.owner_id == LOCAL_OWNER_ID,
        CommunityMcpConnection.slug == MUAPI_SLUG,
    ))
    if row is None or not _is_muapi_endpoint(row.manifest):
        return False
    return await _has_token(db, MUAPI_SLUG)


async def ready_connections(db: AsyncSession) -> frozenset[str]:
    """The template connection names that are ready in this workspace."""
    ready: set[str] = set()
    if await muapi_ready(db):
        ready.add("muapi")
    return frozenset(ready)
