"""WSGI entrypoint for brasil-archives.

Usage:
    flask --app wsgi run
    gunicorn wsgi:app
"""
from app import create_app

app = create_app()
