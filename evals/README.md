# Agent Evaluation Suite

This directory contains regression tasks and an automated evaluation runner for the coding agent.

## Benchmark Dataset
`coding_tasks.jsonl` contains labeled tasks testing:
- **File System Tools**: `list_files`, `read_file`, `write_file`, `delete_file`
- **Shell Tool**: `run_shell` (executing python scripts, commands)
- **RAG Retrieval Tool**: `search_vulkan_docs` (graphics concepts, VUID validation, swapchains)
- **Security & Sandboxing**: Path traversal rejection, `.env` access denial, human approval write declines

## Running Evaluations

Run the automated evaluation benchmark:

```powershell
python -m evals.run_evals
```

Run with a specific model or output report path:

```powershell
python -m evals.run_evals --model qwen2.5-coder:7b --output evals/reports/qwen_eval.json
```
