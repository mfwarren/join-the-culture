"""
Celery task configuration and async tasks.

This module sets up Celery for background processing, primarily for
embedding generation to keep post creation fast.
"""
from datetime import datetime, timezone

from celery import Celery


# Initialize Celery
celery = Celery(
    'culture',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/1'
)

# Celery configuration
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
    worker_prefetch_multiplier=1,  # Process one task at a time
)


@celery.task(name='generate_post_embedding', bind=True)
def generate_post_embedding(self, post_id: int):
    """
    Generate embedding for a post asynchronously.

    Args:
        post_id: ID of the post to generate embedding for.

    Returns:
        dict with status and post_id.
    """
    from app import create_app
    from app.models.social import Post
    from app.extensions import db
    from app.services.embeddings import EmbeddingService

    app = create_app()

    with app.app_context():
        try:
            # Fetch post
            post = Post.query.get(post_id)
            if not post:
                return {
                    'status': 'error',
                    'post_id': post_id,
                    'error': 'Post not found'
                }

            # Generate embedding
            embedding_service = EmbeddingService()
            embedding = embedding_service.embed_post(post.content, post.super_post)

            # Store embedding
            post.embedding_content = embedding.tolist()
            post.embedding_updated_at = datetime.now(timezone.utc)
            db.session.commit()

            return {
                'status': 'success',
                'post_id': post_id,
                'embedding_dimensions': len(embedding)
            }

        except Exception as e:
            db.session.rollback()
            return {
                'status': 'error',
                'post_id': post_id,
                'error': str(e)
            }


@celery.task(name='generate_agent_embedding', bind=True)
def generate_agent_embedding(self, agent_id: str):
    """
    Generate embedding for an agent asynchronously.

    Args:
        agent_id: ID of the agent to generate embedding for.

    Returns:
        dict with status and agent_id.
    """
    from app import create_app
    from app.models.agent import Agent
    from app.extensions import db
    from app.services.embeddings import EmbeddingService

    app = create_app()

    with app.app_context():
        try:
            # Fetch agent
            agent = Agent.get_by_agent_id(agent_id)
            if not agent:
                return {
                    'status': 'error',
                    'agent_id': agent_id,
                    'error': 'Agent not found'
                }

            # Generate embedding
            embedding_service = EmbeddingService()
            embedding = embedding_service.embed_agent(agent.name, agent.bio)

            # Store embedding
            agent.embedding_bio = embedding.tolist()
            agent.embedding_updated_at = datetime.now(timezone.utc)
            db.session.commit()

            return {
                'status': 'success',
                'agent_id': agent_id,
                'embedding_dimensions': len(embedding)
            }

        except Exception as e:
            db.session.rollback()
            return {
                'status': 'error',
                'agent_id': agent_id,
                'error': str(e)
            }


@celery.task(name='batch_generate_embeddings', bind=True)
def batch_generate_embeddings(self, post_ids: list[int]):
    """
    Generate embeddings for multiple posts in batch.

    More efficient than individual tasks when processing many posts.

    Args:
        post_ids: List of post IDs to process.

    Returns:
        dict with results for each post.
    """
    from app import create_app
    from app.models.social import Post
    from app.extensions import db
    from app.services.embeddings import EmbeddingService

    app = create_app()

    with app.app_context():
        results = []
        embedding_service = EmbeddingService()

        for post_id in post_ids:
            try:
                post = Post.query.get(post_id)
                if not post:
                    results.append({
                        'post_id': post_id,
                        'status': 'error',
                        'error': 'Post not found'
                    })
                    continue

                # Generate embedding
                embedding = embedding_service.embed_post(post.content, post.super_post)

                # Store embedding
                post.embedding_content = embedding.tolist()
                post.embedding_updated_at = datetime.now(timezone.utc)

                results.append({
                    'post_id': post_id,
                    'status': 'success'
                })

            except Exception as e:
                results.append({
                    'post_id': post_id,
                    'status': 'error',
                    'error': str(e)
                })

        # Commit all changes
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            return {
                'status': 'error',
                'error': f'Failed to commit: {str(e)}',
                'results': results
            }

        return {
            'status': 'success',
            'processed': len(results),
            'results': results
        }
