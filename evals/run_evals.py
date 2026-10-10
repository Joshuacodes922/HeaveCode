"""Automated evaluation runner for the Coding Agent across benchmark tasks."""

from __future__ import annotations

import argparse
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv

from agent.agent import CodingAgent
from agent.observability import EventLogger
from agent.tools import ToolExecutor
from agent.vulkan_rag import VulkanRagClient


@dataclass
class EvalResult:
    id: str
    prompt: str
    passed: bool
    tools_called: list[str]
    expected_tools: list[str]
    rounds: int
    duration_ms: float
    error: str | None = None
    notes: str | None = None


def run_single_eval(case: dict, agent: CodingAgent, tools: ToolExecutor) -> EvalResult:
    prompt = case["prompt"]
    case_id = case["id"]
    expected_tools = case.get("expected_tools", [])
    expected_result_substr = case.get("expected_result")

    started = perf_counter()
    tools_called: list[str] = []

    # Intercept tool executions to capture tool usage
    original_execute = tools.execute

    def tracked_execute(name: str, arguments: object) -> str:
        tools_called.append(name)
        return original_execute(name, arguments)

    tools.execute = tracked_execute  # type: ignore[method-assign]

    try:
        messages = [{"role": "user", "content": prompt}]
        answer, additions = agent.respond(messages, session_id=f"eval-{case_id}")
        duration_ms = (perf_counter() - started) * 1000

        # Verification logic
        passed = True
        notes = []

        if expected_tools:
            if not any(tool in tools_called for tool in expected_tools):
                passed = False
                notes.append(f"Expected one of tools {expected_tools}, called {tools_called}")

        if expected_result_substr:
            combined_history = " ".join(
                str(m.get("content", "")) for m in additions
            ) + " " + answer
            if expected_result_substr not in combined_history:
                passed = False
                notes.append(f"Expected snippet '{expected_result_substr}' not found in output")

        rounds = len([m for m in additions if m.get("role") == "assistant"])

        return EvalResult(
            id=case_id,
            prompt=prompt,
            passed=passed,
            tools_called=tools_called,
            expected_tools=expected_tools,
            rounds=rounds,
            duration_ms=round(duration_ms, 2),
            notes="; ".join(notes) if notes else "Passed",
        )
    except Exception as error:
        duration_ms = (perf_counter() - started) * 1000
        return EvalResult(
            id=case_id,
            prompt=prompt,
            passed=False,
            tools_called=tools_called,
            expected_tools=expected_tools,
            rounds=0,
            duration_ms=round(duration_ms, 2),
            error=str(error),
            notes="Agent exception raised during execution",
        )
    finally:
        tools.execute = original_execute  # type: ignore[method-assign]


def run_evals(
    dataset_path: Path,
    output_path: Path | None = None,
    model: str | None = None,
    host: str | None = None,
) -> dict:
    load_dotenv()
    cases = [
        json.loads(line)
        for line in dataset_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    model_name = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    ollama_host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
    rag_url = os.getenv("VULKAN_RAG_URL", "http://127.0.0.1:8000")

    vulkan_rag = VulkanRagClient(rag_url) if rag_url else None

    results: list[EvalResult] = []

    print(f"Starting Agent Evaluation on {len(cases)} cases using model '{model_name}'...\n")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_workspace = Path(temp_dir)
        # Create a dummy README.md and test.py in the sandbox
        (temp_workspace / "README.md").write_text("# Project Docs\n\nSample content.", encoding="utf-8")
        (temp_workspace / "test.py").write_text("print('Hello from test')", encoding="utf-8")

        tools = ToolExecutor(
            workspace=temp_workspace,
            require_write_approval=False,  # auto-approve in automated tests
            vulkan_rag=vulkan_rag,
        )
        logger = EventLogger(f"{temp_dir}/eval_events.jsonl")

        agent = CodingAgent(
            model=model_name,
            ollama_host=ollama_host,
            tools=tools,
            logger=logger,
            max_tool_rounds=5,
        )

        for case in cases:
            # Handle decline test cases with custom approval callback
            if case.get("id") == "declined-write":
                tools.require_write_approval = True
                tools.approval_callback = lambda *_: False
            else:
                tools.require_write_approval = False
                tools.approval_callback = None

            print(f"Running [{case['id']}] {case['prompt'][:50]}...")
            res = run_single_eval(case, agent, tools)
            results.append(res)
            status = "PASS" if res.passed else "FAIL"
            print(f"  -> {status} (tools: {res.tools_called}, {res.duration_ms:.0f}ms)")
            if not res.passed and res.notes:
                print(f"     Reason: {res.notes}")

        logger.close()

    # Aggregate summary
    total = len(results)
    passed_count = sum(1 for r in results if r.passed)
    latencies = sorted(r.duration_ms for r in results)
    percentile_95 = latencies[max(0, math.ceil(0.95 * total) - 1)] if latencies else 0.0

    report = {
        "model": model_name,
        "total_cases": total,
        "passed": passed_count,
        "pass_rate": round(passed_count / total, 4) if total else 0.0,
        "latency_p50_ms": round(latencies[total // 2], 2) if latencies else 0.0,
        "latency_p95_ms": round(percentile_95, 2),
        "results": [asdict(r) for r in results],
    }

    print("\n" + "=" * 60)
    print(f"EVALUATION SUMMARY: {passed_count}/{total} Passed ({report['pass_rate'] * 100:.1f}%)")
    print(f"Latency P50: {report['latency_p50_ms']}ms | P95: {report['latency_p95_ms']}ms")
    print("=" * 60)

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Saved evaluation report to {output_path}")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run evaluation benchmark on the coding agent.")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evals/coding_tasks.jsonl"),
        help="Path to tasks jsonl.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("evals/reports/agent_eval_report.json"),
        help="Path to save evaluation report.",
    )
    parser.add_argument("--model", type=str, default=None, help="Ollama model override.")
    parser.add_argument("--host", type=str, default=None, help="Ollama host override.")
    args = parser.parse_args()

    run_evals(
        dataset_path=args.dataset,
        output_path=args.output,
        model=args.model,
        host=args.host,
    )


if __name__ == "__main__":
    main()
