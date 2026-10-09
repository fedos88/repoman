"""Download Swagger UI assets (swagger-ui-dist from npm) for serving without a CDN.

Usage: python fetch_swagger_ui.py VERSION SHA512_INTEGRITY DEST_DIR

The tarball checksum is verified against the npm `dist.integrity` value.
"""

import base64
import hashlib
import io
import sys
import tarfile
import urllib.request
from pathlib import Path

FILES = ("swagger-ui-bundle.js", "swagger-ui.css", "favicon-32x32.png")


def main(version: str, integrity: str, dest: Path) -> None:
    url = f"https://registry.npmjs.org/swagger-ui-dist/-/swagger-ui-dist-{version}.tgz"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read()

    algorithm, _, expected = integrity.partition("-")
    if algorithm != "sha512":
        raise SystemExit(f"Unsupported integrity algorithm: {algorithm}")
    actual = base64.b64encode(hashlib.sha512(data).digest()).decode()
    if actual != expected:
        raise SystemExit(f"Checksum mismatch for {url}")

    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for name in FILES:
            member = archive.extractfile(f"package/{name}")
            if member is None:
                raise SystemExit(f"{name} not found in {url}")
            (dest / name).write_bytes(member.read())
    print(f"Swagger UI {version} -> {dest}")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(sys.argv[1], sys.argv[2], Path(sys.argv[3]))
