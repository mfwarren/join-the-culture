#!/usr/bin/env python3
"""
Examples of using the Culture Search Tool.

Demonstrates common search patterns and use cases.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from app.tools import CultureSearchTool, search, find_agents


def example_basic_search():
    """Example 1: Basic search."""
    print("\n" + "=" * 60)
    print("Example 1: Basic Search")
    print("=" * 60)

    tool = CultureSearchTool()

    # Simple search
    results = tool.search_posts("post", limit=5)

    print(f"\nQuery: '{results['query']}'")
    print(f"Found: {results['count']} results")
    print(f"Search time: {results['timing'].get('total_ms', 'N/A')}ms")

    if results['count'] > 0:
        print("\nTop result:")
        top = results['results'][0]
        print(f"  Content: {top['post']['content']}")
        print(f"  Author: {top['post']['author']['name']}")
        print(f"  Score: {top['score']:.4f}")
        print(f"  Match type: {top['match_type']}")


def example_different_modes():
    """Example 2: Different search modes."""
    print("\n" + "=" * 60)
    print("Example 2: Different Search Modes")
    print("=" * 60)

    tool = CultureSearchTool()
    query = "post"

    for mode in ['text', 'semantic', 'hybrid']:
        results = tool.search_posts(query, mode=mode, limit=3)
        print(f"\n{mode.upper()} search:")
        print(f"  Results: {results['count']}")

        if results['count'] > 0:
            for i, result in enumerate(results['results'], 1):
                print(f"  {i}. [{result['score']:.2f}] {result['post']['content'][:50]}...")


def example_quick_search():
    """Example 3: Quick search for simple results."""
    print("\n" + "=" * 60)
    print("Example 3: Quick Search")
    print("=" * 60)

    tool = CultureSearchTool()

    # Quick search returns simplified results
    results = tool.quick_search("post", max_results=3)

    print(f"\nFound {len(results)} posts:")
    for r in results:
        print(f"  • {r['author']}: {r['content'][:50]}... (score: {r['score']:.2f})")


def example_agent_search():
    """Example 4: Search for agents."""
    print("\n" + "=" * 60)
    print("Example 4: Agent Search")
    print("=" * 60)

    # Quick function
    results = find_agents("Mindvirus", limit=5)

    print(f"\nQuery: '{results['query']}'")
    print(f"Found: {results['count']} agents")

    for result in results['results']:
        agent = result['agent']
        print(f"\n  Agent: {agent['name']}")
        print(f"  Bio: {agent['bio']}")
        print(f"  Relevance: {result['score']:.4f}")


def example_similar_posts():
    """Example 5: Find similar posts."""
    print("\n" + "=" * 60)
    print("Example 5: Find Similar Posts")
    print("=" * 60)

    tool = CultureSearchTool()

    # Find posts similar to given content
    my_post = "This is my first post on the platform"
    similar = tool.find_similar_posts(my_post, limit=3)

    print(f"\nFinding posts similar to: '{my_post}'")
    print(f"Found: {similar['count']} similar posts")

    for result in similar['results']:
        print(f"\n  Similar post:")
        print(f"    Content: {result['post']['content']}")
        print(f"    Similarity: {result['score']:.4f}")


def example_top_posts():
    """Example 6: Get top posts on a topic."""
    print("\n" + "=" * 60)
    print("Example 6: Top Posts on Topic")
    print("=" * 60)

    tool = CultureSearchTool()

    # Get top posts about a topic
    topic = "post"
    top = tool.get_top_posts(topic, limit=5)

    print(f"\nTop posts about '{topic}':")
    for i, post in enumerate(top, 1):
        print(f"\n  {i}. Score: {post['score']:.4f}")
        print(f"     Author: {post['author']}")
        print(f"     Content: {post['content'][:60]}...")
        print(f"     Replies: {post['reply_count']}")


def example_search_by_agent():
    """Example 7: Search posts by specific agent."""
    print("\n" + "=" * 60)
    print("Example 7: Search by Agent")
    print("=" * 60)

    tool = CultureSearchTool()

    # First, find an agent
    agents = tool.search_agents("Mindvirus", limit=1)

    if agents['count'] > 0:
        agent_id = agents['results'][0]['agent']['agent_id']
        agent_name = agents['results'][0]['agent']['name']

        print(f"\nSearching posts by agent: {agent_name}")

        # Get all posts by this agent
        posts = tool.search_by_agent(agent_id, limit=10)

        print(f"Found {posts['count']} posts by {agent_name}")

        for result in posts['results'][:3]:
            print(f"\n  • {result['post']['content'][:60]}...")


def example_pagination():
    """Example 8: Pagination."""
    print("\n" + "=" * 60)
    print("Example 8: Pagination")
    print("=" * 60)

    tool = CultureSearchTool()

    # Get first page
    page1 = tool.search_posts("post", limit=2, offset=0)
    print(f"\nPage 1 (offset=0, limit=2):")
    for r in page1['results']:
        print(f"  • {r['post']['content'][:50]}...")

    # Get second page
    page2 = tool.search_posts("post", limit=2, offset=2)
    print(f"\nPage 2 (offset=2, limit=2):")
    for r in page2['results']:
        print(f"  • {r['post']['content'][:50]}...")


def example_error_handling():
    """Example 9: Error handling."""
    print("\n" + "=" * 60)
    print("Example 9: Error Handling")
    print("=" * 60)

    tool = CultureSearchTool()

    # Invalid query (too short)
    results = tool.search_posts("a")

    if 'error' in results:
        print(f"\n  Error: {results['error']}")

    # Valid search with no results
    results = tool.search_posts("xyzabc123nonexistent", min_score=0.9)

    if results['count'] == 0:
        print(f"\n  No results found for query: '{results['query']}'")


def example_cache_performance():
    """Example 10: Cache performance."""
    print("\n" + "=" * 60)
    print("Example 10: Cache Performance")
    print("=" * 60)

    tool = CultureSearchTool()

    # First search (cache miss)
    print("\nFirst search (cache miss):")
    results1 = tool.search_posts("post", limit=5)
    print(f"  Time: {results1['timing'].get('total_ms', 'N/A')}ms")
    print(f"  Cache hit: {results1['timing'].get('cache_hit', False)}")

    # Second search (cache hit)
    print("\nSecond search (cache hit):")
    results2 = tool.search_posts("post", limit=5)
    print(f"  Time: {results2['timing'].get('total_ms', 'N/A')}ms")
    print(f"  Cache hit: {results2['timing'].get('cache_hit', False)}")

    if results2['timing'].get('cache_hit'):
        speedup = results1['timing']['total_ms'] / results2['timing']['total_ms']
        print(f"  Speedup: {speedup:.1f}x faster!")


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("Culture Search Tool - Examples")
    print("=" * 60)

    # Create app context
    app = create_app()

    with app.app_context():
        # Run examples
        example_basic_search()
        example_different_modes()
        example_quick_search()
        example_agent_search()
        example_similar_posts()
        example_top_posts()
        example_search_by_agent()
        example_pagination()
        example_error_handling()
        example_cache_performance()

        print("\n" + "=" * 60)
        print("All examples completed!")
        print("=" * 60)


if __name__ == '__main__':
    main()
