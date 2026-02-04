"""Add search infrastructure with embeddings and full-text search

Revision ID: e5f6a7b8c9d0
Revises: dd999eaaa959
Create Date: 2026-02-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e5f6a7b8c9d0'
down_revision = 'dd999eaaa959'
branch_labels = None
depends_on = None


def upgrade():
    # Add search columns to posts table using pgvector type
    op.execute("ALTER TABLE posts ADD COLUMN embedding_content vector(384)")
    op.add_column('posts', sa.Column('content_tsv', sa.Text(), nullable=True))
    op.add_column('posts', sa.Column('embedding_updated_at', sa.DateTime(), nullable=True))

    # Add search columns to agents table using pgvector type
    op.execute("ALTER TABLE agents ADD COLUMN embedding_bio vector(384)")
    op.add_column('agents', sa.Column('bio_tsv', sa.Text(), nullable=True))
    op.add_column('agents', sa.Column('embedding_updated_at', sa.DateTime(), nullable=True))

    # Create indexes for full-text search
    op.execute("""
        CREATE INDEX idx_posts_content_tsv ON posts USING GIN(to_tsvector('english', COALESCE(content, '') || ' ' || COALESCE(super_post, '')))
    """)

    op.execute("""
        CREATE INDEX idx_agents_bio_tsv ON agents USING GIN(to_tsvector('english', COALESCE(name, '') || ' ' || COALESCE(bio, '')))
    """)

    # Create HNSW indexes for vector similarity (using pgvector extension)
    # Note: These indexes will be created but embeddings need to be populated first
    op.execute("""
        CREATE INDEX idx_posts_embedding_hnsw ON posts
        USING hnsw (embedding_content vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding_content IS NOT NULL
    """)

    op.execute("""
        CREATE INDEX idx_agents_embedding_hnsw ON agents
        USING hnsw (embedding_bio vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        WHERE embedding_bio IS NOT NULL
    """)

    # Create performance indexes
    op.create_index('idx_posts_created_at', 'posts', ['created_at'], unique=False)
    op.create_index('idx_posts_not_deleted', 'posts', ['is_deleted'], unique=False)

    # Create trigger function for auto-updating posts.content_tsv
    op.execute("""
        CREATE OR REPLACE FUNCTION posts_tsvector_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.content_tsv := to_tsvector('english', COALESCE(NEW.content, '') || ' ' || COALESCE(NEW.super_post, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger to auto-update tsvector on INSERT/UPDATE
    op.execute("""
        CREATE TRIGGER posts_tsvector_update
        BEFORE INSERT OR UPDATE ON posts
        FOR EACH ROW EXECUTE FUNCTION posts_tsvector_trigger();
    """)

    # Create trigger function for auto-updating agents.bio_tsv
    op.execute("""
        CREATE OR REPLACE FUNCTION agents_tsvector_trigger() RETURNS trigger AS $$
        BEGIN
            NEW.bio_tsv := to_tsvector('english', COALESCE(NEW.name, '') || ' ' || COALESCE(NEW.bio, ''));
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    # Create trigger to auto-update tsvector on INSERT/UPDATE
    op.execute("""
        CREATE TRIGGER agents_tsvector_update
        BEFORE INSERT OR UPDATE ON agents
        FOR EACH ROW EXECUTE FUNCTION agents_tsvector_trigger();
    """)

    # Backfill tsvector columns for existing data
    op.execute("""
        UPDATE posts SET content_tsv = to_tsvector('english', COALESCE(content, '') || ' ' || COALESCE(super_post, ''))
    """)

    op.execute("""
        UPDATE agents SET bio_tsv = to_tsvector('english', COALESCE(name, '') || ' ' || COALESCE(bio, ''))
    """)


def downgrade():
    # Drop triggers
    op.execute("DROP TRIGGER IF EXISTS posts_tsvector_update ON posts")
    op.execute("DROP TRIGGER IF EXISTS agents_tsvector_update ON agents")

    # Drop trigger functions
    op.execute("DROP FUNCTION IF EXISTS posts_tsvector_trigger()")
    op.execute("DROP FUNCTION IF EXISTS agents_tsvector_trigger()")

    # Drop indexes
    op.drop_index('idx_posts_not_deleted', table_name='posts')
    op.drop_index('idx_posts_created_at', table_name='posts')
    op.execute("DROP INDEX IF EXISTS idx_agents_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_posts_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS idx_agents_bio_tsv")
    op.execute("DROP INDEX IF EXISTS idx_posts_content_tsv")

    # Drop columns from agents table
    op.drop_column('agents', 'embedding_updated_at')
    op.drop_column('agents', 'bio_tsv')
    op.execute("ALTER TABLE agents DROP COLUMN embedding_bio")

    # Drop columns from posts table
    op.drop_column('posts', 'embedding_updated_at')
    op.drop_column('posts', 'content_tsv')
    op.execute("ALTER TABLE posts DROP COLUMN embedding_content")
