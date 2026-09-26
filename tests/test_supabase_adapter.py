from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from stock_research.supabase_adapter import SupabaseSettings, verify_connection


class _FakeExecuteQuery:
    def __init__(self, count: int | None, data: list[dict]) -> None:
        self._count = count
        self._data = data

    def execute(self) -> object:
        return type("Response", (), {"count": self._count, "data": self._data})()


class _FakeSelectQuery:
    def __init__(self, count: int | None, data: list[dict]) -> None:
        self._count = count
        self._data = data

    def limit(self, value: int) -> _FakeExecuteQuery:
        return _FakeExecuteQuery(self._count, self._data)


class _FakeClient:
    def __init__(self, count: int | None, data: list[dict]) -> None:
        self.count = count
        self.data = data
        self.calls: list[tuple[str, str, str | None]] = []

    def table(self, name: str) -> "_FakeClient":
        self.calls.append(("table", name, None))
        return self

    def select(self, columns: str, count: str | None = None) -> _FakeSelectQuery:
        self.calls.append(("select", columns, count))
        return _FakeSelectQuery(self.count, self.data)


class SupabaseSettingsTest(unittest.TestCase):
    def test_settings_require_server_only_values(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "SUPABASE_URL"):
                SupabaseSettings.from_env()

    def test_settings_load_without_exposing_values(self) -> None:
        with patch.dict(
            os.environ,
            {"SUPABASE_URL": "https://example.supabase.co", "SUPABASE_SERVICE_ROLE_KEY": "test-key"},
            clear=True,
        ):
            settings = SupabaseSettings.from_env()
        self.assertEqual(settings.url, "https://example.supabase.co")
        self.assertEqual(settings.service_role_key, "test-key")
        self.assertNotIn("test-key", repr(settings))

    def test_verify_connection_prefers_exact_count(self) -> None:
        client = _FakeClient(count=7, data=[{"isin": "INE000000000"}])
        self.assertEqual(verify_connection(client), 7)
        self.assertEqual(client.calls, [("table", "securities", None), ("select", "isin", "exact")])

    def test_verify_connection_falls_back_to_row_count(self) -> None:
        client = _FakeClient(count=None, data=[{"isin": "A"}, {"isin": "B"}])
        self.assertEqual(verify_connection(client), 2)
