"""Terminal entry point for the coding agent."""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv

from agent.agent import CodingAgent
from agent.database import SessionStore
from agent.observability import EventLogger
from agent.tools import ToolExecutor
from agent.vulkan_rag import VulkanRagClient


def approve_write(path: str, old_content: str, new_content: str) -> bool:
    """Show a diff and require a human decision before a file is changed."""
    print(f"\nProposed change: {path}")
    print(ToolExecutor.preview(path, old_content, new_content))
    return input("Apply this change? [y/N]: ").strip().lower() in {"y", "yes"}


def main() -> None:
    load_dotenv()
    workspace = os.path.abspath(os.getenv("WORKSPACE_DIR", "."))
    require_approval = os.getenv("REQUIRE_WRITE_APPROVAL", "true").lower() in {"1", "true", "yes"}
    rag_url = os.getenv("VULKAN_RAG_URL", "").strip()
    vulkan_rag = VulkanRagClient(
        rag_url, timeout_seconds=float(os.getenv("VULKAN_RAG_TIMEOUT_SECONDS", "15"))
    ) if rag_url else None
    tools = ToolExecutor(
        workspace,
        require_write_approval=require_approval,
        approval_callback=approve_write if require_approval else None,
        vulkan_rag=vulkan_rag,
    )
    logger = EventLogger(os.getenv("AGENT_LOG_PATH", "logs/agent.jsonl"))

    store = SessionStore(os.environ["DATABASE_URL"])
    store.create_tables()
    session_id = input("Session ID (press Enter for a new one): ").strip() or str(uuid.uuid4())
    messages = store.load_messages(session_id)
    agent = CodingAgent(
        model=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        tools=tools,
        logger=logger,
        max_tool_rounds=int(os.getenv("MAX_TOOL_ROUNDS", "10")),
        max_history_messages=int(os.getenv("MAX_HISTORY_MESSAGES", "40")),
        verbose_tools=os.getenv("VERBOSE_TOOLS", "false").lower() in {"1", "true", "yes"},
        vulkan_rag=vulkan_rag,
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
            answer, additions = agent.respond(messages, session_id)
        except Exception as error:
            print(f"Agent error: {error}")
            continue

        messages.extend(additions)
        store.add_messages(session_id, additions)
        print(f"\nagent> {answer}")

    logger.close()


if __name__ == "__main__":
    main()
