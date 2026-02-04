"""
Flask extensions.

Extensions are initialized here and bound to the app in create_app().
"""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate

# SQLAlchemy instance - configured in create_app()
db = SQLAlchemy()

# Migrate instance for database migrations
migrate = Migrate()
