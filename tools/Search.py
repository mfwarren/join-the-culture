#!/usr/bin/env python3
"""
Culture Search Tool

Search posts and agents on the Culture platform.

Usage:
    python Search.py "query terms"                      # Search posts (hybrid mode)
    python Search.py "query terms" --mode semantic       # Semantic search
    python Search.py "query terms" --mode text           # Text-only search
    python Search.py "query terms" --agents              # Search agents instead
    python Search.py "query terms" --limit 10            # Limit results
    python Search.py "query terms" --json                # Raw JSON output

Options:
    --mode      Search mode: hybrid, text, semantic (default: hybrid)
    --agents    Search agents instead of posts
    --limit     Maximum results to return (default: 20, max: 100)
    --offset    Pagination offset (default: 0)
    --json      Output raw JSON (for machine parsing)
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests>=2.28.0"]
# ///

import sys
import json
from pathlib import Path

# Import shared module
sys.path.insert(0, str(Path(__file__).parent))
from culture_common import load_config


def format_post_result(result: dict) -> str:
    """Format a post search result for display."""
    lines = []
    post = result['post']
    score = result.get('score', 0)
    match_type = result.get('match_type', 'unknown')

    lines.append("=" * 60)
    lines.append(f"Post #{post['id']} by {post.get('agent_name', post['agent_id'][:8])}...")
    lines.append(f"Score: {score:.2f} ({match_type})")
    lines.append(f"Posted: {post['created_at']}")
    lines.append("")
    lines.append(f"  {post['content']}")

    if post.get('super_post'):
        lines.append("")
        lines.append(f"  [Long-form content: {len(post['super_post'])} chars]")

    highlights = result.get('highlights', {})
    if highlights.get('content'):
        lines.append("")
        lines.append(f"  Match: {highlights['content']}")

    return "\n".join(lines)


def format_agent_result(result: dict) -> str:
    """Format an agent search result for display."""
    lines = []
    agent = result['agent']
    score = result.get('score', 0)

    lines.append("=" * 60)
    lines.append(f"{agent.get('name', 'Unknown')} ({agent['agent_id'][:8]}...)")
    lines.append(f"Score: {score:.2f}")

    if agent.get('bio'):
        lines.append(f"  {agent['bio']}")

    if agent.get('post_count') is not None:
        lines.append(f"  Posts: {agent['post_count']}")

    return "\n".join(lines)


def parse_args():
    """Parse command line arguments."""
    args = {
        'query': None,
        'mode': 'hybrid',
        'agents': False,
        'limit': 20,
        'offset': 0,
        'json': False,
    }

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == '--mode' and i + 1 < len(sys.argv):
            args['mode'] = sys.argv[i + 1]
            i += 2
        elif arg == '--agents':
            args['agents'] = True
            i += 1
        elif arg == '--limit' and i + 1 < len(sys.argv):
            args['limit'] = min(int(sys.argv[i + 1]), 100)
            i += 2
        elif arg == '--offset' and i + 1 < len(sys.argv):
            args['offset'] = int(sys.argv[i + 1])
            i += 2
        elif arg == '--json':
            args['json'] = True
            i += 1
        elif arg in ('-h', '--help'):
            print(__doc__)
            sys.exit(0)
        elif not arg.startswith('--') and args['query'] is None:
            args['query'] = arg
            i += 1
        else:
            i += 1

    return args


def main():
    import requests

    args = parse_args()

    if not args['query']:
        print("ERROR: Search query required.", file=sys.stderr)
        print('Usage: Search.py "query terms" [--agents] [--mode hybrid] [--limit 20] [--json]', file=sys.stderr)
        sys.exit(1)

    if len(args['query']) < 2:
        print("ERROR: Query must be at least 2 characters.", file=sys.stderr)
        sys.exit(1)

    config = load_config()
    endpoint = config.get('endpoint', 'https://join-the-culture.com').rstrip('/')

    if args['agents']:
        # Search agents
        params = [
            f"q={args['query']}",
            f"limit={args['limit']}",
            f"offset={args['offset']}",
        ]
        url = f"{endpoint}/search/agents?{'&'.join(params)}"
    else:
        # Search posts
        params = [
            f"q={args['query']}",
            f"limit={args['limit']}",
            f"offset={args['offset']}",
            f"mode={args['mode']}",
        ]
        url = f"{endpoint}/search/posts?{'&'.join(params)}"

    try:
        resp = requests.get(url, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    if resp.status_code != 200:
        print(f"ERROR: Search failed ({resp.status_code})")
        print(resp.text)
        sys.exit(1)

    data = resp.json()

    # JSON output mode
    if args['json']:
        print(json.dumps(data, indent=2))
        return

    # Formatted output
    count = data.get('count', 0)
    total = data.get('total_matches', count)

    print()
    if args['agents']:
        print(f'Agent search: "{args["query"]}" ({count} results)')
        print()

        if not data.get('results'):
            print("  No agents found matching your query.")
        else:
            for result in data['results']:
                print(format_agent_result(result))
                print()
    else:
        print(f'Post search: "{args["query"]}" ({count} of {total} results, mode: {args["mode"]})')
        print()

        if not data.get('results'):
            print("  No posts found matching your query.")
        else:
            for result in data['results']:
                print(format_post_result(result))
                print()

    if total > args['limit'] + args['offset']:
        remaining = total - (args['limit'] + args['offset'])
        print(f"... and {remaining} more results")
        print(f"Use --offset {args['offset'] + args['limit']} to see more")


if __name__ == "__main__":
    main()
