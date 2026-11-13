"""Small, dependency-free terminal presentation helpers."""

from __future__ import annotations

import contextlib
import shutil
import sys
import threading
import time
from collections.abc import Generator
from typing import TextIO


class TerminalUI:
    _SPINNER = ("|", "/", "-", "\\")

    def __init__(
        self,
        output: TextIO | None = None,
        *,
        color: bool | None = None,
    ) -> None:
        self.output = output or sys.stdout
        self.color = self.output.isatty() if color is None else color
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._spinner_thread: threading.Thread | None = None
        self._status = "Working"
        self._started_at = 0.0

    def _paint(self, text: str, code: str) -> str:
        if not self.color:
            return text
        return f"\033[{code}m{text}\033[0m"

    def banner(
        self,
        *,
        model: str,
        workspace: str,
        rag_enabled: bool,
        session_id: str,
        resumed: bool,
    ) -> None:
        width = min(max(shutil.get_terminal_size((78, 20)).columns, 56), 88)
        rule = self._paint("=" * width, "36")
        print(f"\n{rule}", file=self.output)
        print(f"  {self._paint('HeaveCode', '1;36')}  LOCAL AI CODING AGENT", file=self.output)
        print("  Tool-using coding assistant | Ollama + workspace tools", file=self.output)
        print(rule, file=self.output)
        print(
            f"  MODEL      {self._paint(model, '1;37')}    "
            f"RAG  {self._paint('CONNECTED' if rag_enabled else 'OFF', '32' if rag_enabled else '33')}",
            file=self.output,
        )
        print(f"  WORKSPACE  {workspace}", file=self.output)
        print(
            f"  SESSION    {session_id[:8]}  ({'resumed' if resumed else 'new'})",
            file=self.output,
        )
        print(self._paint("-" * width, "90"), file=self.output)
        print("  Commands: :memory  :forget-memory  exit", file=self.output)
        print(file=self.output)
        self.output.flush()

    def prompt(self) -> str:
        return input(f"{self._paint('YOU', '1;32')} > ").strip()

    def session_prompt(self) -> str:
        print(f"\n{self._paint('HeaveCode SESSION', '1;36')}")
        print("  Press Enter to start a new conversation, or enter an ID to resume one.")
        return input("  Session ID > ").strip()

    def answer(self, text: str) -> None:
        print(f"\n{self._paint('Agent', '1;36')} >", file=self.output)
        print(text, file=self.output)
        print(file=self.output)
        self.output.flush()

    def notice(self, text: str) -> None:
        print(self._paint(f"  {text}", "90"), file=self.output)
        self.output.flush()

    def start_activity(self, status: str = "Working") -> None:
        with self._lock:
            if self._spinner_thread and self._spinner_thread.is_alive():
                self._status = status
                return
            self._status = status
            self._started_at = time.monotonic()
            self._stop_event.clear()
            self._spinner_thread = threading.Thread(target=self._spin, daemon=True)
            self._spinner_thread.start()

    def set_activity_status(self, status: str | None) -> None:
        if status is None:
            return
        with self._lock:
            self._status = status

    def stop_activity(self) -> None:
        with self._lock:
            thread = self._spinner_thread
            if thread is None:
                return
            self._stop_event.set()
        if thread is not threading.current_thread():
            thread.join()
        with self._lock:
            self.output.write("\r\033[2K")
            self.output.flush()
            self._spinner_thread = None

    def _spin(self) -> None:
        index = 0
        while not self._stop_event.is_set():
            with self._lock:
                elapsed = time.monotonic() - self._started_at
                line = (
                    f"\r{self._paint(self._SPINNER[index % len(self._SPINNER)], '36')} "
                    f"{self._status}  {elapsed:.1f}s"
                )
                self.output.write(line)
                self.output.flush()
            index += 1
            self._stop_event.wait(0.12)

    @contextlib.contextmanager
    def activity(self, status: str = "Working") -> Generator[None, None, None]:
        self.start_activity(status)
        try:
            yield
        finally:
            self.stop_activity()

    @contextlib.contextmanager
    def pause_activity(self) -> Generator[None, None, None]:
        with self._lock:
            thread = self._spinner_thread
            status = self._status
            started_at = self._started_at
            was_running = thread is not None and thread.is_alive()
            if was_running:
                self._stop_event.set()
        if was_running:
            thread.join()
            with self._lock:
                self.output.write("\r\033[2K")
                self.output.flush()
                self._spinner_thread = None
        try:
            yield
        finally:
            if was_running:
                self.start_activity(status)
                with self._lock:
                    self._started_at = started_at
