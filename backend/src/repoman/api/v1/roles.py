from fastapi import APIRouter
from sqlalchemy import select

from repoman.api.v1.schemas import RoleOut
from repoman.auth.dependencies import AdminPrincipal
from repoman.db.deps import DbSession
from repoman.db.models import IMPLICIT_ROLES, Role

router = APIRouter(prefix="/roles", tags=["roles"])


@router.get("", response_model=list[RoleOut])
async def list_roles(_: AdminPrincipal, db: DbSession) -> list[RoleOut]:
    roles = await db.scalars(select(Role).order_by(Role.builtin.desc(), Role.name))
    return [
        RoleOut(
            id=role.id,
            name=role.name,
            builtin=role.builtin,
            description=role.description,
            assignable=role.name not in IMPLICIT_ROLES,
        )
        for role in roles
    ]
