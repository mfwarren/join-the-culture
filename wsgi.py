"""
WSGI entry point for production deployment.

This file is used by WSGI servers like Gunicorn to serve the application.
"""
from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run()
