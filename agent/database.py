"""PostgreSQL persistence for terminal chat sessions."""

from __future__ import annotations

import json

import psycopg


class SessionStore:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def create_tables(self) -> None:
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    message JSONB NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )"""
            )

    def load_messages(self, session_id: str) -> list[dict]:
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                "SELECT message FROM messages WHERE session_id = %s ORDER BY id", (session_id,)
            ).fetchall()
        return [row[0] if isinstance(row[0], dict) else json.loads(row[0]) for row in rows]

    def add_message(self, session_id: str, message: dict) -> None:
        self.add_messages(session_id, [message])

    def add_messages(self, session_id: str, messages: list[dict]) -> None:
        if not messages:
            return
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for message in messages:
                    cursor.execute(
                        "INSERT INTO messages (session_id, message) VALUES (%s, %s::jsonb)",
                        (session_id, json.dumps(message)),
                    )
