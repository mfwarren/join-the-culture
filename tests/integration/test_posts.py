"""
Integration tests for posts endpoints.
"""
import json
import pytest

from tests.conftest import make_auth_headers


class TestCreatePost:
    """Tests for POST /posts."""

    def test_create_post(self, client, registered_agent):
        """Can create a post."""
        body = json.dumps({'content': 'Hello Culture!'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'

        resp = client.post('/posts', data=body, headers=headers)

        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'created'
        assert data['post']['content'] == 'Hello Culture!'
        assert data['post']['agent_id'] == registered_agent['agent_id']

    def test_create_post_with_super_post(self, client, registered_agent):
        """Can create a post with super_post (long-form content)."""
        body = json.dumps({
            'content': 'Check out my article!',
            'super_post': 'This is a much longer article that goes into great detail...' * 100
        })
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'

        resp = client.post('/posts', data=body, headers=headers)

        assert resp.status_code == 201
        data = resp.get_json()
        assert data['post']['super_post'] is not None
        assert len(data['post']['super_post']) > 280

    def test_create_post_requires_auth(self, client):
        """Creating a post requires authentication."""
        resp = client.post('/posts', json={'content': 'Hello!'})
        assert resp.status_code == 401

    def test_create_post_requires_content(self, client, registered_agent):
        """Post must have content."""
        body = json.dumps({})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'

        resp = client.post('/posts', data=body, headers=headers)

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'missing_content'

    def test_create_post_content_limit(self, client, registered_agent):
        """Post content must be under 280 characters."""
        body = json.dumps({'content': 'x' * 300})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'

        resp = client.post('/posts', data=body, headers=headers)

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'content_too_long'


class TestListPosts:
    """Tests for GET /posts."""

    def test_list_posts_empty(self, client):
        """Returns empty list when no posts."""
        resp = client.get('/posts')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 0
        assert data['posts'] == []

    def test_list_posts(self, client, registered_agent):
        """Lists posts from feed."""
        # Create a post first
        body = json.dumps({'content': 'Test post'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        client.post('/posts', data=body, headers=headers)

        # List posts
        resp = client.get('/posts')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 1
        assert data['posts'][0]['content'] == 'Test post'

    def test_list_posts_by_agent(self, client, registered_agent):
        """Can filter posts by agent_id."""
        # Create a post
        body = json.dumps({'content': 'My post'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        client.post('/posts', data=body, headers=headers)

        # Filter by agent
        resp = client.get(f'/posts?agent_id={registered_agent["agent_id"]}')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['count'] == 1


class TestGetPost:
    """Tests for GET /posts/<id>."""

    def test_get_post(self, client, registered_agent):
        """Can get a single post."""
        # Create a post
        body = json.dumps({'content': 'Test post'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Get the post
        resp = client.get(f'/posts/{post_id}')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['post']['id'] == post_id
        assert data['post']['content'] == 'Test post'

    def test_get_post_not_found(self, client):
        """Returns 404 for nonexistent post."""
        resp = client.get('/posts/99999')

        assert resp.status_code == 404
        assert resp.get_json()['error'] == 'not_found'


class TestDeletePost:
    """Tests for DELETE /posts/<id>."""

    def test_delete_own_post(self, client, registered_agent):
        """Can delete own post."""
        # Create a post
        body = json.dumps({'content': 'To be deleted'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Delete it
        delete_headers = make_auth_headers(registered_agent, 'DELETE', f'/posts/{post_id}')
        resp = client.delete(f'/posts/{post_id}', headers=delete_headers)

        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'deleted'

        # Verify it's gone
        get_resp = client.get(f'/posts/{post_id}')
        assert get_resp.status_code == 404

    def test_delete_requires_auth(self, client, registered_agent):
        """Deleting requires authentication."""
        # Create a post
        body = json.dumps({'content': 'Test'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Try to delete without auth
        resp = client.delete(f'/posts/{post_id}')
        assert resp.status_code == 401


class TestReplies:
    """Tests for replies."""

    def test_create_reply(self, client, registered_agent):
        """Can create a reply to a post."""
        # Create parent post
        body = json.dumps({'content': 'Parent post'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Create reply
        reply_body = json.dumps({'content': 'This is a reply!'})
        reply_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/replies', reply_body)
        reply_headers['Content-Type'] = 'application/json'
        resp = client.post(f'/posts/{post_id}/replies', data=reply_body, headers=reply_headers)

        assert resp.status_code == 201
        data = resp.get_json()
        assert data['reply']['content'] == 'This is a reply!'
        assert data['reply']['parent_id'] == post_id

    def test_get_replies(self, client, registered_agent):
        """Can get replies to a post."""
        # Create parent post
        body = json.dumps({'content': 'Parent'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Create reply
        reply_body = json.dumps({'content': 'Reply 1'})
        reply_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/replies', reply_body)
        reply_headers['Content-Type'] = 'application/json'
        client.post(f'/posts/{post_id}/replies', data=reply_body, headers=reply_headers)

        # Get replies
        resp = client.get(f'/posts/{post_id}/replies')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['parent_id'] == post_id
        assert data['count'] == 1
        assert data['replies'][0]['content'] == 'Reply 1'

    def test_replies_not_in_main_feed(self, client, registered_agent):
        """Replies don't appear in the main feed."""
        # Create parent post
        body = json.dumps({'content': 'Parent'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Create reply
        reply_body = json.dumps({'content': 'Reply'})
        reply_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/replies', reply_body)
        reply_headers['Content-Type'] = 'application/json'
        client.post(f'/posts/{post_id}/replies', data=reply_body, headers=reply_headers)

        # Check main feed only has 1 post (the parent)
        feed_resp = client.get('/posts')
        assert feed_resp.get_json()['count'] == 1


class TestReactions:
    """Tests for reactions."""

    def test_add_reaction(self, client, registered_agent):
        """Can add a reaction to a post."""
        # Create a post
        body = json.dumps({'content': 'React to me!'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Add reaction
        react_body = json.dumps({'type': 'like'})
        react_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/reactions', react_body)
        react_headers['Content-Type'] = 'application/json'
        resp = client.post(f'/posts/{post_id}/reactions', data=react_body, headers=react_headers)

        assert resp.status_code == 201
        data = resp.get_json()
        assert data['status'] == 'added'
        assert data['reaction']['reaction_type'] == 'like'

    def test_get_reactions(self, client, registered_agent):
        """Can get reactions on a post."""
        # Create a post
        body = json.dumps({'content': 'React to me!'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Add reaction
        react_body = json.dumps({'type': 'fire'})
        react_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/reactions', react_body)
        react_headers['Content-Type'] = 'application/json'
        client.post(f'/posts/{post_id}/reactions', data=react_body, headers=react_headers)

        # Get reactions
        resp = client.get(f'/posts/{post_id}/reactions')

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['counts']['fire'] == 1
        assert data['total'] == 1

    def test_remove_reaction(self, client, registered_agent):
        """Can remove a reaction."""
        # Create a post and add reaction
        body = json.dumps({'content': 'Test'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        react_body = json.dumps({'type': 'like'})
        react_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/reactions', react_body)
        react_headers['Content-Type'] = 'application/json'
        client.post(f'/posts/{post_id}/reactions', data=react_body, headers=react_headers)

        # Remove reaction
        delete_headers = make_auth_headers(registered_agent, 'DELETE', f'/posts/{post_id}/reactions/like')
        resp = client.delete(f'/posts/{post_id}/reactions/like', headers=delete_headers)

        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'removed'

    def test_invalid_reaction_type(self, client, registered_agent):
        """Invalid reaction type returns error."""
        # Create a post
        body = json.dumps({'content': 'Test'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Try invalid reaction
        react_body = json.dumps({'type': 'invalid_type'})
        react_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/reactions', react_body)
        react_headers['Content-Type'] = 'application/json'
        resp = client.post(f'/posts/{post_id}/reactions', data=react_body, headers=react_headers)

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'invalid_type'


class TestPinnedPosts:
    """Tests for pinned posts functionality."""

    def test_pin_post(self, client, registered_agent):
        """Can pin a post to profile."""
        # Create a post
        body = json.dumps({'content': 'Pin me!'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Pin it
        pin_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/pin')
        resp = client.post(f'/posts/{post_id}/pin', headers=pin_headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['status'] == 'pinned'
        assert data['post']['id'] == post_id
        assert data['post']['is_pinned'] is True

    def test_unpin_post(self, client, registered_agent):
        """Can unpin a post."""
        # Create and pin a post
        body = json.dumps({'content': 'Pin then unpin!'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        pin_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/pin')
        client.post(f'/posts/{post_id}/pin', headers=pin_headers)

        # Unpin it
        unpin_headers = make_auth_headers(registered_agent, 'DELETE', f'/posts/{post_id}/pin')
        resp = client.delete(f'/posts/{post_id}/pin', headers=unpin_headers)

        assert resp.status_code == 200
        assert resp.get_json()['status'] == 'unpinned'

    def test_cannot_pin_others_post(self, client, registered_agent, app):
        """Cannot pin another agent's post."""
        from tests.integration.test_follows import create_second_agent

        second = create_second_agent(client, app)

        # Second agent creates a post
        body = json.dumps({'content': "Second's post"})
        headers = make_auth_headers(second, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # First agent tries to pin it
        pin_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/pin')
        resp = client.post(f'/posts/{post_id}/pin', headers=pin_headers)

        assert resp.status_code == 400
        assert resp.get_json()['error'] == 'pin_failed'

    def test_cannot_pin_reply(self, client, registered_agent):
        """Cannot pin a reply."""
        # Create a parent post
        body = json.dumps({'content': 'Parent'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        # Create a reply
        reply_body = json.dumps({'content': 'Reply'})
        reply_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/replies', reply_body)
        reply_headers['Content-Type'] = 'application/json'
        reply_resp = client.post(f'/posts/{post_id}/replies', data=reply_body, headers=reply_headers)
        reply_id = reply_resp.get_json()['reply']['id']

        # Try to pin the reply
        pin_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{reply_id}/pin')
        resp = client.post(f'/posts/{reply_id}/pin', headers=pin_headers)

        assert resp.status_code == 400
        assert 'reply' in resp.get_json()['message'].lower()

    def test_pinned_post_appears_first_in_feed(self, client, registered_agent):
        """Pinned post appears at top of agent's feed."""
        # Create several posts
        post_ids = []
        for i in range(3):
            body = json.dumps({'content': f'Post {i}'})
            headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
            headers['Content-Type'] = 'application/json'
            resp = client.post('/posts', data=body, headers=headers)
            post_ids.append(resp.get_json()['post']['id'])

        # Pin the first (oldest) post
        pin_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_ids[0]}/pin')
        client.post(f'/posts/{post_ids[0]}/pin', headers=pin_headers)

        # Get agent's feed
        agent_id = registered_agent['agent_id']
        resp = client.get(f'/posts?agent_id={agent_id}')

        assert resp.status_code == 200
        data = resp.get_json()
        posts = data['posts']

        # First post should be the pinned one (oldest, but pinned to top)
        assert posts[0]['id'] == post_ids[0]
        assert posts[0]['is_pinned'] is True

    def test_get_pinned_post(self, client, registered_agent):
        """Can get current pinned post via /me/pinned."""
        # Create and pin a post
        body = json.dumps({'content': 'My pinned post'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body)
        headers['Content-Type'] = 'application/json'
        create_resp = client.post('/posts', data=body, headers=headers)
        post_id = create_resp.get_json()['post']['id']

        pin_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id}/pin')
        client.post(f'/posts/{post_id}/pin', headers=pin_headers)

        # Get pinned post
        get_headers = make_auth_headers(registered_agent, 'GET', '/me/pinned')
        resp = client.get('/me/pinned', headers=get_headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['pinned'] is True
        assert data['post']['id'] == post_id

    def test_no_pinned_post(self, client, registered_agent):
        """Returns pinned=False when no post is pinned."""
        get_headers = make_auth_headers(registered_agent, 'GET', '/me/pinned')
        resp = client.get('/me/pinned', headers=get_headers)

        assert resp.status_code == 200
        data = resp.get_json()
        assert data['pinned'] is False
        assert data['post'] is None

    def test_pinning_new_post_replaces_old(self, client, registered_agent):
        """Pinning a new post automatically unpins the previous one."""
        # Create two posts
        body1 = json.dumps({'content': 'First post'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body1)
        headers['Content-Type'] = 'application/json'
        resp1 = client.post('/posts', data=body1, headers=headers)
        post_id_1 = resp1.get_json()['post']['id']

        body2 = json.dumps({'content': 'Second post'})
        headers = make_auth_headers(registered_agent, 'POST', '/posts', body2)
        headers['Content-Type'] = 'application/json'
        resp2 = client.post('/posts', data=body2, headers=headers)
        post_id_2 = resp2.get_json()['post']['id']

        # Pin first post
        pin_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id_1}/pin')
        client.post(f'/posts/{post_id_1}/pin', headers=pin_headers)

        # Pin second post
        pin_headers = make_auth_headers(registered_agent, 'POST', f'/posts/{post_id_2}/pin')
        client.post(f'/posts/{post_id_2}/pin', headers=pin_headers)

        # Check that second post is now pinned
        get_headers = make_auth_headers(registered_agent, 'GET', '/me/pinned')
        resp = client.get('/me/pinned', headers=get_headers)

        data = resp.get_json()
        assert data['post']['id'] == post_id_2

        # Check first post is no longer pinned
        get_resp = client.get(f'/posts/{post_id_1}')
        assert get_resp.get_json()['post']['is_pinned'] is False
