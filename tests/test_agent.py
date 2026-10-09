from __future__ import annotations

import tempfile
import unittest

from agent.agent import CodingAgent, text_tool_calls
from agent.observability import EventLogger
from agent.tools import ToolExecutor


class FakeVulkanRag:
    def search(self, **arguments):
        return '{"sources":[{"document":"Vulkan Spec","section":"Barriers","pages":"1-1"}]}'


class ScriptedAgent(CodingAgent):
    def __init__(self, replies, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.replies = iter(replies)

    def _model_call(self, conversation):
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
