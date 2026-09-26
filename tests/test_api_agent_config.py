from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from stock_research.nifty_specialists import api_key_client, quota_limits


class ApiAgentConfigTests(unittest.TestCase):
    def test_api_key_client_uses_caller_owned_openai_compatible_settings(self) -> None:
        values = {
            "RESEARCH_LLM_BASE_URL": "https://api.example.test/v1",
            "RESEARCH_LLM_API_KEY": "secret-for-test",
            "RESEARCH_LLM_MODEL": "research-model",
        }
        with patch.dict(os.environ, values, clear=False):
            client = api_key_client()
        self.assertEqual(client.model, "research-model")
        self.assertTrue(client.url.endswith("/chat/completions"))

    def test_api_key_client_rejects_partial_provider_configuration(self) -> None:
        with patch.dict(os.environ, {
            "RESEARCH_LLM_BASE_URL": "https://api.example.test/v1",
            "RESEARCH_LLM_API_KEY": "",
            "RESEARCH_LLM_MODEL": "research-model",
        }, clear=False):
            with self.assertRaisesRegex(ValueError, "RESEARCH_LLM_API_KEY"):
                api_key_client()

    def test_api_key_quota_uses_research_prefix(self) -> None:
        with patch.dict(os.environ, {
            "RESEARCH_LLM_API_KEY": "secret-for-test",
            "RESEARCH_LLM_RPM": "2", "RESEARCH_LLM_RPD": "20",
            "RESEARCH_LLM_TPM": "2000", "RESEARCH_LLM_TPD": "20000",
        }, clear=False):
            self.assertEqual(quota_limits(), {"RPM": 2, "RPD": 20, "TPM": 2000, "TPD": 20000})


if __name__ == "__main__":
    unittest.main()
