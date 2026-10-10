# Coding agent evaluation

## Scope
This evaluation covers the Python coding agent in the repository root. It focuses on the agent loop, tool execution safety, and the optional Vulkan RAG integration.

## Validation run
Command used:

```powershell
cd "C:\Users\JoshuaS\Documents\mini-coding-agent repo\mini-coding-agent\coding-agent"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Result:
- 12 tests run
- 12 tests passed
- Status: OK

## What the agent currently validates
- text tool-call parsing and repair
- tool result injection back into the conversation
- safe file writes and approvals
- workspace escape and secret denial
- Vulkan RAG tool availability

## Coverage notes
The unit suite confirms the core runtime behaviors expected of the coding agent:

- tool calls are recognized from model output
- write operations are approval-gated when required
- protected paths remain inaccessible
- the agent can access the optional retrieval tool while keeping the rest of the workspace sandboxed

## Strengths
- strong sandboxing model
- explicit approval gate for destructive and mutating actions
- regression tests for core tool logic and security behavior

## Gaps
- the full benchmark runner (`evals/run_evals.py`) depends on a live Ollama model and therefore needs a configured runtime host to exercise the end-to-end agent behavior
- there is no large-scale benchmark report yet for live model quality beyond the unit test suite

## Recommendation
Keep this as the baseline agent validation suite and add real-world task evaluations as the model/toolset changes. The current regression suite is a solid safety baseline, but it is not a substitute for live benchmark scoring against real coding tasks.
