# Project evaluation summary

## Scope
This report reviews the coding-agent project at the repository root and checks whether the current source, tests, and evaluation assets are still useful to the running app.

## Current health
- Unit tests: 11/11 passing
- Command used: `python -m unittest discover -s tests -v`
- Test focus:
  - tool-call parsing and repair
  - file read/write approval flow
  - workspace escape protection
  - Vulkan RAG tool integration

## What is still actively used
- `main.py` is the entry point for the terminal app.
- `agent/agent.py` drives the model loop and tool execution.
- `agent/tools.py` contains the safe file-shell tool allowlist.
- `agent/database.py` persists session messages in PostgreSQL.
- `agent/observability.py` writes JSONL runtime events.
- `agent/vulkan_rag.py` implements the RAG integration used by the optional Vulkan tool.
- `evals/coding_tasks.jsonl` and `evals/run_evals.py` are the evaluation dataset and runner.
- `tests/` contains the regression suite validating behavior.

## Unused or low-value files
These files do not appear to be part of the active runtime or any import path, and they are not required to run the project:

- `bob.txt` — stray sample file; no references found in the codebase.
- `swapchain.cpp` — standalone C++ sample; not imported, not built, and not referenced by any Python code or config.
- `test.py` — used as an example file in the evaluation dataset but not part of the agent runtime.
- `__pycache__/` — generated Python bytecode cache; should be ignored and removed from source control.
- `logs/` — generated runtime output; not part of runtime logic.

## Special note on generated folders
The project also contains generated dependency folders such as:
- `vk-rag/.venv/`
- `vk-rag/app/frontend/node_modules/`

These are local build artifacts and are not required to be in the source tree. They should be treated as generated environment output, not product source.

## Recommendation
Keep the project lean by removing or excluding the unused root-level artifacts and by treating generated caches and local environment folders as build output.

## Suggested cleanup order
1. Remove `bob.txt` if it is only a scratch artifact.
2. Remove `swapchain.cpp` if it was a one-off sample and not kept intentionally.
3. Keep `test.py` only as a sandbox/example file, not as a project dependency.
4. Ignore generated folders (`__pycache__`, `logs`, `.venv`, `node_modules`) via the repo config.

## Evaluation verdict
The project is in good working condition from a code/test perspective, but it has some obvious clutter and sample files that should be cleaned up to keep the project easier to maintain.
