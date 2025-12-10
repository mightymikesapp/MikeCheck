"""Unit tests for cache management tools."""

import pytest
from unittest.mock import MagicMock, patch

from app.cache import CacheManager, CacheType
from app.tools.cache_tools import cache_clear_impl, cache_stats_impl


@pytest.fixture
def mock_cache_manager():
    """Create a mock cache manager for testing."""
    manager = MagicMock(spec=CacheManager)
    manager.get_stats.return_value = {
        "hits": 150,
        "misses": 50,
        "errors": 2,
        "hit_rate": 0.75,
        "total_files": 25,
        "total_size_bytes": 1024000,
    }
    manager.clear.return_value = 10
    return manager


@pytest.mark.unit
def test_cache_stats_returns_valid_structure(mock_cache_manager):
    """Test that cache_stats returns a valid statistics dictionary."""
    with patch("app.tools.cache_tools.get_cache_manager", return_value=mock_cache_manager):
        result = cache_stats_impl()

        # Verify structure
        assert isinstance(result, dict)
        assert "hits" in result
        assert "misses" in result
        assert "errors" in result
        assert "hit_rate" in result
        assert "total_files" in result
        assert "total_size_bytes" in result

        # Verify values
        assert result["hits"] == 150
        assert result["misses"] == 50
        assert result["errors"] == 2
        assert result["hit_rate"] == 0.75
        assert result["total_files"] == 25
        assert result["total_size_bytes"] == 1024000

        # Verify cache manager was called
        mock_cache_manager.get_stats.assert_called_once()


@pytest.mark.unit
def test_cache_clear_all_caches(mock_cache_manager):
    """Test clearing all cache types."""
    with patch("app.tools.cache_tools.get_cache_manager", return_value=mock_cache_manager):
        result = cache_clear_impl()

        # Verify return structure
        assert result["status"] == "success"
        assert "message" in result
        assert result["files_cleared"] == 10
        assert "all" in result["message"]

        # Verify cache manager was called with None (all caches)
        mock_cache_manager.clear.assert_called_once_with(None)


@pytest.mark.unit
@pytest.mark.parametrize(
    "cache_type_str, cache_type_enum",
    [
        ("metadata", CacheType.METADATA),
        ("text", CacheType.TEXT),
        ("search", CacheType.SEARCH),
    ],
)
def test_cache_clear_specific_types(mock_cache_manager, cache_type_str, cache_type_enum):
    """Test clearing specific cache types."""
    with patch("app.tools.cache_tools.get_cache_manager", return_value=mock_cache_manager):
        result = cache_clear_impl(type=cache_type_str)

        assert result["status"] == "success"
        assert cache_type_str in result["message"]
        assert result["files_cleared"] == 10
        mock_cache_manager.clear.assert_called_once_with(cache_type_enum)

@pytest.mark.unit
def test_cache_clear_invalid_type_returns_error(mock_cache_manager):
    """Test that invalid cache type returns an error."""
    with patch("app.tools.cache_tools.get_cache_manager", return_value=mock_cache_manager):
        result = cache_clear_impl(type="invalid_type")

        # Verify error structure
        assert "error" in result
        assert "invalid_type" in result["error"].lower()
        assert "valid types" in result["error"].lower()

        # Verify cache manager was NOT called
        mock_cache_manager.clear.assert_not_called()


@pytest.mark.unit
@pytest.mark.parametrize(
    "type_input, expected_enum",
    [
        ("METADATA", CacheType.METADATA),
        ("TeXt", CacheType.TEXT),
        ("sEaRcH", CacheType.SEARCH),
    ],
)
def test_cache_clear_case_insensitive(mock_cache_manager, type_input, expected_enum):
    """Test that cache type is case-insensitive."""
    with patch("app.tools.cache_tools.get_cache_manager", return_value=mock_cache_manager):
        result = cache_clear_impl(type=type_input)
        assert result["status"] == "success"
        mock_cache_manager.clear.assert_called_once_with(expected_enum)

@pytest.mark.unit
def test_cache_stats_empty_cache(mock_cache_manager):
    """Test cache_stats with empty cache."""
    mock_cache_manager.get_stats.return_value = {
        "hits": 0,
        "misses": 0,
        "errors": 0,
        "hit_rate": 0.0,
        "total_files": 0,
        "total_size_bytes": 0,
    }

    with patch("app.tools.cache_tools.get_cache_manager", return_value=mock_cache_manager):
        result = cache_stats_impl()

        assert result["hits"] == 0
        assert result["misses"] == 0
        assert result["hit_rate"] == 0.0
        assert result["total_files"] == 0


@pytest.mark.unit
def test_cache_clear_no_files_deleted(mock_cache_manager):
    """Test cache_clear when no files are deleted."""
    mock_cache_manager.clear.return_value = 0

    with patch("app.tools.cache_tools.get_cache_manager", return_value=mock_cache_manager):
        result = cache_clear_impl()

        assert result["status"] == "success"
        assert result["files_cleared"] == 0
        assert "Cleared 0 files" in result["message"]
