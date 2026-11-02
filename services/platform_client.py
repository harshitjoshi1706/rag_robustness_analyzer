"""HTTP-only distributed UI adapter; no Redis/Celery or research imports."""

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class PlatformClient:
    def __init__(self, base_url=None):
        self.base_url = (base_url or os.getenv("RAG_API_URL", "http://localhost:8000")).rstrip("/")

    def call(self, path, body=None, key=None):
        headers = {"Content-Type": "application/json"}
        if key:
            headers["Idempotency-Key"] = key
        request = Request(
            self.base_url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method="POST" if body is not None else "GET",
        )
        try:
            with urlopen(request, timeout=10) as response:
                return json.load(response)
        except HTTPError as exc:
            try:
                detail = json.load(exc).get("detail", str(exc))
            except (ValueError, OSError):
                detail = str(exc)
            raise RuntimeError(f"API {exc.code}: {detail}") from exc
