"""The Ollama-powered coding agent and its tool execution loop."""

from __future__ import annotations

import json

from ollama import Client

from agent.tools import TOOL_FUNCTIONS, TOOL_SCHEMAS


SYSTEM_PROMPT = """You are a helpful coding agent working in a local project.
Use tools when you need to inspect or change files. Explain completed work briefly.
Only work inside the configured project directory. Do not claim a tool action succeeded
unless its result says it did. You may call multiple tools when needed."""


def text_tool_calls(content: str) -> list[dict]:
    """Read explicit tool-call JSON from models that do not return native calls.

    This is intentionally limited to objects with exactly the expected `name` and
    `arguments` shape. Native Ollama tool calls are always preferred.
    """
    calls: list[dict] = []
    decoder = json.JSONDecoder()
    position = 0
    while True:
        start = content.find("{", position)
        if start == -1:
            return calls
        try:
            value, end = decoder.raw_decode(content[start:])
        except json.JSONDecodeError:
            position = start + 1
            continue
        position = start + end
        if (
            isinstance(value, dict)
            and isinstance(value.get("name"), str)
            and isinstance(value.get("arguments"), dict)
            and set(value).issubset({"name", "arguments"})
        ):
            calls.append({"function": value})


class CodingAgent:
    def __init__(
        self,
        model: str,
        ollama_host: str,
        max_tool_rounds: int = 10,
        verbose_tools: bool = False,
    ):
        self.client = Client(host=ollama_host)
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.verbose_tools = verbose_tools

    def respond(self, messages: list[dict]) -> tuple[str, list[dict]]:
        """Run the model until it returns text without pending tool calls."""
        conversation = [{"role": "system", "content": SYSTEM_PROMPT}, *messages]
        new_messages: list[dict] = []

        for _ in range(self.max_tool_rounds):
            response = self.client.chat(
                model=self.model,
                messages=conversation,
                tools=TOOL_SCHEMAS,
            )

            print(response)
            raw_message = response["message"]
            # ollama returns a Pydantic Message object in recent client versions.
            # Convert it before adding it to the chat history or PostgreSQL session.
            if hasattr(raw_message, "model_dump"):
                assistant_message = raw_message.model_dump(exclude_none=True)
            else:
                assistant_message = dict(raw_message)
            conversation.append(assistant_message)
            new_messages.append(assistant_message)

            calls = assistant_message.get("tool_calls") or text_tool_calls(
                assistant_message.get("content", "")
            )
            if not calls:
               return assistant_message.get("content", ""), new_messages 

            for call in calls:
                name = call["function"]["name"]
                arguments = call["function"].get("arguments", {})
                function = TOOL_FUNCTIONS.get(name)
                if self.verbose_tools:
                    print(f"  [tool] {name}({arguments})")
                if function is None:
                    result = f"Unknown tool: {name}"
                else:
                    try:
                        result = function(**arguments)
                    except Exception as error:  # Return errors to the model for recovery.
                        result = f"Tool error: {error}"

                if self.verbose_tools:
                    print(f"  [tool result] {result}")

                tool_message = {"role": "tool", "content": str(result)}
                conversation.append(tool_message)
                new_messages.append(tool_message)

        return "I stopped after too many tool calls. Please try a more focused request.", new_messages
