from fastapi import APIRouter, Request
from pydantic import BaseModel

from repoman import __version__
from repoman.db.deps import DbSession
from repoman.ldap.service import get_settings as get_ldap_settings

router = APIRouter(prefix="/system", tags=["system"])


class SystemInfo(BaseModel):
    version: str
    base_url: str | None
    ldap_enabled: bool


@router.get("/info", response_model=SystemInfo)
async def get_system_info(request: Request, db: DbSession) -> SystemInfo:
    return SystemInfo(
        version=__version__,
        base_url=request.app.state.settings.base_url,
        ldap_enabled=(await get_ldap_settings(db)).enabled,
    )
