"""Small PostgreSQL helper layer for the Streamlit app."""

from __future__ import annotations

import os
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor
import streamlit as st


def get_database_url() -> str:
    """Read the PostgreSQL connection string from Streamlit secrets or env vars."""
    try:
        url = st.secrets["database"]["url"]
    except Exception:
        url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Add it to .streamlit/secrets.toml."
        )
    return url


def get_connection():
    """Open a new database connection.

    A new connection per operation is simple and reliable for a class demo.
    """
    return psycopg2.connect(get_database_url(), cursor_factory=RealDictCursor)


def fetch_all(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())


def fetch_one(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    rows = fetch_all(sql, params)
    return rows[0] if rows else None


def execute(sql: str, params: tuple[Any, ...] = ()) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
        conn.commit()


def execute_returning(sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
        conn.commit()
        return row
