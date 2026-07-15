"""Safe mixed ResearchHub workload; no harvest or import mutations."""

from __future__ import annotations

import random

from config import ENABLE_AI, REQUEST_TIMEOUT, SEARCH_QUERIES, TEST_PASSWORD, TEST_USERNAME
from locust import HttpUser, between, task


class ResearchHubUser(HttpUser):
    wait_time = between(1, 5)
    access_token: str | None = None
    refresh_token: str | None = None
    publication_ids: list[str]

    def on_start(self) -> None:
        self.publication_ids = []
        if TEST_USERNAME and TEST_PASSWORD:
            with self.client.post(
                "/api/auth/login",
                data={"username": TEST_USERNAME, "password": TEST_PASSWORD},
                timeout=REQUEST_TIMEOUT,
                name="POST /api/auth/login",
                catch_response=True,
            ) as response:
                if response.ok:
                    payload = response.json()
                    self.access_token = payload["access_token"]
                    self.refresh_token = payload["refresh_token"]
                else:
                    response.failure(f"login failed: {response.status_code}")

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"} if self.access_token else {}

    @task(35)
    def browse_publications(self) -> None:
        with self.client.get(
            "/api/publications?limit=20",
            timeout=REQUEST_TIMEOUT,
            name="GET /api/publications",
            catch_response=True,
        ) as response:
            if response.ok:
                data = response.json()
                items = data if isinstance(data, list) else data.get("items", [])
                self.publication_ids = [str(item["id"]) for item in items[:20] if item.get("id")]

    @task(25)
    def standard_search(self) -> None:
        self.client.get(
            "/api/search/publications",
            params={"q": random.choice(SEARCH_QUERIES), "limit": 20},
            timeout=REQUEST_TIMEOUT,
            name="GET /api/search/publications",
        )

    @task(15)
    def publication_detail(self) -> None:
        if self.publication_ids:
            self.client.get(
                f"/api/publications/{random.choice(self.publication_ids)}",
                timeout=REQUEST_TIMEOUT,
                name="GET /api/publications/:id",
            )

    @task(10)
    def semantic_search(self) -> None:
        self.client.get(
            "/api/search/semantic",
            params={"q": random.choice(SEARCH_QUERIES), "limit": 10},
            timeout=REQUEST_TIMEOUT,
            name="GET /api/search/semantic",
        )

    @task(5)
    def dashboard(self) -> None:
        self.client.get("/api/dashboard/summary", timeout=REQUEST_TIMEOUT)

    @task(5)
    def directories(self) -> None:
        endpoint = random.choice(["/api/universities?limit=50", "/api/repositories?limit=50"])
        self.client.get(endpoint, timeout=REQUEST_TIMEOUT, name="GET directory")

    @task(3)
    def chatbot(self) -> None:
        if ENABLE_AI and self.access_token:
            self.client.get(
                "/api/ai/chat/sessions",
                headers=self.headers,
                timeout=REQUEST_TIMEOUT,
                name="GET /api/ai/chat/sessions",
            )

    @task(2)
    def monitoring(self) -> None:
        self.client.get(
            "/api/sources?limit=20",
            headers=self.headers,
            timeout=REQUEST_TIMEOUT,
            name="GET /api/sources",
        )

    def on_stop(self) -> None:
        if self.refresh_token:
            self.client.post(
                "/api/auth/logout",
                json={"refresh_token": self.refresh_token},
                timeout=REQUEST_TIMEOUT,
                name="POST /api/auth/logout",
            )
