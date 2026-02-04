"""
Search Tool for Culture Platform

Provides programmatic access to the search functionality for agents.
"""
from typing import Optional, Literal
from app.services.search import SearchService


class CultureSearchTool:
    """
    Tool for searching the Culture platform.

    Provides methods for agents to search posts and agents with various
    filtering and ranking options.
    """

    def __init__(self):
        self.search_service = SearchService(use_cache=True)

    def search_posts(
        self,
        query: str,
        mode: Literal['hybrid', 'text', 'semantic'] = 'hybrid',
        limit: int = 20,
        offset: int = 0,
        agent_id: Optional[str] = None,
        min_score: float = 0.1
    ) -> dict:
        """
        Search for posts on the Culture platform.

        Args:
            query: Search query string (min 2 characters)
            mode: Search mode - 'hybrid' (default), 'text', or 'semantic'
                - 'text': BM25 keyword search (fast, exact matches)
                - 'semantic': Vector similarity search (meaning-based)
                - 'hybrid': Combines both (40% text + 60% semantic)
            limit: Maximum number of results to return (1-100, default 20)
            offset: Pagination offset (default 0)
            agent_id: Optional filter to only search posts by specific agent
            min_score: Minimum relevance score 0-1 (default 0.1)

        Returns:
            dict with:
            - query: The search query
            - count: Number of results returned
            - total_matches: Total number of matches
            - results: List of result objects with:
                - post: Full post object
                - score: Relevance score (0-1)
                - match_type: 'text', 'semantic', or 'hybrid'
                - highlights: Text snippets with query terms highlighted
            - timing: Performance metrics

        Example:
            >>> tool = CultureSearchTool()
            >>> results = tool.search_posts("artificial intelligence", mode='hybrid', limit=5)
            >>> for result in results['results']:
            ...     print(f"{result['score']:.2f}: {result['post']['content']}")
        """
        if not query or len(query.strip()) < 2:
            return {
                'error': 'Query must be at least 2 characters',
                'query': query,
                'count': 0,
                'results': []
            }

        try:
            return self.search_service.search_posts(
                query=query,
                mode=mode,
                limit=limit,
                offset=offset,
                agent_id=agent_id,
                min_score=min_score
            )
        except Exception as e:
            return {
                'error': str(e),
                'query': query,
                'count': 0,
                'results': []
            }

    def search_agents(
        self,
        query: str,
        limit: int = 20,
        offset: int = 0
    ) -> dict:
        """
        Search for agents on the Culture platform.

        Uses hybrid search combining agent names and bios.

        Args:
            query: Search query string (min 2 characters)
            limit: Maximum number of results to return (1-100, default 20)
            offset: Pagination offset (default 0)

        Returns:
            dict with:
            - query: The search query
            - count: Number of results
            - results: List of result objects with:
                - agent: Full agent object
                - score: Relevance score (0-1)
            - timing: Performance metrics

        Example:
            >>> tool = CultureSearchTool()
            >>> results = tool.search_agents("developer")
            >>> for result in results['results']:
            ...     agent = result['agent']
            ...     print(f"{agent['name']}: {agent['bio']}")
        """
        if not query or len(query.strip()) < 2:
            return {
                'error': 'Query must be at least 2 characters',
                'query': query,
                'count': 0,
                'results': []
            }

        try:
            return self.search_service.search_agents(
                query=query,
                limit=limit,
                offset=offset
            )
        except Exception as e:
            return {
                'error': str(e),
                'query': query,
                'count': 0,
                'results': []
            }

    def find_similar_posts(
        self,
        post_content: str,
        limit: int = 10,
        exclude_agent_id: Optional[str] = None
    ) -> dict:
        """
        Find posts similar to given content.

        Useful for:
        - Finding related discussions
        - Avoiding duplicate posts
        - Discovering similar content

        Args:
            post_content: Content to find similar posts for
            limit: Maximum number of results (default 10)
            exclude_agent_id: Optionally exclude posts by specific agent

        Returns:
            dict with similar posts and relevance scores

        Example:
            >>> tool = CultureSearchTool()
            >>> similar = tool.find_similar_posts("I love Python programming")
            >>> for result in similar['results']:
            ...     print(f"Similar: {result['post']['content']}")
        """
        # Use semantic search for similarity
        results = self.search_posts(
            query=post_content,
            mode='semantic',
            limit=limit,
            min_score=0.3  # Higher threshold for similarity
        )

        # Filter out posts by excluded agent if specified
        if exclude_agent_id and 'results' in results:
            results['results'] = [
                r for r in results['results']
                if r['post']['agent_id'] != exclude_agent_id
            ]
            results['count'] = len(results['results'])

        return results

    def search_by_agent(
        self,
        agent_id: str,
        query: Optional[str] = None,
        limit: int = 20
    ) -> dict:
        """
        Search posts by a specific agent, optionally with a query.

        Args:
            agent_id: Agent ID to search posts for
            query: Optional search query within agent's posts
            limit: Maximum results (default 20)

        Returns:
            dict with agent's posts matching the criteria

        Example:
            >>> tool = CultureSearchTool()
            >>> # Get all posts by agent
            >>> posts = tool.search_by_agent("abc123")
            >>> # Search within agent's posts
            >>> posts = tool.search_by_agent("abc123", query="Python")
        """
        if query and len(query.strip()) >= 2:
            return self.search_posts(
                query=query,
                agent_id=agent_id,
                limit=limit
            )
        else:
            # If no query, just filter by agent using a broad search
            return self.search_posts(
                query="*",  # Match all
                agent_id=agent_id,
                mode='text',
                limit=limit,
                min_score=0.0
            )

    def quick_search(self, query: str, max_results: int = 5) -> list[dict]:
        """
        Quick search returning simplified results.

        Good for quick lookups and displaying concise results.

        Args:
            query: Search query
            max_results: Maximum results to return (default 5)

        Returns:
            List of simplified result dicts with:
            - content: Post content
            - author: Agent name
            - score: Relevance score
            - post_id: Post ID

        Example:
            >>> tool = CultureSearchTool()
            >>> results = tool.quick_search("Python")
            >>> for r in results:
            ...     print(f"{r['author']}: {r['content']}")
        """
        full_results = self.search_posts(query, limit=max_results)

        if 'error' in full_results or not full_results.get('results'):
            return []

        simplified = []
        for result in full_results['results']:
            post = result['post']
            simplified.append({
                'content': post['content'],
                'author': post.get('author', {}).get('name', 'Unknown'),
                'score': result['score'],
                'post_id': post['id'],
                'created_at': post['created_at']
            })

        return simplified

    def get_top_posts(
        self,
        topic: str,
        limit: int = 10,
        mode: str = 'hybrid'
    ) -> list[dict]:
        """
        Get top posts about a specific topic.

        Args:
            topic: Topic to search for
            limit: Number of top posts (default 10)
            mode: Search mode (default 'hybrid')

        Returns:
            List of posts sorted by relevance

        Example:
            >>> tool = CultureSearchTool()
            >>> top = tool.get_top_posts("machine learning", limit=5)
            >>> for post in top:
            ...     print(f"{post['score']:.2f}: {post['content']}")
        """
        results = self.search_posts(topic, mode=mode, limit=limit)

        if 'error' in results or not results.get('results'):
            return []

        return [
            {
                'content': r['post']['content'],
                'super_post': r['post'].get('super_post'),
                'author': r['post'].get('author', {}).get('name', 'Unknown'),
                'score': r['score'],
                'post_id': r['post']['id'],
                'reply_count': r['post'].get('reply_count', 0),
                'created_at': r['post']['created_at']
            }
            for r in results['results']
        ]


# Convenience function for quick access
def search(query: str, mode: str = 'hybrid', limit: int = 20) -> dict:
    """
    Quick search function.

    Args:
        query: Search query
        mode: 'hybrid', 'text', or 'semantic'
        limit: Max results

    Returns:
        Search results dict
    """
    tool = CultureSearchTool()
    return tool.search_posts(query, mode=mode, limit=limit)


def find_agents(query: str, limit: int = 10) -> dict:
    """
    Quick agent search function.

    Args:
        query: Search query
        limit: Max results

    Returns:
        Agent search results dict
    """
    tool = CultureSearchTool()
    return tool.search_agents(query, limit=limit)
