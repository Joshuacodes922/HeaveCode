"""Terminal entry point for the coding agent."""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv

from agent.agent import CodingAgent
from agent.database import SessionStore
from agent.tools import set_workspace


def main() -> None:
    load_dotenv()
    workspace = os.path.abspath(os.getenv("WORKSPACE_DIR", "."))
    set_workspace(workspace)

    store = SessionStore(os.environ["DATABASE_URL"])
    store.create_tables()
    session_id = input("Session ID (press Enter for a new one): ").strip() or str(uuid.uuid4())
    messages = store.load_messages(session_id)
    agent = CodingAgent(
        model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        verbose_tools=os.getenv("VERBOSE_TOOLS", "false").lower() in {"1", "true", "yes"},
    )

    print("Coding agent ready. Type 'exit' or 'quit' to stop.")
    while True:
        try:
            user_text = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break
        if user_text.lower() in {"exit", "quit"}:
            break
        if not user_text:
            continue

        user_message = {"role": "user", "content": user_text}
        messages.append(user_message)
        store.add_message(session_id, user_message)
        try:
            answer, additions = agent.respond(messages)
        except Exception as error:
            print(f"Agent error: {error}")
            continue

        messages.extend(additions)
        store.add_messages(session_id, additions)
        print(f"\nagent> {answer}")


if __name__ == "__main__":
    main()
