"""Small, safe-by-default tools. Add new tools here as the agent grows."""

from __future__ import annotations
import subprocess
import difflib
from collections.abc import Callable
from pathlib import Path

from agent.vulkan_rag import RAG_TOOL_SCHEMA, VulkanRagClient, VulkanRagError

WORKSPACE = Path.cwd().resolve()
MAX_FILE_BYTES = 100_000
PROTECTED_PARTS = {".git", ".venv", "__pycache__"}
ApprovalCallback = Callable[[str, str, str], bool]


class ToolError(ValueError):
    """An expected tool failure that can be shown to the model."""


class ToolExecutor:
    """A validated allowlist of workspace-contained file and retrieval tools."""

    def __init__(self, workspace: str | Path, require_write_approval: bool = True,
                 approval_callback: ApprovalCallback | None = None,
                 vulkan_rag: VulkanRagClient | None = None) -> None:
        self.workspace = Path(workspace).resolve()
        if not self.workspace.is_dir():
            raise ToolError("Workspace must be an existing directory")
        self.require_write_approval = require_write_approval
        self.approval_callback = approval_callback
        self.vulkan_rag = vulkan_rag

    def _path(self, value: object) -> Path:
        if not isinstance(value, str) or not value.strip():
            raise ToolError("'path' must be a non-empty string")
        
        candidate = (self.workspace / value).resolve()

        if candidate != self.workspace and self.workspace not in candidate.parents:
            raise ToolError("Path must stay inside the workspace")
        
        parts = candidate.relative_to(self.workspace).parts if candidate != self.workspace else ()

        if any(part in PROTECTED_PARTS or part.startswith(".env") for part in parts):
            raise ToolError("Access to protected files and directories is denied")
        return candidate

    @staticmethod
    def _validate(arguments: object, required: set[str], allowed: set[str]) -> dict:
        if not isinstance(arguments, dict):
            raise ToolError("Tool arguments must be an object")
        if missing := required - set(arguments):
            raise ToolError(f"Missing argument(s): {', '.join(sorted(missing))}")
        if unknown := set(arguments) - allowed:
            raise ToolError(f"Unexpected argument(s): {', '.join(sorted(unknown))}")
        return arguments

    def execute(self, name: str, arguments: object) -> str:

        if name == "list_files":
            args = self._validate(arguments, set(), {"path"})
            return self.list_files(args.get("path", "."))
        if name == "read_file":
            args = self._validate(arguments, {"path"}, {"path"})
            return self.read_file(args["path"])
        if name == "write_file":
            args = self._validate(arguments, {"path", "content"}, {"path", "content"})
            return self.write_file(args["path"], args["content"])
        if name == "delete_file":
            args = self._validate(arguments, {"path"}, {"path"})
            return self.delete_file(args["path"])
        if name == "run_shell":
            args = self._validate(arguments, {"command"}, {"command"})
            return self.run_shell(args["command"])
        if name == "search_vulkan_docs":
            args = self._validate(arguments, {"query"}, {"query", "vuid", "limit"})
            return self.search_vulkan_docs(
                query=args["query"],
                vuid=args.get("vuid"),
                limit=args.get("limit", 3),
            )
        raise ToolError(f"Unknown tool: {name}")

    def get_schemas(self) -> list[dict[str, Any]]:
        """Return the tool schemas available to the model."""
        schemas = [*TOOL_SCHEMAS]
        if self.vulkan_rag is not None:
            schemas.append(RAG_TOOL_SCHEMA)
        return schemas

    def list_files(self, path: str = ".") -> str:
        target = self._path(path)
        if not target.is_dir():
            raise ToolError("Path is not a directory")
        entries = []

        for item in sorted(target.iterdir()):
            if item.name not in PROTECTED_PARTS:
                if not item.name.startswith(".env"):
                    relative_path = item.relative_to(self.workspace)
                    path_string = relative_path.as_posix()
                    entries.append(path_string)
                                   
        return "\n".join(entries) or "(empty directory)"

    def read_file(self, path: str) -> str:
        target = self._path(path)
        if not target.is_file():
            raise ToolError("Path is not a file")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise ToolError(f"File exceeds the {MAX_FILE_BYTES}-byte read limit")
        try:
            return target.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ToolError("Only UTF-8 text files can be read") from error

    def write_file(self, path: str, content: str) -> str:
        if not isinstance(content, str):
            raise ToolError("'content' must be a string")
        if len(content.encode("utf-8")) > MAX_FILE_BYTES:
            raise ToolError(f"Content exceeds the {MAX_FILE_BYTES}-byte write limit")
        target = self._path(path)
        old = target.read_text(encoding="utf-8") if target.exists() else ""
        if self.require_write_approval:
            if self.approval_callback is None:
                raise ToolError("Write requires human approval, but no approval handler is configured")
            if not self.approval_callback(path, old, content):
                return "Write was declined by the user"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {target.relative_to(self.workspace).as_posix()}"

    def delete_file(self, path: str) -> str:
        """Delete one approved, non-protected text file from the workspace."""
        target = self._path(path)
        if not target.is_file():
            raise ToolError("Path is not a file")
        try:
            old = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise ToolError("Only UTF-8 text files can be deleted") from error
        if self.require_write_approval:
            if self.approval_callback is None:
                raise ToolError("Delete requires human approval, but no approval handler is configured")
            if not self.approval_callback(path, old, ""):
                return "Delete was declined by the user"
        target.unlink()
        return f"Deleted {target.relative_to(self.workspace).as_posix()}"

    def run_shell(self, command: str) -> str:
        """Run a shell command in the workspace and return its output."""
        if not isinstance(command, str) or not command.strip():
            raise ToolError("Shell command must be a non-empty string")
        
        try:
            result = subprocess.run(command, shell=True, cwd=self.workspace, capture_output=True, text=True, check=True)
            return result.stdout.strip() or "(no output)"
        except subprocess.CalledProcessError as error:
            raise ToolError(f"Shell command failed with exit code {error.returncode}: {error.stderr.strip()}") from error

    def search_vulkan_docs(self, query: str, vuid: str | None = None, limit: int = 3) -> str:
        """Search the local Vulkan and graphics documentation knowledge base."""
        if self.vulkan_rag is None:
            raise ToolError("Vulkan RAG is not configured")
        try:
            return self.vulkan_rag.search(query=query, vuid=vuid, limit=limit)
        except VulkanRagError as error:
            raise ToolError(str(error)) from error

    @staticmethod
    def preview(path: str, old: str, new: str) -> str:
        diff = difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="")
        return "\n".join(diff)[:8_000] or "(no content change)"


TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "list_files", "description": "List workspace files.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory path relative to workspace."}}}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a text file.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path relative to workspace."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Create or replace a text file.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path relative to workspace."}, "content": {"type": "string", "description": "Full file content."}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "delete_file", "description": "Delete one workspace text file after user approval.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path relative to workspace."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "run_shell", "description": "Run a shell command in the workspace directory and return its output. Use to execute scripts, run tests, compile code, or inspect the environment.", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "The shell command to run."}}, "required": ["command"]}}},
]
