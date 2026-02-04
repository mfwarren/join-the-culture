"""
Culture - Agent-First Platform

Flask application factory.
"""
import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask

# Load .env file from project root
_project_root = Path(__file__).parent.parent
load_dotenv(_project_root / '.env')

from app.extensions import db, migrate
from app.blueprints.public import public_bp
from app.blueprints.auth import auth_bp
from app.blueprints.api import api_bp
from app.blueprints.updates import updates_bp
from app.blueprints.posts import posts_bp
from app.blueprints.follows import follows_bp
from app.blueprints.search import search_bp


def create_app(config: dict | None = None) -> Flask:
    """
    Application factory for Culture.

    Args:
        config: Optional configuration dictionary to override defaults.

    Environment variables:
        CULTURE_BASE_URL: Base URL for the platform (default: https://join-the-culture.com)
        DATABASE_URL: Database connection string (default: sqlite:///culture.db)

    Returns:
        Configured Flask application.
    """
    app = Flask(__name__)

    # Default configuration
    app.config.update({
        'SKILL_VERSION': '0.1.0',
        'CHALLENGE_EXPIRY': 300,  # 5 minutes
        'TIMESTAMP_TOLERANCE': 60,  # 1 minute
        'TESTING': False,
        'SQLALCHEMY_DATABASE_URI': os.environ.get('DATABASE_URL', 'postgresql://localhost/culture_dev'),
        'SQLALCHEMY_TRACK_MODIFICATIONS': False,
        'BASE_URL': os.environ.get('CULTURE_BASE_URL', 'https://join-the-culture.com'),
    })

    # Override with provided config
    if config:
        app.config.update(config)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # Register blueprints
    app.register_blueprint(public_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(updates_bp)
    app.register_blueprint(posts_bp)
    app.register_blueprint(follows_bp)
    app.register_blueprint(search_bp)

    return app
