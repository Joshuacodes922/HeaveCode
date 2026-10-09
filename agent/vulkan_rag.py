"""HTTP client and tool schema for the local vkassist Vulkan retrieval service."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


RAG_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_vulkan_docs",
        "description": (
            "Search the local Vulkan and graphics documentation knowledge base. "
            "Always call this tool for questions about graphics pipelines, rendering stages, "
            "swapchains, Vulkan validation VUIDs, API commands, structures, extensions, features, "
            "synchronization, or shader rules."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Precise graphics or Vulkan documentation question."},
                "vuid": {"type": "string", "description": "Optional VUID from a validation message."},
                "limit": {"type": "integer", "description": "Result count from 1 to 5; defaults to 3."},
            },
            "required": ["query"],
        },
    },
}


class VulkanRagError(RuntimeError):
    """A local vkassist service is unavailable or returned an invalid response."""


class VulkanRagClient:
    def __init__(self, base_url: str, timeout_seconds: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def search(self, query: object, vuid: object = None, limit: object = 3) -> str:
        if not isinstance(query, str) or not query.strip():
            raise VulkanRagError("'query' must be a non-empty string")
        if vuid is not None and not isinstance(vuid, str):
            raise VulkanRagError("'vuid' must be a string")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 5:
            raise VulkanRagError("'limit' must be an integer from 1 to 5")

        search_query = f"{vuid.strip()} {query}".strip() if vuid else query.strip()
        body = json.dumps(
            {
                "query": search_query[:1000],
                "limit": limit,
                "rerank": True,
                "context_window": 1,
                "parent_context": False,
            }
        ).encode("utf-8")
        request = Request(
            f"{self.base_url}/v1/search",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as error:
            raise VulkanRagError(f"vk-rag returned HTTP {error.code}") from error
        except URLError as error:
            raise VulkanRagError(f"vk-rag is unavailable at {self.base_url}: {error.reason}") from error
        except TimeoutError as error:
            raise VulkanRagError(f"vk-rag timed out at {self.base_url}") from error
        except json.JSONDecodeError as error:
            raise VulkanRagError("vk-rag returned invalid JSON") from error

        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            raise VulkanRagError("vk-rag response did not contain a results list")
        citations: list[dict[str, Any]] = []
        for result in results:
            if not isinstance(result, dict):
                continue
            citations.append(
                {
                    "document": result.get("document", "unknown"),
                    "section": result.get("section") or "unsectioned",
                    "pages": f"{result.get('page_start', '?')}-{result.get('page_end', '?')}",
                    "api_symbols": result.get("api_symbols", []),
                    "content": str(result.get("content", ""))[:4000],
                    "context": [str(item)[:1000] for item in result.get("context", [])[:2]],
                }
            )
        return json.dumps({"query": search_query, "sources": citations}, ensure_ascii=False)
