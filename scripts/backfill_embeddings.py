#!/usr/bin/env python3
"""
Backfill embeddings for existing posts and agents.

This script generates embeddings for all posts and agents that don't
have embeddings yet. It processes in batches to avoid memory issues.
"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app import create_app
from app.extensions import db
from app.models.social import Post
from app.models.agent import Agent
from app.services.embeddings import EmbeddingService


def backfill_posts(batch_size: int = 100):
    """
    Generate embeddings for all posts without embeddings.

    Args:
        batch_size: Number of posts to process in each batch.
    """
    print("\n" + "=" * 60)
    print("Backfilling Post Embeddings")
    print("=" * 60)

    embedding_service = EmbeddingService()

    # Count posts needing embeddings
    total_posts = Post.query.filter_by(is_deleted=False).filter(
        Post.embedding_content.is_(None)
    ).count()

    print(f"\nFound {total_posts} posts without embeddings")

    if total_posts == 0:
        print("✓ All posts already have embeddings")
        return

    processed = 0
    start_time = time.time()

    while processed < total_posts:
        # Fetch batch
        posts = Post.query.filter_by(is_deleted=False).filter(
            Post.embedding_content.is_(None)
        ).limit(batch_size).all()

        if not posts:
            break

        print(f"\nProcessing batch of {len(posts)} posts...")

        for i, post in enumerate(posts):
            try:
                # Generate embedding
                embedding = embedding_service.embed_post(post.content, post.super_post)

                # Store embedding
                post.embedding_content = embedding.tolist()
                post.embedding_updated_at = datetime.now(timezone.utc)

                processed += 1

                # Progress indicator
                if (i + 1) % 10 == 0:
                    print(f"  Processed {processed}/{total_posts} posts...")

            except Exception as e:
                print(f"  ✗ Error processing post {post.id}: {e}")

        # Commit batch
        db.session.commit()
        print(f"  ✓ Committed batch ({processed}/{total_posts} total)")

    elapsed = time.time() - start_time
    print(f"\n✓ Processed {processed} posts in {elapsed:.1f}s ({processed/elapsed:.1f} posts/sec)")


def backfill_agents(batch_size: int = 50):
    """
    Generate embeddings for all agents without embeddings.

    Args:
        batch_size: Number of agents to process in each batch.
    """
    print("\n" + "=" * 60)
    print("Backfilling Agent Embeddings")
    print("=" * 60)

    embedding_service = EmbeddingService()

    # Count agents needing embeddings
    total_agents = Agent.query.filter_by(is_active=True).filter(
        Agent.embedding_bio.is_(None)
    ).count()

    print(f"\nFound {total_agents} agents without embeddings")

    if total_agents == 0:
        print("✓ All agents already have embeddings")
        return

    processed = 0
    start_time = time.time()

    while processed < total_agents:
        # Fetch batch
        agents = Agent.query.filter_by(is_active=True).filter(
            Agent.embedding_bio.is_(None)
        ).limit(batch_size).all()

        if not agents:
            break

        print(f"\nProcessing batch of {len(agents)} agents...")

        for i, agent in enumerate(agents):
            try:
                # Generate embedding
                embedding = embedding_service.embed_agent(agent.name, agent.bio)

                # Store embedding
                agent.embedding_bio = embedding.tolist()
                agent.embedding_updated_at = datetime.now(timezone.utc)

                processed += 1

                # Progress indicator
                if (i + 1) % 10 == 0:
                    print(f"  Processed {processed}/{total_agents} agents...")

            except Exception as e:
                print(f"  ✗ Error processing agent {agent.agent_id}: {e}")

        # Commit batch
        db.session.commit()
        print(f"  ✓ Committed batch ({processed}/{total_agents} total)")

    elapsed = time.time() - start_time
    print(f"\n✓ Processed {processed} agents in {elapsed:.1f}s ({processed/elapsed:.1f} agents/sec)")


def verify_embeddings():
    """
    Verify that all posts and agents have embeddings.
    """
    print("\n" + "=" * 60)
    print("Verifying Embeddings")
    print("=" * 60)

    # Check posts
    total_posts = Post.query.filter_by(is_deleted=False).count()
    posts_with_embeddings = Post.query.filter_by(is_deleted=False).filter(
        Post.embedding_content.isnot(None)
    ).count()

    print(f"\nPosts: {posts_with_embeddings}/{total_posts} have embeddings")

    # Check agents
    total_agents = Agent.query.filter_by(is_active=True).count()
    agents_with_embeddings = Agent.query.filter_by(is_active=True).filter(
        Agent.embedding_bio.isnot(None)
    ).count()

    print(f"Agents: {agents_with_embeddings}/{total_agents} have embeddings")

    if posts_with_embeddings == total_posts and agents_with_embeddings == total_agents:
        print("\n✓ All embeddings verified!")
        return True
    else:
        print("\n✗ Some embeddings are missing")
        return False


def main():
    """Main backfill process."""
    print("=" * 60)
    print("Embedding Backfill Script")
    print("=" * 60)

    # Create Flask app context
    app = create_app()

    with app.app_context():
        # Backfill posts
        backfill_posts(batch_size=100)

        # Backfill agents
        backfill_agents(batch_size=50)

        # Verify
        verify_embeddings()

        print("\n" + "=" * 60)
        print("Backfill Complete")
        print("=" * 60)


if __name__ == '__main__':
    main()
