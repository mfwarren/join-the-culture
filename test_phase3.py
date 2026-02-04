#!/usr/bin/env python3
"""Test Phase 3: Async processing and caching."""
import time
from app import create_app
from app.services.search import SearchService
from app.services.cache import SearchCache

app = create_app()

with app.app_context():
    print("=" * 60)
    print("Phase 3 Test: Async Processing & Caching")
    print("=" * 60)

    # Test 1: Cache functionality
    print("\n1. Testing cache functionality...")
    search_service = SearchService(use_cache=True)

    # First search (cache miss)
    print("   First search (should be cache miss)...")
    start = time.time()
    results1 = search_service.search_posts("post", mode='hybrid')
    time1 = (time.time() - start) * 1000
    print(f"   ✓ Found {results1['count']} results in {time1:.2f}ms")
    print(f"   Cache hit: {results1['timing'].get('cache_hit', False)}")

    # Second search (cache hit)
    print("   Second search (should be cache hit)...")
    start = time.time()
    results2 = search_service.search_posts("post", mode='hybrid')
    time2 = (time.time() - start) * 1000
    print(f"   ✓ Found {results2['count']} results in {time2:.2f}ms")
    print(f"   Cache hit: {results2['timing'].get('cache_hit', False)}")

    if results2['timing'].get('cache_hit'):
        speedup = time1 / time2 if time2 > 0 else 0
        print(f"   ✓ Cache speedup: {speedup:.1f}x faster")
    else:
        print("   ⚠ Cache miss (Redis may not be running)")

    # Test 2: Cache stats
    print("\n2. Testing cache stats...")
    cache = SearchCache()
    stats = cache.get_stats()
    print(f"   Total keys: {stats.get('total_keys', 'N/A')}")
    print(f"   Cache hits: {stats.get('hits', 'N/A')}")
    print(f"   Cache misses: {stats.get('misses', 'N/A')}")
    print(f"   Hit rate: {stats.get('hit_rate', 'N/A')}%")

    # Test 3: Celery task import
    print("\n3. Testing Celery task configuration...")
    try:
        from app.tasks import generate_post_embedding, celery
        print("   ✓ Celery tasks imported successfully")
        print(f"   Celery broker: {celery.conf.broker_url}")
        print(f"   Celery backend: {celery.conf.result_backend}")
    except Exception as e:
        print(f"   ✗ Failed to import Celery tasks: {e}")

    # Test 4: Different search modes
    print("\n4. Testing all search modes...")
    for mode in ['text', 'semantic', 'hybrid']:
        results = search_service.search_posts("post", mode=mode, limit=5)
        print(f"   {mode.capitalize():10} mode: {results['count']} results")

    print("\n" + "=" * 60)
    print("Phase 3 Tests Complete!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Start Celery worker: celery -A app.tasks.celery worker --loglevel=info")
    print("2. Create a new post to test async embedding generation")
    print("3. Monitor Redis: redis-cli monitor")
