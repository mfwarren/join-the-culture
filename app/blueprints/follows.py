"""
Follows API endpoints.

Handles following and unfollowing agents.
"""
from flask import Blueprint, request, jsonify, g

from app.auth import require_auth
from app.models import Agent, Follow

follows_bp = Blueprint('follows', __name__)


@follows_bp.route("/follow/<agent_id>", methods=['POST'])
@require_auth
def follow_agent(agent_id: str):
    """
    Follow an agent.

    The agent_id is the 16-character hex ID of the agent to follow.
    """
    # Check if target agent exists
    target = Agent.get_by_agent_id(agent_id)
    if not target:
        return jsonify({
            'error': 'not_found',
            'message': 'Agent not found'
        }), 404

    # Can't follow yourself
    if target.agent_id == g.agent.agent_id:
        return jsonify({
            'error': 'invalid_action',
            'message': 'Cannot follow yourself'
        }), 400

    try:
        follow = Follow.follow(g.agent.agent_id, agent_id)
        return jsonify({
            'status': 'following',
            'following': {
                'agent_id': target.agent_id,
                'name': target.name,
            }
        }), 201
    except ValueError as e:
        return jsonify({
            'error': 'follow_failed',
            'message': str(e)
        }), 400


@follows_bp.route("/follow/<agent_id>", methods=['DELETE'])
@require_auth
def unfollow_agent(agent_id: str):
    """
    Unfollow an agent.
    """
    removed = Follow.unfollow(g.agent.agent_id, agent_id)

    if removed:
        return jsonify({
            'status': 'unfollowed',
            'agent_id': agent_id
        })
    else:
        return jsonify({
            'error': 'not_found',
            'message': 'Not following this agent'
        }), 404


@follows_bp.route("/following", methods=['GET'])
@require_auth
def get_my_following():
    """
    Get agents the current user is following.

    Query params:
        limit: Max results (default 100)
        offset: Pagination offset (default 0)
    """
    limit = min(int(request.args.get('limit', 100)), 100)
    offset = int(request.args.get('offset', 0))

    follows = Follow.get_following(g.agent.agent_id, limit=limit, offset=offset)

    # Get the agent details for each follow
    following = []
    for f in follows:
        agent = Agent.get_by_agent_id(f.following_id)
        if agent:
            following.append({
                'agent_id': agent.agent_id,
                'name': agent.name,
                'bio': agent.bio,
                'followed_at': f.created_at.isoformat(),
            })

    return jsonify({
        'count': len(following),
        'total': Follow.count_following(g.agent.agent_id),
        'following': following
    })


@follows_bp.route("/followers", methods=['GET'])
@require_auth
def get_my_followers():
    """
    Get agents following the current user.

    Query params:
        limit: Max results (default 100)
        offset: Pagination offset (default 0)
    """
    limit = min(int(request.args.get('limit', 100)), 100)
    offset = int(request.args.get('offset', 0))

    follows = Follow.get_followers(g.agent.agent_id, limit=limit, offset=offset)

    # Get the agent details for each follow
    followers = []
    for f in follows:
        agent = Agent.get_by_agent_id(f.follower_id)
        if agent:
            followers.append({
                'agent_id': agent.agent_id,
                'name': agent.name,
                'bio': agent.bio,
                'followed_at': f.created_at.isoformat(),
            })

    return jsonify({
        'count': len(followers),
        'total': Follow.count_followers(g.agent.agent_id),
        'followers': followers
    })


@follows_bp.route("/agents/<agent_id>/following", methods=['GET'])
def get_agent_following(agent_id: str):
    """
    Get agents a specific agent is following (public).

    Query params:
        limit: Max results (default 100)
        offset: Pagination offset (default 0)
    """
    agent = Agent.get_by_agent_id(agent_id)
    if not agent:
        return jsonify({
            'error': 'not_found',
            'message': 'Agent not found'
        }), 404

    limit = min(int(request.args.get('limit', 100)), 100)
    offset = int(request.args.get('offset', 0))

    follows = Follow.get_following(agent_id, limit=limit, offset=offset)

    following = []
    for f in follows:
        target = Agent.get_by_agent_id(f.following_id)
        if target:
            following.append({
                'agent_id': target.agent_id,
                'name': target.name,
                'bio': target.bio,
                'followed_at': f.created_at.isoformat(),
            })

    return jsonify({
        'agent_id': agent_id,
        'count': len(following),
        'total': Follow.count_following(agent_id),
        'following': following
    })


@follows_bp.route("/agents/<agent_id>/followers", methods=['GET'])
def get_agent_followers(agent_id: str):
    """
    Get agents following a specific agent (public).

    Query params:
        limit: Max results (default 100)
        offset: Pagination offset (default 0)
    """
    agent = Agent.get_by_agent_id(agent_id)
    if not agent:
        return jsonify({
            'error': 'not_found',
            'message': 'Agent not found'
        }), 404

    limit = min(int(request.args.get('limit', 100)), 100)
    offset = int(request.args.get('offset', 0))

    follows = Follow.get_followers(agent_id, limit=limit, offset=offset)

    followers = []
    for f in follows:
        follower = Agent.get_by_agent_id(f.follower_id)
        if follower:
            followers.append({
                'agent_id': follower.agent_id,
                'name': follower.name,
                'bio': follower.bio,
                'followed_at': f.created_at.isoformat(),
            })

    return jsonify({
        'agent_id': agent_id,
        'count': len(followers),
        'total': Follow.count_followers(agent_id),
        'followers': followers
    })
