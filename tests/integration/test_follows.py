"""
Integration tests for follows endpoints.
"""
import json
import pytest
from nacl.signing import SigningKey
import base64

from tests.conftest import make_auth_headers
from app.models import agent_store


def create_second_agent(client, app):
    """Helper to create a second registered agent for follow tests."""
    with app.app_context():
        # Generate a new keypair
        signing_key = SigningKey.generate()
        private_key = signing_key.encode()
        public_key = signing_key.verify_key.encode()
        private_key_b64 = base64.b64encode(private_key).decode()
        public_key_b64 = base64.b64encode(public_key).decode()

        # Request challenge
        resp = client.post('/register', json={
            'public_key': public_key_b64,
            'name': 'Second Agent'
        })
        challenge = resp.get_json()['challenge']

        # Sign and verify
        signature = signing_key.sign(challenge.encode()).signature
        signature_b64 = base64.b64encode(signature).decode()

        verify_resp = client.post('/register/verify', json={
            'public_key': public_key_b64,
            'signature': signature_b64
        })

        agent_id = verify_resp.get_json()['agent_id']

        return {
            'agent_id': agent_id,
            'public_key_b64': public_key_b64,
            'private_key_b64': private_key_b64,
            'signing_key': signing_key,
            'name': 'Second Agent'
        }


class TestFollow:
    """Tests for POST /follow/<agent_id>."""

    def test_follow_agent(self, client, registered_agent, app):
        """Can follow another agent."""
        second = create_second_agent(client, app)

        headers = make_auth_headers(registered_agent, 'POST', f'/follow/{second["agent_id"]}')
        resp = client.post(f'/follow/{second["agent_id"]}', headers=headers)

        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'following'
        assert data['following']['agent_id'] == second['agent_id']

    def test_cannot_follow_self(self, client, registered_agent):
        """Cannot follow yourself."""
        headers = make_auth_headers(registered_agent, 'POST', f'/follow/{registered_agent["agent_id"]}')
        resp = client.post(f'/follow/{registered_agent["agent_id"]}', headers=headers)

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'invalid_action'

    def test_follow_requires_auth(self, client, registered_agent, app):
        """Following requires authentication."""
        second = create_second_agent(client, app)
        resp = client.post(f'/follow/{second["agent_id"]}')
        assert resp.status_code == 401

    def test_follow_nonexistent_agent(self, client, registered_agent):
        """Cannot follow nonexistent agent."""
        headers = make_auth_headers(registered_agent, 'POST', '/follow/nonexistent')
        resp = client.post('/follow/nonexistent', headers=headers)

        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'not_found'


class TestUnfollow:
    """Tests for DELETE /follow/<agent_id>."""

    def test_unfollow_agent(self, client, registered_agent, app):
        """Can unfollow an agent."""
        second = create_second_agent(client, app)

        # First follow
        follow_headers = make_auth_headers(registered_agent, 'POST', f'/follow/{second["agent_id"]}')
        client.post(f'/follow/{second["agent_id"]}', headers=follow_headers)

        # Then unfollow
        unfollow_headers = make_auth_headers(registered_agent, 'DELETE', f'/follow/{second["agent_id"]}')
        resp = client.delete(f'/follow/{second["agent_id"]}', headers=unfollow_headers)

        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'unfollowed'

    def test_unfollow_not_following(self, client, registered_agent, app):
        """Cannot unfollow someone you're not following."""
        second = create_second_agent(client, app)

        headers = make_auth_headers(registered_agent, 'DELETE', f'/follow/{second["agent_id"]}')
        resp = client.delete(f'/follow/{second["agent_id"]}', headers=headers)

        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'not_found'


class TestFollowing:
    """Tests for GET /following."""

    def test_get_my_following(self, client, registered_agent, app):
        """Can get list of agents I'm following."""
        second = create_second_agent(client, app)

        # Follow them
        follow_headers = make_auth_headers(registered_agent, 'POST', f'/follow/{second["agent_id"]}')
        client.post(f'/follow/{second["agent_id"]}', headers=follow_headers)

        # Get following
        get_headers = make_auth_headers(registered_agent, 'GET', '/following')
        resp = client.get('/following', headers=get_headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 1
        assert data['following'][0]['agent_id'] == second['agent_id']


class TestFollowers:
    """Tests for GET /followers."""

    def test_get_my_followers(self, client, registered_agent, app):
        """Can get list of my followers."""
        second = create_second_agent(client, app)

        # Second agent follows first
        follow_headers = make_auth_headers(second, 'POST', f'/follow/{registered_agent["agent_id"]}')
        client.post(f'/follow/{registered_agent["agent_id"]}', headers=follow_headers)

        # First agent gets their followers
        get_headers = make_auth_headers(registered_agent, 'GET', '/followers')
        resp = client.get('/followers', headers=get_headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 1
        assert data['followers'][0]['agent_id'] == second['agent_id']


class TestPublicFollowEndpoints:
    """Tests for public follow endpoints."""

    def test_get_agent_followers(self, client, registered_agent, app):
        """Can get followers of any agent (public)."""
        second = create_second_agent(client, app)

        # Second follows first
        follow_headers = make_auth_headers(second, 'POST', f'/follow/{registered_agent["agent_id"]}')
        client.post(f'/follow/{registered_agent["agent_id"]}', headers=follow_headers)

        # Get followers (no auth needed)
        resp = client.get(f'/agents/{registered_agent["agent_id"]}/followers')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 1

    def test_get_agent_following(self, client, registered_agent, app):
        """Can get who an agent follows (public)."""
        second = create_second_agent(client, app)

        # First follows second
        follow_headers = make_auth_headers(registered_agent, 'POST', f'/follow/{second["agent_id"]}')
        client.post(f'/follow/{second["agent_id"]}', headers=follow_headers)

        # Get following (no auth needed)
        resp = client.get(f'/agents/{registered_agent["agent_id"]}/following')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 1
        assert data['following'][0]['agent_id'] == second['agent_id']

    def test_get_nonexistent_agent_followers(self, client):
        """Returns 404 for nonexistent agent."""
        resp = client.get('/agents/nonexistent/followers')
        assert resp.status_code == 404
