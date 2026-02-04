#!/usr/bin/env python3
"""
Migrate data from SQLite to PostgreSQL.

This script:
1. Backs up the SQLite database
2. Exports all data from SQLite
3. Imports data into PostgreSQL
4. Verifies data integrity
"""
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import psycopg2
from psycopg2.extras import execute_values

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent.parent))


def backup_sqlite(db_path: Path):
    """Create a timestamped backup of the SQLite database."""
    backup_path = db_path.with_suffix(f'.backup.{datetime.now().strftime("%Y%m%d_%H%M%S")}.db')
    import shutil
    shutil.copy2(db_path, backup_path)
    print(f"✓ Created backup: {backup_path}")
    return backup_path


def export_sqlite_data(db_path: Path) -> dict:
    """Export all data from SQLite database."""
    print(f"\nExporting data from SQLite: {db_path}")

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    data = {}

    # Export agents
    cursor.execute("SELECT * FROM agents ORDER BY id")
    data['agents'] = [dict(row) for row in cursor.fetchall()]
    print(f"  ✓ Exported {len(data['agents'])} agents")

    # Export posts
    cursor.execute("SELECT * FROM posts ORDER BY id")
    data['posts'] = [dict(row) for row in cursor.fetchall()]
    print(f"  ✓ Exported {len(data['posts'])} posts")

    # Export reactions
    cursor.execute("SELECT * FROM reactions ORDER BY id")
    data['reactions'] = [dict(row) for row in cursor.fetchall()]
    print(f"  ✓ Exported {len(data['reactions'])} reactions")

    # Export follows
    cursor.execute("SELECT * FROM follows ORDER BY id")
    data['follows'] = [dict(row) for row in cursor.fetchall()]
    print(f"  ✓ Exported {len(data['follows'])} follows")

    conn.close()
    return data


def create_postgres_tables(pg_conn):
    """Create PostgreSQL tables using Flask-Migrate."""
    print("\nCreating PostgreSQL tables...")
    # Tables will be created by running flask db upgrade
    print("  → Run 'flask db upgrade' to create tables")


def import_to_postgres(data: dict, pg_conn_string: str):
    """Import data into PostgreSQL."""
    print(f"\nImporting data to PostgreSQL...")

    conn = psycopg2.connect(pg_conn_string)
    cursor = conn.cursor()

    try:
        # Import agents first (without pinned_post_id to avoid FK constraint)
        if data['agents']:
            agent_values = [
                (
                    row['id'], row['agent_id'], row['public_key'], row['name'],
                    row.get('bio'), row['registered_at'], row.get('agent_metadata'),
                    bool(row['is_active'])
                )
                for row in data['agents']
            ]
            execute_values(
                cursor,
                """
                INSERT INTO agents (id, agent_id, public_key, name, bio, registered_at, agent_metadata, is_active)
                VALUES %s
                """,
                agent_values
            )
            print(f"  ✓ Imported {len(agent_values)} agents")

        # Import posts
        if data['posts']:
            post_values = [
                (
                    row['id'], row['agent_id'], row['content'], row.get('super_post'),
                    row.get('parent_id'), row['created_at'], row.get('updated_at'),
                    bool(row['is_deleted'])
                )
                for row in data['posts']
            ]
            execute_values(
                cursor,
                """
                INSERT INTO posts (id, agent_id, content, super_post, parent_id, created_at, updated_at, is_deleted)
                VALUES %s
                """,
                post_values
            )
            print(f"  ✓ Imported {len(post_values)} posts")

        # Import reactions
        if data['reactions']:
            reaction_values = [
                (
                    row['id'], row['post_id'], row['agent_id'],
                    row['reaction_type'], row['created_at']
                )
                for row in data['reactions']
            ]
            execute_values(
                cursor,
                """
                INSERT INTO reactions (id, post_id, agent_id, reaction_type, created_at)
                VALUES %s
                """,
                reaction_values
            )
            print(f"  ✓ Imported {len(reaction_values)} reactions")

        # Import follows
        if data['follows']:
            follow_values = [
                (
                    row['id'], row['follower_id'], row['following_id'], row['created_at']
                )
                for row in data['follows']
            ]
            execute_values(
                cursor,
                """
                INSERT INTO follows (id, follower_id, following_id, created_at)
                VALUES %s
                """,
                follow_values
            )
            print(f"  ✓ Imported {len(follow_values)} follows")

        # Update pinned_post_id after posts are imported
        for row in data['agents']:
            if row.get('pinned_post_id'):
                cursor.execute(
                    "UPDATE agents SET pinned_post_id = %s WHERE id = %s",
                    (row['pinned_post_id'], row['id'])
                )
        print(f"  ✓ Updated pinned posts for agents")

        # Update sequences to match max IDs
        for table in ['agents', 'posts', 'reactions', 'follows']:
            cursor.execute(f"SELECT setval('{table}_id_seq', (SELECT MAX(id) FROM {table}), true)")

        conn.commit()
        print("\n✓ All data imported successfully")

    except Exception as e:
        conn.rollback()
        print(f"\n✗ Error importing data: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


def verify_migration(sqlite_data: dict, pg_conn_string: str):
    """Verify that all data was migrated correctly."""
    print("\nVerifying migration...")

    conn = psycopg2.connect(pg_conn_string)
    cursor = conn.cursor()

    try:
        # Verify counts
        tables = ['agents', 'posts', 'reactions', 'follows']
        all_match = True

        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            pg_count = cursor.fetchone()[0]
            sqlite_count = len(sqlite_data[table])

            if pg_count == sqlite_count:
                print(f"  ✓ {table}: {pg_count} rows")
            else:
                print(f"  ✗ {table}: SQLite={sqlite_count}, PostgreSQL={pg_count}")
                all_match = False

        if all_match:
            print("\n✓ Migration verification passed!")
            return True
        else:
            print("\n✗ Migration verification failed - counts don't match")
            return False

    finally:
        cursor.close()
        conn.close()


def main():
    """Main migration process."""
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)

    # Paths
    project_root = Path(__file__).parent.parent
    sqlite_db = project_root / 'instance' / 'culture.db'
    pg_conn_string = 'postgresql://localhost/culture_dev'

    # Check if SQLite database exists
    if not sqlite_db.exists():
        print(f"✗ SQLite database not found: {sqlite_db}")
        print("  No migration needed - starting with fresh PostgreSQL database")
        return

    # Step 1: Backup SQLite
    backup_path = backup_sqlite(sqlite_db)

    # Step 2: Export SQLite data
    sqlite_data = export_sqlite_data(sqlite_db)

    # Save exported data to JSON for inspection
    export_file = project_root / 'instance' / 'sqlite_export.json'
    with open(export_file, 'w') as f:
        # Convert datetime objects to strings for JSON serialization
        json_data = {
            table: [
                {k: str(v) if isinstance(v, datetime) else v for k, v in row.items()}
                for row in rows
            ]
            for table, rows in sqlite_data.items()
        }
        json.dump(json_data, f, indent=2)
    print(f"\n✓ Exported data saved to: {export_file}")

    # Step 3: Import to PostgreSQL
    print("\nProceeding with data import (assuming 'flask db upgrade' has been run)...")
    import_to_postgres(sqlite_data, pg_conn_string)

    # Step 4: Verify migration
    if verify_migration(sqlite_data, pg_conn_string):
        print("\n" + "=" * 60)
        print("Migration completed successfully!")
        print("=" * 60)
        print(f"\nBackup saved at: {backup_path}")
        print(f"Export saved at: {export_file}")
        print(f"\nYou can now update your DATABASE_URL to: {pg_conn_string}")
    else:
        print("\n" + "=" * 60)
        print("Migration completed with errors - please review")
        print("=" * 60)


if __name__ == '__main__':
    main()
