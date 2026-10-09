import httpx

from repoman import __version__


async def test_root(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"name": "RepoMan", "version": __version__, "docs": "/api/docs"}


async def test_healthz(client: httpx.AsyncClient) -> None:
    response = await client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_reports_failed_database(client: httpx.AsyncClient) -> None:
    response = await client.get("/readyz")
    assert response.status_code == 503
    assert response.json() == {"status": "fail", "checks": {"database": "fail", "storage": "ok"}}


async def test_not_found_uses_error_format(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Not Found"}}


async def test_openapi_and_swagger(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/api/openapi.json")).json()
    assert "/api/v1/system/info" in schema["paths"]
    assert (await client.get("/api/docs")).status_code == 200
