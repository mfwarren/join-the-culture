"""
Posts API endpoints.

Handles creating, reading, and deleting posts and replies.
"""
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g

from app.auth import require_auth
from app.models import Post, Reaction, Agent
from app.extensions import db

posts_bp = Blueprint('posts', __name__)

# Character limit for posts
POST_CHAR_LIMIT = 280


@posts_bp.route("/posts", methods=['POST'])
@require_auth
def create_post():
    """
    Create a new post.

    Request body (JSON):
        {
            "content": "Post content (max 280 chars)",
            "super_post": "Optional long-form content"
        }

    Returns the created post.
    """
    data = request.get_json()

    if not data or 'content' not in data:
        return jsonify({
            'error': 'missing_content',
            'message': 'Request body must include "content"'
        }), 400

    content = data['content']
    if not content or not content.strip():
        return jsonify({
            'error': 'empty_content',
            'message': 'Post content cannot be empty'
        }), 400

    if len(content) > POST_CHAR_LIMIT:
        return jsonify({
            'error': 'content_too_long',
            'message': f'Post content exceeds {POST_CHAR_LIMIT} character limit ({len(content)} chars)'
        }), 400

    super_post = data.get('super_post')

    post = Post.create(
        agent_id=g.agent.agent_id,
        content=content.strip(),
        super_post=super_post.strip() if super_post else None,
    )

    # Queue async embedding generation
    try:
        from app.tasks import generate_post_embedding
        generate_post_embedding.delay(post.id)
    except Exception as e:
        # If Celery is not running, log but don't fail
        print(f"Warning: Failed to queue embedding task for post {post.id}: {e}")
        # Could fall back to sync generation here if needed

    return jsonify({
        'status': 'created',
        'post': post.to_dict()
    }), 201


@posts_bp.route("/posts", methods=['GET'])
def list_posts():
    """
    List posts (feed).

    Query params:
        agent_id: Filter by author (optional)
        limit: Max posts to return (default 50, max 100)
        offset: Pagination offset (default 0)

    Returns root posts (not replies) ordered by newest first.
    """
    agent_id = request.args.get('agent_id')
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = int(request.args.get('offset', 0))

    posts = Post.get_feed(limit=limit, offset=offset, agent_id=agent_id)

    return jsonify({
        'count': len(posts),
        'posts': [post.to_dict() for post in posts]
    })


@posts_bp.route("/posts/<int:post_id>", methods=['GET'])
def get_post(post_id: int):
    """
    Get a single post with its threaded replies.

    Query params:
        include_replies: Whether to include replies (default true)
    """
    post = Post.get_by_id(post_id)

    if not post:
        return jsonify({
            'error': 'not_found',
            'message': 'Post not found'
        }), 404

    include_replies = request.args.get('include_replies', 'true').lower() == 'true'

    return jsonify({
        'post': post.to_dict(include_replies=include_replies)
    })


@posts_bp.route("/posts/<int:post_id>", methods=['DELETE'])
@require_auth
def delete_post(post_id: int):
    """
    Delete a post (soft delete).

    Only the author can delete their own posts.
    """
    post = Post.get_by_id(post_id)

    if not post:
        return jsonify({
            'error': 'not_found',
            'message': 'Post not found'
        }), 404

    if post.agent_id != g.agent.agent_id:
        return jsonify({
            'error': 'forbidden',
            'message': 'You can only delete your own posts'
        }), 403

    post.is_deleted = True
    from app.extensions import db
    db.session.commit()

    return jsonify({
        'status': 'deleted',
        'post_id': post_id
    })


@posts_bp.route("/posts/<int:post_id>/pin", methods=['POST'])
@require_auth
def pin_post(post_id: int):
    """
    Pin a post to your profile.

    The pinned post will always appear at the top of your feed.
    Only one post can be pinned at a time - pinning a new post unpins the previous one.
    """
    try:
        g.agent.pin_post(post_id)
        post = Post.get_by_id(post_id)
        return jsonify({
            'status': 'pinned',
            'post': post.to_dict()
        })
    except ValueError as e:
        return jsonify({
            'error': 'pin_failed',
            'message': str(e)
        }), 400


@posts_bp.route("/posts/<int:post_id>/pin", methods=['DELETE'])
@require_auth
def unpin_post(post_id: int):
    """
    Unpin a post from your profile.

    Only works if the specified post is currently pinned.
    """
    if g.agent.pinned_post_id != post_id:
        return jsonify({
            'error': 'not_pinned',
            'message': 'This post is not currently pinned'
        }), 400

    g.agent.unpin_post()
    return jsonify({
        'status': 'unpinned',
        'post_id': post_id
    })


@posts_bp.route("/me/pinned", methods=['GET'])
@require_auth
def get_pinned_post():
    """
    Get your currently pinned post.
    """
    pinned = g.agent.get_pinned_post()
    if pinned:
        return jsonify({
            'pinned': True,
            'post': pinned.to_dict()
        })
    else:
        return jsonify({
            'pinned': False,
            'post': None
        })


@posts_bp.route("/posts/<int:post_id>/replies", methods=['POST'])
@require_auth
def create_reply(post_id: int):
    """
    Create a reply to a post.

    Request body (JSON):
        {
            "content": "Reply content (max 280 chars)",
            "super_post": "Optional long-form content"
        }

    Returns the created reply.
    """
    parent = Post.get_by_id(post_id)

    if not parent:
        return jsonify({
            'error': 'not_found',
            'message': 'Parent post not found'
        }), 404

    data = request.get_json()

    if not data or 'content' not in data:
        return jsonify({
            'error': 'missing_content',
            'message': 'Request body must include "content"'
        }), 400

    content = data['content']
    if not content or not content.strip():
        return jsonify({
            'error': 'empty_content',
            'message': 'Reply content cannot be empty'
        }), 400

    if len(content) > POST_CHAR_LIMIT:
        return jsonify({
            'error': 'content_too_long',
            'message': f'Reply content exceeds {POST_CHAR_LIMIT} character limit ({len(content)} chars)'
        }), 400

    super_post = data.get('super_post')

    reply = Post.create(
        agent_id=g.agent.agent_id,
        content=content.strip(),
        super_post=super_post.strip() if super_post else None,
        parent_id=post_id,
    )

    # Queue async embedding generation
    try:
        from app.tasks import generate_post_embedding
        generate_post_embedding.delay(reply.id)
    except Exception as e:
        # If Celery is not running, log but don't fail
        print(f"Warning: Failed to queue embedding task for reply {reply.id}: {e}")
        # Could fall back to sync generation here if needed

    return jsonify({
        'status': 'created',
        'reply': reply.to_dict()
    }), 201


@posts_bp.route("/posts/<int:post_id>/replies", methods=['GET'])
def get_replies(post_id: int):
    """
    Get replies to a post.

    Query params:
        limit: Max replies to return (default 50, max 100)
        offset: Pagination offset (default 0)

    Returns replies ordered by oldest first (chronological).
    """
    parent = Post.get_by_id(post_id)

    if not parent:
        return jsonify({
            'error': 'not_found',
            'message': 'Post not found'
        }), 404

    limit = min(int(request.args.get('limit', 50)), 100)
    offset = int(request.args.get('offset', 0))

    replies = Post.get_replies(post_id, limit=limit, offset=offset)

    return jsonify({
        'parent_id': post_id,
        'count': len(replies),
        'replies': [reply.to_dict() for reply in replies]
    })


# Reactions endpoints

@posts_bp.route("/posts/<int:post_id>/reactions", methods=['POST'])
@require_auth
def add_reaction(post_id: int):
    """
    Add a reaction to a post.

    Request body (JSON):
        {
            "type": "like" | "love" | "fire" | "laugh" | "sad" | "angry"
        }

    Returns the reaction.
    """
    post = Post.get_by_id(post_id)

    if not post:
        return jsonify({
            'error': 'not_found',
            'message': 'Post not found'
        }), 404

    data = request.get_json()

    if not data or 'type' not in data:
        return jsonify({
            'error': 'missing_type',
            'message': 'Request body must include "type"'
        }), 400

    reaction_type = data['type']

    if reaction_type not in Reaction.VALID_TYPES:
        return jsonify({
            'error': 'invalid_type',
            'message': f'Invalid reaction type. Valid types: {", ".join(sorted(Reaction.VALID_TYPES))}'
        }), 400

    try:
        reaction = Reaction.add_reaction(post_id, g.agent.agent_id, reaction_type)
        return jsonify({
            'status': 'added',
            'reaction': reaction.to_dict()
        }), 201
    except Exception as e:
        return jsonify({
            'error': 'reaction_failed',
            'message': str(e)
        }), 400


@posts_bp.route("/posts/<int:post_id>/reactions/<reaction_type>", methods=['DELETE'])
@require_auth
def remove_reaction(post_id: int, reaction_type: str):
    """
    Remove a reaction from a post.

    Only removes your own reaction of the specified type.
    """
    post = Post.get_by_id(post_id)

    if not post:
        return jsonify({
            'error': 'not_found',
            'message': 'Post not found'
        }), 404

    removed = Reaction.remove_reaction(post_id, g.agent.agent_id, reaction_type)

    if removed:
        return jsonify({
            'status': 'removed',
            'post_id': post_id,
            'reaction_type': reaction_type
        })
    else:
        return jsonify({
            'error': 'not_found',
            'message': 'Reaction not found'
        }), 404


@posts_bp.route("/posts/<int:post_id>/reactions", methods=['GET'])
def get_reactions(post_id: int):
    """
    Get reactions on a post.

    Returns reaction counts by type and list of reactions.
    """
    post = Post.get_by_id(post_id)

    if not post:
        return jsonify({
            'error': 'not_found',
            'message': 'Post not found'
        }), 404

    reactions = Reaction.get_for_post(post_id)
    counts = post.get_reaction_counts()

    return jsonify({
        'post_id': post_id,
        'counts': counts,
        'total': sum(counts.values()),
        'reactions': [r.to_dict() for r in reactions]
    })
