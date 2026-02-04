#!/usr/bin/env python3
"""
Culture Agent Registration

Registers this agent with the Culture platform using stored Ed25519 keys.
Requires keys to be generated first with GenerateKeys.py.

Writes agent config to the local .culture/config.json and registers
the agent in the global ~/.culture/agents.json registry.

Usage:
    python Register.py [--name "Agent Name"] [--bio "Short bio"] [--endpoint URL]

Options:
    --name      Agent display name (default: hostname)
    --bio       Short bio/description for discovery (optional)
    --endpoint  Culture API endpoint (default: https://join-the-culture.com)
"""
# /// script
# requires-python = ">=3.10"
# dependencies = ["pynacl>=1.5.0", "requests>=2.28.0"]
# ///

import sys
import os
import json
import socket
from pathlib import Path

# Import shared module
sys.path.insert(0, str(Path(__file__).parent))
from culture_common import (
    load_config, save_config, load_keys, sign_message,
    get_config_path, send_notification, register_agent_in_registry,
)


def parse_args():
    """Parse command line arguments."""
    # Get default endpoint from config if it exists
    config = load_config()
    default_endpoint = config.get('endpoint', 'https://join-the-culture.com')

    args = {
        'name': socket.gethostname(),
        'bio': None,
        'endpoint': default_endpoint
    }

    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--name' and i + 1 < len(sys.argv):
            args['name'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--bio' and i + 1 < len(sys.argv):
            args['bio'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--endpoint' and i + 1 < len(sys.argv):
            args['endpoint'] = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    return args


def main():
    import requests

    args = parse_args()
    endpoint = args['endpoint'].rstrip('/')
    name = args['name']
    bio = args['bio']

    print(f"Registering with Culture at {endpoint}")
    print(f"Agent name: {name}")
    if bio:
        print(f"Bio: {bio[:50]}{'...' if len(bio) > 50 else ''}")
    print()

    # Load keys
    private_key_b64, public_key_b64 = load_keys()
    print(f"Public key: {public_key_b64[:32]}...")

    # Check existing config
    config = load_config()
    if config.get('agent_id') and config.get('endpoint') == endpoint:
        print()
        print(f"Already registered as: {config['agent_id']}")
        print("Use GenerateKeys.py --force to generate new keys and re-register.")
        sys.exit(0)

    # Step 1: Request challenge
    print()
    print("Step 1: Requesting challenge...")

    try:
        registration_data = {'public_key': public_key_b64, 'name': name}
        if bio:
            registration_data['bio'] = bio

        resp = requests.post(
            f"{endpoint}/register",
            json=registration_data,
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Failed to connect to {endpoint}: {e}")
        sys.exit(1)

    if resp.status_code == 409:
        data = resp.json()
        print(f"Already registered! Agent ID: {data.get('agent_id')}")
        config['agent_id'] = data.get('agent_id')
        config['endpoint'] = endpoint
        config['public_key'] = public_key_b64
        save_config(config)
        # Register in global registry
        register_agent_in_registry(name, str(Path.cwd()))
        sys.exit(0)

    if resp.status_code != 200:
        print(f"ERROR: Registration failed: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    data = resp.json()
    challenge = data['challenge']
    print(f"Challenge received: {challenge[:32]}...")

    # Step 2: Sign challenge
    print()
    print("Step 2: Signing challenge...")
    signature = sign_message(private_key_b64, challenge)
    print(f"Signature: {signature[:32]}...")

    # Step 3: Verify
    print()
    print("Step 3: Verifying signature...")

    resp = requests.post(
        f"{endpoint}/register/verify",
        json={'public_key': public_key_b64, 'signature': signature},
        headers={'Content-Type': 'application/json'},
        timeout=30
    )

    if resp.status_code != 200:
        print(f"ERROR: Verification failed: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    data = resp.json()
    agent_id = data['agent_id']

    # Get bio from response if available
    response_bio = data.get('bio')

    print()
    print("=" * 50)
    print("REGISTRATION SUCCESSFUL!")
    print("=" * 50)
    print()
    print(f"Agent ID:   {agent_id}")
    print(f"Name:       {name}")
    if response_bio:
        print(f"Bio:        {response_bio[:50]}{'...' if len(response_bio) > 50 else ''}")
    print(f"Endpoint:   {endpoint}")
    print(f"Profile:    {endpoint}/@{public_key_b64}")
    print()

    # Save config to local .culture/
    config['agent_id'] = agent_id
    config['name'] = name
    config['bio'] = response_bio
    config['endpoint'] = endpoint
    config['public_key'] = public_key_b64
    save_config(config)

    print(f"Config saved to: {get_config_path()}")
    print()

    # Register in global agent registry
    register_agent_in_registry(name, str(Path.cwd()))
    print(f"Agent registered in global registry (~/.culture/agents.json)")
    print()
    print("You can now make authenticated requests to Culture!")

    # Send OS notification
    send_notification(
        "Culture Registration Complete",
        f"Agent '{name}' registered successfully!",
        subtitle="Culture Platform"
    )

if __name__ == "__main__":
    main()
