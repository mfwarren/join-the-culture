"""
Integration tests for search API endpoints.
"""

import pytest

from app.blueprints import search as search_blueprint


class TestSearchApiErrors:
    """Tests for search API error handling."""

    def test_search_posts_does_not_leak_internal_error_details(self, client, monkeypatch):
        """POST search failures return generic 500 error payload."""

        def _raise(*args, **kwargs):
            raise RuntimeError("database DSN leaked: postgres://secret@localhost/db")

        monkeypatch.setattr(search_blueprint.search_service, 'search_posts', _raise)

        resp = client.get('/search/posts?q=hello')

        assert resp.status_code == 500
        data = resp.get_json()
        assert data['error'] == 'search_failed'
        assert data['message'] == 'Search is temporarily unavailable'
        assert 'details' not in data
        assert 'secret' not in str(data).lower()

    def test_search_agents_does_not_leak_internal_error_details(self, client, monkeypatch):
        """Agent search failures return generic 500 error payload."""

        def _raise(*args, **kwargs):
            raise RuntimeError("openai api key: sk-test-secret")

        monkeypatch.setattr(search_blueprint.search_service, 'search_agents', _raise)

        resp = client.get('/search/agents?q=hello')

        assert resp.status_code == 500
        data = resp.get_json()
        assert data['error'] == 'search_failed'
        assert data['message'] == 'Search is temporarily unavailable'
        assert 'details' not in data
        assert 'secret' not in str(data).lower()

    def test_search_health_does_not_leak_internal_error_details(self, client, monkeypatch):
        """Search health failures return generic 503 error payload."""

        class _FailingEmbeddingService:
            @property
            def model(self):
                raise RuntimeError("hf_token=super-secret")

        monkeypatch.setattr(
            search_blueprint.search_service,
            'embedding_service',
            _FailingEmbeddingService()
        )

        resp = client.get('/search/health')

        assert resp.status_code == 503
        data = resp.get_json()
        assert data['status'] == 'unhealthy'
        assert data['error'] == 'search_unhealthy'
        assert data['message'] == 'Search service health check failed'
        assert 'secret' not in str(data).lower()
