"""
Authentication utilities for Culture.

Ed25519 signature verification and request authentication.
"""
import time
import base64
from functools import wraps
from typing import Callable

from flask import request, jsonify, current_app, g

from app.models import agent_store


def verify_signature(public_key_b64: str, message: bytes, signature_b64: str) -> bool:
    """
    Verify an Ed25519 signature.

    Args:
        public_key_b64: Base64-encoded public key.
        message: The message that was signed.
        signature_b64: Base64-encoded signature.

    Returns:
        True if signature is valid, False otherwise.
    """
    try:
        from nacl.signing import VerifyKey

        public_key_bytes = base64.b64decode(public_key_b64)
        signature_bytes = base64.b64decode(signature_b64)

        # Ed25519 signatures must be exactly 64 bytes
        if len(signature_bytes) != 64:
            return False

        # Ed25519 public keys must be exactly 32 bytes
        if len(public_key_bytes) != 32:
            return False

        verify_key = VerifyKey(public_key_bytes)
        verify_key.verify(message, signature_bytes)
        return True
    except Exception:
        return False


def validate_public_key(public_key_b64: str) -> tuple[bool, str]:
    """
    Validate that a string is a valid base64-encoded Ed25519 public key.

    Args:
        public_key_b64: The public key to validate.

    Returns:
        Tuple of (is_valid, error_message).
    """
    try:
        key_bytes = base64.b64decode(public_key_b64)
        if len(key_bytes) != 32:
            return False, "Ed25519 public keys must be 32 bytes"
        return True, ""
    except Exception as e:
        return False, f"Invalid base64 encoding: {e}"


def require_auth(f: Callable) -> Callable:
    """
    Decorator for endpoints requiring agent authentication.

    Validates:
    - X-Agent-Key header (public key)
    - X-Timestamp header (within tolerance)
    - X-Signature header (valid signature of request)

    Sets g.agent to the authenticated agent on success.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        public_key = request.headers.get('X-Agent-Key')
        signature = request.headers.get('X-Signature')
        timestamp = request.headers.get('X-Timestamp')

        # Check headers present
        if not all([public_key, signature, timestamp]):
            return jsonify({
                'error': 'missing_auth_headers',
                'message': 'Required headers: X-Agent-Key, X-Signature, X-Timestamp'
            }), 401

        # Check agent is registered
        agent = agent_store.get_agent(public_key)
        if not agent:
            return jsonify({
                'error': 'agent_not_registered',
                'message': 'This public key is not registered. POST to /register first.'
            }), 401

        # Check timestamp is recent
        tolerance = current_app.config.get('TIMESTAMP_TOLERANCE', 60)
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > tolerance:
                return jsonify({
                    'error': 'timestamp_expired',
                    'message': f'Timestamp must be within {tolerance} seconds of server time.'
                }), 401
        except ValueError:
            return jsonify({
                'error': 'invalid_timestamp',
                'message': 'X-Timestamp must be a Unix timestamp integer.'
            }), 401

        # Build message to verify
        body = request.get_data(as_text=True) or ''
        message = f"{timestamp}:{request.method}:{request.path}:{body}".encode()

        if not verify_signature(public_key, message, signature):
            return jsonify({
                'error': 'invalid_signature',
                'message': 'Signature verification failed.'
            }), 401

        # Attach agent info to request context
        g.agent = agent
        return f(*args, **kwargs)

    return decorated
