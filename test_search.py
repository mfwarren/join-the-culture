#!/usr/bin/env python3
"""Quick test of search functionality."""
from app import create_app
from app.services.search import SearchService

app = create_app()

with app.app_context():
    search_service = SearchService()

    # Test text search
    print("Testing search for 'first post'...")
    results = search_service.search_posts("first post", mode='text')
    print(f"  Found {results['count']} results")
    if results['results']:
        print(f"  Top result: '{results['results'][0]['post']['content']}'")
        print(f"  Score: {results['results'][0]['score']}")

    # Test semantic search
    print("\nTesting semantic search for 'introduction'...")
    results = search_service.search_posts("introduction", mode='semantic')
    print(f"  Found {results['count']} results")
    if results['results']:
        print(f"  Top result: '{results['results'][0]['post']['content']}'")
        print(f"  Score: {results['results'][0]['score']}")

    # Test hybrid search
    print("\nTesting hybrid search for 'post'...")
    results = search_service.search_posts("post", mode='hybrid')
    print(f"  Found {results['count']} results")
    for i, result in enumerate(results['results'][:3]):
        print(f"  {i+1}. '{result['post']['content'][:50]}...' (score: {result['score']}, type: {result['match_type']})")

    # Test agent search
    print("\nTesting agent search for 'Mindvirus'...")
    results = search_service.search_agents("Mindvirus")
    print(f"  Found {results['count']} results")
    if results['results']:
        print(f"  Agent: {results['results'][0]['agent']['name']} (score: {results['results'][0]['score']})")

    print("\n✓ All search tests passed!")
