"""
Graphiti Memory Caching Layer
=============================

High-performance caching layer for Graphiti memory operations providing:
- LRU caching with TTL expiration for query results
- Query result caching with intelligent cache keys
- Write-through caching with batch support
- Cache invalidation on writes
- Statistics tracking for cache performance

Usage:
    from integrations.graphiti.cache import CachedGraphitiMemory

    # Wrap existing memory with caching
    memory = GraphitiMemory(spec_dir, project_dir)
    cached = CachedGraphitiMemory(memory)

    # Use same API - caching is transparent
    context = await cached.get_relevant_context("implement auth")
    await cached.save_pattern("Use React hooks for state")

    # Check cache stats
    stats = cached.get_cache_stats()
    print(f"Hit rate: {stats.hit_rate:.1%}")
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generic, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


# =============================================================================
# Cache Entry and Statistics
# =============================================================================


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with TTL support."""

    key: str
    value: T
    created_at: float
    ttl_seconds: int
    hits: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired."""
        return time.time() - self.created_at > self.ttl_seconds

    @property
    def age_seconds(self) -> float:
        """Get age of entry in seconds."""
        return time.time() - self.created_at


@dataclass
class CacheStats:
    """Statistics for cache performance."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    expirations: int = 0
    writes: int = 0
    invalidations: int = 0
    current_size: int = 0
    max_size: int = 0

    @property
    def total_requests(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.hits / self.total_requests

    def to_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "expirations": self.expirations,
            "writes": self.writes,
            "invalidations": self.invalidations,
            "current_size": self.current_size,
            "max_size": self.max_size,
            "total_requests": self.total_requests,
            "hit_rate": self.hit_rate,
        }


# =============================================================================
# LRU Cache Implementation
# =============================================================================


class LRUCache(Generic[T]):
    """
    Thread-safe LRU cache with TTL support.

    Features:
    - Configurable max size
    - TTL-based expiration
    - Automatic eviction of oldest entries
    - Statistics tracking
    """

    def __init__(
        self,
        max_size: int = 100,
        default_ttl: int = 300,  # 5 minutes
    ):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = threading.RLock()
        self._stats = CacheStats(max_size=max_size)

    def get(self, key: str) -> T | None:
        """
        Get value from cache.

        Returns None if not found or expired.
        """
        with self._lock:
            if key not in self._cache:
                self._stats.misses += 1
                return None

            entry = self._cache[key]

            # Check expiration
            if entry.is_expired:
                del self._cache[key]
                self._stats.expirations += 1
                self._stats.misses += 1
                self._stats.current_size = len(self._cache)
                return None

            # Move to end (most recently used)
            self._cache.move_to_end(key)
            entry.hits += 1
            self._stats.hits += 1

            return entry.value

    def set(
        self,
        key: str,
        value: T,
        ttl: int | None = None,
    ) -> None:
        """
        Set value in cache.

        Evicts oldest entry if cache is full.
        """
        ttl = ttl if ttl is not None else self.default_ttl

        with self._lock:
            # If key exists, update it
            if key in self._cache:
                self._cache[key].value = value
                self._cache[key].created_at = time.time()
                self._cache[key].ttl_seconds = ttl
                self._cache.move_to_end(key)
            else:
                # Evict if at capacity
                while len(self._cache) >= self.max_size:
                    self._cache.popitem(last=False)
                    self._stats.evictions += 1

                # Add new entry
                self._cache[key] = CacheEntry(
                    key=key,
                    value=value,
                    created_at=time.time(),
                    ttl_seconds=ttl,
                )

            self._stats.writes += 1
            self._stats.current_size = len(self._cache)

    def invalidate(self, key: str) -> bool:
        """
        Invalidate a specific cache entry.

        Returns True if entry was found and removed.
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.invalidations += 1
                self._stats.current_size = len(self._cache)
                return True
            return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all entries matching a key pattern.

        Pattern is a simple prefix match.
        Returns count of invalidated entries.
        """
        with self._lock:
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_remove:
                del self._cache[key]
                self._stats.invalidations += 1

            self._stats.current_size = len(self._cache)
            return len(keys_to_remove)

    def clear(self) -> int:
        """Clear all cache entries. Returns count of cleared entries."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._stats.invalidations += count
            self._stats.current_size = 0
            return count

    def cleanup_expired(self) -> int:
        """Remove all expired entries. Returns count of removed entries."""
        with self._lock:
            expired_keys = [k for k, v in self._cache.items() if v.is_expired]
            for key in expired_keys:
                del self._cache[key]
                self._stats.expirations += 1

            self._stats.current_size = len(self._cache)
            return len(expired_keys)

    def get_stats(self) -> CacheStats:
        """Get cache statistics."""
        with self._lock:
            self._stats.current_size = len(self._cache)
            return CacheStats(
                hits=self._stats.hits,
                misses=self._stats.misses,
                evictions=self._stats.evictions,
                expirations=self._stats.expirations,
                writes=self._stats.writes,
                invalidations=self._stats.invalidations,
                current_size=self._stats.current_size,
                max_size=self._stats.max_size,
            )

    def reset_stats(self) -> None:
        """Reset statistics (keeps cache entries)."""
        with self._lock:
            self._stats = CacheStats(max_size=self.max_size)
            self._stats.current_size = len(self._cache)


# =============================================================================
# Write Batch Support
# =============================================================================


@dataclass
class PendingWrite:
    """A pending write operation for batching."""

    operation: str  # e.g., "pattern", "gotcha", "discovery"
    data: Any
    created_at: float = field(default_factory=time.time)


class WriteBatcher:
    """
    Batches write operations for improved performance.

    Collects writes and flushes them periodically or when batch size reached.
    """

    def __init__(
        self,
        max_batch_size: int = 10,
        max_wait_seconds: float = 5.0,
    ):
        self.max_batch_size = max_batch_size
        self.max_wait_seconds = max_wait_seconds
        self._pending: list[PendingWrite] = []
        self._lock = threading.Lock()
        self._last_flush = time.time()

    def add(self, operation: str, data: Any) -> bool:
        """
        Add a write operation to the batch.

        Returns True if batch is ready to flush.
        """
        with self._lock:
            self._pending.append(PendingWrite(operation=operation, data=data))
            return self.should_flush()

    def should_flush(self) -> bool:
        """Check if batch should be flushed."""
        with self._lock:
            if len(self._pending) >= self.max_batch_size:
                return True
            if time.time() - self._last_flush >= self.max_wait_seconds:
                return True
            return False

    def get_batch(self) -> list[PendingWrite]:
        """Get and clear pending writes."""
        with self._lock:
            batch = self._pending.copy()
            self._pending.clear()
            self._last_flush = time.time()
            return batch

    @property
    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)


# =============================================================================
# Cached Graphiti Memory Wrapper
# =============================================================================


class CachedGraphitiMemory:
    """
    Caching wrapper for GraphitiMemory.

    Provides transparent caching with:
    - Query result caching with LRU eviction
    - TTL-based expiration
    - Cache invalidation on writes
    - Optional write batching
    - Performance statistics

    Usage:
        memory = GraphitiMemory(spec_dir, project_dir)
        cached = CachedGraphitiMemory(memory)

        # Same API as GraphitiMemory
        context = await cached.get_relevant_context("query")
    """

    def __init__(
        self,
        memory,  # GraphitiMemory instance
        cache_size: int = 100,
        default_ttl: int = 300,  # 5 minutes
        enable_write_batching: bool = False,
        batch_size: int = 10,
        batch_wait_seconds: float = 5.0,
    ):
        self._memory = memory
        self._cache = LRUCache[Any](max_size=cache_size, default_ttl=default_ttl)
        self._write_batcher = (
            WriteBatcher(max_batch_size=batch_size, max_wait_seconds=batch_wait_seconds)
            if enable_write_batching
            else None
        )
        self._default_ttl = default_ttl

        # Forward properties
        self.spec_dir = memory.spec_dir
        self.project_dir = memory.project_dir

    def _make_cache_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate a cache key from method name and arguments."""
        # Create stable hash of arguments
        key_data = json.dumps(
            {"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}},
            sort_keys=True,
        )
        key_hash = hashlib.md5(key_data.encode(), usedforsecurity=False).hexdigest()[:16]
        return f"{prefix}:{key_hash}"

    # =========================================================================
    # Cached Query Methods
    # =========================================================================

    async def get_relevant_context(
        self,
        query: str,
        num_results: int = 10,
        include_project_context: bool = True,
        ttl: int | None = None,
        bypass_cache: bool = False,
    ) -> list[dict]:
        """
        Get relevant context with caching.

        Args:
            query: Search query
            num_results: Max results
            include_project_context: Include project-wide context
            ttl: Cache TTL in seconds (None for default)
            bypass_cache: Skip cache lookup (still caches result)

        Returns:
            List of context items
        """
        cache_key = self._make_cache_key(
            "context",
            query,
            num_results=num_results,
            include_project_context=include_project_context,
        )

        # Check cache
        if not bypass_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                logger.debug(f"Cache hit for context query: {query[:50]}...")
                return cached

        # Fetch from memory
        result = await self._memory.get_relevant_context(
            query, num_results, include_project_context
        )

        # Cache result
        self._cache.set(cache_key, result, ttl or self._default_ttl)
        logger.debug(f"Cached context query result: {len(result)} items")

        return result

    async def get_session_history(
        self,
        limit: int = 5,
        spec_only: bool = True,
        ttl: int | None = None,
        bypass_cache: bool = False,
    ) -> list[dict]:
        """Get session history with caching."""
        cache_key = self._make_cache_key("history", limit=limit, spec_only=spec_only)

        if not bypass_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        result = await self._memory.get_session_history(limit, spec_only)
        self._cache.set(cache_key, result, ttl or self._default_ttl)

        return result

    async def get_similar_task_outcomes(
        self,
        task_description: str,
        limit: int = 5,
        ttl: int | None = None,
        bypass_cache: bool = False,
    ) -> list[dict]:
        """Get similar task outcomes with caching."""
        cache_key = self._make_cache_key(
            "outcomes", task_description, limit=limit
        )

        if not bypass_cache:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        result = await self._memory.get_similar_task_outcomes(task_description, limit)
        self._cache.set(cache_key, result, ttl or self._default_ttl)

        return result

    # =========================================================================
    # Write Methods (with cache invalidation)
    # =========================================================================

    async def save_session_insights(
        self,
        session_num: int,
        insights: dict,
    ) -> bool:
        """Save session insights with cache invalidation."""
        result = await self._memory.save_session_insights(session_num, insights)

        if result:
            # Invalidate related caches
            self._cache.invalidate_pattern("history:")
            self._cache.invalidate_pattern("context:")

        return result

    async def save_codebase_discoveries(
        self,
        discoveries: dict[str, str],
    ) -> bool:
        """Save discoveries with cache invalidation."""
        result = await self._memory.save_codebase_discoveries(discoveries)

        if result:
            self._cache.invalidate_pattern("context:")

        return result

    async def save_pattern(self, pattern: str) -> bool:
        """Save pattern with cache invalidation."""
        if self._write_batcher:
            should_flush = self._write_batcher.add("pattern", pattern)
            if should_flush:
                return await self._flush_writes()
            return True

        result = await self._memory.save_pattern(pattern)
        if result:
            self._cache.invalidate_pattern("context:")
        return result

    async def save_gotcha(self, gotcha: str) -> bool:
        """Save gotcha with cache invalidation."""
        if self._write_batcher:
            should_flush = self._write_batcher.add("gotcha", gotcha)
            if should_flush:
                return await self._flush_writes()
            return True

        result = await self._memory.save_gotcha(gotcha)
        if result:
            self._cache.invalidate_pattern("context:")
        return result

    async def save_task_outcome(
        self,
        task_id: str,
        success: bool,
        outcome: str,
        metadata: dict | None = None,
    ) -> bool:
        """Save task outcome with cache invalidation."""
        result = await self._memory.save_task_outcome(task_id, success, outcome, metadata)

        if result:
            self._cache.invalidate_pattern("outcomes:")
            self._cache.invalidate_pattern("context:")

        return result

    async def save_structured_insights(self, insights: dict) -> bool:
        """Save structured insights with cache invalidation."""
        result = await self._memory.save_structured_insights(insights)

        if result:
            self._cache.invalidate_pattern("context:")
            self._cache.invalidate_pattern("history:")

        return result

    async def _flush_writes(self) -> bool:
        """Flush batched writes to memory."""
        if not self._write_batcher:
            return True

        batch = self._write_batcher.get_batch()
        if not batch:
            return True

        success = True
        for write in batch:
            try:
                if write.operation == "pattern":
                    await self._memory.save_pattern(write.data)
                elif write.operation == "gotcha":
                    await self._memory.save_gotcha(write.data)
            except Exception as e:
                logger.warning(f"Failed to flush write: {e}")
                success = False

        # Invalidate caches after batch
        self._cache.invalidate_pattern("context:")

        return success

    # =========================================================================
    # Passthrough Methods
    # =========================================================================

    async def initialize(self) -> bool:
        """Initialize underlying memory."""
        return await self._memory.initialize()

    async def close(self) -> None:
        """Close underlying memory and flush pending writes."""
        if self._write_batcher and self._write_batcher.pending_count > 0:
            await self._flush_writes()
        await self._memory.close()

    @property
    def is_enabled(self) -> bool:
        return self._memory.is_enabled

    @property
    def is_initialized(self) -> bool:
        return self._memory.is_initialized

    def get_status_summary(self) -> dict:
        """Get status including cache stats."""
        status = self._memory.get_status_summary()
        status["cache"] = self.get_cache_stats().to_dict()
        if self._write_batcher:
            status["pending_writes"] = self._write_batcher.pending_count
        return status

    # =========================================================================
    # Cache Management
    # =========================================================================

    def get_cache_stats(self) -> CacheStats:
        """Get cache statistics."""
        return self._cache.get_stats()

    def clear_cache(self) -> int:
        """Clear all cached entries. Returns count cleared."""
        return self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove expired cache entries. Returns count removed."""
        return self._cache.cleanup_expired()

    def invalidate_all_queries(self) -> int:
        """Invalidate all query caches."""
        count = 0
        count += self._cache.invalidate_pattern("context:")
        count += self._cache.invalidate_pattern("history:")
        count += self._cache.invalidate_pattern("outcomes:")
        return count

    def warmup_cache(
        self,
        queries: list[str],
        num_results: int = 10,
    ) -> asyncio.Task:
        """
        Pre-warm cache with common queries.

        Returns a task that can be awaited or run in background.
        """

        async def _warmup():
            for query in queries:
                try:
                    await self.get_relevant_context(query, num_results)
                except Exception as e:
                    logger.warning(f"Cache warmup failed for '{query}': {e}")

        return asyncio.create_task(_warmup())


# =============================================================================
# Factory Function
# =============================================================================


def create_cached_memory(
    spec_dir: Path,
    project_dir: Path,
    group_id_mode: str = "spec",
    cache_size: int = 100,
    ttl_seconds: int = 300,
    enable_batching: bool = False,
) -> CachedGraphitiMemory:
    """
    Create a cached GraphitiMemory instance.

    Convenience function that wraps GraphitiMemory with caching.

    Args:
        spec_dir: Spec directory
        project_dir: Project root
        group_id_mode: "spec" or "project"
        cache_size: Max cache entries
        ttl_seconds: Default TTL for cache entries
        enable_batching: Enable write batching

    Returns:
        CachedGraphitiMemory instance
    """
    # Import here to avoid circular imports
    from .queries_pkg.graphiti import GraphitiMemory

    memory = GraphitiMemory(spec_dir, project_dir, group_id_mode)

    return CachedGraphitiMemory(
        memory=memory,
        cache_size=cache_size,
        default_ttl=ttl_seconds,
        enable_write_batching=enable_batching,
    )


# =============================================================================
# Export All Public APIs
# =============================================================================

__all__ = [
    # Cache classes
    "CacheEntry",
    "CacheStats",
    "LRUCache",
    # Write batching
    "PendingWrite",
    "WriteBatcher",
    # Main wrapper
    "CachedGraphitiMemory",
    # Factory
    "create_cached_memory",
]
