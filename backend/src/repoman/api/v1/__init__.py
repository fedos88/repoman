from fastapi import APIRouter

from repoman.api.v1 import auth, jobs, ldap, me, roles, system, users

router = APIRouter(prefix="/api/v1")
router.include_router(system.router)
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(users.router)
router.include_router(roles.router)
router.include_router(ldap.router)
router.include_router(jobs.router)
