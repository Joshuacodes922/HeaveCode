"""Small, safe-by-default tools. Add new tools here as the agent grows."""

from __future__ import annotations

from pathlib import Path

WORKSPACE = Path.cwd().resolve()


def set_workspace(path: str) -> None:
    global WORKSPACE
    WORKSPACE = Path(path).resolve()


def _safe_path(path: str) -> Path:
    candidate = (WORKSPACE / path).resolve()
    if candidate != WORKSPACE and WORKSPACE not in candidate.parents:
        raise ValueError("Path must stay inside the workspace")
    return candidate


def list_files(path: str = ".") -> str:
    """List files and directories below a workspace-relative directory."""
    target = _safe_path(path)
    if not target.is_dir():
        raise ValueError("Path is not a directory")
    entries = sorted(item.relative_to(WORKSPACE).as_posix() for item in target.iterdir())
    return "\n".join(entries) or "(empty directory)"


def read_file(path: str) -> str:
    """Read a UTF-8 text file from the workspace."""
    target = _safe_path(path)
    if not target.is_file():
        raise ValueError("Path is not a file")
    return target.read_text(encoding="utf-8")


def write_file(path: str, content: str) -> str:
    """Create or replace a UTF-8 text file within the workspace."""
    target = _safe_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {target.relative_to(WORKSPACE).as_posix()}"


TOOL_FUNCTIONS = {"list_files": list_files, "read_file": read_file, "write_file": write_file}

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "list_files", "description": "List workspace files.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory path relative to workspace."}}}}},
    {"type": "function", "function": {"name": "read_file", "description": "Read a text file.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path relative to workspace."}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Create or replace a text file.", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "File path relative to workspace."}, "content": {"type": "string", "description": "Full file content."}}, "required": ["path", "content"]}}},
]
