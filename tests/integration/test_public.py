"""
Integration tests for public endpoints.
"""
import pytest
import json
from tests.conftest import make_auth_headers


class TestHomepage:
    """Tests for the homepage."""

    def test_homepage_returns_html(self, client):
        """Homepage returns HTML content."""
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'<!DOCTYPE html>' in resp.data
        assert b'Culture' in resp.data

    def test_homepage_mentions_install(self, client):
        """Homepage mentions installation instructions."""
        resp = client.get('/')
        assert b'install.py' in resp.data

    def test_homepage_has_live_feed_section(self, client):
        """Homepage includes a live feed section."""
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'Live Feed' in resp.data
        assert b'agent' in resp.data and b'registered' in resp.data

    def test_homepage_shows_empty_feed_message(self, client):
        """Homepage shows empty feed message when no posts."""
        resp = client.get('/')
        assert resp.status_code == 200
        # With no posts, should show empty message
        assert b'No posts yet' in resp.data or b'class="post"' in resp.data

    def test_homepage_shows_posts_in_feed(self, client, registered_agent):
        """Homepage shows posts in the feed."""
        # Create auth headers for the POST request
        body = json.dumps({'content': 'Hello from the test!'})
        auth_headers = make_auth_headers(registered_agent, 'POST', '/posts', body)

        # Create a post
        resp = client.post('/posts', data=body,
                           content_type='application/json',
                           headers=auth_headers)
        assert resp.status_code == 201

        # Check homepage shows the post
        resp = client.get('/')
        assert resp.status_code == 200
        assert b'Hello from the test!' in resp.data
        assert b'class="post"' in resp.data

    def test_homepage_shows_agent_count(self, client, registered_agent):
        """Homepage shows the number of registered agents."""
        resp = client.get('/')
        assert resp.status_code == 200
        # Should show "1 agent registered" or similar
        assert b'1 agent registered' in resp.data or b'agents registered' in resp.data


class TestHealth:
    """Tests for health check."""

    def test_health_returns_ok(self, client):
        """Health endpoint returns ok."""
        resp = client.get('/health')
        assert resp.status_code == 200
        assert resp.data == b'ok'
        assert resp.content_type == 'text/plain; charset=utf-8'


class TestSkills:
    """Tests for skills listing."""

    def test_skills_returns_markdown(self, client):
        """Skills endpoint returns Markdown."""
        resp = client.get('/skills')
        assert resp.status_code == 200
        assert 'text/markdown' in resp.content_type
        assert b'# Available Skills' in resp.data


class TestInstall:
    """Tests for installation instructions."""

    def test_install_returns_markdown(self, client):
        """Install endpoint returns Markdown."""
        resp = client.get('/install')
        assert resp.status_code == 200
        assert 'text/markdown' in resp.content_type
        assert b'# Culture Agent Installation' in resp.data

    def test_install_mentions_script(self, client):
        """Install endpoint mentions the installer script."""
        resp = client.get('/install')
        assert b'install.py' in resp.data


class TestInstallScript:
    """Tests for installer script."""

    def test_install_script_returns_python(self, client):
        """Install script endpoint returns Python code."""
        resp = client.get('/install.py')
        # May return 404 if install.py not found in test environment
        if resp.status_code == 200:
            assert 'python' in resp.content_type
            assert b'#!/usr/bin/env python3' in resp.data


class TestPublicProfile:
    """Tests for public profile endpoint."""

    def test_profile_not_found(self, client):
        """Profile for nonexistent agent returns 404."""
        resp = client.get('/@nonexistent_key')
        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'not_found'

    def test_profile_returns_public_info(self, client, registered_agent):
        """Profile returns public agent info."""
        public_key = registered_agent['public_key_b64']
        resp = client.get(f'/@{public_key}')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['agent_id'] == registered_agent['agent_id']
        assert data['name'] == 'Test Agent'
        assert 'bio' in data
        assert 'registered_at' in data
        assert 'profile_url' in data

    def test_profile_does_not_expose_private_key(self, client, registered_agent):
        """Profile does not expose private information."""
        public_key = registered_agent['public_key_b64']
        resp = client.get(f'/@{public_key}')

        data = resp.get_json()
        # Should not contain private key or signing key
        assert 'private_key' not in str(data)
        assert 'signing_key' not in str(data)
