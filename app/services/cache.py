"""
Search caching service using Redis.

Caches search results to improve performance for repeated queries.
"""
import json
import hashlib
from typing import Optional

import redis


class SearchCache:
    """
    Redis-based cache for search results.

    Caches query results to reduce database load and improve response times
    for frequently searched queries.
    """

    def __init__(self, ttl: int = 3600):
        """
        Initialize search cache.

        Args:
            ttl: Time-to-live for cached results in seconds (default 1 hour).
        """
        self.redis = redis.Redis(
            host='localhost',
            port=6379,
            db=2,  # Use separate DB for search cache
            decode_responses=True  # Automatically decode responses to strings
        )
        self.ttl = ttl

    def get_cached_search(self, query: str, params: dict) -> Optional[dict]:
        """
        Get cached search results.

        Args:
            query: Search query string.
            params: Search parameters (limit, offset, mode, etc).

        Returns:
            Cached results dict or None if not cached.
        """
        cache_key = self._generate_key(query, params)

        try:
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            print(f"Cache get error: {e}")

        return None

    def cache_search(self, query: str, params: dict, results: dict):
        """
        Cache search results.

        Args:
            query: Search query string.
            params: Search parameters.
            results: Results to cache.
        """
        cache_key = self._generate_key(query, params)

        try:
            self.redis.setex(
                cache_key,
                self.ttl,
                json.dumps(results)
            )
        except Exception as e:
            print(f"Cache set error: {e}")

    def invalidate_post(self, post_id: int):
        """
        Clear cache when a post is created/updated.

        Args:
            post_id: ID of the post that was modified.
        """
        try:
            # For simplicity, clear all post search cache
            # In production, could be more selective
            pattern = "search:posts:*"
            for key in self.redis.scan_iter(pattern, count=100):
                self.redis.delete(key)
        except Exception as e:
            print(f"Cache invalidation error: {e}")

    def invalidate_agent(self, agent_id: str):
        """
        Clear cache when an agent is updated.

        Args:
            agent_id: ID of the agent that was modified.
        """
        try:
            # Clear agent search cache
            pattern = "search:agents:*"
            for key in self.redis.scan_iter(pattern, count=100):
                self.redis.delete(key)
        except Exception as e:
            print(f"Cache invalidation error: {e}")

    def clear_all(self):
        """Clear all search cache."""
        try:
            self.redis.flushdb()
        except Exception as e:
            print(f"Cache clear error: {e}")

    def get_stats(self) -> dict:
        """
        Get cache statistics.

        Returns:
            Dict with cache info and stats.
        """
        try:
            info = self.redis.info('stats')
            return {
                'total_keys': self.redis.dbsize(),
                'hits': info.get('keyspace_hits', 0),
                'misses': info.get('keyspace_misses', 0),
                'hit_rate': self._calculate_hit_rate(
                    info.get('keyspace_hits', 0),
                    info.get('keyspace_misses', 0)
                )
            }
        except Exception as e:
            return {
                'error': str(e)
            }

    def _generate_key(self, query: str, params: dict) -> str:
        """
        Generate cache key from query and parameters.

        Args:
            query: Search query.
            params: Search parameters.

        Returns:
            Cache key string.
        """
        # Normalize params for consistent cache keys
        normalized_params = {
            'limit': params.get('limit', 20),
            'offset': params.get('offset', 0),
            'mode': params.get('mode', 'hybrid'),
            'agent_id': params.get('agent_id'),
            'min_score': params.get('min_score', 0.1)
        }

        # Create deterministic string
        key_data = f"{query}:{json.dumps(normalized_params, sort_keys=True)}"

        # Hash to create shorter key
        hash_val = hashlib.sha256(key_data.encode()).hexdigest()[:16]

        # Prefix based on search type
        prefix = "search:posts"
        if params.get('search_type') == 'agents':
            prefix = "search:agents"

        return f"{prefix}:{hash_val}"

    def _calculate_hit_rate(self, hits: int, misses: int) -> float:
        """
        Calculate cache hit rate.

        Args:
            hits: Number of cache hits.
            misses: Number of cache misses.

        Returns:
            Hit rate as percentage (0-100).
        """
        total = hits + misses
        if total == 0:
            return 0.0

        return round((hits / total) * 100, 2)
