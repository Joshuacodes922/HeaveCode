"""PostgreSQL persistence for terminal chat sessions."""

from __future__ import annotations

import json
import re

import psycopg

from agent.memory import EpisodeMemory


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
            connection.execute(
                "CREATE INDEX IF NOT EXISTS messages_session_id_id_idx ON messages (session_id, id)"
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS episodic_memories (
                    session_id TEXT PRIMARY KEY,
                    memory JSONB NOT NULL,
                    searchable_text TEXT NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

    def load_episode(self, session_id: str) -> EpisodeMemory | None:
        with psycopg.connect(self.database_url) as connection:
            row = connection.execute(
                "SELECT memory FROM episodic_memories WHERE session_id = %s",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        value = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return EpisodeMemory.from_dict(value)

    def search_episodes(
        self,
        query: str,
        exclude_session_id: str,
        limit: int = 3,
    ) -> list[EpisodeMemory]:
        terms = list(dict.fromkeys(re.findall(r"[A-Za-z0-9_]+", query)))[:20]
        if not terms:
            return []
        tsquery = " | ".join(f"{term}:*" for term in terms)
        with psycopg.connect(self.database_url) as connection:
            rows = connection.execute(
                """SELECT memory
                   FROM episodic_memories
                   WHERE session_id <> %s
                     AND to_tsvector('simple', searchable_text)
                         @@ to_tsquery('simple', %s)
                   ORDER BY ts_rank(
                       to_tsvector('simple', searchable_text),
                       to_tsquery('simple', %s)
                   ) DESC, updated_at DESC
                   LIMIT %s""",
                (exclude_session_id, tsquery, tsquery, limit),
            ).fetchall()
        return [
            EpisodeMemory.from_dict(row[0] if isinstance(row[0], dict) else json.loads(row[0]))
            for row in rows
        ]

    def save_episode(self, session_id: str, memory: EpisodeMemory) -> None:
        searchable_text = " ".join(
            [memory.summary, *memory.facts, *memory.decisions, *memory.preferences, *memory.open_questions]
        )
        with psycopg.connect(self.database_url) as connection:
            connection.execute(
                """INSERT INTO episodic_memories (session_id, memory, searchable_text)
                   VALUES (%s, %s::jsonb, %s)
                   ON CONFLICT (session_id) DO UPDATE SET
                       memory = EXCLUDED.memory,
                       searchable_text = EXCLUDED.searchable_text,
                       updated_at = NOW()""",
                (session_id, json.dumps(memory.to_dict()), searchable_text),
            )

    def delete_episode(self, session_id: str) -> bool:
        with psycopg.connect(self.database_url) as connection:
            result = connection.execute(
                "DELETE FROM episodic_memories WHERE session_id = %s",
                (session_id,),
            )
        return result.rowcount > 0
