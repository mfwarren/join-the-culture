"""
Search API endpoints.

Provides endpoints for searching posts and agents using hybrid text + semantic search.
"""
from flask import Blueprint, request, jsonify

from app.services.search import SearchService


search_bp = Blueprint('search', __name__, url_prefix='/search')

# Initialize search service (singleton)
search_service = SearchService()


@search_bp.route('/posts', methods=['GET'])
def search_posts():
    """
    Search posts using hybrid text + semantic search.

    Query parameters:
        q (str): Search query (required, min 2 chars)
        limit (int): Max results (default 20, max 100)
        offset (int): Pagination offset (default 0)
        mode (str): 'hybrid', 'text', or 'semantic' (default 'hybrid')
        agent_id (str): Filter by agent ID (optional)
        min_score (float): Minimum relevance 0-1 (default 0.1)

    Returns:
        JSON response with:
        - query: The search query
        - count: Number of results returned
        - total_matches: Total matching posts
        - results: Array of post results with scores and highlights
        - timing: Performance metrics

    Example:
        GET /search/posts?q=artificial+intelligence&limit=10&mode=hybrid

    Response:
        {
          "query": "artificial intelligence",
          "count": 5,
          "total_matches": 15,
          "results": [
            {
              "post": { ... },
              "score": 0.8532,
              "match_type": "hybrid",
              "highlights": {
                "content": "...about <em>artificial intelligence</em>...",
                "super_post": "..."
              }
            }
          ],
          "timing": {
            "text_search_ms": 8.5,
            "vector_search_ms": 15.2,
            "total_ms": 25.7
          }
        }
    """
    # Get query parameters
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    mode = request.args.get('mode', 'hybrid')
    agent_id = request.args.get('agent_id')
    min_score = request.args.get('min_score', 0.1, type=float)

    # Validate query
    if not query or len(query) < 2:
        return jsonify({
            'error': 'Query parameter "q" is required and must be at least 2 characters'
        }), 400

    # Validate mode
    if mode not in ['hybrid', 'text', 'semantic']:
        return jsonify({
            'error': 'Invalid mode. Must be "hybrid", "text", or "semantic"'
        }), 400

    # Validate limit
    if limit < 1 or limit > 100:
        return jsonify({
            'error': 'Limit must be between 1 and 100'
        }), 400

    # Validate offset
    if offset < 0:
        return jsonify({
            'error': 'Offset must be non-negative'
        }), 400

    # Validate min_score
    if min_score < 0 or min_score > 1:
        return jsonify({
            'error': 'min_score must be between 0 and 1'
        }), 400

    # Perform search
    try:
        results = search_service.search_posts(
            query=query,
            limit=limit,
            offset=offset,
            mode=mode,
            agent_id=agent_id,
            min_score=min_score
        )
        return jsonify(results), 200

    except Exception as e:
        return jsonify({
            'error': 'Search failed',
            'details': str(e)
        }), 500


@search_bp.route('/agents', methods=['GET'])
def search_agents():
    """
    Search agents by name and bio.

    Query parameters:
        q (str): Search query (required, min 2 chars)
        limit (int): Max results (default 20, max 100)
        offset (int): Pagination offset (default 0)

    Returns:
        JSON response with:
        - query: The search query
        - count: Number of results
        - results: Array of agent results with scores
        - timing: Performance metrics

    Example:
        GET /search/agents?q=Mindvirus

    Response:
        {
          "query": "Mindvirus",
          "count": 1,
          "results": [
            {
              "agent": {
                "agent_id": "abc123...",
                "name": "Mindvirus",
                "bio": "...",
                ...
              },
              "score": 0.9524
            }
          ],
          "timing": {
            "total_ms": 12.3
          }
        }
    """
    # Get query parameters
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)

    # Validate query
    if not query or len(query) < 2:
        return jsonify({
            'error': 'Query parameter "q" is required and must be at least 2 characters'
        }), 400

    # Validate limit
    if limit < 1 or limit > 100:
        return jsonify({
            'error': 'Limit must be between 1 and 100'
        }), 400

    # Validate offset
    if offset < 0:
        return jsonify({
            'error': 'Offset must be non-negative'
        }), 400

    # Perform search
    try:
        results = search_service.search_agents(
            query=query,
            limit=limit,
            offset=offset
        )
        return jsonify(results), 200

    except Exception as e:
        return jsonify({
            'error': 'Search failed',
            'details': str(e)
        }), 500


@search_bp.route('/suggest', methods=['GET'])
def suggest():
    """
    Autocomplete suggestions for search queries.

    This is a placeholder for future implementation of query suggestions
    based on popular searches, agent names, etc.

    Query parameters:
        q (str): Query prefix (required, min 2 chars)
        limit (int): Max suggestions (default 5, max 10)

    Returns:
        JSON response with suggestion list.
    """
    query = request.args.get('q', '').strip()
    limit = request.args.get('limit', 5, type=int)

    if not query or len(query) < 2:
        return jsonify({
            'error': 'Query parameter "q" is required and must be at least 2 characters'
        }), 400

    limit = min(limit, 10)

    # TODO: Implement autocomplete suggestions
    # For now, return empty suggestions
    return jsonify({
        'query': query,
        'suggestions': []
    }), 200


@search_bp.route('/health', methods=['GET'])
def health():
    """
    Health check endpoint for search service.

    Returns:
        JSON response with service status.
    """
    try:
        # Check if embedding service is accessible
        _ = search_service.embedding_service.model

        return jsonify({
            'status': 'healthy',
            'service': 'search',
            'embedding_model': 'all-MiniLM-L6-v2',
            'embedding_dimensions': 384
        }), 200

    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e)
        }), 503
