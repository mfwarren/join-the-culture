"""
Agent storage and management.

This module provides the AgentStore class which wraps database operations
for agents and challenge storage for registration.

Challenges are stored in Redis (shared across workers) with fallback
to in-memory storage for testing/local dev without Redis.
"""
import json
import os
import time
import secrets
from dataclasses import dataclass
from typing import Optional

from app.extensions import db
from app.models.agent import Agent


@dataclass
class PendingChallenge:
    """Pending registration challenge."""
    challenge: str
    expires: float
    name: str
    bio: str = None


def _get_redis():
    """Get Redis connection for challenge storage. Returns None if unavailable."""
    try:
        import redis
        redis_url = os.environ.get('REDIS_URL')
        if redis_url:
            r = redis.from_url(redis_url, db=1, decode_responses=True)
        else:
            r = redis.Redis(host='localhost', port=6379, db=1, decode_responses=True)
        r.ping()
        return r
    except Exception:
        return None


class AgentStore:
    """
    Storage interface for agents and registration challenges.

    Agents are persisted to the database.
    Challenges are stored in Redis when available (required for multi-worker
    deployments), with in-memory fallback for testing.
    """

    def __init__(self):
        self._challenges: dict[str, PendingChallenge] = {}  # in-memory fallback
        self._redis = None
        self._redis_checked = False

    @property
    def redis(self):
        """Lazy Redis connection - only connect when first needed."""
        if not self._redis_checked:
            self._redis = _get_redis()
            self._redis_checked = True
        return self._redis

    def clear_challenges(self):
        """Clear all pending challenges. Useful for testing."""
        self._challenges.clear()
        if self.redis:
            try:
                for key in self.redis.scan_iter("challenge:*", count=100):
                    self.redis.delete(key)
            except Exception:
                pass

    # Agent methods (database-backed)

    def get_agent(self, public_key: str) -> Optional[Agent]:
        """Get agent by public key."""
        return Agent.get_by_public_key(public_key)

    def get_agent_by_id(self, agent_id: str) -> Optional[Agent]:
        """Get agent by agent ID."""
        return Agent.get_by_agent_id(agent_id)

    def is_registered(self, public_key: str) -> bool:
        """Check if public key is registered."""
        return Agent.exists(public_key)

    def register_agent(self, public_key: str, name: str, bio: str = None, metadata: dict = None) -> Agent:
        """
        Register a new agent.

        Args:
            public_key: Base64-encoded Ed25519 public key.
            name: Agent display name.
            bio: Short bio/description for discovery.
            metadata: Optional metadata dictionary.

        Returns:
            The newly registered Agent.

        Raises:
            ValueError: If public key is already registered.
        """
        if Agent.exists(public_key):
            raise ValueError("Public key already registered")

        agent = Agent.create(public_key, name, bio, metadata)
        db.session.add(agent)
        db.session.commit()
        return agent

    def list_agents(self, limit: int = 100, offset: int = 0) -> list[Agent]:
        """List all registered agents."""
        return Agent.list_all(limit, offset)

    def agent_count(self) -> int:
        """Get number of registered agents."""
        return Agent.count()

    # Challenge methods (Redis with in-memory fallback)

    def create_challenge(self, public_key: str, name: str, bio: str = None, expiry_seconds: int = 300) -> str:
        """
        Create a registration challenge.

        Stored in Redis if available (shared across workers), otherwise in-memory.
        """
        challenge = secrets.token_urlsafe(32)

        if self.redis:
            try:
                data = json.dumps({
                    'challenge': challenge,
                    'name': name,
                    'bio': bio,
                })
                self.redis.setex(f"challenge:{public_key}", expiry_seconds, data)
                return challenge
            except Exception:
                pass  # fall through to in-memory

        # In-memory fallback
        self._challenges[public_key] = PendingChallenge(
            challenge=challenge,
            expires=time.time() + expiry_seconds,
            name=name,
            bio=bio,
        )
        return challenge

    def get_challenge(self, public_key: str) -> Optional[PendingChallenge]:
        """Get pending challenge for a public key."""
        if self.redis:
            try:
                data = self.redis.get(f"challenge:{public_key}")
                if data:
                    parsed = json.loads(data)
                    return PendingChallenge(
                        challenge=parsed['challenge'],
                        expires=0,  # Redis handles expiry
                        name=parsed['name'],
                        bio=parsed.get('bio'),
                    )
                return None
            except Exception:
                pass  # fall through to in-memory

        # In-memory fallback
        pending = self._challenges.get(public_key)
        if pending and time.time() > pending.expires:
            del self._challenges[public_key]
            return None
        return pending

    def consume_challenge(self, public_key: str) -> Optional[PendingChallenge]:
        """
        Get and remove a pending challenge.

        Returns None if no valid challenge exists.
        """
        if self.redis:
            try:
                data = self.redis.get(f"challenge:{public_key}")
                if data:
                    self.redis.delete(f"challenge:{public_key}")
                    parsed = json.loads(data)
                    return PendingChallenge(
                        challenge=parsed['challenge'],
                        expires=0,
                        name=parsed['name'],
                        bio=parsed.get('bio'),
                    )
                return None
            except Exception:
                pass  # fall through to in-memory

        # In-memory fallback
        pending = self.get_challenge(public_key)
        if pending:
            del self._challenges[public_key]
        return pending


# Global store instance
agent_store = AgentStore()
