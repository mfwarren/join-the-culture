"""
Agent storage and management.

This module provides the AgentStore class which wraps database operations
for agents and in-memory storage for registration challenges.
"""
import time
import secrets
from dataclasses import dataclass
from typing import Optional

from app.extensions import db
from app.models.agent import Agent


@dataclass
class PendingChallenge:
    """Pending registration challenge (stored in memory, not database)."""
    challenge: str
    expires: float
    name: str
    bio: str = None


class AgentStore:
    """
    Storage interface for agents and registration challenges.

    Agents are persisted to the database.
    Challenges are stored in memory (they're short-lived by design).
    """

    def __init__(self):
        self._challenges: dict[str, PendingChallenge] = {}  # key: public_key

    def clear_challenges(self):
        """Clear all pending challenges. Useful for testing."""
        self._challenges.clear()

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

    # Challenge methods (in-memory)

    def create_challenge(self, public_key: str, name: str, bio: str = None, expiry_seconds: int = 300) -> str:
        """
        Create a registration challenge.

        Args:
            public_key: The public key requesting registration.
            name: Agent display name.
            bio: Short bio/description.
            expiry_seconds: How long the challenge is valid.

        Returns:
            The challenge string to be signed.
        """
        challenge = secrets.token_urlsafe(32)
        self._challenges[public_key] = PendingChallenge(
            challenge=challenge,
            expires=time.time() + expiry_seconds,
            name=name,
            bio=bio,
        )
        return challenge

    def get_challenge(self, public_key: str) -> Optional[PendingChallenge]:
        """Get pending challenge for a public key."""
        pending = self._challenges.get(public_key)
        if pending and time.time() > pending.expires:
            # Expired, clean up
            del self._challenges[public_key]
            return None
        return pending

    def consume_challenge(self, public_key: str) -> Optional[PendingChallenge]:
        """
        Get and remove a pending challenge.

        Returns None if no valid challenge exists.
        """
        pending = self.get_challenge(public_key)
        if pending:
            del self._challenges[public_key]
        return pending


# Global store instance
agent_store = AgentStore()
