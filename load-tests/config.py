"""Environment-driven, non-destructive load-test configuration."""

import os

SEARCH_QUERIES = ["Ethiopia", "agriculture", "public health", "education", "climate"]
TEST_USERNAME = os.getenv("LOAD_TEST_USERNAME")
TEST_PASSWORD = os.getenv("LOAD_TEST_PASSWORD")
ENABLE_AI = os.getenv("LOAD_TEST_ENABLE_AI", "false").casefold() == "true"
REQUEST_TIMEOUT = float(os.getenv("LOAD_TEST_REQUEST_TIMEOUT", "15"))
