"""Ollama agent loop with bounded retries, context, and safe tool execution."""

from __future__ import annotations

import json
import time
from typing import Any

from ollama import Client

from agent.observability import EventLogger
from agent.tools import TOOL_SCHEMAS, ToolExecutor
from agent.vulkan_rag import RAG_TOOL_SCHEMA, VulkanRagClient

SYSTEM_PROMPT = """You are a careful coding agent working in a local project.
Use tools to inspect facts before modifying files or answering technical questions.
Never claim a tool action succeeded unless its tool result says it did.
File writes and deletions require human approval; if declined, explain the outcome.
Work only in the workspace.

For ANY questions about graphics programming, graphics pipelines, rendering stages, swapchains,
Vulkan concepts, validation messages, VUIDs, API rules, extensions, features, shaders, or synchronization:
You MUST call search_vulkan_docs first before giving your explanation or answer.
Never answer graphics or Vulkan questions from memory alone.
Ground your claims in returned sources and cite them as [document, section, pages].

When no more tool calls are needed, give a concise final answer."""


def text_tool_calls(content: str) -> list[dict[str, Any]]:
    """Compatibility parser for explicit text-form tool calls from older models."""
    calls: list[dict[str, Any]] = []
    decoder = json.JSONDecoder()
    position = 0
    while (start := content.find("{", position)) != -1:
        candidate = content[start:]
        try:
            value, end = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            # Models sometimes emit Python's \' inside code embedded in JSON.
            # JSON requires a literal backslash to be written as \\, so repair only
            # that invalid escape and preserve the intended Python source text.
            try:
                value, end = decoder.raw_decode(candidate.replace("\\'", "\\\\'"))
            except json.JSONDecodeError:
                position = start + 1
                continue
            # The repaired text is longer, so no reliable raw offset remains.
            position = len(content)
        else:
            position = start + end
        if isinstance(value, dict) and isinstance(value.get("name"), str) and isinstance(value.get("arguments"), dict) and set(value).issubset({"name", "arguments"}):
            calls.append({"function": value})
    return calls


class CodingAgent:
    def __init__(self, model: str, ollama_host: str, tools: ToolExecutor, logger: EventLogger,
                 max_tool_rounds: int = 10, max_history_messages: int = 40,
                 verbose_tools: bool = False, vulkan_rag: VulkanRagClient | None = None) -> None:
        self.client = Client(host=ollama_host)
        self.model = model
        self.tools = tools
        self.logger = logger
        self.max_tool_rounds = max_tool_rounds
        self.max_history_messages = max_history_messages
        self.verbose_tools = verbose_tools
        if vulkan_rag is not None and getattr(self.tools, "vulkan_rag", None) is None:
            self.tools.vulkan_rag = vulkan_rag
        self.available_tools = self.tools.get_schemas()

    @staticmethod
    def _message_as_dict(message: Any) -> dict[str, Any]:
        return message.model_dump(exclude_none=True) if hasattr(message, "model_dump") else dict(message)

    def _model_call(self, conversation: list[dict[str, Any]]) -> dict[str, Any]:
        for attempt in range(2):
            started = time.perf_counter()
            try:
                response = self.client.chat(model=self.model, messages=conversation, tools=self.available_tools)

                print(f"\n[model response] {response['message'].get('content', '')}")

                self.logger.log("model_call", model=self.model, attempt=attempt + 1,
                                duration_ms=round((time.perf_counter() - started) * 1000))
                return self._message_as_dict(response["message"])
            except Exception as error:
                self.logger.log("model_error", model=self.model, attempt=attempt + 1, error=str(error))
                if attempt == 1:
                    raise
                time.sleep(0.5)
        raise RuntimeError("Unreachable")

    def respond(self, messages: list[dict[str, Any]], session_id: str) -> tuple[str, list[dict[str, Any]]]:
        history = messages[-self.max_history_messages:]
        conversation: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}, *history]

        print("conversation history:")
        for msg in conversation:
            print(f"  [{msg['role']}] {msg.get('content', '')}")

        print("CONVERSATION HISTORY END\n\n\n\n\n")
        additions: list[dict[str, Any]] = []
        self.logger.log("agent_started", session_id=session_id, history_messages=len(history))
        for round_number in range(1, self.max_tool_rounds + 1):
            assistant_message = self._model_call(conversation)

            print(f"\n[assistant] {assistant_message.get('content', '')}")
            conversation.append(assistant_message)
            additions.append(assistant_message)
            calls = assistant_message.get("tool_calls") or text_tool_calls(assistant_message.get("content", ""))

            print(f"  [tool calls] {calls} \n\n\n\n\n")
            if not calls:
                answer = assistant_message.get("content", "")
                self.logger.log("agent_finished", session_id=session_id, rounds=round_number)
                return answer, additions
            for call in calls:
                function = call.get("function", {})
                name, arguments = function.get("name", ""), function.get("arguments", {})
                self.logger.log("tool_requested", session_id=session_id, tool=name, arguments=arguments)
                if self.verbose_tools:
                    print(f"  [tool] {name}({arguments})")
                try:
                    result = self.tools.execute(name, arguments)
                except Exception as error:
                    result = f"Tool error: {error}"
                self.logger.log("tool_finished", session_id=session_id, tool=name, result=result)
                if self.verbose_tools:
                    print(f"  [tool result] {result}")
                tool_message = {"role": "tool", "content": result}
                conversation.append(tool_message)
                additions.append(tool_message)
        answer = "I stopped after the maximum number of tool rounds. Please try a more focused request."
        self.logger.log("agent_stopped", session_id=session_id, reason="tool_round_limit")
        return answer, additions
