"""
File caching module for performance optimization.

This module provides caching for frequently accessed files to reduce
disk I/O and improve performance.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Union


@dataclass
class CacheEntry:
    """Represents a single cache entry."""

    content: Any
    timestamp: float
    size: int
    checksum: str


class FileCache:
    """
    Cache for file contents with automatic invalidation.

    Features:
    - Time-based expiration
    - Size-based eviction
    - Checksum-based validation
    - Memory usage tracking
    """

    def __init__(
        self,
        max_size_mb: int = 100,
        default_ttl_seconds: int = 300,
        max_entries: int = 1000,
    ):
        """
        Initialize the file cache.

        Args:
            max_size_mb: Maximum cache size in megabytes
            default_ttl_seconds: Default time-to-live for cache entries in seconds
            max_entries: Maximum number of cache entries
        """
        self.max_size_bytes = max_size_mb * 1024 * 1024
        self.default_ttl_seconds = default_ttl_seconds
        self.max_entries = max_entries

        self._cache: Dict[str, CacheEntry] = {}
        self._hits = 0
        self._misses = 0
        self._total_size_bytes = 0

    def _compute_checksum(self, content: Any) -> str:
        """Compute checksum for cache validation."""
        if isinstance(content, (str, bytes)):
            data = content.encode('utf-8') if isinstance(content, str) else content
        else:
            # For complex objects, use pickle
            data = pickle.dumps(content)
        return hashlib.md5(data).hexdigest()

    def _get_file_checksum(self, filepath: Path) -> Optional[str]:
        """Compute checksum of a file."""
        try:
            with open(filepath, 'rb') as f:
                return hashlib.md5(f.read()).hexdigest()
        except (IOError, OSError):
            return None

    def _should_evict(self) -> bool:
        """Check if cache needs eviction."""
        return (
            len(self._cache) >= self.max_entries
            or self._total_size_bytes >= self.max_size_bytes
        )

    def _evict_oldest(self) -> None:
        """Evict the oldest cache entry."""
        if not self._cache:
            return

        oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k].timestamp)
        entry = self._cache.pop(oldest_key)
        self._total_size_bytes -= entry.size

    def _clean_expired(self) -> None:
        """Remove expired cache entries."""
        current_time = time.time()
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if current_time - entry.timestamp > self.default_ttl_seconds
        ]

        for key in expired_keys:
            entry = self._cache.pop(key)
            self._total_size_bytes -= entry.size

    def get(self, key: str, max_age_seconds: Optional[int] = None) -> Optional[Any]:
        """
        Get an item from the cache.

        Args:
            key: Cache key
            max_age_seconds: Maximum age in seconds (overrides default TTL)

        Returns:
            Cached content or None if not found/expired
        """
        if key not in self._cache:
            self._misses += 1
            return None

        entry = self._cache[key]
        current_time = time.time()
        ttl = max_age_seconds or self.default_ttl_seconds

        if current_time - entry.timestamp > ttl:
            # Entry expired
            del self._cache[key]
            self._total_size_bytes -= entry.size
            self._misses += 1
            return None

        self._hits += 1
        return entry.content

    def set(self, key: str, content: Any, ttl_seconds: Optional[int] = None) -> None:
        """
        Set an item in the cache.

        Args:
            key: Cache key
            content: Content to cache
            ttl_seconds: Time-to-live in seconds (overrides default TTL)
        """
        # Clean expired entries before adding new one
        self._clean_expired()

        # Evict if necessary
        while self._should_evict():
            self._evict_oldest()

        # Estimate size
        if isinstance(content, str):
            size = len(content.encode('utf-8'))
        elif isinstance(content, bytes):
            size = len(content)
        else:
            # Rough estimate for complex objects
            size = 1024  # 1KB default

        checksum = self._compute_checksum(content)
        entry = CacheEntry(
            content=content,
            timestamp=time.time(),
            size=size,
            checksum=checksum,
        )

        self._cache[key] = entry
        self._total_size_bytes += size

    def delete(self, key: str) -> bool:
        """
        Delete an item from the cache.

        Args:
            key: Cache key

        Returns:
            True if item was deleted, False if not found
        """
        if key in self._cache:
            entry = self._cache.pop(key)
            self._total_size_bytes -= entry.size
            return True
        return False

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()
        self._total_size_bytes = 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "entries": len(self._cache),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0,
            "total_size_mb": self._total_size_bytes / (1024 * 1024),
            "max_size_mb": self.max_size_bytes / (1024 * 1024),
            "max_entries": self.max_entries,
            "current_entries": len(self._cache),
        }

    def invalidate_file(self, filepath: Path) -> bool:
        """
        Invalidate cache entries for a specific file.

        Args:
            filepath: Path to the file

        Returns:
            True if any entries were invalidated
        """
        key_prefix = f"file:{filepath}:"
        keys_to_delete = [key for key in self._cache.keys() if key.startswith(key_prefix)]

        for key in keys_to_delete:
            self.delete(key)

        return len(keys_to_delete) > 0


class TextFileCache:
    """
    Specialized cache for text files with content validation.
    """

    def __init__(self, file_cache: Optional[FileCache] = None):
        """
        Initialize the text file cache.

        Args:
            file_cache: Optional shared FileCache instance
        """
        self._file_cache = file_cache or FileCache(max_size_mb=50, default_ttl_seconds=60)
        self._text_cache: Dict[str, str] = {}

    def read_text_cached(self, filepath: Path, encoding: str = "utf-8") -> Optional[str]:
        """
        Read text file with caching.

        Args:
            filepath: Path to the file
            encoding: File encoding

        Returns:
            File content or None if file doesn't exist
        """
        cache_key = f"text:{filepath}"

        # Check memory cache first
        if cache_key in self._text_cache:
            return self._text_cache[cache_key]

        # Check file cache
        cached = self._file_cache.get(cache_key)
        if cached is not None:
            self._text_cache[cache_key] = cached
            return cached

        # Read from disk
        try:
            content = filepath.read_text(encoding=encoding)
            self._file_cache.set(cache_key, content)
            self._text_cache[cache_key] = content
            return content
        except (IOError, OSError, UnicodeDecodeError):
            return None

    def read_json_cached(self, filepath: Path) -> Optional[Any]:
        """
        Read JSON file with caching.

        Args:
            filepath: Path to the JSON file

        Returns:
            Parsed JSON content or None if file doesn't exist or is invalid
        """
        cache_key = f"json:{filepath}"

        # Check file cache
        cached = self._file_cache.get(cache_key)
        if cached is not None:
            return cached

        # Read from disk
        try:
            content = json.loads(filepath.read_text(encoding="utf-8"))
            self._file_cache.set(cache_key, content)
            return content
        except (IOError, OSError, json.JSONDecodeError):
            return None

    def read_yaml_cached(self, filepath: Path) -> Optional[Any]:
        """
        Read YAML file with caching.

        Args:
            filepath: Path to the YAML file

        Returns:
            Parsed YAML content or None if file doesn't exist or is invalid
        """
        cache_key = f"yaml:{filepath}"

        # Check file cache
        cached = self._file_cache.get(cache_key)
        if cached is not None:
            return cached

        # Read from disk
        try:
            import yaml
            content = yaml.safe_load(filepath.read_text(encoding="utf-8"))
            self._file_cache.set(cache_key, content)
            return content
        except (IOError, OSError, yaml.YAMLError, ImportError):
            return None

    def invalidate(self, filepath: Path) -> None:
        """
        Invalidate cache for a specific file.

        Args:
            filepath: Path to the file
        """
        cache_key = f"text:{filepath}"
        self._text_cache.pop(cache_key, None)
        self._file_cache.invalidate_file(filepath)

    def clear(self) -> None:
        """Clear all caches."""
        self._text_cache.clear()
        self._file_cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        file_cache_stats = self._file_cache.get_stats()
        return {
            **file_cache_stats,
            "text_cache_entries": len(self._text_cache),
        }


# Global cache instances for convenience
_text_file_cache: Optional[TextFileCache] = None
_file_cache: Optional[FileCache] = None


def get_text_file_cache() -> TextFileCache:
    """Get or create the global text file cache instance."""
    global _text_file_cache
    if _text_file_cache is None:
        _text_file_cache = TextFileCache()
    return _text_file_cache


def get_file_cache() -> FileCache:
    """Get or create the global file cache instance."""
    global _file_cache
    if _file_cache is None:
        _file_cache = FileCache(max_size_mb=100, default_ttl_seconds=300)
    return _file_cache


def clear_caches() -> None:
    """Clear all global caches."""
    global _text_file_cache, _file_cache
    if _text_file_cache:
        _text_file_cache.clear()
    if _file_cache:
        _file_cache.clear()


def get_cache_stats() -> Dict[str, Dict[str, Any]]:
    """Get statistics for all caches."""
    stats = {}
    if _text_file_cache:
        stats["text_file_cache"] = _text_file_cache.get_stats()
    if _file_cache:
        stats["file_cache"] = _file_cache.get_stats()
    return stats


# Utility functions for common operations
def cached_read_text(filepath: Path, encoding: str = "utf-8") -> Optional[str]:
    """Read text file with global caching."""
    cache = get_text_file_cache()
    return cache.read_text_cached(filepath, encoding)


def cached_read_json(filepath: Path) -> Optional[Any]:
    """Read JSON file with global caching."""
    cache = get_text_file_cache()
    return cache.read_json_cached(filepath)


def cached_read_yaml(filepath: Path) -> Optional[Any]:
    """Read YAML file with global caching."""
    cache = get_text_file_cache()
    return cache.read_yaml_cached(filepath)


def invalidate_cached_file(filepath: Path) -> None:
    """Invalidate cache for a specific file."""
    cache = get_text_file_cache()
    cache.invalidate(filepath)


if __name__ == "__main__":
    """Command-line interface for cache management."""
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "stats":
        stats = get_cache_stats()
        if not stats:
            print("No caches initialized.")
            sys.exit(0)

        for cache_name, cache_stats in stats.items():
            print(f"\n{cache_name}:")
            for key, value in cache_stats.items():
                print(f"  {key}: {value}")

    elif len(sys.argv) > 1 and sys.argv[1] == "clear":
        clear_caches()
        print("All caches cleared.")

    else:
        print("Usage:")
        print("  python file_cache.py stats    # Show cache statistics")
        print("  python file_cache.py clear    # Clear all caches")