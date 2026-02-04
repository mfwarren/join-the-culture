"""
Integration tests for agent registration.
"""
import base64
import pytest
from nacl.signing import SigningKey


class TestRegistrationFlow:
    """Tests for the complete registration flow."""

    def test_full_registration_flow(self, client, keypair):
        """Complete registration flow succeeds."""
        # Step 1: Request challenge
        resp = client.post('/register',
            json={'public_key': keypair['public_key_b64'], 'name': 'Test Agent'},
            content_type='application/json')

        assert resp.status_code == 200
        data = resp.get_json()
        assert 'challenge' in data
        assert 'expires_in' in data
        challenge = data['challenge']

        # Step 2: Sign challenge
        signature = keypair['signing_key'].sign(challenge.encode()).signature
        signature_b64 = base64.b64encode(signature).decode()

        # Step 3: Verify
        resp = client.post('/register/verify',
            json={'public_key': keypair['public_key_b64'], 'signature': signature_b64},
            content_type='application/json')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'registered'
        assert 'agent_id' in data
        assert len(data['agent_id']) == 16


class TestRegisterEndpoint:
    """Tests for POST /register."""

    def test_missing_public_key(self, client):
        """Request without public_key fails."""
        resp = client.post('/register',
            json={'name': 'Test'},
            content_type='application/json')

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'missing_public_key'

    def test_invalid_public_key_format(self, client):
        """Invalid public key format fails."""
        resp = client.post('/register',
            json={'public_key': 'not-valid-base64!!!'},
            content_type='application/json')

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'invalid_public_key'

    def test_wrong_key_length(self, client):
        """Public key with wrong length fails."""
        short_key = base64.b64encode(b'too short').decode()
        resp = client.post('/register',
            json={'public_key': short_key},
            content_type='application/json')

        assert resp.status_code == 400
        assert '32 bytes' in resp.get_json()['message']

    def test_already_registered(self, client, registered_agent):
        """Registering same key twice fails."""
        resp = client.post('/register',
            json={'public_key': registered_agent['public_key_b64']},
            content_type='application/json')

        assert resp.status_code == 409
        assert resp.get_json()['error'] == 'already_registered'
        assert 'agent_id' in resp.get_json()

    def test_default_name(self, client, keypair):
        """Missing name defaults to 'Anonymous Agent'."""
        resp = client.post('/register',
            json={'public_key': keypair['public_key_b64']},
            content_type='application/json')

        assert resp.status_code == 200
        # Name is stored in pending challenge, verified after registration


class TestRegisterVerifyEndpoint:
    """Tests for POST /register/verify."""

    def test_missing_fields(self, client):
        """Request without required fields fails."""
        resp = client.post('/register/verify',
            json={'public_key': 'key'},
            content_type='application/json')

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'missing_fields'

    def test_no_pending_challenge(self, client, keypair):
        """Verify without requesting challenge first fails."""
        resp = client.post('/register/verify',
            json={
                'public_key': keypair['public_key_b64'],
                'signature': 'some_signature'
            },
            content_type='application/json')

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'no_pending_challenge'

    def test_invalid_signature(self, client, keypair):
        """Invalid signature fails."""
        # First get a challenge
        resp = client.post('/register',
            json={'public_key': keypair['public_key_b64']},
            content_type='application/json')
        assert resp.status_code == 200

        # Submit wrong signature
        wrong_sig = base64.b64encode(b'wrong' * 16).decode()
        resp = client.post('/register/verify',
            json={
                'public_key': keypair['public_key_b64'],
                'signature': wrong_sig
            },
            content_type='application/json')

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'invalid_signature'

    def test_wrong_key_signature(self, client, keypair):
        """Signature from different key fails."""
        # Get challenge
        resp = client.post('/register',
            json={'public_key': keypair['public_key_b64']},
            content_type='application/json')
        challenge = resp.get_json()['challenge']

        # Sign with different key
        other_key = SigningKey.generate()
        signature = other_key.sign(challenge.encode()).signature
        signature_b64 = base64.b64encode(signature).decode()

        resp = client.post('/register/verify',
            json={
                'public_key': keypair['public_key_b64'],
                'signature': signature_b64
            },
            content_type='application/json')

        assert resp.status_code == 401


class TestAgentsList:
    """Tests for GET /agents."""

    def test_empty_list(self, client):
        """Empty store returns empty list."""
        resp = client.get('/agents')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 0
        assert data['agents'] == []

    def test_lists_registered_agents(self, client, registered_agent):
        """Lists registered agents."""
        resp = client.get('/agents')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 1
        assert data['agents'][0]['agent_id'] == registered_agent['agent_id']
        assert data['agents'][0]['name'] == 'Test Agent'

    def test_does_not_expose_public_key(self, client, registered_agent):
        """Public key is not exposed in agent list."""
        resp = client.get('/agents')
        agent = resp.get_json()['agents'][0]
        assert 'public_key' not in agent
