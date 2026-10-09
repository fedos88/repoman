from pathlib import Path

import httpx
from fastapi import FastAPI

from repoman.docs import install_docs


async def _get(app: FastAPI, url: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get(url)


async def test_swagger_ui_uses_local_assets(tmp_path: Path) -> None:
    for name in ("swagger-ui-bundle.js", "swagger-ui.css", "favicon-32x32.png"):
        (tmp_path / name).write_text(name)
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    install_docs(app, tmp_path)

    html = (await _get(app, "/api/docs")).text
    assert "/api/docs/static/swagger-ui-bundle.js" in html
    assert "cdn.jsdelivr.net" not in html
    asset = await _get(app, "/api/docs/static/swagger-ui.css")
    assert asset.status_code == 200
    assert asset.text == "swagger-ui.css"


async def test_swagger_ui_falls_back_to_cdn(tmp_path: Path) -> None:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    install_docs(app, tmp_path)

    html = (await _get(app, "/api/docs")).text
    assert "cdn.jsdelivr.net" in html
