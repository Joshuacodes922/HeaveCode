"""Structured, distilled notes from completed agent sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class EpisodeMemory:
    summary: str
    facts: list[str]
    decisions: list[str]
    preferences: list[str]
    open_questions: list[str]

    @classmethod
    def from_dict(cls, value: object) -> EpisodeMemory:
        if not isinstance(value, dict):
            raise ValueError("Episode memory must be a JSON object")
        summary = value.get("summary")
        if not isinstance(summary, str):
            raise ValueError("Episode memory summary must be a string")
        fields: dict[str, list[str]] = {}
        for name in ("facts", "decisions", "preferences", "open_questions"):
            items = value.get(name)
            if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
                raise ValueError(f"Episode memory {name} must be a list of strings")
            fields[name] = [item.strip()[:500] for item in items if item.strip()][:8]
        return cls(
            summary=summary.strip()[:1200],
            facts=fields["facts"],
            decisions=fields["decisions"],
            preferences=fields["preferences"],
            open_questions=fields["open_questions"],
        )

    def to_dict(self) -> dict[str, str | list[str]]:
        return {
            "summary": self.summary,
            "facts": self.facts,
            "decisions": self.decisions,
            "preferences": self.preferences,
            "open_questions": self.open_questions,
        }

    def render(self) -> str:
        lines = [f"Summary: {self.summary}"]
        for label, items in (
            ("Facts", self.facts),
            ("Decisions", self.decisions),
            ("Preferences", self.preferences),
            ("Open questions", self.open_questions),
        ):
            if items:
                lines.append(f"{label}:")
                lines.extend(f"- {item}" for item in items)
        return "\n".join(lines)


class EpisodeMemoryStore(Protocol):
    def load_episode(self, session_id: str) -> EpisodeMemory | None: ...

    def search_episodes(
        self,
        query: str,
        exclude_session_id: str,
        limit: int = 3,
    ) -> list[EpisodeMemory]: ...

    def save_episode(self, session_id: str, memory: EpisodeMemory) -> None: ...

    def delete_episode(self, session_id: str) -> bool: ...
