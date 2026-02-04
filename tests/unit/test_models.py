"""
Unit tests for data models.
"""
import time
import pytest

from app.models.agents import AgentStore, PendingChallenge
from app.models.agent import Agent
from app.extensions import db


class TestAgentStore:
    """Tests for AgentStore (requires app context for database)."""

    def test_initial_state(self, app):
        """Store starts empty."""
        with app.app_context():
            store = AgentStore()
            assert store.agent_count() == 0
            assert store.list_agents() == []

    def test_register_agent(self, app):
        """Can register a new agent."""
        with app.app_context():
            store = AgentStore()
            agent = store.register_agent("public_key_123", "Test Agent")

            assert agent.public_key == "public_key_123"
            assert agent.name == "Test Agent"
            assert len(agent.agent_id) == 16
            assert agent.registered_at is not None

    def test_register_duplicate_raises(self, app):
        """Registering same key twice raises error."""
        with app.app_context():
            store = AgentStore()
            store.register_agent("public_key_123", "Test Agent")

            with pytest.raises(ValueError, match="already registered"):
                store.register_agent("public_key_123", "Another Name")

    def test_get_agent(self, app):
        """Can retrieve agent by public key."""
        with app.app_context():
            store = AgentStore()
            store.register_agent("key1", "Agent 1")

            agent = store.get_agent("key1")
            assert agent is not None
            assert agent.name == "Agent 1"

            assert store.get_agent("nonexistent") is None

    def test_get_agent_by_id(self, app):
        """Can retrieve agent by agent ID."""
        with app.app_context():
            store = AgentStore()
            created = store.register_agent("key1", "Agent 1")

            agent = store.get_agent_by_id(created.agent_id)
            assert agent is not None
            assert agent.public_key == "key1"

            assert store.get_agent_by_id("nonexistent") is None

    def test_is_registered(self, app):
        """Can check if key is registered."""
        with app.app_context():
            store = AgentStore()
            store.register_agent("key1", "Agent 1")

            assert store.is_registered("key1") is True
            assert store.is_registered("key2") is False

    def test_list_agents(self, app):
        """Can list all agents."""
        with app.app_context():
            store = AgentStore()
            store.register_agent("key1", "Agent 1")
            store.register_agent("key2", "Agent 2")

            agents = store.list_agents()
            assert len(agents) == 2
            names = {a.name for a in agents}
            assert names == {"Agent 1", "Agent 2"}

    def test_clear_challenges(self, app):
        """clear_challenges removes all challenges but not agents."""
        with app.app_context():
            store = AgentStore()
            store.register_agent("key1", "Agent 1")
            store.create_challenge("key2", "Agent 2")

            store.clear_challenges()

            # Agent still exists
            assert store.agent_count() == 1
            # Challenge is gone
            assert store.get_challenge("key2") is None


class TestChallenges:
    """Tests for challenge management (in-memory, no db needed)."""

    def test_create_challenge(self):
        """Can create a challenge."""
        store = AgentStore()
        challenge = store.create_challenge("key1", "Agent 1", expiry_seconds=300)

        assert len(challenge) > 20  # URL-safe random string
        assert challenge.replace("-", "").replace("_", "").isalnum()

    def test_get_challenge(self):
        """Can retrieve a challenge."""
        store = AgentStore()
        challenge = store.create_challenge("key1", "Agent 1")

        pending = store.get_challenge("key1")
        assert pending is not None
        assert pending.challenge == challenge
        assert pending.name == "Agent 1"

    def test_get_nonexistent_challenge(self):
        """Getting nonexistent challenge returns None."""
        store = AgentStore()
        assert store.get_challenge("key1") is None

    def test_expired_challenge_returns_none(self):
        """Expired challenge is automatically cleaned up."""
        store = AgentStore()
        store.create_challenge("key1", "Agent 1", expiry_seconds=0)

        # Challenge should be expired immediately
        time.sleep(0.01)
        assert store.get_challenge("key1") is None

    def test_consume_challenge(self):
        """Consuming a challenge removes it."""
        store = AgentStore()
        challenge = store.create_challenge("key1", "Agent 1")

        pending = store.consume_challenge("key1")
        assert pending is not None
        assert pending.challenge == challenge

        # Second consume returns None
        assert store.consume_challenge("key1") is None


class TestAgentIdGeneration:
    """Tests for agent ID generation."""

    def test_deterministic(self):
        """Same key always produces same ID."""
        id1 = Agent.generate_agent_id("test_key")
        id2 = Agent.generate_agent_id("test_key")
        assert id1 == id2

    def test_different_keys_different_ids(self):
        """Different keys produce different IDs."""
        id1 = Agent.generate_agent_id("key1")
        id2 = Agent.generate_agent_id("key2")
        assert id1 != id2

    def test_id_length(self):
        """Agent IDs are 16 characters."""
        agent_id = Agent.generate_agent_id("test_key")
        assert len(agent_id) == 16

    def test_id_is_hex(self):
        """Agent IDs are hexadecimal."""
        agent_id = Agent.generate_agent_id("test_key")
        assert all(c in '0123456789abcdef' for c in agent_id)
