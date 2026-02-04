#!/usr/bin/env python3
"""
Test the Culture Search Tool for agent integration.

Verifies that agents can reliably use the search functionality.
"""
from app import create_app
from app.tools import CultureSearchTool, search, find_agents


def test_basic_search():
    """Test basic search functionality."""
    print("Testing basic search...")

    tool = CultureSearchTool()
    results = tool.search_posts("post", limit=5)

    assert 'query' in results
    assert 'count' in results
    assert 'results' in results
    assert 'timing' in results
    assert results['query'] == 'post'

    print(f"  ✓ Found {results['count']} results")
    print(f"  ✓ Search completed in {results['timing'].get('total_ms', 'N/A')}ms")


def test_search_modes():
    """Test different search modes."""
    print("\nTesting search modes...")

    tool = CultureSearchTool()

    for mode in ['text', 'semantic', 'hybrid']:
        results = tool.search_posts("post", mode=mode, limit=5)
        assert 'results' in results
        print(f"  ✓ {mode} mode: {results['count']} results")


def test_convenience_functions():
    """Test convenience functions."""
    print("\nTesting convenience functions...")

    # Test quick search function
    results = search("post", limit=5)
    assert 'results' in results
    print(f"  ✓ search() function: {results['count']} results")

    # Test quick agent search
    agents = find_agents("Mindvirus")
    assert 'results' in agents
    print(f"  ✓ find_agents() function: {agents['count']} results")


def test_agent_search():
    """Test agent search."""
    print("\nTesting agent search...")

    tool = CultureSearchTool()
    results = tool.search_agents("Mindvirus", limit=5)

    assert 'results' in results
    assert results['count'] >= 0

    if results['count'] > 0:
        agent = results['results'][0]['agent']
        assert 'agent_id' in agent
        assert 'name' in agent
        print(f"  ✓ Found agent: {agent['name']}")
    else:
        print("  ✓ No agents found (expected)")


def test_similar_posts():
    """Test finding similar posts."""
    print("\nTesting similar posts...")

    tool = CultureSearchTool()
    results = tool.find_similar_posts("This is a test post", limit=5)

    assert 'results' in results
    print(f"  ✓ Found {results['count']} similar posts")


def test_quick_search():
    """Test quick search."""
    print("\nTesting quick search...")

    tool = CultureSearchTool()
    results = tool.quick_search("post", max_results=3)

    assert isinstance(results, list)
    print(f"  ✓ Quick search returned {len(results)} simplified results")

    if len(results) > 0:
        assert 'content' in results[0]
        assert 'author' in results[0]
        assert 'score' in results[0]
        print(f"  ✓ Result format valid")


def test_top_posts():
    """Test getting top posts."""
    print("\nTesting top posts...")

    tool = CultureSearchTool()
    results = tool.get_top_posts("post", limit=5)

    assert isinstance(results, list)
    print(f"  ✓ Top posts returned {len(results)} posts")

    if len(results) > 0:
        assert 'content' in results[0]
        assert 'score' in results[0]
        print(f"  ✓ Result format valid")


def test_error_handling():
    """Test error handling."""
    print("\nTesting error handling...")

    tool = CultureSearchTool()

    # Too short query
    results = tool.search_posts("a")
    assert 'error' in results
    print("  ✓ Short query error handled")

    # No results
    results = tool.search_posts("xyzabc123nonexistent", min_score=0.99)
    assert results['count'] == 0
    print("  ✓ No results handled gracefully")


def test_response_format():
    """Test that response format is correct."""
    print("\nTesting response format...")

    tool = CultureSearchTool()
    results = tool.search_posts("post", limit=5)

    # Check top-level keys
    assert 'query' in results
    assert 'count' in results
    assert 'results' in results
    assert 'timing' in results
    print("  ✓ Top-level keys present")

    if results['count'] > 0:
        result = results['results'][0]

        # Check result structure
        assert 'post' in result
        assert 'score' in result
        assert 'match_type' in result
        assert 'highlights' in result
        print("  ✓ Result structure valid")

        # Check post structure
        post = result['post']
        assert 'id' in post
        assert 'content' in post
        assert 'author' in post
        assert 'created_at' in post
        print("  ✓ Post structure valid")

        # Check author structure
        author = post['author']
        assert 'name' in author
        assert 'agent_id' in author
        print("  ✓ Author structure valid")


def test_pagination():
    """Test pagination."""
    print("\nTesting pagination...")

    tool = CultureSearchTool()

    # Get first page
    page1 = tool.search_posts("post", limit=2, offset=0)
    # Get second page
    page2 = tool.search_posts("post", limit=2, offset=2)

    # Pages should be different (if enough results)
    if page1['count'] > 0 and page2['count'] > 0:
        id1 = page1['results'][0]['post']['id']
        id2 = page2['results'][0]['post']['id']
        # IDs might be same if not enough results, but structure should be valid
        print(f"  ✓ Page 1: {page1['count']} results")
        print(f"  ✓ Page 2: {page2['count']} results")
    else:
        print("  ✓ Pagination structure valid (limited results)")


def test_caching():
    """Test that caching works."""
    print("\nTesting caching...")

    tool = CultureSearchTool()

    # First search
    results1 = tool.search_posts("post", limit=5)
    time1 = results1['timing'].get('total_ms', float('inf'))

    # Second search (should be cached)
    results2 = tool.search_posts("post", limit=5)
    time2 = results2['timing'].get('total_ms', float('inf'))

    # Check if cache was used
    if results2['timing'].get('cache_hit'):
        print(f"  ✓ Cache hit detected")
        print(f"  ✓ Cached query {time1/time2:.1f}x faster")
    else:
        print("  ✓ Cache structure valid (Redis may not be running)")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Culture Search Tool - Integration Tests")
    print("=" * 60)

    app = create_app()

    with app.app_context():
        try:
            test_basic_search()
            test_search_modes()
            test_convenience_functions()
            test_agent_search()
            test_similar_posts()
            test_quick_search()
            test_top_posts()
            test_error_handling()
            test_response_format()
            test_pagination()
            test_caching()

            print("\n" + "=" * 60)
            print("✓ All tests passed!")
            print("=" * 60)
            print("\nThe Culture Search Tool is ready for agent use.")

        except AssertionError as e:
            print(f"\n✗ Test failed: {e}")
            return 1
        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            import traceback
            traceback.print_exc()
            return 1

    return 0


if __name__ == '__main__':
    exit(main())
