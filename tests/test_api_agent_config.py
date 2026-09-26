from __future__ import annotations

import json
import os
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from stock_research.nifty_specialists import api_key_client, quota_limits
from stock_research.research_agent import OpenAICompatibleLLM


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

    def test_openai_compatible_http_adapter_sends_auth_and_parses_json(self) -> None:
        seen: dict[str, object] = {}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                seen["path"] = self.path
                seen["authorization"] = self.headers.get("Authorization")
                length = int(self.headers.get("Content-Length", "0"))
                seen["payload"] = json.loads(self.rfile.read(length))
                body = json.dumps({"choices": [{"message": {"content": '{"ok": true}'}}]}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_args: object) -> None:
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = OpenAICompatibleLLM(f"http://127.0.0.1:{server.server_port}/v1", "test-secret", "test-model")
            client.max_completion_tokens = 17
            self.assertEqual(client("system", "user"), {"ok": True})
            self.assertEqual(seen["path"], "/v1/chat/completions")
            self.assertEqual(seen["authorization"], "Bearer test-secret")
            self.assertEqual(seen["payload"]["model"], "test-model")
            self.assertEqual(seen["payload"]["max_completion_tokens"], 17)
        finally:
            server.shutdown()
            thread.join(timeout=2)
            server.server_close()


if __name__ == "__main__":
    unittest.main()
