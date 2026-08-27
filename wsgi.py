"""WSGI entrypoint for brasil-archives.

Usage:
    flask --app wsgi run          # dev, via the Flask CLI (auto-loads .env)
    python wsgi.py                # dev, direct (what app.bat runs)
    gunicorn wsgi:app             # prod
"""
from app import create_app

app = create_app()


if __name__ == "__main__":
    import os

    # The Flask CLI auto-loads .env; a direct `python wsgi.py` does not, so
    # pull it in here (dev-only path — never runs under Passenger/gunicorn).
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    # Reloader off on purpose: app.bat's stop/restart tracks a single PID
    # (matches the sister apps). Debugger stays on when FLASK_DEBUG=1.
    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT") or os.environ.get("FLASK_RUN_PORT", "9000")),
        debug=os.environ.get("FLASK_DEBUG") == "1",
        use_reloader=False,
    )
