"""Optional Supabase service adapter; SQLite remains the default local backend."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SupabaseSettings:
    """Server-only Supabase connection settings loaded without persisting secrets."""

    url: str
    service_role_key: str = field(repr=False)

    @classmethod
    def from_env(cls) -> "SupabaseSettings":
        url = os.environ.get("SUPABASE_URL", "").strip()
        service_role_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        missing = [
            name
            for name, value in (("SUPABASE_URL", url), ("SUPABASE_SERVICE_ROLE_KEY", service_role_key))
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing Supabase environment variable(s): {', '.join(missing)}")
        return cls(url=url, service_role_key=service_role_key)


def create_service_client(settings: SupabaseSettings) -> Any:
    """Create a server-only client for service-managed research ingestion.

    Install the optional dependency first: ``python -m pip install -e .[supabase]``.
    Never use this client or its key in a browser.
    """
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("Install the optional Supabase dependency: pip install -e .[supabase]") from exc
    return create_client(settings.url, settings.service_role_key)


def verify_connection(client: Any) -> int:
    """Return the service-visible security count, proving the Data API connection."""
    response = client.table("securities").select("isin", count="exact").limit(1).execute()
    return response.count if response.count is not None else len(response.data or [])
