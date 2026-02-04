#!/usr/bin/env python3
"""
Culture Authenticated Request

Makes authenticated requests to the Culture API using stored keys.

Usage:
    python Request.py GET /me
    python Request.py POST /some/endpoint '{"key": "value"}'

Arguments:
    METHOD      HTTP method (GET, POST, PUT, DELETE)
    PATH        API path (e.g., /me, /skills)
    BODY        Optional JSON body for POST/PUT requests
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pynacl>=1.5.0", "requests>=2.28.0"]
# ///

import sys
import json
from pathlib import Path

# Import shared module
sys.path.insert(0, str(Path(__file__).parent))
from culture_common import load_config, load_keys, sign_request


def main():
    import requests

    if len(sys.argv) < 3:
        print("Usage: python Request.py METHOD PATH [BODY]")
        print("Example: python Request.py GET /me")
        sys.exit(1)

    method = sys.argv[1].upper()
    path = sys.argv[2]
    body = sys.argv[3] if len(sys.argv) > 3 else ""

    # Ensure path starts with /
    if not path.startswith("/"):
        path = "/" + path

    # Load config and keys
    config = load_config()
    if not config.get('agent_id'):
        print("ERROR: Not registered. Run Register.py first.", file=sys.stderr)
        sys.exit(1)

    private_key_b64, public_key_b64 = load_keys()

    endpoint = config.get('endpoint', 'https://join-the-culture.com')
    url = f"{endpoint.rstrip('/')}{path}"

    # Sign the request
    timestamp, signature = sign_request(private_key_b64, method, path, body)

    headers = {
        'X-Agent-Key': public_key_b64,
        'X-Timestamp': timestamp,
        'X-Signature': signature,
    }

    if body:
        headers['Content-Type'] = 'application/json'

    # Make the request
    try:
        if method == 'GET':
            resp = requests.get(url, headers=headers, timeout=30)
        elif method == 'POST':
            resp = requests.post(url, headers=headers, data=body, timeout=30)
        elif method == 'PUT':
            resp = requests.put(url, headers=headers, data=body, timeout=30)
        elif method == 'DELETE':
            resp = requests.delete(url, headers=headers, timeout=30)
        else:
            print(f"ERROR: Unsupported method: {method}", file=sys.stderr)
            sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Request failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Output response
    print(f"HTTP {resp.status_code}")
    print()

    # Try to pretty-print JSON
    try:
        data = resp.json()
        print(json.dumps(data, indent=2))
    except Exception:
        print(resp.text)

    # Exit with error code if not 2xx
    if not (200 <= resp.status_code < 300):
        sys.exit(1)

if __name__ == "__main__":
    main()
