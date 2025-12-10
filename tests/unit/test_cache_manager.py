import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from app.cache import CacheManager, CacheType


class DummySettings:
    def __init__(
        self,
        *,
        cache_enabled: bool,
        base_dir: Path,
        metadata_ttl: int = 60,
        text_ttl: int = 60,
        search_ttl: int = 60,
    ) -> None:
        self.cache_enabled = cache_enabled
        self.courtlistener_cache_dir = base_dir
        self.courtlistener_ttl_metadata = metadata_ttl
        self.courtlistener_ttl_text = text_ttl
        self.courtlistener_ttl_search = search_ttl


@pytest.fixture
def settings_factory(tmp_path: Path):
    def _factory(**overrides: Any) -> DummySettings:
        return DummySettings(
            cache_enabled=overrides.get("cache_enabled", True),
            base_dir=overrides.get("base_dir", tmp_path / "cache"),
            metadata_ttl=overrides.get("metadata_ttl", 60),
            text_ttl=overrides.get("text_ttl", 60),
            search_ttl=overrides.get("search_ttl", 60),
        )

    return _factory


def test_ttl_expired_entry_removed(monkeypatch: pytest.MonkeyPatch, settings_factory) -> None:
    settings = settings_factory(text_ttl=1)
    monkeypatch.setattr("app.cache.get_settings", lambda: settings)
    manager = CacheManager()

    key = "expired-key"
    key_hash = manager._build_key(key)
    path = manager._get_path(CacheType.TEXT, key_hash)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("stale content", encoding="utf-8")

    old_time = time.time() - 10
    os.utime(path, (old_time, old_time))

    assert manager.get(CacheType.TEXT, key) is None
    assert manager.stats["misses"] == 1
    assert not path.exists()


def test_get_set_text_and_json(monkeypatch: pytest.MonkeyPatch, settings_factory) -> None:
    settings = settings_factory()
    monkeypatch.setattr("app.cache.get_settings", lambda: settings)
    manager = CacheManager()

    text_key = "text-key"
    metadata_key = {"case": "roe"}

    assert manager.get(CacheType.TEXT, text_key) is None

    manager.set(CacheType.TEXT, text_key, "cached text")
    manager.set(CacheType.METADATA, metadata_key, {"foo": "bar"})

    assert manager.get(CacheType.TEXT, text_key) == "cached text"
    assert manager.get(CacheType.METADATA, metadata_key) == {"foo": "bar"}

    text_path = manager._get_path(CacheType.TEXT, manager._build_key(text_key))
    metadata_path = manager._get_path(CacheType.METADATA, manager._build_key(metadata_key))

    assert text_path.read_text(encoding="utf-8") == "cached text"
    assert json.loads(metadata_path.read_text(encoding="utf-8")) == {"foo": "bar"}

    assert manager.stats["hits"] == 2
    assert manager.stats["misses"] == 1
    assert manager.stats["errors"] == 0


def test_invalid_json_increments_errors(monkeypatch: pytest.MonkeyPatch, settings_factory) -> None:
    settings = settings_factory()
    monkeypatch.setattr("app.cache.get_settings", lambda: settings)
    manager = CacheManager()

    key_params = {"id": 1}
    path = manager._get_path(CacheType.METADATA, manager._build_key(key_params))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{invalid-json}", encoding="utf-8")

    assert manager.get(CacheType.METADATA, key_params) is None
    assert manager.stats["errors"] == 1
    assert manager.stats["hits"] == 0
    assert manager.stats["misses"] == 0


def test_clear_and_stats_enabled(monkeypatch: pytest.MonkeyPatch, settings_factory) -> None:
    settings = settings_factory()
    monkeypatch.setattr("app.cache.get_settings", lambda: settings)
    manager = CacheManager()

    manager.get(CacheType.TEXT, "missing")
    manager.set(CacheType.TEXT, "kept", "value")
    manager.set(CacheType.METADATA, {"id": 2}, {"data": True})
    manager.get(CacheType.TEXT, "kept")
    manager.get(CacheType.METADATA, {"id": 2})

    stats = manager.get_stats()
    assert stats["enabled"] is True
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["errors"] == 0
    assert stats["files"] == 2
    assert stats["size_bytes"] > 0

    removed = manager.clear()
    assert removed == 2
    cleared_stats = manager.get_stats()
    assert cleared_stats["files"] == 0
    assert cleared_stats["size_bytes"] == 0


def test_clear_and_stats_disabled(monkeypatch: pytest.MonkeyPatch, settings_factory) -> None:
    settings = settings_factory(cache_enabled=False)
    monkeypatch.setattr("app.cache.get_settings", lambda: settings)
    manager = CacheManager()

    manager.set(CacheType.TEXT, "ignored", "value")
    assert manager.get(CacheType.TEXT, "ignored") is None

    stats = manager.get_stats()
    assert stats["enabled"] is False
    assert stats["hits"] == 0
    assert stats["misses"] == 0
    assert stats["errors"] == 0
    assert stats["files"] == 0
    assert stats["size_bytes"] == 0

    assert manager.clear() == 0
