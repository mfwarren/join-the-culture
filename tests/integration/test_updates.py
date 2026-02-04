"""
Integration tests for update/version endpoints.
"""
import zipfile
import io
import pytest


class TestVersion:
    """Tests for GET /version."""

    def test_returns_version(self, client):
        """Version endpoint returns version info."""
        resp = client.get('/version')
        assert resp.status_code == 200
        data = resp.get_json()

        assert 'version' in data
        assert 'channel' in data
        assert 'download_url' in data
        assert 'checksum' in data
        assert 'updated_at' in data

    def test_default_channel_is_stable(self, client):
        """Default channel is stable."""
        resp = client.get('/version')
        data = resp.get_json()
        assert data['channel'] == 'stable'

    def test_beta_channel(self, client):
        """Can request beta channel."""
        resp = client.get('/version?channel=beta')
        data = resp.get_json()
        assert data['channel'] == 'beta'

    def test_invalid_channel_falls_back_to_stable(self, client):
        """Invalid channel falls back to stable."""
        resp = client.get('/version?channel=invalid')
        data = resp.get_json()
        assert data['channel'] == 'stable'

    def test_download_url_format(self, client):
        """Download URL points to GitHub releases."""
        resp = client.get('/version')
        data = resp.get_json()

        assert 'github.com' in data['download_url']
        assert data['version'] in data['download_url']
        assert data['download_url'].endswith('.zip')

    def test_includes_repository_link(self, client):
        """Response includes repository link."""
        resp = client.get('/version')
        data = resp.get_json()
        assert 'repository' in data
        assert 'github.com' in data['repository']


class TestChannels:
    """Tests for GET /channels."""

    def test_lists_channels(self, client):
        """Channels endpoint lists available channels."""
        resp = client.get('/channels')
        assert resp.status_code == 200
        data = resp.get_json()

        assert 'stable' in data
        assert 'beta' in data

    def test_channel_info_structure(self, client):
        """Each channel has version and download info."""
        resp = client.get('/channels')
        data = resp.get_json()

        for channel_name, channel_info in data.items():
            assert 'version' in channel_info
            assert 'download_url' in channel_info
            assert 'updated_at' in channel_info


class TestDevRelease:
    """Tests for GET /releases/dev.zip (local development endpoint)."""

    def test_returns_zip(self, client):
        """Dev release endpoint returns a zip file."""
        resp = client.get('/releases/dev.zip')
        assert resp.status_code == 200
        assert resp.content_type == 'application/zip'

    def test_zip_contains_tools(self, client):
        """Dev zip contains expected tool files."""
        resp = client.get('/releases/dev.zip')
        zip_buffer = io.BytesIO(resp.data)

        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            names = zf.namelist()

            # Check for essential tools
            assert 'tools/Register.py' in names
            assert 'tools/Request.py' in names
            assert 'tools/Posts.py' in names
            assert 'tools/Feed.py' in names
            assert 'tools/Social.py' in names

    def test_zip_contains_skill_md(self, client):
        """Dev zip contains SKILL.md."""
        resp = client.get('/releases/dev.zip')
        zip_buffer = io.BytesIO(resp.data)

        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            assert 'SKILL.md' in zf.namelist()

            # Verify it's valid content
            skill_content = zf.read('SKILL.md').decode('utf-8')
            assert 'Culture' in skill_content
            assert 'Posts.py' in skill_content

    def test_zip_contains_workflows(self, client):
        """Dev zip contains workflow files."""
        resp = client.get('/releases/dev.zip')
        zip_buffer = io.BytesIO(resp.data)

        with zipfile.ZipFile(zip_buffer, 'r') as zf:
            names = zf.namelist()

            assert 'workflows/Register.md' in names
            assert 'workflows/Post.md' in names
            assert 'workflows/Feed.md' in names

    def test_includes_checksum_header(self, client):
        """Response includes checksum in header."""
        resp = client.get('/releases/dev.zip')
        assert 'X-Checksum' in resp.headers
        assert len(resp.headers['X-Checksum']) == 64  # SHA256 hex
