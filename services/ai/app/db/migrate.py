"""Initialise the database once, before the API workers start.

Each uvicorn worker also runs init_db() in the app lifespan. With several
workers starting at once on a database that is not ready yet, they race on
migrations and seeding and one of them fails, stopping the server. Running
this first leaves every worker with nothing to do.

Usage: python -m app.db.migrate
"""
from app.db.session import init_db

if __name__ == "__main__":
    init_db()
