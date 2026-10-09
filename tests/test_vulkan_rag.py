from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from agent.vulkan_rag import VulkanRagClient, VulkanRagError


class FakeResponse:
    def __init__(self, body: dict) -> None:
        self.body = body

    def read(self) -> bytes:
        return json.dumps(self.body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class VulkanRagClientTests(unittest.TestCase):
    @patch("agent.vulkan_rag.urlopen")
    def test_search_serializes_grounded_sources(self, mock_urlopen) -> None:
        mock_urlopen.return_value = FakeResponse(
            {"results": [{"document": "Vulkan Spec", "section": "Barriers", "page_start": 10,
                          "page_end": 11, "api_symbols": ["vkCmdPipelineBarrier2"],
                          "content": "Barrier rule", "context": ["Nearby rule"]}]}
        )
        result = json.loads(VulkanRagClient("http://rag").search("Explain a barrier", "VUID-test", 1))
        self.assertEqual(result["query"], "VUID-test Explain a barrier")
        self.assertEqual(result["sources"][0]["section"], "Barriers")

    def test_rejects_invalid_tool_arguments(self) -> None:
        client = VulkanRagClient("http://rag")
        with self.assertRaises(VulkanRagError):
            client.search("", limit=3)
        with self.assertRaises(VulkanRagError):
            client.search("query", limit=6)
