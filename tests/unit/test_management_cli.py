"""Tests for management CLI commands."""

from __future__ import annotations

import json

import pytest

from app import management
from app.cache import CacheType


class FakeCacheManager:
    def __init__(self, cleared: int = 0, stats: dict[str, object] | None = None) -> None:
        self.clear_calls: list[CacheType | None] = []
        self.get_stats_calls = 0
        self._cleared = cleared
        self._stats = stats or {"hits": 0, "misses": 0, "errors": 0}

    def clear(self, cache_type: CacheType | None) -> int:
        self.clear_calls.append(cache_type)
        return self._cleared

    def get_stats(self) -> dict[str, object]:
        self.get_stats_calls += 1
        return self._stats


def test_cache_clear_without_type(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    manager = FakeCacheManager(cleared=3)
    monkeypatch.setattr(management, "get_cache_manager", lambda: manager)

    exit_code = management.run(["cache:clear"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload == {
        "status": "success",
        "files_cleared": 3,
        "target": "all",
    }
    assert manager.clear_calls == [None]


def test_cache_clear_with_type(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    manager = FakeCacheManager(cleared=1)
    monkeypatch.setattr(management, "get_cache_manager", lambda: manager)

    exit_code = management.run(["cache:clear", "--type", CacheType.METADATA.value])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload == {
        "status": "success",
        "files_cleared": 1,
        "target": CacheType.METADATA.value,
    }
    assert manager.clear_calls == [CacheType.METADATA]


def test_cache_clear_with_invalid_type(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    manager = FakeCacheManager()
    monkeypatch.setattr(management, "get_cache_manager", lambda: manager)

    exit_code = management.run(["cache:clear", "--type", "invalid"],)

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert "Invalid cache type: invalid." in captured.err
    assert manager.clear_calls == []


def test_cache_stats(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    stats = {"enabled": True, "hits": 1, "misses": 2, "errors": 0, "files": 0}
    manager = FakeCacheManager(stats=stats)
    monkeypatch.setattr(management, "get_cache_manager", lambda: manager)

    exit_code = management.run(["cache:stats"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert captured.err == ""
    assert payload == stats
    assert manager.get_stats_calls == 1
