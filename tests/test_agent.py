from __future__ import annotations

import json
import tempfile
import unittest

from agent.agent import CodingAgent, text_tool_calls
from agent.memory import EpisodeMemory
from agent.observability import EventLogger
from agent.tools import ToolExecutor


class FakeVulkanRag:
    def search(self, **arguments):
        return '{"sources":[{"document":"Vulkan Spec","section":"Barriers","pages":"1-1"}]}'


class FakeMemoryStore:
    def __init__(self, memories=None):
        self.memories = memories or []
        self.saved = {}
        self.search_query = None

    def load_episode(self, session_id):
        return self.saved.get(session_id)

    def search_episodes(self, query, exclude_session_id, limit=3):
        self.search_query = query
        return self.memories[:limit]

    def save_episode(self, session_id, memory):
        self.saved[session_id] = memory

    def delete_episode(self, session_id):
        return self.saved.pop(session_id, None) is not None


class ScriptedAgent(CodingAgent):
    def __init__(self, replies, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.replies = iter(replies)
        self.conversations = []

    def _model_call(self, conversation):
        self.conversations.append(list(conversation))
        return next(self.replies)


class AgentTests(unittest.TestCase):
    def test_text_tool_call_parser(self) -> None:
        calls = text_tool_calls('Use {"name":"read_file","arguments":{"path":"x.py"}} now')
        self.assertEqual(calls[0]["function"]["name"], "read_file")

    def test_text_tool_call_parser_repairs_python_quote_escape(self) -> None:
        content = r'{"name":"write_file","arguments":{"path":"game.py","content":"print(\'X\')"}}'
        calls = text_tool_calls(content)
        self.assertEqual(calls[0]["function"]["arguments"]["content"], "print(\\'X\\')")

    def test_tool_result_is_added_to_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            tools = ToolExecutor(directory, require_write_approval=False)
            logger = EventLogger(f"{directory}/events.jsonl")
            agent = ScriptedAgent(
                [
                    {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "write_file", "arguments": {"path": "x.txt", "content": "ok"}}}]},
                    {"role": "assistant", "content": "Done."},
                ],
                model="test", ollama_host="http://unused", tools=tools, logger=logger,
            )
            answer, additions = agent.respond([], "test-session")
            self.assertEqual(answer, "Done.")
            self.assertEqual(additions[1]["role"], "tool")
            self.assertEqual((tools.workspace / "x.txt").read_text(), "ok")
            logger.close()

    def test_vulkan_rag_is_available_as_a_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logger = EventLogger(f"{directory}/events.jsonl")
            agent = ScriptedAgent(
                [
                    {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": "search_vulkan_docs", "arguments": {"query": "What is a VUID?"}}}]},
                    {"role": "assistant", "content": "A VUID is documented."},
                ],
                model="test", ollama_host="http://unused",
                tools=ToolExecutor(directory, require_write_approval=False), logger=logger,
                vulkan_rag=FakeVulkanRag(),
            )
            answer, additions = agent.respond([], "vulkan-session")
            self.assertEqual(answer, "A VUID is documented.")
            self.assertIn("Vulkan Spec", additions[1]["content"])
            logger.close()

    def test_vulkan_questions_are_grounded_by_rag_when_model_ignores_the_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logger = EventLogger(f"{directory}/events.jsonl")
            agent = ScriptedAgent(
                [
                    {"role": "assistant", "content": "Validation layers are helper code."},
                    {"role": "assistant", "content": "Grounded answer from docs."},
                ],
                model="test", ollama_host="http://unused",
                tools=ToolExecutor(directory, require_write_approval=False), logger=logger,
                vulkan_rag=FakeVulkanRag(),
            )
            answer, additions = agent.respond([
                {"role": "user", "content": "What is a Vulkan validation layer?"},
            ], "forced-rag-session")
            self.assertEqual(answer, "Grounded answer from docs.")
            self.assertTrue(any(m.get("role") == "tool" for m in additions))
            self.assertTrue(any("Vulkan Spec" in m.get("content", "") for m in additions if m.get("role") == "tool"))
            logger.close()

    def test_relevant_episodic_memory_is_added_to_working_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            logger = EventLogger(f"{directory}/events.jsonl")
            memory_store = FakeMemoryStore([
                EpisodeMemory(
                    summary="The project uses PostgreSQL for chat history.",
                    facts=["The coding agent is built in Python."],
                    decisions=[],
                    preferences=[],
                    open_questions=[],
                ),
            ])
            agent = ScriptedAgent(
                [{"role": "assistant", "content": "I will use the existing PostgreSQL store."}],
                model="test", ollama_host="http://unused",
                tools=ToolExecutor(directory, require_write_approval=False), logger=logger,
                memory_store=memory_store,
            )
            answer, _ = agent.respond([
                {"role": "user", "content": "How does this project persist chat history?"},
            ], "current-session")
            self.assertIn("PostgreSQL", agent.conversations[0][1]["content"])
            self.assertEqual(memory_store.search_query, "How does this project persist chat history?")
            self.assertEqual(answer, "I will use the existing PostgreSQL store.")
            logger.close()

    def test_distill_session_saves_structured_episode_memory(self) -> None:
        class MemoryClient:
            def chat(self, **kwargs):
                return {
                    "message": {
                        "content": (
                            '{"summary":"The project uses PostgreSQL for sessions.",'
                            '"facts":["The agent uses Ollama."],"decisions":["Use a local model."],'
                            '"preferences":["Prefer concise explanations."],"open_questions":[]}'
                        )
                    }
                }

        with tempfile.TemporaryDirectory() as directory:
            log_path = f"{directory}/events.jsonl"
            logger = EventLogger(log_path)
            memory_store = FakeMemoryStore()
            agent = ScriptedAgent(
                [], model="test", ollama_host="http://unused",
                tools=ToolExecutor(directory, require_write_approval=False), logger=logger,
                memory_store=memory_store,
            )
            agent.client = MemoryClient()
            saved = agent.distill_session([
                {"role": "user", "content": "Use PostgreSQL for sessions."},
                {"role": "assistant", "content": "Understood."},
            ], "completed-session")
            self.assertTrue(saved)
            self.assertEqual(
                memory_store.saved["completed-session"].summary,
                "The project uses PostgreSQL for sessions.",
            )
            with open(log_path, encoding="utf-8") as log_file:
                events = [json.loads(line) for line in log_file]
            distilled = next(event for event in events if event["event"] == "episode_distilled")
            self.assertIn("model_duration_ms", distilled)
            self.assertIn("storage_duration_ms", distilled)
            self.assertEqual(distilled["transcript_messages"], 2)
            logger.close()
