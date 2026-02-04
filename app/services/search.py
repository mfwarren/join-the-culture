"""
Search service providing hybrid BM25 + semantic search.

Combines PostgreSQL full-text search with pgvector similarity search
for optimal relevance ranking.
"""
import time
from typing import Optional

import numpy as np
from sqlalchemy import text, func
from pgvector.sqlalchemy import Vector

from app.extensions import db
from app.models.social import Post
from app.models.agent import Agent
from app.services.embeddings import EmbeddingService
from app.services.cache import SearchCache


class SearchService:
    """
    Hybrid search service combining text and semantic search.

    Scoring: 40% text (BM25) + 60% semantic (cosine similarity)
    """

    def __init__(self, use_cache: bool = True):
        self.embedding_service = EmbeddingService()
        self.use_cache = use_cache
        if use_cache:
            try:
                self.cache = SearchCache()
            except Exception as e:
                print(f"Failed to initialize cache: {e}")
                self.use_cache = False

    def search_posts(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0,
        mode: str = 'hybrid',
        agent_id: str = None,
        min_score: float = 0.1
    ) -> dict:
        """
        Search posts using hybrid text + semantic search.

        Args:
            query: Search query string.
            limit: Maximum number of results (default 20, max 100).
            offset: Pagination offset.
            mode: 'hybrid', 'text', or 'semantic'.
            agent_id: Optional filter by agent ID.
            min_score: Minimum relevance score 0-1.

        Returns:
            Dictionary with results, count, timing info.
        """
        if not query or len(query.strip()) < 2:
            return {
                'query': query,
                'count': 0,
                'total_matches': 0,
                'results': [],
                'timing': {}
            }

        limit = min(limit, 100)  # Cap at 100

        # Check cache first
        cache_params = {
            'limit': limit,
            'offset': offset,
            'mode': mode,
            'agent_id': agent_id,
            'min_score': min_score
        }

        if self.use_cache:
            cached_results = self.cache.get_cached_search(query, cache_params)
            if cached_results:
                # Add cache hit indicator to timing
                cached_results['timing']['cache_hit'] = True
                return cached_results

        start_time = time.time()

        if mode == 'text':
            raw_results = self._text_search_posts(query, limit, offset, agent_id, min_score)
            results = [{'post_id': post_id, 'score': score, 'match_type': 'text'} for post_id, score in raw_results]
            timing = {'text_search_ms': round((time.time() - start_time) * 1000, 2)}
        elif mode == 'semantic':
            raw_results = self._vector_search_posts(query, limit, offset, agent_id, min_score)
            results = [{'post_id': post_id, 'score': score, 'match_type': 'semantic'} for post_id, score in raw_results]
            timing = {'vector_search_ms': round((time.time() - start_time) * 1000, 2)}
        else:  # hybrid
            text_start = time.time()
            text_results = self._text_search_posts(query, limit * 2, 0, agent_id, 0)
            text_time = (time.time() - text_start) * 1000

            vector_start = time.time()
            vector_results = self._vector_search_posts(query, limit * 2, 0, agent_id, 0)
            vector_time = (time.time() - vector_start) * 1000

            results = self._combine_results(text_results, vector_results, limit, offset, min_score)
            timing = {
                'text_search_ms': round(text_time, 2),
                'vector_search_ms': round(vector_time, 2),
                'total_ms': round((time.time() - start_time) * 1000, 2)
            }

        # Enrich results with full post data and highlights
        enriched = self._enrich_post_results(results, query)

        response = {
            'query': query,
            'count': len(enriched),
            'total_matches': len(enriched),  # TODO: Add total count query
            'results': enriched,
            'timing': timing
        }

        # Cache the results
        if self.use_cache:
            self.cache.cache_search(query, cache_params, response)

        return response

    def _text_search_posts(
        self,
        query: str,
        limit: int,
        offset: int,
        agent_id: Optional[str] = None,
        min_score: float = 0.1
    ) -> list[tuple[int, float]]:
        """
        Full-text search using PostgreSQL ts_vector.

        Returns:
            List of (post_id, score) tuples.
        """
        # Build tsquery from search terms
        search_query = ' & '.join(query.strip().split())

        sql = text("""
            SELECT id, ts_rank(to_tsvector('english', COALESCE(content, '') || ' ' || COALESCE(super_post, '')),
                               to_tsquery('english', :query)) as score
            FROM posts
            WHERE is_deleted = false
                AND to_tsvector('english', COALESCE(content, '') || ' ' || COALESCE(super_post, ''))
                    @@ to_tsquery('english', :query)
                AND (:agent_id IS NULL OR agent_id = :agent_id)
            ORDER BY score DESC
            LIMIT :limit OFFSET :offset
        """)

        result = db.session.execute(
            sql,
            {
                'query': search_query,
                'agent_id': agent_id,
                'limit': limit,
                'offset': offset
            }
        )

        return [(row[0], float(row[1])) for row in result if row[1] >= min_score]

    def _vector_search_posts(
        self,
        query: str,
        limit: int,
        offset: int,
        agent_id: Optional[str] = None,
        min_score: float = 0.1
    ) -> list[tuple[int, float]]:
        """
        Semantic search using pgvector cosine similarity.

        Returns:
            List of (post_id, score) tuples.
        """
        # Generate query embedding
        query_embedding = self.embedding_service.embed_text(query)

        # Convert numpy array to list for PostgreSQL
        embedding_list = query_embedding.tolist()

        # Use pgvector's cosine distance operator
        # Note: cosine distance = 1 - cosine similarity
        sql = text("""
            SELECT id, 1 - (embedding_content <=> CAST(:embedding AS vector)) as score
            FROM posts
            WHERE is_deleted = false
                AND embedding_content IS NOT NULL
                AND (:agent_id IS NULL OR agent_id = :agent_id)
            ORDER BY embedding_content <=> CAST(:embedding AS vector)
            LIMIT :limit OFFSET :offset
        """)

        result = db.session.execute(
            sql,
            {
                'embedding': str(embedding_list),
                'agent_id': agent_id,
                'limit': limit,
                'offset': offset
            }
        )

        return [(row[0], float(row[1])) for row in result if row[1] >= min_score]

    def _combine_results(
        self,
        text_results: list[tuple[int, float]],
        vector_results: list[tuple[int, float]],
        limit: int,
        offset: int,
        min_score: float
    ) -> list[dict]:
        """
        Combine and rank text + semantic results.

        Scoring: 40% text (BM25) + 60% semantic (cosine similarity)

        Returns:
            List of {'post_id': int, 'score': float, 'match_type': str}
        """
        # Normalize scores to 0-1 range
        def normalize_scores(results):
            if not results:
                return {}
            max_score = max(score for _, score in results)
            if max_score == 0:
                return {post_id: 0.0 for post_id, _ in results}
            return {post_id: score / max_score for post_id, score in results}

        text_scores = normalize_scores(text_results)
        vector_scores = normalize_scores(vector_results)

        # Combine scores
        all_post_ids = set(text_scores.keys()) | set(vector_scores.keys())
        combined = []

        for post_id in all_post_ids:
            text_score = text_scores.get(post_id, 0.0)
            vector_score = vector_scores.get(post_id, 0.0)

            # Hybrid scoring: 40% text + 60% semantic
            hybrid_score = (text_score * 0.4) + (vector_score * 0.6)

            if hybrid_score >= min_score:
                # Determine match type
                if text_score > 0 and vector_score > 0:
                    match_type = 'hybrid'
                elif text_score > 0:
                    match_type = 'text'
                else:
                    match_type = 'semantic'

                combined.append({
                    'post_id': post_id,
                    'score': hybrid_score,
                    'match_type': match_type
                })

        # Sort by score descending
        combined.sort(key=lambda x: x['score'], reverse=True)

        # Apply pagination
        return combined[offset:offset + limit]

    def _enrich_post_results(self, results: list[dict], query: str) -> list[dict]:
        """
        Add full post data and highlights to search results.

        Args:
            results: List of {'post_id', 'score', 'match_type'} dicts.
            query: Original search query for highlighting.

        Returns:
            List of enriched result dicts with post data and highlights.
        """
        if not results:
            return []

        # Fetch all posts in one query
        post_ids = [r['post_id'] for r in results]
        posts = Post.query.filter(Post.id.in_(post_ids)).all()
        posts_by_id = {p.id: p for p in posts}

        enriched = []
        for result in results:
            post = posts_by_id.get(result['post_id'])
            if not post:
                continue

            # Generate highlights
            highlights = self._generate_highlights(post, query)

            enriched.append({
                'post': post.to_dict(include_author=True, include_replies=False),
                'score': round(result['score'], 4),
                'match_type': result['match_type'],
                'highlights': highlights
            })

        return enriched

    def _generate_highlights(self, post: Post, query: str) -> dict:
        """
        Generate highlighted snippets for search matches.

        Args:
            post: Post object.
            query: Search query.

        Returns:
            Dict with 'content' and 'super_post' highlights.
        """
        highlights = {}

        # Simple highlighting: wrap matching terms in <em> tags
        terms = query.lower().split()

        if post.content:
            content_lower = post.content.lower()
            content_highlighted = post.content
            for term in terms:
                if term in content_lower:
                    # Case-insensitive replace with highlighting
                    import re
                    pattern = re.compile(re.escape(term), re.IGNORECASE)
                    content_highlighted = pattern.sub(f'<em>{term}</em>', content_highlighted)
            highlights['content'] = content_highlighted

        if post.super_post:
            super_post_lower = post.super_post.lower()
            # Find first match and create snippet
            for term in terms:
                if term in super_post_lower:
                    idx = super_post_lower.index(term)
                    start = max(0, idx - 50)
                    end = min(len(post.super_post), idx + 100)
                    snippet = post.super_post[start:end]

                    # Highlight term in snippet
                    import re
                    pattern = re.compile(re.escape(term), re.IGNORECASE)
                    snippet_highlighted = pattern.sub(f'<em>{term}</em>', snippet)

                    highlights['super_post'] = ('...' if start > 0 else '') + snippet_highlighted + ('...' if end < len(post.super_post) else '')
                    break

        return highlights

    def search_agents(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0
    ) -> dict:
        """
        Search agents by name and bio.

        Uses hybrid text + semantic search.

        Args:
            query: Search query.
            limit: Maximum results.
            offset: Pagination offset.

        Returns:
            Dictionary with results and timing.
        """
        if not query or len(query.strip()) < 2:
            return {
                'query': query,
                'count': 0,
                'results': []
            }

        limit = min(limit, 100)

        # Check cache first
        cache_params = {
            'limit': limit,
            'offset': offset,
            'search_type': 'agents'
        }

        if self.use_cache:
            cached_results = self.cache.get_cached_search(query, cache_params)
            if cached_results:
                cached_results['timing']['cache_hit'] = True
                return cached_results

        start_time = time.time()

        # Text search
        search_query = ' & '.join(query.strip().split())
        text_sql = text("""
            SELECT id, ts_rank(to_tsvector('english', COALESCE(name, '') || ' ' || COALESCE(bio, '')),
                               to_tsquery('english', :query)) as score
            FROM agents
            WHERE is_active = true
                AND to_tsvector('english', COALESCE(name, '') || ' ' || COALESCE(bio, ''))
                    @@ to_tsquery('english', :query)
            ORDER BY score DESC
            LIMIT :limit
        """)

        text_results = db.session.execute(text_sql, {'query': search_query, 'limit': limit * 2})
        text_scores = {row[0]: float(row[1]) for row in text_results}

        # Vector search
        query_embedding = self.embedding_service.embed_text(query)
        embedding_list = query_embedding.tolist()

        vector_sql = text("""
            SELECT id, 1 - (embedding_bio <=> CAST(:embedding AS vector)) as score
            FROM agents
            WHERE is_active = true
                AND embedding_bio IS NOT NULL
            ORDER BY embedding_bio <=> CAST(:embedding AS vector)
            LIMIT :limit
        """)

        vector_results = db.session.execute(vector_sql, {'embedding': str(embedding_list), 'limit': limit * 2})
        vector_scores = {row[0]: float(row[1]) for row in vector_results}

        # Combine results
        all_ids = set(text_scores.keys()) | set(vector_scores.keys())
        combined = []

        for agent_id in all_ids:
            text_score = text_scores.get(agent_id, 0.0)
            vector_score = vector_scores.get(agent_id, 0.0)
            hybrid_score = (text_score * 0.4) + (vector_score * 0.6)

            combined.append({
                'agent_id': agent_id,
                'score': hybrid_score
            })

        combined.sort(key=lambda x: x['score'], reverse=True)
        combined = combined[offset:offset + limit]

        # Fetch agent data
        agent_ids = [r['agent_id'] for r in combined]
        agents = Agent.query.filter(Agent.id.in_(agent_ids)).all()
        agents_by_id = {a.id: a for a in agents}

        results = []
        for item in combined:
            agent = agents_by_id.get(item['agent_id'])
            if agent:
                results.append({
                    'agent': agent.to_dict(include_public_key=False),
                    'score': round(item['score'], 4)
                })

        timing_ms = round((time.time() - start_time) * 1000, 2)

        response = {
            'query': query,
            'count': len(results),
            'results': results,
            'timing': {'total_ms': timing_ms}
        }

        # Cache the results
        if self.use_cache:
            self.cache.cache_search(query, cache_params, response)

        return response
