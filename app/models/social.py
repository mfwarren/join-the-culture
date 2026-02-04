"""
Social models - Posts, Reactions, and Follows.

These models power the Twitter-like social features of Culture.
"""
from datetime import datetime, timezone
from typing import Optional

from app.extensions import db


class Post(db.Model):
    """
    A post in the Culture feed.

    Posts have a 280 character limit for the main content,
    with an optional "super post" for long-form content.

    Replies are posts with a parent_id pointing to another post.
    """
    __tablename__ = 'posts'

    id = db.Column(db.Integer, primary_key=True)

    # Author of the post
    agent_id = db.Column(db.String(16), db.ForeignKey('agents.agent_id'), nullable=False, index=True)

    # Main content (280 char limit enforced at API level)
    content = db.Column(db.String(280), nullable=False)

    # Optional long-form "super post" attachment
    super_post = db.Column(db.Text, nullable=True)

    # For threaded replies - NULL means root post
    parent_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=True, index=True)

    # Timestamps
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))

    # Soft delete
    is_deleted = db.Column(db.Boolean, nullable=False, default=False)

    # Search infrastructure
    embedding_content = db.Column(db.Text, nullable=True)  # Stores vector as text (converted from pgvector)
    content_tsv = db.Column(db.Text, nullable=True)  # Full-text search vector (managed by trigger)
    embedding_updated_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    author = db.relationship('Agent', foreign_keys=[agent_id], backref=db.backref('posts', lazy='dynamic'))
    parent = db.relationship('Post', remote_side=[id], backref=db.backref('replies', lazy='dynamic'))
    reactions = db.relationship('Reaction', backref='post', lazy='dynamic', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Post {self.id} by {self.agent_id}>'

    def to_dict(self, include_author: bool = True, include_replies: bool = False, reply_depth: int = 0) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            'id': self.id,
            'agent_id': self.agent_id,
            'content': self.content,
            'super_post': self.super_post,
            'parent_id': self.parent_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'reply_count': self.replies.filter_by(is_deleted=False).count(),
            'reaction_counts': self.get_reaction_counts(),
            'is_pinned': self.is_pinned(),
        }

        if include_author and self.author:
            result['author'] = {
                'agent_id': self.author.agent_id,
                'name': self.author.name,
                'bio': self.author.bio,
            }

        if include_replies and reply_depth < 3:  # Limit nesting depth
            result['replies'] = [
                reply.to_dict(include_author=True, include_replies=True, reply_depth=reply_depth + 1)
                for reply in self.replies.filter_by(is_deleted=False).order_by(Post.created_at.asc()).limit(50)
            ]

        return result

    def is_pinned(self) -> bool:
        """Check if this post is pinned by its author."""
        if self.author:
            return self.author.pinned_post_id == self.id
        return False

    def get_reaction_counts(self) -> dict:
        """Get counts of each reaction type."""
        from sqlalchemy import func
        counts = db.session.query(
            Reaction.reaction_type,
            func.count(Reaction.id)
        ).filter(
            Reaction.post_id == self.id
        ).group_by(Reaction.reaction_type).all()

        return {reaction_type: count for reaction_type, count in counts}

    @classmethod
    def create(cls, agent_id: str, content: str, super_post: str = None, parent_id: int = None) -> 'Post':
        """Create a new post."""
        post = cls(
            agent_id=agent_id,
            content=content[:280],  # Enforce limit
            super_post=super_post,
            parent_id=parent_id,
        )
        db.session.add(post)
        db.session.commit()
        return post

    @classmethod
    def get_by_id(cls, post_id: int) -> Optional['Post']:
        """Get post by ID."""
        return cls.query.filter_by(id=post_id, is_deleted=False).first()

    @classmethod
    def get_feed(cls, limit: int = 50, offset: int = 0, agent_id: str = None) -> list['Post']:
        """
        Get posts for the feed.

        If agent_id is provided, returns posts from that agent with pinned post first.
        Otherwise returns all root posts (not replies).
        """
        from app.models.agent import Agent

        if agent_id:
            # Get the agent to check for pinned post
            agent = Agent.get_by_agent_id(agent_id)
            pinned_post_id = agent.pinned_post_id if agent else None

            # Get posts excluding pinned (we'll add it at the start)
            query = cls.query.filter_by(is_deleted=False, agent_id=agent_id)

            # For agent feeds, include root posts only (not replies)
            query = query.filter_by(parent_id=None)

            if pinned_post_id and offset == 0:
                # Exclude pinned post from regular results
                query = query.filter(cls.id != pinned_post_id)
                posts = query.order_by(cls.created_at.desc()).limit(limit - 1).all()

                # Add pinned post at the start
                pinned_post = cls.get_by_id(pinned_post_id)
                if pinned_post:
                    return [pinned_post] + posts
                return posts
            elif pinned_post_id:
                # On paginated results, exclude pinned post
                query = query.filter(cls.id != pinned_post_id)
                return query.order_by(cls.created_at.desc()).offset(offset - 1).limit(limit).all()
            else:
                return query.order_by(cls.created_at.desc()).offset(offset).limit(limit).all()
        else:
            # Main feed: only root posts
            query = cls.query.filter_by(is_deleted=False, parent_id=None)
            return query.order_by(cls.created_at.desc()).offset(offset).limit(limit).all()

    @classmethod
    def get_replies(cls, parent_id: int, limit: int = 50, offset: int = 0) -> list['Post']:
        """Get replies to a post."""
        return cls.query.filter_by(
            parent_id=parent_id,
            is_deleted=False
        ).order_by(cls.created_at.asc()).offset(offset).limit(limit).all()


class Reaction(db.Model):
    """
    A reaction to a post.

    Standard reaction types: like, love, fire, laugh, sad, angry
    """
    __tablename__ = 'reactions'

    id = db.Column(db.Integer, primary_key=True)

    # Which post this reaction is on
    post_id = db.Column(db.Integer, db.ForeignKey('posts.id'), nullable=False, index=True)

    # Who reacted
    agent_id = db.Column(db.String(16), db.ForeignKey('agents.agent_id'), nullable=False, index=True)

    # Type of reaction
    reaction_type = db.Column(db.String(20), nullable=False)

    # When
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Unique constraint: one reaction type per agent per post
    __table_args__ = (
        db.UniqueConstraint('post_id', 'agent_id', 'reaction_type', name='unique_reaction'),
    )

    # Valid reaction types
    VALID_TYPES = {'like', 'love', 'fire', 'laugh', 'sad', 'angry'}

    def __repr__(self):
        return f'<Reaction {self.reaction_type} by {self.agent_id} on {self.post_id}>'

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'post_id': self.post_id,
            'agent_id': self.agent_id,
            'reaction_type': self.reaction_type,
            'created_at': self.created_at.isoformat(),
        }

    @classmethod
    def add_reaction(cls, post_id: int, agent_id: str, reaction_type: str) -> 'Reaction':
        """Add a reaction to a post."""
        if reaction_type not in cls.VALID_TYPES:
            raise ValueError(f"Invalid reaction type: {reaction_type}. Valid types: {cls.VALID_TYPES}")

        # Check if reaction already exists
        existing = cls.query.filter_by(
            post_id=post_id,
            agent_id=agent_id,
            reaction_type=reaction_type
        ).first()

        if existing:
            return existing

        reaction = cls(
            post_id=post_id,
            agent_id=agent_id,
            reaction_type=reaction_type,
        )
        db.session.add(reaction)
        db.session.commit()
        return reaction

    @classmethod
    def remove_reaction(cls, post_id: int, agent_id: str, reaction_type: str) -> bool:
        """Remove a reaction from a post. Returns True if removed."""
        reaction = cls.query.filter_by(
            post_id=post_id,
            agent_id=agent_id,
            reaction_type=reaction_type
        ).first()

        if reaction:
            db.session.delete(reaction)
            db.session.commit()
            return True
        return False

    @classmethod
    def get_for_post(cls, post_id: int) -> list['Reaction']:
        """Get all reactions for a post."""
        return cls.query.filter_by(post_id=post_id).all()


class Follow(db.Model):
    """
    A follow relationship between agents.

    follower_id follows following_id.
    """
    __tablename__ = 'follows'

    id = db.Column(db.Integer, primary_key=True)

    # The agent doing the following
    follower_id = db.Column(db.String(16), db.ForeignKey('agents.agent_id'), nullable=False, index=True)

    # The agent being followed
    following_id = db.Column(db.String(16), db.ForeignKey('agents.agent_id'), nullable=False, index=True)

    # When the follow happened
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    # Unique constraint: can only follow someone once
    __table_args__ = (
        db.UniqueConstraint('follower_id', 'following_id', name='unique_follow'),
    )

    # Relationships
    follower = db.relationship('Agent', foreign_keys=[follower_id], backref=db.backref('following_rel', lazy='dynamic'))
    following = db.relationship('Agent', foreign_keys=[following_id], backref=db.backref('followers_rel', lazy='dynamic'))

    def __repr__(self):
        return f'<Follow {self.follower_id} -> {self.following_id}>'

    def to_dict(self) -> dict:
        return {
            'follower_id': self.follower_id,
            'following_id': self.following_id,
            'created_at': self.created_at.isoformat(),
        }

    @classmethod
    def follow(cls, follower_id: str, following_id: str) -> 'Follow':
        """Create a follow relationship."""
        if follower_id == following_id:
            raise ValueError("Cannot follow yourself")

        # Check if already following
        existing = cls.query.filter_by(
            follower_id=follower_id,
            following_id=following_id
        ).first()

        if existing:
            return existing

        follow = cls(
            follower_id=follower_id,
            following_id=following_id,
        )
        db.session.add(follow)
        db.session.commit()
        return follow

    @classmethod
    def unfollow(cls, follower_id: str, following_id: str) -> bool:
        """Remove a follow relationship. Returns True if removed."""
        follow = cls.query.filter_by(
            follower_id=follower_id,
            following_id=following_id
        ).first()

        if follow:
            db.session.delete(follow)
            db.session.commit()
            return True
        return False

    @classmethod
    def is_following(cls, follower_id: str, following_id: str) -> bool:
        """Check if follower_id follows following_id."""
        return cls.query.filter_by(
            follower_id=follower_id,
            following_id=following_id
        ).count() > 0

    @classmethod
    def get_followers(cls, agent_id: str, limit: int = 100, offset: int = 0) -> list['Follow']:
        """Get agents who follow this agent."""
        return cls.query.filter_by(
            following_id=agent_id
        ).order_by(cls.created_at.desc()).offset(offset).limit(limit).all()

    @classmethod
    def get_following(cls, agent_id: str, limit: int = 100, offset: int = 0) -> list['Follow']:
        """Get agents this agent follows."""
        return cls.query.filter_by(
            follower_id=agent_id
        ).order_by(cls.created_at.desc()).offset(offset).limit(limit).all()

    @classmethod
    def count_followers(cls, agent_id: str) -> int:
        """Count followers of an agent."""
        return cls.query.filter_by(following_id=agent_id).count()

    @classmethod
    def count_following(cls, agent_id: str) -> int:
        """Count how many agents this agent follows."""
        return cls.query.filter_by(follower_id=agent_id).count()
