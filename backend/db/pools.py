"""
Shared database clients for the API process (one pool per worker under Gunicorn).
"""
from __future__ import annotations

import os
from typing import Optional

from neo4j import GraphDatabase
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from backend.config import settings


_engine: Optional[Engine] = None
_neo4j_driver = None


def get_sqlalchemy_engine() -> Engine:
    """Singleton SQLAlchemy engine with bounded pool (safe under concurrent load)."""
    global _engine
    if _engine is None:
        url = settings.DATABASE_URL

        pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
        max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "15"))
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "3600")),
            pool_timeout=float(os.getenv("DB_POOL_TIMEOUT", "30")),
        )
    return _engine


def get_neo4j_driver():
    """Singleton Neo4j driver with bounded connection pool."""
    global _neo4j_driver
    if _neo4j_driver is None:
        max_pool = int(os.getenv("NEO4J_MAX_POOL_SIZE", "40"))
        _neo4j_driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(
                os.getenv("NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j")),
                os.getenv("NEO4J_PASSWORD"),
            ),
            max_connection_pool_size=max_pool,
        )
    return _neo4j_driver


def dispose_sqlalchemy_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


def close_neo4j_driver() -> None:
    global _neo4j_driver
    if _neo4j_driver is not None:
        _neo4j_driver.close()
        _neo4j_driver = None
