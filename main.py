"""Terminal entry point for the coding agent."""

from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv

from agent.agent import CodingAgent
from agent.database import SessionStore
from agent.observability import EventLogger
from agent.terminal_ui import TerminalUI
from agent.tools import ToolExecutor
from agent.vulkan_rag import VulkanRagClient


def approve_write(ui: TerminalUI, path: str, old_content: str, new_content: str) -> bool:
    """Show a diff and require a human decision before a file is changed."""
    with ui.pause_activity():
        ui.notice(f"REVIEW WRITE  {path}")
        print(ToolExecutor.preview(path, old_content, new_content), file=ui.output)
        return input("Apply this change? [y/N]: ").strip().lower() in {"y", "yes"}


def main() -> None:
    load_dotenv()
    ui = TerminalUI()
    workspace = os.path.abspath(os.getenv("WORKSPACE_DIR", "."))
    require_approval = os.getenv("REQUIRE_WRITE_APPROVAL", "true").lower() in {"1", "true", "yes"}
    rag_url = os.getenv("VULKAN_RAG_URL", "").strip()
    vulkan_rag = VulkanRagClient(
        rag_url, timeout_seconds=float(os.getenv("VULKAN_RAG_TIMEOUT_SECONDS", "15"))
    ) if rag_url else None
    tools = ToolExecutor(
        workspace,
        require_write_approval=require_approval,
        approval_callback=(
            lambda path, old, new: approve_write(ui, path, old, new)
        ) if require_approval else None,
        vulkan_rag=vulkan_rag,
    )
    logger = EventLogger(os.getenv("AGENT_LOG_PATH", "logs/agent.jsonl"))

    store = SessionStore(os.environ["DATABASE_URL"])
    store.create_tables()
    session_id = ui.session_prompt() or str(uuid.uuid4())
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
        memory_store=store,
        status_callback=ui.set_activity_status,
    )

    ui.banner(
        model=agent.model,
        workspace=workspace,
        rag_enabled=vulkan_rag is not None,
        session_id=session_id,
        resumed=bool(messages),
    )
    while True:
        try:
            user_text = ui.prompt()
        except (EOFError, KeyboardInterrupt):
            ui.notice("Session ended.")
            break
        if user_text.lower() in {"exit", "quit"}:
            break
        if user_text == ":memory":
            memory = store.load_episode(session_id)
            print(memory.render() if memory else "No episodic memory saved for this session.", file=ui.output)
            continue
        if user_text == ":forget-memory":
            if store.delete_episode(session_id):
                ui.notice("Deleted episodic memory for this session.")
            else:
                ui.notice("No episodic memory was saved for this session.")
            continue
        if not user_text:
            continue

        user_message = {"role": "user", "content": user_text}
        messages.append(user_message)
        store.add_message(session_id, user_message)
        try:
            with ui.activity("Starting agent"):
                answer, additions = agent.respond(messages, session_id)
        except Exception as error:
            ui.notice(f"Agent error: {error}")
            continue

        messages.extend(additions)
        store.add_messages(session_id, additions)
        ui.answer(answer)

    try:
        with ui.activity("Summarizing session memory with local model"):
            saved_memory = agent.distill_session(messages, session_id)
        if saved_memory:
            ui.notice("Saved a concise episodic memory for this session.")
    except Exception as error:
        ui.notice(f"Could not save episodic memory: {error}")
        logger.log("episode_distillation_error", session_id=session_id, error=str(error))
    finally:
        logger.close()


if __name__ == "__main__":
    main()
