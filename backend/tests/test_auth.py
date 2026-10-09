import base64

from fastapi import FastAPI
from sqlalchemy import func, select

from repoman.auth.policy import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE
from repoman.config import Settings
from repoman.db.models import AuthSession, User
from repoman.users.bootstrap import ensure_admin


async def test_login_sets_cookies_and_me(api, create_user) -> None:
    await create_user("alice", roles=("admin",))
    response = await api.login("  ALICE ", "password123")
    assert response.json()["username"] == "alice"
    assert response.json()["is_admin"] is True
    assert SESSION_COOKIE in api.cookies and CSRF_COOKIE in api.cookies
    set_cookie = ";".join(response.headers.get_list("set-cookie"))
    assert "HttpOnly" in set_cookie and "SameSite=lax" in set_cookie

    me = await api.get("/api/v1/me")
    assert me.status_code == 200
    assert me.json()["roles"] == ["admin"]


async def test_login_wrong_password_and_unknown_user(api, create_user) -> None:
    await create_user("alice")
    for username, password in (("alice", "wrong-password"), ("nobody", "password123")):
        response = await api.post(
            "/api/v1/auth/login", json={"username": username, "password": password}
        )
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"


async def test_login_rate_limited(api, create_user) -> None:
    await create_user("alice")
    for _ in range(5):
        await api.post("/api/v1/auth/login", json={"username": "alice", "password": "bad-pass"})
    response = await api.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "password123"}
    )
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "too_many_attempts"


async def test_blocked_user_cannot_login(api, create_user) -> None:
    await create_user("alice", is_active=False)
    response = await api.post(
        "/api/v1/auth/login", json={"username": "alice", "password": "password123"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "user_blocked"


async def test_anonymous_me_is_401(api) -> None:
    response = await api.get("/api/v1/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


async def test_csrf_required_for_unsafe_session_requests(api, create_user) -> None:
    await create_user("alice")
    await api.login("alice", "password123")
    response = await api.post(
        "/api/v1/me/tokens", json={"name": "ci"}, headers={CSRF_HEADER: "wrong"}
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf_failed"
    assert (await api.post("/api/v1/me/tokens", json={"name": "ci"})).status_code == 201


async def test_logout_deletes_session(app: FastAPI, api, create_user) -> None:
    await create_user("alice")
    await api.login("alice", "password123")
    assert (await api.post("/api/v1/auth/logout")).status_code == 204
    assert (await api.get("/api/v1/me")).status_code == 401
    async with app.state.db_sessionmaker() as db:
        assert await db.scalar(select(func.count()).select_from(AuthSession)) == 0


async def test_api_token_bearer_and_basic(make_api, create_user) -> None:
    await create_user("alice")
    ui = make_api()
    await ui.login("alice", "password123")
    created = (await ui.post("/api/v1/me/tokens", json={"name": "ci"})).json()
    token = created["token"]
    assert token.startswith("rpm_") and created["prefix"] == token[:12]
    assert created["expires_at"] is not None

    bearer = make_api()
    response = await bearer.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.json()["username"] == "alice"

    basic = base64.b64encode(f"alice:{token}".encode()).decode()
    response = await bearer.get("/api/v1/me", headers={"Authorization": f"Basic {basic}"})
    assert response.status_code == 200

    # Token requests need no CSRF header.
    response = await bearer.post(
        "/api/v1/me/tokens", json={"name": "x"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 201


async def test_basic_with_password_or_wrong_user_rejected(make_api, create_user) -> None:
    await create_user("alice")
    await create_user("bob")
    ui = make_api()
    await ui.login("alice", "password123")
    token = (await ui.post("/api/v1/me/tokens", json={"name": "ci"})).json()["token"]

    client = make_api()
    for credentials in ("alice:password123", f"bob:{token}"):
        basic = base64.b64encode(credentials.encode()).decode()
        response = await client.get("/api/v1/me", headers={"Authorization": f"Basic {basic}"})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_token"


async def test_token_without_expiry_and_revocation(make_api, create_user) -> None:
    await create_user("alice")
    ui = make_api()
    await ui.login("alice", "password123")
    created = (
        await ui.post("/api/v1/me/tokens", json={"name": "forever", "expires_in_days": None})
    ).json()
    assert created["expires_at"] is None

    tokens = (await ui.get("/api/v1/me/tokens")).json()
    assert [t["name"] for t in tokens] == ["forever"]
    assert "token" not in tokens[0]

    assert (await ui.delete(f"/api/v1/me/tokens/{created['id']}")).status_code == 204
    other = make_api()
    response = await other.get(
        "/api/v1/me", headers={"Authorization": f"Bearer {created['token']}"}
    )
    assert response.status_code == 401


async def test_must_change_password_flow(api, create_user) -> None:
    await create_user("alice", must_change_password=True)
    me = (await api.login("alice", "password123")).json()
    assert me["must_change_password"] is True

    response = await api.get("/api/v1/me/tokens")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "password_change_required"

    response = await api.put(
        "/api/v1/me/password",
        json={"current_password": "wrong", "new_password": "new-password"},
    )
    assert response.json()["error"]["code"] == "invalid_current_password"

    response = await api.put(
        "/api/v1/me/password",
        json={"current_password": "password123", "new_password": "short"},
    )
    assert response.status_code == 422

    response = await api.put(
        "/api/v1/me/password",
        json={"current_password": "password123", "new_password": "new-password"},
    )
    assert response.status_code == 204
    # The current session stays valid.
    assert (await api.get("/api/v1/me/tokens")).status_code == 200


async def test_password_change_signs_out_other_sessions(make_api, create_user) -> None:
    await create_user("alice")
    first, second = make_api(), make_api()
    await first.login("alice", "password123")
    await second.login("alice", "password123")
    await first.put(
        "/api/v1/me/password",
        json={"current_password": "password123", "new_password": "new-password"},
    )
    assert (await first.get("/api/v1/me")).status_code == 200
    assert (await second.get("/api/v1/me")).status_code == 401


async def test_bootstrap_creates_admin_once(app: FastAPI, caplog) -> None:
    settings = app.state.settings
    await ensure_admin(app.state.db_sessionmaker, settings)
    async with app.state.db_sessionmaker() as db:
        admin = await db.scalar(select(User).where(User.username == "admin"))
        assert admin is not None
        assert admin.role_names == ["admin"]
        assert admin.must_change_password is True
    assert "generated password" in caplog.text

    caplog.clear()
    await ensure_admin(app.state.db_sessionmaker, settings)
    assert "generated password" not in caplog.text


async def test_bootstrap_with_configured_password(app: FastAPI, api) -> None:
    current = app.state.settings
    settings = Settings(
        database_url=current.database_url,
        storage_path=current.storage_path,
        secret_key=current.secret_key,
        admin_user="Root",
        admin_password="configured-pass",
    )
    await ensure_admin(app.state.db_sessionmaker, settings)
    me = (await api.login("root", "configured-pass")).json()
    assert me["is_admin"] is True and me["must_change_password"] is False
