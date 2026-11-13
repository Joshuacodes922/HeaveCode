from __future__ import annotations

import io
import time
import unittest

from agent.terminal_ui import TerminalUI


class TerminalUITests(unittest.TestCase):
    def test_banner_and_answer_render_without_color_for_non_tty(self) -> None:
        output = io.StringIO()
        ui = TerminalUI(output)

        ui.banner(
            model="qwen3:8b",
            workspace="C:\\demo\\project",
            rag_enabled=True,
            session_id="12345678-abcd",
            resumed=False,
        )
        ui.answer("Ready to help.")

        rendered = output.getvalue()
        self.assertIn("HEAVECODE", rendered)
        self.assertIn("qwen3:8b", rendered)
        self.assertIn("CONNECTED", rendered)
        self.assertIn("C:\\demo\\project", rendered)
        self.assertIn("AGENT >", rendered)
        self.assertIn("Ready to help.", rendered)
        self.assertNotIn("\033[", rendered)

    def test_activity_displays_status_and_stops_cleanly(self) -> None:
        output = io.StringIO()
        ui = TerminalUI(output, color=False)

        with ui.activity("Starting"):
            ui.set_activity_status("Thinking with qwen3:8b")
            time.sleep(0.14)

        rendered = output.getvalue()
        self.assertIn("Thinking with qwen3:8b", rendered)
        self.assertIsNone(ui._spinner_thread)


if __name__ == "__main__":
    unittest.main()
