from __future__ import annotations

from question_api.core.langgraph_redis_settings import sanitize_redis_url_for_log


def test_sanitize_redis_url_for_log_strips_credentials() -> None:
    assert sanitize_redis_url_for_log("redis://:secret@10.0.1.5:6380/2") == "10.0.1.5:6380/2"


def test_sanitize_redis_url_for_log_default_port_redis() -> None:
    assert sanitize_redis_url_for_log("redis://localhost") == "localhost:6379"


def test_sanitize_redis_url_for_log_default_port_rediss() -> None:
    assert sanitize_redis_url_for_log("rediss://cache.example.internal") == "cache.example.internal:6379"
