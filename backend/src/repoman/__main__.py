"""Entry point: apply database migrations, then start the HTTP server."""

import logging

import uvicorn

from repoman.config import get_settings
from repoman.db.migrate import upgrade_to_head
from repoman.main import create_app


def main() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    logging.getLogger(__name__).info("Applying database migrations")
    upgrade_to_head(settings.database_url)

    uvicorn.run(
        create_app(settings),
        host=settings.listen_host,
        port=settings.listen_port,
        log_level=settings.log_level.lower(),
        proxy_headers=True,
        forwarded_allow_ips=settings.trusted_proxies or None,
        server_header=False,
    )


if __name__ == "__main__":
    main()
