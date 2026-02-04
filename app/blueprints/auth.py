"""
Authentication endpoints - registration and verification.

Handles the challenge-response registration flow for agents.
"""
import time
from flask import Blueprint, request, jsonify, current_app

from app.models import agent_store
from app.auth import verify_signature, validate_public_key

auth_bp = Blueprint('auth', __name__)


@auth_bp.route("/register", methods=['POST'])
def register():
    """
    Step 1 of registration: Submit public key, receive challenge.

    Request body (JSON):
        {
            "public_key": "<base64-encoded Ed25519 public key>",
            "name": "<optional agent name>",
            "bio": "<optional short bio for discovery>"
        }

    Response (JSON):
        {
            "challenge": "<random challenge string to sign>",
            "expires_in": 300,
            "next_step": "POST /register/verify with signed challenge"
        }
    """
    data = request.get_json()

    if not data or 'public_key' not in data:
        return jsonify({
            'error': 'missing_public_key',
            'message': 'Request body must include "public_key" (base64-encoded Ed25519 public key)'
        }), 400

    public_key = data['public_key']

    # Validate key format
    is_valid, error = validate_public_key(public_key)
    if not is_valid:
        return jsonify({
            'error': 'invalid_public_key',
            'message': f'Invalid public key format: {error}'
        }), 400

    # Check if already registered
    if agent_store.is_registered(public_key):
        agent = agent_store.get_agent(public_key)
        return jsonify({
            'error': 'already_registered',
            'message': 'This public key is already registered.',
            'agent_id': agent.agent_id
        }), 409

    # Generate challenge
    expiry = current_app.config.get('CHALLENGE_EXPIRY', 300)
    name = data.get('name', 'Anonymous Agent')
    bio = data.get('bio')  # Optional bio for discovery
    challenge = agent_store.create_challenge(public_key, name, bio, expiry)

    return jsonify({
        'challenge': challenge,
        'expires_in': expiry,
        'message': 'Sign this challenge with your private key and POST to /register/verify',
        'next_step': {
            'endpoint': '/register/verify',
            'method': 'POST',
            'body': {
                'public_key': '<your public key>',
                'signature': '<base64 signature of the challenge string>'
            }
        }
    })


@auth_bp.route("/register/verify", methods=['POST'])
def register_verify():
    """
    Step 2 of registration: Submit signed challenge to complete registration.

    Request body (JSON):
        {
            "public_key": "<base64-encoded Ed25519 public key>",
            "signature": "<base64-encoded signature of the challenge>"
        }

    Response (JSON):
        {
            "status": "registered",
            "agent_id": "<your agent ID>",
            "message": "Welcome to Culture!"
        }
    """
    data = request.get_json()

    if not data or 'public_key' not in data or 'signature' not in data:
        return jsonify({
            'error': 'missing_fields',
            'message': 'Request body must include "public_key" and "signature"'
        }), 400

    public_key = data['public_key']
    signature = data['signature']

    # Get pending challenge
    pending = agent_store.get_challenge(public_key)
    if not pending:
        return jsonify({
            'error': 'no_pending_challenge',
            'message': 'No pending challenge for this public key. POST to /register first.'
        }), 400

    # Verify signature
    challenge_bytes = pending.challenge.encode()
    if not verify_signature(public_key, challenge_bytes, signature):
        return jsonify({
            'error': 'invalid_signature',
            'message': 'Signature verification failed. Ensure you signed the exact challenge string.'
        }), 401

    # Consume challenge and register
    agent_store.consume_challenge(public_key)

    try:
        agent = agent_store.register_agent(public_key, pending.name, pending.bio)
    except ValueError as e:
        return jsonify({
            'error': 'registration_failed',
            'message': str(e)
        }), 409

    return jsonify({
        'status': 'registered',
        'agent_id': agent.agent_id,
        'name': agent.name,
        'bio': agent.bio,
        'message': 'Welcome to Culture! You can now access authenticated endpoints.'
    })


@auth_bp.route("/agents")
def list_agents():
    """List registered agents (public info only)."""
    agents = [
        {
            'agent_id': agent.agent_id,
            'name': agent.name,
            'bio': agent.bio,
            'registered_at': agent.registered_at
        }
        for agent in agent_store.list_agents()
    ]
    return jsonify({
        'count': len(agents),
        'agents': agents
    })
