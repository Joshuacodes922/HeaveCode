from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.tools import ToolError, ToolExecutor


class ToolExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_write_requires_approval(self) -> None:
        tools = ToolExecutor(self.workspace, approval_callback=lambda *_: False)
        result = tools.execute("write_file", {"path": "hello.txt", "content": "hello"})
        self.assertEqual(result, "Write was declined by the user")
        self.assertFalse((self.workspace / "hello.txt").exists())

    def test_approved_write_and_read(self) -> None:
        tools = ToolExecutor(self.workspace, approval_callback=lambda *_: True)
        self.assertEqual(tools.execute("write_file", {"path": "src/hello.txt", "content": "hello"}), "Wrote src/hello.txt")
        self.assertEqual(tools.execute("read_file", {"path": "src/hello.txt"}), "hello")

    def test_rejects_workspace_escape_and_secrets(self) -> None:
        tools = ToolExecutor(self.workspace, require_write_approval=False)
        with self.assertRaises(ToolError):
            tools.execute("read_file", {"path": "../outside.txt"})
        with self.assertRaises(ToolError):
            tools.execute("write_file", {"path": ".env", "content": "secret"})

    def test_rejects_invalid_arguments(self) -> None:
        tools = ToolExecutor(self.workspace, require_write_approval=False)
        with self.assertRaises(ToolError):
            tools.execute("write_file", {"path": "x.txt"})
        with self.assertRaises(ToolError):
            tools.execute("read_file", {"path": "x.txt", "extra": True})

    def test_approved_delete(self) -> None:
        path = self.workspace / "remove-me.txt"
        path.write_text("temporary", encoding="utf-8")
        tools = ToolExecutor(self.workspace, approval_callback=lambda *_: True)
        self.assertEqual(tools.execute("delete_file", {"path": "remove-me.txt"}), "Deleted remove-me.txt")
        self.assertFalse(path.exists())
