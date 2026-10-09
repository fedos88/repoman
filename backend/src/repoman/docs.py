"""Swagger UI served from local assets, so /api/docs works without internet access.

The assets are downloaded into SWAGGER_UI_DIR when the Docker image is built
(see scripts/fetch_swagger_ui.py). Without them (e.g. running from a source tree)
FastAPI's default CDN assets are used.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

SWAGGER_UI_DIR = Path(__file__).resolve().parent / "static" / "swagger-ui"
DOCS_URL = "/api/docs"
STATIC_URL = f"{DOCS_URL}/static"


def install_docs(app: FastAPI, swagger_ui_dir: Path = SWAGGER_UI_DIR) -> None:
    local = (swagger_ui_dir / "swagger-ui-bundle.js").is_file()
    assets: dict[str, str] = {}
    if local:
        app.mount(STATIC_URL, StaticFiles(directory=swagger_ui_dir), name="swagger-ui")
        assets = {
            "swagger_js_url": f"{STATIC_URL}/swagger-ui-bundle.js",
            "swagger_css_url": f"{STATIC_URL}/swagger-ui.css",
            "swagger_favicon_url": f"{STATIC_URL}/favicon-32x32.png",
        }

    @app.get(DOCS_URL, include_in_schema=False)
    async def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(
            openapi_url=app.openapi_url or "/api/openapi.json",
            title=f"{app.title} API",
            **assets,
        )
