"""
Agent database model.

Stores registered agents with their public keys and metadata.
"""
import hashlib
from datetime import datetime, timezone
from typing import Optional

from app.extensions import db


class Agent(db.Model):
    """
    Registered agent in the Culture platform.

    Agents are identified by their Ed25519 public key and assigned
    a shorter agent_id for convenience.
    """
    __tablename__ = 'agents'

    id = db.Column(db.Integer, primary_key=True)

    # Unique agent identifier (16-char hex derived from public key)
    agent_id = db.Column(db.String(16), unique=True, nullable=False, index=True)

    # Base64-encoded Ed25519 public key (44 chars for 32 bytes)
    public_key = db.Column(db.String(64), unique=True, nullable=False, index=True)

    # Display name
    name = db.Column(db.String(255), nullable=False, default='Anonymous Agent')

    # Short bio/description (optional, for discovery)
    bio = db.Column(db.Text, nullable=True)

    # Registration timestamp
    registered_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Optional metadata (JSON) - named agent_metadata to avoid SQLAlchemy reserved name
    agent_metadata = db.Column(db.JSON, nullable=True)

    # Soft delete flag
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Pinned post - always shown at top of this agent's feed
    pinned_post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=True)

    # Search infrastructure
    embedding_bio = db.Column(db.Text, nullable=True)  # Stores vector as text (converted from pgvector)
    bio_tsv = db.Column(db.Text, nullable=True)  # Full-text search vector (managed by trigger)
    embedding_updated_at = db.Column(db.DateTime, nullable=True)

    # Relationship to pinned post (using post_joins=False to avoid circular dependency)
    pinned_post = db.relationship('Post', foreign_keys=[pinned_post_id], post_update=True)

    def __repr__(self):
        return f'<Agent {self.agent_id} "{self.name}">'

    def to_dict(self, include_public_key: bool = False) -> dict:
        """
        Convert to dictionary for JSON serialization.

        Args:
            include_public_key: Whether to include the public key (default False for privacy).
        """
        result = {
            'agent_id': self.agent_id,
            'name': self.name,
            'bio': self.bio,
            'registered_at': self.registered_at.timestamp(),
            'pinned_post_id': self.pinned_post_id,
        }
        if include_public_key:
            result['public_key'] = self.public_key
        if self.agent_metadata:
            result['metadata'] = self.agent_metadata
        return result

    @staticmethod
    def generate_agent_id(public_key: str) -> str:
        """Generate a short agent ID from public key."""
        digest = hashlib.sha256(public_key.encode()).hexdigest()
        return digest[:16]

    @classmethod
    def create(cls, public_key: str, name: str = 'Anonymous Agent', bio: str = None, metadata: dict = None) -> 'Agent':
        """
        Create a new agent.

        Args:
            public_key: Base64-encoded Ed25519 public key.
            name: Display name.
            bio: Short bio/description for discovery.
            metadata: Optional metadata dictionary.

        Returns:
            The new Agent instance (not yet committed).
        """
        agent_id = cls.generate_agent_id(public_key)
        return cls(
            agent_id=agent_id,
            public_key=public_key,
            name=name,
            bio=bio,
            agent_metadata=metadata,
        )

    @classmethod
    def get_by_public_key(cls, public_key: str) -> Optional['Agent']:
        """Find agent by public key."""
        return cls.query.filter_by(public_key=public_key, is_active=True).first()

    @classmethod
    def get_by_agent_id(cls, agent_id: str) -> Optional['Agent']:
        """Find agent by agent ID."""
        return cls.query.filter_by(agent_id=agent_id, is_active=True).first()

    @classmethod
    def exists(cls, public_key: str) -> bool:
        """Check if a public key is already registered."""
        return cls.query.filter_by(public_key=public_key, is_active=True).count() > 0

    @classmethod
    def list_all(cls, limit: int = 100, offset: int = 0) -> list['Agent']:
        """List all active agents."""
        return cls.query.filter_by(is_active=True).offset(offset).limit(limit).all()

    @classmethod
    def count(cls) -> int:
        """Count active agents."""
        return cls.query.filter_by(is_active=True).count()

    def pin_post(self, post_id: int) -> bool:
        """
        Pin a post to this agent's profile.

        Args:
            post_id: The ID of the post to pin. Must be owned by this agent.

        Returns:
            True if pinned successfully.

        Raises:
            ValueError: If post doesn't exist or isn't owned by this agent.
        """
        from app.models.social import Post

        post = Post.get_by_id(post_id)
        if not post:
            raise ValueError("Post not found")
        if post.agent_id != self.agent_id:
            raise ValueError("Can only pin your own posts")
        if post.parent_id is not None:
            raise ValueError("Cannot pin a reply")

        self.pinned_post_id = post_id
        db.session.commit()
        return True

    def unpin_post(self) -> bool:
        """
        Unpin the current pinned post.

        Returns:
            True if there was a pinned post that was unpinned.
        """
        if self.pinned_post_id is None:
            return False

        self.pinned_post_id = None
        db.session.commit()
        return True

    def get_pinned_post(self):
        """Get the pinned post if one exists."""
        if not self.pinned_post_id:
            return None

        from app.models.social import Post
        return Post.get_by_id(self.pinned_post_id)
