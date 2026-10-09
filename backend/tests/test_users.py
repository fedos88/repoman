import pytest


@pytest.fixture
async def admin(api, create_user):
    user = await create_user("root", roles=("admin",))
    await api.login("root", "password123")
    return user


async def test_non_admin_forbidden(api, create_user) -> None:
    await create_user("alice")
    await api.login("alice", "password123")
    response = await api.get("/api/v1/users")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


async def test_create_list_and_search(api, admin) -> None:
    response = await api.post(
        "/api/v1/users",
        json={
            "username": " Alice ",
            "password": "password123",
            "display_name": "Alice Liddell",
            "email": "alice@example.com",
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()
    assert created["username"] == "alice"
    assert created["auth_source"] == "local"
    assert created["must_change_password"] is True
    assert created["roles"] == []

    duplicate = await api.post("/api/v1/users", json={"username": "alice", "password": "12345678"})
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "username_taken"

    page = (await api.get("/api/v1/users")).json()
    assert page["total"] == 2
    assert [u["username"] for u in page["items"]] == ["alice", "root"]
    found = (await api.get("/api/v1/users", params={"q": "liddell"})).json()
    assert [u["username"] for u in found["items"]] == ["alice"]
    # LIKE wildcards are matched literally.
    assert (await api.get("/api/v1/users", params={"q": "%"})).json()["total"] == 0


async def test_create_validation(api, admin) -> None:
    for body in (
        {"username": "bad name", "password": "password123"},
        {"username": "bob", "password": "short"},
        {"username": "bob", "password": "password123", "email": "not-an-email"},
    ):
        response = await api.post("/api/v1/users", json=body)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


async def test_new_user_must_change_password(api, make_api, admin) -> None:
    await api.post("/api/v1/users", json={"username": "bob", "password": "password123"})
    bob = make_api()
    assert (await bob.login("bob", "password123")).json()["must_change_password"] is True


async def test_update_profile(api, admin, create_user) -> None:
    user = await create_user("alice")
    await api.patch(f"/api/v1/users/{user.id}", json={"first_name": "Alice", "email": None})
    response = await api.patch(f"/api/v1/users/{user.id}", json={"last_name": "Liddell"})
    body = response.json()
    assert (body["first_name"], body["last_name"]) == ("Alice", "Liddell")


async def test_roles_assignment(api, admin, create_user) -> None:
    user = await create_user("alice")
    response = await api.put(f"/api/v1/users/{user.id}/roles", json={"roles": ["admin"]})
    assert response.json()["roles"] == ["admin"]

    response = await api.put(f"/api/v1/users/{user.id}/roles", json={"roles": ["anonymous"]})
    assert response.json()["error"]["code"] == "role_not_assignable"
    response = await api.put(f"/api/v1/users/{user.id}/roles", json={"roles": ["nope"]})
    assert response.json()["error"]["code"] == "role_not_found"

    response = await api.put(f"/api/v1/users/{user.id}/roles", json={"roles": []})
    assert response.json()["roles"] == []

    roles = (await api.get("/api/v1/roles")).json()
    assert {r["name"]: r["assignable"] for r in roles} == {
        "admin": True,
        "anonymous": False,
        "authenticated": False,
    }


async def test_last_admin_protected(api, admin) -> None:
    response = await api.put(f"/api/v1/users/{admin.id}/roles", json={"roles": []})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "last_admin"


async def test_cannot_delete_or_block_self(api, admin) -> None:
    response = await api.delete(f"/api/v1/users/{admin.id}")
    assert response.json()["error"]["code"] == "cannot_delete_self"
    response = await api.post(f"/api/v1/users/{admin.id}/block")
    assert response.json()["error"]["code"] == "cannot_block_self"


async def test_block_and_unblock(api, make_api, admin, create_user) -> None:
    user = await create_user("alice")
    alice = make_api()
    await alice.login("alice", "password123")
    token = (await alice.post("/api/v1/me/tokens", json={"name": "ci"})).json()["token"]

    body = (await api.post(f"/api/v1/users/{user.id}/block")).json()
    assert (body["is_active"], body["blocked_by"]) == (False, "admin")
    # Sessions and tokens stop working.
    assert (await alice.get("/api/v1/me")).status_code == 401
    other = make_api()
    response = await other.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401

    body = (await api.post(f"/api/v1/users/{user.id}/unblock")).json()
    assert (body["is_active"], body["blocked_by"]) == (True, None)
    response = await other.get("/api/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200


async def test_reset_password(api, make_api, admin, create_user) -> None:
    user = await create_user("alice")
    alice = make_api()
    await alice.login("alice", "password123")
    response = await api.put(f"/api/v1/users/{user.id}/password", json={"password": "new-pass-1"})
    assert response.status_code == 204
    assert (await alice.get("/api/v1/me")).status_code == 401
    me = (await make_api().login("alice", "new-pass-1")).json()
    assert me["must_change_password"] is True


async def test_delete_local_user(api, admin, create_user) -> None:
    user = await create_user("alice")
    assert (await api.delete(f"/api/v1/users/{user.id}")).status_code == 204
    response = await api.get(f"/api/v1/users/{user.id}")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "user_not_found"


async def test_ldap_user_restrictions(api, admin, create_user) -> None:
    user = await create_user("ivanov", auth_source="ldap")
    response = await api.delete(f"/api/v1/users/{user.id}")
    assert response.json()["error"]["code"] == "ldap_user_cannot_be_deleted"
    response = await api.patch(f"/api/v1/users/{user.id}", json={"first_name": "x"})
    assert response.json()["error"]["code"] == "ldap_user_readonly"
    response = await api.put(f"/api/v1/users/{user.id}/password", json={"password": "password123"})
    assert response.json()["error"]["code"] == "ldap_user_password"
    # Blocking is allowed.
    assert (await api.post(f"/api/v1/users/{user.id}/block")).status_code == 200


async def test_admin_manages_user_tokens(api, make_api, admin, create_user) -> None:
    user = await create_user("alice")
    alice = make_api()
    await alice.login("alice", "password123")
    created = (await alice.post("/api/v1/me/tokens", json={"name": "ci"})).json()

    tokens = (await api.get(f"/api/v1/users/{user.id}/tokens")).json()
    assert [t["id"] for t in tokens] == [created["id"]]
    response = await api.delete(f"/api/v1/users/{user.id}/tokens/{created['id']}")
    assert response.status_code == 204
    assert (await api.get(f"/api/v1/users/{user.id}/tokens")).json() == []
