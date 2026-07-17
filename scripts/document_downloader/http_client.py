from __future__ import annotations

import logging
import random
import time
from typing import Any

import requests
from requests.adapters import HTTPAdapter

LOGGER = logging.getLogger(__name__)


class ResilientHttpClient:
    def __init__(
        self,
        *,
        timeout: float = 300.0,
        retries: int = 10,
        delay: float = 1.5,
        verify_tls: bool = True,
        user_agent: str = "ResearchHub-Ethiopia-Document-Downloader/1.1",
    ) -> None:
        self.connect_timeout = 30.0
        self.read_timeout = timeout
        self.retries = retries
        self.delay = delay
        self.verify_tls = verify_tls

        self.session = requests.Session()

        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "*/*",
                "Connection": "keep-alive",
            }
        )

        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=0,
        )

        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def request(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        last_error: Exception | None = None

        request_timeout = kwargs.pop(
            "timeout",
            (
                self.connect_timeout,
                self.read_timeout,
            ),
        )

        allow_redirects = kwargs.pop(
            "allow_redirects",
            True,
        )

        for attempt in range(1, self.retries + 1):
            try:
                response = self.session.request(
                    method,
                    url,
                    timeout=request_timeout,
                    verify=self.verify_tls,
                    allow_redirects=allow_redirects,
                    **kwargs,
                )

                if response.status_code in {
                    408,
                    425,
                    429,
                    500,
                    502,
                    503,
                    504,
                }:
                    retry_after = response.headers.get("Retry-After")

                    if retry_after and retry_after.isdigit():
                        wait = float(retry_after)
                    else:
                        wait = min(
                            2 ** (attempt - 1),
                            60,
                        )

                    wait += random.uniform(0, 1)

                    LOGGER.warning(
                        "HTTP %s for %s; retrying in %.1fs",
                        response.status_code,
                        url,
                        wait,
                    )

                    response.close()
                    time.sleep(wait)
                    continue

                response.raise_for_status()

                if self.delay:
                    time.sleep(self.delay)

                return response

            except requests.RequestException as exc:
                last_error = exc

                if attempt >= self.retries:
                    break

                wait = min(
                    2 ** (attempt - 1),
                    60,
                ) + random.uniform(0, 1)

                LOGGER.warning(
                    "Request failed for %s (attempt %s/%s): %s; retrying in %.1fs",
                    url,
                    attempt,
                    self.retries,
                    exc,
                    wait,
                )

                time.sleep(wait)

        raise RuntimeError(f"Request failed after {self.retries} attempts: {url}: {last_error}")

    def get_json(
        self,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        headers = kwargs.pop(
            "headers",
            {"Accept": ("application/hal+json,application/json")},
        )

        response = self.request(
            "GET",
            url,
            headers=headers,
            **kwargs,
        )

        try:
            data = response.json()
        finally:
            response.close()

        if not isinstance(data, dict):
            raise RuntimeError(f"Expected JSON object from {url}")

        return data

    def get_json_value(
        self,
        url: str,
        **kwargs: Any,
    ) -> Any:
        headers = kwargs.pop(
            "headers",
            {"Accept": ("application/hal+json,application/json")},
        )

        response = self.request(
            "GET",
            url,
            headers=headers,
            **kwargs,
        )

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(f"Invalid JSON response from {url}") from exc
        finally:
            response.close()

    def stream(
        self,
        url: str,
        **kwargs: Any,
    ) -> requests.Response:
        return self.request(
            "GET",
            url,
            stream=True,
            **kwargs,
        )

    def close(self) -> None:
        self.session.close()
