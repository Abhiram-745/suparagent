"""The business profile over HTTP: read by the person's screens, written only by the person."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from app.services import business_profile
from app.services.local_access_policy import require_local_access

router = APIRouter(prefix="/business-profile", tags=["Business profile"], dependencies=[Depends(require_local_access)])


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: dict[str, str]
    expected_hash: str | None = None


@router.get("")
async def read_profile():
    return business_profile.read()


@router.put("")
async def write_profile(body: ProfileWrite):
    try:
        return business_profile.write(body.fields, expected_hash=body.expected_hash)
    except business_profile.UnknownField as exc:
        raise HTTPException(
            status_code=422, detail={"error_code": "unknown_field", "message": f"No such field: {exc}."}
        ) from None
    except business_profile.ProfileTooLarge as exc:
        raise HTTPException(
            status_code=413, detail={"error_code": "profile_too_large", "message": str(exc)}
        ) from None
    except business_profile.ProfileLooksSecret as exc:
        label = business_profile.FIELDS[exc.field][0]
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "profile_looks_secret",
                "field": exc.field,
                "message": f"{label} looks like it contains a key, token or password. "
                "Remove it: every agent can read this profile.",
            },
        ) from None
    except business_profile.ProfileConflict as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "profile_changed",
                "message": "The business profile changed since it was opened.",
                "current": exc.current["fields"],
                "current_hash": exc.current["hash"],
            },
        ) from None
