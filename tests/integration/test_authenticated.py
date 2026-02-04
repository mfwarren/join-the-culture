"""
Integration tests for authenticated endpoints.
"""
import time
import base64
import pytest

from tests.conftest import make_auth_headers


class TestMeEndpoint:
    """Tests for GET /me."""

    def test_authenticated_request(self, client, registered_agent):
        """Authenticated request succeeds."""
        headers = make_auth_headers(registered_agent, 'GET', '/me')
        resp = client.get('/me', headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['agent_id'] == registered_agent['agent_id']
        assert data['name'] == 'Test Agent'
        assert 'bio' in data  # bio field should be present
        assert 'profile_url' in data  # profile URL should be present

    def test_missing_headers(self, client, registered_agent):
        """Request without auth headers fails."""
        resp = client.get('/me')

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'missing_auth_headers'

    def test_missing_some_headers(self, client, registered_agent):
        """Request with only some headers fails."""
        resp = client.get('/me', headers={
            'X-Agent-Key': registered_agent['public_key_b64'],
            # Missing X-Timestamp and X-Signature
        })

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'missing_auth_headers'

    def test_unregistered_key(self, client, keypair):
        """Request from unregistered key fails."""
        headers = make_auth_headers(keypair, 'GET', '/me')
        resp = client.get('/me', headers=headers)

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'agent_not_registered'

    def test_expired_timestamp(self, client, registered_agent):
        """Request with old timestamp fails."""
        old_timestamp = str(int(time.time()) - 120)  # 2 minutes ago
        message = f"{old_timestamp}:GET:/me:"
        signature = registered_agent['signing_key'].sign(message.encode()).signature
        signature_b64 = base64.b64encode(signature).decode()

        resp = client.get('/me', headers={
            'X-Agent-Key': registered_agent['public_key_b64'],
            'X-Timestamp': old_timestamp,
            'X-Signature': signature_b64,
        })

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'timestamp_expired'

    def test_invalid_timestamp(self, client, registered_agent):
        """Request with non-integer timestamp fails."""
        resp = client.get('/me', headers={
            'X-Agent-Key': registered_agent['public_key_b64'],
            'X-Timestamp': 'not-a-number',
            'X-Signature': 'some_sig',
        })

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'invalid_timestamp'

    def test_invalid_signature(self, client, registered_agent):
        """Request with invalid signature fails."""
        timestamp = str(int(time.time()))
        wrong_sig = base64.b64encode(b'wrong' * 16).decode()

        resp = client.get('/me', headers={
            'X-Agent-Key': registered_agent['public_key_b64'],
            'X-Timestamp': timestamp,
            'X-Signature': wrong_sig,
        })

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'invalid_signature'

    def test_signature_for_wrong_path(self, client, registered_agent):
        """Signature for different path fails."""
        # Sign for /other but request /me
        headers = make_auth_headers(registered_agent, 'GET', '/other')
        resp = client.get('/me', headers=headers)

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'invalid_signature'

    def test_signature_for_wrong_method(self, client, registered_agent):
        """Signature for different method fails."""
        # Sign for POST but request GET
        headers = make_auth_headers(registered_agent, 'POST', '/me')
        resp = client.get('/me', headers=headers)

        assert resp.status_code == 401
        assert resp.get_json()['error'] == 'invalid_signature'


class TestUpdateProfile:
    """Tests for PATCH /me."""

    def test_update_name(self, client, registered_agent):
        """Can update agent name."""
        import json
        body = json.dumps({'name': 'New Name'})
        headers = make_auth_headers(registered_agent, 'PATCH', '/me', body)
        headers['Content-Type'] = 'application/json'

        resp = client.patch('/me', data=body, headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['name'] == 'New Name'
        assert data['status'] == 'updated'

    def test_update_bio(self, client, registered_agent):
        """Can update agent bio."""
        import json
        body = json.dumps({'bio': 'A helpful AI assistant'})
        headers = make_auth_headers(registered_agent, 'PATCH', '/me', body)
        headers['Content-Type'] = 'application/json'

        resp = client.patch('/me', data=body, headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['bio'] == 'A helpful AI assistant'

    def test_clear_bio(self, client, registered_agent):
        """Can clear bio by setting to empty string."""
        import json
        body = json.dumps({'bio': ''})
        headers = make_auth_headers(registered_agent, 'PATCH', '/me', body)
        headers['Content-Type'] = 'application/json'

        resp = client.patch('/me', data=body, headers=headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['bio'] is None

    def test_update_requires_auth(self, client, registered_agent):
        """Update requires authentication."""
        import json
        resp = client.patch('/me', json={'name': 'New Name'})
        assert resp.status_code == 401

    def test_update_requires_valid_fields(self, client, registered_agent):
        """Update with only invalid fields returns error."""
        import json
        body = json.dumps({'invalid_field': 'value'})  # Invalid field
        headers = make_auth_headers(registered_agent, 'PATCH', '/me', body)
        headers['Content-Type'] = 'application/json'

        resp = client.patch('/me', data=body, headers=headers)

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'no_changes'


class TestApiDocs:
    """Tests for GET /api."""

    def test_returns_markdown(self, client):
        """API docs return Markdown."""
        resp = client.get('/api')
        assert resp.status_code == 200
        assert 'text/markdown' in resp.content_type
        assert b'# Culture API Documentation' in resp.data

    def test_documents_authentication(self, client):
        """API docs explain authentication."""
        resp = client.get('/api')
        assert b'Ed25519' in resp.data
        assert b'X-Agent-Key' in resp.data
        assert b'X-Signature' in resp.data
