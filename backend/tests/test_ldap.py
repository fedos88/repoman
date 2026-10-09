import pytest
from fastapi import FastAPI
from sqlalchemy import select

from repoman.crypto import SecretBox, SecretDecryptionError
from repoman.db.models import Job, LdapSettings, User
from repoman.jobs.runner import JobRunner
from repoman.ldap.directory import LdapError, guid_filter_value, sid_to_str
from repoman.users.names import normalize_login
from tests.fakes import ADMINS_DN, ADMINS_SID, USERS_DN, USERS_SID, FakeDirectory

SETTINGS = {
    "enabled": True,
    "mode": "ldaps",
    "host": "dc01.example.test",
    "port": 636,
    "bind_dn": "EXAMPLE\\svc-repoman",
    "bind_password": "service-pass",
    "user_base_dn": "DC=example,DC=test",
}


@pytest.fixture
async def admin_api(api, create_user):
    await create_user("root", roles=("admin",))
    await api.login("root", "password123")
    return api


@pytest.fixture
async def ldap_enabled(admin_api, directory: FastAPI):
    response = await admin_api.put("/api/v1/ldap/settings", json=SETTINGS)
    assert response.status_code == 200, response.text
    response = await admin_api.post(
        "/api/v1/ldap/group-mappings", json={"group_dn": ADMINS_DN, "role": "admin"}
    )
    assert response.status_code == 201, response.text
    return directory


async def run_sync(app: FastAPI) -> dict:
    """Run queued jobs and return the latest one."""
    runner: JobRunner = app.state.job_runner
    await runner.run_pending()
    async with app.state.db_sessionmaker() as db:
        job = await db.scalar(select(Job).order_by(Job.id.desc()).limit(1))
    return {"status": job.status, "result": job.result, "error": job.error}


# --- units ------------------------------------------------------------------------------


def test_normalize_login() -> None:
    assert normalize_login(" EXAMPLE\\Alice.Smith ") == "alice.smith"
    assert normalize_login("alice.smith@example.test") == "alice.smith"
    assert normalize_login("alice") == "alice"


def test_sid_and_guid_helpers() -> None:
    raw = bytes.fromhex("010500000000000515000000a1b2c3d4a1b2c3d4a1b2c3d453040000")
    assert sid_to_str(raw).startswith("S-1-5-21-") and sid_to_str(raw).endswith("-1107")
    assert guid_filter_value("11d3d496-bc53-4afb-b530-69bac6686eac").startswith("\\96\\d4\\d3\\11")


def test_secret_box_roundtrip_and_wrong_key() -> None:
    token = SecretBox("a" * 32).encrypt("s3cret")
    assert SecretBox("a" * 32).decrypt(token) == "s3cret"
    with pytest.raises(SecretDecryptionError):
        SecretBox("b" * 32).decrypt(token)


# --- settings ---------------------------------------------------------------------------


async def test_settings_defaults_and_password_write_only(app: FastAPI, admin_api) -> None:
    assert (await admin_api.get("/api/v1/system/info")).json()["ldap_enabled"] is False
    defaults = (await admin_api.get("/api/v1/ldap/settings")).json()
    assert defaults["enabled"] is False and defaults["mode"] == "ldaps"
    assert defaults["has_bind_password"] is False

    saved = (await admin_api.put("/api/v1/ldap/settings", json=SETTINGS)).json()
    assert saved["has_bind_password"] is True
    assert "bind_password" not in saved
    async with app.state.db_sessionmaker() as db:
        row = await db.get(LdapSettings, 1)
        assert row.bind_password_encrypted and "service-pass" not in row.bind_password_encrypted
        assert app.state.ldap.secret_box.decrypt(row.bind_password_encrypted) == "service-pass"

    # Omitted password keeps the saved one.
    body = {k: v for k, v in SETTINGS.items() if k != "bind_password"} | {"port": 3269}
    assert (await admin_api.put("/api/v1/ldap/settings", json=body)).json()["has_bind_password"]

    status = (await admin_api.get("/api/v1/ldap/sync/status")).json()
    assert status["enabled"] is True and status["interval_seconds"] == 3600
    assert (await admin_api.get("/api/v1/system/info")).json()["ldap_enabled"] is True


async def test_settings_validation(admin_api) -> None:
    response = await admin_api.put("/api/v1/ldap/settings", json={**SETTINGS, "host": ""})
    assert response.json()["error"]["code"] == "validation_error"
    body = {k: v for k, v in SETTINGS.items() if k != "bind_password"}
    response = await admin_api.put("/api/v1/ldap/settings", json=body)
    assert response.json()["error"]["code"] == "ldap_bind_password_required"


async def test_connection_test_endpoint(admin_api, directory: FakeDirectory) -> None:
    directory.add_user("ivanov", groups={ADMINS_SID}, display_name="Ivan Ivanov")
    await admin_api.post(
        "/api/v1/ldap/group-mappings", json={"group_dn": ADMINS_DN, "role": "admin"}
    )

    body = {**SETTINGS, "enabled": False, "test_username": "EXAMPLE\\Ivanov"}
    result = (await admin_api.post("/api/v1/ldap/test", json=body)).json()
    assert result["ok"] is True and result["user_found"] is True
    assert result["user"]["roles"] == ["admin"]
    assert directory.configs[-1].bind_password == "service-pass"

    result = (await admin_api.post("/api/v1/ldap/test", json={**body, "test_username": "x"})).json()
    assert result == {
        "ok": True,
        "error_code": None,
        "message": None,
        "user_found": False,
        "user": None,
    }

    directory.error = LdapError("ldap_signing_required", "The server requires LDAP signing")
    result = (await admin_api.post("/api/v1/ldap/test", json=body)).json()
    assert (result["ok"], result["error_code"]) == (False, "ldap_signing_required")


async def test_group_mappings_crud(admin_api) -> None:
    created = await admin_api.post(
        "/api/v1/ldap/group-mappings", json={"group_dn": USERS_DN, "role": "admin"}
    )
    mapping = created.json()
    assert mapping["role"] == "admin"
    duplicate = await admin_api.post(
        "/api/v1/ldap/group-mappings", json={"group_dn": USERS_DN, "role": "admin"}
    )
    assert duplicate.json()["error"]["code"] == "group_mapping_exists"
    implicit = await admin_api.post(
        "/api/v1/ldap/group-mappings", json={"group_dn": USERS_DN, "role": "authenticated"}
    )
    assert implicit.json()["error"]["code"] == "role_not_assignable"
    assert len((await admin_api.get("/api/v1/ldap/group-mappings")).json()) == 1
    assert (
        await admin_api.delete(f"/api/v1/ldap/group-mappings/{mapping['id']}")
    ).status_code == 204


# --- sign-in ----------------------------------------------------------------------------


async def test_domain_sign_in_creates_user_with_roles(app: FastAPI, make_api, ldap_enabled) -> None:
    ldap_enabled.add_user("ivanov", groups={ADMINS_SID}, email="ivanov@example.test")
    ldap_enabled.add_user("petrov", groups={USERS_SID})

    me = (await make_api().login("EXAMPLE\\Ivanov", "domain-pass")).json()
    assert (me["username"], me["auth_source"], me["is_admin"]) == ("ivanov", "ldap", True)
    assert me["email"] == "ivanov@example.test" and me["must_change_password"] is False

    me = (await make_api().login("petrov@example.test", "domain-pass")).json()
    assert me["roles"] == [] and me["is_admin"] is False

    async with app.state.db_sessionmaker() as db:
        ivanov = await db.scalar(select(User).where(User.username == "ivanov"))
        assert ivanov.ldap_object_guid and ivanov.password_hash is None
        assert [(ur.role.name, ur.source) for ur in ivanov.roles] == [("admin", "ldap")]


async def test_domain_sign_in_failures(make_api, ldap_enabled) -> None:
    ldap_enabled.add_user("ivanov")
    client = make_api()
    for username, password in (("ivanov", "wrong"), ("ivanov", ""), ("nobody", "domain-pass")):
        response = await client.post(
            "/api/v1/auth/login", json={"username": username, "password": password or "x"}
        )
        assert response.json()["error"]["code"] == "invalid_credentials"

    ldap_enabled.error = LdapError("ldap_connection_failed", "Cannot connect")
    response = await client.post(
        "/api/v1/auth/login", json={"username": "ivanov", "password": "domain-pass"}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ldap_unavailable"


async def test_local_users_work_without_ldap_and_cannot_shadow_domain(
    admin_api, make_api, ldap_enabled
) -> None:
    ldap_enabled.add_user("ivanov")
    response = await admin_api.post(
        "/api/v1/users", json={"username": "ivanov", "password": "password123"}
    )
    assert response.json()["error"]["code"] == "username_exists_in_ldap"

    # Break-glass: local administrators sign in while AD is down.
    ldap_enabled.error = LdapError("ldap_connection_failed", "Cannot connect")
    assert (await make_api().login("root", "password123")).json()["is_admin"] is True


async def test_admin_blocked_domain_user_cannot_sign_in(admin_api, make_api, ldap_enabled) -> None:
    ldap_enabled.add_user("ivanov")
    me = (await make_api().login("ivanov", "domain-pass")).json()
    await admin_api.post(f"/api/v1/users/{me['id']}/block")
    response = await make_api().post(
        "/api/v1/auth/login", json={"username": "ivanov", "password": "domain-pass"}
    )
    assert response.json()["error"]["code"] == "user_blocked"


# --- synchronization ---------------------------------------------------------------------


async def test_sync_updates_blocks_and_unblocks(
    app: FastAPI, admin_api, make_api, ldap_enabled
) -> None:
    ivanov = ldap_enabled.add_user("ivanov", groups={ADMINS_SID})
    petrov = ldap_enabled.add_user("petrov")
    ivanov_client = make_api()
    await ivanov_client.login("ivanov", "domain-pass")
    await make_api().login("petrov", "domain-pass")

    ivanov.group_sids.discard(ADMINS_SID)
    ivanov.display_name = "Ivan Ivanov"
    petrov.disabled = True

    response = await admin_api.post("/api/v1/ldap/sync")
    assert response.status_code == 202
    again = await admin_api.post("/api/v1/ldap/sync")
    assert again.json()["error"]["code"] == "job_already_active"

    job = await run_sync(app)
    assert job["status"] == "succeeded", job
    assert job["result"] == {"checked": 2, "updated": 1, "blocked": 1, "unblocked": 0}

    users = {u["username"]: u for u in (await admin_api.get("/api/v1/users")).json()["items"]}
    assert users["ivanov"]["roles"] == [] and users["ivanov"]["display_name"] == "Ivan Ivanov"
    assert (users["petrov"]["is_active"], users["petrov"]["blocked_by"]) == (False, "ldap_sync")
    assert (await ivanov_client.get("/api/v1/me")).json()["is_admin"] is False

    petrov.disabled = False
    await admin_api.post("/api/v1/ldap/sync")
    job = await run_sync(app)
    assert job["result"]["unblocked"] == 1


async def test_sync_mass_block_protection(app: FastAPI, admin_api, make_api, ldap_enabled) -> None:
    for name in ("u1", "u2", "u3", "u4"):
        ldap_enabled.add_user(name)
        await make_api().login(name, "domain-pass")
    ldap_enabled.users.clear()  # e.g. a wrong base DN: nobody is found

    await admin_api.post("/api/v1/ldap/sync")
    job = await run_sync(app)
    assert job["status"] == "failed" and "Mass-block protection" in job["error"]
    users = (await admin_api.get("/api/v1/users", params={"q": "u"})).json()["items"]
    assert all(u["is_active"] for u in users)


async def test_sync_fails_without_changes_when_ldap_unavailable(
    app: FastAPI, admin_api, make_api, ldap_enabled
) -> None:
    ldap_enabled.add_user("ivanov")
    await make_api().login("ivanov", "domain-pass")
    ldap_enabled.error = LdapError("ldap_connection_failed", "Cannot connect")
    await admin_api.post("/api/v1/ldap/sync")
    job = await run_sync(app)
    assert job["status"] == "failed" and job["error"].startswith("ldap_connection_failed")


async def test_sync_requires_enabled_ldap(admin_api) -> None:
    response = await admin_api.post("/api/v1/ldap/sync")
    assert response.json()["error"]["code"] == "ldap_disabled"
