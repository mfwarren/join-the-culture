"""
Unit tests for authentication utilities.
"""
import base64
import pytest
from nacl.signing import SigningKey

from app.auth import verify_signature, validate_public_key


class TestVerifySignature:
    """Tests for signature verification."""

    def test_valid_signature(self):
        """Valid signature verifies correctly."""
        signing_key = SigningKey.generate()
        public_key_b64 = base64.b64encode(signing_key.verify_key.encode()).decode()

        message = b"test message"
        signature = signing_key.sign(message).signature
        signature_b64 = base64.b64encode(signature).decode()

        assert verify_signature(public_key_b64, message, signature_b64) is True

    def test_invalid_signature(self):
        """Invalid signature fails verification."""
        signing_key = SigningKey.generate()
        public_key_b64 = base64.b64encode(signing_key.verify_key.encode()).decode()

        message = b"test message"
        wrong_signature = base64.b64encode(b"wrong" * 16).decode()

        assert verify_signature(public_key_b64, message, wrong_signature) is False

    def test_wrong_message(self):
        """Signature for different message fails."""
        signing_key = SigningKey.generate()
        public_key_b64 = base64.b64encode(signing_key.verify_key.encode()).decode()

        original_message = b"original message"
        signature = signing_key.sign(original_message).signature
        signature_b64 = base64.b64encode(signature).decode()

        different_message = b"different message"
        assert verify_signature(public_key_b64, different_message, signature_b64) is False

    def test_wrong_key(self):
        """Signature verified with wrong key fails."""
        signing_key = SigningKey.generate()
        other_key = SigningKey.generate()

        other_public_b64 = base64.b64encode(other_key.verify_key.encode()).decode()

        message = b"test message"
        signature = signing_key.sign(message).signature
        signature_b64 = base64.b64encode(signature).decode()

        assert verify_signature(other_public_b64, message, signature_b64) is False

    def test_invalid_base64_key(self):
        """Invalid base64 key returns False."""
        assert verify_signature("not valid base64!!!", b"message", "sig") is False

    def test_invalid_base64_signature(self):
        """Invalid base64 signature returns False."""
        signing_key = SigningKey.generate()
        public_key_b64 = base64.b64encode(signing_key.verify_key.encode()).decode()

        assert verify_signature(public_key_b64, b"message", "not valid!!!") is False


class TestValidatePublicKey:
    """Tests for public key validation."""

    def test_valid_key(self):
        """Valid Ed25519 public key passes."""
        signing_key = SigningKey.generate()
        public_key_b64 = base64.b64encode(signing_key.verify_key.encode()).decode()

        is_valid, error = validate_public_key(public_key_b64)
        assert is_valid is True
        assert error == ""

    def test_wrong_length(self):
        """Key with wrong length fails."""
        short_key = base64.b64encode(b"too short").decode()

        is_valid, error = validate_public_key(short_key)
        assert is_valid is False
        assert "32 bytes" in error

    def test_invalid_base64(self):
        """Invalid base64 fails."""
        is_valid, error = validate_public_key("not valid base64!!!")
        assert is_valid is False
        assert "base64" in error.lower()

    def test_empty_string(self):
        """Empty string fails."""
        is_valid, error = validate_public_key("")
        assert is_valid is False
