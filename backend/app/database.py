"""Explicit PostgreSQL configuration; migrations never run during API startup."""

from sqlalchemy import Engine, create_engine


def make_engine(url: str) -> Engine:
    return create_engine(url, pool_pre_ping=True, hide_parameters=True)
