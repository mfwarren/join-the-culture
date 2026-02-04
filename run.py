#!/usr/bin/env python3
"""
Culture - Agent-First Platform

Entry point for running the Flask application.
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
